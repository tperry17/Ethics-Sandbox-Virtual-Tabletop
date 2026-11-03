import { expect, test, type Browser, type Page } from "@playwright/test";
import { openFromLanding } from "./rooms";

/**
 * A class: one activity at several tables, run by whoever starts it. Pairs
 * is the reference game (two players a table).
 */

async function openRoom(browser: Browser, name: string): Promise<{ page: Page; code: string }> {
  const page = await (await browser.newContext()).newPage();
  await openFromLanding(page, "Test room");
  await page.getByLabel("Your name").fill(name);
  await page.getByRole("button", { name: "Join table" }).click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  return { page, code: page.url().split("/t/")[1]! };
}

async function join(browser: Browser, code: string, name: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(`/join?code=${code}`);
  await page.locator('input[name="display_name"]').fill(name);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(new RegExp(`/t/${code}$`));
  return page;
}

test("a facilitator sorts a class into tables, begins them and times them", async ({
  browser,
}) => {
  const { page: host, code } = await openRoom(browser, "Ines");
  const guests = [
    await join(browser, code, "Tomas"),
    await join(browser, code, "Rowan"),
    await join(browser, code, "Ana"),
    await join(browser, code, "Lee"),
  ];

  await host.getByLabel("Activity for the class").selectOption("pairs");
  await host.getByLabel("Number of tables").fill("2");
  await host.getByRole("button", { name: "Start a class" }).click();
  await expect(host.getByText("Class: Pairs, 2 tables")).toBeVisible();
  await expect(guests[0]!.getByText("Table 2: signing up, 0 of 2")).toBeVisible();
  // The facilitator is not offered a seat; a person is.
  await expect(host.getByRole("button", { name: "Join this table" })).toHaveCount(0);
  await expect(guests[0]!.getByRole("button", { name: "Join this table" })).toHaveCount(2);
  // And only the facilitator runs it.
  await expect(guests[0]!.getByRole("button", { name: "Sort people into tables" })).toHaveCount(0);

  await host.getByRole("button", { name: "Sort people into tables" }).click();
  await expect(host.getByRole("group", { name: "Proposed tables" })).toBeVisible();
  await host.getByRole("button", { name: "Seat them like this" }).click();
  await expect(host.getByText("Table 1: signing up, 2 of 2")).toBeVisible();
  await expect(host.getByText("Table 2: signing up, 2 of 2")).toBeVisible();

  await host.getByRole("button", { name: "Begin the tables" }).click();
  await expect(guests[0]!.getByText(/Table 1: running/)).toBeVisible();
  await expect(guests[0]!.getByText(/Table 2: running/)).toBeVisible();

  // The facilitator takes someone off a table that has begun, then seats them again.
  await host
    .locator(".toolbar__class-tables li")
    .first()
    .locator("select[data-seat]")
    .first()
    .selectOption({ label: "no table" });
  await expect(host.getByText(/Table 1: running, 1 of 2/)).toBeVisible();
  await expect(host.getByText("Not at a table:")).toBeVisible();
  await host.locator(".toolbar__waiting select").selectOption({ label: "Table 1" });
  await expect(host.getByText(/Table 1: running, 2 of 2/)).toBeVisible();
  await expect(host.getByText("Not at a table:")).toHaveCount(0);

  await host.getByLabel("Minutes on the timer").fill("2");
  await host.getByRole("button", { name: "Start timer for every table" }).click();
  for (const page of [host, ...guests]) {
    await expect(page.getByRole("timer")).toHaveText(/^[12]:\d\d$/);
  }
});
