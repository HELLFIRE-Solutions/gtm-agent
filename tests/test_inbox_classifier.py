from gtm_agent.inbox.classifier import classify
from gtm_agent.inbox.models import Classification


def test_pricing_question_is_a_lead():
    classification, reason = classify("What's the pricing for the AI GTM module for a 20-person team?")
    assert classification is Classification.LEAD
    assert "lead-signal" in reason


def test_demo_request_is_a_lead():
    classification, _ = classify("Can we set up a demo call to talk about DSGVO compliance for our onboarding flow?")
    assert classification is Classification.LEAD


def test_seo_spam_is_spam():
    classification, reason = classify("We offer top SEO services and backlinks to boost your ranking fast!")
    assert classification is Classification.SPAM_OR_IRRELEVANT
    assert "spam rule" in reason


def test_url_flood_is_spam():
    classification, _ = classify("check http://spam1.example http://spam2.example http://spam3.example")
    assert classification is Classification.SPAM_OR_IRRELEVANT


def test_greeting_only_is_not_a_lead():
    classification, _ = classify("hi")
    assert classification is Classification.SPAM_OR_IRRELEVANT


def test_empty_message_is_not_a_lead():
    classification, reason = classify("   ")
    assert classification is Classification.SPAM_OR_IRRELEVANT
    assert reason == "empty message"


def test_too_short_generic_message_is_not_a_lead():
    classification, _ = classify("ok cool")
    assert classification is Classification.SPAM_OR_IRRELEVANT


def test_genuine_question_without_keywords_defaults_to_lead():
    classification, reason = classify("How long does it usually take to get one of these set up for a small team?")
    assert classification is Classification.LEAD
    assert "defaulting to lead" in reason
