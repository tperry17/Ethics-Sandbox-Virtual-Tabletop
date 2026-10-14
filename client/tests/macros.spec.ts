import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * Macro buttons in a live room built from a game definition. Two Doors is
 * the reference game: two seats, a private hand each, and a Deal button.
 */

async function startTwoDoors(browser: Browser): Promise<{ page: Page; code: string }> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/start?game=two-doors");
  await page.getByLabel("Your name").fill("Ines");
  await page.getByRole("button", { name: "Start a table" }).click();
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

test("the facilitator deals, and each person sees only their own card", async ({ browser }) => {
  const { page: host, code } = await startTwoDoors(browser);
  const guest = await join(browser, code, "Tomas");

  const deal = host.getByRole("button", { name: "Deal one each" });
  await expect(deal).toBeVisible();
  await deal.click();

  const hostCard = host.locator(".hand-tray__fan .piece .piece__title");
  const guestCard = guest.locator(".hand-tray__fan .piece .piece__title");
  await expect(hostCard).toHaveCount(1);
  await expect(guestCard).toHaveCount(1);
  const hostTitle = (await hostCard.textContent()) ?? "";
  const guestTitle = (await guestCard.textContent()) ?? "";
  expect(hostTitle).not.toBe("");
  expect(hostTitle).not.toBe(guestTitle);
  // The other hand is on the table as backs, with no text to read.
  await expect(guest.locator(".tabletop__pieces-layer .piece__title", { hasText: hostTitle })).toHaveCount(0);

  await expect(guest.getByText("Ines dealt one card to each seat.")).toBeVisible();
});

test("a destructive button asks first, and does nothing if declined", async ({ browser }) => {
  const { page: host } = await startTwoDoors(browser);
  await host.getByRole("button", { name: "Deal one each" }).click();
  await expect(host.locator(".hand-tray__fan .piece")).toHaveCount(1);

  host.once("dialog", (dialog) => void dialog.dismiss());
  await host.getByRole("button", { name: "Reset" }).click();
  await expect(host.locator(".hand-tray__fan .piece")).toHaveCount(1);

  host.once("dialog", (dialog) => void dialog.accept());
  await host.getByRole("button", { name: "Reset" }).click();
  await expect(host.locator(".hand-tray__fan .piece")).toHaveCount(0);
});

test("a participant does not get the facilitator's buttons", async ({ browser }) => {
  const { code } = await startTwoDoors(browser);
  const guest = await join(browser, code, "Tomas");

  await expect(guest.locator("[data-macro-id]")).toHaveCount(0);
});
