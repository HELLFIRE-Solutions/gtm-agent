from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Classification(str, Enum):
    LEAD = "lead"
    SPAM_OR_IRRELEVANT = "spam_or_irrelevant"


class ChatInquiryInput(BaseModel):
    """What the chat widget actually POSTs — pre-classification."""

    message: str = Field(min_length=1, max_length=4000)
    contact_name: str | None = None
    contact_email: str | None = None
    page_path: str | None = None
    session_id: str | None = None


class ChatInquiry(ChatInquiryInput):
    """One submission from the website chat widget, already classified.
    Mirrors marketing.chat_inquiries (migrations/0008 in internal-db) --
    keep the two in sync if either changes.
    """

    source: str = "website_chat"
    classification: Classification
    classification_reason: str


class ChatInquiryRecord(ChatInquiry):
    """A stored inquiry, as read back from the database."""

    id: str
    created_at: datetime
