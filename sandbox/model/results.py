"""What an operation reports back: either it happened, or a clear reason it didn't."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Patch:
    """A minimal description of one thing that changed on the table.

    ``kind`` names the sort of entity affected. ``op`` says what happened to
    it: ``upsert`` for a piece/zone/seat/stroke that now exists or has
    changed fields, ``remove`` for one that no longer exists, ``event`` for
    something that happened without changing any stored field (a pointer
    ping, a reveal, a peek). ``entity_id`` identifies the affected piece,
    zone, seat or stroke, and is ``None`` for a table-wide event.

    ``fields`` carries the raw truth as the model sees it. Stripping what a
    particular viewer is not entitled to see is not this type's job - that
    happens when a patch is projected for a viewer, on its way to a browser.
    """

    kind: Literal["piece", "zone", "seat", "stroke", "offer", "table"]
    op: Literal["upsert", "remove", "event"]
    entity_id: str | None
    fields: dict[str, object]


@dataclass(frozen=True)
class Ok:
    """The operation applied. Here is what changed."""

    patches: list[Patch]


@dataclass(frozen=True)
class Reject:
    """The operation did not apply. The reason is a sentence a person could be shown."""

    reason: str


OpOutcome = Ok | Reject
