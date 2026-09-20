/**
 * Getting around the table: pan, zoom, and fit.
 *
 * This is the only input this half of the client listens for, and it moves
 * the camera, never a piece. Doing something to a piece is an intent, and
 * intents belong to the interaction half.
 */

import {
  type Bounds,
  type Size,
  type Viewport,
  clampPan,
  fitBounds,
  identityViewport,
  panBy,
  viewportsEqual,
  zoomAt,
} from "./viewport.js";

interface Options {
  surface: HTMLElement;
  onChange: (viewport: Viewport) => void;
  bounds: () => Bounds | null;
  size: () => Size;
}

export class ViewportController {
  private viewport: Viewport = identityViewport();
  private spaceHeld = false;
  private panPointer: number | null = null;
  private lastPoint: [number, number] = [0, 0];
  private touches = new Map<number, [number, number]>();
  private pinchDistance: number | null = null;
  /** True once the person has moved the camera themselves. */
  private touchedByPerson = false;

  constructor(private readonly options: Options) {}

  get current(): Viewport {
    return this.viewport;
  }

  get adjustedByPerson(): boolean {
    return this.touchedByPerson;
  }

  attach(): void {
    const surface = this.options.surface;
    surface.addEventListener("wheel", this.onWheel, { passive: false });
    surface.addEventListener("pointerdown", this.onPointerDown);
    surface.addEventListener("pointermove", this.onPointerMove);
    surface.addEventListener("pointerup", this.onPointerUp);
    surface.addEventListener("pointercancel", this.onPointerUp);
    window.addEventListener("keydown", this.onKeyDown);
    window.addEventListener("keyup", this.onKeyUp);
  }

  detach(): void {
    const surface = this.options.surface;
    surface.removeEventListener("wheel", this.onWheel);
    surface.removeEventListener("pointerdown", this.onPointerDown);
    surface.removeEventListener("pointermove", this.onPointerMove);
    surface.removeEventListener("pointerup", this.onPointerUp);
    surface.removeEventListener("pointercancel", this.onPointerUp);
    window.removeEventListener("keydown", this.onKeyDown);
    window.removeEventListener("keyup", this.onKeyUp);
  }

  /** Put the whole table on screen. Also what the "fit table" control does. */
  fit(byPerson = false): void {
    const bounds = this.options.bounds();
    if (bounds === null) return;
    if (byPerson) this.touchedByPerson = true;
    this.set(fitBounds(bounds, this.options.size()));
  }

  zoomBy(factor: number): void {
    const size = this.options.size();
    this.touchedByPerson = true;
    this.set(zoomAt(this.viewport, size.width / 2, size.height / 2, factor));
  }

  private set(next: Viewport): void {
    const bounds = this.options.bounds();
    const clamped =
      bounds === null ? next : clampPan(next, bounds, this.options.size());
    if (viewportsEqual(clamped, this.viewport)) return;
    this.viewport = clamped;
    this.options.onChange(clamped);
  }

  private localPoint(event: { clientX: number; clientY: number }): [number, number] {
    const box = this.options.surface.getBoundingClientRect();
    return [event.clientX - box.left, event.clientY - box.top];
  }

  private onWheel = (event: WheelEvent): void => {
    event.preventDefault();
    const [x, y] = this.localPoint(event);
    // A trackpad pinch arrives as a wheel event with ctrlKey set, and at a
    // much finer grain than a mouse wheel notch.
    const strength = event.ctrlKey ? 0.01 : 0.0015;
    this.touchedByPerson = true;
    this.set(zoomAt(this.viewport, x, y, Math.exp(-event.deltaY * strength)));
  };

  private onPointerDown = (event: PointerEvent): void => {
    if (event.pointerType === "touch") {
      this.touches.set(event.pointerId, this.localPoint(event));
      return;
    }
    const wantsPan = event.button === 1 || (event.button === 0 && this.spaceHeld);
    if (!wantsPan) return;
    event.preventDefault();
    this.panPointer = event.pointerId;
    this.lastPoint = this.localPoint(event);
    this.options.surface.setPointerCapture(event.pointerId);
    this.options.surface.classList.add("is-panning");
  };

  private onPointerMove = (event: PointerEvent): void => {
    if (event.pointerType === "touch") {
      if (!this.touches.has(event.pointerId)) return;
      this.touches.set(event.pointerId, this.localPoint(event));
      this.handleTouches();
      return;
    }
    if (this.panPointer !== event.pointerId) return;
    const [x, y] = this.localPoint(event);
    const [lastX, lastY] = this.lastPoint;
    this.lastPoint = [x, y];
    this.touchedByPerson = true;
    this.set(panBy(this.viewport, x - lastX, y - lastY));
  };

  private onPointerUp = (event: PointerEvent): void => {
    if (event.pointerType === "touch") {
      this.touches.delete(event.pointerId);
      if (this.touches.size < 2) this.pinchDistance = null;
      return;
    }
    if (this.panPointer !== event.pointerId) return;
    this.panPointer = null;
    this.options.surface.classList.remove("is-panning");
  };

  /** Two fingers pan and pinch together; one finger is left for the pieces. */
  private handleTouches(): void {
    if (this.touches.size !== 2) return;
    const [a, b] = [...this.touches.values()];
    const midX = (a![0] + b![0]) / 2;
    const midY = (a![1] + b![1]) / 2;
    const distance = Math.hypot(a![0] - b![0], a![1] - b![1]);
    this.touchedByPerson = true;
    if (this.pinchDistance !== null && this.pinchDistance > 0) {
      const factor = distance / this.pinchDistance;
      this.set(zoomAt(this.viewport, midX, midY, factor));
    }
    this.pinchDistance = distance;
  }

  private onKeyDown = (event: KeyboardEvent): void => {
    if (event.code !== "Space" || event.repeat) return;
    const target = event.target;
    if (target instanceof HTMLElement && isTypingTarget(target)) return;
    this.spaceHeld = true;
    this.options.surface.classList.add("is-pannable");
    event.preventDefault();
  };

  private onKeyUp = (event: KeyboardEvent): void => {
    if (event.code !== "Space") return;
    this.spaceHeld = false;
    this.options.surface.classList.remove("is-pannable");
  };
}

function isTypingTarget(element: HTMLElement): boolean {
  const tag = element.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || element.isContentEditable;
}
