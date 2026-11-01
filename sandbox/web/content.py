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


HELP_RECORDS_CSV = "site/help_records.csv"


def _load_help_records() -> list[dict[str, str]]:
    """The Help page's notes on records: a heading and a paragraph each."""
    return [
        {"heading": row["heading"], "text": row["text"]}
        for row in read_rows(HELP_RECORDS_CSV)
    ]


HELP_RECORDS: list[dict[str, str]] = _load_help_records()
