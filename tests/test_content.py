"""Editorial content is read from content/, not hardcoded in Python."""

from __future__ import annotations

import pytest

from sandbox.games.content import load_exercise
from sandbox.games.value_cards import VALUE_CARDS_TRADING
from sandbox.web.content import PRINCIPLES


def test_principles_load_from_csv() -> None:
    assert len(PRINCIPLES) == 6
    assert PRINCIPLES[0].title == "Steelman before you object"
    assert all(p.title and p.copy for p in PRINCIPLES)


def test_load_exercise_assembles_every_field() -> None:
    exercise = load_exercise("value-cards-trading")

    assert exercise == VALUE_CARDS_TRADING
    assert exercise.title == "Value Cards Trading"
    assert len(exercise.session_shape) == 3
    assert len(exercise.tensions) == 3
    assert len(exercise.facilitator_notes) == 3
    assert len(exercise.preview_zones) == 3
    assert len(exercise.preview_cards) == 3
    assert exercise.preview_cards[0].title == "Freedom of inquiry"


def test_load_exercise_raises_for_an_unknown_slug() -> None:
    with pytest.raises(KeyError):
        load_exercise("not-a-real-exercise")
