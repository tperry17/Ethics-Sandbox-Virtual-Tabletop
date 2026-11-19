import { expect, test } from "@playwright/test";

import {
  MAX_SCALE,
  MIN_SCALE,
  clampScale,
  fitBounds,
  screenToWorld,
  worldToScreen,
  zoomAt,
} from "../src/viewport.js";

test.describe("viewport arithmetic", () => {
  test("round-trips a point through screen space", () => {
    const viewport = { offsetX: 120, offsetY: -40, scale: 1.75 };
    const [screenX, screenY] = worldToScreen(viewport, 300, 210);
    const [worldX, worldY] = screenToWorld(viewport, screenX, screenY);
    expect(worldX).toBeCloseTo(300, 6);
    expect(worldY).toBeCloseTo(210, 6);
  });

  test("keeps the world point under the pointer while zooming", () => {
    const viewport = { offsetX: 10, offsetY: 30, scale: 1 };
    const before = screenToWorld(viewport, 400, 250);
    const zoomed = zoomAt(viewport, 400, 250, 1.6);
    const after = screenToWorld(zoomed, 400, 250);
    expect(after[0]).toBeCloseTo(before[0], 6);
    expect(after[1]).toBeCloseTo(before[1], 6);
  });

  test("clamps zoom to the readable range", () => {
    expect(clampScale(0.01)).toBe(MIN_SCALE);
    expect(clampScale(12)).toBe(MAX_SCALE);
    const tiny = zoomAt({ offsetX: 0, offsetY: 0, scale: MIN_SCALE }, 0, 0, 0.1);
    expect(tiny.scale).toBe(MIN_SCALE);
  });

  test("fits a table into a window, centred", () => {
    const bounds = { minX: 0, minY: 0, maxX: 1400, maxY: 1000 };
    const viewport = fitBounds(bounds, { width: 1200, height: 800 }, 48);
    const [left, top] = worldToScreen(viewport, bounds.minX, bounds.minY);
    const [right, bottom] = worldToScreen(viewport, bounds.maxX, bounds.maxY);
    expect(left).toBeGreaterThanOrEqual(0);
    expect(top).toBeGreaterThanOrEqual(0);
    expect(right).toBeLessThanOrEqual(1200);
    expect(bottom).toBeLessThanOrEqual(800);
    expect((left + right) / 2).toBeCloseTo(600, 3);
    expect((top + bottom) / 2).toBeCloseTo(400, 3);
  });

  test("puts a table too wide for the smallest zoom at its left edge, not cut in half", () => {
    const bounds = { minX: 0, minY: 0, maxX: 1400, maxY: 1000 };
    const viewport = fitBounds(bounds, { width: 390, height: 400 }, 16);
    expect(viewport.scale).toBe(MIN_SCALE);
    const [left, top] = worldToScreen(viewport, bounds.minX, bounds.minY);
    expect(left).toBeCloseTo(16, 3);
    expect(top).toBeCloseTo(16, 3);
  });
});
