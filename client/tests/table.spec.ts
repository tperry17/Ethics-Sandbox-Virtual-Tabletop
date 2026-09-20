import type {} from "../src/main.js";

import { expect, test } from "@playwright/test";

const PREVIEW = "/table-preview";

test.describe("the table client renders a recorded session", () => {
  test("draws zones and pieces, with card faces as real text", async ({ page }) => {
    await page.goto(PREVIEW);

    const zones = page.locator(".tabletop__zones .zone");
    await expect(zones).toHaveCount(6);
    await expect(page.locator(".zone__label", { hasText: "Public claims" })).toBeVisible();

    const card = page.locator('[data-piece-id="claim-1"]');
    await expect(card).toHaveClass(/piece--card/);
    await expect(card.locator(".piece__title")).toHaveText("Equal standing");
    await expect(card.locator(".piece__folio")).toHaveText("i");
  });

  test("draws a piece it was sent no face for as a back, carrying no text", async ({ page }) => {
    await page.goto(PREVIEW);

    const back = page.locator('[data-piece-id="deck-0"]');
    await expect(back).toHaveClass(/is-face-down/);
    await expect(back).toHaveText("");
    await expect(back.locator(".piece__title")).toHaveCount(0);
  });

  test("puts this viewer's own hand in the tray, not on the table", async ({ page }) => {
    await page.goto(PREVIEW);

    await expect(page.locator(".hand-tray")).toBeVisible();
    await expect(page.locator(".hand-tray__fan .piece")).toHaveCount(3);
    await expect(page.locator('.tabletop__pieces-layer [data-piece-id="hand-1-a"]')).toHaveCount(0);
    await expect(page.locator(".hand-tray__label")).toContainText("Your hand");
  });

  test("shows another seat's hand on the table with its faces withheld", async ({ page }) => {
    await page.goto(PREVIEW);

    const sealed = page.locator('.zone[data-zone-id="hand-2"]');
    await expect(sealed).toHaveClass(/zone--sealed/);
    await expect(page.locator('[data-piece-id="hand-2-a"]')).toHaveClass(/is-face-down/);
  });

  test("builds the toolbar from the macros the server sent", async ({ page }) => {
    await page.goto(PREVIEW);

    const buttons = page.locator("#table-toolbar button");
    await expect(buttons).toHaveCount(3);
    await expect(buttons.first()).toHaveText("Set up");
  });

  test("reports the connection", async ({ page }) => {
    await page.goto(PREVIEW);
    await expect(page.locator(".tabletop__status")).toHaveText("Connected");
  });

  test("reveals a face only when the server sends one", async ({ page }) => {
    await page.goto(PREVIEW);

    const card = page.locator('[data-piece-id="claim-2"]');
    await expect(card).toHaveClass(/is-face-down/);
    await expect(card.locator(".piece__title")).toHaveCount(0);

    await expect(card.locator(".piece__title")).toHaveText("Who decides", { timeout: 5000 });
    await expect(card).not.toHaveClass(/is-face-down/);
  });

  test("glides another person's piece rather than teleporting it", async ({ page }) => {
    await page.goto(PREVIEW);

    const samples = await page.evaluate(async () => {
      const seen: Array<[number, number]> = [];
      const start = performance.now();
      return await new Promise<Array<[number, number]>>((resolve) => {
        const tick = () => {
          const table = window.ethicsSandboxTable;
          const at = table?.visualPositionOf("claim-2") ?? null;
          if (at !== null) seen.push(at);
          if (performance.now() - start > 1400) resolve(seen);
          else requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
    });

    const xs = [...new Set(samples.map(([x]) => Math.round(x)))];
    // The move is one patch, from 840 to 700. Seeing values in between is
    // the whole point: a teleport would show those two numbers and no others.
    expect(xs.length).toBeGreaterThan(3);
    expect(samples.at(-1)![0]).toBeCloseTo(700, 0);
  });

  test("stacks pieces by zone and z, not by the order nodes were made", async ({ page }) => {
    await page.goto(PREVIEW);

    const order = await page.evaluate(() => {
      const read = (id: string): number =>
        Number.parseInt(
          getComputedStyle(document.querySelector(`[data-piece-id="${id}"]`)!).zIndex,
          10,
        );
      return { table: read("token-1"), claim: read("claim-1"), deck: read("deck-1") };
    });

    expect(order.deck).toBeLessThan(order.claim);
    expect(order.table).toBeLessThan(order.claim);
  });

  test("lights a zone up as a drop target when asked", async ({ page }) => {
    await page.goto(PREVIEW);

    const zone = page.locator('.zone[data-zone-id="discard"]');
    await expect(zone).not.toHaveClass(/is-drop-target/);
    await page.evaluate(() => window.ethicsSandboxTable?.setDropTarget("discard"));
    await expect(zone).toHaveClass(/is-drop-target/);
    await page.evaluate(() => window.ethicsSandboxTable?.setDropTarget(null));
    await expect(zone).not.toHaveClass(/is-drop-target/);
  });

  test("zooms toward the pointer, clamped, and fits the table again", async ({ page }) => {
    await page.goto(PREVIEW);
    const surface = page.locator(".tabletop__viewport");
    const box = (await surface.boundingBox())!;

    const fitted = await page.evaluate(() => window.ethicsSandboxTable!.currentViewport.scale);

    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    for (let step = 0; step < 40; step += 1) {
      await page.mouse.wheel(0, -120);
    }
    const zoomed = await page.evaluate(() => window.ethicsSandboxTable!.currentViewport.scale);
    expect(zoomed).toBeGreaterThan(fitted);
    expect(zoomed).toBeLessThanOrEqual(2.5);

    for (let step = 0; step < 80; step += 1) {
      await page.mouse.wheel(0, 120);
    }
    const out = await page.evaluate(() => window.ethicsSandboxTable!.currentViewport.scale);
    expect(out).toBeGreaterThanOrEqual(0.4);

    await page.getByRole("button", { name: "Fit table" }).click();
    const refitted = await page.evaluate(() => window.ethicsSandboxTable!.currentViewport.scale);
    expect(refitted).toBeCloseTo(fitted, 2);
  });
});
