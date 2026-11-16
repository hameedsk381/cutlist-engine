"""The studio details printed on a client's quote: name, contact, logo, colour, tax.

Stored per account (`users.brand_json`); the logo is a small PNG on disk. The PDF
printer can only draw Western letters (see `printable`), so text fields are checked
when they are saved and the user is told which characters will not print.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

from .storage import STORAGE_ROOT

LOGO_MAX_BYTES = 1_000_000
LOGO_MAX_WIDTH = 600
DEFAULT_ACCENT = "#0f766e"

_TEXT_FIELDS = {
    "studio_name": 80,
    "phone": 40,
    "email": 120,
    "address": 200,
    "tax_id": 40,
    "tax_name": 20,
    "terms": 800,
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAULT_BRAND: dict[str, Any] = {
    "studio_name": "",
    "phone": "",
    "email": "",
    "address": "",
    "tax_id": "",
    "tax_name": "GST",
    "tax_percent": 0.0,
    "validity_days": 15,
    "terms": "",
    "accent": DEFAULT_ACCENT,
    "show_breakdown": False,
}


def printable(text: str) -> bool:
    """True if the PDF can draw every character (the standard Latin set)."""
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def unprintable_chars(text: str) -> str:
    return "".join(sorted({ch for ch in text if not printable(ch)}))[:10]


def normalise_brand(raw: Any, current: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate studio details. Raises ValueError with a message for the user."""
    if not isinstance(raw, dict):
        raise ValueError("The studio details must be a set of named fields.")
    brand = dict(DEFAULT_BRAND)
    brand.update(current or {})
    for field, limit in _TEXT_FIELDS.items():
        if field in raw:
            value = str(raw[field] or "").strip()
            if len(value) > limit:
                raise ValueError(f"'{field.replace('_', ' ')}' can be at most {limit} characters.")
            bad = unprintable_chars(value)
            if bad:
                raise ValueError(
                    f"'{field.replace('_', ' ')}' has characters the PDF cannot print yet ({bad}). "
                    "Write it with English letters."
                )
            brand[field] = value
    if "tax_percent" in raw:
        try:
            tax = float(raw["tax_percent"] or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("The tax rate must be a number.") from exc
        if not 0 <= tax <= 100:
            raise ValueError("The tax rate must be between 0 and 100 percent.")
        brand["tax_percent"] = round(tax, 2)
    if "validity_days" in raw:
        try:
            days = int(raw["validity_days"] or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Validity must be a whole number of days.") from exc
        if not 1 <= days <= 365:
            raise ValueError("A quote can be valid for 1 to 365 days.")
        brand["validity_days"] = days
    if "accent" in raw:
        accent = str(raw["accent"] or "").strip()
        if not _HEX.match(accent):
            raise ValueError("The colour must look like #0f766e.")
        brand["accent"] = accent.lower()
    if "show_breakdown" in raw:
        brand["show_breakdown"] = bool(raw["show_breakdown"])
    return brand


def load_brand(user) -> dict[str, Any]:
    brand = dict(DEFAULT_BRAND)
    try:
        stored = json.loads(user.brand_json or "{}")
    except ValueError:
        stored = {}
    if isinstance(stored, dict):
        brand.update({k: v for k, v in stored.items() if k in DEFAULT_BRAND})
    return brand


def logo_path(user_id: int) -> Path:
    return STORAGE_ROOT / "brands" / str(user_id) / "logo.png"


def brand_dir(user_id: int) -> Path:
    return STORAGE_ROOT / "brands" / str(user_id)


def save_logo(user_id: int, content: bytes) -> None:
    """Check the upload is a real image, shrink it, and keep it as a PNG. Raises ValueError."""
    if len(content) > LOGO_MAX_BYTES:
        raise ValueError("The logo is bigger than 1 MB. Use a smaller image.")
    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("That file is not a PNG or JPEG image.") from exc
    if image.format not in {"PNG", "JPEG"}:
        raise ValueError("The logo must be a PNG or JPEG image.")
    if image.width * image.height > 40_000_000:
        raise ValueError("That image is too large.")
    image = image.convert("RGBA")
    if image.width > LOGO_MAX_WIDTH:
        image = image.resize((LOGO_MAX_WIDTH, max(1, round(image.height * LOGO_MAX_WIDTH / image.width))))
    path = logo_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG")
