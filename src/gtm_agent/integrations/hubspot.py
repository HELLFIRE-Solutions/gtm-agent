"""HubSpot CRM integration.

Chosen per docs/architecture.md §2 (HubSpot Free — confirmed with Bob,
2026-07-20). Kept behind this narrow interface (upsert_contact /
log_legitimate_interest / add_note / attach_meeting_link) so Etap 2 can swap
in a different CRM per client without touching the orchestrator.

Requires custom contact properties to exist in the HubSpot portal before
first use (Settings -> Properties -> Contact properties):
  legitimate_interest_source   (single-line text)
  legitimate_interest_basis    (single-line text)
  legitimate_interest_recorded_at (date picker)
  legitimate_interest_notes    (multi-line text)
  gtm_icp_score                (number)
  gtm_qualified                (single checkbox / boolean)
"""

from __future__ import annotations

import requests

from ..models import LegitimateInterestRecord, Lead, QualificationResult

_BASE_URL = "https://api.hubapi.com"


class HubSpotError(Exception):
    pass


class HubSpotClient:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("HubSpot API key is required")
        self._session = requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    def find_contact_id_by_email(self, email: str) -> str | None:
        resp = self._session.post(
            f"{_BASE_URL}/crm/v3/objects/contacts/search",
            json={
                "filterGroups": [
                    {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
                ],
                "limit": 1,
            },
            timeout=15,
        )
        _raise_for_status(resp)
        results = resp.json().get("results", [])
        return results[0]["id"] if results else None

    def upsert_contact(self, lead: Lead) -> str:
        properties = {
            "email": lead.email,
            "firstname": lead.name.split(" ", 1)[0],
            "lastname": lead.name.split(" ", 1)[1] if " " in lead.name else "",
            "company": lead.company,
        }
        if lead.linkedin_url:
            properties["linkedin_url"] = lead.linkedin_url

        existing_id = self.find_contact_id_by_email(lead.email)
        if existing_id:
            resp = self._session.patch(
                f"{_BASE_URL}/crm/v3/objects/contacts/{existing_id}",
                json={"properties": properties},
                timeout=15,
            )
            _raise_for_status(resp)
            return existing_id

        resp = self._session.post(
            f"{_BASE_URL}/crm/v3/objects/contacts",
            json={"properties": properties},
            timeout=15,
        )
        _raise_for_status(resp)
        return resp.json()["id"]

    def log_legitimate_interest(self, contact_id: str, record: LegitimateInterestRecord) -> None:
        resp = self._session.patch(
            f"{_BASE_URL}/crm/v3/objects/contacts/{contact_id}",
            json={
                "properties": {
                    "legitimate_interest_source": record.source_type.value,
                    "legitimate_interest_basis": record.legal_basis,
                    "legitimate_interest_recorded_at": record.recorded_at.date().isoformat(),
                    "legitimate_interest_notes": f"{record.source_detail} | balancing test: {record.balancing_test_notes}",
                }
            },
            timeout=15,
        )
        _raise_for_status(resp)

    def log_qualification(self, contact_id: str, qualification: QualificationResult) -> None:
        resp = self._session.patch(
            f"{_BASE_URL}/crm/v3/objects/contacts/{contact_id}",
            json={
                "properties": {
                    "gtm_icp_score": qualification.icp_score,
                    "gtm_qualified": qualification.qualified,
                }
            },
            timeout=15,
        )
        _raise_for_status(resp)

    def add_note(self, contact_id: str, body: str) -> str:
        resp = self._session.post(
            f"{_BASE_URL}/crm/v3/objects/notes",
            json={
                "properties": {"hs_note_body": body, "hs_timestamp": _now_ms()},
                "associations": [
                    {
                        "to": {"id": contact_id},
                        "types": [
                            {
                                # HubSpot's default note-to-contact association type ID.
                                # Verify against a live portal (Settings -> Objects ->
                                # Associations) once the account exists — this wasn't
                                # testable without HubSpot access in this session.
                                "associationCategory": "HUBSPOT_DEFINED",
                                "associationTypeId": 202,
                            }
                        ],
                    }
                ],
            },
            timeout=15,
        )
        _raise_for_status(resp)
        return resp.json()["id"]


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _raise_for_status(resp: requests.Response) -> None:
    if resp.status_code >= 400:
        raise HubSpotError(f"HubSpot API {resp.status_code}: {resp.text}")
