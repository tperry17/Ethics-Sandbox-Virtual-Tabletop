/**
 * The table, rendered.
 *
 * Everything here reconciles from state. A message updates the model and
 * records what changed; one animation frame later, exactly the DOM nodes
 * that changed are rewritten. The table is never rebuilt, and no node is
 * touched because a message arrived - only because a value on it differs.
 *
 * This file renders and moves the camera; `interaction.ts` turns what a
 * person does into intents. Neither knows a rule or holds a deck: a face
 * this client was not sent is a face it cannot draw, and the only local
 * result of a gesture is an override laid over the server's truth until the
 * server says yes - or no, at which point the override is taken away and
 * the piece is seen to go back.
 */

import { Announcer } from "./announcer.js";
import { InkLayer } from "./ink.js";
import { IntentTracker } from "./intents.js";
import { ContextMenu } from "./menu.js";
import { type Diff, type LocalPiece, TableModel, emptyDiff, mergeDiff } from "./model.js";
import { PieceNode, initialsFor, pieceSize, seatTintClass } from "./piece-node.js";
import { geometryBounds, polygonClipPath } from "./geometry.js";
import type {
  ClientMessage,
  LinkStatus,
  MacroView,
  MenuItemView,
  SeatView,
  ServerLink,
  ServerMessage,
  StrokeView,
} from "./protocol.js";
import { RevealLayer } from "./reveal.js";
import { ViewportController } from "./viewport-input.js";
import { type Bounds, type Viewport, screenToWorld, unionBounds } from "./viewport.js";

/** Where a card's centre sits in the tray, so its top edge starts at the top. */
const TRAY_BASELINE = 160;
const MAX_NOTICES = 3;
const NOTICE_MS = 6000;
/** How long a piece that was sent back stays marked as having been sent back. */
const ROLLBACK_MARK_MS = 700;
/** More zone changes than this in one go are summarised, not listed. */
const ANNOUNCE_EACH_UP_TO = 3;

/**
 * A local, not-yet-confirmed result laid over what the server last said.
 *
 * `x`/`y`/`rotation` pin where a piece is drawn (its own hand is on it);
 * `hideFace` draws the back of a card just turned face down; `lifted` draws
 * it picked up. Any field left out falls through to the server's truth.
 */
export interface Override {
  x?: number;
  y?: number;
  rotation?: number;
  hideFace?: boolean;
  lifted?: boolean;
}
export interface RendererOptions {
  root: HTMLElement;
  toolbar: HTMLElement | null;
  link: ServerLink;
  roomCode: string;
}

/** Things the interaction half wants to hear about as they arrive. */
export interface RendererListener {
  /** This viewer's own close look at a piece, confirmed by the server. */
  onOwnPeek?: (pieceId: string) => void;
  /** The whole table was replaced; any gesture in progress is moot. */
  onSnapshot?: () => void;
}

export class TableRenderer {
  readonly model = new TableModel();
  readonly intents: IntentTracker;
  readonly menu: ContextMenu;
  readonly reveals: RevealLayer;
  readonly announcer = new Announcer();
  listener: RendererListener = {};
  /** True while a gesture is in progress, so the camera does not refit under it. */
  interacting = false;

  private readonly surface: HTMLElement;
  private readonly world: HTMLElement;
  private readonly zoneLayer: HTMLElement;
  private readonly pieceLayer: HTMLElement;
  private readonly canvas: HTMLCanvasElement;
  private readonly tray: HTMLElement;
  private readonly trayFan: HTMLElement;
  private readonly trayLabel: HTMLElement;
  private readonly status: HTMLElement;
  private readonly notices: HTMLElement;
  private readonly controller: ViewportController;
  private readonly ink: InkLayer;

  private readonly pieceNodes = new Map<string, PieceNode>();
  private readonly pieceHome = new Map<string, "world" | "tray">();
  private readonly zoneNodes = new Map<string, HTMLElement>();
  private readonly animating = new Set<string>();
  private readonly overrides = new Map<string, Override>();
  private readonly rollingBack = new Set<string>();
  private selection = new Set<string>();
  private stackTarget: string | null = null;
  private draftStroke: StrokeView | null = null;
  private trayInvited = false;
  private readonly controlsElement: HTMLElement;
  private readonly toolGroup = element("div", "toolbar__group toolbar__group--tools");
  private lastNotice = { text: "", at: 0 };

  private diff: Diff = emptyDiff();
  private frameRequested = false;
  private canvasDirty = true;
  private trayDirty = true;
  private viewport: Viewport;
  private dropTargetZone: string | null = null;
  private reduceMotion = false;
  private resizeObserver: ResizeObserver | null = null;

  constructor(private readonly options: RendererOptions) {
    const root = options.root;
    root.classList.add("tabletop", "tabletop--live");
    root.replaceChildren();

    this.surface = element("div", "tabletop__viewport");
    this.world = element("div", "tabletop__world");
    this.zoneLayer = element("div", "tabletop__zones");
    this.pieceLayer = element("div", "tabletop__pieces-layer");
    this.canvas = document.createElement("canvas");
    this.canvas.className = "tabletop__ink";
    this.status = element("p", "tabletop__status");
    this.notices = element("div", "tabletop__notices");
    this.notices.setAttribute("role", "status");
    this.notices.setAttribute("aria-live", "polite");

    this.world.append(this.zoneLayer, this.pieceLayer);
    this.controlsElement = this.controls();
    this.surface.append(this.world, this.canvas, this.controlsElement, this.status);
    this.surface.append(this.notices);

    this.tray = element("div", "hand-tray");
    this.tray.hidden = true;
    this.trayLabel = element("p", "hand-tray__label");
    this.trayFan = element("div", "hand-tray__fan");
    this.tray.append(this.trayLabel, this.trayFan);

    this.intents = new IntentTracker(options.link, (reason) =>
      this.notice(reason, "warning"),
    );
    this.reveals = new RevealLayer({
      putAway: (pieceId) => {
        this.intents.send("end_show", { piece_id: pieceId });
      },
      nameOf: (seatId) => this.nameOf(seatId),
    });
    this.surface.append(this.reveals.element, this.reveals.peek);

    root.append(this.surface, this.tray, this.announcer.element);
    this.menu = new ContextMenu(root, options.link, (item, pieceId) =>
      this.chooseMenuItem(item, pieceId),
    );

    this.ink = new InkLayer(this.canvas);
    this.controller = new ViewportController({
      surface: this.surface,
      onChange: (viewport) => {
        this.viewport = viewport;
        this.canvasDirty = true;
        this.writeWorldTransform();
        this.schedule();
      },
      bounds: () => this.tableBounds(),
      size: () => this.surfaceSize(),
    });
    this.viewport = this.controller.current;

    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    this.reduceMotion = motion?.matches ?? false;
    motion?.addEventListener?.("change", (event) => {
      this.reduceMotion = event.matches;
    });

    this.setStatus("reconnecting");
  }

  start(): void {
    this.controller.attach();
    this.observeSize();
    this.options.link.onMessage((message) => this.receive(message));
    this.options.link.onStatus((status) => this.setStatus(status));
    this.options.link.start();
    this.renderToolbar();
  }

  stop(): void {
    this.controller.detach();
    this.resizeObserver?.disconnect();
    this.options.link.stop();
  }

  /** Light a zone up as somewhere a held piece could be let go. */
  setDropTarget(zoneId: string | null): void {
    if (zoneId === this.dropTargetZone) return;
    const previous =
      this.dropTargetZone === null ? null : this.zoneNodes.get(this.dropTargetZone);
    previous?.classList.remove("is-drop-target");
    this.dropTargetZone = zoneId;
    if (zoneId === null) return;
    this.zoneNodes.get(zoneId)?.classList.add("is-drop-target");
  }

  /** Where a piece is being drawn this instant, mid-flight included. */
  visualPositionOf(pieceId: string): [number, number] | null {
    const node = this.pieceNodes.get(pieceId);
    if (node === undefined) return null;
    const visual = node.visual;
    return [visual.x, visual.y];
  }

  get currentViewport(): Viewport {
    return this.viewport;
  }

  fitTable(): void {
    this.controller.fit(true);
  }

  // -- incoming ---------------------------------------------------------------

  private receive(message: ServerMessage): void {
    if (message.type === "snapshot") {
      this.absorb(this.model.applySnapshot(message));
      this.listener.onSnapshot?.();
      return;
    }
    if (message.type === "patches") {
      this.absorb(
        this.model.applyPatches(message.patches, message.seq, message.components ?? []),
      );
      return;
    }
    if (message.type === "ack") {
      this.intents.ack(message.client_id);
      return;
    }
    if (message.type === "menu") {
      this.menu.receive(message);
      return;
    }
    if (message.type === "presence") {
      this.absorb(this.model.applyPresence(message.seats, message.cursors));
      this.canvasDirty = true;
      return;
    }
    if (message.type === "notice") {
      this.notice(message.text, message.level);
      return;
    }
    // A rejection is answered twice: the gesture that proposed it is taken
    // back, and the person is told why in the server's own words.
    this.intents.reject(message.client_id, message.reason);
    this.notice(message.reason, "warning");
  }

  private absorb(diff: Diff): void {
    mergeDiff(this.diff, diff);
    this.schedule();
  }

  private schedule(): void {
    if (this.frameRequested) return;
    this.frameRequested = true;
    requestAnimationFrame((now) => this.frame(now));
  }

  // -- the one reconcile pass --------------------------------------------------

  private frame(now: number): void {
    this.frameRequested = false;
    const diff = this.diff;
    this.diff = emptyDiff();

    if (diff.everything) {
      this.syncAllZones();
      this.syncAllPieces(now);
      this.canvasDirty = true;
      this.trayDirty = true;
      this.renderToolbar();
      if (!this.controller.adjustedByPerson && !this.interacting) this.controller.fit();
    } else {
      for (const id of diff.removedZones) this.dropZone(id);
      for (const id of diff.zones) this.syncZone(id);
      for (const id of diff.removedPieces) this.dropPiece(id);
      for (const id of diff.pieces) this.syncPiece(id, now);
      if (diff.catalog) this.renderToolbar();
    }

    if (diff.seats) {
      this.canvasDirty = true;
      for (const id of this.pieceNodes.keys()) this.syncHolder(id);
    }
    if (diff.strokes) this.canvasDirty = true;

    for (const event of diff.events) {
      if (event.type === "point") {
        const x = event.fields["x"];
        const y = event.fields["y"];
        const seat = event.fields["seat_id"];
        if (typeof x === "number" && typeof y === "number" && typeof seat === "string") {
          this.ink.ping(x, y, seat, now);
          this.canvasDirty = true;
        }
        continue;
      }
      this.announceEvent(event.type, event.fields);
    }
    this.announceZoneChanges(diff);
    if (diff.everything || diff.pieces.size > 0 || diff.removedPieces.size > 0 || diff.seats) {
      this.reveals.sync(this.model);
    }

    if (this.trayDirty) {
      this.trayDirty = false;
      const wasShowing = !this.tray.hidden;
      this.layoutTray();
      if (
        wasShowing !== !this.tray.hidden &&
        !this.controller.adjustedByPerson &&
        !this.interacting
      ) {
        this.controller.fit();
      }
    }

    let animating = false;
    for (const id of [...this.animating]) {
      const node = this.pieceNodes.get(id);
      if (node === undefined) {
        this.animating.delete(id);
        continue;
      }
      if (node.advance(now)) animating = true;
      else this.animating.delete(id);
    }

    let pinging = false;
    if (this.canvasDirty || animating) {
      this.canvasDirty = false;
      const strokes: StrokeView[] = [...this.model.strokes.values()];
      if (this.draftStroke !== null && !this.model.strokes.has(this.draftStroke.id)) {
        strokes.push(this.draftStroke);
      }
      // Your own pointer is already on screen; its echo from the server
      // would only trail behind it.
      const cursors = this.model.cursors.filter(
        (cursor) => cursor.seat_id !== this.model.seatId,
      );
      pinging = this.ink.draw(
        this.viewport,
        strokes,
        cursors,
        this.model.seats,
        now,
      );
    }
    if (animating || pinging) this.schedule();
  }

  // -- zones --------------------------------------------------------------------

  private syncAllZones(): void {
    for (const id of [...this.zoneNodes.keys()]) {
      if (!this.model.zones.has(id)) this.dropZone(id);
    }
    for (const id of this.model.zones.keys()) this.syncZone(id);
  }

  private dropZone(id: string): void {
    this.zoneNodes.get(id)?.remove();
    this.zoneNodes.delete(id);
  }

  private syncZone(id: string): void {
    const zone = this.model.zones.get(id);
    if (zone === undefined) return this.dropZone(id);

    let node = this.zoneNodes.get(id);
    if (node === undefined) {
      node = element("div", "zone");
      node.dataset.zoneId = id;
      node.append(element("span", "zone__label"));
      this.zoneLayer.append(node);
      this.zoneNodes.set(id, node);
    }

    const bounds = geometryBounds(zone.geometry);
    const width = Math.max(bounds.maxX - bounds.minX, 1);
    const height = Math.max(bounds.maxY - bounds.minY, 1);
    const transform = `translate3d(${bounds.minX}px, ${bounds.minY}px, 0)`;
    if (node.style.transform !== transform) node.style.transform = transform;
    if (node.style.width !== `${width}px`) node.style.width = `${width}px`;
    if (node.style.height !== `${height}px`) node.style.height = `${height}px`;
    if (zone.geometry.shape === "polygon") {
      const clip = polygonClipPath(zone.geometry.points);
      if (clip !== null && node.style.clipPath !== clip) node.style.clipPath = clip;
    }

    const mine = zone.owner_seat !== null && zone.owner_seat === this.model.seatId;
    const classes = ["zone", `zone--${zone.kind}`];
    if (zone.visibility === "private_to_owner") {
      classes.push(mine ? "zone--private" : "zone--sealed");
    }
    if (zone.visibility === "hidden") classes.push("zone--hidden");
    if (zone.visibility === "facilitator_only") classes.push("zone--facilitator");
    if (mine) classes.push("is-mine");
    if (id === this.dropTargetZone) classes.push("is-drop-target");
    const className = classes.join(" ");
    if (node.className !== className) node.className = className;

    const label = node.firstElementChild;
    const text = this.zoneLabel(zone.label, zone.owner_seat);
    if (label instanceof HTMLElement && label.textContent !== text) {
      label.textContent = text;
    }
  }

  private zoneLabel(label: string, ownerSeat: string | null): string {
    if (ownerSeat === null) return label;
    const seat = this.model.seats.get(ownerSeat);
    const name = seat?.display_name ?? seat?.label ?? null;
    if (name === null) return label;
    return ownerSeat === this.model.seatId ? `${label} · you` : `${label} · ${name}`;
  }

  // -- pieces ---------------------------------------------------------------------

  private syncAllPieces(now: number): void {
    for (const id of [...this.pieceNodes.keys()]) {
      if (!this.model.pieces.has(id)) this.dropPiece(id);
    }
    for (const id of this.model.pieces.keys()) this.syncPiece(id, now);
  }

  private dropPiece(id: string): void {
    const node = this.pieceNodes.get(id);
    if (node === undefined) return;
    if (this.pieceHome.get(id) === "tray") this.trayDirty = true;
    node.remove();
    this.pieceNodes.delete(id);
    this.pieceHome.delete(id);
    this.animating.delete(id);
  }

  private syncPiece(id: string, now: number): void {
    const piece = this.model.pieces.get(id);
    if (piece === undefined) return this.dropPiece(id);

    let node = this.pieceNodes.get(id);
    const fresh = node === undefined;
    if (node === undefined) {
      node = new PieceNode(id, piece);
      this.pieceNodes.set(id, node);
    }

    const override = this.overrides.get(id);
    const pinned = override?.x !== undefined && override.y !== undefined;
    const home = pinned || !this.isInMyHand(piece.zone_id) ? "world" : "tray";
    if (this.pieceHome.get(id) !== home) {
      const hadFocus = document.activeElement === node.element;
      const leavingTray = this.pieceHome.get(id) === "tray";
      this.pieceHome.set(id, home);
      (home === "tray" ? this.trayFan : this.pieceLayer).append(node.element);
      if (hadFocus) node.element.focus({ preventScroll: true });
      this.trayDirty = true;
      this.animating.delete(id);
      // A card leaving the tray starts from where it was let go, not from
      // its old spot in the fan, which is in another coordinate space.
      if (leavingTray && !pinned) node.placeAt(piece.x, piece.y, piece.rotation);
    }

    const shown = this.shownPiece(piece);
    const component =
      shown.component_id === null
        ? undefined
        : this.model.components.get(shown.component_id);
    const [width, height] = pieceSize(shown, component);
    node.setSize(width, height);
    node.setZ(this.model.stackingOrder(piece.zone_id, piece.z));
    node.setFace(shown, component, this.model.zones.get(piece.zone_id)?.label ?? "");
    this.syncHolder(id);

    if (home === "tray") {
      this.trayDirty = true;
      return;
    }

    if (pinned) {
      // The piece under this person's own hand goes exactly where the hand
      // is, and stays above everything while it is held.
      node.placeAt(override!.x!, override!.y!, override!.rotation ?? piece.rotation);
      node.setZ(10_000_000);
      this.animating.delete(id);
      return;
    }

    // Everyone else's pieces glide, so that a table in motion reads as
    // hands moving things rather than things teleporting. A piece that was
    // sent back glides too, so that the going back is seen.
    const target =
      override?.rotation === undefined ? piece : { ...piece, rotation: override.rotation };
    const mine = piece.held_by !== null && piece.held_by === this.model.seatId;
    const rollback = this.rollingBack.has(id);
    const animate = !fresh && (!mine || rollback) && !this.reduceMotion;
    node.setTarget(target, animate, now);
    if (animate) this.animating.add(id);
    else node.advance(now);
  }

  /** The piece as this viewer should see it now: the server's truth, plus overrides. */
  private shownPiece(piece: LocalPiece): LocalPiece {
    const override = this.overrides.get(piece.id);
    if (override === undefined) return piece;
    const shown = { ...piece };
    if (override.hideFace === true) {
      shown.component_id = null;
      shown.face_up = false;
    }
    if (override.lifted === true) shown.held_by = this.model.seatId;
    return shown;
  }

  private syncHolder(id: string): void {
    const node = this.pieceNodes.get(id);
    const truth = this.model.pieces.get(id);
    if (node === undefined || truth === undefined) return;
    const piece = this.shownPiece(truth);
    const holder =
      piece.held_by === null ? undefined : this.model.seats.get(piece.held_by);
    const extra: string[] = [];
    if (this.pieceHome.get(id) === "tray") extra.push("piece--in-tray");
    if (this.selection.has(id)) extra.push("is-selected");
    if (this.stackTarget === id) extra.push("is-stack-target");
    if (this.rollingBack.has(id)) extra.push("is-rolling-back");
    if (this.overrides.get(id)?.lifted === true) extra.push("is-dragging");
    if (truth.revealed_by !== null && truth.revealed_to.length > 0) extra.push("is-shown");
    node.setClasses(piece, holder, extra.join(" "));
    node.setHolder(holder);
    const name = this.pieceLabel(id);
    const held =
      holder === undefined ? "" : `, held by ${holder.display_name ?? holder.label}`;
    const label = `${name}${held}`;
    if (node.element.getAttribute("aria-label") !== label) {
      node.element.setAttribute("aria-label", label);
    }
  }

  private isInMyHand(zoneId: string): boolean {
    const zone = this.model.zones.get(zoneId);
    if (zone === undefined) return false;
    return zone.kind === "hand" && zone.owner_seat === this.model.seatId;
  }

  // -- the hand tray ------------------------------------------------------------

  /**
   * Lay this viewer's own private zone out as a fan along the bottom edge.
   *
   * The tray sits outside the world transform: your own hand stays the same
   * size and in the same place however far the table is zoomed or panned,
   * because it is yours and you are always holding it.
   */
  private layoutTray(): void {
    const ids = [...this.model.pieces.values()]
      .filter((piece) => this.isInMyHand(piece.zone_id))
      .sort((a, b) => a.z - b.z)
      .map((piece) => piece.id);

    this.tray.hidden = ids.length === 0 && !this.trayInvited;
    if (ids.length === 0) {
      this.trayLabel.textContent = this.trayInvited ? "Drop here to take it into your hand" : "";
      return;
    }

    const zone = [...this.model.zones.values()].find(
      (candidate) =>
        candidate.kind === "hand" && candidate.owner_seat === this.model.seatId,
    );
    const noun = ids.length === 1 ? "piece" : "pieces";
    this.trayLabel.textContent = `${zone?.label ?? "Your hand"} · ${ids.length} ${noun}`;

    const widest = Math.max(
      ...ids.map((id) => {
        const piece = this.model.pieces.get(id)!;
        const component =
          piece.component_id === null
            ? undefined
            : this.model.components.get(piece.component_id);
        return pieceSize(piece, component)[0];
      }),
    );
    const available = this.trayFan.clientWidth || widest * 3;
    const step =
      ids.length === 1
        ? 0
        : Math.min(widest * 0.78, (available - widest) / (ids.length - 1));
    const spread = Math.min(14, ids.length * 2);
    const totalWidth = step * (ids.length - 1);
    const baseX = available / 2 - totalWidth / 2;

    ids.forEach((id, index) => {
      const node = this.pieceNodes.get(id);
      if (node === undefined) return;
      const middle = (ids.length - 1) / 2;
      const offset = ids.length === 1 ? 0 : (index - middle) / Math.max(middle, 1);
      const rotation = offset * spread;
      const lift = Math.abs(offset) * 14;
      node.setZ(index);
      node.placeAt(baseX + step * index, TRAY_BASELINE + lift, rotation);
    });
  }

  // -- chrome ----------------------------------------------------------------------

  private controls(): HTMLElement {
    const controls = element("div", "tabletop__controls");
    controls.append(
      button("Fit table", () => this.controller.fit(true)),
      button("Zoom out", () => this.controller.zoomBy(1 / 1.2), "−"),
      button("Zoom in", () => this.controller.zoomBy(1.2), "+"),
    );
    return controls;
  }

  /**
   * Where the interaction half puts its own tools: the page toolbar, beside
   * the exercise's macros, so nothing sits on the felt covering pieces. A
   * page with no toolbar gets them among the camera controls instead.
   */
  get toolArea(): HTMLElement {
    if (this.options.toolbar === null) return this.controlsElement;
    return this.toolGroup;
  }

  private renderToolbar(): void {
    const toolbar = this.options.toolbar;
    if (toolbar === null) return;
    toolbar.replaceChildren();
    if (this.model.macros.length === 0) {
      const empty = element("p", "toolbar__empty prose");
      empty.textContent =
        "Macro buttons for this exercise appear here once it defines them.";
      toolbar.append(empty);
    }
    for (const macro of this.model.macros) {
      toolbar.append(this.macroButton(macro));
    }
    toolbar.append(this.toolGroup);
  }

  private macroButton(macro: MacroView): HTMLElement {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "button button--sm";
    node.dataset.macroId = macro.id;
    node.textContent = macro.label;
    if (macro.hint !== null) node.title = macro.hint;
    node.addEventListener("click", () => this.pressMacro(macro));
    return node;
  }

  /**
   * Ask the server to run a toolbar button. What it does, and whether it
   * may, is the server's to decide; the client only asks the question the
   * server supplied before a destructive one, and reports the answer.
   */
  pressMacro(macro: MacroView): void {
    if (macro.confirm !== null && !window.confirm(macro.confirm)) return;
    this.intents.send("macro", { macro_id: macro.id });
  }

  private setStatus(status: LinkStatus): void {
    this.status.dataset.status = status;
    this.status.textContent =
      status === "connected"
        ? "Connected"
        : status === "reconnecting"
          ? "Reconnecting…"
          : "Offline";
  }

  notice(text: string, level: "info" | "warning"): void {
    // One refused gesture can draw the same refusal for several pieces at
    // once; saying it once is enough.
    const now = performance.now();
    if (text === this.lastNotice.text && now - this.lastNotice.at < 1500) return;
    this.lastNotice = { text, at: now };
    const toast = element("aside", "toast toast--compact");
    toast.dataset.level = level;
    const message = element("p", "toast__message");
    message.textContent = text;
    toast.append(message);
    this.notices.append(toast);
    while (this.notices.childElementCount > MAX_NOTICES) {
      this.notices.firstElementChild?.remove();
    }
    window.setTimeout(() => toast.remove(), NOTICE_MS);
  }

  // -- what the interaction half may ask for -------------------------------------------

  /** Send something to the server that is not an intent - a cursor position. */
  send(message: ClientMessage): void {
    this.options.link.send(message);
  }

  get surfaceElement(): HTMLElement {
    return this.surface;
  }

  get trayElement(): HTMLElement {
    return this.tray;
  }

  get selected(): ReadonlySet<string> {
    return this.selection;
  }

  overrideOf(id: string): Override | undefined {
    return this.overrides.get(id);
  }

  /** Draw `id` per `override` until told otherwise. Merges with any already set. */
  setOverride(id: string, override: Override): void {
    this.overrides.set(id, { ...this.overrides.get(id), ...override });
    this.touch(id);
  }

  /**
   * Stop overriding `id` and draw it where the server says it is.
   *
   * With `rollback`, the server refused what the override showed: the piece
   * is seen to travel back, and is marked for a moment as having been sent
   * back, so a refusal is never a silent snap.
   */
  clearOverride(id: string, rollback: boolean): void {
    if (!this.overrides.delete(id) && !rollback) return;
    if (rollback && this.model.pieces.has(id)) {
      this.rollingBack.add(id);
      window.setTimeout(() => {
        this.rollingBack.delete(id);
        this.touch(id);
      }, ROLLBACK_MARK_MS);
    }
    this.touch(id);
  }

  setSelection(ids: Iterable<string>): void {
    const next = new Set([...ids].filter((id) => this.model.pieces.has(id)));
    const changed = [...this.selection, ...next].filter(
      (id) => this.selection.has(id) !== next.has(id),
    );
    this.selection = next;
    for (const id of changed) this.syncHolder(id);
  }

  setStackTarget(id: string | null): void {
    if (id === this.stackTarget) return;
    const previous = this.stackTarget;
    this.stackTarget = id;
    if (previous !== null) this.syncHolder(previous);
    if (id !== null) this.syncHolder(id);
  }

  /** Light the hand tray up as somewhere a held piece could be let go. */
  setTrayTarget(on: boolean): void {
    this.tray.classList.toggle("is-drop-target", on);
  }

  /** Show the tray even when the hand is empty, so there is somewhere to drop. */
  inviteTray(on: boolean): void {
    if (on === this.trayInvited) return;
    this.trayInvited = on && this.myHandZoneId() !== null;
    this.trayDirty = true;
    this.schedule();
  }

  setDraftStroke(stroke: StrokeView | null): void {
    this.draftStroke = stroke === null ? null : { ...stroke, points: [...stroke.points] };
    this.canvasDirty = true;
    this.schedule();
  }

  /** The piece drawn at a screen point, or null. Pieces being dragged are see-through. */
  pieceIdAt(clientX: number, clientY: number): string | null {
    const hit = document.elementFromPoint(clientX, clientY);
    if (!(hit instanceof Element)) return null;
    const node = hit.closest<HTMLElement>("[data-piece-id]");
    if (node === null || !this.root.contains(node)) return null;
    return node.dataset.pieceId ?? null;
  }

  isInTray(id: string): boolean {
    return this.pieceHome.get(id) === "tray";
  }

  overTray(clientX: number, clientY: number): boolean {
    if (this.tray.hidden) return false;
    const box = this.tray.getBoundingClientRect();
    return (
      clientX >= box.left && clientX <= box.right && clientY >= box.top && clientY <= box.bottom
    );
  }

  /** The topmost zone whose outline contains a world point, or null. */
  zoneAtWorld(x: number, y: number): string | null {
    const zones = [...this.model.zones.values()].sort(
      (a, b) => (this.model.zoneOrder.get(b.id) ?? 0) - (this.model.zoneOrder.get(a.id) ?? 0),
    );
    for (const zone of zones) {
      if (zone.geometry.shape === "rect") {
        const g = zone.geometry;
        if (x >= g.x && x <= g.x + g.width && y >= g.y && y <= g.y + g.height) return zone.id;
      } else if (pointInPolygon(x, y, zone.geometry.points)) {
        return zone.id;
      }
    }
    return null;
  }

  myHandZoneId(): string | null {
    for (const zone of this.model.zones.values()) {
      if (zone.kind === "hand" && zone.owner_seat === this.model.seatId) return zone.id;
    }
    return null;
  }

  clientToWorld(clientX: number, clientY: number): [number, number] {
    const box = this.surface.getBoundingClientRect();
    return screenToWorld(this.viewport, clientX - box.left, clientY - box.top);
  }

  /** Where a piece is drawn on screen, centre, in client coordinates. */
  clientPositionOf(id: string): [number, number] | null {
    const node = this.pieceNodes.get(id);
    if (node === undefined) return null;
    const box = node.element.getBoundingClientRect();
    return [box.left + box.width / 2, box.top + box.height / 2];
  }

  pieceElement(id: string): HTMLElement | null {
    return this.pieceNodes.get(id)?.element ?? null;
  }

  /** A short name for a piece, for menus and announcements. Never more than this viewer may know. */
  pieceLabel(id: string): string {
    const piece = this.model.pieces.get(id);
    if (piece === undefined) return "a piece";
    const component =
      piece.component_id === null ? undefined : this.model.components.get(piece.component_id);
    if (component?.title) return component.title;
    return piece.component_id === null ? `face-down ${piece.kind}` : `a ${piece.kind}`;
  }

  zoneLabelOf(zoneId: string): string {
    const zone = this.model.zones.get(zoneId);
    if (zone === undefined) return "the table";
    return this.zoneLabel(zone.label, zone.owner_seat);
  }

  nameOf(seatId: string): string {
    const seat = this.model.seats.get(seatId);
    return seat?.display_name ?? seat?.label ?? "Someone";
  }

  /** The CSS colour of a seat's tint, for ink. */
  seatColour(seatId: string): string {
    const seat = this.model.seats.get(seatId);
    if (seat === undefined) return "#9db0b2";
    const token = seatTintClass(seat.tint_index).replace("seat-", "--seat-");
    const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
    return value || "#9db0b2";
  }

  private get root(): HTMLElement {
    return this.options.root;
  }

  private touch(id: string): void {
    this.diff.pieces.add(id);
    this.schedule();
  }

  private chooseMenuItem(item: MenuItemView, pieceId: string): void {
    this.intents.send(item.op_type, item.payload);
    if (item.op_type === "peek") this.lookingFromMenu = pieceId;
  }

  /** Set when "Look closely" was chosen, so the look opens once the server agrees. */
  lookingFromMenu: string | null = null;

  // -- announcing ------------------------------------------------------------------------

  private announceEvent(type: string, fields: Record<string, unknown>): void {
    const pieceId = typeof fields["piece_id"] === "string" ? fields["piece_id"] : null;
    const by = typeof fields["by_seat"] === "string" ? fields["by_seat"] : null;
    if (type === "peek" && pieceId !== null && by === this.model.seatId) {
      this.listener.onOwnPeek?.(pieceId);
      return;
    }
    if (type === "show" && pieceId !== null && by !== null) {
      const seats = Array.isArray(fields["to_seats"])
        ? fields["to_seats"].filter((seat): seat is string => typeof seat === "string")
        : [];
      const audience = this.reveals.audience(this.model, seats, by, this.model.seatId);
      const who = by === this.model.seatId ? "You are" : `${this.nameOf(by)} is`;
      const toMe = this.model.seatId !== null && seats.includes(this.model.seatId);
      const what = toMe || by === this.model.seatId ? this.pieceLabel(pieceId) : "a card";
      this.announcer.announce(`${who} showing ${what} to ${audience}.`);
      return;
    }
    if (type === "show_end" && by !== null) {
      const who = by === this.model.seatId ? "You" : this.nameOf(by);
      this.announcer.announce(`${who} put away the card being shown.`);
    }
  }

  private announceZoneChanges(diff: Diff): void {
    const changes = diff.zoneChanges;
    if (changes.length === 0) return;
    if (changes.length > ANNOUNCE_EACH_UP_TO) {
      this.announcer.announce(`${changes.length} pieces moved.`);
      return;
    }
    const sentences = changes.map((change) => {
      const where = this.isInMyHand(change.to)
        ? "your hand"
        : this.zoneLabelOf(change.to);
      const name = this.pieceLabel(change.id);
      return `${name[0]!.toUpperCase()}${name.slice(1)} moved to ${where}.`;
    });
    this.announcer.announce(sentences.join(" "));
  }

  // -- geometry ----------------------------------------------------------------------

  private writeWorldTransform(): void {
    const { offsetX, offsetY, scale } = this.viewport;
    this.world.style.transform =
      `translate3d(${offsetX.toFixed(2)}px, ${offsetY.toFixed(2)}px, 0)` +
      ` scale(${scale.toFixed(4)})`;
  }

  /**
   * The part of the surface the table gets to use.
   *
   * The hand tray covers the bottom edge, so fitting the table to the whole
   * surface would tuck the near edge of it underneath your own hand.
   */
  private surfaceSize(): { width: number; height: number } {
    const height = this.surface.clientHeight || 600;
    const trayHeight = this.tray.hidden ? 0 : this.tray.clientHeight;
    return {
      width: this.surface.clientWidth || 960,
      height: Math.max(height - trayHeight, 240),
    };
  }

  private tableBounds(): Bounds | null {
    const boxes: Bounds[] = [];
    for (const zone of this.model.zones.values()) {
      if (this.isInMyHand(zone.id)) continue;
      boxes.push(geometryBounds(zone.geometry));
    }
    for (const piece of this.model.pieces.values()) {
      if (this.isInMyHand(piece.zone_id)) continue;
      const component =
        piece.component_id === null
          ? undefined
          : this.model.components.get(piece.component_id);
      const [width, height] = pieceSize(piece, component);
      boxes.push({
        minX: piece.x - width / 2,
        minY: piece.y - height / 2,
        maxX: piece.x + width / 2,
        maxY: piece.y + height / 2,
      });
    }
    return unionBounds(boxes);
  }

  private observeSize(): void {
    const apply = (): void => {
      const width = this.surface.clientWidth || 960;
      const height = this.surface.clientHeight || 600;
      this.ink.resize(width, height, window.devicePixelRatio || 1);
      this.canvasDirty = true;
      this.trayDirty = true;
      if (!this.controller.adjustedByPerson) this.controller.fit();
      this.schedule();
    };
    apply();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", apply);
      return;
    }
    this.resizeObserver = new ResizeObserver(apply);
    this.resizeObserver.observe(this.surface);
  }
}

function pointInPolygon(x: number, y: number, points: Array<[number, number]>): boolean {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i, i += 1) {
    const [xi, yi] = points[i]!;
    const [xj, yj] = points[j]!;
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function element(tag: string, className: string): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  return node;
}

function button(label: string, onClick: () => void, glyph?: string): HTMLElement {
  const node = document.createElement("button");
  node.type = "button";
  // Raised rather than quiet: these sit on the felt, not on paper.
  node.className = "button button--secondary button--sm";
  node.textContent = glyph ?? label;
  node.setAttribute("aria-label", label);
  node.addEventListener("click", onClick);
  return node;
}

export { initialsFor };
