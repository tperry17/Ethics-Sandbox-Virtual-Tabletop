"""A small, fixed tabletop used across the model test suite.

Not a test module itself - a shared fixture builder. Every test that needs a
table with seats, zones and pieces already in place should build one from
here, so the tests read as scenarios on a known table rather than repeating
setup boilerplate.
"""

from __future__ import annotations

from sandbox.model.entities import Piece, Rect, Seat, Table, Zone
from sandbox.model.rng import TableRng
from sandbox.model.types import Layout, PieceKind, Visibility, ZoneKind

FACILITATOR = "facilitator"
SEAT_A = "seat-a"
SEAT_B = "seat-b"

DECK = "deck"
DISCARD = "discard"
PUBLIC_TABLE = "table"
HAND_A = "hand-a"
HAND_B = "hand-b"
FACILITATOR_TRAY = "facilitator-tray"

DECK_SIZE = 6


def build_sample_table(seed: int = 0, deck_size: int = DECK_SIZE) -> Table:
    """A table with a facilitator, two seats, and a deck of face-down cards.

    Zones: a hidden ``deck``, an empty public ``discard``, an empty public
    ``table``, a private hand per seat, and a facilitator-only tray. The deck
    starts with ``deck_size`` cards, each with a distinct ``component_id``,
    stacked in ``z`` order 0..deck_size-1 (index 0 at the bottom).
    """
    table = Table(rng=TableRng(seed=seed))

    table.seats[FACILITATOR] = Seat(
        id=FACILITATOR, label="Facilitator", tint_index=0, is_facilitator=True
    )
    table.seats[SEAT_A] = Seat(id=SEAT_A, label="A", tint_index=1)
    table.seats[SEAT_B] = Seat(id=SEAT_B, label="B", tint_index=2)

    table.zones[DECK] = Zone(
        id=DECK,
        kind=ZoneKind.DECK,
        label="Deck",
        geometry=Rect(x=0, y=0, width=100, height=140),
        visibility=Visibility.HIDDEN,
        layout=Layout.STACK,
    )
    table.zones[DISCARD] = Zone(
        id=DISCARD,
        kind=ZoneKind.DISCARD,
        label="Discard",
        geometry=Rect(x=120, y=0, width=100, height=140),
        visibility=Visibility.PUBLIC,
        layout=Layout.STACK,
    )
    table.zones[PUBLIC_TABLE] = Zone(
        id=PUBLIC_TABLE,
        kind=ZoneKind.TABLE,
        label="Table",
        geometry=Rect(x=0, y=200, width=800, height=400),
        visibility=Visibility.PUBLIC,
        layout=Layout.FREE,
    )
    table.zones[HAND_A] = Zone(
        id=HAND_A,
        kind=ZoneKind.HAND,
        label="A's hand",
        geometry=Rect(x=0, y=650, width=400, height=120),
        visibility=Visibility.PRIVATE_TO_OWNER,
        layout=Layout.FAN,
        owner_seat=SEAT_A,
    )
    table.zones[HAND_B] = Zone(
        id=HAND_B,
        kind=ZoneKind.HAND,
        label="B's hand",
        geometry=Rect(x=400, y=650, width=400, height=120),
        visibility=Visibility.PRIVATE_TO_OWNER,
        layout=Layout.FAN,
        owner_seat=SEAT_B,
    )
    table.zones[FACILITATOR_TRAY] = Zone(
        id=FACILITATOR_TRAY,
        kind=ZoneKind.TRAY,
        label="Facilitator tray",
        geometry=Rect(x=820, y=0, width=100, height=140),
        visibility=Visibility.FACILITATOR_ONLY,
        layout=Layout.STACK,
    )

    for index in range(deck_size):
        piece_id = f"card-{index}"
        table.pieces[piece_id] = Piece(
            id=piece_id,
            kind=PieceKind.CARD,
            component_id=f"the-{index}-of-values",
            zone_id=DECK,
            x=50,
            y=70,
            z=index,
            face_up=False,
        )

    return table


def build_die(die_id: str = "die-1", zone_id: str = PUBLIC_TABLE) -> Piece:
    """A six-sided die piece, ready to be added to a table's pieces."""
    return Piece(
        id=die_id,
        kind=PieceKind.DIE,
        component_id="d6",
        zone_id=zone_id,
        x=10,
        y=10,
        z=0,
        face_up=True,
        props={"faces": [1, 2, 3, 4, 5, 6]},
    )
