"""Shared editorial content for the public site and tabletop.

The actual words live in ``content/site/*.csv`` (see
``content/README.md``), not here - this module just shapes rows into what
the templates expect.
"""

from __future__ import annotations

from sandbox.content_loading import read_rows

SITE_COPY_CSV = "site/site_copy.csv"


def _load_site_copy() -> dict[str, str]:
    """Named blocks of standalone site copy (the landing page's lede, etc.)."""
    return {row["key"]: row["text"] for row in read_rows(SITE_COPY_CSV)}


SITE_COPY: dict[str, str] = _load_site_copy()
