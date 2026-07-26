"""Custom lightweight orchestrator for gtm-agent Etap 1.

Deliberately not LangGraph — see docs/architecture.md §1 for the reasoning.
The pipeline is linear enough (qualify -> draft -> [human approval] -> send
-> track reply) that a couple of direct Claude API calls plus explicit
Python control flow is simpler to run and reason about than a graph
framework, especially on HELLFIRE's resource-constrained shared server.
"""

from __future__ import annotations

import json

import anthropic

from .models import Lead, MissingLegitimateInterestError, OutreachDraft, QualificationResult
from .prompts import DEFAULT_ICP_RUBRIC, DRAFT_SYSTEM_PROMPT, QUALIFICATION_SYSTEM_PROMPT

MODEL = "claude-opus-4-8"

_QUALIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "qualified": {"type": "boolean"},
        "icp_score": {"type": "integer", "description": "0-100 fit score against the ICP rubric"},
        "reasoning": {"type": "string", "description": "Specific, grounded reasoning citing the lead's actual context"},
    },
    "required": ["qualified", "icp_score", "reasoning"],
    "additionalProperties": False,
}

_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["subject", "body"],
    "additionalProperties": False,
}


class Orchestrator:
    def __init__(self, api_key: str | None = None, icp_rubric: str = DEFAULT_ICP_RUBRIC) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._icp_rubric = icp_rubric

    def qualify(self, lead: Lead) -> QualificationResult:
        response = self._client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=QUALIFICATION_SYSTEM_PROMPT.format(icp_rubric=self._icp_rubric),
            output_config={"format": {"type": "json_schema", "schema": _QUALIFICATION_SCHEMA}},
            messages=[{"role": "user", "content": self._lead_context(lead)}],
        )
        data = json.loads(_first_text(response))
        return QualificationResult(lead_id=lead.id, **data)

    def draft_outreach(self, lead: Lead, qualification: QualificationResult) -> OutreachDraft:
        """Raises MissingLegitimateInterestError if the lead has no active
        LegitimateInterestRecord — this is the DSGVO enforcement gate, not
        just a warning. See docs/architecture.md §3."""
        legitimate_interest = lead.require_legitimate_interest()
        if not qualification.qualified:
            raise ValueError(f"lead {lead.id!r} was not qualified (score {qualification.icp_score}) — do not draft outreach")

        user_content = (
            f"{self._lead_context(lead)}\n\n"
            f"Legitimate interest basis (must be referenced concretely in the email):\n"
            f"- Source: {legitimate_interest.source_type.value}\n"
            f"- Detail: {legitimate_interest.source_detail}\n\n"
            f"Qualification reasoning:\n{qualification.reasoning}"
        )
        response = self._client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=DRAFT_SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": _DRAFT_SCHEMA}},
            messages=[{"role": "user", "content": user_content}],
        )
        data = json.loads(_first_text(response))
        return OutreachDraft(lead_id=lead.id, subject=data["subject"], body=data["body"])

    @staticmethod
    def _lead_context(lead: Lead) -> str:
        lines = [
            f"Name: {lead.name}",
            f"Company: {lead.company}",
            f"Email: {lead.email}",
        ]
        if lead.linkedin_url:
            lines.append(f"LinkedIn: {lead.linkedin_url}")
        if lead.context:
            lines.append(f"Context: {lead.context}")
        return "\n".join(lines)


def _first_text(response: anthropic.types.Message) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    raise RuntimeError("Claude response had no text block")
