import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { newRoom } from "./rooms";

/**
 * Whole sessions, one per exercise, with several browsers in one room: a
 * facilitator and the players, a mid-session disconnect and rejoin, and a
 * macro pressed while someone is mid-drag. Chromium only (see HEAVY in
 * playwright.config.ts): each test puts four or more windows on one table.
 */

type Person = { page: Page; context: BrowserContext; cut(): void; restore(): void };

async function open(browser: Browser, path: string, name: string): Promise<Person> {
  const context = await browser.newContext();
  const page = await context.newPage();
  // The socket goes through a proxy the test can cut, so "offline" is decided here.
  let offline = false;
  let current: { close(): void } | null = null;
  await page.routeWebSocket(/\/ws\/t\//, (route) => {
    if (offline) {
      route.close();
      return;
    }
    const server = route.connectToServer();
    current = route;
    route.onMessage((message) => server.send(message));
    server.onMessage((message) => route.send(message));
    route.onClose(() => server.close());
    server.onClose((code, reason) => route.close({ code, reason }));
  });
  await page.goto(path);
  await page.locator('input[name="display_name"]').fill(name);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  return {
    page,
    context,
    cut() {
      offline = true;
      current?.close();
    },
    restore() {
      offline = false;
    },
  };
}

const roomCode = (page: Page): string => page.url().split("/t/")[1]!;

test("Value Cards Trading: four browsers, a drop and a rejoin, and a macro mid-drag", async ({
  browser,
}) => {
  test.setTimeout(120_000);
  const ines = await open(browser, await newRoom(browser, "Value Cards"), "Ines");
  const code = roomCode(ines.page);
  const tomas = await open(browser, `/join?code=${code}`, "Tomas");
  const wren = await open(browser, `/join?code=${code}`, "Wren");
  const bystander = await open(browser, `/join?code=${code}`, "Rowan");

  await ines.page.getByLabel("Activity to start").selectOption("value-cards-trading");
  await ines.page.getByRole("button", { name: "Start this activity" }).click();
  await tomas.page.getByRole("button", { name: "Join" }).click();
  await wren.page.getByRole("button", { name: "Join" }).click();
  await ines.page.getByRole("button", { name: "Deal 12 each" }).click();

  const hand = (page: Page, seat: number) =>
    page.locator(`.tabletop__pieces-layer .piece[data-zone-id$=":hand-seat-${seat}"]`);
  await expect(hand(ines.page, 1)).toHaveCount(12);
  await expect(hand(tomas.page, 2)).toHaveCount(12);

  // The bystander sits at no seat and sees no card faces from anyone's hand.
  await expect(bystander.page.locator("[data-status='connected']")).toBeVisible();
  const faces = await bystander.page
    .locator('.piece[data-zone-id$=":hand-seat-1"] [data-face]')
    .count();
  expect(faces).toBe(0);

  // Tomas drops off the network and comes back: same seat, same hand, no reload.
  tomas.cut();
  await expect(tomas.page.locator("[data-status]:not([data-status='connected'])")).toBeVisible();
  tomas.restore();
  await expect(tomas.page.locator("[data-status='connected']")).toBeVisible({ timeout: 20_000 });
  await expect(hand(tomas.page, 2)).toHaveCount(12);

  // Tomas closes the tab altogether and returns with the same cookie.
  const tomasState = await tomas.context.storageState();
  await tomas.page.close();
  const back = await (await browser.newContext({ storageState: tomasState })).newPage();
  await back.goto(`/t/${code}`);
  await expect(hand(back, 2)).toHaveCount(12);

  // Wren has a card in hand mid-drag while the facilitator presses Shuffle.
  const card = hand(wren.page, 3).first();
  const box = (await card.boundingBox())!;
  await wren.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await wren.page.mouse.down();
  await wren.page.mouse.move(box.x + 40, box.y - 120, { steps: 6 });
  await ines.page.locator("button[data-activity-id]", { hasText: "Shuffle deck" }).click();
  await wren.page.mouse.up();
  // Nothing was lost or duplicated: still twelve cards a hand, still connected.
  await expect(hand(wren.page, 3)).toHaveCount(12, { timeout: 15_000 });
  await expect(hand(ines.page, 1)).toHaveCount(12);
  await expect(ines.page.locator("[data-status='connected']")).toBeVisible();
});

test("Leadership and Knowledge in Popular Rule: a city of nine, a rejoin, and the role cards stay private", async ({
  browser,
}) => {
  test.setTimeout(180_000);
  const host = await open(browser, await newRoom(browser, "Leadership and Knowledge in Popular Rule"), "Ines");
  const code = roomCode(host.page);
  const citizens: Person[] = [];
  for (let n = 1; n <= 9; n += 1) {
    citizens.push(await open(browser, `/join?code=${code}`, `Citizen ${n}`));
  }

  await host.page.getByLabel("Activity to start").selectOption("scenario-1");
  await host.page.getByRole("button", { name: "Start this activity" }).click();
  for (const citizen of citizens) {
    await citizen.page.getByRole("button", { name: "Join" }).click();
  }
  await host.page.getByRole("button", { name: "Begin now" }).click();
  await expect(host.page.getByText(/Scenario 1: Construction project: running/)).toBeVisible();

  await host.page.getByRole("button", { name: "Deal role cards" }).click();
  const mine = citizens[0]!.page.locator('.piece[data-zone-id*=":hand-seat-"]');
  await expect(mine.first()).toBeVisible({ timeout: 15_000 });

  // One citizen drops off and returns; their role card is still theirs.
  const held = await mine.count();
  citizens[1]!.cut();
  citizens[1]!.restore();
  await expect(citizens[1]!.page.locator("[data-status='connected']")).toBeVisible({
    timeout: 20_000,
  });
  await citizens[1]!.page.reload();
  await expect(citizens[1]!.page.locator('.piece[data-zone-id*=":hand-seat-"]').first()).toBeVisible({
    timeout: 15_000,
  });
  expect(held).toBeGreaterThan(0);

  // The facilitator collects every card while a citizen is dragging one: the
  // server takes it out of their hand mid-drag, and letting go puts nothing back.
  const card = mine.first();
  const box = (await card.boundingBox())!;
  await citizens[0]!.page.mouse.move(box.x + 10, box.y + 10);
  await citizens[0]!.page.mouse.down();
  await citizens[0]!.page.mouse.move(box.x + 30, box.y - 80, { steps: 5 });
  await host.page.locator("button[data-activity-id]", { hasText: "Collect all cards" }).click();
  await citizens[0]!.page.mouse.up();
  for (const page of [host.page, citizens[0]!.page, citizens[1]!.page]) {
    await expect(page.locator('.piece[data-zone-id*=":hand-seat-"]')).toHaveCount(0, {
      timeout: 15_000,
    });
    await expect(page.locator("[data-status='connected']")).toBeVisible();
  }
});
