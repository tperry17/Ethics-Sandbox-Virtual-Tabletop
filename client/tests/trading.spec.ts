import { expect, test, type Browser, type Page } from "@playwright/test";
import { newRoom } from "./rooms";

/** Three people trade value cards: an offer, its answer, and the checklist. */

async function person(browser: Browser, path: string, name: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(path);
  await page.locator('input[name="display_name"]').fill(name);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  return page;
}

test("an offer is made from the selected cards, answered, and ticks the checklist", async ({
  browser,
}) => {
  const ines = await person(browser, await newRoom(browser, "Value Cards"), "Ines");
  const code = ines.url().split("/t/")[1]!;
  const tomas = await person(browser, `/join?code=${code}`, "Tomas");
  const wren = await person(browser, `/join?code=${code}`, "Wren");

  await ines.getByRole("button", { name: "Start Value Cards Trading", exact: true }).click();
  await tomas.getByRole("button", { name: "Join" }).click();
  await wren.getByRole("button", { name: "Join" }).click();
  await ines.getByRole("button", { name: "Deal 6 each" }).click();

  const mine = ines.locator('.tabletop__pieces-layer .piece[data-zone-id$=":hand-seat-1"]');
  const theirs = ines.locator('.tabletop__pieces-layer .piece[data-zone-id$=":hand-seat-2"]');
  await expect(mine).toHaveCount(6);
  await expect(theirs).toHaveCount(6);

  // Offering with nothing selected says what to select.
  await ines.getByRole("button", { name: "Offer a trade" }).click();
  await expect(ines.getByText(/Select cards of your own/)).toBeVisible();

  await mine.first().click();
  await theirs.first().click({ modifiers: ["Shift"] });
  await ines.getByRole("button", { name: "Offer a trade" }).click();

  // Everyone sees the offer; only the one it is made to may answer it.
  await expect(wren.locator("[data-offer-id]")).toHaveCount(1);
  await expect(wren.getByRole("button", { name: "Accept" })).toHaveCount(0);
  await expect(ines.getByRole("button", { name: "Withdraw" })).toBeVisible();
  await tomas.getByRole("button", { name: "Accept" }).click();

  await expect(ines.locator("[data-offer-id]")).toHaveCount(0);
  await expect(wren.getByText(/Ines and Tomas: have traded/)).toBeVisible();
  await expect(wren.getByText(/Ines and Wren: not yet/)).toBeVisible();
  await expect(mine).toHaveCount(6);
});
