# gtm-agent — Architecture Decisions (Session 05, Stage 1)

Status: decided in this session (2026-07-20). Supersedes the "open questions" list in the root README.

## 1. Agent orchestration stack

**Decision: a small custom orchestrator on the Anthropic Python SDK (`anthropic` package, tool use / Tool Runner), not LangGraph.**

Rationale:
- The Stage 1 pipeline is a mostly linear pipeline with one real branch point (human approval before send), not an open-ended graph: `ingest leads → qualify → draft outreach → [human approval] → send → track reply → log to CRM`. LangGraph's value is managing complex branching/cyclic graphs; that complexity isn't here yet.
- HELLFIRE's shared droplet is resource-constrained (1 vCPU / ~1.9GB RAM, shared with TETA+PI — see `STATE.md`). LangGraph pulls in a heavier dependency tree (langgraph, langchain-core, checkpointers) for no functional gain at this stage.
- Dogfoods the same stack HELLFIRE sells (Claude API / Anthropic SDK), consistent with the "our own tool is a live example of what we sell" positioning for this module.
- The Anthropic Python SDK's `client.beta.messages.tool_runner()` (see `shared/tool-use-concepts.md` in the claude-api skill) already handles the agentic loop (qualify → decide → draft) without hand-rolling a `while` loop, while staying a thin dependency.

Revisit if: Stage 2's client-configurable framework needs genuine multi-branch workflows per client ICP (e.g. different qualification logic per industry with real conditional routing) — LangGraph or a similar graph library becomes worth the dependency cost then, not before.

Model: `claude-opus-4-8` for qualification/drafting (quality matters more than latency for outbound messages representing the company). Effort `medium`; raise to `high` if qualification accuracy in the field is inconsistent.

## 2. CRM integration

**Decision: HubSpot (Free tier) — confirmed with Bob 2026-07-20.**

Rationale: no cost at HELLFIRE's current warm-lead volume, has a real API (contacts, deals, notes, custom properties, meeting links), and Stage 2's "pluggable into a client's CRM" requirement means the integration is built behind an abstraction (`integrations/hubspot.py` implements a narrow interface) so swapping in Pipedrive or another CRM per-client later doesn't require touching the orchestrator.

HubSpot also has a built-in **Meetings** tool — used for the calendar-booking piece of Stage 1 instead of standing up a separate booking system. A HubSpot contact gets a meeting-scheduling link generated/sent once qualified and approved, avoiding a second integration (Calendly etc.) for something HubSpot already does.

Blocked on: a real HubSpot account + private-app API token for HELLFIRE. Not created in this session (no account access). `integrations/hubspot.py` is written against HubSpot's CRM API v3 contact/note/property shape and is safe to run once `HUBSPOT_API_KEY` is set in `.env` — see `.env.example`.

## 3. Legitimate interest documentation (DSGVO, Art. 6(1)(f))

**Decision:** every contact gets a `LegitimateInterestRecord` (see `src/gtm_agent/models.py`) **before** any outreach draft can be generated for them — enforced in code (`Orchestrator.qualify_and_draft` raises if the record is missing), not just as a process guideline.

Fields, and why each is there:
- `source_type` / `source_detail` — where the lead came from (LinkedIn connection, referral, inbound) and the specific fact establishing a pre-existing connection (e.g. "mutual connection X", "engaged with HELLFIRE's DSGVO compliance post on 2026-06-01"). This is what makes cold outreach *not* mass/unsolicited.
- `legal_basis` — fixed to `"Art. 6(1)(f) GDPR – legitimate interest"` for this module; a placeholder field so the compliance-layer module (session 11) can later swap in a different basis or add a consent-based path without a schema change.
- `balancing_test_notes` — short free-text justification for why HELLFIRE's interest in reaching out doesn't override the contact's rights (required non-empty — this is the actual DSGVO Art. 6(1)(f) balancing test, not a formality).
- `recorded_by` / `recorded_at` — who logged it and when (accountability).
- `opt_out_at` — nullable; once set, the orchestrator refuses to draft or send anything further to that contact.
- `review_date` — periodic re-validation; a stale legitimate-interest basis (e.g. a LinkedIn connection from 3 years ago with no recent interaction) is weaker grounds and should be re-assessed, not assumed to hold forever.

This record is synced to HubSpot as custom contact properties (`legitimate_interest_source`, `legitimate_interest_basis`, `legitimate_interest_recorded_at`, `legitimate_interest_notes`) so it's visible on the contact record itself, not buried in a separate system — auditable by anyone looking at the CRM, and readable by the future compliance-layer module without a new integration.

**Explicit non-goal for Stage 1:** no LinkedIn scraping or automated LinkedIn messaging. LinkedIn's ToS prohibits automated connection/messaging activity, and building that tooling would itself be the kind of legally risky mass-outreach automation this module exists to avoid (see root README: "no mass cold email... legally risky in DACH" — the same logic applies to automated LinkedIn outreach). Leads are added to the pipeline **manually** by Bob (CSV import) after he identifies them on LinkedIn/via referral himself. The agent's job starts after that: qualify, draft, and (on approval) send/track — never scrape or auto-connect.

Coordination note for session 11 (compliance-layer): this schema is intentionally minimal and Stage-1-scoped. When compliance-layer is built, expect it to add an audit/export view over these records rather than changing how they're captured here.

## 4. Human-in-the-loop send gate

Every outbound message (email) requires an explicit approval step before the agent sends it — no autonomous sending. This is:
- A compliance safeguard (a human reviews the legitimate-interest basis and message content before it goes out).
- A quality safeguard (Bob reviews AI-drafted copy before it represents HELLFIRE to a prospect).
- Consistent with this tool's own operating rules around not autonomously sending messages on a user's behalf.

Implemented as a `status` field on each `OutreachDraft` (`draft → approved → sent`); the `cli.py` `send` command only sends drafts with `status == "approved"`, and approval is a separate explicit CLI action (`gtm-agent approve <lead_id>`).
