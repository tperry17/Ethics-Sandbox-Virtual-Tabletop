"""The signed identity cookie: the whole identity system, per CLAUDE.md."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.testclient import TestClient

from sandbox.web.identity import (
    COOKIE_NAME,
    ensure_participant_id,
    new_participant_id,
    read_participant_cookie,
    set_participant_cookie,
)


def _empty_request(scheme: str = "http") -> Request:
    scope = {
        "type": "http",
        "headers": [],
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "scheme": scheme,
        "server": ("testserver", 443 if scheme == "https" else 80),
    }
    return Request(scope)


def test_new_participant_ids_are_unique() -> None:
    ids = {new_participant_id() for _ in range(200)}

    assert len(ids) == 200


def test_read_participant_cookie_returns_none_without_a_cookie() -> None:
    assert read_participant_cookie(_empty_request()) is None


def test_set_participant_cookie_is_http_only_and_signed() -> None:
    response = Response()

    set_participant_cookie(response, _empty_request(), "participant-123")

    set_cookie_header = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header
    assert "participant-123." in set_cookie_header


def test_set_participant_cookie_is_secure_only_over_https() -> None:
    http_response = Response()
    set_participant_cookie(http_response, _empty_request("http"), "participant-1")
    assert "Secure" not in http_response.headers.get("set-cookie", "")

    https_response = Response()
    set_participant_cookie(https_response, _empty_request("https"), "participant-1")
    assert "Secure" in https_response.headers.get("set-cookie", "")


def test_ensure_participant_id_mints_once_then_reuses_the_cookie() -> None:
    app = FastAPI()

    @app.get("/id")
    def get_id(request: Request) -> PlainTextResponse:
        response = PlainTextResponse("")
        participant_id = ensure_participant_id(request, response)
        response.body = participant_id.encode()
        return response

    client = TestClient(app)

    first = client.get("/id")
    assert first.status_code == 200
    assert COOKIE_NAME in first.cookies
    first_id = first.text

    second = client.get("/id")
    assert second.text == first_id


def test_a_tampered_cookie_is_rejected_and_a_fresh_id_is_issued() -> None:
    app = FastAPI()

    @app.get("/id")
    def get_id(request: Request) -> PlainTextResponse:
        response = PlainTextResponse("")
        participant_id = ensure_participant_id(request, response)
        response.body = participant_id.encode()
        return response

    client = TestClient(app)
    first = client.get("/id")
    first_id = first.text

    signed = client.cookies.get(COOKIE_NAME)
    assert signed is not None
    flipped_last_char = "0" if signed[-1] != "0" else "1"
    client.cookies.set(COOKIE_NAME, signed[:-1] + flipped_last_char)

    second = client.get("/id")
    assert second.text != first_id
