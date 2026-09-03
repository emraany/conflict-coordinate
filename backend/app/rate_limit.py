"""Per-IP request throttle for the public API.

Nothing here guards a secret — every read endpoint is deliberately open. It
guards the single Postgres instance behind them, which is what actually
falls over when one caller walks all 293 dossiers in a loop.

Counters live in this process, so the window is per-worker: two workers mean
a caller gets two buckets. That is the right shape for one Railway container
and would need a shared store before the API is ever scaled out.
"""

from __future__ import annotations

from slowapi import Limiter
from starlette.requests import Request

# Generous for a person: a cold globe load plus every dossier they can click
# through in a minute sits well under this. Tight enough that a scraper
# pulling the whole dot list end to end has to slow to a walk.
DEFAULT_LIMIT = "120/minute"


def client_ip(request: Request) -> str:
    """The caller's address, as seen from behind one trusted proxy.

    Railway terminates TLS and forwards, so `request.client.host` is the
    proxy on every request and would put the entire internet in one bucket.
    `X-Forwarded-For` is a caller-supplied list that the proxy *appends* its
    peer to, so the last entry is the one the proxy observed and the only one
    a caller cannot spoof — reading the first entry instead would let anyone
    skip the limit by rotating a header.

    Assumes exactly one proxy in front of the app. With two, this reads the
    inner proxy's address and everyone shares a bucket — over-throttling
    rather than failing open, but check it against a real request once
    Railway is up.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


# headers_enabled is what actually emits Retry-After (and the X-RateLimit-*
# trio); retry_after alone is inert without it. A 429 carrying neither leaves
# a well-behaved client guessing, and the ones that guess badly are the ones
# that caused the 429.
limiter = Limiter(
    key_func=client_ip,
    default_limits=[DEFAULT_LIMIT],
    headers_enabled=True,
    retry_after="delta-seconds",
)
