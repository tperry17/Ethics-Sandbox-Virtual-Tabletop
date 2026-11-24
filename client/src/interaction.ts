/**
 * Everything a person can do with their hands, turned into intents.
 *
 * Every gesture is shown locally at once - a card lifts and follows the
 * pointer, a flipped card shows its back - and proposed to the server as an
 * intent. The local result is an override on the renderer, not a change to
 * the model: when the server agrees, its patches carry the truth and the
 * override is dropped; when it refuses, the override is dropped anyway and
 * the piece is seen to go back, with the server's sentence in a toast.
 *
 * Nothing here decides whether a move is legal. Which zone a piece is let
 * go over, or which piece it is dropped on, is input - where the hand was.
 * What that means is the server's to say.
 */

import { landingBesidePiles, stepPastPiles } from "./geometry.js";
import { newClientId } from "./intents.js";
import type { TableRenderer } from "./table.js";

/** How far a press must travel before it is a drag rather than a click. */
const DRAG_THRESHOLD_PX = 5;
/** A touch held this long on a piece on the table opens its menu. */
const LONG_PRESS_MS = 500;
/** A second tap on the same card in the hand this soon after the first turns it over. */
const DOUBLE_TAP_MS = 350;
/** ...if it lands this close to the first, in CSS pixels. */
const DOUBLE_TAP_PX = 24;
/** A card in the hand held this long is lifted up close to be read. */
const PEEK_HOLD_MS = 450;
/** At most one move per piece this often while dragging; the server coalesces anyway. */
const MOVE_SEND_MS = 50;
/** How long the pointer rests on a piece before its keyboard hint appears. */
const HINT_DELAY_MS = 450;
/** One arrow-key press moves a piece this far, in world units. Shift moves five steps. */
export const GRID_STEP = 20;
const INK_WIDTH = 4;
const INK_MIN_STEP = 3;
const INK_SEND_MS = 40;
const CURSOR_SEND_MS = 100;

type Tool = "hand" | "pen" | "point";

interface Dragged {
  id: string;
  offsetX: number;
  offsetY: number;
  fromTray: boolean;
  lastSentAt: number;
  /** The server refused something about this piece's drag; it has already gone back. */
  refused: boolean;
}

/** What letting go of one dragged piece will do; see `planDrop`. */
type DropPlan =
  | { kind: "hand"; zone: string }
  | { kind: "stack"; onto: string }
  | { kind: "join"; zone: string }
  | { kind: "zone"; zone: string; x: number; y: number }
  | { kind: "move"; x: number; y: number }
  | { kind: "none" };

type Gesture =
  | {
      kind: "press";
      pointerId: number;
      pointerType: string;
      startX: number;
      startY: number;
      pieceId: string | null;
      fromTray: boolean;
      additive: boolean;
      /** Shift was held: a click adds the piece to the selection or takes it out, and never turns it over. */
      shift: boolean;
      timer: number | null;
    }
  | { kind: "drag"; pointerId: number; pieces: Dragged[] }
  | {
      kind: "marquee";
      pointerId: number;
      startX: number;
      startY: number;
      box: HTMLElement;
      additive: boolean;
      base: Set<string>;
    }
  | {
      kind: "pen";
      pointerId: number;
      strokeId: string;
      colour: string;
      points: Array<[number, number]>;
      lastSentAt: number;
      refused: boolean;
    }
  | { kind: "pan"; pointerId: number; lastX: number; lastY: number }
  | { kind: "peek"; pointerId: number; pieceId: string }
  | { kind: "consumed"; pointerId: number };

export class InteractionController {
  private gesture: Gesture | null = null;
  /**
   * The last tap of a finger on a card in the hand, so a second tap can turn
   * it over as a double-click does. A card in the hand is never selected, so
   * it cannot be turned over by a tap on it while selected, as one on the
   * table is. Browsers do not reliably make a double-click from two taps on a
   * table that takes every touch itself (touch-action: none).
   */
  private lastTap: { pieceId: string; at: number; x: number; y: number } | null = null;
  /** When a double tap last turned something over, so a double-click from the same taps does not turn it back. */
  private lastTapFlipAt = -Infinity;
  private tool: Tool = "hand";
  private readonly touches = new Set<number>();
  private lastCursorAt = 0;
  /** The release that settles each keyboard-moved piece, so only the last one clears it. */
  private readonly keyboardSettle = new Map<string, string>();
  private toolButtons: { point: HTMLButtonElement; pen: HTMLButtonElement } | null = null;
  /** The Draw menu's own button, marked while the pen is in hand. */
  private drawSummary: HTMLElement | null = null;
  private clearAllButton: HTMLButtonElement | null = null;
  private facilitatorButton: HTMLButtonElement | null = null;
  /** The piece under a mouse pointer, which the single-key shortcuts act on first. */
  private hovered: string | null = null;
  private readonly hint: HTMLElement;
  private hintTimer: number | null = null;
  /** A close look is open because Space is held down; letting go closes it. */
  private spaceLook = false;

  constructor(private readonly table: TableRenderer) {
    this.hint = document.createElement("div");
    this.hint.className = "piece-hint";
    this.hint.hidden = true;
    // A reminder for the mouse; what the keys do is also on the piece's menu,
    // and a screen reader is not read the hint on every piece it passes.
    this.hint.setAttribute("aria-hidden", "true");
  }

  attach(): void {
    const root = this.root;
    root.addEventListener("pointerdown", this.onPointerDown);
    root.addEventListener("pointermove", this.onPointerMove);
    root.addEventListener("pointerup", this.onPointerUp);
    root.addEventListener("pointercancel", this.onPointerCancel);
    root.addEventListener("dblclick", this.onDoubleClick);
    root.addEventListener("contextmenu", this.onContextMenu);
    root.addEventListener("pointerover", this.onPointerOver);
    root.addEventListener("pointerleave", this.onPointerLeave);
    root.append(this.hint);
    window.addEventListener("keydown", this.onKeyDown);
    window.addEventListener("keyup", this.onKeyUp);
    // A look held open by Space ends if the window loses the key-up.
    window.addEventListener("blur", this.endSpaceLook);
    document.addEventListener("pointerdown", this.onDocumentPointerDown, true);
    this.table.listener = {
      onOwnPeek: (pieceId) => this.onOwnPeek(pieceId),
      onSnapshot: () => this.syncTools(),
    };
    this.buildTools();
    // A snapshot may have arrived before this listener was set.
    this.syncTools();
  }

  private get root(): HTMLElement {
    return this.table.surfaceElement.parentElement ?? this.table.surfaceElement;
  }

  private get model() {
    return this.table.model;
  }

  // -- tools ---------------------------------------------------------------------------

  private buildTools(): void {
    // The pen, Point and clearing ink are in a Draw menu beside the Table
    // buttons, closed until opened.
    const draw = document.createElement("details");
    draw.className = "draw-menu";
    const summary = document.createElement("summary");
    summary.className = "button button--secondary button--sm";
    summary.textContent = "Draw";
    const panel = document.createElement("div");
    panel.className = "draw-menu__panel";
    panel.setAttribute("role", "group");
    panel.setAttribute("aria-label", "Drawing");
    const pen = toolButton("Pen", "Draw on the table in your colour.");
    pen.addEventListener("click", () => {
      this.setTool(this.tool === "pen" ? "hand" : "pen");
      // Out of the way of the table, which is what the pen is for.
      draw.open = false;
    });
    const point = toolButton("Point", "Point at a spot on the table. Alt-click also points.");
    point.addEventListener("click", () => {
      this.setTool(this.tool === "point" ? "hand" : "point");
      // Out of the way of the table, which is where the point goes.
      draw.open = false;
    });
    const clearMine = plainButton("Clear my ink", () => {
      this.table.intents.send("clear_ink", { everyone: false });
    });
    // The room's own "Clear ink" button, when it has one, so its question
    // and its announcement come with it; otherwise the plain intent.
    const clearAll = plainButton("Clear all ink", () => {
      const macro = this.table.roomClearInk;
      if (macro !== null) this.table.pressMacro(macro);
      else this.table.intents.send("clear_ink", { everyone: true });
    });
    clearAll.hidden = true;
    panel.append(pen, point, clearMine, clearAll);
    draw.append(summary, panel);
    this.table.drawArea.replaceChildren(draw);
    this.drawSummary = summary;

    const facilitator = plainButton("Become facilitator", () => {
      const holding = this.model.you?.is_facilitator === true;
      this.table.intents.send(holding ? "release_facilitator" : "take_facilitator", {});
    });
    facilitator.hidden = true;
    // "Become facilitator" belongs with the room, in its top bar, if the page has one.
    const bar = document.getElementById("room-bar-actions");
    if (bar !== null) bar.append(facilitator);
    else this.table.toolArea.append(facilitator);
    this.toolButtons = { point, pen };
    this.clearAllButton = clearAll;
    this.facilitatorButton = facilitator;
  }

  /** Show the facilitator's own tools to the facilitator. Whether they work is the server's call. */
  private syncTools(): void {
    if (this.clearAllButton !== null) {
      this.clearAllButton.hidden = this.model.you?.is_facilitator !== true;
    }
    if (this.facilitatorButton !== null) {
      // Whether it works is the server's call; this only offers it while it could.
      const holding = this.model.you?.is_facilitator === true;
      const taken = [...this.model.seats.values()].some((seat) => seat.is_facilitator);
      this.facilitatorButton.hidden = this.model.seatId === null || (taken && !holding);
      this.facilitatorButton.textContent = holding ? "Hand back facilitator" : "Become facilitator";
    }
    this.cancelGesture();
  }

  private setTool(tool: Tool): void {
    this.tool = tool;
    if (this.toolButtons !== null) {
      this.toolButtons.point.setAttribute("aria-pressed", String(tool === "point"));
      this.toolButtons.pen.setAttribute("aria-pressed", String(tool === "pen"));
    }
    if (this.drawSummary !== null) {
      this.drawSummary.textContent =
        tool === "pen" ? "Draw: pen" : tool === "point" ? "Draw: point" : "Draw";
      this.drawSummary.classList.toggle("is-active", tool !== "hand");
    }
    this.table.surfaceElement.dataset.tool = tool;
  }

  // -- pointer -------------------------------------------------------------------------

  private onDocumentPointerDown = (event: PointerEvent): void => {
    const target = event.target;
    if (!(target instanceof Node)) return;
    if (this.table.menu.isOpen && !this.table.menu.element.contains(target)) {
      this.table.menu.close(false);
    }
  };

  private onPointerDown = (event: PointerEvent): void => {
    this.hideHint();
    const target = event.target;
    if (!(target instanceof Element)) return;
    // The table's own controls (its menus' summaries and panels included)
    // are not the table: a press there never starts a drag, a stroke or a point.
    if (target.closest("button, summary, .tabletop__controls, .table-menu, .reveals, .peek, input, a")) return;
    if (event.pointerType === "touch") {
      this.touches.add(event.pointerId);
      // A second finger means pan or pinch, which the camera owns.
      if (this.touches.size > 1) {
        this.cancelGesture();
        return;
      }
    }
    // The middle button pans the view, which the camera owns (viewport-input.ts).
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (this.table.surfaceElement.classList.contains("is-pannable")) return;
    if (this.gesture !== null) return;

    const [x, y] = this.table.clientToWorld(event.clientX, event.clientY);
    if (this.tool === "point" || event.altKey) {
      event.preventDefault();
      this.table.intents.send("point", { x, y });
      if (this.tool === "point") this.setTool("hand");
      return;
    }
    if (this.tool === "pen" && this.table.surfaceElement.contains(target)) {
      event.preventDefault();
      this.beginStroke(event, x, y);
      return;
    }

    const pieceNode = target.closest<HTMLElement>("[data-piece-id]");
    const pieceId = pieceNode?.dataset.pieceId ?? null;
    if (pieceId === null && !this.table.surfaceElement.contains(target)) return;
    if (pieceNode !== null && pieceNode !== undefined) {
      pieceNode.focus({ preventScroll: true });
    }
    const fromTray = pieceId !== null && this.table.isInTray(pieceId);
    const press: Gesture = {
      kind: "press",
      pointerId: event.pointerId,
      pointerType: event.pointerType,
      startX: event.clientX,
      startY: event.clientY,
      pieceId,
      fromTray,
      // A finger has no Shift key: tapping a piece toggles it in the selection,
      // tapping empty table clears it.
      additive: event.shiftKey || (event.pointerType === "touch" && pieceId !== null),
      shift: event.shiftKey,
      timer: null,
    };
    if (pieceId !== null && fromTray) {
      press.timer = window.setTimeout(() => this.beginPeek(pieceId, event.pointerId), PEEK_HOLD_MS);
    } else if (pieceId !== null && event.pointerType === "touch") {
      press.timer = window.setTimeout(() => {
        this.gesture = { kind: "consumed", pointerId: event.pointerId };
        this.openMenu(pieceId, event.clientX, event.clientY);
      }, LONG_PRESS_MS);
    }
    // No pointer capture yet: a plain click or double-click must still be
    // delivered to the piece it landed on. Capture starts with a drag.
    this.gesture = press;
  };

  private onPointerMove = (event: PointerEvent): void => {
    this.sendCursor(event);
    const gesture = this.gesture;
    if (gesture === null || gesture.pointerId !== event.pointerId) return;

    if (gesture.kind === "press") {
      const distance = Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY);
      if (distance < DRAG_THRESHOLD_PX) return;
      if (gesture.timer !== null) window.clearTimeout(gesture.timer);
      if (gesture.pieceId !== null) this.beginDrag(gesture.pieceId, gesture, event);
      // On empty table the mouse's main button draws a selection box; with
      // Shift it pans instead, for a trackpad that has no middle button. A
      // finger or a pen pans.
      else if (gesture.pointerType === "mouse" && !gesture.shift) this.beginMarquee(gesture, event);
      else this.beginPan(gesture, event);
      return;
    }
    if (gesture.kind === "drag") this.continueDrag(gesture.pieces, event);
    else if (gesture.kind === "pan") this.continuePan(gesture, event);
    else if (gesture.kind === "marquee") this.continueMarquee(gesture, event);
    else if (gesture.kind === "pen") this.continueStroke(gesture, event);
  };

  private onPointerUp = (event: PointerEvent): void => {
    this.touches.delete(event.pointerId);
    const gesture = this.gesture;
    if (gesture === null || gesture.pointerId !== event.pointerId) return;
    this.gesture = null;

    if (gesture.kind === "press") {
      if (gesture.timer !== null) window.clearTimeout(gesture.timer);
      if (gesture.pointerType === "touch" && gesture.pieceId !== null && gesture.fromTray) {
        this.trayTap(gesture.pieceId, event);
        return;
      }
      this.lastTap = null;
      this.click(gesture.pieceId, gesture.additive, gesture.shift);
      return;
    }
    if (gesture.kind === "drag") this.finishDrag(gesture.pieces, event);
    else if (gesture.kind === "marquee") this.endMarquee(gesture);
    else if (gesture.kind === "pen") this.finishStroke(gesture);
    else if (gesture.kind === "peek") this.closePeek();
  };

  private onPointerCancel = (event: PointerEvent): void => {
    this.touches.delete(event.pointerId);
    if (this.gesture?.pointerId === event.pointerId) this.cancelGesture();
  };

  /** Abandon whatever is in progress, putting back anything that was picked up. */
  private cancelGesture(): void {
    const gesture = this.gesture;
    this.gesture = null;
    if (gesture === null) return;
    if (gesture.kind === "press" && gesture.timer !== null) window.clearTimeout(gesture.timer);
    if (gesture.kind === "marquee") this.endMarquee(gesture);
    if (gesture.kind === "peek") this.closePeek();
    if (gesture.kind === "pen") this.finishStroke(gesture);
    if (gesture.kind === "drag") {
      for (const piece of gesture.pieces) {
        if (piece.refused) continue;
        this.release(piece.id, true);
      }
      this.endDragChrome();
    }
  }

  /** A finger's tap on a card in the hand: a second on the same card soon after turns it over. */
  private trayTap(pieceId: string, event: PointerEvent): void {
    const now = performance.now();
    const last = this.lastTap;
    if (
      last !== null &&
      last.pieceId === pieceId &&
      now - last.at <= DOUBLE_TAP_MS &&
      Math.hypot(event.clientX - last.x, event.clientY - last.y) <= DOUBLE_TAP_PX
    ) {
      this.lastTap = null;
      this.lastTapFlipAt = now;
      this.turnOver(pieceId);
      return;
    }
    this.lastTap = { pieceId, at: now, x: event.clientX, y: event.clientY };
  }

  /**
   * A click or a tap on the table. On a piece that is not selected, the
   * first always selects it: alone with a mouse, added to the selection with
   * a finger. On a piece already selected, it turns it over (the selection
   * with it), or writes on a note or token, as a double-click once did.
   * A card still in a deck is not turned over by a click, alone or as part
   * of the selection: the click only selects it. (The server refuses to turn
   * a card face up in a deck however it is asked; a click does not ask, so
   * it raises no refusal.) With Shift a click only adds the piece to the
   * selection or takes it out.
   */
  private click(pieceId: string | null, additive: boolean, shift: boolean): void {
    if (pieceId !== null && !shift && this.table.selected.has(pieceId) && !this.table.isInTray(pieceId)) {
      if (this.inDeck(pieceId)) return;
      const piece = this.model.pieces.get(pieceId);
      if (piece?.kind === "note" || piece?.kind === "token") {
        this.write(pieceId, piece.kind);
        return;
      }
      this.flip(this.targetsFor(pieceId).filter((id) => !this.inDeck(id)));
      return;
    }
    this.select(pieceId, additive);
  }

  /** Whether a piece lies in a zone of kind deck, as drawn: where it is, not what may be done to it. */
  private inDeck(pieceId: string): boolean {
    const piece = this.model.pieces.get(pieceId);
    return piece !== undefined && this.model.zones.get(piece.zone_id)?.kind === "deck";
  }

  /** Select `pieceId` alone, or with `additive` add it to the selection or take it out; null clears it. */
  private select(pieceId: string | null, additive: boolean): void {
    if (pieceId === null) {
      if (!additive) this.table.setSelection([]);
      return;
    }
    if (this.table.isInTray(pieceId)) return;
    if (!additive) {
      this.table.setSelection([pieceId]);
      return;
    }
    const next = new Set(this.table.selected);
    if (next.has(pieceId)) next.delete(pieceId);
    else next.add(pieceId);
    this.table.setSelection(next);
  }

  private sendCursor(event: PointerEvent): void {
    if (this.model.seatId === null) return;
    const now = performance.now();
    if (now - this.lastCursorAt < CURSOR_SEND_MS) return;
    if (!this.table.surfaceElement.contains(event.target as Node)) return;
    this.lastCursorAt = now;
    const [x, y] = this.table.clientToWorld(event.clientX, event.clientY);
    this.table.send({ type: "cursor", x, y });
  }

  // -- dragging ------------------------------------------------------------------------

  private beginDrag(
    pieceId: string,
    press: Extract<Gesture, { kind: "press" }>,
    event: PointerEvent,
  ): void {
    const fromTray = press.fromTray;
    let ids: string[];
    if (fromTray) {
      ids = [pieceId];
    } else {
      if (!this.table.selected.has(pieceId)) this.table.setSelection([pieceId]);
      ids = [...this.table.selected].filter((id) => !this.table.isInTray(id));
    }
    this.root.setPointerCapture?.(press.pointerId);
    // Offsets are taken from where the press began, so the spot that was
    // grabbed stays under the pointer for the whole drag.
    const [x, y] = this.table.clientToWorld(press.startX, press.startY);
    const pieces: Dragged[] = [];
    for (const id of ids) {
      const piece = this.model.pieces.get(id);
      if (piece === undefined) continue;
      const at = fromTray ? [x, y] : (this.table.visualPositionOf(id) ?? [piece.x, piece.y]);
      const dragged: Dragged = {
        id,
        offsetX: x - at[0]!,
        offsetY: y - at[1]!,
        fromTray,
        lastSentAt: 0,
        refused: false,
      };
      pieces.push(dragged);
      this.table.setOverride(id, { x: at[0]!, y: at[1]!, lifted: true });
      this.table.intents.send("grab", { piece_id: id }, {
        // Never picked up, so there is nothing to put down.
        onReject: () => this.refuse(dragged, false),
      });
    }
    this.gesture = { kind: "drag", pointerId: press.pointerId, pieces };
    this.table.interacting = true;
    this.continueDrag(pieces, event);
  }

  private continueDrag(pieces: Dragged[], event: PointerEvent): void {
    const [x, y] = this.table.clientToWorld(event.clientX, event.clientY);
    const now = performance.now();
    for (const piece of pieces) {
      if (piece.refused) continue;
      const px = x - piece.offsetX;
      const py = y - piece.offsetY;
      this.table.setOverride(piece.id, { x: px, y: py });
      // A card lifted out of the hand has no business moving about inside
      // the hand zone on everyone else's screen; it moves once, on release.
      if (!piece.fromTray && now - piece.lastSentAt >= MOVE_SEND_MS) {
        piece.lastSentAt = now;
        this.table.intents.send("move", { piece_id: piece.id, x: px, y: py }, {
          onReject: () => this.refuse(piece),
        });
      }
    }
    this.showDropTargets(pieces, event);
  }

  /**
   * What letting go here would do with one piece: the single decision that
   * both the highlight while dragging and the release use, so that what is
   * lit up is what happens.
   *
   * Over a pile, where the hand opened does not decide: how much of the piece
   * lies over the pile does. More than half, and it goes into the pile;
   * otherwise it is put down clear of it. So a pile, or a card in one, under
   * the pointer counts as the table beneath it.
   */
  private planDrop(piece: Dragged, count: number, event: PointerEvent): DropPlan {
    const [x, y] = this.table.clientToWorld(event.clientX, event.clientY);
    const truth = this.model.pieces.get(piece.id);
    if (truth === undefined) return { kind: "none" };
    const hand = this.table.myHandZoneId();
    if (hand !== null && this.table.overTray(event.clientX, event.clientY)) {
      return { kind: "hand", zone: hand };
    }
    const pointedAt = count === 1 ? this.stackTargetAt(piece.id, event) : null;
    const pointedPile =
      pointedAt !== null && this.table.isPile(this.model.pieces.get(pointedAt)?.zone_id);
    if (pointedAt !== null && !pointedPile) return { kind: "stack", onto: pointedAt };
    let zoneUnder = this.table.zoneAtWorld(x, y);
    if (zoneUnder !== null && this.table.isPile(zoneUnder)) zoneUnder = this.table.zoneAtWorld(x, y, true);
    // The table has no edge: over no zone at all is on the table.
    zoneUnder ??= this.table.tableFor(truth.zone_id);

    let px = x - piece.offsetX;
    let py = y - piece.offsetY;
    const landing =
      zoneUnder !== null && zoneUnder !== truth.zone_id
        ? zoneUnder
        : piece.fromTray ? null : truth.zone_id;
    if (landing !== null && this.model.zones.get(landing)?.layout === "free") {
      const piles = this.table.piles(landing);
      const [width, height] = this.table.pieceSizeOf(piece.id);
      const spot = landingBesidePiles(
        px, py, width, height, piles.map((pile) => pile.bounds),
        truth.kind === "card" || truth.kind === "tile",
      );
      if ("join" in spot) return { kind: "join", zone: piles[spot.join]!.id };
      px = spot.x;
      py = spot.y;
    }
    if (zoneUnder !== null && zoneUnder !== truth.zone_id) {
      return { kind: "zone", zone: zoneUnder, x: px, y: py };
    }
    if (!piece.fromTray) return { kind: "move", x: px, y: py };
    // Lifted out of the hand and let go nowhere in particular: back it goes.
    return { kind: "none" };
  }

  /** Light up where the pieces would go if let go now: exactly what the release will do. */
  private showDropTargets(pieces: Dragged[], event: PointerEvent): void {
    const live = pieces.filter((piece) => !piece.refused);
    const plan = live[0] === undefined ? { kind: "none" as const } : this.planDrop(live[0], live.length, event);
    this.table.setTrayTarget(plan.kind === "hand");
    this.table.setStackTarget(plan.kind === "stack" ? plan.onto : null);
    // The table itself is where anything let go lands by default, and it is
    // not drawn: it is never lit.
    const lit = plan.kind === "join" || plan.kind === "zone" ? plan.zone : null;
    this.table.setDropTarget(lit !== null && this.model.zones.get(lit)?.kind === "table" ? null : lit);
  }

  private stackTargetAt(draggedId: string, event: PointerEvent): string | null {
    const under = this.table.pieceIdAt(event.clientX, event.clientY);
    if (under === null || under === draggedId || this.table.isInTray(under)) return null;
    return under;
  }

  private finishDrag(pieces: Dragged[], event: PointerEvent): void {
    const live = pieces.filter((piece) => !piece.refused);
    for (const piece of live) {
      const truth = this.model.pieces.get(piece.id);
      if (truth === undefined) continue;
      const refuse = { onReject: () => this.refuse(piece) };
      const plan = this.planDrop(piece, live.length, event);
      switch (plan.kind) {
        case "hand":
          if (truth.zone_id !== plan.zone) {
            this.table.intents.send("move_to_zone", { piece_id: piece.id, zone_id: plan.zone }, refuse);
          }
          break;
        case "stack":
          this.table.intents.send("stack_onto", { piece_id: piece.id, onto_id: plan.onto }, refuse);
          break;
        case "join":
          this.table.intents.send("move_to_zone", { piece_id: piece.id, zone_id: plan.zone }, refuse);
          break;
        case "zone":
          // Show it where it will be, so it does not jump when the server agrees.
          this.table.setOverride(piece.id, { x: plan.x, y: plan.y });
          this.table.intents.send(
            "move_to_zone",
            { piece_id: piece.id, zone_id: plan.zone, x: plan.x, y: plan.y },
            refuse,
          );
          break;
        case "move":
          this.table.setOverride(piece.id, { x: plan.x, y: plan.y });
          this.table.intents.send("move", { piece_id: piece.id, x: plan.x, y: plan.y }, refuse);
          break;
        case "none":
          this.release(piece.id, false);
          this.table.clearOverride(piece.id, false);
          continue;
      }
      this.release(piece.id, false);
      this.announceDrop(
        piece.id,
        plan.kind === "hand" || plan.kind === "join" || plan.kind === "zone" ? plan.zone : null,
        plan.kind === "stack" ? plan.onto : null,
      );
    }
    this.endDragChrome();
  }

  /** Put a piece down. The override goes once the server confirms it - or refuses. */
  private release(pieceId: string, rollback: boolean): void {
    this.table.intents.send("release", { piece_id: pieceId }, {
      onAck: () => this.table.clearOverride(pieceId, rollback),
      onReject: () => this.table.clearOverride(pieceId, true),
    });
  }

  /**
   * The server said no to part of a drag: the piece goes back, now.
   *
   * If it had been picked up, it is put down too, rather than left held
   * until the server's own timeout lets go of it.
   */
  private refuse(piece: Dragged, putDown = true): void {
    if (piece.refused) return;
    piece.refused = true;
    this.table.clearOverride(piece.id, true);
    if (putDown && this.gesture?.kind === "drag" && this.gesture.pieces.includes(piece)) {
      this.table.intents.send("release", { piece_id: piece.id });
    }
  }

  private endDragChrome(): void {
    this.table.setDropTarget(null);
    this.table.setStackTarget(null);
    this.table.setTrayTarget(false);
    this.table.interacting = false;
  }

  private announceDrop(pieceId: string, zoneId: string | null, onto: string | null): void {
    const name = this.table.pieceLabel(pieceId);
    if (onto !== null) {
      this.table.announcer.announce(`${capital(name)} put on ${this.table.pieceLabel(onto)}.`);
      return;
    }
    if (zoneId !== null && zoneId === this.table.myHandZoneId()) {
      this.table.announcer.announce(`${capital(name)} taken into your hand.`);
    }
  }

  // -- panning across empty table -----------------------------------------------------

  /**
   * A finger or a pen dragged across empty table moves the view, and so does
   * the mouse's main button with Shift. Without Shift it draws a selection
   * box (see above); the middle button pans in viewport-input.ts.
   */
  private beginPan(press: Extract<Gesture, { kind: "press" }>, event: PointerEvent): void {
    this.root.setPointerCapture?.(press.pointerId);
    this.gesture = { kind: "pan", pointerId: press.pointerId, lastX: press.startX, lastY: press.startY };
    this.continuePan(this.gesture, event);
  }

  private continuePan(gesture: Extract<Gesture, { kind: "pan" }>, event: PointerEvent): void {
    this.table.panBy(event.clientX - gesture.lastX, event.clientY - gesture.lastY);
    gesture.lastX = event.clientX;
    gesture.lastY = event.clientY;
  }

  // -- marquee selection ---------------------------------------------------------------

  private beginMarquee(press: Extract<Gesture, { kind: "press" }>, event: PointerEvent): void {
    this.root.setPointerCapture?.(press.pointerId);
    // The press was not prevented (a click must still reach its target), so
    // the browser has begun selecting text: drop it, and select none while
    // the box is drawn, so labels and buttons are not lit up under it.
    window.getSelection()?.removeAllRanges();
    document.documentElement.classList.add("is-drawing-marquee");
    const box = document.createElement("div");
    box.className = "tabletop__marquee";
    this.table.surfaceElement.append(box);
    this.gesture = {
      kind: "marquee",
      pointerId: press.pointerId,
      startX: press.startX,
      startY: press.startY,
      box,
      additive: press.additive,
      base: press.additive ? new Set(this.table.selected) : new Set(),
    };
    this.continueMarquee(this.gesture, event);
  }

  private endMarquee(gesture: Extract<Gesture, { kind: "marquee" }>): void {
    gesture.box.remove();
    document.documentElement.classList.remove("is-drawing-marquee");
  }

  private continueMarquee(gesture: Extract<Gesture, { kind: "marquee" }>, event: PointerEvent): void {
    const surface = this.table.surfaceElement.getBoundingClientRect();
    const left = Math.min(gesture.startX, event.clientX);
    const top = Math.min(gesture.startY, event.clientY);
    const width = Math.abs(event.clientX - gesture.startX);
    const height = Math.abs(event.clientY - gesture.startY);
    gesture.box.style.transform = `translate(${left - surface.left}px, ${top - surface.top}px)`;
    gesture.box.style.width = `${width}px`;
    gesture.box.style.height = `${height}px`;

    const [ax, ay] = this.table.clientToWorld(left, top);
    const [bx, by] = this.table.clientToWorld(left + width, top + height);
    const chosen = new Set(gesture.base);
    for (const piece of this.model.pieces.values()) {
      if (this.table.isInTray(piece.id)) continue;
      const [px, py] = this.table.visualPositionOf(piece.id) ?? [piece.x, piece.y];
      if (px >= ax && px <= bx && py >= ay && py <= by) chosen.add(piece.id);
    }
    this.table.setSelection(chosen);
  }

  // -- a close look at your own card -------------------------------------------------

  private beginPeek(pieceId: string, pointerId: number): void {
    if (this.gesture?.kind !== "press" || this.gesture.pieceId !== pieceId) return;
    if (!this.openPeek(pieceId)) return;
    this.gesture = { kind: "peek", pointerId, pieceId };
    this.table.intents.send("peek", { piece_id: pieceId });
  }

  /** Lift a card up close. False if there is no face here to look at. */
  private openPeek(pieceId: string): boolean {
    const piece = this.model.pieces.get(pieceId);
    if (piece === undefined || piece.component_id === null) return false;
    const component = this.model.components.get(piece.component_id);
    if (component === undefined) return false;
    this.table.reveals.openPeek(pieceId, piece.kind, component, () => this.closePeek());
    return true;
  }

  private closePeek(): void {
    this.spaceLook = false;
    const pieceId = this.table.reveals.peekingAt;
    this.table.reveals.closePeek();
    if (pieceId !== null) this.table.pieceElement(pieceId)?.focus({ preventScroll: true });
  }

  /** The server confirmed a look chosen from the menu; open it, from the keyboard. */
  private onOwnPeek(pieceId: string): void {
    if (this.table.lookingFromMenu !== pieceId) return;
    this.table.lookingFromMenu = null;
    if (this.openPeek(pieceId)) this.table.reveals.focusPeek();
  }

  // -- hovering, and the hint that says what the keys do -------------------------------

  private onPointerOver = (event: PointerEvent): void => {
    if (event.pointerType === "touch") return;
    const node = (event.target as Element | null)?.closest<HTMLElement>("[data-piece-id]");
    const pieceId = node?.dataset.pieceId ?? null;
    if (pieceId === this.hovered) return;
    this.hovered = pieceId;
    this.hideHint();
    if (pieceId === null || node === null || node === undefined) return;
    this.hintTimer = window.setTimeout(() => this.showHint(pieceId, node), HINT_DELAY_MS);
  };

  private onPointerLeave = (): void => {
    this.hovered = null;
    this.hideHint();
  };

  /** The hovered piece, if it is still on the table. */
  private get hoveredPiece(): string | null {
    if (this.hovered === null || !this.model.pieces.has(this.hovered)) return null;
    return this.hovered;
  }

  private showHint(pieceId: string, node: HTMLElement): void {
    this.hintTimer = null;
    if (this.gesture !== null || this.hovered !== pieceId || this.table.menu.isOpen) return;
    const piece = this.model.pieces.get(pieceId);
    if (piece === undefined || (piece.kind !== "card" && piece.kind !== "tile")) return;
    // Which keys are worth mentioning, from what is drawn: whether the server
    // allows any of them is still the server's to say when one is pressed.
    const keys: Array<[string, string]> = [];
    const inDeck = this.model.zones.get(piece.zone_id)?.kind === "deck";
    if (piece.component_id !== null) keys.push(["Space", "hold to enlarge"]);
    // A face-down card in a deck is not turned over until it is off the deck.
    if (!(inDeck && piece.kind === "card" && !piece.face_up)) keys.push(["F", "turn over"]);
    if (inDeck) keys.push(["S", "shuffle"]);
    if (piece.locked) keys.push(["U", "unlock"]);
    else if (piece.kind === "tile") keys.push(["L", "lock"]);
    this.hint.replaceChildren();
    keys.forEach(([key, what], index) => {
      if (index > 0) this.hint.append(" · ");
      const kbd = document.createElement("kbd");
      kbd.textContent = key;
      this.hint.append(kbd, ` ${what}`);
    });
    const box = this.root.getBoundingClientRect();
    const rect = node.getBoundingClientRect();
    this.hint.hidden = false;
    const width = this.hint.offsetWidth;
    const left = Math.min(
      Math.max(rect.left + rect.width / 2 - box.left - width / 2, 8),
      Math.max(box.width - width - 8, 8),
    );
    // Below the piece when there is room, otherwise above it.
    const below = rect.bottom - box.top + 8;
    const top =
      below + this.hint.offsetHeight + 8 <= box.height
        ? below
        : Math.max(rect.top - box.top - this.hint.offsetHeight - 8, 8);
    this.hint.style.left = `${left}px`;
    this.hint.style.top = `${top}px`;
  }

  private hideHint(): void {
    if (this.hintTimer !== null) window.clearTimeout(this.hintTimer);
    this.hintTimer = null;
    this.hint.hidden = true;
  }

  // -- ink -----------------------------------------------------------------------------

  private beginStroke(event: PointerEvent, x: number, y: number): void {
    const seat = this.model.seatId;
    if (seat === null) return;
    const strokeId = newClientId();
    const colour = this.table.seatColour(seat);
    const gesture: Extract<Gesture, { kind: "pen" }> = {
      kind: "pen",
      pointerId: event.pointerId,
      strokeId,
      colour,
      points: [[x, y]],
      lastSentAt: performance.now(),
      refused: false,
    };
    this.gesture = gesture;
    this.root.setPointerCapture?.(event.pointerId);
    this.table.intents.send(
      "ink_begin",
      { stroke_id: strokeId, colour, width: INK_WIDTH, x, y },
      {
        onReject: () => {
          gesture.refused = true;
          this.table.setDraftStroke(null);
        },
      },
    );
    this.drawDraft(gesture);
  }

  private continueStroke(gesture: Extract<Gesture, { kind: "pen" }>, event: PointerEvent): void {
    if (gesture.refused) return;
    const [x, y] = this.table.clientToWorld(event.clientX, event.clientY);
    const [lastX, lastY] = gesture.points.at(-1)!;
    if (Math.hypot(x - lastX, y - lastY) < INK_MIN_STEP) return;
    gesture.points.push([x, y]);
    this.drawDraft(gesture);
    const now = performance.now();
    if (now - gesture.lastSentAt < INK_SEND_MS) return;
    gesture.lastSentAt = now;
    this.table.intents.send("ink_append", { stroke_id: gesture.strokeId, x, y });
  }

  private finishStroke(gesture: Extract<Gesture, { kind: "pen" }>): void {
    if (gesture.refused) return;
    // The last point always reaches the server, even if it came too soon after the one before.
    const [x, y] = gesture.points.at(-1)!;
    if (gesture.points.length > 1) {
      this.table.intents.send("ink_append", { stroke_id: gesture.strokeId, x, y });
    }
    this.table.intents.send(
      "ink_end",
      { stroke_id: gesture.strokeId },
      {
        onAck: () => this.table.setDraftStroke(null),
        onReject: () => this.table.setDraftStroke(null),
      },
    );
  }

  private drawDraft(gesture: Extract<Gesture, { kind: "pen" }>): void {
    this.table.setDraftStroke({
      id: gesture.strokeId,
      seat_id: this.model.seatId ?? "",
      colour: gesture.colour,
      width: INK_WIDTH,
      points: gesture.points,
    });
  }

  // -- flip, rotate, menus -------------------------------------------------------------

  private onDoubleClick = (event: MouseEvent): void => {
    const node = (event.target as Element | null)?.closest<HTMLElement>("[data-piece-id]");
    const pieceId = node?.dataset.pieceId;
    if (pieceId === undefined) return;
    event.preventDefault();
    // On the table, the second click of a double-click has already turned
    // the piece over: it landed on a selected piece. Only a card in the hand,
    // which is never selected, is turned over by a double-click.
    if (!this.table.isInTray(pieceId)) return;
    // The same two taps, already turned over by the double tap.
    if (performance.now() - this.lastTapFlipAt < 1000) return;
    this.turnOver(pieceId);
  };

  /** What a double-click or double tap on a card in the hand does: write on a note or token, turn anything else over. */
  private turnOver(pieceId: string): void {
    const piece = this.model.pieces.get(pieceId);
    if (piece?.kind === "note" || piece?.kind === "token") {
      this.write(pieceId, piece.kind);
      return;
    }
    this.flip(this.targetsFor(pieceId));
  }

  /** Ask what to write on a note or a token. The server judges whether it may be. */
  private write(pieceId: string, kind: "note" | "token" = "note"): void {
    const current = this.model.pieces.get(pieceId)?.text ?? "";
    const question = kind === "token" ? "One word or number for this token:" : "Write on this note:";
    const text = window.prompt(question, current);
    if (text === null) return;
    this.table.intents.send("set_text", { piece_id: pieceId, text }, this.settles(pieceId));
    this.table.announcer.announce(kind === "token" ? "Token written on." : "Note written on.");
  }

  private onContextMenu = (event: MouseEvent): void => {
    const node = (event.target as Element | null)?.closest<HTMLElement>("[data-piece-id]");
    const pieceId = node?.dataset.pieceId;
    if (pieceId === undefined) return;
    event.preventDefault();
    if (this.gesture?.kind === "press" && this.gesture.timer !== null) {
      window.clearTimeout(this.gesture.timer);
    }
    this.gesture = null;
    this.openMenu(pieceId, event.clientX, event.clientY);
  };

  private openMenu(pieceId: string, clientX: number, clientY: number): void {
    this.table.menu.open(
      pieceId,
      clientX,
      clientY,
      this.table.pieceLabel(pieceId),
      this.table.pieceElement(pieceId),
    );
  }

  /** The pieces a gesture on `pieceId` applies to: the selection, if it is part of it. */
  private targetsFor(pieceId: string): string[] {
    if (this.table.selected.has(pieceId)) return [...this.table.selected];
    return [pieceId];
  }

  private flip(ids: string[]): void {
    for (const id of ids) {
      const piece = this.model.pieces.get(id);
      if (piece === undefined) continue;
      // Only a face being hidden can be shown in advance: a face being
      // turned up is not known here until the server sends it.
      // A tile's other side is public and already here, so it can be shown either way.
      if (piece.kind === "tile") this.table.setOverride(id, { turned: true });
      else if (piece.component_id !== null) this.table.setOverride(id, { hideFace: true });
      this.table.intents.send("flip", { piece_id: id }, this.settles(id));
    }
    if (ids.length === 1) {
      this.table.announcer.announce(`${capital(this.table.pieceLabel(ids[0]!))} turned over.`);
    } else if (ids.length > 1) {
      this.table.announcer.announce(`${ids.length} pieces turned over.`);
    }
  }

  private rotate(ids: string[], degrees: number): void {
    for (const id of ids) {
      const piece = this.model.pieces.get(id);
      if (piece === undefined) continue;
      const from = this.table.overrideOf(id)?.rotation ?? piece.rotation;
      this.table.setOverride(id, { rotation: (((from + degrees) % 360) + 360) % 360 });
      this.table.intents.send("rotate", { piece_id: id, degrees }, this.settles(id));
    }
    const way = degrees > 0 ? "clockwise" : "anticlockwise";
    if (ids.length === 1) {
      this.table.announcer.announce(`${capital(this.table.pieceLabel(ids[0]!))} rotated ${way}.`);
    }
  }

  private lock(ids: string[], locked: boolean): void {
    for (const id of ids) {
      this.table.intents.send(locked ? "lock" : "unlock", { piece_id: id });
    }
    const what = locked ? "locked" : "unlocked";
    if (ids.length === 1) {
      this.table.announcer.announce(`${capital(this.table.pieceLabel(ids[0]!))} ${what}.`);
    } else if (ids.length > 1) {
      this.table.announcer.announce(`${ids.length} pieces ${what}.`);
    }
  }

  /**
   * Shuffle the deck `pieceId` lies in. Whether there is one to shuffle is
   * the menu's question, so this asks it and sends the menu's own entry.
   */
  private shuffle(pieceId: string): void {
    this.table.menu.ask(pieceId, (items) => {
      const entry = items.find((item) => item.id === "shuffle");
      if (entry === undefined) {
        this.table.notice("There is no deck here to shuffle.", "info");
        return;
      }
      this.table.chooseMenuItem(entry, pieceId);
      this.table.announcer.announce("Deck shuffled.");
    });
  }

  /** Callbacks that drop a piece's override once the server answers. */
  private settles(id: string): { onAck: () => void; onReject: () => void } {
    return {
      onAck: () => this.table.clearOverride(id, false),
      onReject: () => this.table.clearOverride(id, true),
    };
  }

  // -- the keyboard --------------------------------------------------------------------

  private onKeyDown = (event: KeyboardEvent): void => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.closest(".table-menu") || isTyping(target)) return;
    // With the pointer resting on a piece, or a close look open, the
    // single-key shortcuts are for the table wherever focus was left - on a
    // button just pressed in the side panel, say.
    const pointing = this.hoveredPiece !== null || this.table.reveals.peekingAt !== null;
    const plain = !(event.ctrlKey || event.metaKey || event.altKey);
    if (pointing && plain && this.shortcut(event, target)) return;
    // Otherwise keys belong to the table when focus is on it, or on nothing at all;
    // never while someone is typing, or using a control elsewhere on the page.
    const onTable = this.root.contains(target);
    if (!onTable && target !== document.body) return;
    if (isTyping(target) || (target instanceof HTMLButtonElement && event.key !== "Escape")) return;
    if (event.key === "Escape") {
      if (this.table.reveals.peekingAt !== null) {
        this.closePeek();
      } else if (this.gesture !== null) {
        this.cancelGesture();
      } else {
        this.table.setSelection([]);
        this.setTool("hand");
      }
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (this.shortcut(event, target)) return;
    const pieceId = target.dataset.pieceId;
    if (pieceId === undefined) {
      // Nothing focused, but something selected: the selection is what R turns.
      const selected = [...this.table.selected];
      if (selected.length === 0) return;
      if (event.key === "r" || event.key === "R") {
        event.preventDefault();
        this.rotate(selected, event.shiftKey ? -90 : 90);
      } else if (event.key === "Enter") {
        event.preventDefault();
        this.flip(selected);
      }
      return;
    }
    const ids = this.targetsFor(pieceId);

    const step = event.shiftKey ? GRID_STEP * 5 : GRID_STEP;
    const arrows: Record<string, [number, number, string]> = {
      ArrowLeft: [-step, 0, "left"],
      ArrowRight: [step, 0, "right"],
      ArrowUp: [0, -step, "up"],
      ArrowDown: [0, step, "down"],
    };
    const arrow = arrows[event.key];
    if (arrow !== undefined) {
      event.preventDefault();
      this.nudge(ids, arrow[0], arrow[1], arrow[2]);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      this.flip(ids);
      return;
    }
    if (event.key === "x" || event.key === "X") {
      // Select, as a click does: X picks this piece alone, Shift-X adds it
      // to (or takes it from) the selection. Offers use the selection.
      event.preventDefault();
      this.select(pieceId, event.shiftKey);
      const count = this.table.selected.size;
      this.table.announcer.announce(
        this.table.selected.has(pieceId)
          ? `${capital(this.table.pieceLabel(pieceId))} selected. ${count} selected.`
          : `${capital(this.table.pieceLabel(pieceId))} not selected. ${count} selected.`,
      );
      return;
    }
    if (event.key === "r" || event.key === "R") {
      event.preventDefault();
      this.rotate(ids, event.shiftKey ? -90 : 90);
      return;
    }
    if (event.key === "ContextMenu" || event.key === "m" || (event.key === "F10" && event.shiftKey)) {
      event.preventDefault();
      const at = this.table.clientPositionOf(pieceId) ?? [0, 0];
      this.openMenu(pieceId, at[0], at[1]);
      return;
    }
    if (event.key === "p") {
      event.preventDefault();
      const piece = this.model.pieces.get(pieceId);
      if (piece !== undefined && !this.table.isInTray(pieceId)) {
        this.table.intents.send("point", { x: piece.x, y: piece.y });
      }
    }
  };

  private onKeyUp = (event: KeyboardEvent): void => {
    if (event.key === " ") this.endSpaceLook();
  };

  private endSpaceLook = (): void => {
    if (!this.spaceLook) return;
    this.spaceLook = false;
    if (this.table.reveals.peekingAt !== null) this.closePeek();
  };

  /**
   * F, L, U, S and Space: the keys that act on the piece under the pointer
   * first, then on the focused piece, then on the selection. True if the key
   * was one of them and has been used.
   */
  private shortcut(event: KeyboardEvent, target: HTMLElement): boolean {
    this.hideHint();
    if (event.key === " " && this.spaceLook) {
      // Space is being held: the look stays open until it is let go.
      event.preventDefault();
      return true;
    }
    // The single-letter keys act on the piece under the pointer first, then
    // on the focused piece, then on the selection.
    const hovered = this.hoveredPiece;
    const subject = hovered ?? target.dataset.pieceId ?? null;
    const subjects = subject !== null ? this.targetsFor(subject) : [...this.table.selected];
    const letter = event.key.length === 1 ? event.key.toLowerCase() : "";
    if (letter === "f" && subjects.length > 0) {
      event.preventDefault();
      this.flip(subjects);
      return true;
    }
    if ((letter === "l" || letter === "u") && subjects.length > 0) {
      event.preventDefault();
      this.lock(subjects, letter === "l");
      return true;
    }
    if (letter === "s" && subject !== null) {
      event.preventDefault();
      this.shuffle(subject);
      return true;
    }
    if (event.key === " " && subject !== null && this.openPeek(subject)) {
      // A close look at the card, for as long as Space is held down.
      event.preventDefault();
      this.spaceLook = true;
      this.table.intents.send("peek", { piece_id: subject });
      return true;
    }
    return false;
  }

  /** Move pieces by a grid step: one move and one release each, settled on the release. */
  private nudge(ids: string[], dx: number, dy: number, way: string): void {
    const moved: string[] = [];
    for (const id of ids) {
      if (this.table.isInTray(id)) continue;
      const piece = this.model.pieces.get(id);
      if (piece === undefined) continue;
      const override = this.table.overrideOf(id);
      let x = (override?.x ?? piece.x) + dx;
      let y = (override?.y ?? piece.y) + dy;
      // Never left over a pile: a step that would overlap one goes just past
      // it, and a card stepped off a pile goes onto the table beneath.
      const leaving = this.table.isPile(piece.zone_id);
      const landing = leaving
        ? (this.table.zoneAtWorld(x, y, true) ?? this.table.tableFor(piece.zone_id))
        : piece.zone_id;
      if (landing !== null && this.model.zones.get(landing)?.layout === "free") {
        const [width, height] = this.table.pieceSizeOf(id);
        const piles = this.table.piles(null).map((pile) => pile.bounds);
        ({ x, y } = stepPastPiles(x, y, width, height, piles, dx, dy));
      }
      this.table.setOverride(id, { x, y });
      const [op, payload] =
        leaving && landing !== null
          ? (["move_to_zone", { piece_id: id, zone_id: landing, x, y }] as const)
          : (["move", { piece_id: id, x, y }] as const);
      this.table.intents.send(op, payload, {
        onReject: () => {
          this.keyboardSettle.delete(id);
          this.table.clearOverride(id, true);
        },
      });
      const releaseId = this.table.intents.send("release", { piece_id: id }, {
        onAck: () => {
          if (this.keyboardSettle.get(id) !== releaseId) return;
          this.keyboardSettle.delete(id);
          this.table.clearOverride(id, false);
        },
      });
      this.keyboardSettle.set(id, releaseId);
      moved.push(id);
    }
    if (moved.length === 1) {
      this.table.announcer.announce(`${capital(this.table.pieceLabel(moved[0]!))} moved ${way}.`);
    } else if (moved.length > 1) {
      this.table.announcer.announce(`${moved.length} pieces moved ${way}.`);
    }
  }
}

function toolButton(label: string, hint: string): HTMLButtonElement {
  const button = plainButton(label, () => {});
  button.setAttribute("aria-pressed", "false");
  button.title = hint;
  return button;
}

function plainButton(label: string, onClick: () => void): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button button--secondary button--sm";
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function isTyping(element: HTMLElement): boolean {
  const tag = element.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || element.isContentEditable;
}

function capital(text: string): string {
  return text.length === 0 ? text : `${text[0]!.toUpperCase()}${text.slice(1)}`;
}
