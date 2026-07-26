"""IMAP reply tracking.

Polls the sending mailbox and matches inbound replies to previously-sent
OutreachDrafts by the In-Reply-To / References headers against the
Message-ID we generated when sending (email_sender.send_outreach). Chosen
over a webhook/provider-specific inbound-parse setup because it works with
any IMAP-capable mailbox and needs no extra infrastructure beyond the
sending mailbox itself — reasonable for HELLFIRE's current volume.
"""

from __future__ import annotations

import email
import imaplib
from datetime import datetime
from email.utils import parsedate_to_datetime

from ..config import Config
from ..models import OutreachDraft, ReplyRecord


class ReplyTrackingError(Exception):
    pass


def check_replies(config: Config, sent_drafts: list[OutreachDraft]) -> list[ReplyRecord]:
    """sent_drafts must all have status == 'sent' and a message_id set."""
    if not all([config.imap_host, config.imap_username, config.imap_password]):
        raise ReplyTrackingError("IMAP is not configured — set IMAP_HOST/IMAP_USERNAME/IMAP_PASSWORD in .env")

    message_id_to_lead = {d.message_id: d.lead_id for d in sent_drafts if d.status == "sent" and d.message_id}
    if not message_id_to_lead:
        return []

    replies: list[ReplyRecord] = []
    with imaplib.IMAP4_SSL(config.imap_host, config.imap_port) as imap:
        imap.login(config.imap_username, config.imap_password)
        imap.select("INBOX")
        status, data = imap.search(None, "ALL")
        if status != "OK":
            raise ReplyTrackingError(f"IMAP search failed: {status}")

        for num in data[0].split():
            status, msg_data = imap.fetch(num, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            in_reply_to = msg.get("In-Reply-To", "")
            references = msg.get("References", "")
            matched_message_id = next(
                (mid for mid in message_id_to_lead if mid in in_reply_to or mid in references),
                None,
            )
            if matched_message_id is None:
                continue

            replies.append(
                ReplyRecord(
                    lead_id=message_id_to_lead[matched_message_id],
                    in_reply_to_message_id=matched_message_id,
                    received_at=_parse_date(msg.get("Date")),
                    snippet=_snippet(msg),
                )
            )

    return replies


def _parse_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.utcnow()
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return datetime.utcnow()


def _snippet(msg: email.message.Message, max_chars: int = 280) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return body.strip()[:max_chars]
