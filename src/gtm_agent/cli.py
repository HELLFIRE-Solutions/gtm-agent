"""gtm-agent CLI — see docs/demo-ready-criteria.md for the intended flow.

    gtm-agent import leads.csv
    gtm-agent qualify
    gtm-agent list
    gtm-agent approve <lead_id>
    gtm-agent send
    gtm-agent check-replies
    gtm-agent inbox list
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .config import load_config
from .inbox.db import list_inquiries
from .integrations.email_sender import EmailSendError, send_outreach
from .integrations.hubspot import HubSpotClient, HubSpotError
from .integrations.reply_tracker import ReplyTrackingError, check_replies as imap_check_replies
from .models import LeadSource, LegitimateInterestRecord, Lead, MissingLegitimateInterestError
from .orchestrator import Orchestrator
from .store import PipelineStore


def cmd_import(args: argparse.Namespace) -> None:
    store = PipelineStore()
    with open(args.csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            legitimate_interest = LegitimateInterestRecord(
                source_type=LeadSource(row["source_type"]),
                source_detail=row["source_detail"],
                balancing_test_notes=row["balancing_test_notes"],
                recorded_by=row.get("recorded_by") or "bob",
            )
            lead = Lead(
                id=row.get("id") or row["email"],
                name=row["name"],
                company=row["company"],
                email=row["email"],
                linkedin_url=row.get("linkedin_url") or None,
                context=row.get("context") or None,
                legitimate_interest=legitimate_interest,
            )
            store.add_lead(lead)
            count += 1
    store.save()
    print(f"Imported {count} lead(s) into {store.path}")


def cmd_qualify(args: argparse.Namespace) -> None:
    config = load_config()
    store = PipelineStore()
    orchestrator = Orchestrator(api_key=config.anthropic_api_key)
    hubspot = HubSpotClient(config.hubspot_api_key) if config.hubspot_api_key else None
    if hubspot is None:
        print("warning: HUBSPOT_API_KEY not set — skipping CRM sync (results still saved locally)", file=sys.stderr)

    for lead_id, lead in store.leads.items():
        if lead_id in store.qualifications:
            continue
        try:
            qualification = orchestrator.qualify(lead)
        except MissingLegitimateInterestError as exc:
            print(f"skipping {lead_id}: {exc}", file=sys.stderr)
            continue
        store.qualifications[lead_id] = qualification
        print(f"{lead_id}: qualified={qualification.qualified} score={qualification.icp_score}")

        if hubspot is not None:
            try:
                contact_id = hubspot.upsert_contact(lead)
                lead.hubspot_contact_id = contact_id
                hubspot.log_legitimate_interest(contact_id, lead.legitimate_interest)
                hubspot.log_qualification(contact_id, qualification)
            except HubSpotError as exc:
                print(f"  HubSpot sync failed for {lead_id}: {exc}", file=sys.stderr)

        if qualification.qualified:
            try:
                draft = orchestrator.draft_outreach(lead, qualification)
            except MissingLegitimateInterestError as exc:
                print(f"  cannot draft for {lead_id}: {exc}", file=sys.stderr)
                continue
            store.drafts[lead_id] = draft
            print(f"  drafted outreach: {draft.subject!r}")
            if hubspot is not None and lead.hubspot_contact_id:
                try:
                    hubspot.add_note(lead.hubspot_contact_id, f"[gtm-agent draft, pending approval]\nSubject: {draft.subject}\n\n{draft.body}")
                except HubSpotError as exc:
                    print(f"  HubSpot note failed for {lead_id}: {exc}", file=sys.stderr)

    store.save()


def cmd_list(args: argparse.Namespace) -> None:
    store = PipelineStore()
    for lead_id, lead in store.leads.items():
        qualification = store.qualifications.get(lead_id)
        draft = store.drafts.get(lead_id)
        q_str = f"score={qualification.icp_score} qualified={qualification.qualified}" if qualification else "not qualified yet"
        d_str = f"draft status={draft.status}" if draft else "no draft"
        print(f"{lead_id} ({lead.name}, {lead.company}): {q_str} | {d_str}")


def cmd_approve(args: argparse.Namespace) -> None:
    store = PipelineStore()
    draft = store.drafts.get(args.lead_id)
    if draft is None:
        print(f"no draft found for lead {args.lead_id!r}", file=sys.stderr)
        sys.exit(1)
    draft.approve(by=args.by)
    store.save()
    print(f"approved outreach for {args.lead_id}")


def cmd_send(args: argparse.Namespace) -> None:
    config = load_config()
    store = PipelineStore()
    hubspot = HubSpotClient(config.hubspot_api_key) if config.hubspot_api_key else None

    sent_any = False
    for lead_id, draft in store.drafts.items():
        if draft.status != "approved":
            continue
        lead = store.leads[lead_id]
        try:
            message_id = send_outreach(config, lead, draft)
        except EmailSendError as exc:
            print(f"failed to send to {lead_id}: {exc}", file=sys.stderr)
            continue
        draft.mark_sent(message_id)
        sent_any = True
        print(f"sent outreach to {lead_id} (message-id {message_id})")
        if hubspot is not None and lead.hubspot_contact_id:
            try:
                hubspot.add_note(lead.hubspot_contact_id, f"[gtm-agent] Outreach sent: {draft.subject}")
            except HubSpotError as exc:
                print(f"  HubSpot note failed for {lead_id}: {exc}", file=sys.stderr)

    if not sent_any:
        print("no approved drafts to send")
    store.save()


def cmd_check_replies(args: argparse.Namespace) -> None:
    config = load_config()
    store = PipelineStore()
    hubspot = HubSpotClient(config.hubspot_api_key) if config.hubspot_api_key else None

    sent_drafts = [d for d in store.drafts.values() if d.status == "sent"]
    try:
        replies = imap_check_replies(config, sent_drafts)
    except ReplyTrackingError as exc:
        print(f"reply tracking failed: {exc}", file=sys.stderr)
        sys.exit(1)

    known = {(r.lead_id, r.in_reply_to_message_id) for r in store.replies}
    for reply in replies:
        if (reply.lead_id, reply.in_reply_to_message_id) in known:
            continue
        store.replies.append(reply)
        print(f"reply from {reply.lead_id}: {reply.snippet[:80]!r}")
        lead = store.leads.get(reply.lead_id)
        if hubspot is not None and lead and lead.hubspot_contact_id:
            try:
                hubspot.add_note(lead.hubspot_contact_id, f"[gtm-agent] Reply received: {reply.snippet}")
            except HubSpotError as exc:
                print(f"  HubSpot note failed for {reply.lead_id}: {exc}", file=sys.stderr)

    if not replies:
        print("no new replies")
    store.save()


def cmd_inbox_list(args: argparse.Namespace) -> None:
    config = load_config()
    if not config.database_url:
        print("GTM_AGENT_DATABASE_URL is not set — cannot reach internal-db", file=sys.stderr)
        sys.exit(1)

    inquiries = list_inquiries(config.database_url, limit=args.limit, classification=args.classification)
    if not inquiries:
        print("no chat inquiries found")
        return

    for inquiry in inquiries:
        who = inquiry.contact_name or inquiry.contact_email or "anonymous"
        print(f"[{inquiry.created_at:%Y-%m-%d %H:%M} UTC] {inquiry.classification.value:>18} | {who} | {inquiry.page_path or '-'}")
        print(f"    {inquiry.message[:200]!r}")
        print(f"    reason: {inquiry.classification_reason}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gtm-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="import a CSV of manually-curated leads")
    p_import.add_argument("csv_path", type=Path)
    p_import.set_defaults(func=cmd_import)

    p_qualify = sub.add_parser("qualify", help="qualify all new leads and draft outreach for qualified ones")
    p_qualify.set_defaults(func=cmd_qualify)

    p_list = sub.add_parser("list", help="show pipeline status")
    p_list.set_defaults(func=cmd_list)

    p_approve = sub.add_parser("approve", help="approve a draft for sending")
    p_approve.add_argument("lead_id")
    p_approve.add_argument("--by", default="bob")
    p_approve.set_defaults(func=cmd_approve)

    p_send = sub.add_parser("send", help="send all approved drafts")
    p_send.set_defaults(func=cmd_send)

    p_replies = sub.add_parser("check-replies", help="poll the inbox for replies to sent outreach")
    p_replies.set_defaults(func=cmd_check_replies)

    p_inbox = sub.add_parser("inbox", help="website chat widget inquiries")
    p_inbox_sub = p_inbox.add_subparsers(dest="inbox_command", required=True)
    p_inbox_list = p_inbox_sub.add_parser("list", help="show recent chat widget inquiries from internal-db")
    p_inbox_list.add_argument("--limit", type=int, default=20)
    p_inbox_list.add_argument("--classification", choices=["lead", "spam_or_irrelevant"], default=None)
    p_inbox_list.set_defaults(func=cmd_inbox_list)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
