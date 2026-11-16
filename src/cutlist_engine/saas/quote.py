"""Client quote on top of a cutting plan: tape, labour, hardware and margin.

The quote inputs are stored per project (inside `config_json["quote"]`). The
totals are always recomputed from the latest plan, so a re-run with different
edge banding or sheet count keeps the quote in step.
"""
from __future__ import annotations

from typing import Any

_MONEY_FIELDS = ("labour", "hardware", "other", "edge_band_rate")
_LIMIT = 100_000_000.0


def normalise_quote(raw: Any) -> dict[str, Any]:
    """Validate quote inputs. Raises ValueError with a user-facing message."""
    if not isinstance(raw, dict):
        raise ValueError("The quote must be a set of named amounts.")
    quote: dict[str, Any] = {}
    for field in _MONEY_FIELDS:
        try:
            value = float(raw.get(field) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'{field}' must be a number.") from exc
        if not 0 <= value <= _LIMIT:
            raise ValueError(f"'{field}' must be zero or more.")
        quote[field] = round(value, 2)
    try:
        margin = float(raw.get("margin_percent") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("'margin_percent' must be a number.") from exc
    if not 0 <= margin <= 500:
        raise ValueError("The margin must be between 0 and 500 percent.")
    quote["margin_percent"] = round(margin, 2)
    quote["customer"] = str(raw.get("customer") or "").strip()[:120]
    quote["note"] = str(raw.get("note") or "").strip()[:500]
    return quote


def quote_totals(summary: dict[str, Any] | None, quote: dict[str, Any] | None) -> dict[str, Any] | None:
    """Price a plan. Returns None when no quote has been saved or no plan exists."""
    if not quote or not summary:
        return None
    material_summary = summary.get("material_summary") or {}
    material = float(material_summary.get("total_material_cost") or 0)
    tape_m = float((summary.get("edge_banding") or {}).get("total_m") or 0)
    tape = round(tape_m * float(quote.get("edge_band_rate") or 0), 2)
    labour = float(quote.get("labour") or 0)
    hardware = float(quote.get("hardware") or 0)
    other = float(quote.get("other") or 0)
    subtotal = round(material + tape + labour + hardware + other, 2)
    margin = round(subtotal * float(quote.get("margin_percent") or 0) / 100.0, 2)
    return {
        "currency": material_summary.get("currency") or "INR",
        "material": round(material, 2),
        "edge_banding": tape,
        "edge_banding_m": round(tape_m, 2),
        "labour": labour,
        "hardware": hardware,
        "other": other,
        "subtotal": subtotal,
        "margin": margin,
        "total": round(subtotal + margin, 2),
        "customer": quote.get("customer", ""),
        "note": quote.get("note", ""),
    }
