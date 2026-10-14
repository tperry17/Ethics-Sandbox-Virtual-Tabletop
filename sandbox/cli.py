"""The ``sandbox`` command: ``uv run sandbox validate-games``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def _validate_games() -> int:
    from sandbox.games.validation import validate_games

    report = validate_games()
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sandbox")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "validate-games",
        help="Check every game definition against the schema, and play it.",
    )
    arguments = parser.parse_args(argv)
    if arguments.command == "validate-games":
        return _validate_games()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
