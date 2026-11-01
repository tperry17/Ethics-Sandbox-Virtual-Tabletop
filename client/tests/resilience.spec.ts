import { expect, test, type Browser, type Page, type WebSocketRoute } from "@playwright/test";

/**
 * A flaky network, a locked iPad, a refresh, two hands on one piece. The
 * socket is routed through a proxy the test can cut, so "offline" is
 * something the test decides rather than something it hopes for.
 */

interface Wire {
  /** Everything the server has sent this page, in order. */
  received: string[];
  /** Drop the socket, and refuse new ones until `restore`. */
  cut(): void;
  restore(): void;
}

async function watch(page: Page): Promise<Wire> {
  let offline = false;
  let current: WebSocketRoute | null = null;
  const wire: Wire = {
    received: [],
    cut() {
      offline = true;
      current?.close();
      current = null;
    },
    restore() {
      offline = false;
    },
  };
  await page.routeWebSocket(/\/ws\/t\//, (route) => {
    if (offline) {
      route.close();
      return;
    }
    const server = route.connectToServer();
    current = route;
    route.onMessage((message) => server.send(message));
    server.onMessage((message) => {
      wire.received.push(String(message));
      route.send(message);
    });
    route.onClose(() => server.close());
    server.onClose((code, reason) => route.close({ code, reason }));
  });
  return wire;
}

async function openRoom(
  browser: Browser,
  name: string,
): Promise<{ page: Page; code: string; wire: Wire }> {
  const page = await (await browser.newContext()).newPage();
  const wire = await watch(page);
  await page.goto("/start");
  await page.getByLabel("Your name").fill(name);
  await page.getByRole("button", { name: "Open a room" }).click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  await expect(page.locator(".tabletop__pieces-layer .piece").first()).toBeAttached();
  return { page, code: page.url().split("/t/")[1]!, wire };
}

async function join(browser: Browser, code: string, name: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(`/join?code=${code}`);
  await page.locator('input[name="display_name"]').fill(name);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(new RegExp(`/t/${code}$`));
  await expect(page.locator(".tabletop__pieces-layer .piece").first()).toBeAttached();
  return page;
}

const positionOf = (page: Page, id: string): Promise<[number, number] | null> =>
  page.evaluate((pieceId) => window.ethicsSandboxTable!.visualPositionOf(pieceId), id);

async function firstTokenId(page: Page): Promise<string> {
  const id = await page.locator(".tabletop__pieces-layer .piece--token").first().getAttribute("data-piece-id");
  expect(id).not.toBeNull();
  return id!;
}

test("a tab that was backgrounded catches up by replay, not a reload", async ({ browser }) => {
  const { page: ana, code, wire } = await openRoom(browser, "Ana");
  const bo = await join(browser, code, "Bo");
  const id = await firstTokenId(ana);

  wire.cut();
  // Bo moves a piece while Ana's tab is asleep.
  await bo.locator(`[data-piece-id="${id}"]`).focus();
  for (let i = 0; i < 4; i += 1) await bo.keyboard.press("ArrowRight");
  const target = await expect
    .poll(() => positionOf(bo, id), { timeout: 5000 })
    .not.toBeNull()
    .then(() => positionOf(bo, id));
  const before = wire.received.length;
  wire.restore();

  await expect
    .poll(async () => (await positionOf(ana, id))?.[0] ?? 0, { timeout: 15000 })
    .toBeCloseTo(target![0], 0);
  const after = wire.received.slice(before).map((text) => JSON.parse(text).type as string);
  expect(after).not.toContain("snapshot");
  expect(after).toContain("patches");
  await expect(ana.locator("[data-status='connected']")).toBeVisible();
});

test("thirty seconds offline recovers without a reload, and nothing is left hanging", async ({
  browser,
}) => {
  test.setTimeout(120_000);
  const { page: ana, wire } = await openRoom(browser, "Ana");
  const id = await firstTokenId(ana);
  await ana.evaluate(() => {
    (window as unknown as { stayedLoaded: boolean }).stayedLoaded = true;
  });

  wire.cut();
  // An intent sent into the dark is answered, within eight seconds, with a sentence.
  await ana.locator(`[data-piece-id="${id}"]`).focus();
  await ana.keyboard.press("ArrowRight");
  await expect(ana.getByText("That did not reach the table. Please try again.")).toBeVisible({
    timeout: 12_000,
  });
  await ana.waitForTimeout(20_000);
  wire.restore();

  await expect(ana.locator("[data-status='connected']")).toBeVisible({ timeout: 20_000 });
  expect(
    await ana.evaluate(() => (window as unknown as { stayedLoaded?: boolean }).stayedLoaded),
  ).toBe(true);
  // The table works again.
  await ana.locator(`[data-piece-id="${id}"]`).focus();
  const start = (await positionOf(ana, id))![0];
  await ana.keyboard.press("ArrowRight");
  await expect.poll(async () => (await positionOf(ana, id))![0]).toBeGreaterThan(start);
});

test("a refresh keeps the seat, the hand and the view", async ({ browser }) => {
  const { page: host, code } = await openRoom(browser, "Ines");
  const guest = await join(browser, code, "Tomas");
  await host.getByLabel("Activity to start").selectOption("pairs");
  await host.getByRole("button", { name: "Start this activity" }).click();
  await guest.getByRole("button", { name: "Join" }).click();
  await expect(host.getByText(/Pairs: running/)).toBeVisible();
  await host.getByRole("button", { name: "Deal three each" }).click();
  const hand = host.locator(".hand-tray__fan .piece .piece__title");
  await expect(hand).toHaveCount(3);
  const titles = (await hand.allTextContents()).sort();
  const seat = await host.locator("#table-root").getAttribute("data-seat-id");

  await host.getByRole("button", { name: "Zoom in" }).or(host.getByRole("button", { name: "+" })).click();
  const kept = (): Promise<{ scale: number; centreX: number; centreY: number }> =>
    host.evaluate((roomCode) => JSON.parse(window.localStorage.getItem(`sandbox:view:${roomCode}`)!), code);
  await expect.poll(() => kept().catch(() => null)).not.toBeNull();
  const view = await kept();

  await host.reload();
  await expect(host.locator(".hand-tray__fan .piece .piece__title")).toHaveCount(3);
  expect((await host.locator(".hand-tray__fan .piece .piece__title").allTextContents()).sort()).toEqual(titles);
  expect(await host.locator("#table-root").getAttribute("data-seat-id")).toBe(seat);
  // The same place on the table, whatever size the window came back at.
  await expect.poll(async () => (await kept().catch(() => view)).scale).toBeCloseTo(view.scale, 3);
  const after = await kept();
  expect(Math.abs(after.centreX - view.centreX)).toBeLessThan(2);
  expect(Math.abs(after.centreY - view.centreY)).toBeLessThan(2);
});

test("a view kept in storage that cannot be read does not break the table", async ({ browser }) => {
  const context = await browser.newContext();
  await context.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new Error("storage is blocked");
      },
    });
  });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/start");
  await page.getByLabel("Your name").fill("Ines");
  await page.getByRole("button", { name: "Open a room" }).click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  await expect(page.locator(".tabletop__pieces-layer .piece").first()).toBeAttached();
  expect(errors).toEqual([]);
});

test("two people dragging the same piece settle without a glitch", async ({ browser }) => {
  const { page: ana, code } = await openRoom(browser, "Ana");
  const bo = await join(browser, code, "Bo");
  const id = await firstTokenId(ana);
  const errors: string[] = [];
  for (const page of [ana, bo]) page.on("pageerror", (error) => errors.push(error.message));

  const centre = async (page: Page) => {
    const box = (await page.locator(`[data-piece-id="${id}"]`).boundingBox())!;
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  };
  const start = await centre(ana);
  const drag = async (page: Page, dx: number) => {
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(start.x + dx, start.y + 40, { steps: 10 });
    await page.mouse.up();
  };
  await Promise.all([drag(ana, 120), drag(bo, -120)]);

  await expect(ana.locator(`[data-piece-id="${id}"].is-held`)).toHaveCount(0, { timeout: 10_000 });
  await expect(bo.locator(`[data-piece-id="${id}"].is-held`)).toHaveCount(0, { timeout: 10_000 });
  await expect
    .poll(async () => JSON.stringify(await positionOf(ana, id)) === JSON.stringify(await positionOf(bo, id)))
    .toBe(true);
  expect(errors).toEqual([]);
});

test("a table that will not open for you says so, and stops retrying", async ({ browser }) => {
  const { page, wire } = await openRoom(browser, "Ana");
  await page.context().clearCookies();
  wire.cut();
  wire.restore();
  await expect(page.locator("[data-status='refused']")).toHaveText("Not in this room", {
    timeout: 20_000,
  });
  await expect(page.getByText(/would not open for you/)).toBeVisible();
});
