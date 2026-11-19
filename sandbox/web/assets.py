"""Static files that no cache keeps past a change.

Served without a ``Cache-Control`` header, a stylesheet or script may be
reused by a browser, or by Cloudflare's edge in front of a tunnel, for hours
after it changed, so a new page was drawn with the old CSS and client. Two
things stop that:

- every link a template makes to ``/static`` carries ``?v=`` and the file's
  modification time, so a changed file has a new address no cache has seen;
- every ``/static`` response says ``Cache-Control: no-cache``, so whatever is
  kept is checked with the server (a cheap 304) before it is used again.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Scope

STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"


class StaticAssets(StaticFiles):
    """``StaticFiles`` whose every answer must be revalidated before reuse."""

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response


def static_version(path: str) -> str | None:
    """The version a link to ``/static{path}`` carries: the file's mtime."""
    target = (STATIC_ROOT / path.lstrip("/")).resolve()
    if not target.is_relative_to(STATIC_ROOT):
        return None
    try:
        return str(target.stat().st_mtime_ns)
    except OSError:
        return None


def version_static_links(templates: Jinja2Templates) -> None:
    """Make ``url_for('static', path=...)`` in these templates add ``?v=``."""

    @pass_context
    def url_for(context: dict[str, Any], name: str, /, **path_params: Any) -> str:
        request: Request = context["request"]
        url = request.url_for(name, **path_params)
        if name != "static":
            return str(url)
        version = static_version(str(path_params.get("path", "")))
        return str(url if version is None else url.include_query_params(v=version))

    templates.env.globals["url_for"] = url_for
