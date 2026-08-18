"""Rule-based lead-vs-spam classification for chat widget submissions.

Same reasoning as office-agent's email_triage/classifier.py: deterministic,
testable offline, costs nothing per message, and there is no autonomous
action gated on the result (nothing gets sent or promoted automatically --
Bob reviews `gtm-agent inbox list` himself), so a keyword pass is the right
weight for Stage 1. An LLM pass can replace this later if the false-positive
rate on real traffic turns out to matter.

Rule order matters: spam signals are checked first, so a message that pairs
an obvious spam pattern with an incidental business word still lands as
spam. The lead-signal pass then looks for real intent (pricing, modules,
timelines, compliance). Anything left over defaults to `lead` if it reads
like a genuine question, and to spam/irrelevant only when it's too short or
content-free to be either -- a false lead (an extra row Bob skims past)
costs nothing; a missed lead does.
"""

from __future__ import annotations

import re

from gtm_agent.inbox.models import Classification

_SPAM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("url_flood", re.compile(r"(https?://\S+.*){2,}", re.IGNORECASE | re.DOTALL)),
    (
        "promo_keywords",
        re.compile(
            r"\b(seo services|backlinks?|crypto giveaway|forex|viagra|casino|escort|"
            r"unsubscribe|loan approv\w*|work from home|click here now)\b",
            re.IGNORECASE,
        ),
    ),
    ("repeated_char_spam", re.compile(r"(.)\1{9,}")),
]

_LEAD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "commercial_intent",
        re.compile(
            r"\b(pricing|price|quote|demo|proposal|interested in|hire|contract|"
            r"partnership|timeline|cost|budget|implement|onboard|book a call|"
            r"schedule a call|meeting|consult)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "module_or_domain",
        re.compile(
            r"\b(gtm-agent|office-agent|rag-01|uni-tag|mcp-dev|in-house llm|"
            r"inhouse-llm|compliance-layer|module|dsgvo|gdpr|ai act|"
            r"contractor|specialist|outstaff)\b",
            re.IGNORECASE,
        ),
    ),
]

_GREETING_ONLY = re.compile(r"^\s*(hi|hello|hey|test|testing|hallo|привіт)[.!?\s]*$", re.IGNORECASE)


def classify(message: str) -> tuple[Classification, str]:
    """Return (classification, human-readable reason)."""
    text = message.strip()

    if not text:
        return Classification.SPAM_OR_IRRELEVANT, "empty message"

    for rule_name, pattern in _SPAM_PATTERNS:
        if pattern.search(text):
            return Classification.SPAM_OR_IRRELEVANT, f"matched spam rule: {rule_name}"

    if _GREETING_ONLY.match(text):
        return Classification.SPAM_OR_IRRELEVANT, "greeting/test message only, no content"

    for rule_name, pattern in _LEAD_PATTERNS:
        if pattern.search(text):
            return Classification.LEAD, f"matched lead-signal rule: {rule_name}"

    word_count = len(text.split())
    if word_count < 3:
        return Classification.SPAM_OR_IRRELEVANT, "too short to carry business intent"

    return Classification.LEAD, "no spam signal, reads as a genuine question — defaulting to lead for human review"
