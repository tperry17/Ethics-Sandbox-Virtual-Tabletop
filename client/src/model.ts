/**
 * The client's copy of what the server has told it, and nothing more.
 *
 * Reconciliation works from state, not from events: a patch is folded into
 * this model, which records which entities changed, and the renderer then
 * updates exactly those DOM nodes. Nothing here decides whether a change
 * was allowed - by the time a patch arrives, the server has already decided.
 *
 * Pieces and zones are stored in the same shape they arrive in, field names
 * and all. One representation means one place for a mistake to hide.
 */

import type {
  ActivityChoiceView,
  PieceMenuView,
  ActivityView,
  ClassSortMessage,
  ClassView,
  OfferView,
  ComponentView,
  CursorView,
  MacroView,
  PatchView,
  PieceKind,
  PieceView,
  SeatView,
  SnapshotMessage,
  StrokeView,
  YouView,
  ZoneView,
} from "./protocol.js";

export type LocalPiece = PieceView;
export type LocalZone = ZoneView;

/** Something that happened without changing a stored field. */
export interface TableEvent {
  type: string;
  fields: Record<string, unknown>;
}

/** A piece that arrived in a different zone, for announcing. */
export interface ZoneChange {
  id: string;
  from: string;
  to: string;
}

/** What changed, so the renderer can touch only those nodes. */
export interface Diff {
  pieces: Set<string>;
  removedPieces: Set<string>;
  zones: Set<string>;
  removedZones: Set<string>;
  strokes: boolean;
  seats: boolean;
  catalog: boolean;
  everything: boolean;
  events: TableEvent[];
  zoneChanges: ZoneChange[];
}

export function emptyDiff(): Diff {
  return {
    pieces: new Set(),
    removedPieces: new Set(),
    zones: new Set(),
    removedZones: new Set(),
    strokes: false,
    seats: false,
    catalog: false,
    everything: false,
    events: [],
    zoneChanges: [],
  };
}

export function mergeDiff(into: Diff, from: Diff): Diff {
  for (const id of from.pieces) into.pieces.add(id);
  for (const id of from.removedPieces) into.removedPieces.add(id);
  for (const id of from.zones) into.zones.add(id);
  for (const id of from.removedZones) into.removedZones.add(id);
  into.strokes = into.strokes || from.strokes;
  into.seats = into.seats || from.seats;
  into.catalog = into.catalog || from.catalog;
  into.everything = into.everything || from.everything;
  into.events.push(...from.events);
  into.zoneChanges.push(...from.zoneChanges);
  return into;
}

export class TableModel {
  pieces = new Map<string, LocalPiece>();
  zones = new Map<string, LocalZone>();
  seats = new Map<string, SeatView>();
  strokes = new Map<string, StrokeView>();
  components = new Map<string, ComponentView>();
  /**
   * The order the server listed the zones in.
   *
   * A piece's `z` orders it within its own zone and says nothing about a
   * piece in another zone, so two pieces can hold the same `z` and overlap.
   * Composing the zone's position in the server's own list with that `z`
   * gives one order for the whole table, decided by the model rather than
   * by which element happens to have been created first.
   */
  zoneOrder = new Map<string, number>();
  macros: MacroView[] = [];
  activities = new Map<string, ActivityView>();
  activityChoices: ActivityChoiceView[] = [];
  piecesMenu: PieceMenuView[] = [];
  classes: ClassView[] = [];
  /** When each class's timer runs out, on this browser's clock, in ms. */
  classTimerEnds = new Map<string, number>();
  /** The facilitator's proposed sorting, until it is confirmed or dropped. */
  classSort: ClassSortMessage | null = null;
  offers = new Map<string, OfferView>();
  /** Pairs of seats that have swapped, each as its two seat ids joined by `|`, sorted. */
  swapped = new Set<string>();
  cursors: CursorView[] = [];
  you: YouView | null = null;
  version = 0;
  seq = 0;

  /** The seat this browser is sitting in, or null for an observer. */
  get seatId(): string | null {
    return this.you?.seat_id ?? null;
  }

  /** One stacking order for the whole table: zone first, then `z` within it. */
  stackingOrder(zoneId: string, z: number): number {
    const zone = this.zoneOrder.get(zoneId) ?? this.zoneOrder.size;
    return zone * 10_000 + Math.min(Math.max(Math.round(z), 0), 9_999);
  }

  /** Replace everything. Used on first connection and on a forced resync. */
  applySnapshot(message: SnapshotMessage): Diff {
    const diff = emptyDiff();
    diff.everything = true;
    diff.strokes = true;
    diff.seats = true;
    diff.catalog = true;

    this.pieces = new Map(
      message.view_table.pieces.map((piece) => [piece.id, { ...piece }]),
    );
    this.zones = new Map(
      message.view_table.zones.map((zone) => [zone.id, { ...zone }]),
    );
    this.zoneOrder = new Map(
      message.view_table.zones.map((zone, index) => [zone.id, index]),
    );
    this.seats = new Map(message.seats.map((seat) => [seat.id, { ...seat }]));
    this.strokes = new Map(
      message.view_table.strokes.map((stroke) => [stroke.id, { ...stroke }]),
    );
    this.components = new Map(
      message.components.map((component) => [component.id, { ...component }]),
    );
    this.macros = message.macros.map((macro) => ({ ...macro }));
    this.activities = new Map(
      (message.view_table.activities ?? []).map((activity) => [activity.id, { ...activity }]),
    );
    this.offers = new Map(
      (message.view_table.offers ?? []).map((offer) => [offer.id, { ...offer }]),
    );
    this.swapped = new Set(
      (message.view_table.swapped ?? []).map((pair) => [...pair].sort().join("|")),
    );
    this.activityChoices = (message.activity_choices ?? []).map((choice) => ({ ...choice }));
    this.piecesMenu = (message.pieces_menu ?? []).map((entry) => ({ ...entry }));
    this.classes = (message.classes ?? []).map((group) => ({ ...group }));
    this.classTimerEnds = new Map(
      this.classes
        .filter((group) => group.timer_remaining !== null)
        .map((group) => [group.id, performance.now() + (group.timer_remaining ?? 0) * 1000]),
    );
    if (this.classSort !== null && !this.classes.some((g) => g.id === this.classSort?.class_id)) {
      this.classSort = null;
    }
    this.you = { ...message.you };
    this.version = message.view_table.version;
    this.seq = message.seq;
    return diff;
  }

  applyPatches(
    patches: PatchView[],
    seq: number,
    components: ComponentView[] = [],
  ): Diff {
    const diff = emptyDiff();
    // Faces first, so the pieces that name them can be drawn this frame.
    for (const component of components) {
      this.components.set(component.id, { ...component });
    }
    for (const patch of patches) {
      this.applyPatch(patch, diff);
    }
    this.seq = seq;
    return diff;
  }

  applyPresence(seats: SeatView[], cursors: CursorView[]): Diff {
    const diff = emptyDiff();
    this.seats = new Map(seats.map((seat) => [seat.id, { ...seat }]));
    this.cursors = cursors.map((cursor) => ({ ...cursor }));
    diff.seats = true;
    return diff;
  }

  private applyPatch(patch: PatchView, diff: Diff): void {
    if (patch.kind === "table" && patch.op === "event") {
      const type = patch.fields["type"];
      diff.events.push({
        type: typeof type === "string" ? type : "unknown",
        fields: patch.fields,
      });
      return;
    }
    if (patch.entity_id === null) return;

    if (patch.kind === "piece") {
      this.applyPiecePatch(patch.entity_id, patch, diff);
      return;
    }
    if (patch.kind === "zone") {
      this.applyZonePatch(patch.entity_id, patch, diff);
      return;
    }
    if (patch.kind === "stroke") {
      this.applyStrokePatch(patch.entity_id, patch, diff);
      return;
    }
    if (patch.kind === "seat") {
      this.applySeatPatch(patch.entity_id, patch, diff);
      return;
    }
    if (patch.kind === "offer") {
      if (patch.op === "remove") {
        this.offers.delete(patch.entity_id);
        const pair = patch.fields["swapped"];
        if (Array.isArray(pair)) this.swapped.add(pair.map(String).sort().join("|"));
      } else {
        this.offers.set(patch.entity_id, {
          ...(patch.fields as Partial<OfferView>),
          id: patch.entity_id,
        } as OfferView);
      }
      diff.catalog = true;
      return;
    }
    if (patch.kind === "activity") {
      if (patch.op === "remove") this.activities.delete(patch.entity_id);
      else {
        const existing = this.activities.get(patch.entity_id);
        this.activities.set(patch.entity_id, {
          ...(existing ?? ({ id: patch.entity_id } as ActivityView)),
          ...(patch.fields as Partial<ActivityView>),
        });
      }
      diff.catalog = true;
    }
  }

  private applyPiecePatch(id: string, patch: PatchView, diff: Diff): void {
    if (patch.op === "remove") {
      this.pieces.delete(id);
      diff.removedPieces.add(id);
      return;
    }
    const existing = this.pieces.get(id);
    const fields = patch.fields;
    const piece: LocalPiece = existing
      ? { ...existing }
      : {
          id,
          kind: (readString(fields, "kind") ?? "token") as PieceKind,
          zone_id: readString(fields, "zone_id") ?? "",
          x: 0,
          y: 0,
          z: 0,
          rotation: 0,
          face_up: false,
          held_by: null,
          locked: false,
          component_id: null,
          revealed_to: [],
          revealed_by: null,
          value: null,
          text: null,
        };

    if ("kind" in fields) piece.kind = (readString(fields, "kind") ??
      piece.kind) as PieceKind;
    if ("zone_id" in fields) piece.zone_id = readString(fields, "zone_id") ?? piece.zone_id;
    if ("x" in fields) piece.x = readNumber(fields, "x") ?? piece.x;
    if ("y" in fields) piece.y = readNumber(fields, "y") ?? piece.y;
    if ("z" in fields) piece.z = readNumber(fields, "z") ?? piece.z;
    if ("rotation" in fields) piece.rotation = readNumber(fields, "rotation") ?? piece.rotation;
    if ("face_up" in fields) piece.face_up = fields["face_up"] === true;
    if ("held_by" in fields) piece.held_by = readString(fields, "held_by");
    if ("locked" in fields) piece.locked = fields["locked"] === true;
    // A projected patch sets `component_id` to null for a viewer who may not
    // see the face. That null is the truth for this viewer and overwrites
    // whatever face they were shown before - a card put back face-down stops
    // being readable the moment the server says so.
    if ("component_id" in fields) piece.component_id = readString(fields, "component_id");
    if ("revealed_to" in fields) piece.revealed_to = readStrings(fields["revealed_to"]);
    if ("revealed_by" in fields) piece.revealed_by = readString(fields, "revealed_by");
    if ("value" in fields) piece.value = readString(fields, "value");
    if ("text" in fields) piece.text = readString(fields, "text");

    if (existing !== undefined && existing.zone_id !== piece.zone_id) {
      diff.zoneChanges.push({ id, from: existing.zone_id, to: piece.zone_id });
    }
    this.pieces.set(id, piece);
    diff.pieces.add(id);
  }

  private applyZonePatch(id: string, patch: PatchView, diff: Diff): void {
    if (patch.op === "remove") {
      this.zones.delete(id);
      diff.removedZones.add(id);
      return;
    }
    const existing = this.zones.get(id);
    if (existing === undefined) {
      // A zone the client has never seen cannot be assembled from a partial
      // patch. Ask for the whole table instead of guessing an outline.
      diff.everything = true;
      return;
    }
    const zone: LocalZone = { ...existing, ...(patch.fields as Partial<LocalZone>) };
    this.zones.set(id, zone);
    if (!this.zoneOrder.has(id)) this.zoneOrder.set(id, this.zoneOrder.size);
    diff.zones.add(id);
  }

  private applyStrokePatch(id: string, patch: PatchView, diff: Diff): void {
    diff.strokes = true;
    if (patch.op === "remove") {
      this.strokes.delete(id);
      return;
    }
    const existing = this.strokes.get(id);
    const fields = patch.fields;
    const stroke: StrokeView = existing
      ? { ...existing }
      : { id, seat_id: "", colour: "", width: 1, points: [] };
    if ("seat_id" in fields) stroke.seat_id = readString(fields, "seat_id") ?? stroke.seat_id;
    if ("colour" in fields) stroke.colour = readString(fields, "colour") ?? stroke.colour;
    if ("width" in fields) stroke.width = readNumber(fields, "width") ?? stroke.width;
    if ("points" in fields) stroke.points = readPoints(fields["points"]) ?? stroke.points;
    this.strokes.set(id, stroke);
  }

  private applySeatPatch(id: string, patch: PatchView, diff: Diff): void {
    diff.seats = true;
    if (patch.op === "remove") {
      this.seats.delete(id);
      return;
    }
    const existing = this.seats.get(id);
    if (existing === undefined) {
      diff.everything = true;
      return;
    }
    this.seats.set(id, { ...existing, ...(patch.fields as Partial<SeatView>) });
  }
}

function readString(fields: Record<string, unknown>, key: string): string | null {
  const value = fields[key];
  return typeof value === "string" ? value : null;
}

function readStrings(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === "string");
}

function readNumber(fields: Record<string, unknown>, key: string): number | null {
  const value = fields[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readPoints(value: unknown): Array<[number, number]> | null {
  if (!Array.isArray(value)) return null;
  const points: Array<[number, number]> = [];
  for (const entry of value) {
    if (!Array.isArray(entry) || entry.length < 2) continue;
    const [x, y] = entry;
    if (typeof x !== "number" || typeof y !== "number") continue;
    points.push([x, y]);
  }
  return points;
}
