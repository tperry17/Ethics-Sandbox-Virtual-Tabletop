"""Opening a room the way a person does: "Open a room", then the join form.

``start_room`` stands in for the old ``POST /start``: it opens a room of
``kind`` and joins it with ``data`` (``display_name``, perhaps
``as_facilitator``), returning the join form's response - a redirect to the
table, or the form again with an error.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

DEFAULT_KIND = "value-cards-room"


def open_room_code(client: TestClient, kind: str = DEFAULT_KIND) -> str:
    """Open a room of ``kind`` and return its code, without joining it."""
    opened = client.post("/rooms", data={"kind": kind}, follow_redirects=False)
    assert opened.status_code == 303, opened.text
    location = str(opened.headers["location"])
    assert location.startswith("/join?code=")
    return location.removeprefix("/join?code=")


def start_room(
    client: TestClient,
    data: dict[str, Any] | None = None,
    *,
    kind: str = DEFAULT_KIND,
) -> Response:
    """Open a room of ``kind`` and join it with ``data``."""
    code = open_room_code(client, kind)
    joined: Response = client.post(
        "/join",
        data={"room_code": code, **(data or {})},
        follow_redirects=False,
    )
    return joined
