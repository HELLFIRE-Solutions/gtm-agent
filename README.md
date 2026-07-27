# HELLFIRE AI Solutions — GTM / Sales Agent

Module 1 (priority #1). AI agent for qualifying warm leads (LinkedIn/referrals — no mass cold email, legally risky in DACH), personalized outreach on a manually curated list, and calendar-booking integration.

**Dogfooding:** first runs inside HELLFIRE itself as a real sales tool. Only after proven in real use does a universal template get extracted — a configurable GTM-agent framework for a client's ICP, plugged into their CRM/email/LinkedIn.

## Technical decisions (locked 2026-07-20, details: `docs/architecture.md`)

- **Orchestration:** a custom lightweight orchestrator on the Claude API (`anthropic` SDK, structured outputs), not LangGraph — Stage 1's pipeline is linear enough, and the server is shared and resource-constrained.
- **CRM:** HubSpot Free (free tier, has an API, built-in Meetings tool for booking).
- **Legitimate interest (DSGVO):** every lead has a `LegitimateInterestRecord` — a concrete contact source, a balancing-test note, a recorded date. Without an active record the agent **refuses** to generate outreach (enforced in code, not just a process requirement).
- **Stage 1 demo-ready criterion:** locked in with Bob — a human-in-the-loop pipeline with real email sending and reply tracking. Details: `docs/demo-ready-criteria.md`.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in ANTHROPIC_API_KEY, HUBSPOT_API_KEY, SMTP_*/IMAP_*

gtm-agent import data/leads.example.csv   # or your own CSV of manually curated leads
gtm-agent qualify                          # qualification + outreach draft + HubSpot sync
gtm-agent list
gtm-agent approve <lead_id>                # human approves before sending
gtm-agent send                             # real send (needs SMTP + a verified domain)
gtm-agent check-replies                    # IMAP reply polling, logged to HubSpot
```

`pytest tests/` — 10 tests, covering the data model (including legitimate-interest gate enforcement) and the orchestrator (Claude API mocked).

## Known blocker before going live

Real email sending (steps 7-8 in the demo-ready criteria) needs a verified sending domain (SPF/DKIM/DMARC) — `hellfiresol.com` (session 02/03). Until then — qualification, drafting, HubSpot sync, and meeting-link generation are fully working and demoable.

**Status:** Stage 1 — code ready, waiting on a HubSpot account (no access in this session) and a domain for live sending. Not tested on real leads yet.

**License:** MIT.
