"""Value Cards Trading's debrief, read from the log.

For one trio: the hand each person was dealt and the hand they ended with,
the trades in order, the offers that were declined and what they asked for,
the cards that changed hands most, those that never moved and those nobody
put in a top three. A top three that its owner did not show is visible only
to its owner. Nothing here compares people; across trios, nothing compares
one trio with another.
"""

from __future__ import annotations

from collections.abc import Sequence

from sandbox.games.content import load_exercise
from sandbox.games.debrief import (
    ClassContext,
    Context,
    Entry,
    Section,
    activity_debrief,
    activity_entries,
    bars,
    class_debrief,
    clock,
    counted,
    listing,
    outcomes_and_questions,
    piece_ids_of,
    table,
    text,
    timing_block,
)
from sandbox.model import Table

KIND = "value-cards-trading"


def _components(table_: Table, zone_id: str) -> list[str]:
    return [
        piece.component_id
        for piece in table_.pieces_in_zone(zone_id)
        if piece.component_id is not None
    ]


def hands_dealt_and_final(context: Context) -> dict[str, tuple[list[str], list[str]]]:
    """For each seat: the cards dealt, and the cards held at the end."""
    activity = context.activity
    deal = next(
        (
            entry
            for entry in context.entries
            if entry.macro == "macro:deal" and entry.activity_id == activity.id
        ),
        None,
    )
    hands: dict[str, tuple[list[str], list[str]]] = {}
    for seat in activity.seats:
        zone = f"{activity.id}:hand-{seat}"
        dealt = (
            _components(context.table_at(deal.seq), zone) if deal is not None else []
        )
        hands[seat] = (dealt, _components(context.final, zone))
    return hands


def _shown_pieces(entries: Sequence[Entry], pieces: dict[str, str]) -> set[str]:
    return {
        str(entry.payload["piece_id"])
        for entry in entries
        if entry.op_type == "ShowTo" and str(entry.payload["piece_id"]) in pieces
    }


def trades(
    context: Context, names: dict[str, str]
) -> tuple[list[tuple[str, ...]], list[tuple[str, ...]], list[str]]:
    """Accepted trades, declined offers, and every card that changed hands."""
    pieces = piece_ids_of(context.entries)
    face = context.game.faces()

    def card(piece_id: str) -> str:
        component = pieces.get(piece_id)
        if component is None:
            return "a card"
        shown = face.get(component)
        return (shown.title if shown is not None else None) or component

    offers: dict[str, Entry] = {}
    accepted: list[tuple[str, ...]] = []
    declined: list[tuple[str, ...]] = []
    moved: list[str] = []
    for entry in activity_entries(context.entries, context.activity):
        if entry.op_type == "OfferSwap":
            offers[str(entry.payload["op_id"])] = entry
            continue
        if entry.op_type not in ("AcceptSwap", "DeclineSwap"):
            continue
        offer = offers.get(str(entry.payload["offer_id"]))
        if offer is None:
            continue
        who = str(offer.actor_seat)
        other = str(offer.payload["to_seat"])
        give = [card(p) for p in offer.payload["give"]]
        want = [card(p) for p in offer.payload["want"]]
        when = clock(entry.at, context.started_at)
        if entry.op_type == "AcceptSwap":
            accepted.append(
                (
                    when,
                    f"{names[who]} gave {', '.join(give)}",
                    f"{names[other]} gave {', '.join(want)}",
                )
            )
            moved += give + want
        else:
            declined.append(
                (
                    when,
                    f"{names[who]} offered {', '.join(give)}",
                    f"to {names[other]}, asking for {', '.join(want)}",
                )
            )
    return accepted, declined, moved


@activity_debrief(KIND)
def value_cards_debrief(context: Context) -> list[Section]:
    activity = context.activity
    names = {seat: context.name(seat) for seat in activity.seats}
    face = context.game.faces()

    def title(component: str) -> str:
        shown = face.get(component)
        return (shown.title if shown is not None else None) or component

    hands = hands_dealt_and_final(context)
    people_rows: list[tuple[str, ...]] = []
    for seat in activity.seats:
        dealt, final = hands[seat]
        kept = [c for c in dealt if c in final]
        given = [c for c in dealt if c not in final]
        received = [c for c in final if c not in dealt]
        people_rows.append(
            (
                names[seat],
                ", ".join(sorted(title(c) for c in dealt)) or "not dealt",
                ", ".join(sorted(title(c) for c in kept)) or "none",
                ", ".join(sorted(title(c) for c in given)) or "none",
                ", ".join(sorted(title(c) for c in received)) or "none",
            )
        )

    pieces = piece_ids_of(context.entries)
    shown = _shown_pieces(context.entries, pieces)
    top_rows: list[tuple[str, ...]] = []
    top_cards: list[str] = []
    for seat in activity.seats:
        zone = f"{activity.id}:top-three-{seat}"
        held = context.final.pieces_in_zone(zone)
        components = [p.component_id for p in held if p.component_id is not None]
        top_cards += components
        visible = context.mine(seat) or any(p.id in shown for p in held)
        if not held:
            line = "none chosen"
        elif visible:
            line = ", ".join(title(c) for c in components)
        else:
            line = "not shown"
        top_rows.append((names[seat], line))

    accepted, declined, moved = trades(context, names)
    dealt_all = [c for dealt, _ in hands.values() for c in dealt]
    changed = counted([title(c) for c in moved])
    never = sorted(
        title(c) for c in set(dealt_all) if title(c) not in {n for n, _ in changed}
    )
    nobody = sorted(title(c) for c in set(dealt_all) if c not in set(top_cards))

    spans: list[tuple[str, float | None]] = []
    deal_entry = next(
        (
            e
            for e in context.entries
            if e.macro == "macro:deal" and e.activity_id == activity.id
        ),
        None,
    )
    if deal_entry is not None and accepted:
        first = next(
            e
            for e in activity_entries(context.entries, activity)
            if e.op_type == "AcceptSwap"
        )
        last = [
            e
            for e in activity_entries(context.entries, activity)
            if e.op_type == "AcceptSwap"
        ][-1]
        spans.append(
            (
                "From dealing to the first trade",
                (first.at - deal_entry.at).total_seconds(),
            )
        )
        spans.append(
            ("From the first trade to the last", (last.at - first.at).total_seconds())
        )
    elif deal_entry is not None:
        spans.append(("From dealing to the first trade", None))

    outcomes = load_exercise(KIND).learning_outcomes
    return [
        Section(
            title="Hands, side by side",
            blocks=(
                table(
                    ["Person", "Dealt", "Kept", "Given away", "Received"],
                    people_rows,
                ),
            ),
        ),
        Section(
            title="Top three",
            note=(
                "A top three is shown here only if its owner showed it. Your own is "
                "always shown to you."
            ),
            blocks=(table(["Person", "Top three"], top_rows),),
        ),
        Section(
            title="The trades, in order",
            blocks=(
                table(["When", "One side", "The other side"], accepted)
                if accepted
                else text("No trades were made."),
                table(
                    ["When", "Offered", "Asked for"],
                    declined,
                    title="Offers that were declined",
                )
                if declined
                else text(
                    "No offers were declined.", title="Offers that were declined"
                ),
            ),
        ),
        Section(
            title="Across the trio",
            blocks=(
                bars(changed, title="Cards that changed hands, and how many times")
                if changed
                else text("No cards changed hands."),
                listing(never, title="Cards that never moved"),
                listing(nobody, title="Cards nobody put in a top three"),
            ),
        ),
        Section(
            title="Timing",
            blocks=(
                timing_block(
                    spans,
                    activity_entries(context.entries, activity),
                    context.started_at,
                ),
            ),
        ),
        outcomes_and_questions(context.game, outcomes),
    ]


@class_debrief(KIND)
def value_cards_class(context: ClassContext) -> list[Section]:
    """Which values were kept and given away most often, across all trios.

    Each count is of cards, pooled over every trio. No trio is set beside
    another.
    """
    kept: list[str] = []
    given: list[str] = []
    face = context.game.faces()

    def title(component: str) -> str:
        shown = face.get(component)
        return (shown.title if shown is not None else None) or component

    for tablecontext in context.tables:
        for dealt, final in hands_dealt_and_final(tablecontext).values():
            kept += [title(c) for c in dealt if c in final]
            given += [title(c) for c in dealt if c not in final]
    blocks = [
        bars(counted(kept)[:10], title="Values kept most often")
        if kept
        else text("No hands were recorded."),
        bars(counted(given)[:10], title="Values given away most often")
        if given
        else text("No cards were given away."),
        text(
            f"Across {len(context.tables)} trio(s). Counts pool every trio; no trio is "
            "compared with another."
        ),
    ]
    return [Section(title="Across the class", blocks=tuple(blocks))]
