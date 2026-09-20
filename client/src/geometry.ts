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
