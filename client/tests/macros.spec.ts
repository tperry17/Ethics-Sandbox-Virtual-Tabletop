import { expect, test, type Browser, type Page } from "@playwright/test";
import { openFromLanding } from "./rooms";

/**
 * Activities started in an open room. Pairs is the reference game: two
 * players, a private hand each, and a Deal button.
 */

async function openRoom(browser: Browser, name: string): Promise<{ page: Page; code: string }> {
  const page = await (await browser.newContext()).newPage();
  await openFromLanding(page, "Test room");
  await page.getByLabel("Your name").fill(name);
  await page.getByRole("button", { name: "Join table" }).click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  const code = page.url().split("/t/")[1]!;
  return { page, code };
}

async function join(browser: Browser, code: string, name: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(`/join?code=${code}`);
  await page.locator('input[name="display_name"]').fill(name);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(new RegExp(`/t/${code}$`));
  return page;
}

/** A room where Ines and Tomas are playing Pairs. */
async function startPairs(
  browser: Browser,
): Promise<{ host: Page; guest: Page; code: string }> {
  const { page: host, code } = await openRoom(browser, "Ines");
  const guest = await join(browser, code, "Tomas");
  await host.getByRole("button", { name: "Start Pairs", exact: true }).click();
  await guest.getByRole("button", { name: "Join" }).click();
  await expect(host.getByText(/Pairs: running/)).toBeVisible();
  await expect(guest.getByText(/Pairs: running/)).toBeVisible();
  return { host, guest, code };
}

test("a player deals, and each person sees only their own cards", async ({ browser }) => {
  const { host, guest } = await startPairs(browser);

  // The hand is docked below the table before any card arrives, and is not
  // drawn on the table as well.
  await expect(host.locator(".hand-tray__empty")).toBeVisible();
  // The room's own hand and the activity's are both docked, never drawn.
  await expect(host.locator(".tabletop__zones .zone--private:visible")).toHaveCount(0);

  const deal = host.getByRole("button", { name: "Deal three each" });
  await expect(deal).toBeVisible();
  await deal.click();
  await expect(host.locator(".hand-tray__empty")).toBeHidden();

  const hostCards = host.locator(".hand-tray__fan .piece .piece__title");
  const guestCards = guest.locator(".hand-tray__fan .piece .piece__title");
  await expect(hostCards).toHaveCount(3);
  await expect(guestCards).toHaveCount(3);
  const hostTitles = await hostCards.allTextContents();
  const guestTitles = await guestCards.allTextContents();
  for (const title of hostTitles) expect(guestTitles).not.toContain(title);
  // The other hand is on the table as backs, with no text to read.
  for (const title of hostTitles) {
    await expect(
      guest.locator(".tabletop__pieces-layer .piece__title", { hasText: title }),
    ).toHaveCount(0);
  }

  await expect(guest.getByText("Ines dealt three cards to each seat.")).toBeVisible();
});

test("a destructive button asks first, and does nothing if declined", async ({ browser }) => {
  const { host } = await startPairs(browser);
  await host.getByRole("button", { name: "Deal three each" }).click();
  await expect(host.locator(".hand-tray__fan .piece")).toHaveCount(3);

  host.once("dialog", (dialog) => void dialog.dismiss());
  await host.getByRole("button", { name: "Reset" }).click();
  await expect(host.locator(".hand-tray__fan .piece")).toHaveCount(3);

  host.once("dialog", (dialog) => void dialog.accept());
  await host.getByRole("button", { name: "Reset" }).click();
  await expect(host.locator(".hand-tray__fan .piece")).toHaveCount(0);
});

test("with a facilitator in the room, a player gets only the buttons for anyone", async ({
  browser,
}) => {
  const { host, guest } = await startPairs(browser);
  await expect(guest.getByRole("button", { name: "Deal three each" })).toBeVisible();

  await host.getByRole("button", { name: "Become facilitator" }).click();

  await expect(guest.getByRole("button", { name: "Deal three each" })).toHaveCount(0);
  await expect(guest.getByRole("button", { name: "Catch pairs" })).toBeVisible();
  await expect(host.getByRole("button", { name: "Deal three each" })).toBeVisible();
});

test("nobody is the facilitator until someone takes the seat, and only one at a time", async ({
  browser,
}) => {
  const { page, code } = await openRoom(browser, "Ines");
  const guest = await join(browser, code, "Tomas");

  await expect(page.getByRole("button", { name: "Become facilitator" })).toBeVisible();
  await page.getByRole("button", { name: "Become facilitator" }).click();
  await expect(page.getByRole("button", { name: "Hand back facilitator" })).toBeVisible();
  await expect(guest.getByRole("button", { name: "Become facilitator" })).toBeHidden();

  await page.getByRole("button", { name: "Hand back facilitator" }).click();
  await expect(guest.getByRole("button", { name: "Become facilitator" })).toBeVisible();
});

test("an open room starts an activity for those who sign up, and its buttons are theirs", async ({
  browser,
}) => {
  const { page: host, code } = await openRoom(browser, "Ines");
  const guest = await join(browser, code, "Tomas");
  const bystander = await join(browser, code, "Wren");

  await host.getByRole("button", { name: "Start Pairs", exact: true }).click();
  await expect(host.getByText(/Pairs: signing up, 1 of 2/)).toBeVisible();

  await guest.getByRole("button", { name: "Join" }).click();
  await expect(host.getByText(/Pairs: running/)).toBeVisible();
  await expect(guest.getByText(/Pairs: running/)).toBeVisible();
  // A player can use the facilitator's buttons while nobody facilitates; the bystander cannot.
  await expect(
    host.locator("button[data-activity-id]", { hasText: "Deal three each" }),
  ).toBeVisible();
  await expect(
    guest.locator("button[data-activity-id]", { hasText: "Deal three each" }),
  ).toBeVisible();
  await expect(bystander.locator("button[data-activity-id]")).toHaveCount(0);

  await host.getByRole("button", { name: "End" }).click();
  await expect(host.getByText(/Pairs: running/)).toBeHidden();
  await expect(guest.locator("button[data-activity-id]")).toHaveCount(0);
});
