/**
 * A recorded session, for developing and testing rendering with no backend.
 *
 * Everything here is fixture data in the shape the server sends, and
 * nothing in it is a rule: no exercise's real deck, no notion of a legal
 * move, no decision about what any of it means. It exists so that the
 * rendering path - a snapshot, a glide, a reveal, a deal, ink, a cursor -
 * can be exercised end to end in a browser that has never opened a socket.
 */

import type {
  ComponentView,
  PatchView,
  PieceKind,
  PieceView,
  SeatView,
  SnapshotMessage,
  ZoneView,
} from "./protocol.js";

export interface RecordedFrame {
  /** Milliseconds after the snapshot. */
  at: number;
  message: import("./protocol.js").ServerMessage;
}

export interface Recording {
  snapshot: SnapshotMessage;
  frames: RecordedFrame[];
}

export const MY_SEAT = "seat-1";
const OTHER_SEAT = "seat-2";

function zone(
  id: string,
  kind: ZoneView["kind"],
  label: string,
  x: number,
  y: number,
  width: number,
  height: number,
  visibility: ZoneView["visibility"] = "public",
  layout: ZoneView["layout"] = "free",
  ownerSeat: string | null = null,
): ZoneView {
  return {
    id,
    kind,
    label,
    geometry: { shape: "rect", x, y, width, height },
    visibility,
    layout,
    owner_seat: ownerSeat,
  };
}

function piece(
  id: string,
  kind: PieceKind,
  zoneId: string,
  x: number,
  y: number,
  z: number,
  componentId: string | null,
  rotation = 0,
): PieceView {
  return {
    id,
    kind,
    zone_id: zoneId,
    x,
    y,
    z,
    rotation,
    face_up: componentId !== null,
    held_by: null,
    locked: false,
    component_id: componentId,
  };
}

function component(
  id: string,
  title: string,
  body: string,
  folio: string,
): ComponentView {
  return {
    id,
    title,
    body,
    folio,
    image: null,
    tint_index: null,
    width: null,
    height: null,
  };
}

const SEATS: SeatView[] = [
  {
    id: MY_SEAT,
    label: "Seat 1",
    tint_index: 0,
    participant_id: "p-1",
    display_name: "Ines Okafor",
    is_facilitator: true,
    connected: true,
  },
  {
    id: OTHER_SEAT,
    label: "Seat 2",
    tint_index: 1,
    participant_id: "p-2",
    display_name: "Rowan Bell",
    is_facilitator: false,
    connected: true,
  },
];

const COMPONENTS: ComponentView[] = [
  component(
    "sample-a",
    "Equal standing",
    "Everyone affected by a decision has the same claim to be heard about it.",
    "i",
  ),
  component(
    "sample-b",
    "Least harm",
    "Where harm cannot be avoided, it should fall where it does the least damage.",
    "ii",
  ),
  component(
    "sample-c",
    "Kept promises",
    "An agreement freely made is a reason to act even when it has stopped being convenient.",
    "iii",
  ),
  component(
    "sample-d",
    "Room to differ",
    "A settlement everyone can live with beats agreement nobody actually holds.",
    "iv",
  ),
  component(
    "sample-e",
    "Who decides",
    "Ask not only what the right answer is, but whose place it is to give it.",
    "v",
  ),
  component(
    "sample-f",
    "The long view",
    "Count the people who are not in the room yet.",
    "vi",
  ),
  component("marker-a", "3", "", ""),
];

const ZONES: ZoneView[] = [
  zone("table", "table", "The table", 0, 0, 1400, 1000),
  zone("deck", "deck", "Value deck", 30, 400, 240, 320, "hidden", "stack"),
  zone("discard", "discard", "Set aside", 1130, 400, 240, 320, "public", "stack"),
  zone("claims", "slot", "Public claims", 380, 340, 640, 300, "public", "spread"),
  zone(
    "hand-2",
    "hand",
    "Hand",
    380,
    20,
    640,
    320,
    "private_to_owner",
    "fan",
    OTHER_SEAT,
  ),
  zone(
    "hand-1",
    "hand",
    "Your hand",
    380,
    700,
    640,
    300,
    "private_to_owner",
    "fan",
    MY_SEAT,
  ),
];

function startingPieces(): PieceView[] {
  const pieces: PieceView[] = [];
  for (let index = 0; index < 8; index += 1) {
    pieces.push(piece(`deck-${index}`, "card", "deck", 150, 560, index, null));
  }
  pieces.push(piece("claim-1", "card", "claims", 560, 490, 0, "sample-a"));
  pieces.push(piece("claim-2", "card", "claims", 840, 490, 1, null, 2));
  pieces.push(piece("discard-1", "card", "discard", 1250, 560, 0, null));
  pieces.push(piece("hand-1-a", "card", "hand-1", 520, 830, 0, "sample-b"));
  pieces.push(piece("hand-1-b", "card", "hand-1", 700, 830, 1, "sample-c"));
  pieces.push(piece("hand-1-c", "card", "hand-1", 880, 830, 2, "sample-d"));
  pieces.push(piece("hand-2-a", "card", "hand-2", 620, 180, 0, null, -4));
  pieces.push(piece("hand-2-b", "card", "hand-2", 790, 180, 1, null, 4));
  pieces.push(piece("token-1", "token", "table", 180, 160, 0, "marker-a"));
  pieces.push(piece("cube-1", "cube", "table", 260, 160, 1, null));
  pieces.push(piece("die-1", "die", "table", 1220, 160, 2, null));
  pieces.push(
    piece("note-1", "note", "table", 1180, 830, 3, "sample-f", -3),
  );
  return pieces;
}

function piecePatch(id: string, fields: Record<string, unknown>): PatchView {
  return { kind: "piece", op: "upsert", entity_id: id, fields };
}

/** A short session: a glide, a reveal, a deal, some ink, a ping, a notice. */
export function demoRecording(): Recording {
  const snapshot: SnapshotMessage = {
    type: "snapshot",
    seq: 0,
    view_table: {
      pieces: startingPieces(),
      zones: ZONES,
      seats: SEATS,
      strokes: [],
      version: 1,
    },
    seats: SEATS,
    you: {
      participant_id: "p-1",
      seat_id: MY_SEAT,
      display_name: "Ines Okafor",
      is_facilitator: true,
      is_observer: false,
    },
    components: COMPONENTS,
    macros: [
      { id: "set-up", label: "Set up", hint: "Arrange the table", facilitator_only: true },
      { id: "deal", label: "Deal", hint: null, facilitator_only: true },
      { id: "reset", label: "Reset", hint: null, facilitator_only: true },
    ],
  };

  const frames: RecordedFrame[] = [
    {
      at: 300,
      message: {
        type: "presence",
        seats: SEATS,
        cursors: [{ seat_id: OTHER_SEAT, x: 820, y: 300 }],
      },
    },
    {
      at: 600,
      message: {
        type: "patches",
        seq: 1,
        patches: [piecePatch("claim-2", { held_by: OTHER_SEAT })],
      },
    },
    {
      at: 800,
      message: {
        type: "patches",
        seq: 2,
        patches: [piecePatch("claim-2", { x: 700, y: 430, rotation: -4 })],
      },
    },
    {
      at: 1200,
      message: {
        type: "patches",
        seq: 3,
        patches: [
          piecePatch("claim-2", {
            held_by: null,
            face_up: true,
            component_id: "sample-e",
          }),
        ],
      },
    },
    {
      at: 1500,
      message: {
        type: "patches",
        seq: 4,
        patches: [
          piecePatch("deck-7", {
            zone_id: "hand-1",
            x: 960,
            y: 830,
            z: 3,
            face_up: true,
            component_id: "sample-f",
          }),
        ],
      },
    },
    {
      at: 1800,
      message: {
        type: "patches",
        seq: 5,
        patches: [
          {
            kind: "table",
            op: "event",
            entity_id: null,
            fields: { type: "point", seat_id: OTHER_SEAT, x: 700, y: 430 },
          },
        ],
      },
    },
    {
      at: 2100,
      message: {
        type: "patches",
        seq: 6,
        patches: [
          {
            kind: "stroke",
            op: "upsert",
            entity_id: "ink-1",
            fields: {
              seat_id: OTHER_SEAT,
              colour: "#e69f00",
              width: 5,
              points: [
                [420, 300],
                [520, 280],
                [620, 300],
              ],
            },
          },
        ],
      },
    },
    {
      at: 2400,
      message: {
        type: "patches",
        seq: 7,
        patches: [
          {
            kind: "stroke",
            op: "upsert",
            entity_id: "ink-1",
            fields: {
              points: [
                [420, 300],
                [520, 280],
                [620, 300],
                [720, 270],
                [860, 300],
              ],
            },
          },
        ],
      },
    },
    {
      at: 2700,
      message: { type: "notice", level: "info", text: "Rowan Bell has joined the table." },
    },
    {
      at: 3000,
      message: {
        type: "presence",
        seats: SEATS,
        cursors: [{ seat_id: OTHER_SEAT, x: 640, y: 520 }],
      },
    },
  ];

  return { snapshot, frames };
}

/**
 * The same table carrying `count` pieces, and one of them being dragged.
 *
 * This is the shape of the performance question the project cares about:
 * a crowded table, one piece moving under someone's own hand, and a frame
 * budget that has to survive it.
 */
/** When the drag in `denseRecording` begins, and so when measuring should. */
export const DENSE_DRAG_START_MS = 1200;

export function denseRecording(count: number, dragFrames = 200): Recording {
  const recording = demoRecording();
  const pieces = recording.snapshot.view_table.pieces.slice();
  const columns = Math.ceil(Math.sqrt(count * 1.6));
  for (let index = 0; index < count; index += 1) {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const face = COMPONENTS[index % 6]!;
    pieces.push(
      piece(
        `bulk-${index}`,
        "card",
        "table",
        120 + column * 44,
        120 + row * 58,
        100 + index,
        index % 3 === 0 ? null : face.id,
        ((index % 7) - 3) * 1.5,
      ),
    );
  }
  recording.snapshot.view_table.pieces = pieces;

  // The drag starts after the table has finished appearing, so that a
  // measurement taken during it measures dragging rather than mounting.
  const frames: RecordedFrame[] = [
    {
      at: DENSE_DRAG_START_MS - 100,
      message: {
        type: "patches",
        seq: 1,
        patches: [piecePatch("bulk-0", { held_by: MY_SEAT })],
      },
    },
  ];
  for (let step = 0; step < dragFrames; step += 1) {
    const angle = (step / dragFrames) * Math.PI * 4;
    frames.push({
      at: DENSE_DRAG_START_MS + step * 16,
      message: {
        type: "patches",
        seq: 2 + step,
        patches: [
          piecePatch("bulk-0", {
            x: 700 + Math.cos(angle) * 320,
            y: 500 + Math.sin(angle) * 220,
          }),
        ],
      },
    });
  }
  frames.push({
    at: DENSE_DRAG_START_MS + dragFrames * 16 + 50,
    message: {
      type: "patches",
      seq: 2 + dragFrames,
      patches: [piecePatch("bulk-0", { held_by: null })],
    },
  });
  recording.frames = frames;
  return recording;
}
