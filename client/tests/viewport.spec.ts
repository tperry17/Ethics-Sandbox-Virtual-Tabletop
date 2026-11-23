import { expect, test } from "@playwright/test";

import {
  FIT_MAX_SCALE,
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

  test("fills the window's width with the table, its top at the top when it is taller", () => {
    const bounds = { minX: 0, minY: 0, maxX: 1400, maxY: 1000 };
    const viewport = fitBounds(bounds, { width: 1200, height: 800 }, 48, 64);
    const [left, top] = worldToScreen(viewport, bounds.minX, bounds.minY);
    const [right] = worldToScreen(viewport, bounds.maxX, bounds.maxY);
    expect(left).toBeCloseTo(48, 3);
    expect(right).toBeCloseTo(1200 - 48, 3);
    expect(top).toBeCloseTo(64, 3);
  });

  test("centres a table that fills the width and is shorter than the window", () => {
    const bounds = { minX: 0, minY: 0, maxX: 1400, maxY: 400 };
    const viewport = fitBounds(bounds, { width: 1200, height: 800 }, 48, 64);
    const [, top] = worldToScreen(viewport, bounds.minX, bounds.minY);
    const [, bottom] = worldToScreen(viewport, bounds.maxX, bounds.maxY);
    // Centred in the room left below the controls: 64 to 800 - 48.
    expect((top + bottom) / 2).toBeCloseTo((64 + 800 - 48) / 2, 3);
  });

  test("fitting what is on the table never zooms past 100%, and centres it across", () => {
    // Two piles side by side: fitted to the width alone, they would fill a laptop.
    const bounds = { minX: 40, minY: 40, maxX: 560, maxY: 360 };
    const viewport = fitBounds(bounds, { width: 1440, height: 760 }, 16, 64, FIT_MAX_SCALE);
    expect(viewport.scale).toBe(1);
    const [left] = worldToScreen(viewport, bounds.minX, bounds.minY);
    const [right] = worldToScreen(viewport, bounds.maxX, bounds.maxY);
    expect((left + right) / 2).toBeCloseTo(1440 / 2, 3);
    // On a phone the same piles are narrower than 100% allows, so they fill the width.
    const phone = fitBounds(bounds, { width: 390, height: 600 }, 16, 64, FIT_MAX_SCALE);
    expect(phone.scale).toBeCloseTo((390 - 32) / 520, 6);
  });

  test("fits a table wider than the smallest manual zoom on a phone, all of it across", () => {
    // A room's table and a card put to its side: wider than MIN_SCALE shows on a phone.
    const bounds = { minX: 0, minY: 0, maxX: 5200, maxY: 1000 };
    const viewport = fitBounds(bounds, { width: 390, height: 400 }, 16, 16);
    expect(viewport.scale).toBeLessThan(MIN_SCALE);
    const [left] = worldToScreen(viewport, bounds.minX, bounds.minY);
    const [right] = worldToScreen(viewport, bounds.maxX, bounds.maxY);
    expect(left).toBeCloseTo(16, 3);
    expect(right).toBeCloseTo(390 - 16, 3);
  });

  test("fitted out past the smallest zoom, zooming out stays put and zooming in works", () => {
    const fitted = { offsetX: 0, offsetY: 0, scale: MIN_SCALE / 2 };
    expect(zoomAt(fitted, 0, 0, 0.5)).toBe(fitted);
    expect(zoomAt(fitted, 0, 0, 1.2).scale).toBeCloseTo((MIN_SCALE / 2) * 1.2, 6);
  });
});
