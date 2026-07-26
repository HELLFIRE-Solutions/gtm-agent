import json
from unittest.mock import MagicMock, patch

import pytest

from gtm_agent.models import LeadSource, LegitimateInterestRecord, Lead, MissingLegitimateInterestError, QualificationResult
from gtm_agent.orchestrator import Orchestrator


def _fake_response(payload: dict):
    block = MagicMock()
    block.type = "text"
    block.text = json.dumps(payload)
    response = MagicMock()
    response.content = [block]
    return response


@pytest.fixture
def qualified_lead() -> Lead:
    return Lead(
        id="jane@example.com",
        name="Jane Doe",
        company="Example GmbH",
        email="jane@example.com",
        context="COO at a 60-person logistics firm, manual order processing bottleneck",
        legitimate_interest=LegitimateInterestRecord(
            source_type=LeadSource.LINKEDIN_CONNECTION,
            source_detail="Connected since 2025, commented on our DSGVO post 2026-06-10",
            balancing_test_notes="Existing connection, proportionate single email",
            recorded_by="bob",
        ),
    )


@patch("gtm_agent.orchestrator.anthropic.Anthropic")
def test_qualify_parses_structured_response(mock_anthropic_cls, qualified_lead):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _fake_response(
        {"qualified": True, "icp_score": 82, "reasoning": "Strong ICP fit: mid-market DACH, manual bottleneck."}
    )
    mock_anthropic_cls.return_value = mock_client

    orchestrator = Orchestrator(api_key="test-key")
    result = orchestrator.qualify(qualified_lead)

    assert isinstance(result, QualificationResult)
    assert result.qualified is True
    assert result.icp_score == 82
    assert result.lead_id == qualified_lead.id


@patch("gtm_agent.orchestrator.anthropic.Anthropic")
def test_draft_outreach_requires_legitimate_interest(mock_anthropic_cls):
    mock_anthropic_cls.return_value = MagicMock()
    orchestrator = Orchestrator(api_key="test-key")

    lead_without_li = Lead(id="x@example.com", name="X", company="Y", email="x@example.com")
    qualification = QualificationResult(lead_id="x@example.com", qualified=True, icp_score=90, reasoning="n/a")

    with pytest.raises(MissingLegitimateInterestError):
        orchestrator.draft_outreach(lead_without_li, qualification)


@patch("gtm_agent.orchestrator.anthropic.Anthropic")
def test_draft_outreach_refuses_unqualified_lead(mock_anthropic_cls, qualified_lead):
    mock_anthropic_cls.return_value = MagicMock()
    orchestrator = Orchestrator(api_key="test-key")

    not_qualified = QualificationResult(lead_id=qualified_lead.id, qualified=False, icp_score=20, reasoning="poor fit")

    with pytest.raises(ValueError):
        orchestrator.draft_outreach(qualified_lead, not_qualified)


@patch("gtm_agent.orchestrator.anthropic.Anthropic")
def test_draft_outreach_references_legitimate_interest_in_prompt(mock_anthropic_cls, qualified_lead):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _fake_response(
        {"subject": "Following up on our LinkedIn chat", "body": "Hi Jane, ..."}
    )
    mock_anthropic_cls.return_value = mock_client

    orchestrator = Orchestrator(api_key="test-key")
    qualification = QualificationResult(lead_id=qualified_lead.id, qualified=True, icp_score=82, reasoning="Strong fit")

    draft = orchestrator.draft_outreach(qualified_lead, qualification)

    assert draft.status == "draft"
    call_kwargs = mock_client.messages.create.call_args.kwargs
    user_message = call_kwargs["messages"][0]["content"]
    assert qualified_lead.legitimate_interest.source_detail in user_message
