import { expect, test } from "@playwright/test";

test("serves the Ethics Sandbox landing page", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Ethics Sandbox" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-table-client", "ready");
});
