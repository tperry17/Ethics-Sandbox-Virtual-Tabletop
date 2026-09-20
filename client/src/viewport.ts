/**
 * Pan and zoom, as arithmetic.
 *
 * One rule holds throughout: `screen = world * scale + offset`. Every
 * function here is pure, so the awkward cases - zooming toward a pointer,
 * fitting a table into a window - are testable without a browser.
 */

export const MIN_SCALE = 0.4;
export const MAX_SCALE = 2.5;

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
  const scale = clampScale(viewport.scale * factor);
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

/** The viewport that shows all of `bounds` inside `size`, centred. */
export function fitBounds(bounds: Bounds, size: Size, padding = 48): Viewport {
  const width = Math.max(bounds.maxX - bounds.minX, 1);
  const height = Math.max(bounds.maxY - bounds.minY, 1);
  const usableWidth = Math.max(size.width - padding * 2, 1);
  const usableHeight = Math.max(size.height - padding * 2, 1);
  const scale = clampScale(Math.min(usableWidth / width, usableHeight / height));
  const centreX = (bounds.minX + bounds.maxX) / 2;
  const centreY = (bounds.minY + bounds.maxY) / 2;
  return {
    scale,
    offsetX: size.width / 2 - centreX * scale,
    offsetY: size.height / 2 - centreY * scale,
  };
}

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
