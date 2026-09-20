/**
 * The wire, exactly as `sandbox/web/live.py` defines it.
 *
 * Every type here mirrors a Pydantic model on the server. Nothing in this
 * file knows a rule: it describes the shape of what arrives, not what any
 * of it means. When the server's models change, these change with them and
 * nothing else in the client has to.
 */

export type PieceKind =
  | "card"
  | "die"
  | "cube"
  | "meeple"
  | "token"
  | "note"
  | "marker"
  | "board";

export type ZoneKind =
  | "table"
  | "hand"
  | "deck"
  | "discard"
  | "tray"
  | "seat_area"
  | "slot";

export type ZoneVisibility =
  | "public"
  | "private_to_owner"
  | "facilitator_only"
  | "hidden";

export type ZoneLayout = "free" | "stack" | "fan" | "grid" | "spread";

export interface RectView {
  shape: "rect";
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PolygonView {
  shape: "polygon";
  points: Array<[number, number]>;
}

export type GeometryView = RectView | PolygonView;

/**
 * One piece as this viewer is entitled to see it.
 *
 * `component_id` is null for every piece whose face this viewer may not
 * see. That is not a placeholder to be resolved later: there is no face to
 * draw, and the client has no way to ask for one.
 */
export interface PieceView {
  id: string;
  kind: PieceKind;
  zone_id: string;
  x: number;
  y: number;
  z: number;
  rotation: number;
  face_up: boolean;
  held_by: string | null;
  locked: boolean;
  component_id: string | null;
}

export interface ZoneView {
  id: string;
  kind: ZoneKind;
  label: string;
  geometry: GeometryView;
  visibility: ZoneVisibility;
  layout: ZoneLayout;
  owner_seat: string | null;
}

export interface SeatView {
  id: string;
  label: string;
  tint_index: number;
  participant_id: string | null;
  display_name: string | null;
  is_facilitator: boolean;
  connected: boolean;
}

export interface StrokeView {
  id: string;
  seat_id: string;
  colour: string;
  width: number;
  points: Array<[number, number]>;
}

/** What a component looks like. Sent only for faces this viewer already holds. */
export interface ComponentView {
  id: string;
  title: string | null;
  body: string | null;
  folio: string | null;
  image: string | null;
  tint_index: number | null;
  width: number | null;
  height: number | null;
}

/** One toolbar button. The client knows its label and nothing about its effect. */
export interface MacroView {
  id: string;
  label: string;
  hint: string | null;
  facilitator_only: boolean;
}

export interface YouView {
  participant_id: string;
  seat_id: string | null;
  display_name: string;
  is_facilitator: boolean;
  is_observer: boolean;
}

export interface TableView {
  pieces: PieceView[];
  zones: ZoneView[];
  seats: SeatView[];
  strokes: StrokeView[];
  version: number;
}

export interface PatchView {
  kind: "piece" | "zone" | "seat" | "stroke" | "table";
  op: "upsert" | "remove" | "event";
  entity_id: string | null;
  fields: Record<string, unknown>;
}

export interface CursorView {
  seat_id: string;
  x: number;
  y: number;
}

export interface SnapshotMessage {
  type: "snapshot";
  seq: number;
  view_table: TableView;
  seats: SeatView[];
  you: YouView;
  components: ComponentView[];
  macros: MacroView[];
}

export interface PatchesMessage {
  type: "patches";
  seq: number;
  patches: PatchView[];
}

export interface RejectMessage {
  type: "reject";
  client_id: string;
  reason: string;
}

export interface PresenceMessage {
  type: "presence";
  seats: SeatView[];
  cursors: CursorView[];
}

export interface NoticeMessage {
  type: "notice";
  level: "info" | "warning";
  text: string;
}

export type ServerMessage =
  | SnapshotMessage
  | PatchesMessage
  | RejectMessage
  | PresenceMessage
  | NoticeMessage;

export interface HelloMessage {
  type: "hello";
  room_code: string;
  last_seq: number;
}

export interface IntentMessage {
  type: "intent";
  client_id: string;
  op_type: string;
  payload: Record<string, unknown>;
}

export interface CursorMessage {
  type: "cursor";
  x: number;
  y: number;
}

export interface HeartbeatMessage {
  type: "heartbeat";
}

export type ClientMessage =
  | HelloMessage
  | IntentMessage
  | CursorMessage
  | HeartbeatMessage;

/** Connected, catching up, or not talking to anything. */
export type LinkStatus = "connected" | "reconnecting" | "offline";

/**
 * Anything the renderer can be driven by.
 *
 * The live WebSocket and the recorded session in `fake-server.ts` both
 * satisfy this, which is what lets rendering be developed and tested with
 * no backend running at all.
 */
export interface ServerLink {
  /** Begin, and keep, whatever connection this link represents. */
  start(): void;
  stop(): void;
  send(message: ClientMessage): void;
  onMessage(handler: (message: ServerMessage) => void): void;
  onStatus(handler: (status: LinkStatus) => void): void;
}
