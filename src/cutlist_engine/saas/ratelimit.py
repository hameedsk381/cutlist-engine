"""A small per-address rate limit for the endpoints strangers can reach.

Sign-in, sign-up and password reset are open to the internet, so they get a
limit per client address to slow down password guessing and sign-up spam.
Counts are held in memory in each process: a restart resets them, and with
several replicas each keeps its own. That is enough to stop a script; put a
proxy-level limit in front for anything stronger.

Behind a reverse proxy every request seems to come from the proxy, which would
put all users in one bucket. So when the connection comes from a private or
loopback address (a proxy on the same host or Docker network) the client address
is taken from the LAST X-Forwarded-For entry, the one the proxy itself added.
A connection from a public address is never trusted to name someone else.
CUTLIST_TRUST_PROXY=1 always trusts the header, 0 never does.

CUTLIST_RATE_LIMIT=off turns the limits off (tests, local use).
"""
from __future__ import annotations

import ipaddress
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_HITS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def enabled() -> bool:
    return os.environ.get("CUTLIST_RATE_LIMIT", "on").strip().lower() not in {"off", "0", "false", "no"}


def _private(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback


def client_address(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    setting = os.environ.get("CUTLIST_TRUST_PROXY", "").strip()
    trust = setting == "1" or (setting != "0" and _private(host))
    if trust:
        forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
        if forwarded:
            return forwarded[-1]
    return host


def limit(bucket: str, attempts: int, per_seconds: int):
    """A FastAPI dependency: at most `attempts` calls per `per_seconds` from one address."""

    def check(request: Request) -> None:
        if not enabled():
            return
        now = time.monotonic()
        hits = _HITS[(bucket, client_address(request))]
        while hits and now - hits[0] > per_seconds:
            hits.popleft()
        if len(hits) >= attempts:
            wait = max(1, int(per_seconds - (now - hits[0])))
            raise HTTPException(
                429,
                f"Too many attempts. Try again in {max(1, round(wait / 60))} minute(s).",
                headers={"Retry-After": str(wait)},
            )
        hits.append(now)

    return check


def reset() -> None:
    """Forget every count (tests)."""
    _HITS.clear()
