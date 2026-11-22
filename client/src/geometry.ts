/**
 * Reading the outlines the server sends.
 *
 * World units are CSS pixels at 100% zoom, which is what lets a zone's
 * geometry and a piece's size be stated in the same numbers the design
 * system uses.
 */

import type { GeometryView } from "./protocol.js";
import type { Bounds } from "./viewport.js";

export function geometryBounds(geometry: GeometryView): Bounds {
  if (geometry.shape === "rect") {
    return {
      minX: geometry.x,
      minY: geometry.y,
      maxX: geometry.x + geometry.width,
      maxY: geometry.y + geometry.height,
    };
  }
  if (geometry.points.length === 0) {
    return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  }
  const xs = geometry.points.map(([x]) => x);
  const ys = geometry.points.map(([, y]) => y);
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  };
}

export function boundsCentre(bounds: Bounds): [number, number] {
  return [(bounds.minX + bounds.maxX) / 2, (bounds.minY + bounds.maxY) / 2];
}

export function boundsContain(bounds: Bounds, x: number, y: number): boolean {
  return x >= bounds.minX && x <= bounds.maxX && y >= bounds.minY && y <= bounds.maxY;
}

export function expandBounds(bounds: Bounds, by: number): Bounds {
  return {
    minX: bounds.minX - by,
    minY: bounds.minY - by,
    maxX: bounds.maxX + by,
    maxY: bounds.maxY + by,
  };
}

/**
 * A polygon zone as a CSS `clip-path`, relative to its own bounding box.
 *
 * The element is laid out as that bounding box; the clip path is what makes
 * it the shape the server actually described.
 */
export function polygonClipPath(points: Array<[number, number]>): string | null {
  if (points.length < 3) return null;
  const bounds = geometryBounds({ shape: "polygon", points });
  const width = Math.max(bounds.maxX - bounds.minX, 1);
  const height = Math.max(bounds.maxY - bounds.minY, 1);
  const pairs = points.map(([x, y]) => {
    const px = ((x - bounds.minX) / width) * 100;
    const py = ((y - bounds.minY) / height) * 100;
    return `${px.toFixed(3)}% ${py.toFixed(3)}%`;
  });
  return `polygon(${pairs.join(", ")})`;
}

/** How far outside a pile a piece is put when it is moved clear of one. */
const PILE_GAP = 12;

/**
 * Where a piece let go at (`x`, `y`) should land so that it is not left
 * half under a pile: `{ join }` if more than half of it lies over a pile it
 * can go into (the one it overlaps most), otherwise a spot clear of every
 * pile it overlapped, as near as possible.
 *
 * This reads where the hand let go, as finding the zone under the pointer
 * does; whether the piece may go there is still the server's to say.
 */
export function landingBesidePiles(
  x: number,
  y: number,
  width: number,
  height: number,
  piles: Bounds[],
  canJoin: boolean,
): { join: number } | { x: number; y: number } {
  if (canJoin) {
    const box = { minX: x - width / 2, minY: y - height / 2, maxX: x + width / 2, maxY: y + height / 2 };
    const overlaps = piles.map((pile) => overlapArea(box, pile));
    const most = Math.max(0, ...overlaps);
    if (most > (width * height) / 2) return { join: overlaps.indexOf(most) };
  }
  // Moving clear of one pile can land on another; a few rounds settle it.
  for (let round = 0; round < 4; round++) {
    const box = { minX: x - width / 2, minY: y - height / 2, maxX: x + width / 2, maxY: y + height / 2 };
    const pile = piles.find(
      (p) => box.minX < p.maxX && box.maxX > p.minX && box.minY < p.maxY && box.maxY > p.minY,
    );
    if (pile === undefined) break;
    const choices: Array<[number, number]> = [
      [pile.minX - PILE_GAP - width / 2, y],
      [pile.maxX + PILE_GAP + width / 2, y],
      [x, pile.minY - PILE_GAP - height / 2],
      [x, pile.maxY + PILE_GAP + height / 2],
    ];
    [x, y] = choices.reduce((best, next) =>
      Math.hypot(next[0] - x, next[1] - y) < Math.hypot(best[0] - x, best[1] - y) ? next : best,
    );
  }
  return { x, y };
}

function overlapArea(a: Bounds, b: Bounds): number {
  const width = Math.min(a.maxX, b.maxX) - Math.max(a.minX, b.minX);
  const height = Math.min(a.maxY, b.maxY) - Math.max(a.minY, b.minY);
  return width > 0 && height > 0 ? width * height : 0;
}
