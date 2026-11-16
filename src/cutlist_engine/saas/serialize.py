"""Result serialization shared with the review server.

The canonical serializers live in server.py; importing them lazily (inside
functions) avoids a circular import because server.py mounts the SaaS router.
"""
from __future__ import annotations

from typing import Any


def serialize_result(result) -> dict[str, Any]:
    from ..server import _serialize_result

    return _serialize_result(result)
