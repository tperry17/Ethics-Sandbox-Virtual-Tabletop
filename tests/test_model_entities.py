from _model_support import DECK, build_sample_table

from sandbox.model.entities import Rect, Zone
from sandbox.model.layout import place_in_zone
from sandbox.model.types import Layout, Visibility, ZoneKind


def test_pieces_in_zone_orders_by_ascending_z() -> None:
    table = build_sample_table(deck_size=3)

    ordered = table.pieces_in_zone(DECK)

    assert [piece.id for piece in ordered] == ["card-0", "card-1", "card-2"]
    assert [piece.z for piece in ordered] == [0, 1, 2]


def test_pieces_in_zone_ignores_pieces_elsewhere() -> None:
    table = build_sample_table(deck_size=2)

    assert table.pieces_in_zone("discard") == []


def test_next_z_in_zone_is_one_above_the_top_or_zero_when_empty() -> None:
    table = build_sample_table(deck_size=3)

    assert table.next_z_in_zone(DECK) == 3
    assert table.next_z_in_zone("discard") == 0


def test_is_facilitator() -> None:
    table = build_sample_table()

    assert table.is_facilitator("facilitator") is True
    assert table.is_facilitator("seat-a") is False
    assert table.is_facilitator("no-such-seat") is False


_RECT = Rect(x=0, y=0, width=100, height=50)


def _rect_zone(layout: Layout) -> Zone:
    return Zone(
        id="z",
        kind=ZoneKind.TABLE,
        label="Z",
        geometry=_RECT,
        visibility=Visibility.PUBLIC,
        layout=layout,
    )


def test_stack_layout_puts_every_piece_at_the_same_point() -> None:
    zone = _rect_zone(Layout.STACK)

    positions = {place_in_zone(zone, index=i, count=5) for i in range(5)}

    assert len(positions) == 1


def test_fan_layout_spreads_across_the_zone_width_and_stays_in_bounds() -> None:
    zone = _rect_zone(Layout.FAN)
    count = 5

    xs = [place_in_zone(zone, index=i, count=count)[0] for i in range(count)]

    left, right = _RECT.x, _RECT.x + _RECT.width
    assert xs == sorted(xs)
    assert all(left <= x <= right for x in xs)


def test_fan_layout_of_one_piece_has_no_rotation() -> None:
    zone = _rect_zone(Layout.FAN)

    _, _, rotation = place_in_zone(zone, index=0, count=1)

    assert rotation == 0.0


def test_grid_layout_tiles_within_the_zone_bounds() -> None:
    zone = _rect_zone(Layout.GRID)
    count = 9

    points = [place_in_zone(zone, index=i, count=count) for i in range(count)]

    assert len({(x, y) for x, y, _ in points}) == count
    for x, y, _ in points:
        assert _RECT.x <= x <= _RECT.x + _RECT.width
        assert _RECT.y <= y <= _RECT.y + _RECT.height


def test_place_in_zone_never_divides_by_a_zero_count() -> None:
    zone = _rect_zone(Layout.FAN)

    # A defensive case: no pieces yet, but a caller still asks where #0 goes.
    x, y, rotation = place_in_zone(zone, index=0, count=0)

    assert isinstance(x, float)
    assert isinstance(y, float)
    assert isinstance(rotation, float)


def test_table_and_piece_equality_is_by_value() -> None:
    one = build_sample_table(seed=7, deck_size=2)
    other = build_sample_table(seed=7, deck_size=2)

    assert one == other
    assert one.pieces["card-0"] == other.pieces["card-0"]
    assert one.pieces["card-0"] is not other.pieces["card-0"]


def test_table_with_different_seed_has_an_unequal_rng() -> None:
    one = build_sample_table(seed=1)
    other = build_sample_table(seed=2)

    assert one.rng != other.rng
    assert one != other
