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
 * Open the room's side panel, where the activities and the table's buttons
 * are. On a laptop or tablet it starts closed behind "Activities"; on a phone
 * it is always open, below the table, and there is no button.
 */
export async function openPanel(page: Page): Promise<void> {
  const toggle = page.locator("#room-panel-toggle");
  if (!(await toggle.isVisible())) return;
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
}
