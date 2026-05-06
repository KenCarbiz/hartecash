"""Inbound-message intent classifier (sold / not_for_sale / interested)."""

from fsbo.messaging.intent import classify_inbound


def test_classifies_sold_phrasings():
    for body in [
        "Sold",
        "Yes, sold!",
        "It's been sold",
        "Already sold",
        "Sold it last week",
        "No longer available",
        "Sorry, found a buyer",
        "Already gone",
    ]:
        res = classify_inbound(body)
        assert res.intent == "sold", body


def test_classifies_not_for_sale():
    for body in [
        "Decided to keep it",
        "Took it off the market",
        "Removed the listing",
        "Changed my mind, not selling",
    ]:
        assert classify_inbound(body).intent == "not_for_sale", body


def test_classifies_negative():
    for body in [
        "Not interested",
        "Don't message me",
        "Wrong number",
        "Leave me alone",
    ]:
        assert classify_inbound(body).intent == "negative", body


def test_classifies_interested():
    for body in [
        "Yes still available",
        "$18500",
        "Come see it Tuesday",
        "How much would you offer?",
        "Cash offer?",
    ]:
        assert classify_inbound(body).intent == "interested", body


def test_unknown_for_blank_or_unmatched():
    assert classify_inbound("").intent == "unknown"
    assert classify_inbound(None).intent == "unknown"
    assert classify_inbound("hi").intent == "unknown"
    assert classify_inbound("ok thanks").intent == "unknown"


def test_does_not_misclassify_ambiguous_text():
    """'sold for top dollar' is dealer marketing, not a seller status."""
    res = classify_inbound("My neighbor sold his for top dollar last year")
    assert res.intent != "sold"
