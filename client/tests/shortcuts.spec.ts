import { expect, test, type Browser, type Page } from "@playwright/test";
import { openFromLanding, type RoomKind, openControls, openTableButtons } from "./rooms";

/**
 * The single-key shortcuts on the piece under the pointer, the deck's own
 * menu entries, the city tiles, and the way home from the table.
 */

async function openRoom(browser: Browser, kind: RoomKind, name: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await openFromLanding(page, kind);
  await page.getByLabel("Your name").fill(name);
  await page.getByRole("button", { name: "Join table" }).click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  await openControls(page);
  await expect(page.locator(".tabletop__pieces-layer .piece").first()).toBeVisible();
  return page;
}

const deckCard = (page: Page) =>
  page.locator('.tabletop__pieces-layer .piece--card[data-zone-id="deck"]').last();

test("the deck's menu deals to everyone and shuffles", async ({ browser }) => {
  const page = await openRoom(browser, "Value Cards", "Ines");

  await deckCard(page).click({ button: "right" });
  await expect(page.getByRole("menuitem", { name: "Shuffle the deck" })).toBeVisible();
  const deckLabel = page.locator('.zone[data-zone-id="deck"] .zone__label');
  await expect(deckLabel).toHaveText("Core deck · 18");
  await page.getByRole("menuitem", { name: "3 cards each", exact: true }).click();
  // Dealt face up into the person's own hand, so they can read what they hold.
  await expect(page.locator(".hand-tray__fan .piece .piece__face")).toHaveCount(3);
  // The deck's label counts what is left in it.
  await expect(deckLabel).toHaveText("Core deck · 15");
  // Cards arriving open the tray.
  await expect(page.locator(".hand-tray__toggle")).toHaveAttribute("aria-expanded", "true");
  // Each face is the printed card's picture, read out as its name and definition.
  const face = page.locator(".hand-tray__fan .piece .piece__face").first();
  await expect(face).toHaveAttribute("alt", /^[A-Z][a-z]+\. \S/);
  // It loads: waited for, since the picture arrives after the card does.
  await expect
    .poll(() => face.evaluate((image) => (image as HTMLImageElement).naturalWidth))
    .toBeGreaterThan(0);
  // The tray's name sits in its bottom corner, drawn over the fan rather
  // than in a row of its own, and never under a card; each card ends inside
  // the tray.
  const head = (await page.locator(".hand-tray__head").boundingBox())!;
  const tray = (await page.locator(".hand-tray").boundingBox())!;
  expect(head.y + head.height).toBeLessThanOrEqual(tray.y + tray.height);
  expect(head.y + head.height).toBeGreaterThan(tray.y + tray.height - 48);
  const onTop = await page.evaluate(
    ([x, y]) => document.elementFromPoint(x, y)?.closest(".hand-tray__toggle") !== null,
    [head.x + head.width / 2, head.y + head.height / 2],
  );
  expect(onTop).toBe(true);
  for (const card of await page.locator(".hand-tray__fan .piece").all()) {
    const box = (await card.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(tray.y);
    expect(box.y + box.height).toBeLessThanOrEqual(tray.y + tray.height);
  }

  await deckCard(page).hover();
  await page.keyboard.press("s");
  await expect(page.locator("[data-announcer]")).toContainText("Deck shuffled.");
});

test("hovering a card says what the keys do; Space enlarges it and F turns it over", async ({
  browser,
}) => {
  const page = await openRoom(browser, "Value Cards", "Ines");
  await page.getByRole("button", { name: "Deal 3 core cards" }).click();
  const card = page.locator(".hand-tray__fan .piece").first();
  await expect(card.locator(".piece__face")).toBeVisible();

  await card.hover();
  await expect(page.locator(".piece-hint")).toContainText("Space hold to enlarge");
  await expect(page.locator(".piece-hint")).toContainText("F turn over");

  // The close look lasts exactly as long as Space is held.
  await page.keyboard.down(" ");
  await expect(page.locator(".peek .piece--enlarged")).toBeVisible();
  await page.waitForTimeout(300);
  await expect(page.locator(".peek .piece--enlarged")).toBeVisible();
  await page.keyboard.up(" ");
  await expect(page.locator(".peek")).toBeHidden();
  // Space does not select.
  await expect(page.locator(".is-selected")).toHaveCount(0);

  await card.hover();
  await page.keyboard.press("f");
  await expect(page.locator(".hand-tray__fan .piece.is-face-down")).toHaveCount(1);
});

test("a city's tile is locked in place, unlocks with U, and keeps its size turned over", async ({
  browser,
}) => {
  const page = await openRoom(browser, "Leadership and Knowledge in Popular Rule", "Ines");
  const tile = page.locator('.tabletop__pieces-layer .piece--tile[data-zone-id="potamosia"]');
  await expect(tile).toHaveClass(/is-locked/);
  const front = await tile.boundingBox();

  await tile.hover();
  await page.keyboard.press("f");
  await expect(page.getByText("That piece is locked.")).toBeVisible();

  await tile.hover();
  await page.keyboard.press("u");
  await expect(tile).not.toHaveClass(/is-locked/);
  await page.keyboard.press("f");
  await expect(tile).toHaveClass(/is-back/);
  await expect(tile.locator(".piece__title")).toHaveText("Potamosia");
  await expect(tile.locator(".piece__copy")).toHaveCount(0);
  const back = await tile.boundingBox();
  expect(back?.width).toBeCloseTo(front!.width, 0);
  expect(back?.height).toBeCloseTo(front!.height, 0);

  await tile.click({ button: "right" });
  await page.getByRole("menuitem", { name: "Lock in place" }).click();
  await expect(tile).toHaveClass(/is-locked/);
});

test("the site's name above the table leads back to the main page", async ({ browser }) => {
  const page = await openRoom(browser, "Value Cards", "Ines");
  await page.getByRole("link", { name: "Ethics Sandbox" }).click();
  await page.waitForURL(/\/$/);
});

test("the Value Cards room lays out the core deck and the sidebar, and the Pieces menu adds more", async ({
  browser,
}) => {
  const page = await openRoom(browser, "Value Cards", "Ines");
  const cardsIn = (zone: string) =>
    page.locator(`.tabletop__pieces-layer .piece--card[data-zone-id${zone}]`);
  await expect(cardsIn('="deck"')).toHaveCount(18);
  await expect(cardsIn('="sidebar"')).toHaveCount(18);

  await page.locator(".pieces-menu summary").click();
  const row = page.locator(".pieces-menu__row", { hasText: "Sidebar" });
  await row.getByRole("button", { name: "Add" }).click();
  await expect(cardsIn('^="added-deck-"')).toHaveCount(18);
  await expect(cardsIn('="sidebar"')).toHaveCount(18);
  // A pile of its own, outlined and named like the others.
  await expect(page.locator('.zone[data-zone-id^="added-deck-"] .zone__label')).toHaveText("Sidebar 2 · 18");

  // The menu, still open, now lists it; removing it takes the pile and its cards away.
  await page.getByRole("button", { name: "Remove Sidebar 2" }).click();
  await expect(cardsIn('^="added-deck-"')).toHaveCount(0);
  await expect(page.locator('.zone[data-zone-id^="added-deck-"]')).toHaveCount(0);
  await expect(cardsIn('="sidebar"')).toHaveCount(18);
});

test("a card in an added deck offers to remove the deck", async ({ browser }) => {
  const page = await openRoom(browser, "Value Cards", "Ines");
  await page.locator(".pieces-menu summary").click();
  await page.locator(".pieces-menu__row", { hasText: "Core deck" }).getByRole("button", { name: "Add" }).click();
  const added = page.locator('.tabletop__pieces-layer .piece--card[data-zone-id^="added-deck-"]');
  await expect(added).toHaveCount(18);

  await added.last().click({ button: "right" });
  await page.getByRole("menuitem", { name: "Remove this deck" }).click();
  await expect(added).toHaveCount(0);
  await expect(page.locator(".toast")).toContainText("Ines removed Core deck 2.");
});

test("Reset asks “Are you sure?” first, and clears the whole table only if confirmed", async ({
  browser,
}) => {
  const page = await openRoom(browser, "Value Cards", "Ines");
  // Reset is the facilitator's.
  await page.getByRole("button", { name: "Become facilitator" }).click();
  await expect(page.getByRole("button", { name: "Reset", exact: true })).toBeVisible();
  await page.locator(".pieces-menu summary").click();
  await page.locator(".pieces-menu__row", { hasText: "Sidebar" }).getByRole("button", { name: "Add" }).click();
  const cards = page.locator(".tabletop__pieces-layer .piece--card");
  await expect(cards).toHaveCount(54);

  let asked = "";
  page.once("dialog", (dialog) => {
    asked = dialog.message();
    void dialog.dismiss();
  });
  // Opening the Pieces menu closed the Table buttons menu.
  await expect(page.locator("details.table-buttons[open]")).toHaveCount(0);
  await openTableButtons(page);
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect.poll(() => asked).toContain("Are you sure?");
  await expect(cards).toHaveCount(54);

  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(cards).toHaveCount(0);
  await expect(page.locator('.zone[data-zone-id^="added-deck-"]')).toHaveCount(0);
});
