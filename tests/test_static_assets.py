"""Static files are linked by version and revalidated, so no cache serves an old one."""

import os
import re

from fastapi.testclient import TestClient

from sandbox.web.app import app
from sandbox.web.assets import STATIC_ROOT, static_version


def test_pages_link_static_files_with_their_version() -> None:
    page = TestClient(app).get("/").text
    version = str((STATIC_ROOT / "css" / "site.css").stat().st_mtime_ns)
    assert re.search(rf'href="[^"]*/static/css/site\.css\?v={version}"', page)


def test_a_changed_file_gets_a_new_address() -> None:
    before = static_version("/css/site.css")
    assert before is not None
    target = STATIC_ROOT / "css" / "site.css"
    stat = target.stat()
    try:
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        assert static_version("/css/site.css") != before
    finally:
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))


def test_static_files_must_be_revalidated_before_reuse() -> None:
    client = TestClient(app)
    response = client.get("/static/css/site.css")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    again = client.get(
        "/static/css/site.css", headers={"if-none-match": response.headers["etag"]}
    )
    assert again.status_code == 304
    assert again.headers["cache-control"] == "no-cache"


def test_no_version_for_a_path_outside_static() -> None:
    assert static_version("/../pyproject.toml") is None
    assert static_version("/no-such-file.css") is None
