"""Data model for gtm-agent.

The LegitimateInterestRecord is the DSGVO Art. 6(1)(f) documentation gate —
see docs/architecture.md §3. Orchestrator.qualify_and_draft() refuses to
produce an outreach draft for any Lead that lacks one, or whose record has
opted out.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MissingLegitimateInterestError(Exception):
    """Raised when the orchestrator is asked to draft outreach for a lead
    with no recorded legitimate-interest basis, or one that has opted out."""


class LeadSource(str, Enum):
    LINKEDIN_CONNECTION = "linkedin_connection"
    REFERRAL = "referral"
    EVENT = "event"
    INBOUND_ENGAGEMENT = "inbound_engagement"
    OTHER = "other"


class LegitimateInterestRecord(BaseModel):
    source_type: LeadSource
    source_detail: str = Field(min_length=1, description="Concrete fact establishing the connection, e.g. 'mutual connection Jane Doe' or 'commented on HELLFIRE DSGVO post, 2026-06-01'")
    legal_basis: str = "Art. 6(1)(f) GDPR – legitimate interest"
    balancing_test_notes: str = Field(min_length=1, description="Why this outreach does not override the contact's rights/interests")
    recorded_by: str
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    opt_out_at: datetime | None = None
    review_date: date | None = None

    @property
    def is_active(self) -> bool:
        return self.opt_out_at is None


class Lead(BaseModel):
    id: str = Field(description="Stable identifier — typically the email address")
    name: str
    company: str
    email: str
    linkedin_url: str | None = None
    context: str | None = Field(default=None, description="Free-text notes Bob supplies: role, why they matter, recent activity")
    legitimate_interest: LegitimateInterestRecord | None = None
    hubspot_contact_id: str | None = None

    @field_validator("email")
    @classmethod
    def _basic_email_shape(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError(f"not a valid email address: {v!r}")
        return v

    def require_legitimate_interest(self) -> LegitimateInterestRecord:
        if self.legitimate_interest is None:
            raise MissingLegitimateInterestError(
                f"lead {self.id!r} has no LegitimateInterestRecord — add one before qualifying/drafting"
            )
        if not self.legitimate_interest.is_active:
            raise MissingLegitimateInterestError(
                f"lead {self.id!r} opted out at {self.legitimate_interest.opt_out_at} — do not contact"
            )
        return self.legitimate_interest


class QualificationResult(BaseModel):
    lead_id: str
    qualified: bool
    icp_score: int = Field(ge=0, le=100)
    reasoning: str
    qualified_at: datetime = Field(default_factory=datetime.utcnow)


DraftStatus = Literal["draft", "approved", "sent"]


class OutreachDraft(BaseModel):
    lead_id: str
    subject: str
    body: str
    status: DraftStatus = "draft"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: datetime | None = None
    approved_by: str | None = None
    sent_at: datetime | None = None
    message_id: str | None = Field(default=None, description="Email Message-ID header, set once sent — used to match replies")

    def approve(self, by: str) -> None:
        if self.status != "draft":
            raise ValueError(f"cannot approve a draft in status {self.status!r}")
        self.status = "approved"
        self.approved_by = by
        self.approved_at = datetime.utcnow()

    def mark_sent(self, message_id: str) -> None:
        if self.status != "approved":
            raise ValueError(f"cannot send a draft in status {self.status!r} — approve it first")
        self.status = "sent"
        self.message_id = message_id
        self.sent_at = datetime.utcnow()


class ReplyRecord(BaseModel):
    lead_id: str
    in_reply_to_message_id: str
    received_at: datetime
    snippet: str
