"""Minimal local JSON-file pipeline store.

Stage 1 scope: HubSpot is the system of record for anything client-facing
(see docs/architecture.md §2); this file just lets the CLI persist
in-progress state (qualifications, drafts, send status) between separate
command invocations without standing up a database. Stage 2 can replace this
with whatever the target client's stack already uses.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Lead, OutreachDraft, QualificationResult, ReplyRecord

DEFAULT_STORE_PATH = Path("data/pipeline_state.json")


class PipelineStore:
    def __init__(self, path: Path = DEFAULT_STORE_PATH) -> None:
        self.path = path
        self.leads: dict[str, Lead] = {}
        self.qualifications: dict[str, QualificationResult] = {}
        self.drafts: dict[str, OutreachDraft] = {}
        self.replies: list[ReplyRecord] = []
        if self.path.exists():
            self._load()

    def add_lead(self, lead: Lead) -> None:
        self.leads[lead.id] = lead

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "leads": {k: json.loads(v.model_dump_json()) for k, v in self.leads.items()},
            "qualifications": {k: json.loads(v.model_dump_json()) for k, v in self.qualifications.items()},
            "drafts": {k: json.loads(v.model_dump_json()) for k, v in self.drafts.items()},
            "replies": [json.loads(r.model_dump_json()) for r in self.replies],
        }
        self.path.write_text(json.dumps(payload, indent=2, default=str))

    def _load(self) -> None:
        payload = json.loads(self.path.read_text())
        self.leads = {k: Lead.model_validate(v) for k, v in payload.get("leads", {}).items()}
        self.qualifications = {
            k: QualificationResult.model_validate(v) for k, v in payload.get("qualifications", {}).items()
        }
        self.drafts = {k: OutreachDraft.model_validate(v) for k, v in payload.get("drafts", {}).items()}
        self.replies = [ReplyRecord.model_validate(r) for r in payload.get("replies", [])]
