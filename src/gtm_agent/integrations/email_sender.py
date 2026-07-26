"""SMTP outreach sending.

Only ever called on an OutreachDraft with status == "approved" — see
Orchestrator / cli.py `send`. There is no path in this codebase that sends a
"draft"-status message; the CLI enforces the approval gate before this
function is reachable (docs/architecture.md §4).

Needs a verified sending domain (SPF/DKIM/DMARC) — see
docs/demo-ready-criteria.md for the hellfire.dev dependency.
"""

from __future__ import annotations

import smtplib
import uuid
from email.message import EmailMessage

from ..config import Config
from ..models import Lead, OutreachDraft


class EmailSendError(Exception):
    pass


def send_outreach(config: Config, lead: Lead, draft: OutreachDraft) -> str:
    if draft.status != "approved":
        raise ValueError(f"refusing to send a draft in status {draft.status!r} — it must be approved first")
    if not all([config.smtp_host, config.smtp_username, config.smtp_password, config.smtp_from_address]):
        raise EmailSendError("SMTP is not configured — set SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD/SMTP_FROM_ADDRESS in .env")

    message_id = f"<{uuid.uuid4()}@{config.smtp_from_address.split('@')[-1]}>"

    msg = EmailMessage()
    msg["Message-ID"] = message_id
    msg["Subject"] = draft.subject
    msg["From"] = config.smtp_from_address
    msg["To"] = lead.email
    msg.set_content(draft.body)

    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(config.smtp_username, config.smtp_password)
            server.send_message(msg)
    except smtplib.SMTPException as exc:
        raise EmailSendError(f"failed to send outreach to {lead.email}: {exc}") from exc

    return message_id
