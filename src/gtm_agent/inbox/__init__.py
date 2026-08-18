"""Website chat widget inbox — receives, classifies, and stores inquiries
from hellfiresol.com's chat widget in internal-db's `marketing` schema.

Deliberately separate from the CSV-driven Lead pipeline in gtm_agent.models:
a chat inquiry is raw and unqualified, closer to office-agent's inbound
email triage than to a curated Lead with a LegitimateInterestRecord. See
docs/architecture.md for how the two relate.
"""
