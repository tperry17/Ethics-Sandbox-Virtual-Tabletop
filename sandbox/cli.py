"""The ``sandbox`` command: ``uv run sandbox validate-games``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def _validate_games() -> int:
    from sandbox.games import extra_game_roots
    from sandbox.games.validation import validate_games

    report = validate_games()
    for root in extra_game_roots():
        extra = validate_games(root, root / "content", catalog_notes=False)
        report.checked += extra.checked
        report.errors += extra.errors
    for slug in report.checked:
        print(f"checked {slug}")
    for note in report.notes:
        print(f"note: {note}")
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    if report.ok:
        print(f"{len(report.checked)} game definition(s) valid.")
        return 0
    print(f"{len(report.errors)} problem(s) found.", file=sys.stderr)
    return 1


def _data_dictionary(check: bool) -> int:
    from pathlib import Path

    from sandbox.web.record import data_dictionary_markdown

    path = Path(__file__).resolve().parents[1] / "docs" / "DATA-DICTIONARY.md"
    text = data_dictionary_markdown()
    if check:
        if path.read_text() == text:
            return 0
        print(
            "docs/DATA-DICTIONARY.md is out of date; "
            "run `uv run sandbox data-dictionary`.",
            file=sys.stderr,
        )
        return 1
    path.write_text(text)
    print(f"wrote {path}")
    return 0


def _seed_demo(slug: str, people: int | None) -> int:
    from sandbox.db.engine import session_scope
    from sandbox.seed import SeedError, seed_demo

    try:
        with session_scope() as session:
            code = seed_demo(session, slug, people=people)
    except SeedError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        f"Demo room {code}. Open /t/{code} on the running server, "
        "or enter the code at /join."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sandbox")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "validate-games",
        help="Check every game definition against the schema, and play it.",
    )
    dictionary = commands.add_parser(
        "data-dictionary",
        help="Write docs/DATA-DICTIONARY.md from the operation classes.",
    )
    dictionary.add_argument(
        "--check", action="store_true", help="Fail if the file is out of date."
    )
    seed = commands.add_parser(
        "seed-demo",
        help="Make a room with fake participants and a begun exercise.",
    )
    seed.add_argument(
        "exercise", help="The exercise's slug, such as value-cards-trading."
    )
    seed.add_argument("--people", type=int, default=None, help="How many to seat.")
    arguments = parser.parse_args(argv)
    if arguments.command == "validate-games":
        return _validate_games()
    if arguments.command == "data-dictionary":
        return _data_dictionary(arguments.check)
    if arguments.command == "seed-demo":
        return _seed_demo(arguments.exercise, arguments.people)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
