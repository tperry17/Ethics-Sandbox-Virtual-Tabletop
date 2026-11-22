import { expect, test, type Page } from "@playwright/test";
import { openFromLanding, openControls } from "./rooms";

/**
 * A card let go partly over a pile goes into it, if more than half of the
 * card is over the pile, or is put down clear of it: never left under it.
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

test("a card let go mostly over a pile goes into the pile", async ({ page }) => {
  await valueCardsRoom(page);
  const id = await topOfDeck(page);
  const card = await box(page, `[data-piece-id="${id}"]`);
  const sidebar = await box(page, '.tabletop__zones [data-zone-id="sidebar"]');
  // Held by its bottom edge and let go just below the Sidebar: the hand is
  // on the open table, but almost all of the card is over the pile.
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

test("a card let go with the hand over a pile but most of the card off it is put clear", async ({
  page,
}) => {
  await valueCardsRoom(page);
  const id = await topOfDeck(page);
  const card = await box(page, `[data-piece-id="${id}"]`);
  const sidebar = await box(page, '.tabletop__zones [data-zone-id="sidebar"]');
  // Held by its top edge and let go with the hand just inside the bottom of
  // the Sidebar: the pointer is on the pile, but nearly all of the card is below it.
  const toX = sidebar.x + sidebar.width / 2;
  const toY = sidebar.y + sidebar.height - 10;
  await drag(page, [card.x + card.width / 2, card.y + 4], [toX, toY]);
  await expect(page.locator('.tabletop__zones [data-zone-id="deck"] .zone__label')).toContainText("17");
  await expect(page.locator('.tabletop__zones [data-zone-id="sidebar"] .zone__label')).toContainText(
    "18",
  );
  await page.waitForTimeout(500);
  const settled = await box(page, `[data-piece-id="${id}"]`);
  expect(settled.y).toBeGreaterThanOrEqual(sidebar.y + sidebar.height - 1);
  expect(await page.locator(".toast").count()).toBe(0);
});

test("the pile lights up only when letting go would put the card into it", async ({ page }) => {
  await valueCardsRoom(page);
  const id = await topOfDeck(page);
  const card = await box(page, `[data-piece-id="${id}"]`);
  const sidebar = await box(page, '.tabletop__zones [data-zone-id="sidebar"]');
  const lit = page.locator('.tabletop__zones [data-zone-id="sidebar"].is-drop-target');
  const from: [number, number] = [card.x + card.width / 2, card.y + 4];
  await page.mouse.move(...from);
  await page.mouse.down();
  // The pointer just inside the bottom of the pile, the card mostly below it: not lit.
  const toX = sidebar.x + sidebar.width / 2;
  for (let step = 1; step <= 10; step++) {
    await page.mouse.move(
      from[0] + ((toX - from[0]) * step) / 10,
      from[1] + ((sidebar.y + sidebar.height - 10 - from[1]) * step) / 10,
    );
  }
  await expect(lit).toHaveCount(0);
  // Higher, so most of the card is over the pile: lit, and letting go joins.
  await page.mouse.move(toX, sidebar.y + 10, { steps: 6 });
  await expect(lit).toHaveCount(1);
  await page.mouse.up();
  await expect(page.locator('.tabletop__zones [data-zone-id="sidebar"] .zone__label')).toContainText(
    "19",
  );
});

test("arrow keys never leave a card over a pile: it steps off and past", async ({ page }) => {
  await valueCardsRoom(page);
  const id = await topOfDeck(page);
  const deck = await box(page, '.tabletop__zones [data-zone-id="deck"]');
  const sidebar = await box(page, '.tabletop__zones [data-zone-id="sidebar"]');
  await page.locator(`[data-piece-id="${id}"]`).focus();
  // One step right takes the top card off the core deck, to just beside it.
  await page.keyboard.press("ArrowRight");
  await expect(page.locator('.tabletop__zones [data-zone-id="deck"] .zone__label')).toContainText(
    "17",
  );
  const overlaps = (a: Box, b: Box): boolean =>
    a.x < b.x + b.width - 1 && a.x + a.width > b.x + 1 && a.y < b.y + b.height - 1 && a.y + a.height > b.y + 1;
  await page.waitForTimeout(400);
  let now = await box(page, `[data-piece-id="${id}"]`);
  expect(overlaps(now, deck)).toBe(false);
  // Stepping on to the right, it hops over the Sidebar rather than resting on it.
  for (let press = 0; press < 12; press++) {
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(60);
    now = await box(page, `[data-piece-id="${id}"]`);
    expect(overlaps(now, sidebar)).toBe(false);
  }
  await page.waitForTimeout(400);
  now = await box(page, `[data-piece-id="${id}"]`);
  expect(overlaps(now, sidebar)).toBe(false);
  expect(now.x).toBeGreaterThan(sidebar.x + sidebar.width);
  await expect(page.locator('.tabletop__zones [data-zone-id="sidebar"] .zone__label')).toContainText(
    "18",
  );
  expect(await page.locator(".toast").count()).toBe(0);
});
