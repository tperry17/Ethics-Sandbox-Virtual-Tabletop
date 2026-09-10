"""Shared enumerations for the tabletop model."""

from __future__ import annotations

from enum import StrEnum


class PieceKind(StrEnum):
    """What kind of physical object a piece represents."""

    CARD = "card"
    DIE = "die"
    CUBE = "cube"
    MEEPLE = "meeple"
    TOKEN = "token"
    NOTE = "note"
    MARKER = "marker"
    BOARD = "board"


class ZoneKind(StrEnum):
    """What role a zone plays on the table."""

    TABLE = "table"
    HAND = "hand"
    DECK = "deck"
    DISCARD = "discard"
    TRAY = "tray"
    SEAT_AREA = "seat_area"
    SLOT = "slot"


class Visibility(StrEnum):
    """Who is entitled to see the face of a piece resting in a zone."""

    PUBLIC = "public"
    PRIVATE_TO_OWNER = "private_to_owner"
    FACILITATOR_ONLY = "facilitator_only"
    HIDDEN = "hidden"


class Layout(StrEnum):
    """How pieces already in a zone are automatically arranged."""

    FREE = "free"
    STACK = "stack"
    FAN = "fan"
    GRID = "grid"
    SPREAD = "spread"
