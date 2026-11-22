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
  /** Where this room's view is kept between visits, if anywhere. */
  storageKey?: string;
}

interface SavedView {
  scale: number;
  centreX: number;
  centreY: number;
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

  private lastSize: Size | null = null;

  constructor(private readonly options: Options) {}

  /**
   * The surface changed size: the window opened, or the iPad turned over.
   *
   * The first time, a view kept from an earlier visit is brought back;
   * otherwise the table is fitted. After that, a view the person chose keeps
   * the same point of the table in the middle of the screen.
   */
  resized(): void {
    const size = this.options.size();
    const before = this.lastSize;
    this.lastSize = size;
    if (before === null) {
      const saved = this.load();
      if (saved !== null) {
        this.touchedByPerson = true;
        this.set({
          scale: saved.scale,
          offsetX: size.width / 2 - saved.centreX * saved.scale,
          offsetY: size.height / 2 - saved.centreY * saved.scale,
        });
        return;
      }
    }
    if (!this.touchedByPerson) {
      this.fit();
      return;
    }
    const view = this.viewport;
    const centreX = (before ?? size).width / 2;
    const centreY = (before ?? size).height / 2;
    const worldX = (centreX - view.offsetX) / view.scale;
    const worldY = (centreY - view.offsetY) / view.scale;
    this.set({
      scale: view.scale,
      offsetX: size.width / 2 - worldX * view.scale,
      offsetY: size.height / 2 - worldY * view.scale,
    });
  }

  private load(): SavedView | null {
    const key = this.options.storageKey;
    if (key === undefined) return null;
    try {
      const raw = window.localStorage.getItem(key);
      if (raw === null) return null;
      const value = JSON.parse(raw) as Partial<SavedView>;
      const { scale, centreX, centreY } = value;
      if (
        typeof scale === "number" && typeof centreX === "number" &&
        typeof centreY === "number" && [scale, centreX, centreY].every(Number.isFinite)
      ) {
        return { scale, centreX, centreY };
      }
    } catch {
      // Storage can be blocked or empty: the view simply starts fresh.
    }
    return null;
  }

  private save(): void {
    const key = this.options.storageKey;
    if (key === undefined || !this.touchedByPerson) return;
    const size = this.options.size();
    const view = this.viewport;
    const saved: SavedView = {
      scale: view.scale,
      centreX: (size.width / 2 - view.offsetX) / view.scale,
      centreY: (size.height / 2 - view.offsetY) / view.scale,
    };
    try {
      window.localStorage.setItem(key, JSON.stringify(saved));
    } catch {
      // Not kept; nothing else depends on it.
    }
  }

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
    // Moves and lifts are heard on the window, not the surface: once the
    // interaction half captures a finger (for a drag or a pan), its events go
    // to the table's root and never reach the surface. Heard only there, a
    // lifted finger was never forgotten, and pinching stopped working.
    window.addEventListener("pointermove", this.onPointerMove);
    window.addEventListener("pointerup", this.onPointerUp);
    window.addEventListener("pointercancel", this.onPointerUp);
    window.addEventListener("keydown", this.onKeyDown);
    window.addEventListener("keyup", this.onKeyUp);
  }

  detach(): void {
    const surface = this.options.surface;
    surface.removeEventListener("wheel", this.onWheel);
    surface.removeEventListener("pointerdown", this.onPointerDown);
    window.removeEventListener("pointermove", this.onPointerMove);
    window.removeEventListener("pointerup", this.onPointerUp);
    window.removeEventListener("pointercancel", this.onPointerUp);
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

  /**
   * Pan by a distance in screen pixels. A one-finger drag on empty table
   * comes here from the interaction half, which alone knows whether the
   * finger landed on a piece.
   */
  panByPerson(dx: number, dy: number): void {
    this.touchedByPerson = true;
    this.set(panBy(this.viewport, dx, dy));
  }

  private set(next: Viewport): void {
    const bounds = this.options.bounds();
    const clamped =
      bounds === null ? next : clampPan(next, bounds, this.options.size());
    if (viewportsEqual(clamped, this.viewport)) return;
    this.viewport = clamped;
    this.save();
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

  /**
   * Two fingers pan and pinch together. One finger is left to the interaction
   * half: it moves a piece, or pans across empty table.
   */
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
