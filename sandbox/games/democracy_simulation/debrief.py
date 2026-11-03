"""Leadership and Knowledge in Popular Rule's debrief, read from the log.

For one city: a timeline (the moderators, each proposal as written with who
wrote it and its edits, when it was put to the vote and what happened),
each vote's tally, interest against vote, the information that existed in
the room, and the debrief questions under their learning outcomes.

What stays private: a card's back is never shown to anyone but its holder
and the facilitator; jobs are public. In Hudrosia's council only the tally
is shown unless the facilitator chooses to show more.
"""

from __future__ import annotations

from typing import Any

from sandbox.content_loading import read_rows
from sandbox.games.content import load_exercise
from sandbox.games.debrief import (
    ClassContext,
    Context,
    Entry,
    Section,
    activity_debrief,
    checklist,
    class_debrief,
    clock,
    listing,
    outcomes_and_questions,
    table,
    text,
    timing_block,
)
from sandbox.games.pairing import may_pair, pair_outcome

KIND = "democracy-simulation"
HUDROSIA = "hudrosia"
ROOT = "exercises/democracy-simulation"


def _records(context: Context, label: str) -> list[Entry]:
    return [
        e
        for e in context.entries
        if e.op_type == "Record"
        and e.activity_id == context.activity.id
        and e.payload["label"] == label
    ]


def _proposals(context: Context) -> list[dict[str, Any]]:
    """Each proposal: its number, author, piece id, and every text written on it."""
    found: list[dict[str, Any]] = []
    by_seq: dict[int, list[Entry]] = {}
    for entry in context.entries:
        by_seq.setdefault(entry.seq, []).append(entry)
    for record in _records(context, "proposal"):
        spawn = next((e for e in by_seq[record.seq] if e.op_type == "Spawn"), None)
        piece = (spawn.payload.get("piece_ids") or [None])[0] if spawn else None
        edits = [
            (e.at, str(e.actor_seat), str(e.payload["text"]))
            for e in context.entries
            if e.op_type == "SetText"
            and piece is not None
            and e.payload["piece_id"] == piece
        ]
        found.append(
            {
                "number": record.payload["data"]["number"],
                "by": str(record.payload["data"]["by"]),
                "piece": piece,
                "at": record.at,
                "edits": edits,
            }
        )
    return found


def _votes(context: Context) -> list[Entry]:
    return _records(context, "vote")


def _seat_for_label(context: Context, label: str) -> str | None:
    for seat in context.activity.seats:
        if context.label(seat) == label:
            return seat
    return None


def _person(context: Context, label: str) -> str:
    seat = _seat_for_label(context, label)
    return context.name(seat) if seat is not None else label


def _vote_word(value: str) -> str:
    return "For" if value == "yes" else "Not for"


def information_items(context: Context) -> list[tuple[str, str]]:
    """Every knowledge item and rumour on the cards dealt, as (id, text).

    Items are listed without saying who held them, so no card's back is
    given away. The cards dealt come from the log's record of the meeting.
    """
    started = _records(context, "meeting_started")
    if not started:
        return []
    data = started[0].payload["data"]
    phase = str(data["phase"])
    seats: dict[str, dict[str, Any]] = data["seats"]
    items: list[tuple[str, str]] = []
    features = {
        row["feature"]: row
        for row in read_rows(f"{ROOT}/features.csv")
        if row["phase"] == phase
    }
    if any(v.get("river") for v in seats.values()) and features.get("River"):
        items.append(
            (
                "feature:river",
                features["River"]["knowledge"] or features["River"]["interest"],
            )
        )
    if any(v.get("rumour") for v in seats.values()) and features.get("Rumors"):
        items.append(("feature:rumours", features["Rumors"]["knowledge"]))
    dealt_jobs = {str(v["job"]) for v in seats.values()}
    for row in read_rows(f"{ROOT}/jobs.csv"):
        if row["phase"] == phase and row["job"] in dealt_jobs and row["elite"] != "yes":
            items.append((f"job:{row['key']}", f"{row['job']}: {row['knowledge']}"))
    city = str(data["city"])
    for row in read_rows(f"{ROOT}/elite_sheets.csv"):
        if (
            row["phase"] == phase
            and row["city"].lower() == city
            and row["job"] in dealt_jobs
        ):
            first = row["text"].strip().splitlines()
            items.append(
                (
                    f"sheet:{row['key']}",
                    f"Information sheet for the {row['job']}: {' '.join(first[:3])}",
                )
            )
    return items


@activity_debrief(KIND)
def democracy_debrief(context: Context) -> list[Section]:
    activity = context.activity
    started = context.started_at
    sections: list[Section] = []

    # -- the timeline
    timeline: list[tuple[int, tuple[str, ...]]] = []
    for entry in _records(context, "moderators_chosen"):
        chosen = ", ".join(
            _person(context, str(label)) for label in entry.payload["data"]["seats"]
        )
        timeline.append(
            (entry.seq, (clock(entry.at, started), "Moderators chosen", chosen))
        )
    for entry in _records(context, "meeting_started"):
        timeline.append((entry.seq, (clock(entry.at, started), "Meeting started", "")))
    for entry in _records(context, "assembly_opened"):
        timeline.append(
            (
                entry.seq,
                (
                    clock(entry.at, started),
                    "Council opened to a public assembly",
                    "",
                ),
            )
        )
    proposals = _proposals(context)
    for proposal in proposals:
        who = _person(context, proposal["by"])
        timeline.append(
            (
                int(proposal["at"].timestamp() * 1000),
                (
                    clock(proposal["at"], started),
                    f"Proposal {proposal['number']} opened",
                    f"by {who}",
                ),
            )
        )
        for index, (when, actor, body) in enumerate(proposal["edits"]):
            name = context.name(actor) if actor in context.final.seats else actor
            label = "written" if index == 0 else "edited"
            timeline.append(
                (
                    int(when.timestamp() * 1000),
                    (
                        clock(when, started),
                        f"Proposal {proposal['number']} {label}",
                        f"by {name}: {body}",
                    ),
                )
            )
    votes = _votes(context)
    for number, entry in enumerate(votes, start=1):
        data = entry.payload["data"]
        timeline.append(
            (
                int(entry.at.timestamp() * 1000) + 1,
                (
                    clock(entry.at, started),
                    f"Vote {number} counted",
                    f"{data['proposal_text']!r}: {data['result'].replace('-', ' ')}",
                ),
            )
        )
    timeline.sort(key=lambda pair: pair[0])
    sections.append(
        Section(
            title="Timeline",
            note="Read from the log.",
            blocks=(
                table(["When", "What", "Detail"], [row for _, row in timeline])
                if timeline
                else text("Nothing was logged for this city yet."),
            ),
        )
    )

    # -- each vote
    show_council = bool(context.settings.get("show_council_votes"))
    vote_blocks = []
    for number, entry in enumerate(votes, start=1):
        data = entry.payload["data"]
        rows: list[tuple[str, ...]] = [
            ("For", str(data["for"])),
            ("Not for", str(data["not_for"])),
            ("Present", str(data["present"])),
            ("Result", str(data["result"]).replace("-", " ")),
        ]
        if not data["secret"] or show_council:
            for label, value in data["votes"].items():
                rows.append((_person(context, label), _vote_word(value)))
        vote_blocks.append(
            table(["", ""], rows, title=f"Vote {number}: {data['proposal_text']}")
        )
    if not vote_blocks:
        vote_blocks.append(text("No vote was counted."))
    elif any(entry.payload["data"]["secret"] for entry in votes) and not show_council:
        vote_blocks.append(
            text(
                "This council voted in secret, so only the tally is shown. The "
                "facilitator can choose to show how each member voted."
            )
        )
    sections.append(Section(title="Votes", blocks=tuple(vote_blocks)))

    # -- interest against vote
    meeting = _records(context, "meeting_started")
    if meeting:
        seats: dict[str, dict[str, Any]] = meeting[0].payload["data"]["seats"]
        head = [
            "Person",
            "Job",
            "Card favoured",
            *[f"Vote {n}" for n in range(1, len(votes) + 1)],
        ]
        grid: list[tuple[str, ...]] = []
        for label, info in seats.items():
            seat = _seat_for_label(context, label)
            if not context.is_facilitator and not (seat and context.mine(seat)):
                continue
            row = [_person(context, label), str(info["job"]), str(info["interest"])]
            for entry in votes:
                cast = entry.payload["data"]["votes"]
                if label in cast:
                    row.append(_vote_word(cast[label]))
                else:
                    row.append("not a voter")
            grid.append(tuple(row))
        note = "The facilitator sees everyone. Each person sees only their own row."
        sections.append(
            Section(
                title="Interest against vote",
                note=note,
                blocks=(
                    table(head, grid)
                    if grid
                    else text(
                        "Your row appears here once you are in this city and the "
                        "meeting has started."
                    ),
                ),
            )
        )

    # -- information
    items = information_items(context)
    surfaced = set(context.settings.get("surfaced") or ())
    if items:
        if context.is_facilitator:
            block = checklist(
                [(i, t, i in surfaced) for i, t in items], title="Tick what surfaced"
            )
        else:
            block = listing(
                [t for i, t in items if i in surfaced], title="What surfaced"
            )
        sections.append(
            Section(
                title="Information that existed in the room",
                note=(
                    "The software cannot hear the call, so the facilitator ticks "
                    "what surfaced."
                ),
                blocks=(block,),
            )
        )

    # -- timing
    spans: list[tuple[str, float | None]] = []
    deal = next(
        (
            e
            for e in context.entries
            if e.macro == "macro:deal" and e.activity_id == activity.id
        ),
        None,
    )
    began = meeting[0] if meeting else None
    if deal is not None:
        spans.append(
            (
                "From dealing to the meeting starting",
                (began.at - deal.at).total_seconds() if began else None,
            )
        )
    opens = [
        e
        for e in context.entries
        if e.macro == "macro:put_to_vote" and e.activity_id == activity.id
    ]
    for number, closed in enumerate(votes, start=1):
        opened = next((o for o in reversed(opens) if o.seq < closed.seq), None)
        spans.append(
            (
                f"Vote {number}",
                (closed.at - opened.at).total_seconds() if opened else None,
            )
        )
    mine = [e for e in context.entries if e.activity_id == activity.id]
    sections.append(
        Section(title="Timing", blocks=(timing_block(spans, mine, started),))
    )

    sections.append(
        outcomes_and_questions(context.game, load_exercise(KIND).learning_outcomes)
    )
    return sections


def _decisions(context: Context) -> str:
    passed = [
        str(entry.payload["data"]["proposal_text"])
        for entry in _votes(context)
        if entry.payload["data"]["result"] == "passed"
    ]
    return "; ".join(passed) if passed else "No proposal passed."


@class_debrief(KIND)
def democracy_class(context: ClassContext) -> list[Section]:
    """Each city's decision side by side, democracies and oligarchies apart.

    The comparison comes first: the document calls the exercise a controlled
    experiment, so the cities are read against each other before anything else.
    """
    democracies: list[str] = []
    oligarchies: list[str] = []
    for tablecontext in context.tables:
        city = tablecontext.activity.options.get("city", "")
        decision = context.group.decisions.get(tablecontext.activity.id, "")
        line = f"{tablecontext.activity.title}: {_decisions(tablecontext)}"
        if decision:
            line += f" Decision recorded: {decision}."
        (oligarchies if city == HUDROSIA else democracies).append(line)
    rows: list[tuple[str, ...]] = []
    for index in range(max(len(democracies), len(oligarchies), 1)):
        rows.append(
            (
                democracies[index] if index < len(democracies) else "",
                oligarchies[index] if index < len(oligarchies) else "",
            )
        )
    sections = [
        Section(
            title="The cities side by side",
            note=(
                "The cities share the same people, interests and information. Only "
                "the decision procedure differs."
            ),
            blocks=(table(["Democracies", "Oligarchies"], rows),),
        )
    ]
    pairs: list[tuple[str, ...]] = []
    for first, second in context.group.pairs:
        one = context.group.decisions.get(first, "")
        two = context.group.decisions.get(second, "")
        if one and two:
            outcome = pair_outcome(context.game, one, two) or ""
            names = {c.activity.id: c.activity.title for c in context.tables}
            pairs.append(
                (names.get(first, first), one, names.get(second, second), two, outcome)
            )
    first_options = context.tables[0].activity.options if context.tables else {}
    if pairs and may_pair(context.game, first_options):
        sections.append(
            Section(
                title="Scenario 2: the paired cities",
                blocks=(
                    table(["City", "Chose", "Paired city", "Chose", "Outcome"], pairs),
                ),
            )
        )
    return sections
