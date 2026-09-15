"""Reading a photographed order slip.

The fixtures in `tests/fixtures` are real photographs of handwritten orders,
taken on a phone. They are the reason this file exists: everything here was
measured against them rather than imagined, including the failures.

Nothing here calls an OCR service. The recorded strings are what OCR.space
actually returned for those images, so the tests pin the *handling* of a real
engine's output - its strengths and its two known blind spots - without needing
a key or spending anyone's quota.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.ocr import ParsedInvoice, ParsedInvoiceLine
from app.ai.slip import parse_slip
from app.smart_input import party_by_phone, phone_key

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# What OCR.space really returned, verbatim, for four of the slips
# ---------------------------------------------------------------------------
LATHA = """Name: Latha
Ph no: 9880011223
Order:
5 kgs Dal
10 kgs Rice
2 kgs Salt"""

#: Two merged rows and a 1 read as a capital I - both seen on this slip.
IMRAN = """Name: Imran
Ph: 7012345678
Order:
3 boxes Cement
4 bags Sand\tI unit Angle Grinder"""

#: The first item sits on the "Order:" line itself.
SHARMA = """Name: A. Sharma
Ph no: 6969696969
Order: 3 units Product A,
4 bags Product B.
23 kgs Cement bag."""

#: The crossed-out line OCR cannot see, read as if it were live.
MEENA = """Name: Meena
Ph: 9001122334
Order:
3 kgs Sugar
2 kgs Tea Powder
1 kg. Coffee
1 kg Coffee"""


def test_the_fixtures_are_present():
    """If these disappear, every expectation below is meaningless."""
    slips = sorted(FIXTURES.glob("*.jpg"))
    assert len(slips) == 12, f"expected 12 order slips, found {len(slips)}"
    assert all(p.stat().st_size < 400_000 for p in slips), "fixtures should stay small"


# ---------------------------------------------------------------------------
# The slip parser
# ---------------------------------------------------------------------------
def test_a_plain_slip_is_read_completely():
    invoice = parse_slip(LATHA)
    assert invoice.party == "Latha"
    assert invoice.phone == "9880011223"
    assert [(li.quantity, li.product) for li in invoice.lineItems] == [
        (5, "Dal"),
        (10, "Rice"),
        (2, "Salt"),
    ]


def test_a_merged_row_becomes_two_items():
    """The engine sometimes decides two short lines are columns and joins them
    with a tab. Left alone that produces one item called "Sand I unit Angle
    Grinder", which is not a thing anybody sells."""
    invoice = parse_slip(IMRAN)
    assert [(li.quantity, li.product) for li in invoice.lineItems] == [
        (3, "Cement"),
        (4, "Sand"),
        (1, "Angle Grinder"),
    ]


def test_a_capital_i_is_the_number_one():
    """Every OCR engine confuses a handwritten 1 with an I."""
    invoice = parse_slip("Name: X\nOrder:\nI bag White Cement")
    assert [(li.quantity, li.product) for li in invoice.lineItems] == [(1, "White Cement")]


def test_the_first_item_can_share_the_order_line():
    invoice = parse_slip(SHARMA)
    assert invoice.party == "A. Sharma"
    assert invoice.phone == "6969696969"
    quantities = [(li.quantity, li.product) for li in invoice.lineItems]
    assert (3, "Product A") in quantities
    assert (23, "Cement bag") in quantities


def test_unit_words_are_not_part_of_the_product():
    invoice = parse_slip("Order:\n6 m PVC pipe\n2 boxes Taps\n1 pc Wash Basin")
    assert [li.product for li in invoice.lineItems] == ["PVC pipe", "Taps", "Wash Basin"]


def test_a_quantity_less_line_is_not_an_item():
    """A heading or a stray word must not become an order for one of something."""
    invoice = parse_slip("Name: Neha\nPh no: 8056789123\nOrder:\nThanks!\n4 brackets")
    assert [(li.quantity, li.product) for li in invoice.lineItems] == [(4, "brackets")]


def test_an_empty_slip_produces_an_empty_invoice_rather_than_an_error():
    invoice = parse_slip("")
    assert invoice.lineItems == [] and invoice.party is None


def test_the_blind_spot_is_recorded_not_hidden():
    """This is the failure that justifies preferring a vision model.

    OCR.space reads Meena's slip perfectly, including the line she crossed out,
    because a strikethrough is not in the text. Read literally it is two
    kilograms of coffee when she ordered one. The parser cannot fix it and does
    not pretend to - the vision path and the confirm screen are the answer.
    """
    invoice = parse_slip(MEENA)
    coffee = [li for li in invoice.lineItems if li.product.lower() == "coffee"]
    assert len(coffee) == 2, "if this ever becomes 1, OCR.space learned to see strikethrough"
    assert sum(li.quantity for li in coffee) == 2


# ---------------------------------------------------------------------------
# Phone numbers: the only exact key an order slip carries
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "written",
    ["9880011223", "+91 98800 11223", "098800-11223", "+91-9880011223", "91 9880011223"],
)
def test_a_phone_number_is_the_same_however_it_is_written(written):
    assert phone_key(written) == "9880011223"


def test_a_short_number_is_not_padded_into_a_match():
    assert phone_key("12345") == "12345"
    assert party_by_phone([], "12345") is None


def test_a_customer_is_found_by_number_when_the_name_would_never_match():
    class Party:
        def __init__(self, name, phone):
            self.name = name
            self.phone = phone

    parties = [Party("Sharma Kirana Stores", "+919880011223"), Party("Other", "9000000000")]
    # "Latha" is who wrote the slip; the shop is filed under its business name.
    assert party_by_phone(parties, "9880011223") is parties[0]
    assert party_by_phone(parties, "9999999999") is None


def test_two_parties_sharing_a_number_are_not_guessed_between():
    class Party:
        def __init__(self, name, phone):
            self.name = name
            self.phone = phone

    twins = [Party("A", "9880011223"), Party("B", "+91 9880011223")]
    assert party_by_phone(twins, "9880011223") is None


def test_a_party_with_no_number_is_never_matched_by_one():
    class Party:
        def __init__(self, name, phone):
            self.name = name
            self.phone = phone

    assert party_by_phone([Party("A", None), Party("B", "")], "9880011223") is None


# ---------------------------------------------------------------------------
# The whole path, with the engine stubbed
# ---------------------------------------------------------------------------
def test_an_image_becomes_a_draft_against_the_real_catalogue(client, workspace, monkeypatch):
    """Image -> invoice -> the tenant's own products and prices."""
    import base64

    from sqlalchemy import select

    from app import smart_input
    from app.core.db import SessionLocal
    from app.models import Business

    monkeypatch.setattr(smart_input, "has_vision", lambda: True)
    monkeypatch.setattr(
        smart_input,
        "parse_invoice_image",
        lambda *_a, **_k: ParsedInvoice(
            party="Anita Stores",
            phone="9000000001",
            docType="sale",
            lineItems=[ParsedInvoiceLine(product="Cooking Oil", quantity=4)],
        ),
    )

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        draft = smart_input.draft_from_image(
            db, business_id, base64.b64encode(b"x").decode(), "image/png"
        )

    assert draft["partyId"] == workspace["customerId"], draft["partyName"]
    assert draft["items"][0]["productId"] == workspace["productId"]
    assert draft["items"][0]["quantity"] == 4
    assert draft["items"][0]["unitPrice"] > 0, "the price comes from the catalogue"


def test_the_free_engine_is_used_when_there_is_no_vision_key(client, monkeypatch):
    """No AI key is the common case for a new clone, and it should still read a
    slip - just with the engine named on the draft, so the person reviewing
    knows a crossed-out line could be sitting in it."""
    import base64

    from sqlalchemy import select

    from app import smart_input
    from app.ai import ocr_space
    from app.core.db import SessionLocal
    from app.models import Business

    monkeypatch.setattr(smart_input, "has_vision", lambda: False)
    monkeypatch.setattr(ocr_space, "enabled", lambda: True)
    monkeypatch.setattr(ocr_space, "read_text", lambda *_a, **_k: LATHA)

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        draft = smart_input.draft_from_image(
            db, business_id, base64.b64encode(b"x").decode(), "image/png"
        )

    assert draft["engine"] == "OCR.space"
    assert [i["quantity"] for i in draft["items"]] == [5, 10, 2]
    assert draft["partyName"] == "Latha"


def test_with_no_engine_at_all_the_error_says_what_to_do(client, monkeypatch):
    import base64

    from sqlalchemy import select

    from app import smart_input
    from app.ai import ocr_space
    from app.core.db import SessionLocal
    from app.models import Business

    monkeypatch.setattr(smart_input, "has_vision", lambda: False)
    monkeypatch.setattr(ocr_space, "enabled", lambda: False)

    with SessionLocal() as db:
        business_id = db.scalar(select(Business.id).where(Business.name == "Smoke Test Traders"))
        with pytest.raises(ValueError) as err:
            smart_input.draft_from_image(
                db, business_id, base64.b64encode(b"x").decode(), "image/png"
            )

    message = str(err.value)
    assert "GOOGLE_API_KEY" in message and "OCR_SPACE_API_KEY" in message


def test_a_broken_vision_provider_falls_back_instead_of_failing(client, monkeypatch):
    """Both engines configured and the model is having a bad day.

    Erroring out here would be the wrong call: the free engine is right there,
    it reads the handwriting fine, and the draft it produces is labelled with
    its own name so the person reviewing knows to check for a crossed-out line.
    """
    import base64

    from app import smart_input
    from app.ai import ocr_space

    monkeypatch.setattr(smart_input, "has_vision", lambda: True)
    monkeypatch.setattr(
        smart_input,
        "parse_invoice_image",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("503 model overloaded")),
    )
    monkeypatch.setattr(ocr_space, "enabled", lambda: True)
    monkeypatch.setattr(ocr_space, "read_text", lambda *_a, **_k: LATHA)

    invoice, engine = smart_input.read_image(base64.b64encode(b"x").decode(), "image/jpeg")
    assert engine == "ocr.space"
    assert invoice.party == "Latha"


def test_a_broken_vision_provider_with_no_fallback_still_reports_the_error(client, monkeypatch):
    """Nothing to fall back to, so the real cause must reach the caller rather
    than being swallowed into a vaguer message."""
    import base64

    from app import smart_input
    from app.ai import ocr_space

    monkeypatch.setattr(smart_input, "has_vision", lambda: True)
    monkeypatch.setattr(
        smart_input,
        "parse_invoice_image",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("503 model overloaded")),
    )
    monkeypatch.setattr(ocr_space, "enabled", lambda: False)

    with pytest.raises(RuntimeError, match="503"):
        smart_input.read_image(base64.b64encode(b"x").decode(), "image/jpeg")
