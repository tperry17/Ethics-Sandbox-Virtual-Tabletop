"""Identity without sign-in.

The whole identity system, per CLAUDE.md: a signed, http-only cookie holding
a random participant id, issued on first visit and long-lived. No email, no
password, no account, no third-party auth - a display name is typed when
joining a room and stored against the participant for that room, and the
same browser returning to the same room reclaims its seat and its hand
because it still carries this cookie. No later route may add a login.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import Request, Response

COOKIE_NAME = "sandbox_id"
COOKIE_MAX_AGE_SECONDS = 400 * 24 * 60 * 60  # ~400 days, the browser-cookie ceiling


def _secret_key() -> bytes:
    # A fixed fallback keeps local dev and tests working without setup; it is
    # not fit for production, where SANDBOX_SECRET_KEY must be set.
    return os.environ.get("SANDBOX_SECRET_KEY", "dev-only-insecure-secret").encode()


def _sign(participant_id: str) -> str:
    digest = hmac.new(
        _secret_key(), participant_id.encode(), hashlib.sha256
    ).hexdigest()
    return f"{participant_id}.{digest}"


def _verify(cookie_value: str) -> str | None:
    participant_id, _, digest = cookie_value.rpartition(".")
    if not participant_id or not digest:
        return None
    expected = hmac.new(
        _secret_key(), participant_id.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, digest):
        return None
    return participant_id


def new_participant_id() -> str:
    """A fresh, unguessable participant id."""
    return secrets.token_urlsafe(18)


def read_participant_cookie(request: Request) -> str | None:
    """The participant id in ``request``'s cookie, if it is present and valid."""
    raw = request.cookies.get(COOKIE_NAME)
    if raw is None:
        return None
    return _verify(raw)


def set_participant_cookie(
    response: Response, request: Request, participant_id: str
) -> None:
    """Write the signed identity cookie for ``participant_id`` onto ``response``."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=_sign(participant_id),
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


def ensure_participant_id(request: Request, response: Response) -> str:
    """The caller's participant id, issuing and setting a fresh cookie if needed.

    Use this as a FastAPI dependency on any route that needs to know who is
    asking. It is the only place a participant id is minted.
    """
    participant_id = read_participant_cookie(request)
    if participant_id is None:
        participant_id = new_participant_id()
        set_participant_cookie(response, request, participant_id)
    return participant_id


__all__ = [
    "COOKIE_MAX_AGE_SECONDS",
    "COOKIE_NAME",
    "ensure_participant_id",
    "new_participant_id",
    "read_participant_cookie",
    "set_participant_cookie",
]
