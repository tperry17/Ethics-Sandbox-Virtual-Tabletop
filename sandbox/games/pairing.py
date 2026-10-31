"""Pairing two tables of a class: the choices a table may make, and what they lead to.

A game declares pairing in its ``game.yaml`` and keeps the outcomes as a CSV.
Everything here reads that data; nothing knows what any choice means.
"""

from __future__ import annotations

from collections.abc import Mapping

from sandbox.games.loader import Game


def may_pair(game: Game, options: Mapping[str, str]) -> bool:
    """Whether tables of ``game`` started with ``options`` may be paired."""
    pairing = game.definition.pairing
    if pairing is None:
        return False
    return all(options.get(key) == value for key, value in pairing.when.items())


def pairing_choices(game: Game, options: Mapping[str, str]) -> tuple[str, ...]:
    """The choices a paired table may record, in the order the file lists them."""
    if not may_pair(game, options):
        return ()
    seen: list[str] = []
    for outcome in game.pair_outcomes:
        if outcome.ours not in seen:
            seen.append(outcome.ours)
    return tuple(seen)


def pair_outcome(game: Game, ours: str, theirs: str) -> str | None:
    """What follows when one table chose ``ours`` and its partner ``theirs``."""
    for outcome in game.pair_outcomes:
        if outcome.ours == ours and outcome.theirs == theirs:
            return outcome.text
    return None
