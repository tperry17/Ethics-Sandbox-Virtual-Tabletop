import type { Browser, Page } from "@playwright/test";

/** The kinds of room the landing page's "Open a room" menu offers. */
export type RoomKind = "Value Cards" | "Leadership and Knowledge in Popular Rule" | "Test room";

/** Open a room from the landing page's menu, on `page`, and land on its join form. */
export async function openFromLanding(page: Page, kind: RoomKind): Promise<void> {
  await page.goto("/");
  await page.locator("summary", { hasText: "Open a room" }).click();
  await page.getByRole("button", { name: kind, exact: true }).click();
  await page.waitForURL(/\/join\?code=[A-Z0-9]{6}$/);
}

/** Open a room of `kind` and return its join form's path, for anyone to join with. */
export async function newRoom(browser: Browser, kind: RoomKind): Promise<string> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await openFromLanding(page, kind);
  const path = new URL(page.url()).pathname + new URL(page.url()).search;
  await context.close();
  return path;
}

/**
 * Open the room's controls: the side panel, where the activities are, and the
 * "Table buttons" menu among the table's controls, where the table's buttons
 * are. On a laptop or tablet the panel starts closed behind "Activities"; on a
 * phone it is always open, below the table, and there is no button. The menu
 * starts closed everywhere, and stays open while the toolbar redraws.
 */
export async function openControls(page: Page): Promise<void> {
  const toggle = page.locator("#room-panel-toggle");
  if ((await toggle.isVisible()) && (await toggle.getAttribute("aria-expanded")) !== "true") {
    await toggle.click();
  }
  await openTableButtons(page);
}

/** Open the View menu among the table's controls, where "Fit table" and the zoom buttons are. */
export async function openView(page: Page): Promise<void> {
  const menu = page.locator("details.view-menu");
  if (!(await menu.evaluate((node) => (node as HTMLDetailsElement).open))) {
    await menu.locator("summary").click();
  }
}

/**
 * Open the "Table buttons" menu, once the table has sent its buttons. Every
 * room has a Pieces menu, drawn with them; someone who may press none of the
 * room's buttons gets no Table buttons menu at all.
 */
export async function openTableButtons(page: Page): Promise<void> {
  await page.locator("details.pieces-menu").waitFor({ timeout: 10_000 });
  const menu = page.locator("details.table-buttons");
  if ((await menu.count()) === 0) return;
  await menu.waitFor();
  if (!(await menu.evaluate((node) => (node as HTMLDetailsElement).open))) {
    await menu.locator("summary").click();
  }
}
