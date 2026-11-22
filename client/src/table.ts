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

import { activityInProgress, renderActivities, renderTrades } from "./activities.js";
import { clock, renderClasses } from "./classes.js";
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
  ZoneView,
} from "./protocol.js";
import { RevealLayer } from "./reveal.js";
import { ViewportController } from "./viewport-input.js";
import { renderPiecesMenu } from "./pieces.js";
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
 * `hideFace` draws the back of a card just turned face down; `turned` draws
 * a tile's other side; `lifted` draws it picked up. Any field left out falls
 * through to the server's truth.
 */
export interface Override {
  x?: number;
  y?: number;
  rotation?: number;
  hideFace?: boolean;
  turned?: boolean;
  lifted?: boolean;
}
export interface RendererOptions {
  root: HTMLElement;
  toolbar: HTMLElement | null;
  /** The room page's button that opens and closes the side panel, if any. */
  panelToggle?: HTMLElement | null;
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
  private readonly trayToggle: HTMLButtonElement;
  private readonly trayBody: HTMLElement;
  private readonly trayEmpty: HTMLElement;
  private readonly status: HTMLElement;
  private readonly banner: HTMLElement;
  private readonly timerText: HTMLElement;
  private readonly promptCard: HTMLElement;
  /** Prompts this person has put away, as `<class>:<serial>`. */
  private readonly dismissedPrompts = new Set<string>();
  /** Classes whose timer has been seen running, so each chimes once. */
  private readonly timerArmed = new Set<string>();
  private audio: AudioContext | null = null;
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
  private readonly controlsElement: HTMLElement;
  private readonly toolGroup = element("div", "tabletop__palette");
  private readonly piecesSlot = element("div", "tabletop__pieces-slot");
  private readonly buttonsSlot = element("div", "tabletop__pieces-slot");
  /** The Draw menu (pen and clearing ink) and the Point button, filled by the interaction half. */
  private readonly drawSlot = element("div", "tabletop__pieces-slot");
  private readonly pointSlot = element("div", "tabletop__pieces-slot");
  /** Sign-ups this person has seen with the side panel open. */
  private readonly seenSignups = new Set<string>();
  private piecesAdded = 0;
  private lastNotice = { text: "", at: 0 };

  private diff: Diff = emptyDiff();
  private frameRequested = false;
  private canvasDirty = true;
  private trayDirty = true;
  /** The pieces last seen in this viewer's hand; null until a snapshot has been laid out. */
  private trayKnown: Set<string> | null = null;
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
    this.banner = element("div", "tabletop__banner");
    this.timerText = element("p", "tabletop__timer");
    this.timerText.setAttribute("role", "timer");
    this.promptCard = element("aside", "tabletop__prompt");
    this.banner.append(this.timerText, this.promptCard);
    this.banner.hidden = true;
    this.notices = element("div", "tabletop__notices");
    this.notices.setAttribute("role", "status");
    this.notices.setAttribute("aria-live", "polite");

    this.world.append(this.zoneLayer, this.pieceLayer);
    this.controlsElement = this.controls();
    this.surface.append(this.world, this.canvas, this.controlsElement, this.status);
    // Your tools float over the table, where your hand is.
    this.surface.append(this.toolGroup);
    this.surface.append(this.notices, this.banner);

    this.tray = element("div", "hand-tray");
    this.tray.hidden = true;
    // Docked below the table, for anyone who has a private hand: it is
    // there before the first card arrives, so there is always somewhere to
    // drop one.
    // It starts closed on every load, a single row naming the hand; its
    // name is a button that opens and closes it. Closed, it is still
    // somewhere to drop a card.
    const trayHead = element("div", "hand-tray__head");
    this.trayToggle = document.createElement("button");
    this.trayToggle.type = "button";
    this.trayToggle.className = "hand-tray__toggle";
    this.trayToggle.id = "hand-tray-toggle";
    this.trayToggle.setAttribute("aria-controls", "hand-tray-body");
    this.trayToggle.title = "Only you see the faces of the cards in your hand";
    this.trayLabel = element("span", "hand-tray__label");
    this.trayToggle.append(element("span", "hand-tray__chevron"), this.trayLabel);
    this.trayToggle.addEventListener("click", () =>
      this.setTrayOpen(this.trayToggle.getAttribute("aria-expanded") !== "true"),
    );
    trayHead.append(this.trayToggle);
    this.trayEmpty = element(
      "p",
      "hand-tray__empty",
      "Cards dealt to you land here, and only you see their faces. Drag a card here to take it into your hand.",
    );
    this.trayFan = element("div", "hand-tray__fan");
    this.trayBody = element("div", "hand-tray__body");
    this.trayBody.id = "hand-tray-body";
    this.trayBody.append(this.trayEmpty, this.trayFan);
    this.tray.append(trayHead, this.trayBody);
    this.trayToggle.setAttribute("aria-expanded", "false");
    this.tray.classList.add("is-collapsed");
    this.trayBody.hidden = true;

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
      ...(this.options.roomCode === ""
        ? {}
        : { storageKey: `sandbox:view:${this.options.roomCode}` }),
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
    // Opening the panel shows every sign-up, so its mark goes.
    this.options.panelToggle?.addEventListener("click", () => this.markActivitiesButton());
    this.controller.attach();
    this.observeSize();
    this.options.link.onMessage((message) => this.receive(message));
    this.options.link.onStatus((status) => this.setStatus(status));
    this.options.link.start();
    this.renderToolbar();
    this.bannerTimer = window.setInterval(() => this.updateBanner(), 500);
  }

  private bannerTimer = 0;

  /**
   * The class's countdown and pushed prompt, drawn on every screen. The
   * countdown is advisory: reaching zero chimes once and changes nothing.
   */
  private updateBanner(): void {
    const now = performance.now();
    const mine = this.model.classes.find((group) => group.timer_remaining !== null);
    const lines: string[] = [];
    for (const group of this.model.classes) {
      const ends = this.model.classTimerEnds.get(group.id);
      if (ends === undefined) {
        this.timerArmed.delete(group.id);
        continue;
      }
      const left = (ends - now) / 1000;
      lines.push(left > 0 ? clock(left) : "Time");
      if (left > 0) this.timerArmed.add(group.id);
      else if (this.timerArmed.delete(group.id)) {
        this.chime();
        this.announcer.announce("Time is up.");
      }
    }
    const shown = lines.length > 0 && mine !== undefined;
    this.timerText.hidden = !shown;
    if (shown) this.timerText.textContent = lines.join(" · ");
    const group = this.model.classes.find(
      (g) => g.prompt !== "" && !this.dismissedPrompts.has(`${g.id}:${g.prompt_serial}`),
    );
    if (group === undefined) this.promptCard.hidden = true;
    else if (this.promptCard.dataset.key !== `${group.id}:${group.prompt_serial}`) {
      this.promptCard.hidden = false;
      this.promptCard.dataset.key = `${group.id}:${group.prompt_serial}`;
      const text = element("p", "tabletop__prompt-text");
      text.textContent = group.prompt;
      const close = button("Put away", () => {
        this.dismissedPrompts.add(`${group.id}:${group.prompt_serial}`);
        this.updateBanner();
      });
      this.promptCard.replaceChildren(text, close);
    }
    this.banner.hidden = this.timerText.hidden && this.promptCard.hidden;
  }

  private chime(): void {
    try {
      const AudioCtor = window.AudioContext;
      this.audio ??= new AudioCtor();
      const tone = this.audio.createOscillator();
      const gain = this.audio.createGain();
      tone.frequency.value = 660;
      gain.gain.setValueAtTime(0.0001, this.audio.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.2, this.audio.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, this.audio.currentTime + 1.2);
      tone.connect(gain).connect(this.audio.destination);
      tone.start();
      tone.stop(this.audio.currentTime + 1.3);
    } catch {
      // No sound is available; the banner and the live region still say it.
    }
  }

  stop(): void {
    window.clearInterval(this.bannerTimer);
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

  /** Move the camera by a finger's travel, in screen pixels. */
  panBy(dx: number, dy: number): void {
    this.controller.panByPerson(dx, dy);
  }

  // -- incoming ---------------------------------------------------------------

  private receive(message: ServerMessage): void {
    if (message.type === "snapshot") {
      this.absorb(this.model.applySnapshot(message));
      this.listener.onSnapshot?.();
      return;
    }
    if (message.type === "patches") {
      const swappedBefore = new Set(this.model.swapped);
      this.absorb(
        this.model.applyPatches(message.patches, message.seq, message.components ?? []),
      );
      for (const pair of this.model.swapped) {
        if (swappedBefore.has(pair)) continue;
        const [a, b] = pair.split("|");
        if (a !== undefined && b !== undefined) {
          // Said at the next render, in place of the cards' own moves.
          this.tradeAnnouncement = `${this.nameOf(a)} and ${this.nameOf(b)} have traded cards.`;
        }
      }
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
    if (message.type === "class_sort") {
      this.model.classSort = message;
      this.renderToolbar();
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
      // What a snapshot brings was already in the hand, not just arriving.
      this.trayKnown = null;
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
      // A deck's label carries its count, which any move may change.
      if (diff.pieces.size > 0 || diff.removedPieces.size > 0) this.syncDeckLabels();
    }

    if (diff.seats) {
      this.canvasDirty = true;
      // The tray is named for this viewer, who may have just been named.
      this.writeTrayLabel();
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
    // Your own private hand is drawn in the tray docked below the table;
    // anyone else's is not drawn at all.
    const docked = this.isInMyHand(id) || this.isOthersHand(id);
    if (node.hidden !== docked) node.hidden = docked;

    const label = node.firstElementChild;
    let text = this.zoneLabel(zone);
    // A deck says how many cards it holds ("Core deck · 18"): the count of
    // backs the server sent, never anything about their faces.
    if (zone.kind === "deck") text = `${text} · ${this.piecesIn(id)}`;
    if (label instanceof HTMLElement && label.textContent !== text) {
      label.textContent = text;
    }
  }

  private piecesIn(zoneId: string): number {
    let count = 0;
    for (const piece of this.model.pieces.values()) {
      if (piece.zone_id === zoneId) count += 1;
    }
    return count;
  }

  private syncDeckLabels(): void {
    for (const zone of this.model.zones.values()) {
      if (zone.kind === "deck") this.syncZone(zone.id);
    }
  }

  /**
   * A zone's name as this viewer reads it. A hand is named for whoever holds
   * it, by the name they joined with ("Ada's hand"), not for their seat.
   */
  private zoneLabel(zone: ZoneView): string {
    const { label, owner_seat: ownerSeat } = zone;
    if (ownerSeat === null) return label;
    const seat = this.model.seats.get(ownerSeat);
    const name = seat?.display_name ?? seat?.label ?? null;
    if (name === null) return label;
    if (zone.kind === "hand") return ownerSeat === this.model.seatId ? "your hand" : `${name}'s hand`;
    return ownerSeat === this.model.seatId ? `${label} · you` : `${label} · ${name}`;
  }

  /**
   * Someone else's private hand: not drawn on the table, nor the backs of
   * the cards in it. An open hand stays on the table, to be read in place.
   */
  private isOthersHand(zoneId: string): boolean {
    const zone = this.model.zones.get(zoneId);
    return (
      zone !== undefined &&
      zone.kind === "hand" &&
      zone.visibility === "private_to_owner" &&
      zone.owner_seat !== null &&
      zone.owner_seat !== this.model.seatId
    );
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
    // Kept current in the tray too, where setTarget (which also sets it) is not called.
    if (node.element.dataset.zoneId !== piece.zone_id) node.element.dataset.zoneId = piece.zone_id;

    if (home === "tray") {
      this.trayDirty = true;
      return;
    }
    const elsewhere = this.isOthersHand(piece.zone_id) && !pinned;
    if (node.element.hidden !== elsewhere) node.element.hidden = elsewhere;

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
    // A tile's other side is known already, so turning one over can be shown at once.
    if (override.turned === true) shown.face_up = !piece.face_up;
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
    const component =
      piece.component_id === null ? undefined : this.model.components.get(piece.component_id);
    node.setClasses(piece, holder, extra.join(" "), component?.tint_index ?? null);
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
    // Only a private hand goes in the tray; an open one stays on the table
    // where everyone, its owner included, reads it in place.
    return (
      zone.kind === "hand" &&
      zone.visibility === "private_to_owner" &&
      zone.owner_seat === this.model.seatId
    );
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
    const ids = this.handPieceIds();
    const zone = this.myHandZone();
    const hidden = zone === undefined && ids.length === 0;
    if (this.tray.hidden !== hidden) this.tray.hidden = hidden;
    if (this.trayEmpty.hidden !== ids.length > 0) this.trayEmpty.hidden = ids.length > 0;

    // A piece arriving opens the tray, so it is seen; what was already
    // there when the page loaded leaves it closed.
    const known = this.trayKnown;
    this.trayKnown = new Set(ids);
    if (known !== null && this.trayBody.hidden && ids.some((id) => !known.has(id))) {
      this.setTrayOpen(true);
    }

    this.writeTrayLabel(ids, zone);
    if (ids.length === 0) return;

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
    // The Table buttons, Draw and Pieces menus drop down over the same
    // corner, so opening one closes the others. "toggle" does not bubble;
    // capture it.
    controls.addEventListener(
      "toggle",
      (event) => {
        const opened = event.target;
        if (!(opened instanceof HTMLDetailsElement) || !opened.open) return;
        for (const other of controls.querySelectorAll("details")) {
          if (other !== opened) other.open = false;
        }
      },
      true,
    );
    controls.append(
      this.buttonsSlot,
      this.drawSlot,
      this.piecesSlot,
      this.pointSlot,
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
    return this.toolGroup;
  }

  /** Where the Draw menu goes: beside the Table buttons, among the table's controls. */
  get drawArea(): HTMLElement {
    return this.drawSlot;
  }

  /** Where the Point button goes: on the same row as the menus. */
  get pointArea(): HTMLElement {
    return this.pointSlot;
  }

  /** The room's Pieces menu, among the camera controls; redrawn with the toolbar. */
  private renderPiecesMenu(): void {
    const wasOpen = this.piecesSlot.querySelector("details")?.open ?? false;
    const menu = renderPiecesMenu(
      this.model.piecesMenu,
      (componentId) => {
        // Where the person is looking: the middle of the visible table.
        const box = this.surface.getBoundingClientRect();
        const [x, y] = this.clientToWorld(box.left + box.width / 2, box.top + box.height / 2);
        // Several added in a row fan out a little, rather than hiding each other.
        const step = (this.piecesAdded++ % 6) * 60;
        this.intents.send("add_piece", { component_id: componentId, x: x + step, y: y + step / 3 });
      },
      (zoneId) => this.intents.send("remove_deck", { zone_id: zoneId }),
      wasOpen,
    );
    this.piecesSlot.replaceChildren(...(menu === null ? [] : [menu]));
  }

  /**
   * The room's buttons, in their own menu among the camera controls, closed
   * until it is opened; it stays open or closed as it was while the toolbar
   * redraws. An activity's buttons are drawn in that activity's own row of
   * the side panel instead; only those whose activity has no row there are
   * kept here, so none is lost.
   */
  private renderButtonsMenu(placed: ReadonlySet<MacroView>): void {
    const wasOpen = this.buttonsSlot.querySelector("details")?.open ?? false;
    const macros = this.model.macros.filter((macro) => !placed.has(macro));
    if (macros.length === 0) {
      this.buttonsSlot.replaceChildren();
      return;
    }
    const root = element("details", "table-buttons");
    (root as HTMLDetailsElement).open = wasOpen;
    const summary = element("summary", "button button--secondary button--sm");
    summary.textContent = "Table buttons";
    const panel = element("div", "table-buttons__panel");
    panel.setAttribute("role", "group");
    panel.setAttribute("aria-label", "Table buttons");
    for (const macro of macros) panel.append(this.macroButton(macro));
    root.append(summary, panel);
    this.buttonsSlot.replaceChildren(root);
  }

  /**
   * Put each activity's buttons in that activity's row of the side panel (a
   * running activity, or a class's table), and say which went there.
   */
  private placeActivityButtons(toolbar: HTMLElement): Set<MacroView> {
    const placed = new Set<MacroView>();
    for (const macro of this.model.macros) {
      if (!macro.activity_id) continue;
      const row = [...toolbar.querySelectorAll<HTMLElement>("[data-activity-id]")].find(
        (candidate) =>
          candidate.dataset.activityId === macro.activity_id && candidate.tagName !== "BUTTON",
      );
      if (row === undefined) continue;
      let buttons = row.querySelector<HTMLElement>(":scope > .toolbar__activity-buttons");
      if (buttons === null) {
        buttons = element("div", "toolbar__activity-buttons room-panel__buttons");
        row.append(buttons);
      }
      buttons.append(this.macroButton(macro));
      placed.add(macro);
    }
    return placed;
  }

  /**
   * Mark the side panel's "Activities" button while the panel is closed and
   * a sign-up has opened that this person has not seen with it open.
   */
  private markActivitiesButton(): void {
    const toggle = this.options.panelToggle ?? null;
    if (toggle === null) return;
    const signups = [...this.model.activities.values()]
      .filter((activity) => activity.status === "signup")
      .map((activity) => activity.id);
    if (toggle.getAttribute("aria-expanded") === "true") {
      for (const id of signups) this.seenSignups.add(id);
    }
    const unseen = signups.some((id) => !this.seenSignups.has(id));
    let mark = toggle.querySelector<HTMLElement>(".room__panel-toggle-mark-new");
    if (unseen && mark === null) {
      mark = element("span", "room__panel-toggle-mark-new");
      mark.append(element("span", "visually-hidden", ": a new sign-up"));
      toggle.append(mark);
    } else if (!unseen && mark !== null) {
      mark.remove();
    }
  }

  private renderToolbar(): void {
    this.renderPiecesMenu();
    const toolbar = this.options.toolbar;
    if (toolbar === null) return;
    const kept = rememberControls(toolbar);
    toolbar.replaceChildren();
    if (this.model.macros.length === 0 && this.model.activityChoices.length === 0) {
      const empty = element("p", "toolbar__empty prose");
      empty.textContent =
        "Macro buttons for this exercise appear here once it defines them.";
      toolbar.append(empty);
    }
    const activities = renderActivities(this.model, (payload) =>
      this.intents.send("activity", payload),
    );
    if (activities !== null) toolbar.append(activities);
    const classes = renderClasses(
      this.model,
      (payload) => this.intents.send("class", payload),
      (payload) => this.intents.send("activity", payload),
      () => this.renderToolbar(),
    );
    // While an activity is going the panel is that activity's; a class can
    // be started again once it is finished.
    const showClasses = classes !== null && (this.model.classes.length > 0 || !activityInProgress(this.model));
    if (showClasses) toolbar.append(panelSection("Run a class", classes, "room-panel__class"));
    this.renderButtonsMenu(this.placeActivityButtons(toolbar));
    this.markActivitiesButton();
    const trades = renderTrades(this.model, () => this.selection, (opType, payload) =>
      this.intents.send(opType, payload),
    );
    if (trades !== null) toolbar.append(panelSection("Trades", trades));
    restoreControls(toolbar, kept);
  }

  private macroButton(macro: MacroView): HTMLElement {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "button button--sm";
    node.dataset.macroId = macro.id;
    if (macro.activity_id) node.dataset.activityId = macro.activity_id;
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
    this.intents.send("macro", {
      macro_id: macro.id,
      ...(macro.activity_id ? { activity_id: macro.activity_id } : {}),
    });
  }

  private setStatus(status: LinkStatus): void {
    this.status.dataset.status = status;
    this.status.textContent =
      status === "connected"
        ? "Connected"
        : status === "reconnecting"
          ? "Reconnecting…"
          : status === "refused"
            ? "Not in this room"
            : "Offline";
    if (status === "offline" && !this.offlineTold) {
      this.offlineTold = true;
      this.notice(
        "Can't reach the table. Check your Wi-Fi. Your place is kept, and this page keeps trying.",
        "warning",
      );
    }
    if (status === "connected") this.offlineTold = false;
    if (status === "refused") {
      this.notice(
        "This table would not open for you: you have not joined this room, or it is closed. Go to the join page and enter the room code again.",
        "warning",
      );
    }
  }

  private offlineTold = false;
  private tradeAnnouncement: string | null = null;

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

  /** This viewer's own private hand, if they have one. */
  private myHandZone(): ZoneView | undefined {
    for (const zone of this.model.zones.values()) {
      if (this.isInMyHand(zone.id)) return zone;
    }
    return undefined;
  }

  /** The pieces in this viewer's hand, bottom first. */
  private handPieceIds(): string[] {
    return [...this.model.pieces.values()]
      .filter((piece) => this.isInMyHand(piece.zone_id))
      .sort((a, b) => a.z - b.z)
      .map((piece) => piece.id);
  }

  /**
   * Name the tray for whoever holds it ("Tomer's Hand"), not for the seat
   * the zone's label names ("Hand · Seat 1"); closed and holding something,
   * say how much. Written only when it changes: presence updates call this
   * often, and every write would lay the page out again.
   */
  private writeTrayLabel(
    ids: string[] = this.handPieceIds(),
    zone: ZoneView | undefined = this.myHandZone(),
  ): void {
    const hand = zone === undefined ? "Hand" : handName(zone.label);
    const me = this.model.seatId === null ? undefined : this.model.seats.get(this.model.seatId);
    const owner = me?.display_name?.trim();
    let text = owner ? `${owner}'s ${hand}` : hand;
    if (this.trayBody.hidden && ids.length > 0) {
      const allCards = ids.every((id) => this.model.pieces.get(id)?.kind === "card");
      const noun = allCards ? "card" : "piece";
      text += ` (${ids.length} ${noun}${ids.length === 1 ? "" : "s"})`;
    }
    if (this.trayLabel.textContent !== text) this.trayLabel.textContent = text;
  }

  /** Open or close the hand tray. Closed, only its name shows. */
  private setTrayOpen(open: boolean): void {
    this.trayToggle.setAttribute("aria-expanded", String(open));
    this.tray.classList.toggle("is-collapsed", !open);
    this.trayBody.hidden = !open;
    // The fan is measured to lay it out, and it has no width while closed.
    this.trayDirty = true;
    this.schedule();
  }

  /** Light the hand tray up as somewhere a held piece could be let go. */
  setTrayTarget(on: boolean): void {
    this.tray.classList.toggle("is-drop-target", on);
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
  /**
   * The table a piece let go over no zone lands on. The table has no edge:
   * its zone is not drawn, and anywhere outside every other zone is on it.
   * A piece already in an activity's zones goes to that activity's table
   * (zones of one activity share the id prefix before ":"), anything else to
   * the room's.
   */
  tableFor(pieceZoneId: string | null): string | null {
    const prefix = pieceZoneId?.includes(":") ? pieceZoneId.slice(0, pieceZoneId.indexOf(":") + 1) : "";
    let room: string | null = null;
    for (const zone of this.model.zones.values()) {
      if (zone.kind !== "table") continue;
      if (prefix !== "" && zone.id.startsWith(prefix)) return zone.id;
      if (room === null && !zone.id.includes(":")) room = zone.id;
    }
    return room;
  }

  /** Whether a zone is a pile: a deck or a discard pile. */
  isPile(zoneId: string | null | undefined): boolean {
    const kind = zoneId == null ? undefined : this.model.zones.get(zoneId)?.kind;
    return kind === "deck" || kind === "discard";
  }

  /** The topmost zone at a point; with `skipPiles`, the topmost that is not a pile. */
  zoneAtWorld(x: number, y: number, skipPiles = false): string | null {
    const zones = [...this.model.zones.values()].filter(
      (zone) => !skipPiles || !this.isPile(zone.id),
    ).sort(
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

  /** A piece's size in world units, as it is drawn. */
  pieceSizeOf(id: string): [number, number] {
    const piece = this.model.pieces.get(id);
    if (piece === undefined) return [0, 0];
    const component =
      piece.component_id === null ? undefined : this.model.components.get(piece.component_id);
    return pieceSize(piece, component);
  }

  /** The decks and discard piles on the table, other than `except`, with their outlines. */
  piles(except: string | null): Array<{ id: string; bounds: Bounds }> {
    const piles: Array<{ id: string; bounds: Bounds }> = [];
    for (const zone of this.model.zones.values()) {
      if (zone.id === except || !this.isPile(zone.id)) continue;
      piles.push({ id: zone.id, bounds: geometryBounds(zone.geometry) });
    }
    return piles;
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
    return this.zoneLabel(zone);
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

  /** Send what a menu entry stands for, as if it had been chosen from the menu. */
  chooseMenuItem(item: MenuItemView, pieceId: string): void {
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
    if (this.tradeAnnouncement !== null) {
      this.announcer.announce(this.tradeAnnouncement);
      this.tradeAnnouncement = null;
      return;
    }
    if (diff.zoneChanges.length === 0) return;
    // A piece set down on the open table is an ordinary move, and ordinary
    // moves are not announced. A few pieces going into a hand, a deck or a
    // named zone are; so is a deal or a collect, which moves many at once.
    const changes =
      diff.zoneChanges.length > ANNOUNCE_EACH_UP_TO
        ? diff.zoneChanges
        : diff.zoneChanges.filter((change) => this.model.zones.get(change.to)?.kind !== "table");
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
   * The hand tray is docked below the surface, not over it, so the whole
   * surface is the table's.
   */
  private surfaceSize(): { width: number; height: number } {
    return {
      width: this.surface.clientWidth || 960,
      height: Math.max(this.surface.clientHeight || 600, 240),
    };
  }

  private tableBounds(): Bounds | null {
    const boxes: Bounds[] = [];
    // The table has no edge: what is fitted is what is on it - every other
    // zone and every piece - and the table zone's own area only when there
    // is nothing else. The fit never zooms past 100% (FIT_MAX_SCALE).
    const tables: Bounds[] = [];
    for (const zone of this.model.zones.values()) {
      if (this.isInMyHand(zone.id) || this.isOthersHand(zone.id)) continue;
      (zone.kind === "table" ? tables : boxes).push(geometryBounds(zone.geometry));
    }
    for (const piece of this.model.pieces.values()) {
      if (this.isInMyHand(piece.zone_id) || this.isOthersHand(piece.zone_id)) continue;
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
    return unionBounds(boxes.length > 0 ? boxes : tables);
  }

  private observeSize(): void {
    const apply = (): void => {
      const width = this.surface.clientWidth || 960;
      const height = this.surface.clientHeight || 600;
      this.ink.resize(width, height, window.devicePixelRatio || 1);
      this.canvasDirty = true;
      this.trayDirty = true;
      this.controller.resized();
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

/**
 * The toolbar is rebuilt whenever the table changes, and a rebuilt dropdown
 * starts again at its first entry. Someone choosing an activity must find
 * their choice still there when they press Start, however many people have
 * joined or moved a cursor in between.
 */
interface KeptControl {
  value: string;
  focused: boolean;
}

/** The toolbar's choices that are made first and acted on later, by a button. */
const KEPT_LABELS = new Set(["Activity to start", "Activity for the class", "Number of tables"]);

/** A stable name for a control worth keeping, or null: most are acted on at once. */
function controlKey(control: Element, counts: Map<string, number>): string | null {
  const label = control.getAttribute("aria-label");
  const option = (control as HTMLElement).dataset["option"];
  if (!(label !== null && KEPT_LABELS.has(label)) && option === undefined) return null;
  const base = `${control.tagName}:${label ?? ""}:${option ?? ""}`;
  const seen = counts.get(base) ?? 0;
  counts.set(base, seen + 1);
  return `${base}#${seen}`;
}

/** One headed section of the room's side panel. */
function panelSection(title: string, body: HTMLElement, extra = ""): HTMLElement {
  const section = element("section", `room-panel__section ${extra}`.trim());
  const heading = element("h2", "room-panel__heading");
  heading.textContent = title;
  section.append(heading, body);
  return section;
}

function rememberControls(toolbar: HTMLElement): Map<string, KeptControl> {
  const kept = new Map<string, KeptControl>();
  const counts = new Map<string, number>();
  for (const control of toolbar.querySelectorAll("select, input")) {
    if (!(control instanceof HTMLSelectElement || control instanceof HTMLInputElement)) continue;
    const key = controlKey(control, counts);
    if (key === null) continue;
    kept.set(key, {
      value: control.value,
      focused: document.activeElement === control,
    });
  }
  return kept;
}

function restoreControls(toolbar: HTMLElement, kept: Map<string, KeptControl>): void {
  const counts = new Map<string, number>();
  for (const control of toolbar.querySelectorAll("select, input")) {
    if (!(control instanceof HTMLSelectElement || control instanceof HTMLInputElement)) continue;
    const key = controlKey(control, counts);
    const before = key === null ? undefined : kept.get(key);
    if (before === undefined) continue;
    if (control.value !== before.value) {
      control.value = before.value;
      // No control is told it changed, so none acts on its own.
    }
    if (before.focused) control.focus({ preventScroll: true });
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

/** A per-seat zone's own name, without the seat the engine adds after " · ". */
function handName(label: string): string {
  const cut = label.lastIndexOf(" · ");
  return cut === -1 ? label : label.slice(0, cut);
}

function element(tag: string, className: string, text?: string): HTMLElement {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
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
