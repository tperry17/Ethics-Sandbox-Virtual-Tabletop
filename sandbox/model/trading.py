"""Swaps between two seats: an offer, and the answer that settles it.

A swap is the one way a piece changes hands between two owners' zones. One
seat offers some of its own pieces for the same number of another seat's,
and the other seat accepts or declines; the offerer may withdraw until it is
answered. Acceptance exchanges the pieces as a single operation, so no one
ever sees a half-made trade. Nothing here knows what the pieces are.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sandbox.model.entities import Offer, Piece, Table
from sandbox.model.ops import _clear_reveal, _piece_patch, new_op_id
from sandbox.model.results import Patch


def _offer_patch(offer: Offer) -> Patch:
    return Patch(
        kind="offer",
        op="upsert",
        entity_id=offer.id,
        fields={
            "from_seat": offer.from_seat,
            "to_seat": offer.to_seat,
            "give": list(offer.give),
            "want": list(offer.want),
        },
    )


def _offer_removed(offer_id: str) -> Patch:
    return Patch(kind="offer", op="remove", entity_id=offer_id, fields={})


def _owner_of(table: Table, piece: Piece) -> str | None:
    zone = table.zones.get(piece.zone_id)
    return None if zone is None else zone.owner_seat


def _seat_label(table: Table, seat_id: str) -> str:
    seat = table.seats.get(seat_id)
    return seat_id if seat is None else seat.label


def _reason_pieces_not_in_place(table: Table, offer: Offer) -> str | None:
    """Whether the pieces of ``offer`` are still where its makers left them."""
    stale = (
        "Those cards have moved since the offer was made. "
        "Withdraw it and make a new one."
    )
    for ids, owner in ((offer.give, offer.from_seat), (offer.want, offer.to_seat)):
        for piece_id in ids:
            piece = table.pieces.get(piece_id)
            if piece is None or _owner_of(table, piece) != owner:
                return stale
    return None


@dataclass(frozen=True)
class OfferSwap:
    """Offer some of your own pieces for the same number of another seat's.

    The offer's id is this operation's ``op_id``. ``give`` are pieces in
    your own zones; ``want`` are pieces in ``to_seat``'s.
    """

    to_seat: str
    give: tuple[str, ...]
    want: tuple[str, ...]
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        me = table.seats.get(actor_seat)
        them = table.seats.get(self.to_seat)
        if me is None or me.is_facilitator:
            return "Only a seated player can make an offer."
        if them is None or them.is_facilitator:
            return f"There is no player {self.to_seat!r} to trade with."
        if self.to_seat == actor_seat:
            return "You cannot trade with yourself."
        if not self.give and not self.want:
            return "Choose at least one card from each hand."
        if not self.want:
            return "A trade is an exchange. Ask for a card in return."
        if not self.give:
            return "A trade is an exchange. You cannot take a card without giving one."
        if len(self.give) != len(self.want):
            return (
                f"A trade swaps the same number of cards each way. "
                f"You offered {len(self.give)} and asked for {len(self.want)}."
            )
        if len(set(self.give)) != len(self.give) or len(set(self.want)) != len(
            self.want
        ):
            return "A card can be named only once in an offer."
        pending = {
            piece_id
            for offer in table.offers.values()
            for piece_id in (*offer.give, *offer.want)
        }
        for ids, owner in ((self.give, actor_seat), (self.want, self.to_seat)):
            for piece_id in ids:
                piece = table.pieces.get(piece_id)
                if piece is None:
                    return f"There is no piece {piece_id!r} on the table."
                if _owner_of(table, piece) != owner:
                    whose = (
                        "your own hand"
                        if owner == actor_seat
                        else f"{_seat_label(table, owner)}'s hand"
                    )
                    return f"Every card in this offer must be in {whose}."
                if piece.locked or piece.held_by not in (None, owner):
                    return "A card in this offer is locked or being held."
                if piece_id in pending:
                    return "A card in this offer is already in another open offer."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        offer = Offer(
            id=self.op_id,
            from_seat=actor_seat,
            to_seat=self.to_seat,
            give=self.give,
            want=self.want,
        )
        table.offers[offer.id] = offer
        return [_offer_patch(offer)]


def _reason_no_such_offer(table: Table, offer_id: str) -> str | None:
    if offer_id not in table.offers:
        return "That offer has already been answered or withdrawn."
    return None


@dataclass(frozen=True)
class AcceptSwap:
    """Agree to an offer made to you. The pieces change hands at once."""

    offer_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_no_such_offer(table, self.offer_id)) is not None:
            return reason
        offer = table.offers[self.offer_id]
        if actor_seat != offer.to_seat:
            return "Only the player this offer was made to can accept it."
        return _reason_pieces_not_in_place(table, offer)

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        offer = table.offers.pop(self.offer_id)
        patches: list[Patch] = []
        for mine_id, theirs_id in zip(offer.give, offer.want, strict=True):
            mine, theirs = table.pieces[mine_id], table.pieces[theirs_id]
            for name in ("zone_id", "x", "y", "z", "rotation"):
                first, second = getattr(mine, name), getattr(theirs, name)
                setattr(mine, name, second)
                setattr(theirs, name, first)
            for piece in (mine, theirs):
                piece.held_by = None
                _clear_reveal(piece)
                patches.append(_piece_patch(piece))
        table.swapped.add(frozenset((offer.from_seat, offer.to_seat)))
        patches.append(_offer_removed(offer.id))
        return patches


@dataclass(frozen=True)
class DeclineSwap:
    """Turn down an offer made to you. Nothing moves."""

    offer_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_no_such_offer(table, self.offer_id)) is not None:
            return reason
        if actor_seat != table.offers[self.offer_id].to_seat:
            return "Only the player this offer was made to can decline it."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        table.offers.pop(self.offer_id)
        return [_offer_removed(self.offer_id)]


@dataclass(frozen=True)
class WithdrawSwap:
    """Take back your own offer before it is answered. The facilitator may too."""

    offer_id: str
    op_id: str = field(default_factory=new_op_id)

    def validate(self, table: Table, actor_seat: str) -> str | None:
        if (reason := _reason_no_such_offer(table, self.offer_id)) is not None:
            return reason
        offer = table.offers[self.offer_id]
        if actor_seat != offer.from_seat and not table.is_facilitator(actor_seat):
            return "Only the player who made this offer can withdraw it."
        return None

    def apply(self, table: Table, actor_seat: str) -> list[Patch]:
        table.offers.pop(self.offer_id)
        return [_offer_removed(self.offer_id)]
