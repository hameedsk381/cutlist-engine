"""The branded client quote: studio details, logo, the price a client may see, and the PDF."""
from __future__ import annotations

import io

import pytest

from cutlist_engine.saas.brand import normalise_brand
from cutlist_engine.saas.quote_pdf import money, price_lines

from test_saas import _auth, _described_project, _signup, client  # noqa: F401 - pytest fixture

pypdf = pytest.importorskip("pypdf")

TOTALS = {"currency": "INR", "material": 40000.0, "edge_banding": 2000.0, "hardware": 8000.0,
          "labour": 10000.0, "other": 0.0, "subtotal": 60000.0, "margin": 9000.0, "total": 69000.0}


def _text(pdf_bytes: bytes) -> str:
    return "\n".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages)


def _png(width=200, height=80) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (width, height), (15, 118, 110)).save(out, "PNG")
    return out.getvalue()


def _quoted_project(client, email="designer@example.com"):  # noqa: F811
    token = _signup(client, email)["token"]
    project_id = _described_project(client, token)["id"]
    saved = client.put(
        f"/api/projects/{project_id}/settings",
        json={"quote": {"labour": 12000, "hardware": 5000, "margin_percent": 20, "customer": "Mrs Rao",
                        "note": "Delivery in 3 weeks."}},
        headers=_auth(token),
    )
    assert saved.status_code == 200, saved.text
    return token, project_id


# ---- the numbers -----------------------------------------------------------

def test_rupees_use_indian_grouping_and_other_currencies_do_not():
    assert money(63000) == "INR 63,000"
    assert money(1234567) == "INR 12,34,567"
    assert money(999) == "INR 999"
    assert money(1234567, "USD") == "USD 1,234,567"


def test_the_breakdown_adds_up_to_the_total_and_never_shows_the_margin():
    shown = price_lines(TOTALS, breakdown=True, tax_percent=0)
    assert shown["total"] == 69000 and shown["tax"] == 0 and shown["grand"] == 69000
    assert sum(amount for _, amount in shown["lines"]) == 69000
    labels = [label for label, _ in shown["lines"]]
    assert "Material and edge banding" in labels and "Hardware" in labels and "Labour and installation" in labels
    assert not any("margin" in label.lower() for label in labels)
    assert all(amount > 0 for _, amount in shown["lines"])  # the 9000 of margin is inside them, not a line of its own


def test_rounding_never_breaks_the_sum():
    odd = dict(TOTALS, material=333.33, edge_banding=0.0, hardware=333.33, labour=333.34, total=1000.0)
    shown = price_lines(odd, breakdown=True, tax_percent=0)
    assert sum(amount for _, amount in shown["lines"]) == 1000


def test_tax_is_added_on_top():
    shown = price_lines(TOTALS, breakdown=False, tax_percent=18)
    assert shown["lines"] == [] and shown["tax"] == 12420 and shown["grand"] == 81420


# ---- studio details --------------------------------------------------------

def test_studio_details_are_validated():
    brand = normalise_brand({"studio_name": " Rao Interiors ", "tax_percent": "18", "validity_days": 30,
                             "accent": "#AA3300", "show_breakdown": True})
    assert brand["studio_name"] == "Rao Interiors" and brand["tax_percent"] == 18.0
    assert brand["validity_days"] == 30 and brand["accent"] == "#aa3300" and brand["show_breakdown"] is True
    for bad in ({"tax_percent": 150}, {"validity_days": 0}, {"accent": "red"}, {"studio_name": "x" * 200},
                {"phone": "+91 98765 ०१"}):
        with pytest.raises(ValueError):
            normalise_brand(bad)


def test_brand_round_trip_and_logo(client):  # noqa: F811
    token = _signup(client, "brand@example.com")["token"]
    headers = _auth(token)
    first = client.get("/api/brand", headers=headers).json()
    assert first["studio_name"] == "" and first["has_logo"] is False and first["accent"] == "#0f766e"
    saved = client.put("/api/brand", json={"studio_name": "Rao Interiors", "phone": "+91 98765 43210"}, headers=headers)
    assert saved.status_code == 200 and saved.json()["studio_name"] == "Rao Interiors"
    assert client.put("/api/brand", json={"tax_percent": 500}, headers=headers).status_code == 422
    assert client.get("/api/brand", headers=headers).json()["phone"] == "+91 98765 43210"  # a bad save changed nothing

    logo = client.post("/api/brand/logo", files={"file": ("logo.png", _png(), "image/png")}, headers=headers)
    assert logo.status_code == 200 and logo.json()["has_logo"] is True
    assert client.get("/api/brand/logo", headers=headers).headers["content-type"] == "image/png"
    assert client.delete("/api/brand/logo", headers=headers).json()["has_logo"] is False


def test_logo_must_be_a_real_image(client):  # noqa: F811
    headers = _auth(_signup(client, "badlogo@example.com")["token"])
    bad = client.post("/api/brand/logo", files={"file": ("logo.png", b"not an image", "image/png")}, headers=headers)
    assert bad.status_code == 422
    big = client.post("/api/brand/logo", files={"file": ("big.png", b"0" * 1_100_000, "image/png")}, headers=headers)
    assert big.status_code == 422 and "1 MB" in big.json()["detail"]


# ---- the PDF ---------------------------------------------------------------

def test_the_pdf_carries_the_studio_the_customer_and_a_price_without_the_margin(client):  # noqa: F811
    token, project_id = _quoted_project(client)
    headers = _auth(token)
    client.put("/api/brand", json={"studio_name": "Rao Interiors", "phone": "+91 98765 43210", "tax_id": "29ABCDE1234F1Z5",
                                   "tax_percent": 18, "terms": "50% advance, balance on delivery."}, headers=headers)
    client.post("/api/brand/logo", files={"file": ("logo.png", _png(), "image/png")}, headers=headers)

    response = client.get(f"/api/projects/{project_id}/quote.pdf", headers=headers)
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF") and "quote.pdf" in response.headers["content-disposition"]
    text = _text(response.content)
    for expected in ("Rao Interiors", "QUOTATION", f"Q-{project_id:04d}", "Mrs Rao", "Delivery in 3 weeks.",
                     "50% advance", "GST: 29ABCDE1234F1Z5", "GST 18%", "Total (including tax)", "Valid until"):
        assert expected in text, expected
    assert "margin" not in text.lower()


def test_the_parts_list_is_optional(client):  # noqa: F811
    token, project_id = _quoted_project(client, "parts@example.com")
    headers = _auth(token)
    without = _text(client.get(f"/api/projects/{project_id}/quote.pdf", headers=headers).content)
    with_parts = _text(client.get(f"/api/projects/{project_id}/quote.pdf?parts=true", headers=headers).content)
    assert "PARTS LIST" not in without and "PARTS LIST" in with_parts


def test_a_quote_must_be_saved_before_it_can_be_printed(client):  # noqa: F811
    token = _signup(client, "noquote@example.com")["token"]
    project_id = _described_project(client, token)["id"]
    response = client.get(f"/api/projects/{project_id}/quote.pdf", headers=_auth(token))
    assert response.status_code == 409 and "Save a quote" in response.json()["detail"]


def test_text_the_pdf_cannot_draw_is_refused_with_a_reason(client):  # noqa: F811
    token = _signup(client, "hindi@example.com")["token"]
    project_id = _described_project(client, token)["id"]
    client.put(f"/api/projects/{project_id}/settings", json={"quote": {"labour": 1000, "customer": "श्रीमती राव"}},
               headers=_auth(token))
    response = client.get(f"/api/projects/{project_id}/quote.pdf", headers=_auth(token))
    assert response.status_code == 422 and "English letters" in response.json()["detail"]


def test_nobody_else_can_print_my_quote(client):  # noqa: F811
    token, project_id = _quoted_project(client, "mine@example.com")
    other = _auth(_signup(client, "theirs@example.com")["token"])
    assert client.get(f"/api/projects/{project_id}/quote.pdf", headers=other).status_code == 404
    assert client.get(f"/api/projects/{project_id}/quote.pdf").status_code == 401


def test_deleting_the_account_removes_the_logo(client):  # noqa: F811
    from cutlist_engine.saas.brand import logo_path

    signed = _signup(client, "gone@example.com")
    headers = _auth(signed["token"])
    client.post("/api/brand/logo", files={"file": ("logo.png", _png(), "image/png")}, headers=headers)
    assert logo_path(signed["user"]["id"]).exists()
    client.request("DELETE", "/auth/me", data={"password": "workshop123"}, headers=headers)
    assert not logo_path(signed["user"]["id"]).exists()
