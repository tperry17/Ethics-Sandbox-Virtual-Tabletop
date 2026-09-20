/**
 * The table, rendered.
 *
 * Everything here reconciles from state. A message updates the model and
 * records what changed; one animation frame later, exactly the DOM nodes
 * that changed are rewritten. The table is never rebuilt, and no node is
 * touched because a message arrived - only because a value on it differs.
 *
 * This half of the client renders and moves the camera. It knows no rule,
 * holds no deck, and asks for nothing: a face it was not sent is a face it
 * cannot draw.
 */

import { InkLayer } from "./ink.js";
import { type Diff, TableModel, emptyDiff, mergeDiff } from "./model.js";
import { PieceNode, initialsFor, pieceSize } from "./piece-node.js";
import { geometryBounds, polygonClipPath } from "./geometry.js";
import type {
  LinkStatus,
  MacroView,
  SeatView,
  ServerLink,
  ServerMessage,
} from "./protocol.js";
import { ViewportController } from "./viewport-input.js";
import { type Bounds, type Viewport, unionBounds } from "./viewport.js";

/** Where a card's centre sits in the tray, so its top edge starts at the top. */
const TRAY_BASELINE = 160;
const MAX_NOTICES = 3;
const NOTICE_MS = 6000;

export interface RendererOptions {
  root: HTMLElement;
  toolbar: HTMLElement | null;
  link: ServerLink;
  roomCode: string;
  /** Called when a toolbar button is pressed. What it means is the server's. */
  onMacro?: (macroId: string) => void;
}

export class TableRenderer {
  readonly model = new TableModel();

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
    this.surface.append(this.world, this.canvas, this.controls(), this.status);
    this.surface.append(this.notices);

    this.tray = element("div", "hand-tray");
    this.tray.hidden = true;
    this.trayLabel = element("p", "hand-tray__label");
    this.trayFan = element("div", "hand-tray__fan");
    this.tray.append(this.trayLabel, this.trayFan);

    root.append(this.surface, this.tray);

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
      return;
    }
    if (message.type === "patches") {
      this.absorb(this.model.applyPatches(message.patches, message.seq));
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
      if (!this.controller.adjustedByPerson) this.controller.fit();
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
      if (event.type !== "point") continue;
      const x = event.fields["x"];
      const y = event.fields["y"];
      const seat = event.fields["seat_id"];
      if (typeof x === "number" && typeof y === "number" && typeof seat === "string") {
        this.ink.ping(x, y, seat, now);
        this.canvasDirty = true;
      }
    }

    if (this.trayDirty) {
      this.trayDirty = false;
      const wasShowing = !this.tray.hidden;
      this.layoutTray();
      if (wasShowing !== !this.tray.hidden && !this.controller.adjustedByPerson) {
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
      pinging = this.ink.draw(
        this.viewport,
        this.model.strokes.values(),
        this.model.cursors,
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

    const home = this.isInMyHand(piece.zone_id) ? "tray" : "world";
    if (this.pieceHome.get(id) !== home) {
      this.pieceHome.set(id, home);
      (home === "tray" ? this.trayFan : this.pieceLayer).append(node.element);
      this.trayDirty = true;
      this.animating.delete(id);
    }

    const component =
      piece.component_id === null
        ? undefined
        : this.model.components.get(piece.component_id);
    const [width, height] = pieceSize(piece, component);
    node.setSize(width, height);
    node.setZ(this.model.stackingOrder(piece.zone_id, piece.z));
    node.setFace(piece, component, this.model.zones.get(piece.zone_id)?.label ?? "");
    this.syncHolder(id);

    if (home === "tray") {
      this.trayDirty = true;
      return;
    }

    // The person dragging must see their own piece exactly where their hand
    // is. Everyone else's pieces glide, so that a table in motion reads as
    // hands moving things rather than things teleporting.
    const mine = piece.held_by !== null && piece.held_by === this.model.seatId;
    const animate = !fresh && !mine && !this.reduceMotion;
    node.setTarget(piece, animate, now);
    if (animate) this.animating.add(id);
    else node.advance(now);
  }

  private syncHolder(id: string): void {
    const node = this.pieceNodes.get(id);
    const piece = this.model.pieces.get(id);
    if (node === undefined || piece === undefined) return;
    const holder =
      piece.held_by === null ? undefined : this.model.seats.get(piece.held_by);
    node.setClasses(piece, holder, this.pieceHome.get(id) === "tray" ? "piece--in-tray" : "");
    node.setHolder(holder);
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

    this.tray.hidden = ids.length === 0;
    if (ids.length === 0) {
      this.trayLabel.textContent = "";
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

  private renderToolbar(): void {
    const toolbar = this.options.toolbar;
    if (toolbar === null) return;
    toolbar.replaceChildren();
    if (this.model.macros.length === 0) {
      const empty = element("p", "toolbar__empty prose");
      empty.textContent =
        "Macro buttons for this exercise appear here once it defines them.";
      toolbar.append(empty);
      return;
    }
    for (const macro of this.model.macros) {
      toolbar.append(this.macroButton(macro));
    }
  }

  private macroButton(macro: MacroView): HTMLElement {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "button button--sm";
    node.dataset.macroId = macro.id;
    node.textContent = macro.label;
    if (macro.hint !== null) node.title = macro.hint;
    node.addEventListener("click", () => this.options.onMacro?.(macro.id));
    return node;
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

  private notice(text: string, level: "info" | "warning"): void {
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
