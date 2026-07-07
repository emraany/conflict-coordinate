"""Shared ACLED OAuth helpers.

The aggregated xlsx source and the lagged event API source both authenticate
against the same myACLED account, so they must share one token cache to avoid
contention (each new password-grant invalidates the previous refresh token).

Cache file: `backend/.cache/acled_token.json`. Access tokens last 24 h,
refresh tokens 14 days.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from app.config import settings

ACLED_OAUTH_URL = "https://acleddata.com/oauth/token"
ACLED_CLIENT_ID = "acled"

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
TOKEN_CACHE_PATH = CACHE_DIR / "acled_token.json"


@dataclass
class CachedToken:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime

    def access_valid(self, now: datetime) -> bool:
        return now < self.access_expires_at - timedelta(seconds=60)

    def refresh_valid(self, now: datetime) -> bool:
        return now < self.refresh_expires_at - timedelta(seconds=60)


def _load_cached_token() -> CachedToken | None:
    if not TOKEN_CACHE_PATH.exists():
        return None
    try:
        data = json.loads(TOKEN_CACHE_PATH.read_text())
        return CachedToken(
            access_token=data["access_token"],
            access_expires_at=datetime.fromisoformat(data["access_expires_at"]),
            refresh_token=data["refresh_token"],
            refresh_expires_at=datetime.fromisoformat(data["refresh_expires_at"]),
        )
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def _save_cached_token(tok: CachedToken) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_PATH.write_text(
        json.dumps(
            {
                "access_token": tok.access_token,
                "access_expires_at": tok.access_expires_at.isoformat(),
                "refresh_token": tok.refresh_token,
                "refresh_expires_at": tok.refresh_expires_at.isoformat(),
            }
        )
    )


def _token_from_response(payload: dict, now: datetime) -> CachedToken:
    access_secs = int(payload.get("expires_in", 24 * 3600))
    refresh_secs = int(payload.get("refresh_expires_in", 14 * 24 * 3600))
    return CachedToken(
        access_token=payload["access_token"],
        access_expires_at=now + timedelta(seconds=access_secs),
        refresh_token=payload.get("refresh_token", ""),
        refresh_expires_at=now + timedelta(seconds=refresh_secs),
    )


def _password_grant(client: httpx.Client, now: datetime) -> CachedToken:
    resp = client.post(
        ACLED_OAUTH_URL,
        data={
            "username": settings.acled_username,
            "password": settings.acled_password,
            "grant_type": "password",
            "client_id": ACLED_CLIENT_ID,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return _token_from_response(resp.json(), now)


def _refresh_grant(
    client: httpx.Client, refresh_token: str, now: datetime
) -> CachedToken:
    resp = client.post(
        ACLED_OAUTH_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": ACLED_CLIENT_ID,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return _token_from_response(resp.json(), now)


def get_token(client: httpx.Client) -> CachedToken:
    now = datetime.now(UTC)
    cached = _load_cached_token()
    if cached and cached.access_valid(now):
        return cached
    if cached and cached.refresh_valid(now):
        tok = _refresh_grant(client, cached.refresh_token, now)
        _save_cached_token(tok)
        return tok
    tok = _password_grant(client, now)
    _save_cached_token(tok)
    return tok


def get_fresh_token(client: httpx.Client) -> CachedToken:
    """Force a password grant, bypassing the cache. Use after a 401 —
    ACLED can revoke a token chain server-side while the cached
    timestamps still look valid."""
    tok = _password_grant(client, datetime.now(UTC))
    _save_cached_token(tok)
    return tok
