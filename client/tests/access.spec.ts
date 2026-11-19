import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { newRoom, openFromLanding, type RoomKind, openControls } from "./rooms";

/** Accessibility, touch and small screens. */

async function openRoom(
  browser: Browser,
  name: string,
  options = {},
  kind: RoomKind = "Test room",
): Promise<Page> {
  const page = await (await browser.newContext(options)).newPage();
  await openFromLanding(page, kind);
  await page.getByLabel("Your name").fill(name);
  await page.getByRole("button", { name: "Join table" }).click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  await openControls(page);
  await expect(page.locator("html[data-table-client='ready']")).toHaveCount(1);
  return page;
}

async function violations(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations.map(
    (v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(" | ")})`,
  );
}

for (const path of ["/", "/help", "/join", "/health", "/exercises/value-cards-trading"]) {
  for (const scheme of ["light", "dark"] as const) {
    test(`axe finds nothing on ${path} (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(path);
      expect(await violations(page)).toEqual([]);
    });
  }
}

test("axe finds nothing on a table with an activity running", async ({ browser }) => {
  const page = await openRoom(browser, "Ines", {}, "Value Cards");
  await expect(page.locator(".tabletop__pieces-layer")).toBeAttached();
  // The debrief has its own heading, below the activities.
  const debrief = page.getByRole("heading", { name: "Debrief", exact: true });
  await expect(debrief).toBeVisible();
  await expect(
    page.locator(".room-panel__heading + .activity-cards .activity-card__title"),
  ).toHaveText("Value Cards Trading debrief");
  expect(await violations(page)).toEqual([]);
  await page.getByRole("button", { name: "Start Value Cards Trading", exact: true }).click();
  await expect(page.getByText(/Value Cards Trading: /)).toBeVisible();
  expect(await violations(page)).toEqual([]);
});

test("the unknown-room page says what happened and what to do", async ({ page }) => {
  const response = await page.goto("/t/ZZZZZZ");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "We couldn't find that" })).toBeVisible();
  await expect(page.getByText("Check the room code")).toBeVisible();
  expect(await violations(page)).toEqual([]);
});

test("reduced motion removes transitions and animations", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/join");
  const longest = await page.evaluate(() => {
    let longest = 0;
    for (const el of Array.from(document.querySelectorAll("*"))) {
      const style = getComputedStyle(el);
      for (const value of [style.transitionDuration, style.animationDuration]) {
        for (const part of value.split(",")) {
          const seconds = part.trim().endsWith("ms")
            ? parseFloat(part) / 1000
            : parseFloat(part);
          if (Number.isFinite(seconds)) longest = Math.max(longest, seconds);
        }
      }
    }
    return longest;
  });
  expect(longest).toBeLessThan(0.01);
});

test("the side panel starts closed on a laptop or tablet, and sits below the table on a phone", async ({
  browser,
}) => {
  const wide = await (await browser.newContext()).newPage();
  await openFromLanding(wide, "Test room");
  await wide.getByLabel("Your name").fill("Ines");
  await wide.getByRole("button", { name: "Join table" }).click();
  await wide.waitForURL(/\/t\/[A-Z0-9]{6}$/);
  const toggle = wide.getByRole("button", { name: "Activities" });
  const viewport = wide.viewportSize();
  if (viewport !== null && viewport.width > 768) {
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(wide.locator("#room-panel")).toBeHidden();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(wide.getByRole("button", { name: "Start Pairs", exact: true })).toBeVisible();
    // Closing it hides it again, and a reload starts it closed.
    await wide.getByRole("button", { name: "Activities" }).click();
    await expect(wide.locator("#room-panel")).toBeHidden();
    await wide.getByRole("button", { name: "Activities" }).click();
    await wide.reload();
    await expect(wide.locator("#room-panel")).toBeHidden();
  }

  const phone = await openRoom(browser, "Tomas", {
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 800 },
  });
  await expect(phone.getByRole("button", { name: "Activities" })).toBeHidden();
  const start = phone.getByRole("button", { name: "Start Pairs", exact: true });
  await expect(start).toBeAttached();
  const table = await phone.locator(".room__table").boundingBox();
  const panel = await phone.locator("#room-panel").boundingBox();
  expect(table).not.toBeNull();
  expect(panel).not.toBeNull();
  expect(panel!.y).toBeGreaterThanOrEqual(table!.y + table!.height - 1);
  // Nothing scrolls the page sideways.
  const overflow = await phone.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test("the Activities button is marked while a sign-up it has not shown is open", async ({
  browser,
}) => {
  const host = await openRoom(browser, "Ines");
  const code = host.url().split("/t/")[1]!;
  const guest = await (await browser.newContext()).newPage();
  await guest.goto(`/join?code=${code}`);
  await guest.locator('input[name="display_name"]').fill("Tomas");
  await guest.locator('form button[type="submit"]').click();
  await guest.waitForURL(new RegExp(`/t/${code}$`));
  const toggle = guest.getByRole("button", { name: "Activities" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(guest.locator(".room__panel-toggle-mark-new")).toHaveCount(0);

  await host.getByRole("button", { name: "Start Pairs", exact: true }).click();
  await expect(guest.locator(".room__panel-toggle-mark-new")).toHaveCount(1);
  await expect(toggle).toHaveAccessibleName(/a new sign-up/);

  // Opening the panel shows it, and the mark goes, even once closed again.
  await toggle.click();
  await expect(guest.locator(".room__panel-toggle-mark-new")).toHaveCount(0);
  await toggle.click();
  await expect(guest.locator(".room__panel-toggle-mark-new")).toHaveCount(0);
});

test("pages work with text at 200 percent", async ({ page }) => {
  // 200% text zoom on a 1280 x 800 laptop is, to the layout, a 640 x 400 window.
  await page.setViewportSize({ width: 640, height: 400 });
  for (const path of ["/", "/help", "/join", "/health"]) {
    await page.goto(path);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});

test("on a touch screen every control is at least 44 px", async ({ browser }) => {
  const page = await openRoom(browser, "Ines", {
    hasTouch: true,
    isMobile: true,
    viewport: { width: 820, height: 1180 },
  });
  const small = await page.evaluate(() => {
    const found: string[] = [];
    for (const el of Array.from(
      document.querySelectorAll("button, select, input:not([type=hidden]), summary"),
    )) {
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0) continue;
      if (el.closest(".visually-hidden")) continue;
      if (box.height < 43.5 || box.width < 43.5) {
        found.push(`${el.tagName} "${(el.textContent ?? "").trim().slice(0, 30)}" ${Math.round(box.width)}x${Math.round(box.height)}`);
      }
    }
    return found;
  });
  expect(small).toEqual([]);
});

test("on a phone the public table is read-only and the page says a tablet is better", async ({
  browser,
}) => {
  const context = await browser.newContext({
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 800 },
  });
  const join = await context.newPage();
  await join.goto("/join");
  await expect(join.locator("[data-device-note]")).toContainText("tablet or laptop works best");

  const page = await openRoom(browser, "Ines", {
    hasTouch: true,
    isMobile: true,
    viewport: { width: 390, height: 800 },
  });
  await expect(page.locator(".tabletop__pieces-layer .piece").first()).toBeAttached();
  const events = await page.evaluate(() => {
    const layer = document.querySelector(".tabletop__pieces-layer");
    return layer ? getComputedStyle(layer.querySelector(".piece") ?? layer).pointerEvents : "none";
  });
  expect(events).toBe("none");
});

// -- trading and announcing, by keyboard and by touch --------------------------------------

async function startTrading(browser: Browser, touch: boolean) {
  const options = touch ? { hasTouch: true, isMobile: false, viewport: { width: 1180, height: 820 } } : {};
  const person = async (path: string, name: string): Promise<Page> => {
    const page = await (await browser.newContext(options)).newPage();
    await page.goto(path);
    await page.locator('input[name="display_name"]').fill(name);
    await page.locator('form button[type="submit"]').click();
    await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
    await openControls(page);
    return page;
  };
  const ines = await person(await newRoom(browser, "Value Cards"), "Ines");
  const code = ines.url().split("/t/")[1]!;
  const tomas = await person(`/join?code=${code}`, "Tomas");
  const wren = await person(`/join?code=${code}`, "Wren");
  await ines.getByRole("button", { name: "Start Value Cards Trading", exact: true }).click();
  await tomas.getByRole("button", { name: "Join" }).click();
  await wren.getByRole("button", { name: "Join" }).click();
  await ines.getByRole("button", { name: "Deal 6 each" }).click();
  return { ines, tomas, wren };
}

test("a trade is offered and answered with the keyboard alone", async ({ browser }) => {
  const { ines, tomas, wren } = await startTrading(browser, false);
  const mine = ines.locator('.tabletop__pieces-layer .piece[data-zone-id$=":hand-seat-1"]');
  const theirs = ines.locator('.tabletop__pieces-layer .piece[data-zone-id$=":hand-seat-2"]');
  await expect(mine).toHaveCount(6);

  await mine.first().focus();
  await ines.keyboard.press("x");
  await theirs.first().focus();
  await ines.keyboard.press("Shift+X");
  await expect(ines.locator("[data-announcer]")).toContainText("2 selected");

  await ines.getByRole("button", { name: "Offer a trade" }).focus();
  await ines.keyboard.press("Enter");
  await expect(wren.locator("[data-offer-id]")).toHaveCount(1);
  await tomas.getByRole("button", { name: "Accept" }).focus();
  await tomas.keyboard.press("Enter");
  await expect(ines.locator("[data-offer-id]")).toHaveCount(0);
  // Said out loud, to everyone, in the live region.
  await expect(wren.locator("[data-announcer]")).toContainText("Ines and Tomas have traded cards.");
});

test("a trade is offered and answered by touch alone", async ({ browser }) => {
  const { ines, tomas, wren } = await startTrading(browser, true);
  const mine = ines.locator('.tabletop__pieces-layer .piece[data-zone-id$=":hand-seat-1"]');
  const theirs = ines.locator('.tabletop__pieces-layer .piece[data-zone-id$=":hand-seat-2"]');
  await expect(mine).toHaveCount(6);

  await mine.first().tap();
  await theirs.first().tap();
  await ines.getByRole("button", { name: "Offer a trade" }).tap();
  await expect(wren.locator("[data-offer-id]")).toHaveCount(1);
  await tomas.getByRole("button", { name: "Accept" }).tap();
  await expect(ines.locator("[data-offer-id]")).toHaveCount(0);
});

test("the announcer says joins, and does not say ordinary moves", async ({ browser }) => {
  const host = await openRoom(browser, "Ines");
  const guest = await (await browser.newContext()).newPage();
  await guest.goto(`/join?code=${host.url().split("/t/")[1]}`);
  await guest.locator('input[name="display_name"]').fill("Tomas");
  await guest.locator('form button[type="submit"]').click();
  await expect(host.locator(".tabletop__notices")).toContainText("Tomas has joined the table.");

  const announcer = host.locator("[data-announcer]");
  const before = await announcer.textContent();
  const token = host.locator(".tabletop__pieces-layer .piece--token").first();
  const box = (await token.boundingBox())!;
  await host.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await host.mouse.down();
  await host.mouse.move(box.x + 80, box.y + 40, { steps: 6 });
  await host.mouse.up();
  await host.waitForTimeout(500);
  expect(await announcer.textContent()).toBe(before);
});

test("a card goes out of the hand and back into it with the keyboard alone", async ({
  browser,
}) => {
  const person = async (path: string, name: string): Promise<Page> => {
    const page = await (await browser.newContext()).newPage();
    await page.goto(path);
    await page.locator('input[name="display_name"]').fill(name);
    await page.locator('form button[type="submit"]').click();
    await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
    await openControls(page);
    return page;
  };
  const host = await person(await newRoom(browser, "Test room"), "Ines");
  const guest = await person(`/join?code=${host.url().split("/t/")[1]}`, "Tomas");
  await host.getByRole("button", { name: "Start Pairs", exact: true }).click();
  await guest.getByRole("button", { name: "Join" }).click();
  await expect(host.getByText(/Pairs: running/)).toBeVisible();
  await host.getByRole("button", { name: "Deal three each" }).click();

  const hand = host.locator(".hand-tray__fan .piece");
  await expect(hand).toHaveCount(3);
  await host.getByRole("button", { name: "Ines's Hand", exact: true }).click();
  const id = (await hand.first().getAttribute("data-piece-id"))!;
  const choose = async (label: string): Promise<void> => {
    const item = host.locator(".table-menu__item", { hasText: label }).first();
    for (let i = 0; i < 40; i += 1) {
      if (await item.evaluate((el) => el === document.activeElement)) break;
      await host.keyboard.press("ArrowDown");
    }
    await host.keyboard.press("Enter");
  };

  await host.locator(`[data-piece-id="${id}"]`).focus();
  await host.keyboard.press("m");
  await choose("Pairs caught");
  await expect(host.locator(`.tabletop__pieces-layer [data-piece-id="${id}"]`)).toBeAttached();
  await expect(hand).toHaveCount(2);

  await host.locator(`.tabletop__pieces-layer [data-piece-id="${id}"]`).focus();
  await host.keyboard.press("m");
  await choose("Send to my hand");
  await expect(hand).toHaveCount(3);
});

test("a choice made for an activity stays chosen while the toolbar redraws", async ({ browser }) => {
  const host = await openRoom(browser, "Ines");
  const select = host.getByLabel("Choosy: Side");
  await select.selectOption("south");
  // Someone arriving redraws everyone's toolbar.
  const guest = await (await browser.newContext()).newPage();
  await guest.goto(`/join?code=${host.url().split("/t/")[1]}`);
  await guest.locator('input[name="display_name"]').fill("Tomas");
  await guest.locator('form button[type="submit"]').click();
  await expect(host.locator(".tabletop__notices")).toContainText("Tomas has joined the table.");
  await expect(select).toHaveValue("south");
});
