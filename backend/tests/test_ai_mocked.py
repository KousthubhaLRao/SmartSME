"""The AI path, with the model faked.

These cover the code around the provider rather than the model itself: which
provider gets picked, what the prompt asks for, and — the part that actually
breaks in production — what happens when the model answers badly. Models wrap
JSON in markdown, trail off mid-object, invent fields, and return prose when
asked for none of it, so every one of those is exercised here.

No network, no key, no cost. A real-image OCR suite belongs beside this one and
needs sample bills to be worth writing.
"""

from __future__ import annotations

import json

import pytest

from app.ai import client as ai_client
from app.ai import nlp, ocr
from app.ai.client import AiProvider, extract_json
from app.core.config import settings


@pytest.fixture
def fake_provider(monkeypatch):
    """A provider whose `complete` returns whatever the test wants, and records
    what it was asked."""

    class Fake(AiProvider):
        pass

    calls: list[dict] = []
    reply = {"text": "{}"}

    def complete(self, *, prompt, system=None, image=None, max_tokens=1024):
        calls.append({"prompt": prompt, "system": system, "image": image, "max_tokens": max_tokens})
        if isinstance(reply["text"], Exception):
            raise reply["text"]
        return reply["text"]

    monkeypatch.setattr(AiProvider, "complete", complete)
    provider = AiProvider(
        id="anthropic", label="Test Model", model="test-1", vision=True, api_key="x"
    )
    # **kwargs because callers ask for what they need - `get_provider(vision=True)`
    # for an image - and a stub that cannot take the question is a stub that
    # stops testing the real call.
    stub = lambda **_: provider  # noqa: E731
    monkeypatch.setattr(ai_client, "get_provider", stub)
    monkeypatch.setattr(nlp, "get_provider", stub)
    monkeypatch.setattr(ocr, "get_provider", stub)
    return {"calls": calls, "reply": reply, "provider": provider}


# ---------------------------------------------------------------------------
# Choosing a provider
# ---------------------------------------------------------------------------
def test_no_keys_means_no_provider(monkeypatch):
    for key in ("anthropic_api_key", "openai_api_key", "google_api_key"):
        monkeypatch.setattr(settings, key, "")
    monkeypatch.setattr(settings, "ai_provider", "")
    assert ai_client.get_provider() is None


def test_the_first_configured_provider_wins(monkeypatch):
    for key in ("anthropic_api_key", "openai_api_key", "google_api_key"):
        monkeypatch.setattr(settings, key, "")
    monkeypatch.setattr(settings, "ai_provider", "")
    monkeypatch.setattr(settings, "google_api_key", "g")
    assert ai_client.get_provider().id == "google"

    # Anthropic comes earlier in the order, so adding it takes precedence.
    monkeypatch.setattr(settings, "anthropic_api_key", "a")
    assert ai_client.get_provider().id == "anthropic"


def test_ai_provider_setting_overrides_the_order(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "a")
    monkeypatch.setattr(settings, "google_api_key", "g")
    monkeypatch.setattr(settings, "ai_provider", "google")
    assert ai_client.get_provider().id == "google"


def test_forcing_a_provider_with_no_key_yields_nothing(monkeypatch):
    """Better to fall back to the built-in parser than to call an endpoint with
    an empty key and get a 401 per request."""
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "ai_provider", "openai")
    assert ai_client.get_provider() is None


# ---------------------------------------------------------------------------
# Reading what the model said
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        # Wrapped in a markdown fence, which most chat models do by default.
        ('```json\n{"a": 1}\n```', {"a": 1}),
        # Prose either side of it.
        ('Sure! Here is the JSON:\n{"a": 1}\nLet me know if you need anything.', {"a": 1}),
        ('{"nested": {"b": 2}}', {"nested": {"b": 2}}),
    ],
)
def test_json_is_recovered_from_a_chatty_reply(raw, expected):
    assert extract_json(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "no json here at all",
        '{"truncated": ',  # hit the token limit mid-object
        "[1, 2, 3]",  # a list is not an event
        "{}}{",
    ],
)
def test_unusable_replies_return_none_rather_than_raising(raw):
    assert extract_json(raw) is None


# ---------------------------------------------------------------------------
# Text parsing
# ---------------------------------------------------------------------------
def test_a_good_reply_is_used_and_labelled_with_the_provider(fake_provider):
    fake_provider["reply"]["text"] = json.dumps(
        {
            "eventType": "SALE_CREATED",
            "party": "Anita Stores",
            "product": "Rice",
            "quantity": 5,
            "amount": 700,
            "discountType": "percentage",
            "discountValue": 10,
            "date": "2026-09-01",
        }
    )
    parsed = nlp.parse_command("sold 5 kg rice to Anita Stores")
    assert parsed.eventType == "SALE_CREATED"
    assert parsed.party == "Anita Stores"
    assert parsed.quantity == 5
    assert parsed.discountValue == 10
    assert parsed.date == "2026-09-01"
    # The UI shows which engine read the note.
    assert parsed.engine == "Test Model"


def test_the_prompt_carries_the_note_and_todays_date(fake_provider):
    fake_provider["reply"]["text"] = '{"eventType": "SALE_CREATED"}'
    nlp.parse_command("sold 5 kg rice to Anita")
    prompt = fake_provider["calls"][0]["prompt"]
    assert "sold 5 kg rice to Anita" in prompt
    assert "Today is" in prompt
    assert "JSON" in prompt


def test_the_prompt_asks_for_hindi_and_kannada(fake_provider):
    """The model is told about the languages, and told to leave names in the
    script they arrived in — the catalogue is matched against them raw."""
    fake_provider["reply"]["text"] = '{"eventType": "SALE_CREATED"}'
    nlp.parse_command("ಅನಿತಾಗೆ ೫ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ")
    call = fake_provider["calls"][0]
    blob = f"{call['system']} {call['prompt']}"
    assert "Hindi" in blob and "Kannada" in blob
    assert "do not translate" in blob.lower()
    # And the note reaches the model in its original script, not normalised.
    assert "ಅಕ್ಕಿ" in call["prompt"]


@pytest.mark.parametrize(
    "bad_reply",
    [
        "the shopkeeper sold some rice",  # no JSON
        '{"party": "Anita"}',  # no eventType
        '{"eventType": ',  # truncated
        "",
    ],
)
def test_a_bad_reply_falls_back_to_the_built_in_parser(fake_provider, bad_reply):
    fake_provider["reply"]["text"] = bad_reply
    parsed = nlp.parse_command("sold 5 kg rice to Anita Stores")
    assert parsed.engine == "Heuristic"
    assert parsed.eventType == "SALE_CREATED"
    assert parsed.party == "Anita Stores"


def test_a_provider_that_raises_falls_back_too(fake_provider):
    """A timeout or a 500 must degrade to the built-in parser, not to an error
    on the shopkeeper's screen."""
    fake_provider["reply"]["text"] = ConnectionError("upstream timed out")
    parsed = nlp.parse_command("bought 10 bags sugar from ABC Suppliers")
    assert parsed.engine == "Heuristic"
    assert parsed.eventType == "PURCHASE_CREATED"


def test_nonsense_field_types_do_not_crash_the_parser(fake_provider):
    """Models return strings where numbers belong, and vice versa."""
    fake_provider["reply"]["text"] = json.dumps(
        {
            "eventType": "SALE_CREATED",
            "quantity": "five",
            "amount": "seven hundred",
            "discountValue": None,
            "date": "not a date",
        }
    )
    parsed = nlp.parse_command("sold five kg rice")
    assert parsed.quantity is None
    assert parsed.amount is None
    assert parsed.date is None


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def test_ocr_sends_the_image_and_reads_the_lines(fake_provider):
    fake_provider["reply"]["text"] = json.dumps(
        {
            "party": "ABC Suppliers",
            "docType": "purchase",
            "lineItems": [
                {"product": "Rice", "quantity": 10, "unitPrice": 50},
                {"product": "Sugar", "quantity": 2, "unitPrice": 45.5},
            ],
            "total": 591,
            "date": "2026-09-01",
            "discountType": "none",
            "discountValue": 0,
        }
    )
    invoice = ocr.parse_invoice_image("ZmFrZQ==", "image/png")
    assert invoice.party == "ABC Suppliers"
    assert invoice.docType == "purchase"
    assert [li.product for li in invoice.lineItems] == ["Rice", "Sugar"]
    assert invoice.lineItems[1].unitPrice == 45.5
    assert invoice.total == 591
    assert invoice.date == "2026-09-01"

    sent = fake_provider["calls"][0]["image"]
    assert sent is not None
    assert sent.base64 == "ZmFrZQ=="
    assert sent.media_type == "image/png"


def test_ocr_refuses_a_provider_that_cannot_see(fake_provider):
    fake_provider["provider"].vision = False
    with pytest.raises(ValueError, match="OCR"):
        ocr.parse_invoice_image("ZmFrZQ==", "image/png")


def test_ocr_rejects_a_reply_it_cannot_read(fake_provider):
    fake_provider["reply"]["text"] = "I can't make out this receipt, sorry."
    with pytest.raises(ValueError, match="Could not read"):
        ocr.parse_invoice_image("ZmFrZQ==", "image/png")


def test_ocr_survives_a_half_filled_reply(fake_provider):
    """A crumpled bill gives a model plenty to be unsure about; missing and
    malformed fields have to become defaults, not exceptions."""
    fake_provider["reply"]["text"] = json.dumps(
        {
            "lineItems": [
                {"product": "Rice"},  # no quantity, no price
                {"quantity": "two", "unitPrice": "cheap"},  # unreadable
                "not even an object",
                {"product": "Oil", "quantity": -5, "unitPrice": 100},  # nonsense quantity
            ],
            "total": "illegible",
            "date": "20-08-2026",  # not ISO
            "discountType": "wishful",
            "discountValue": "lots",
        }
    )
    invoice = ocr.parse_invoice_image("ZmFrZQ==", "image/png")
    assert invoice.total is None
    assert invoice.date is None
    assert invoice.discountType == "none"
    assert invoice.discountValue == 0
    # Three usable lines; the string entry is dropped.
    assert len(invoice.lineItems) == 3
    assert invoice.lineItems[0].product == "Rice"
    assert invoice.lineItems[0].quantity == 1
    assert invoice.lineItems[1].product == "Item"
    # A negative quantity is clamped rather than trusted.
    assert invoice.lineItems[2].quantity == 1
    # An unreadable doc type defaults to a sale.
    assert invoice.docType == "sale"
