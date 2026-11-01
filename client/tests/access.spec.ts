import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";

/** Accessibility, touch and small screens. */

async function openRoom(browser: Browser, name: string, options = {}): Promise<Page> {
  const page = await (await browser.newContext(options)).newPage();
  await page.goto("/start");
  await page.getByLabel("Your name").fill(name);
  await page.getByRole("button", { name: "Open a room" }).click();
  await page.waitForURL(/\/t\/[A-Z0-9]{6}$/);
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

for (const path of ["/", "/help", "/join", "/health", "/start", "/exercises/value-cards-trading"]) {
  for (const scheme of ["light", "dark"] as const) {
    test(`axe finds nothing on ${path} (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(path);
      expect(await violations(page)).toEqual([]);
    });
  }
}

test("axe finds nothing on a table with an activity running", async ({ browser }) => {
  const page = await openRoom(browser, "Ines");
  await expect(page.locator(".tabletop__pieces-layer")).toBeAttached();
  expect(await violations(page)).toEqual([]);
  await page.getByLabel("Activity to start").selectOption("value-cards-trading");
  await page.getByRole("button", { name: "Start this activity" }).click();
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

test("pages work with text at 200 percent", async ({ page }) => {
  // 200% text zoom on a 1280 x 800 laptop is, to the layout, a 640 x 400 window.
  await page.setViewportSize({ width: 640, height: 400 });
  for (const path of ["/", "/help", "/join", "/start", "/health"]) {
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
  const events = await page.evaluate(() => {
    const layer = document.querySelector(".tabletop__pieces-layer");
    return layer ? getComputedStyle(layer.querySelector(".piece") ?? layer).pointerEvents : "none";
  });
  expect(events).toBe("none");
});
