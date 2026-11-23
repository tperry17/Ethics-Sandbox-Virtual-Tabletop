/**
 * Pan and zoom, as arithmetic.
 *
 * One rule holds throughout: `screen = world * scale + offset`. Every
 * function here is pure, so the awkward cases - zooming toward a pointer,
 * fitting a table into a window - are testable without a browser.
 */

/**
 * How far the wheel, a pinch or the zoom buttons go out. "Fit table" goes
 * further when what is on the table needs it (FIT_MIN_SCALE): a phone is
 * 390px across and a room's table 1700 world units, a class several times that.
 */
export const MIN_SCALE = 0.1;
export const MAX_SCALE = 2.5;
/** Below this a fit is degenerate: something lies absurdly far away. */
export const FIT_MIN_SCALE = 0.01;

export interface Viewport {
  /** Where world (0, 0) sits on screen, in CSS pixels. */
  offsetX: number;
  offsetY: number;
  scale: number;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export interface Size {
  width: number;
  height: number;
}

export function identityViewport(): Viewport {
  return { offsetX: 0, offsetY: 0, scale: 1 };
}

export function clampScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale));
}

export function worldToScreen(
  viewport: Viewport,
  x: number,
  y: number,
): [number, number] {
  return [x * viewport.scale + viewport.offsetX, y * viewport.scale + viewport.offsetY];
}

export function screenToWorld(
  viewport: Viewport,
  x: number,
  y: number,
): [number, number] {
  return [(x - viewport.offsetX) / viewport.scale, (y - viewport.offsetY) / viewport.scale];
}

export function panBy(viewport: Viewport, dx: number, dy: number): Viewport {
  return { ...viewport, offsetX: viewport.offsetX + dx, offsetY: viewport.offsetY + dy };
}

/**
 * Zoom by `factor`, leaving the world point under (`screenX`, `screenY`) put.
 *
 * Zooming toward the pointer is the difference between a table that follows
 * your attention and one that slides out from under it.
 */
export function zoomAt(
  viewport: Viewport,
  screenX: number,
  screenY: number,
  factor: number,
): Viewport {
  // Fitted out past MIN_SCALE, zooming in still works and zooming out stays put.
  const lowest = Math.min(MIN_SCALE, viewport.scale);
  const scale = Math.min(MAX_SCALE, Math.max(lowest, viewport.scale * factor));
  if (scale === viewport.scale) return viewport;
  const [worldX, worldY] = screenToWorld(viewport, screenX, screenY);
  return {
    scale,
    offsetX: screenX - worldX * scale,
    offsetY: screenY - worldY * scale,
  };
}

export function unionBounds(bounds: Bounds[]): Bounds | null {
  if (bounds.length === 0) return null;
  let { minX, minY, maxX, maxY } = bounds[0]!;
  for (const box of bounds.slice(1)) {
    minX = Math.min(minX, box.minX);
    minY = Math.min(minY, box.minY);
    maxX = Math.max(maxX, box.maxX);
    maxY = Math.max(maxY, box.maxY);
  }
  return { minX, minY, maxX, maxY };
}

/** The gap "Fit table" leaves between the table and the window's sides. */
export const FIT_PADDING = 16;
/** The gap above it, clear of the row of table controls along the top. */
export const FIT_TOP = 64;

/**
 * The viewport that fills the window's width with `bounds`: the table runs
 * from the window's left edge to its right, where the side panel opens and
 * the decks are laid, and no felt is wasted beside it.
 */
export function fitBounds(
  bounds: Bounds,
  size: Size,
  padding = FIT_PADDING,
  top = FIT_TOP,
  maxScale = Number.POSITIVE_INFINITY,
): Viewport {
  const width = Math.max(bounds.maxX - bounds.minX, 1);
  const height = Math.max(bounds.maxY - bounds.minY, 1);
  const usableWidth = Math.max(size.width - padding * 2, 1);
  const usableHeight = Math.max(size.height - top - padding, 1);
  // Everything fits, however far out that takes the view: the point of a fit.
  const scale = Math.min(MAX_SCALE, Math.max(FIT_MIN_SCALE, Math.min(usableWidth / width, maxScale)));
  // Narrower than the window (held back by maxScale), it is centred across.
  const spareX = Math.max(usableWidth - width * scale, 0);
  // Up and down it is centred where it fits; where it is taller than the
  // window, its top edge is put at the padding, so what lies at its top is
  // on screen and the rest is a scroll away.
  const offsetY =
    height * scale > usableHeight
      ? top - bounds.minY * scale
      : top + usableHeight / 2 - (bounds.minY + height / 2) * scale;
  return { scale, offsetX: padding + spareX / 2 - bounds.minX * scale, offsetY };
}

/**
 * "Fit table" never zooms in past this: fitted to what is on the table, two
 * piles would otherwise fill the window.
 */
export const FIT_MAX_SCALE = 1;

/**
 * Keep at least a corner of the table on screen.
 *
 * Panning is free, but not free enough to lose the table off the edge of
 * the window and have no idea which way to drag back.
 */
export function clampPan(viewport: Viewport, bounds: Bounds, size: Size): Viewport {
  const margin = 96;
  const [left, top] = worldToScreen(viewport, bounds.minX, bounds.minY);
  const [right, bottom] = worldToScreen(viewport, bounds.maxX, bounds.maxY);
  let offsetX = viewport.offsetX;
  let offsetY = viewport.offsetY;
  if (left > size.width - margin) offsetX -= left - (size.width - margin);
  if (right < margin) offsetX += margin - right;
  if (top > size.height - margin) offsetY -= top - (size.height - margin);
  if (bottom < margin) offsetY += margin - bottom;
  return { ...viewport, offsetX, offsetY };
}

export function viewportsEqual(a: Viewport, b: Viewport): boolean {
  return a.offsetX === b.offsetX && a.offsetY === b.offsetY && a.scale === b.scale;
}
