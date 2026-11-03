"""The rules: dealing, the co-Chairs, proposals, votes.

For Leadership and Knowledge in Popular Rule.

One activity is one city, and its options say which: ``city`` (Potamosia, a
democracy, or Hudrosia, an oligarchy) and ``phase`` (1, the construction
project, or 2, going to war). The cards say who is who, so everything here
asks ``context.cards`` what a card is and the table where it sits.

- ``deal`` gives each citizen one role card, the elite their information
  sheet, and every seat a name tent showing its job. A card's back, and a
  sheet, are never shown to anyone (the decks are ``revealable: false``).
- ``choose_moderators`` (Potamosia) picks two co-Chairs by a logged shuffle.
- ``new_proposal`` adds a numbered proposal. Who added it, and when, is in
  the event log.
- ``put_to_vote`` calls a vote on the one written proposal that has been
  moved onto the floor; ``close_vote`` counts it against everyone who may vote
  (a show of hands: anyone without a hand up is against). The speaking queue
  is ``join_queue``, ``next_speaker`` and ``clear_queue``. Potamosia's hands
  are turned up in each voter's name tent. Hudrosia's council votes in
  secret: the table sees only a tally of fresh, unmarked tokens, and who
  voted for what is in the log and in the facilitator's view.
"""

from __future__ import annotations

from collections.abc import Sequence

from sandbox.games.hatch import GameContext, MacroRefused, macro, preview
from sandbox.model import (
    Deal,
    Despawn,
    Flip,
    MoveToZone,
    Operation,
    Piece,
    PieceKind,
    Record,
    SetProp,
    SetText,
    Shuffle,
    Spawn,
    Table,
    new_op_id,
)
from sandbox.model.entities import written_text

POTAMOSIA = "potamosia"
HUDROSIA = "hudrosia"
KING = "King"


# -- reading the table ---------------------------------------------------------


def _fields(context: GameContext, piece: Piece) -> dict[str, str]:
    return dict(context.cards.get(piece.component_id, {}))


def _kind(context: GameContext, piece: Piece) -> str:
    return _fields(context, piece).get("kind", "")


def _everything(table: Table, context: GameContext) -> list[Piece]:
    """Every piece in this activity's own zones, in a stable order."""
    zones = {zone for zone in table.zones if zone.startswith(context.prefix)}
    return sorted(
        (piece for piece in table.pieces.values() if piece.zone_id in zones),
        key=lambda piece: (piece.zone_id, piece.z),
    )


def _in(table: Table, context: GameContext, zone: str) -> list[Piece]:
    return table.pieces_in_zone(context.zone(zone))


def _role_in_hand(table: Table, context: GameContext, seat: str) -> Piece | None:
    return next(
        (
            piece
            for piece in table.pieces_in_zone(context.zone("hand", seat))
            if _kind(context, piece) == "role"
        ),
        None,
    )


def _dealt(table: Table, context: GameContext) -> bool:
    return any(_role_in_hand(table, context, seat) for seat in context.seats)


def _component(piece: Piece) -> str:
    return piece.component_id


def _of(table: Table, context: GameContext, component: str) -> list[Piece]:
    return [p for p in _everything(table, context) if p.component_id == component]


def _despawn(pieces: Sequence[Piece]) -> list[Operation]:
    return [Despawn(piece_ids=tuple(piece.id for piece in pieces))] if pieces else []


def _spawn(component: str, kind: PieceKind, zone: str) -> Spawn:
    return Spawn(
        component_id=component, kind=kind, zone_id=zone, piece_ids=(new_op_id(),)
    )


def _city(context: GameContext) -> str:
    return context.options.get("city", POTAMOSIA)


# -- who may call a vote ----------------------------------------------------------


def _may_call(table: Table, context: GameContext) -> bool:
    """The facilitator, a co-Chair (Potamosia) or a king (Hudrosia)."""
    seat = context.actor_seat
    if table.is_facilitator(seat):
        return True
    if seat not in context.seats:
        return False
    if _city(context) == POTAMOSIA:
        tent = table.pieces_in_zone(context.zone("tent", seat))
        return any(piece.component_id == "moderator-token" for piece in tent)
    role = _role_in_hand(table, context, seat)
    return role is not None and _fields(context, role).get("job") == KING


def _require_caller(table: Table, context: GameContext) -> None:
    if _may_call(table, context):
        return
    who = "a co-Chair" if _city(context) == POTAMOSIA else "a king"
    raise MacroRefused(f"Only {who}, or the facilitator, can do that.")


# -- dealing ------------------------------------------------------------------------


def _meeting_started(table: Table, context: GameContext) -> bool:
    return bool(_of(table, context, "meeting-started"))


@macro("deal")
def deal(table: Table, context: GameContext) -> list[Operation]:
    """Cards 1 to N to N citizens, sheets to the elite, a name tent to all."""
    if _meeting_started(table, context):
        raise MacroRefused(
            "The meeting has started, so the cards cannot be dealt again."
        )
    seats = context.seats
    count = len(seats)
    box, spare = context.zone("box"), context.zone("spare")
    operations: list[Operation] = []

    # Take back whatever an earlier deal left: cards, sheets, tents, tokens.
    for piece in _everything(table, context):
        if piece.component_id.startswith(("tent-", "moderator-token")):
            continue
        if piece.zone_id in (box, spare, context.zone("notice")):
            continue
        if _kind(context, piece):
            operations.append(MoveToZone(piece_id=piece.id, zone_id=spare))
    operations += _despawn(
        [
            piece
            for piece in _everything(table, context)
            if piece.component_id.startswith("tent-")
            or piece.component_id in ("moderator-token", "meeting-started")
        ]
    )
    tidy = preview(table, operations)

    # Only cards 1 to N are in play; the rest, and the sheets, wait in the spare pile.
    in_box = [p for p in tidy.pieces_in_zone(box)]
    in_spare = [p for p in tidy.pieces_in_zone(spare)]
    for piece in [*in_box, *in_spare]:
        fields = _fields(context, piece)
        wanted = fields.get("kind") == "role" and int(fields["card_number"]) <= count
        if wanted and piece.zone_id != box:
            operations.append(MoveToZone(piece_id=piece.id, zone_id=box))
        elif not wanted and piece.zone_id != spare:
            operations.append(MoveToZone(piece_id=piece.id, zone_id=spare))
    operations.append(Shuffle(zone_id=box))
    hands = tuple(context.zone("hand", seat) for seat in seats)
    operations.append(Deal(from_zone=box, to_zones=hands, count_each=1))
    dealt = preview(table, operations)

    for seat in seats:
        hand = context.zone("hand", seat)
        role = next(
            p for p in dealt.pieces_in_zone(hand) if _kind(context, p) == "role"
        )
        fields = _fields(context, role)
        operations.append(Flip(piece_id=role.id, face_up=True))
        sheet = next(
            (
                p
                for p in dealt.pieces_in_zone(spare)
                if _kind(context, p) == "sheet"
                and _fields(context, p).get("card_number") == fields["card_number"]
            ),
            None,
        )
        if sheet is not None:
            operations += [
                MoveToZone(piece_id=sheet.id, zone_id=hand),
                Flip(piece_id=sheet.id, face_up=True),
            ]
        tent = context.zone("tent", seat)
        operations.append(_spawn(f"tent-{fields['job'].lower()}", PieceKind.NOTE, tent))
    final = preview(table, operations)
    if _city(context) == HUDROSIA:
        for seat in seats:
            held = _role_in_hand(final, context, seat)
            assert held is not None
            if _fields(context, held)["council"] == "yes":
                tent_piece = final.pieces_in_zone(context.zone("tent", seat))[-1]
                operations.append(
                    MoveToZone(piece_id=tent_piece.id, zone_id=context.zone("council"))
                )
    return operations


@macro("choose_moderators")
def choose_moderators(table: Table, context: GameContext) -> list[Operation]:
    """Two seats at random get a Moderator token and the moderator card."""
    if _city(context) != POTAMOSIA:
        raise MacroRefused("Hudrosia has no co-Chairs; its kings run the council.")
    if not _dealt(table, context):
        raise MacroRefused("Deal the role cards first.")
    if _of(table, context, "moderator-token"):
        raise MacroRefused("The co-Chairs have been chosen already.")
    lots = context.zone("lots")
    operations: list[Operation] = []
    for seat in context.seats:
        lot = new_op_id()
        operations += [
            Spawn(
                component_id="lot",
                kind=PieceKind.MARKER,
                zone_id=lots,
                piece_ids=(lot,),
            ),
            SetProp(piece_id=lot, key="seat", value=seat),
        ]
    operations.append(Shuffle(zone_id=lots))
    drawn = preview(table, operations)
    chosen = [str(p.props["seat"]) for p in drawn.pieces_in_zone(lots)[:2]]
    operations += _despawn(drawn.pieces_in_zone(lots))
    cards = [
        p
        for p in drawn.pieces_in_zone(context.zone("spare"))
        if _kind(context, p) == "moderator"
    ]
    for seat, card in zip(chosen, cards, strict=True):
        operations += [
            _spawn("moderator-token", PieceKind.TOKEN, context.zone("tent", seat)),
            MoveToZone(piece_id=card.id, zone_id=context.zone("hand", seat)),
            Flip(piece_id=card.id, face_up=True),
        ]
    operations.append(
        Record(
            label="moderators_chosen",
            data={"seats": [table.seats[seat].label for seat in chosen]},
        )
    )
    return operations


@macro("start_meeting")
def start_meeting(table: Table, context: GameContext) -> list[Operation]:
    """Keep each seat's card, job and interest; the cards can no longer be redealt."""
    if not _dealt(table, context):
        raise MacroRefused("Deal the role cards first.")
    if _meeting_started(table, context):
        raise MacroRefused("The meeting has started already.")
    seats: dict[str, object] = {}
    for seat in context.seats:
        role = _role_in_hand(table, context, seat)
        assert role is not None
        fields = _fields(context, role)
        seats[table.seats[seat].label] = {
            "card_number": int(fields["card_number"]),
            "job": fields["job"],
            "interest": fields["interest"],
            "river": fields["river"] == "yes",
            "rumour": fields["rumour"] == "yes",
            "council": fields["council"] == "yes",
        }
    return [
        _spawn("meeting-started", PieceKind.MARKER, context.zone("spare")),
        Record(
            label="meeting_started",
            data={
                "city": _city(context),
                "phase": context.options.get("phase", ""),
                "seats": seats,
            },
        ),
    ]


@macro("open_assembly")
def open_assembly(table: Table, context: GameContext) -> list[Operation]:
    """Hudrosia: a king (or the facilitator) opens the council to the townspeople.

    The log keeps when, so the debrief can show the change from council to
    assembly. Nothing else on the table changes.
    """
    if _city(context) != HUDROSIA:
        raise MacroRefused("Only Hudrosia has a council that opens to an assembly.")
    _require_caller(table, context)
    if not _meeting_started(table, context):
        raise MacroRefused("Start the meeting first.")
    if _of(table, context, "assembly-open"):
        raise MacroRefused("The public assembly is open already.")
    return [
        _spawn("assembly-open", PieceKind.MARKER, context.zone("floor")),
        Record(
            label="assembly_opened",
            data={"city": _city(context), "phase": context.options.get("phase", "")},
        ),
    ]


# -- proposals and votes -------------------------------------------------------------

PROPOSAL_ZONES = ("proposals", "floor", "passed", "not-passed")


def _proposals(table: Table, context: GameContext) -> list[Piece]:
    return [
        piece
        for zone in PROPOSAL_ZONES
        for piece in _in(table, context, zone)
        if piece.component_id == "proposal"
    ]


@macro("new_proposal")
def new_proposal(table: Table, context: GameContext) -> list[Operation]:
    """A blank proposal, numbered by the log, to be written on with the pen."""
    number = len(_proposals(table, context)) + 1
    seat = context.actor_seat
    label = table.seats[seat].label if seat in table.seats else seat
    return [
        _spawn("proposal", PieceKind.NOTE, context.zone("proposals")),
        Record(label="proposal", data={"number": number, "by": label}),
    ]


def _voters(table: Table, context: GameContext) -> tuple[str, ...]:
    """Every seat in Potamosia; in Hudrosia, the council's."""
    if _city(context) == POTAMOSIA:
        return context.seats
    council = []
    for seat in context.seats:
        role = _role_in_hand(table, context, seat)
        if role is not None and _fields(context, role).get("council") == "yes":
            council.append(seat)
    return tuple(council)


def _ballot_tokens(table: Table, context: GameContext) -> list[Piece]:
    return [p for p in _everything(table, context) if p.component_id in ("yes", "no")]


@macro("put_to_vote")
def put_to_vote(table: Table, context: GameContext) -> list[Operation]:
    """Call a vote on the one written proposal on the floor, and hand out ballots.

    The caller chooses the proposal by moving it onto the floor. In
    Potamosia each citizen has one "For" token to raise; in Hudrosia each
    council member has a "For" and an "Against" and casts one, in secret.
    """
    _require_caller(table, context)
    if not _dealt(table, context):
        raise MacroRefused("Deal the role cards first.")
    if _of(table, context, "vote-open"):
        raise MacroRefused("A vote is open. Count it first.")
    on_floor = [p for p in _in(table, context, "floor") if p.component_id == "proposal"]
    if not on_floor:
        raise MacroRefused("Move the proposal to be voted on onto the floor first.")
    if len(on_floor) > 1:
        raise MacroRefused("Only one proposal can be on the floor at a time.")
    if not written_text(on_floor[0]):
        raise MacroRefused("Write the proposal on its note before it is voted on.")
    operations: list[Operation] = []
    # The last vote's tokens and result go.
    operations += _despawn(_ballot_tokens(table, context))
    operations += _despawn(
        [
            p
            for p in _in(table, context, "floor")
            if p.component_id.startswith("result-")
        ]
    )
    operations.append(_spawn("vote-open", PieceKind.MARKER, context.zone("floor")))
    for seat in _voters(table, context):
        box = context.zone("ballot-box", seat)
        operations.append(_spawn("yes", PieceKind.TOKEN, box))
        if _city(context) == HUDROSIA:
            operations.append(_spawn("no", PieceKind.TOKEN, box))
    return operations


@macro("close_vote")
def close_vote(table: Table, context: GameContext) -> list[Operation]:
    """Count the ballots against everyone who may vote.

    A vote is a show of hands, so only the "for" side is ever counted: a
    proposal passes when more than half of those present are for it, and
    anyone without a hand up is against. Hudrosia's council votes the same
    way over its own members, with a secret "Against" token that counts the
    same as no token at all. A tie reports as a tie and nothing passes.
    """
    _require_caller(table, context)
    markers = _of(table, context, "vote-open")
    if not markers:
        raise MacroRefused("No vote is open.")
    voters = _voters(table, context)
    cast: dict[str, str] = {}
    for seat in voters:
        slot = table.pieces_in_zone(context.zone("ballot", seat))
        if slot:
            cast[seat] = slot[0].component_id
    yes = sum(1 for value in cast.values() if value == "yes")
    no = len(voters) - yes
    outcome = (
        "passed"
        if yes * 2 > len(voters)
        else "tie"
        if yes * 2 == len(voters)
        else "not-passed"
    )
    proposal = next(
        p for p in _in(table, context, "floor") if p.component_id == "proposal"
    )
    operations: list[Operation] = _despawn(markers)
    destination = {"passed": "passed", "not-passed": "not-passed", "tie": "proposals"}
    operations.append(
        MoveToZone(piece_id=proposal.id, zone_id=context.zone(destination[outcome]))
    )

    secret = _city(context) == HUDROSIA
    cast_tokens = [
        p for seat in cast for p in table.pieces_in_zone(context.zone("ballot", seat))
    ]
    uncast = [
        p
        for seat in voters
        for p in table.pieces_in_zone(context.zone("ballot-box", seat))
    ]
    if secret:
        # Fresh tokens carry the tally, so no id leads back to a voter.
        operations += _despawn([*cast_tokens, *uncast])
    else:
        operations += _despawn(uncast)
        for seat in cast:
            token = table.pieces_in_zone(context.zone("ballot", seat))[0]
            operations += [
                MoveToZone(piece_id=token.id, zone_id=context.zone("tent", seat)),
                Flip(piece_id=token.id, face_up=True),
            ]
    # The tally shows the hands that were raised (and, in secret, the
    # council's "Against" tokens); everyone else is simply not for it.
    against_cast = sum(1 for value in cast.values() if value == "no")
    for _ in range(yes):
        operations.append(_spawn("yes", PieceKind.TOKEN, context.zone("tally-yes")))
    for _ in range(against_cast if secret else 0):
        operations.append(_spawn("no", PieceKind.TOKEN, context.zone("tally-no")))
    result = {
        "passed": "result-passed",
        "not-passed": "result-not-passed",
        "tie": "result-tie",
    }[outcome]
    operations.append(_spawn(result, PieceKind.MARKER, context.zone("floor")))
    operations.append(
        Record(
            label="vote",
            data={
                "city": _city(context),
                "phase": context.options.get("phase", ""),
                "proposal": proposal.id,
                "proposal_text": written_text(proposal),
                "present": len(voters),
                "for": yes,
                "not_for": no,
                "result": outcome,
                "secret": secret,
                "votes": {
                    table.seats[seat].label: cast.get(seat, "no") for seat in voters
                },
            },
        )
    )
    return operations


# -- the speaking queue -----------------------------------------------------------


def _queue(table: Table, context: GameContext) -> list[Piece]:
    return _in(table, context, "queue")


@macro("join_queue")
def join_queue(table: Table, context: GameContext) -> list[Operation]:
    """Put your name on the speaking queue, as your name tent says it."""
    seat = context.actor_seat
    if seat not in context.seats:
        raise MacroRefused("Only the city's citizens can join its queue.")
    if any(p.props.get("seat") == seat for p in _queue(table, context)):
        raise MacroRefused("You are already in the queue.")
    tent = next(
        iter(table.pieces_in_zone(context.zone("tent", seat))),
        None,
    )
    name = (written_text(tent) if tent is not None else None) or table.seats[seat].label
    note = new_op_id()
    return [
        Spawn(
            component_id="speaker",
            kind=PieceKind.NOTE,
            zone_id=context.zone("queue"),
            piece_ids=(note,),
        ),
        SetText(piece_id=note, text=name),
        SetProp(piece_id=note, key="seat", value=seat),
    ]


@macro("next_speaker")
def next_speaker(table: Table, context: GameContext) -> list[Operation]:
    """The first in the queue has had their turn: take them off."""
    _require_caller(table, context)
    queue = _queue(table, context)
    if not queue:
        raise MacroRefused("Nobody is in the queue.")
    return _despawn(queue[:1])


@macro("clear_queue")
def clear_queue(table: Table, context: GameContext) -> list[Operation]:
    """Empty the queue."""
    _require_caller(table, context)
    queue = _queue(table, context)
    if not queue:
        raise MacroRefused("Nobody is in the queue.")
    return _despawn(queue)
