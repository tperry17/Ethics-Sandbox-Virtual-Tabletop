"""The record of a room: its event log, exported for the facilitator.

Everything here is read from the rows the room already wrote (``Event``,
``Participant``, ``Reflection``); nothing is tracked for the export. The
JSON shape is versioned (``SCHEMA_VERSION``) and described by
``docs/DATA-DICTIONARY.md``, which ``sandbox data-dictionary`` regenerates
from this module and the operation classes, so the two cannot drift.

Two choices belong to the facilitator: whether names are replaced by stable
pseudonyms (``anonymise``), and whether written text is included
(``include_text``). An anonymised export never carries a display name, and
text is left out unless it is asked for.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import zipfile
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sandbox.db.models import Event, Participant, Reflection, Room

SCHEMA_VERSION = 1

# Fields that hold what a person typed. They are removed from the export
# unless the facilitator ticks "include written text".
FREE_TEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "SetText": ("text",),
    "PushClassPrompt": ("text",),
}

# Keys inside a ``Record``'s data that hold what a person wrote (an observation
# note, the text of a proposal that was voted on).
RECORD_TEXT_KEYS = frozenset({"text", "proposal_text"})

# Payload fields that name a participant (not a seat). Anonymised, they
# become the participant's pseudonym.
PARTICIPANT_FIELDS = frozenset({"participant_id"})


def pseudonym(index: int) -> str:
    """``Participant A`` for 0, ``B`` for 1, ... ``Participant AA`` for 26."""
    letters = ""
    number = index
    while True:
        letters = chr(ord("A") + number % 26) + letters
        number = number // 26 - 1
        if number < 0:
            return f"Participant {letters}"


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _scrub(
    op_type: str,
    payload: Mapping[str, Any],
    *,
    include_text: bool,
    pseudonyms: Mapping[str, str] | None,
) -> dict[str, Any]:
    """``payload`` with free text and (when anonymising) participant ids dealt with.

    A transaction's steps are scrubbed by their own operation names.
    """
    hidden = () if include_text else FREE_TEXT_FIELDS.get(op_type, ())
    if (
        op_type == "Record"
        and not include_text
        and isinstance(payload.get("data"), dict)
    ):
        payload = {
            **payload,
            "data": {
                k: v for k, v in payload["data"].items() if k not in RECORD_TEXT_KEYS
            },
        }
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in hidden:
            continue
        if key == "steps" and op_type == "Transaction" and isinstance(value, list):
            out[key] = [
                {
                    "op_type": step["op_type"],
                    "payload": _scrub(
                        step["op_type"],
                        step["payload"],
                        include_text=include_text,
                        pseudonyms=pseudonyms,
                    ),
                }
                for step in value
            ]
        elif (
            pseudonyms is not None
            and key in PARTICIPANT_FIELDS
            and isinstance(value, str)
        ):
            out[key] = pseudonyms.get(value, "Participant (unknown)")
        else:
            out[key] = value
    return out


def build_record(
    session: Session,
    room: Room,
    *,
    anonymise: bool = False,
    include_text: bool = False,
    exported_at: datetime,
) -> dict[str, Any]:
    """The room's whole record as plain, JSON-safe data."""
    people = list(
        session.execute(
            select(Participant)
            .where(Participant.room_id == room.id)
            .order_by(Participant.last_seen_at, Participant.id)
        ).scalars()
    )
    # Stable within one export: the order people are listed in is fixed by
    # the query above, and each pseudonym is that position.
    pseudonyms = {p.id: pseudonym(i) for i, p in enumerate(people)}
    scrub_names = pseudonyms if anonymise else None

    participants: list[dict[str, Any]] = []
    for person in people:
        entry: dict[str, Any] = {
            "participant": pseudonyms[person.id] if anonymise else person.id,
            "seat_id": person.seat_id,
            "is_observer": person.is_observer,
        }
        if not anonymise:
            entry["display_name"] = person.display_name
        participants.append(entry)

    events = session.execute(
        select(Event).where(Event.room_id == room.id).order_by(Event.seq)
    ).scalars()
    event_rows = [
        {
            "seq": event.seq,
            "created_at": _iso(event.created_at),
            "actor_seat": event.actor_seat,
            "op_type": event.op_type,
            "payload": _scrub(
                event.op_type,
                event.payload,
                include_text=include_text,
                pseudonyms=scrub_names,
            ),
        }
        for event in events
    ]

    reflections = session.execute(
        select(Reflection)
        .where(Reflection.room_id == room.id)
        .order_by(Reflection.created_at, Reflection.id)
    ).scalars()
    reflection_rows: list[dict[str, Any]] = []
    for reflection in reflections:
        row: dict[str, Any] = {
            "participant": (
                pseudonyms.get(reflection.participant_id, "Participant (unknown)")
                if anonymise
                else reflection.participant_id
            ),
            "prompt_key": reflection.prompt_key,
            "visibility": reflection.visibility,
            "created_at": _iso(reflection.created_at),
        }
        # An answer the person kept private never leaves the room, even in
        # the facilitator's export; only one they shared can be included.
        if include_text and reflection.visibility == "shared":
            row["body"] = reflection.body
        reflection_rows.append(row)

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": _iso(exported_at),
        "anonymised": anonymise,
        "includes_written_text": include_text,
        "room": {
            "code": None if anonymise else room.code,
            "game_slug": room.game_slug,
            "created_at": _iso(room.created_at),
        },
        "participants": participants,
        "events": event_rows,
        "reflections": reflection_rows,
    }


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _write_csv(columns: list[str], rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(column)) for column in columns])
    return buffer.getvalue()


def record_csv_files(record: Mapping[str, Any]) -> dict[str, str]:
    """One CSV per event type, plus ``participants`` and ``reflections``.

    A transaction's steps are written to their own type's file with
    ``parent_seq`` (the transaction's ``seq``) and ``step`` (their position),
    and the transaction itself keeps its name and label.
    """
    by_type: dict[str, list[dict[str, Any]]] = {}
    for event in record["events"]:
        op_type = event["op_type"]
        base = {
            "seq": event["seq"],
            "created_at": event["created_at"],
            "actor_seat": event["actor_seat"],
        }
        payload = event["payload"]
        if op_type == "Transaction":
            by_type.setdefault(op_type, []).append(
                {**base, **{k: v for k, v in payload.items() if k != "steps"}}
            )
            for index, step in enumerate(payload.get("steps", [])):
                by_type.setdefault(step["op_type"], []).append(
                    {
                        **base,
                        "parent_seq": event["seq"],
                        "step": index,
                        **step["payload"],
                    }
                )
        else:
            by_type.setdefault(op_type, []).append({**base, **payload})

    files: dict[str, str] = {}
    lead = ["seq", "created_at", "actor_seat", "parent_seq", "step"]
    for op_type, rows in sorted(by_type.items()):
        extra: list[str] = []
        for row in rows:
            for key in row:
                if key not in lead and key not in extra:
                    extra.append(key)
        columns = [c for c in lead if any(c in row for row in rows)] + extra
        files[f"events/{op_type}.csv"] = _write_csv(columns, rows)

    people = list(record["participants"])
    files["participants.csv"] = _write_csv(
        ["participant", "display_name", "seat_id", "is_observer"], people
    )
    files["reflections.csv"] = _write_csv(
        ["participant", "prompt_key", "visibility", "created_at", "body"],
        list(record["reflections"]),
    )
    return files


def record_zip(record: Mapping[str, Any]) -> bytes:
    """The CSV export as a zip, with a ``manifest.json`` naming the schema."""
    manifest = {
        key: record[key]
        for key in (
            "schema_version",
            "exported_at",
            "anonymised",
            "includes_written_text",
            "room",
        )
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, text in record_csv_files(record).items():
            archive.writestr(name, text)
    return buffer.getvalue()


# -- the data dictionary --------------------------------------------------------


def operation_classes() -> dict[str, type]:
    """Every operation type that can appear as an event's ``op_type``.

    An operation is a dataclass in the model with both ``validate`` and
    ``apply``; every module that defines some is scanned, so a new one is
    logged, decoded for replay and described here without being listed.
    """
    import sandbox.model.activities as activities
    import sandbox.model.classes as classes
    import sandbox.model.ops as ops
    import sandbox.model.roles as roles
    import sandbox.model.trading as trading

    found: dict[str, type] = {}
    for module in (ops, trading, roles, activities, classes):
        for name in dir(module):
            value = getattr(module, name)
            if (
                isinstance(value, type)
                and dataclasses.is_dataclass(value)
                and value.__module__ == module.__name__
                and hasattr(value, "validate")
                and hasattr(value, "apply")
            ):
                found[name] = value
    return dict(sorted(found.items()))


def data_dictionary_markdown() -> str:
    """``docs/DATA-DICTIONARY.md``, built from the operation classes themselves."""
    lines = [
        "# Data dictionary",
        "",
        "<!-- Generated by `uv run sandbox data-dictionary`. Do not edit by hand;",
        "     edit the operation's docstring or sandbox/web/record.py instead. -->",
        "",
        "The record of a room is its event log, exported by the facilitator as",
        "JSON or as CSV (one file per event type). Speech is never recorded: the",
        "software cannot hear the call, and nothing here is audio or video.",
        "",
        f"Schema version: **{SCHEMA_VERSION}**. The version changes whenever a",
        "field is renamed, removed or changes meaning.",
        "",
        "## The JSON export",
        "",
        "| Field | Meaning |",
        "| --- | --- |",
        "| `schema_version` | The version above. |",
        "| `exported_at` | When the export was made (ISO 8601, UTC). |",
        "| `anonymised` | True if names were replaced by pseudonyms. |",
        "| `includes_written_text` | True if typed text is included. |",
        "| `room` | `code` (null when anonymised), `game_slug`, `created_at`. |",
        "| `participants` | One entry per person: `participant`, `seat_id`,"
        " `is_observer`, and `display_name` unless anonymised. |",
        "| `events` | The event log in order: `seq`, `created_at`, `actor_seat`,"
        " `op_type`, `payload`. |",
        "| `reflections` | Answers to prompts: `participant`, `prompt_key`,"
        " `visibility`, `created_at`, and `body` only when text is included"
        " and the person shared the answer. |",
        "",
        "## Anonymising and written text",
        "",
        "An anonymised export replaces each person with a pseudonym"
        " (`Participant A`, `Participant B`, ...) that is stable within that one"
        " export and means nothing in another. Seats are not people and keep"
        " their ids. The room code is left out.",
        "",
        'Written text is left out unless the facilitator ticks "include written'
        ' text". These fields are removed otherwise: '
        + ", ".join(
            f"`{op}.{field}`"
            for op, fields in FREE_TEXT_FIELDS.items()
            for field in fields
        )
        + ". A reflection that its writer kept private is never included.",
        "",
        "## CSV export",
        "",
        "A zip with `manifest.json`, `participants.csv`, `reflections.csv`, and"
        " `events/<op_type>.csv`, one file per event type. Every events file"
        " starts with `seq`, `created_at` and `actor_seat`. A step of a"
        " `Transaction` is written to its own type's file with `parent_seq`"
        " (the transaction's `seq`) and `step` (its position). Lists are JSON in"
        " one cell.",
        "",
        "## Event types",
        "",
        "`op_type` is the operation's class name. `actor_seat` is the seat that"
        " acted (`room` for the platform itself). Every payload also has"
        " `op_id`, which makes a repeated request apply once.",
        "",
    ]
    for name, cls in operation_classes().items():
        doc = (cls.__doc__ or "").strip().split("\n\n")[0]
        doc = " ".join(doc.split())
        lines.append(f"### {name}")
        lines.append("")
        if doc:
            lines.append(doc)
            lines.append("")
        fields = [f for f in dataclasses.fields(cls) if f.name != "op_id"]
        if fields:
            lines.append("| Field | Type |")
            lines.append("| --- | --- |")
            for f in fields:
                type_name = (
                    f.type
                    if isinstance(f.type, str)
                    else getattr(f.type, "__name__", str(f.type))
                )
                lines.append(f"| `{f.name}` | `{type_name}` |")
        else:
            lines.append("No fields.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
