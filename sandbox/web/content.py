"""Shared editorial content for the public site and tabletop.

The actual words live in ``content/site/*.csv`` (see
``content/README.md``), not here - this module just shapes rows into what
the templates expect.
"""

from __future__ import annotations

from dataclasses import dataclass

from sandbox.content_loading import read_rows

PRINCIPLES_CSV = "site/principles.csv"
SITE_COPY_CSV = "site/site_copy.csv"


@dataclass(frozen=True)
class Principle:
    """One norm of engagement shown to participants and facilitators."""

    title: str
    copy: str


def _load_principles() -> tuple[Principle, ...]:
    return tuple(
        Principle(title=row["title"], copy=row["copy"])
        for row in read_rows(PRINCIPLES_CSV)
    )


def _load_site_copy() -> dict[str, str]:
    """Named blocks of standalone site copy (the landing page's lede, etc.)."""
    return {row["key"]: row["text"] for row in read_rows(SITE_COPY_CSV)}


# These norms are intentionally data, not template copy: the tabletop can
# import the same list when its session chrome is implemented.
PRINCIPLES: tuple[Principle, ...] = _load_principles()

SITE_COPY: dict[str, str] = _load_site_copy()
