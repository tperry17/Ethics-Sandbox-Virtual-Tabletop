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

import { newClientId } from "./intents.js";
import type { TableRenderer } from "./table.js";

/** How far a press must travel before it is a drag rather than a click. */
const DRAG_THRESHOLD_PX = 5;
/** A touch held this long on a piece on the table opens its menu. */
const LONG_PRESS_MS = 500;
/** A card in the hand held this long is lifted up close to be read. */
const PEEK_HOLD_MS = 450;
/** At most one move per piece this often while dragging; the server coalesces anyway. */
const MOVE_SEND_MS = 50;
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
  | { kind: "peek"; pointerId: number; pieceId: string }
  | { kind: "consumed"; pointerId: number };

export class InteractionController {
  private gesture: Gesture | null = null;
  private tool: Tool = "hand";
  private readonly touches = new Set<number>();
  private lastCursorAt = 0;
  /** The release that settles each keyboard-moved piece, so only the last one clears it. */
  private readonly keyboardSettle = new Map<string, string>();
  private toolButtons: { point: HTMLButtonElement; pen: HTMLButtonElement } | null = null;
  private clearAllButton: HTMLButtonElement | null = null;
  private facilitatorButton: HTMLButtonElement | null = null;

  constructor(private readonly table: TableRenderer) {}

  attach(): void {
    const root = this.root;
    root.addEventListener("pointerdown", this.onPointerDown);
    root.addEventListener("pointermove", this.onPointerMove);
    root.addEventListener("pointerup", this.onPointerUp);
    root.addEventListener("pointercancel", this.onPointerCancel);
    root.addEventListener("dblclick", this.onDoubleClick);
    root.addEventListener("contextmenu", this.onContextMenu);
    window.addEventListener("keydown", this.onKeyDown);
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
    const group = document.createElement("div");
    group.className = "tabletop__tools";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", "Pointing and ink");

    const point = toolButton("Point", "Point at a spot on the table. Alt-click also points.");
    point.addEventListener("click", () => this.setTool(this.tool === "point" ? "hand" : "point"));
    const pen = toolButton("Pen", "Draw on the table in your colour.");
    pen.addEventListener("click", () => this.setTool(this.tool === "pen" ? "hand" : "pen"));
    const clearMine = plainButton("Clear my ink", () => {
      this.table.intents.send("clear_ink", { everyone: false });
    });
    const clearAll = plainButton("Clear all ink", () => {
      this.table.intents.send("clear_ink", { everyone: true });
    });
    clearAll.hidden = true;
    const facilitator = plainButton("Become facilitator", () => {
      const holding = this.model.you?.is_facilitator === true;
      this.table.intents.send(holding ? "release_facilitator" : "take_facilitator", {});
    });
    facilitator.hidden = true;

    group.append(point, pen, clearMine, clearAll, facilitator);
    this.table.toolArea.prepend(group);
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
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest("button, .table-menu, .reveals, .peek, input, a")) return;
    if (event.pointerType === "touch") {
      this.touches.add(event.pointerId);
      // A second finger means pan or pinch, which the camera owns.
      if (this.touches.size > 1) {
        this.cancelGesture();
        return;
      }
    }
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
      additive: event.shiftKey,
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
      else this.beginMarquee(gesture, event);
      return;
    }
    if (gesture.kind === "drag") this.continueDrag(gesture.pieces, event);
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
      this.click(gesture.pieceId, gesture.additive);
      return;
    }
    if (gesture.kind === "drag") this.finishDrag(gesture.pieces, event);
    else if (gesture.kind === "marquee") gesture.box.remove();
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
    if (gesture.kind === "marquee") gesture.box.remove();
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

  private click(pieceId: string | null, additive: boolean): void {
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
    this.table.inviteTray(true);
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
    this.showDropTargets(pieces, event, x, y);
  }

  /** Light up where the pieces would go if let go now. */
  private showDropTargets(pieces: Dragged[], event: PointerEvent, x: number, y: number): void {
    const live = pieces.filter((piece) => !piece.refused);
    if (this.table.overTray(event.clientX, event.clientY)) {
      this.table.setTrayTarget(true);
      this.table.setDropTarget(null);
      this.table.setStackTarget(null);
      return;
    }
    this.table.setTrayTarget(false);
    const onto = live.length === 1 ? this.stackTargetAt(live[0]!.id, event) : null;
    this.table.setStackTarget(onto);
    const zone = this.table.zoneAtWorld(x, y);
    const current = live[0] === undefined ? null : this.model.pieces.get(live[0].id)?.zone_id;
    this.table.setDropTarget(onto === null && zone !== null && zone !== current ? zone : null);
  }

  private stackTargetAt(draggedId: string, event: PointerEvent): string | null {
    const under = this.table.pieceIdAt(event.clientX, event.clientY);
    if (under === null || under === draggedId || this.table.isInTray(under)) return null;
    return under;
  }

  private finishDrag(pieces: Dragged[], event: PointerEvent): void {
    const [x, y] = this.table.clientToWorld(event.clientX, event.clientY);
    const overTray = this.table.overTray(event.clientX, event.clientY);
    const hand = this.table.myHandZoneId();
    const live = pieces.filter((piece) => !piece.refused);
    const onto = live.length === 1 ? this.stackTargetAt(live[0]!.id, event) : null;
    const zoneUnder = this.table.zoneAtWorld(x, y);

    for (const piece of live) {
      const truth = this.model.pieces.get(piece.id);
      if (truth === undefined) continue;
      const px = x - piece.offsetX;
      const py = y - piece.offsetY;
      const refuse = { onReject: () => this.refuse(piece) };

      if (overTray && hand !== null) {
        if (truth.zone_id !== hand) {
          this.table.intents.send("move_to_zone", { piece_id: piece.id, zone_id: hand }, refuse);
        }
      } else if (onto !== null) {
        this.table.intents.send("stack_onto", { piece_id: piece.id, onto_id: onto }, refuse);
      } else if (zoneUnder !== null && zoneUnder !== truth.zone_id) {
        this.table.intents.send(
          "move_to_zone",
          { piece_id: piece.id, zone_id: zoneUnder, x: px, y: py },
          refuse,
        );
      } else if (!piece.fromTray) {
        this.table.intents.send("move", { piece_id: piece.id, x: px, y: py }, refuse);
      } else {
        // Lifted out of the hand and let go nowhere in particular: back it goes.
        this.release(piece.id, false);
        this.table.clearOverride(piece.id, false);
        continue;
      }
      this.release(piece.id, false);
      this.announceDrop(piece.id, overTray && hand !== null ? hand : zoneUnder, onto);
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
    this.table.inviteTray(false);
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

  // -- marquee selection ---------------------------------------------------------------

  private beginMarquee(press: Extract<Gesture, { kind: "press" }>, event: PointerEvent): void {
    this.root.setPointerCapture?.(press.pointerId);
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
    const piece = this.model.pieces.get(pieceId);
    if (piece?.kind === "note") {
      this.write(pieceId);
      return;
    }
    this.flip(this.targetsFor(pieceId));
  };

  /** Ask what to write on a note. The server judges whether it may be written. */
  private write(pieceId: string): void {
    const current = this.model.pieces.get(pieceId)?.text ?? "";
    const text = window.prompt("Write on this note:", current);
    if (text === null) return;
    this.table.intents.send("set_text", { piece_id: pieceId, text }, this.settles(pieceId));
    this.table.announcer.announce("Note written on.");
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
      if (piece.component_id !== null) this.table.setOverride(id, { hideFace: true });
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
    if (target.closest(".table-menu")) return;
    // Keys belong to the table when focus is on it, or on nothing at all;
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

  /** Move pieces by a grid step: one move and one release each, settled on the release. */
  private nudge(ids: string[], dx: number, dy: number, way: string): void {
    const moved: string[] = [];
    for (const id of ids) {
      if (this.table.isInTray(id)) continue;
      const piece = this.model.pieces.get(id);
      if (piece === undefined) continue;
      const override = this.table.overrideOf(id);
      const x = (override?.x ?? piece.x) + dx;
      const y = (override?.y ?? piece.y) + dy;
      this.table.setOverride(id, { x, y });
      this.table.intents.send("move", { piece_id: id, x, y }, {
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
