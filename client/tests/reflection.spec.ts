import { expect, test } from "@playwright/test";
import { openFromLanding } from "./rooms";

/** The reflection page and the side panel's debrief links. */

test("a reflection can be written before any activity, and no debrief link leads nowhere", async ({
  browser,
}) => {
  const page = await (await browser.newContext()).newPage();
  await openFromLanding(page, "Value Cards");
  await page.getByLabel("Your name").fill("Ines");
  await page.getByRole("button", { name: "Join table" }).click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  const code = page.url().split("/t/")[1]!;

  await expect(page.getByRole("link", { name: "Write a reflection" })).toBeVisible();
  // Nothing has been played and nothing opened, so there is no debrief link.
  await expect(page.locator("#room-debrief-links")).toBeHidden();
  await expect(page.getByRole("link", { name: "Debriefs" })).toHaveCount(0);

  await page.goto(`/t/${code}/reflect`);
  await page.getByLabel("Anything you want to note").fill("Something to come back to.");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(page.getByText("Something to come back to. (free writing)")).toBeVisible();
});

test("once an activity with questions is played, the panel offers to respond to them", async ({
  browser,
}) => {
  const person = async (path: string, name: string) => {
    const page = await (await browser.newContext()).newPage();
    if (path === "") {
      await openFromLanding(page, "Value Cards");
    } else {
      await page.goto(path);
    }
    await page.getByLabel("Your name").fill(name);
    await page.getByRole("button", { name: "Join table" }).click();
    await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
    return page;
  };
  const ines = await person("", "Ines");
  const code = ines.url().split("/t/")[1]!;
  const tomas = await person(`/join?code=${code}`, "Tomas");
  const wren = await person(`/join?code=${code}`, "Wren");
  await ines.getByRole("button", { name: "Start Value Cards Trading", exact: true }).click();
  await tomas.getByRole("button", { name: "Join" }).click();
  await wren.getByRole("button", { name: "Join" }).click();
  await expect(ines.getByRole("button", { name: "Deal 12 each" })).toBeVisible();

  // The page asks again whenever it is looked at again.
  await ines.evaluate(() => window.dispatchEvent(new Event("focus")));
  const respond = ines.getByRole("link", { name: "Respond to debrief questions" });
  await expect(respond).toBeVisible();
  await expect(respond).toHaveAttribute("href", `/t/${code}/reflect#questions`);
  // Nobody is facilitating, so no debrief has been opened to read.
  await expect(ines.locator('[data-room-link="debrief"]')).toHaveCount(0);
});
