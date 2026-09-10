import { expect, test } from "@playwright/test";

test("renders every design-system section", async ({ page }) => {
  await page.goto("/styleguide");

  await expect(page.getByRole("heading", { name: "A quiet room for consequential questions." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Button" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tabletop pieces" })).toBeVisible();
  await expect(page.locator(".avatar")).toHaveCount(6);
});

test("keeps card content legible and contained at sixty percent", async ({ page }) => {
  await page.goto("/styleguide");

  const card = page.getByTestId("card-at-60-percent");
  const copy = card.locator(".piece__copy");
  await expect(card).toBeVisible();
  await expect(copy).toBeVisible();

  const metrics = await card.evaluate((element) => {
    const copyElement = element.querySelector<HTMLElement>(".piece__copy");
    const cardBox = element.getBoundingClientRect();
    const copyBox = copyElement?.getBoundingClientRect();
    return {
      zoom: Number.parseFloat(getComputedStyle(element.parentElement!).zoom),
      fontSize: Number.parseFloat(getComputedStyle(element).fontSize),
      cardWidth: cardBox.width,
      copyIsContained: Boolean(
        copyBox &&
        copyBox.left >= cardBox.left &&
        copyBox.right <= cardBox.right &&
        copyBox.top >= cardBox.top &&
        copyBox.bottom <= cardBox.bottom,
      ),
    };
  });

  expect(metrics.zoom).toBe(0.6);
  expect(metrics.fontSize).toBeGreaterThanOrEqual(16);
  expect(metrics.cardWidth).toBeGreaterThanOrEqual(120);
  expect(metrics.copyIsContained).toBe(true);
});

test("honors system dark mode and explicit theme overrides", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/styleguide");

  const root = page.locator("html");
  const systemDark = await root.evaluate((element) => getComputedStyle(element).getPropertyValue("--surface-page"));
  await root.evaluate((element) => element.setAttribute("data-theme", "light"));
  const explicitLight = await root.evaluate((element) => getComputedStyle(element).getPropertyValue("--surface-page"));
  await root.evaluate((element) => element.setAttribute("data-theme", "dark"));
  const explicitDark = await root.evaluate((element) => getComputedStyle(element).getPropertyValue("--surface-page"));

  expect(systemDark).not.toBe(explicitLight);
  expect(explicitDark).toBe(systemDark);
});

test("shows a focus ring on interactive controls", async ({ page }) => {
  await page.goto("/styleguide");
  const button = page.getByRole("button", { name: "Primary" }).first();

  await button.focus();
  await expect(button).toBeFocused();
  const focusShadow = await button.evaluate((element) => getComputedStyle(element).boxShadow);
  expect(focusShadow).not.toBe("none");
});
