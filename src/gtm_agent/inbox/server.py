"""Minimal HTTP endpoint for the hellfiresol.com chat widget.

Stdlib http.server, not a framework — this is one POST route and a health
check, and the shared session-02 droplet is resource-constrained (1 vCPU,
~1.9GB shared with TETA+PI, see STATE.md). Every submission is classified
(gtm_agent.inbox.classifier) and written for real to internal-db's
marketing.chat_inquiries (gtm_agent.inbox.db) — nothing here fakes a reply
or drops a message on the floor.

Run: GTM_AGENT_DATABASE_URL=... python -m gtm_agent.inbox.server
"""

from __future__ import annotations

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pydantic import ValidationError

from gtm_agent.inbox.classifier import classify
from gtm_agent.inbox.db import insert_inquiry
from gtm_agent.inbox.models import ChatInquiry, ChatInquiryInput

logger = logging.getLogger("gtm_agent.inbox")

MAX_BODY_BYTES = 8192

LEAD_REPLY = (
    "Thanks — that's logged. A person from HELLFIRE will follow up directly, "
    "not a bot. If you'd rather move now, reach us at hello@hellfire.ai."
)
FALLBACK_REPLY = (
    "Got it — logged for a human to look at. If this needs a faster answer, "
    "email hello@hellfire.ai directly."
)
ERROR_REPLY = (
    "That didn't save on our end — please try again, or email hello@hellfire.ai directly."
)


def _database_url() -> str:
    dsn = os.environ.get("GTM_AGENT_DATABASE_URL")
    if not dsn:
        raise RuntimeError("GTM_AGENT_DATABASE_URL is not set (postgresql://marketing_app:...@host:5432/db)")
    return dsn


def _allowed_origins() -> list[str]:
    raw = os.environ.get("INBOX_ALLOWED_ORIGINS", "https://hellfiresol.com,https://www.hellfiresol.com")
    return [o.strip() for o in raw.split(",") if o.strip()]


class InboxHandler(BaseHTTPRequestHandler):
    server_version = "gtm-agent-inbox/0.1"

    def _cors_origin(self) -> str | None:
        origin = self.headers.get("Origin")
        if origin and origin in _allowed_origins():
            return origin
        return None

    def _send_json(self, status: int, payload: dict, origin: str | None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        origin = self._cors_origin()
        self.send_response(204)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(200, {"status": "ok"}, origin=None)
            return
        self._send_json(404, {"error": "not found"}, origin=None)

    def do_POST(self) -> None:
        origin = self._cors_origin()
        if self.path != "/api/inbox":
            self._send_json(404, {"error": "not found"}, origin)
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(400, {"error": "invalid content length"}, origin)
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
            data = ChatInquiryInput.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            self._send_json(400, {"error": f"invalid request: {exc}"}, origin)
            return

        classification, reason = classify(data.message)
        inquiry = ChatInquiry(
            **data.model_dump(),
            classification=classification,
            classification_reason=reason,
        )

        reply = LEAD_REPLY if classification.value == "lead" else FALLBACK_REPLY
        try:
            insert_inquiry(_database_url(), inquiry)
        except Exception:
            logger.exception("failed to store chat inquiry")
            self._send_json(200, {"reply": ERROR_REPLY, "stored": False}, origin)
            return

        self._send_json(200, {"reply": reply, "stored": True}, origin)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        logger.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(message)s")
    _database_url()  # fail fast if misconfigured
    port = int(os.environ.get("INBOX_PORT", "8090"))
    host = os.environ.get("INBOX_HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), InboxHandler)
    logger.info("gtm-agent inbox server listening on %s:%s", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
