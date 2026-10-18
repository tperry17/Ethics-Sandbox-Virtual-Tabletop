/**
 * One piece, as a DOM element.
 *
 * Pieces are real elements carrying real text, not pixels on a canvas, so a
 * card stays readable at any zoom and inherits the design system's
 * typography for free. Each node keeps signatures of what it last drew and
 * rewrites only the parts that changed - the reconcile pass may run on
 * every frame, and a node that rebuilds itself is a node that drops frames.
 */

import type { ComponentView, PieceKind, SeatView } from "./protocol.js";
import type { LocalPiece } from "./model.js";

/** Roughly how long another person's piece takes to travel to where it now is. */
export const INTERPOLATION_MS = 120;

/**
 * Default piece sizes in world units, which are CSS pixels at 100% zoom.
 *
 * These match the design system's own dimensions. A component may override
 * them; nothing else may.
 */
const DEFAULT_SIZE: Record<PieceKind, [number, number]> = {
  card: [208, 288],
  die: [72, 72],
  cube: [56, 56],
  meeple: [64, 88],
  token: [64, 64],
  note: [160, 128],
  marker: [36, 36],
  board: [480, 320],
};

export function pieceSize(
  piece: LocalPiece,
  component: ComponentView | undefined,
): [number, number] {
  const [defaultWidth, defaultHeight] = DEFAULT_SIZE[piece.kind] ?? DEFAULT_SIZE.token;
  return [component?.width ?? defaultWidth, component?.height ?? defaultHeight];
}

export function seatTintClass(tintIndex: number): string {
  return `seat-${(((tintIndex % 6) + 6) % 6) + 1}`;
}

interface Visual {
  x: number;
  y: number;
  rotation: number;
}

export class PieceNode {
  readonly element: HTMLElement;
  private readonly body: HTMLElement;
  private faceSignature = "";
  private classSignature = "";
  private sizeSignature = "";
  private transformSignature = "";
  private from: Visual;
  private to: Visual;
  private startedAt = 0;
  private duration = 0;

  constructor(
    readonly id: string,
    piece: LocalPiece,
  ) {
    this.element = document.createElement("article");
    this.element.dataset.pieceId = piece.id;
    // Every piece is reachable from the keyboard: Tab to it, then act on it.
    this.element.tabIndex = 0;
    this.element.setAttribute("role", "button");
    this.element.setAttribute("aria-roledescription", piece.kind);
    this.body = document.createElement("div");
    this.body.className = "piece__body";
    this.element.append(this.body);
    this.from = { x: piece.x, y: piece.y, rotation: piece.rotation };
    this.to = { ...this.from };
  }

  /** Where this node is being drawn right now, mid-flight included. */
  get visual(): Visual {
    return { ...this.from };
  }

  /**
   * Point this piece at where the server says it is.
   *
   * `animate` is false for the piece under this person's own hand, which
   * must track the pointer exactly, and for a piece that has just appeared.
   */
  setTarget(piece: LocalPiece, animate: boolean, now: number): void {
    const target = { x: piece.x, y: piece.y, rotation: piece.rotation };
    if (!animate) {
      this.from = target;
      this.to = target;
      this.duration = 0;
      return;
    }
    if (
      target.x === this.to.x &&
      target.y === this.to.y &&
      target.rotation === this.to.rotation
    ) {
      return;
    }
    this.from = this.sample(now);
    this.to = target;
    this.startedAt = now;
    this.duration = INTERPOLATION_MS;
  }

  private sample(now: number): Visual {
    if (this.duration <= 0) return { ...this.to };
    const elapsed = now - this.startedAt;
    if (elapsed >= this.duration) return { ...this.to };
    const t = Math.max(0, elapsed / this.duration);
    const eased = t * t * (3 - 2 * t);
    return {
      x: this.from.x + (this.to.x - this.from.x) * eased,
      y: this.from.y + (this.to.y - this.from.y) * eased,
      rotation: this.from.rotation + (this.to.rotation - this.from.rotation) * eased,
    };
  }

  /**
   * Write this frame's transform. Returns true while there is more to come.
   */
  advance(now: number): boolean {
    const visual = this.sample(now);
    const settled = this.duration <= 0 || now - this.startedAt >= this.duration;
    if (settled) {
      this.duration = 0;
      this.from = { ...this.to };
    } else {
      this.from = visual;
    }
    this.writeTransform(visual.x, visual.y, visual.rotation);
    return !settled;
  }

  /** Place this node at an exact spot, ignoring any flight in progress. */
  placeAt(x: number, y: number, rotation: number): void {
    this.from = { x, y, rotation };
    this.to = { x, y, rotation };
    this.duration = 0;
    this.writeTransform(x, y, rotation);
  }

  private writeTransform(x: number, y: number, rotation: number): void {
    const transform =
      `translate3d(calc(${x.toFixed(2)}px - 50%), calc(${y.toFixed(2)}px - 50%), 0)` +
      ` rotate(${rotation.toFixed(2)}deg)`;
    if (transform === this.transformSignature) return;
    this.transformSignature = transform;
    this.element.style.transform = transform;
  }

  setZ(z: number): void {
    // Z-order is the model's, not the DOM's. Reordering elements to express
    // stacking would mean moving nodes every time a card is picked up.
    const value = String(z);
    if (this.element.style.zIndex !== value) this.element.style.zIndex = value;
  }

  setSize(width: number, height: number): void {
    const signature = `${width}x${height}`;
    if (signature === this.sizeSignature) return;
    this.sizeSignature = signature;
    this.element.style.width = `${width}px`;
    this.element.style.height = `${height}px`;
  }

  setClasses(piece: LocalPiece, holder: SeatView | undefined, extra: string): void {
    const classes = ["piece", "piece--placed", `piece--${piece.kind}`];
    if (piece.component_id === null) classes.push("is-face-down");
    if (piece.held_by !== null) classes.push("is-held", "is-lifted");
    if (piece.locked) classes.push("is-locked");
    if (holder !== undefined) classes.push(seatTintClass(holder.tint_index));
    if (extra) classes.push(extra);
    const signature = classes.join(" ");
    if (signature === this.classSignature) return;
    this.classSignature = signature;
    this.element.className = signature;
  }

  /**
   * Draw the face, or the back.
   *
   * A piece whose face this viewer is not entitled to arrives with no
   * component at all, so there is nothing here to withhold: the back is
   * drawn because nothing else was sent. The back is the same for every
   * piece of a kind - a back that varied would leak what varies.
   */
  setFace(
    piece: LocalPiece,
    component: ComponentView | undefined,
    label: string,
  ): void {
    const signature =
      piece.component_id === null
        ? `back:${piece.kind}`
        : [
            "face",
            piece.component_id,
            component?.title ?? "",
            component?.body ?? "",
            component?.folio ?? "",
            component?.image ?? "",
            piece.value ?? "",
            label,
          ].join("\u0000");
    if (signature === this.faceSignature) return;
    this.faceSignature = signature;
    this.body.replaceChildren();

    if (piece.component_id === null) {
      this.element.setAttribute("aria-label", `Face-down ${piece.kind}`);
      return;
    }
    this.element.setAttribute(
      "aria-label",
      component?.title ?? label ?? `A ${piece.kind}`,
    );
    if (component !== undefined) appendFace(this.body, component);
    // A component the client has not been sent gets a blank face rather
    // than an invented one; a rolled die still shows what it landed on.
    if (piece.value !== undefined && piece.value !== null) {
      const value = document.createElement("span");
      value.className = "piece__value";
      value.textContent = piece.value;
      this.body.append(value);
      this.element.setAttribute(
        "aria-label",
        `${component?.title ?? `A ${piece.kind}`} showing ${piece.value}`,
      );
    }
  }

  /** The little badge showing whose hand is on this piece. */
  setHolder(holder: SeatView | undefined): void {
    const existing = this.element.querySelector<HTMLElement>(".piece__holder");
    if (holder === undefined) {
      existing?.remove();
      return;
    }
    const initials = initialsFor(holder);
    if (existing !== null) {
      if (existing.textContent !== initials) existing.textContent = initials;
      return;
    }
    const badge = document.createElement("span");
    badge.className = "piece__holder";
    badge.textContent = initials;
    badge.title = holder.display_name ?? holder.label;
    this.element.append(badge);
  }

  remove(): void {
    this.element.remove();
  }
}

/** A component's face - image, title, body, folio - appended to `container`. */
export function appendFace(container: HTMLElement, component: ComponentView): void {
  if (component.image !== null) {
    const image = document.createElement("img");
    image.className = "piece__image";
    image.src = component.image;
    image.alt = component.title ?? "";
    image.draggable = false;
    container.append(image);
  }
  if (component.title !== null) {
    container.append(span("piece__title", component.title));
  }
  if (component.body !== null) {
    container.append(span("piece__copy", component.body));
  }
  if (component.folio !== null) {
    container.append(span("piece__folio", component.folio));
  }
}

function span(className: string, text: string): HTMLElement {
  const element = document.createElement("span");
  element.className = className;
  element.textContent = text;
  return element;
}

export function initialsFor(seat: SeatView): string {
  const name = seat.display_name ?? seat.label;
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "··";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}
