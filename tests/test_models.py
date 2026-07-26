from datetime import datetime

import pytest

from gtm_agent.models import (
    Lead,
    LeadSource,
    LegitimateInterestRecord,
    MissingLegitimateInterestError,
    OutreachDraft,
)


def make_lead(**overrides) -> Lead:
    defaults = dict(
        id="jane@example.com",
        name="Jane Doe",
        company="Example GmbH",
        email="jane@example.com",
    )
    defaults.update(overrides)
    return Lead(**defaults)


def make_li_record(**overrides) -> LegitimateInterestRecord:
    defaults = dict(
        source_type=LeadSource.LINKEDIN_CONNECTION,
        source_detail="Connected since 2025, engaged with our DSGVO post",
        balancing_test_notes="Existing connection, single opt-out-able email, proportionate",
        recorded_by="bob",
    )
    defaults.update(overrides)
    return LegitimateInterestRecord(**defaults)


def test_lead_without_legitimate_interest_raises():
    lead = make_lead()
    with pytest.raises(MissingLegitimateInterestError):
        lead.require_legitimate_interest()


def test_lead_with_legitimate_interest_returns_record():
    record = make_li_record()
    lead = make_lead(legitimate_interest=record)
    assert lead.require_legitimate_interest() is record


def test_opted_out_lead_raises_even_with_record():
    record = make_li_record(opt_out_at=datetime.utcnow())
    lead = make_lead(legitimate_interest=record)
    with pytest.raises(MissingLegitimateInterestError):
        lead.require_legitimate_interest()


def test_legitimate_interest_requires_nonempty_balancing_notes():
    with pytest.raises(Exception):
        make_li_record(balancing_test_notes="")


def test_outreach_draft_lifecycle():
    draft = OutreachDraft(lead_id="jane@example.com", subject="Hi", body="Body text")
    assert draft.status == "draft"

    with pytest.raises(ValueError):
        draft.mark_sent("<msg-id>")

    draft.approve(by="bob")
    assert draft.status == "approved"
    assert draft.approved_by == "bob"

    with pytest.raises(ValueError):
        draft.approve(by="bob")

    draft.mark_sent("<msg-id>")
    assert draft.status == "sent"
    assert draft.message_id == "<msg-id>"


def test_lead_rejects_invalid_email():
    with pytest.raises(Exception):
        make_lead(email="not-an-email")
