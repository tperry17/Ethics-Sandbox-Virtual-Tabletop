import { expect, test, type Page } from "@playwright/test";
import { openFromLanding, openControls } from "./rooms";

/**
 * A card let go partly over a pile goes into it, if its middle is on the
 * pile, or is put down clear of it: never left half under it.
 */

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

async function valueCardsRoom(page: Page): Promise<void> {
  await openFromLanding(page, "Value Cards");
  await page.getByLabel("Your name").fill("Ines");
  await page.getByRole("button", { name: "Join table" }).click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  await openControls(page);
  await expect(page.locator("html[data-table-client='ready']")).toHaveCount(1);
  await expect(page.locator('.tabletop__zones [data-zone-id="sidebar"] .zone__label')).toContainText("18");
}

async function box(page: Page, selector: string): Promise<Box> {
  const found = await page.locator(selector).boundingBox();
  expect(found).not.toBeNull();
  return found!;
}

/** The card on top of the core deck: the one a press on the deck picks up. */
async function topOfDeck(page: Page): Promise<string> {
  const deck = await box(page, '.tabletop__zones [data-zone-id="deck"]');
  return page.evaluate(
    ([x, y]) =>
      document.elementFromPoint(x!, y!)?.closest<HTMLElement>("[data-piece-id]")?.dataset
        .pieceId ?? "",
    [deck.x + deck.width / 2, deck.y + deck.height / 2],
  );
}

/** Press the card at (fromX, fromY), drag it, and let go at (toX, toY). */
async function drag(page: Page, from: [number, number], to: [number, number]): Promise<void> {
  await page.mouse.move(...from);
  await page.mouse.down();
  for (let step = 1; step <= 10; step++) {
    await page.mouse.move(
      from[0] + ((to[0] - from[0]) * step) / 10,
      from[1] + ((to[1] - from[1]) * step) / 10,
    );
  }
  await page.mouse.up();
}

test.use({ viewport: { width: 1440, height: 900 } });

test("a card let go with its middle on a pile goes into the pile", async ({ page }) => {
  await valueCardsRoom(page);
  const id = await topOfDeck(page);
  const card = await box(page, `[data-piece-id="${id}"]`);
  const sidebar = await box(page, '.tabletop__zones [data-zone-id="sidebar"]');
  // Held by its bottom edge and let go just below the Sidebar: the hand is
  // on the open table, but the card's middle is on the pile.
  const grabY = card.y + card.height - 4;
  const toY = sidebar.y + sidebar.height + 6;
  await drag(page, [card.x + card.width / 2, grabY], [sidebar.x + sidebar.width / 2, toY]);
  await expect(page.locator('.tabletop__zones [data-zone-id="sidebar"] .zone__label')).toContainText("19");
  await expect(page.locator('.tabletop__zones [data-zone-id="deck"] .zone__label')).toContainText("17");
});

test("a card let go partly over a pile is put down clear of it", async ({ page }) => {
  await valueCardsRoom(page);
  const id = await topOfDeck(page);
  const card = await box(page, `[data-piece-id="${id}"]`);
  const sidebar = await box(page, '.tabletop__zones [data-zone-id="sidebar"]');
  // Held by its middle and let go so its top third lies over the Sidebar.
  const toX = sidebar.x + sidebar.width / 2;
  const toY = sidebar.y + sidebar.height + card.height * 0.2;
  await drag(page, [card.x + card.width / 2, card.y + card.height / 2], [toX, toY]);
  await expect(page.locator('.tabletop__zones [data-zone-id="deck"] .zone__label')).toContainText("17");
  await expect(page.locator('.tabletop__zones [data-zone-id="sidebar"] .zone__label')).toContainText("18");
  // It stays where the server put it: wholly below the pile, not under it.
  await expect
    .poll(async () => {
      const now = await box(page, `[data-piece-id="${id}"]`);
      return Math.round(now.y - (sidebar.y + sidebar.height));
    })
    .toBeGreaterThanOrEqual(0);
  await page.waitForTimeout(500);
  const settled = await box(page, `[data-piece-id="${id}"]`);
  expect(settled.y).toBeGreaterThanOrEqual(sidebar.y + sidebar.height - 1);
  // ...and near it, not thrown across the table.
  expect(settled.y - (sidebar.y + sidebar.height)).toBeLessThan(card.height * 0.5);
  expect(await page.locator(".toast").count()).toBe(0);
});
