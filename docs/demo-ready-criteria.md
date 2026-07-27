# Stage 1 — "Demo-ready" criteria (locked in with Bob, 2026-07-20)

Bob selected the **expanded** option: human-in-the-loop pipeline plus real sending and reply tracking.

Stage 1 is demo-ready when the agent, running against a real (small, manually-curated) HELLFIRE lead list, can:

1. **Ingest** a manually curated list of warm leads (CSV: name, company, LinkedIn URL/context, source, legitimate-interest detail) — ≥10 real contacts.
2. **Qualify** each lead against a simple ICP rubric, with Claude's reasoning attached to the record (not just a score).
3. **Draft** a personalized outreach email per qualified lead that explicitly references the specific legitimate-interest reason for contacting them (not generic mail-merge copy).
4. **Refuse to draft** for any contact missing a `LegitimateInterestRecord` or with `opt_out_at` set — enforced in code, verified by a test.
5. **Log** the legitimate-interest record and qualification result to HubSpot as contact properties, visible on the contact record.
6. **Hold for human approval** — no message leaves the system without an explicit `approve` action from Bob.
7. **Send** the approved email for real (via SMTP through a verified sending domain).
8. **Track replies** — an IMAP poll against the sending mailbox matches replies to the original outreach (by thread/Message-ID) and logs the reply (received, timestamp, snippet) onto the HubSpot contact/deal timeline.
9. **Offer a booking path** — once a lead replies positively (or on demand), the agent can attach/send a HubSpot Meetings scheduling link for a demo call.

## Known blocker before criterion 7–8 can run live

Real sending needs a **verified sending domain** (SPF/DKIM/DMARC configured) and SMTP credentials. `hellfire.dev` is expected to be purchased 2026-07-21 (per `STATE.md`) — this blocks live email sending until the domain exists and DNS records are set up (session 02/03 territory). Until then, criteria 1–6 and 9 (drafting-through-HubSpot-logging, plus meeting-link generation) are fully runnable and demoable; 7–8 (live send + reply tracking) are code-complete but need the domain to actually execute end-to-end.

Also needs: a real HubSpot account + API token (see `docs/architecture.md` §2) — no account was created in this session since it requires Bob's sign-up.

## What "demo to a client" looks like concretely

Bob picks 10–15 real HELLFIRE prospects he's already connected to on LinkedIn or has a referral path to. He drops them into a CSV with a one-line note on *why* each is a legitimate contact (the source of the legitimate-interest record). He runs `gtm-agent qualify leads.csv`, reviews the qualification + drafts, approves the good ones, and the agent sends and starts tracking replies — live, on a real name-brand HubSpot instance he can screen-share. That's the same tool a client would get configured for their own list.
