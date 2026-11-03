"""Building the card files, ``*_cards.csv``, from the sheets.

For Leadership and Knowledge in Popular Rule.

The author edits ``roles.csv``, ``jobs.csv``, ``features.csv``,
``elite_sheets.csv`` and ``invitations.csv`` as spreadsheets. A card's back
is made of several of them (its job's text, plus a line for each mark it
carries), so each of the game's decks reads a composed file beside them
(``role_cards.csv``, ``moderator_cards.csv``, ``sheet_cards.csv``,
``invitation_cards.csv``);
``tests/test_democracy_simulation.py`` fails when it is out of date.
Rebuild it with ``uv run python sandbox/games/democracy_simulation/compose.py``.

One row per card, with a ``kind``: ``role`` (80), ``moderator`` (two per
phase), ``sheet`` (an elite's information sheet) and ``invitation``.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from sandbox.content_loading import CONTENT_ROOT, read_rows

FOLDER = "exercises/democracy-simulation"
COLUMNS = (
    "key",
    "kind",
    "phase",
    "city",
    "card_number",
    "job",
    "river",
    "rumour",
    "council",
    "title",
    "interest",
    "body",
    "folio",
    "image",
)
FEATURE_FLAGS = (("river", "River"), ("rumour", "Rumors"), ("council", "Council"))


def _rows(name: str, root: Path) -> list[dict[str, str]]:
    return read_rows(f"{FOLDER}/{name}", root=root)


def _paragraphs(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part.strip())


def _icon(name: str) -> str:
    return f"{name.lower()}.png"


def compose(root: Path = CONTENT_ROOT) -> list[dict[str, str]]:
    """Every card of the exercise, ready to write as ``cards.csv``."""
    jobs = {(row["phase"], row["job"]): row for row in _rows("jobs.csv", root)}
    features = {
        (row["phase"], row["feature"]): row for row in _rows("features.csv", root)
    }
    cards: list[dict[str, str]] = []

    for role in _rows("roles.csv", root):
        phase, job = role["phase"], role["job"]
        text = jobs[(phase, job)]
        parts = [text["interest"], text["knowledge"]]
        interests = [text["interest"]]
        for flag, feature in FEATURE_FLAGS:
            if role[flag] == "yes":
                line = features[(phase, feature)]
                parts += [line["interest"], line["knowledge"]]
                interests.append(line["interest"])
        cards.append(
            {
                "key": f"role-{role['key']}",
                "kind": "role",
                "phase": phase,
                "city": role["city"],
                "card_number": role["card_number"],
                "job": job,
                "river": role["river"],
                "rumour": role["rumour"],
                "council": role["council"],
                "title": job,
                "interest": _paragraphs(*interests),
                "body": _paragraphs(*parts),
                "folio": role["card_number"],
                "image": role["image"] or _icon(job),
            }
        )

    for phase in sorted({row["phase"] for row in jobs.values()}):
        text = jobs[(phase, "Moderator")]
        for copy in (1, 2):  # a city has two co-Chairs
            cards.append(
                {
                    "key": f"moderator-p{phase}-{copy}",
                    "kind": "moderator",
                    "phase": phase,
                    "title": "Moderator",
                    "body": _paragraphs(text["interest"], text["knowledge"]),
                    "image": text["image"] or _icon("Moderator"),
                }
            )

    for sheet in _rows("elite_sheets.csv", root):
        cards.append(
            {
                "key": f"sheet-{sheet['key']}",
                "kind": "sheet",
                "phase": sheet["phase"],
                "city": sheet["city"],
                "card_number": sheet["card_number"],
                "job": sheet["job"],
                "title": f"Information sheet · {sheet['job']}",
                "body": sheet["text"],
                "folio": sheet["card_number"],
            }
        )

    for invitation in _rows("invitations.csv", root):
        cards.append(
            {
                "key": f"invitation-{invitation['key']}",
                "kind": "invitation",
                "phase": invitation["phase"],
                "city": invitation["city"],
                "title": "Invitation",
                "body": invitation["text"],
            }
        )
    return cards


FILES = {
    "role": "role_cards.csv",
    "moderator": "moderator_cards.csv",
    "sheet": "sheet_cards.csv",
    "invitation": "invitation_cards.csv",
}


def files(root: Path = CONTENT_ROOT) -> dict[str, str]:
    """Each composed file, by its path under the exercise's folder, as text."""
    cards = compose(root)
    return {
        path: render([card for card in cards if card["kind"] == kind])
        for kind, path in FILES.items()
    }


def render(cards: list[dict[str, str]]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for card in cards:
        writer.writerow({column: card.get(column, "") for column in COLUMNS})
    return out.getvalue()


def main() -> None:
    for path, text in files().items():
        target = CONTENT_ROOT / FOLDER / path
        target.write_text(text, encoding="utf-8", newline="")
        print(f"Wrote {target}")


if __name__ == "__main__":
    main()
