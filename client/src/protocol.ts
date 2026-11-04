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
  | "board"
  | "tile";

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
  /** Seats being shown this piece's face right now. Public: a reveal is seen. */
  revealed_to: string[];
  /** Who is showing it, or null when nobody is. */
  revealed_by: string | null;
  /** A rolled die's face, sent only to a viewer who may see the die's face. */
  value?: string | null;
  /** What has been written on a note, sent only to a viewer who may see its face. */
  text?: string | null;
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
  /** A card's group, drawn as a frame colour. */
  group?: string | null;
  /** An icon drawn beside the folio. */
  badge?: string | null;
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
  /** Asked before the button runs, when the server says it is destructive. */
  confirm: string | null;
  /** Set when the button belongs to a running activity rather than the room. */
  activity_id?: string | null;
}

/** An activity in the room: signing up, or running. Who plays is public. */
export interface ActivityView {
  id: string;
  kind: string;
  title: string;
  min_players: number;
  max_players: number;
  seats: string[];
  status: "signup" | "running";
  /** What was chosen when it was opened, such as which city. */
  options?: Record<string, string>;
  /** The class this is one table of, or "" when it stands alone. */
  class_id?: string;
}

/** Two paired tables of a class. Sent to the facilitator only. */
export interface ClassPairView {
  first: string;
  second: string;
  first_decision: string | null;
  second_decision: string | null;
  /** What someone at each table proposed, waiting for the facilitator. */
  first_proposed?: string | null;
  second_proposed?: string | null;
  /** What follows from the two decisions, once both are in. */
  outcome: string | null;
  /** The partner is hypothetical: only the facilitator decides for it. */
  hypothetical?: boolean;
  /** With a hypothetical partner still undecided: what follows from each choice. */
  outcomes?: { their_choice: string; text: string }[];
}

/** A class: one activity at several tables, run by the facilitator. */
export interface ClassView {
  id: string;
  kind: string;
  title: string;
  tables: string[];
  /** Seconds left at the moment this was sent, or null with no timer. */
  timer_remaining: number | null;
  timer_seconds: number;
  prompt: string;
  /** Counts up with each prompt pushed, so a dismissed one stays dismissed. */
  prompt_serial: number;
  can_pair?: boolean;
  pair_choices?: string[];
  /** For someone at a paired table: their table, and what it has chosen. */
  your_table?: string;
  your_decision?: string | null;
  /** What this person's table proposed, until the facilitator confirms it. */
  your_proposal?: string | null;
  pairs?: ClassPairView[];
  prompt_choices?: Array<{ id: string; text: string }>;
}

/** A proposed sorting of people into a class's tables. Facilitator only. */
export interface ClassSortMessage {
  type: "class_sort";
  class_id: string;
  tables: string[][];
}

/** An open swap offer. The whole table sees who offers what to whom. */
export interface OfferView {
  id: string;
  from_seat: string;
  to_seat: string;
  give: string[];
  want: string[];
}

/** An activity this room can start. */
/** One piece the room's Pieces menu adds. */
export interface PieceMenuView {
  component_id: string;
  kind: PieceKind;
  title: string;
  /** A seat colour, for a player piece; none for a die. */
  tint_index?: number | null;
}

export interface ActivityChoiceView {
  slug: string;
  title: string;
  min_players: number;
  max_players: number;
  duration_minutes: number;
  /** Choices the person makes when starting it; the first is the default. */
  options?: ActivityOptionView[];
  /** Offered only as a class: the room's toolbar does not start it alone. */
  class_only?: boolean;
  /** Listed under the room's "Debrief" heading, below the activities. */
  debrief?: boolean;
}

export interface ActivityOptionView {
  id: string;
  label: string;
  choices: { id: string; label: string }[];
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
  activities?: ActivityView[];
  offers?: OfferView[];
  /** Each pair of seats that has completed a swap. */
  swapped?: Array<[string, string]>;
}

export interface PatchView {
  kind: "piece" | "zone" | "seat" | "stroke" | "activity" | "offer" | "table";
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
  epoch?: string;
  view_table: TableView;
  seats: SeatView[];
  you: YouView;
  components: ComponentView[];
  macros: MacroView[];
  activity_choices?: ActivityChoiceView[];
  pieces_menu?: PieceMenuView[];
  classes?: ClassView[];
}

export interface PatchesMessage {
  type: "patches";
  seq: number;
  patches: PatchView[];
  /** Faces these patches newly entitle this viewer to. Absent means none. */
  components?: ComponentView[];
}

/** The intent `client_id` was accepted; its patches have already arrived. */
export interface AckMessage {
  type: "ack";
  client_id: string;
}

/** One context-menu entry, and the intent choosing it sends. */
export interface MenuItemView {
  id: string;
  label: string;
  group: string | null;
  op_type: string;
  payload: Record<string, unknown>;
}

/** What this viewer may do to one piece, as the server judged it. */
export interface MenuMessage {
  type: "menu";
  client_id: string;
  piece_id: string;
  items: MenuItemView[];
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
  | AckMessage
  | MenuMessage
  | RejectMessage
  | PresenceMessage
  | NoticeMessage
  | ClassSortMessage;

export interface HelloMessage {
  type: "hello";
  room_code: string;
  last_seq: number;
  /** Which run of the room `last_seq` belongs to; absent before a first snapshot. */
  epoch?: string;
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

/** Ask what may be done to a piece. Answered by a `MenuMessage`. */
export interface MenuRequestMessage {
  type: "menu_request";
  client_id: string;
  piece_id: string;
}

export type ClientMessage =
  | HelloMessage
  | IntentMessage
  | CursorMessage
  | HeartbeatMessage
  | MenuRequestMessage;

/** Connected, catching up, or not talking to anything. */
export type LinkStatus = "connected" | "reconnecting" | "offline" | "refused";

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
