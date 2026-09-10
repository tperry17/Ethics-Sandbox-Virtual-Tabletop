"""Reading CSV content files into plain rows.

Editorial text - principles, exercise copy, and (once an exercise defines
game content) card and role decks - lives as CSV files under ``content/``
at the project root rather than as Python literals, so updating what the
site says is editing a spreadsheet, not touching code. See
``content/README.md`` for the full convention.

This module is the one place that turns a CSV file into rows of plain
strings. ``sandbox.web.content`` and ``sandbox.games`` build their own
dataclasses out of those rows; neither this module nor the CSV files it
reads know anything about tabletop rules or exercise mechanics.
"""

from __future__ import annotations

import csv
from pathlib import Path

CONTENT_ROOT = Path(__file__).resolve().parent.parent / "content"


def read_rows(relative_path: str) -> list[dict[str, str]]:
    """Every row of the CSV at ``content/<relative_path>``, in file order."""
    path = CONTENT_ROOT / relative_path
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def rows_for_slug(relative_path: str, slug: str) -> list[dict[str, str]]:
    """Rows of a shared CSV whose ``slug`` column matches, in file order."""
    return [row for row in read_rows(relative_path) if row["slug"] == slug]


__all__ = ["CONTENT_ROOT", "read_rows", "rows_for_slug"]
