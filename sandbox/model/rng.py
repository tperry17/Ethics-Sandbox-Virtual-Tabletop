"""A single seeded random source per table, so any session can be replayed exactly.

Model code must never reach for the ``random`` module's global functions -
draw from a table's own ``TableRng`` instead. Its state is part of the
table, so a table can be reconstructed and its remaining randomness continues
exactly where the original would have.
"""

from __future__ import annotations

import random
from typing import Any


class TableRng:
    """Wraps ``random.Random`` so its state can be captured, restored, and compared."""

    def __init__(self, seed: int, source: random.Random | None = None) -> None:
        self.seed = seed
        self._random = source if source is not None else random.Random(seed)

    def get_state(self) -> tuple[Any, ...]:
        """The internal state, suitable for storing and restoring later."""
        state: tuple[Any, ...] = self._random.getstate()
        return state

    def set_state(self, state: tuple[Any, ...]) -> None:
        self._random.setstate(state)

    def clone(self) -> TableRng:
        """An independent copy that will produce exactly the same future draws."""
        clone = TableRng(self.seed)
        clone.set_state(self.get_state())
        return clone

    def shuffled_indices(self, length: int) -> list[int]:
        """A random permutation of ``range(length)``."""
        indices = list(range(length))
        self._random.shuffle(indices)
        return indices

    def choice_index(self, length: int) -> int:
        """One index in ``range(length)``, chosen uniformly at random."""
        if length <= 0:
            raise ValueError("cannot choose an index from an empty range")
        return self._random.randrange(length)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TableRng):
            return NotImplemented
        return self.seed == other.seed and self.get_state() == other.get_state()

    def __repr__(self) -> str:
        return f"TableRng(seed={self.seed!r})"
