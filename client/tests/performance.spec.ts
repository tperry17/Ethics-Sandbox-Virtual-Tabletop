import { expect, test } from "@playwright/test";

/**
 * The frame budget CLAUDE.md records: three hundred pieces on the table,
 * one of them being dragged, and the frame rate that survives it.
 *
 * The assertion is a floor, not the target. The target is 60fps on a
 * five-year-old laptop; the floor is what distinguishes "this machine is
 * busy" from "something in the render path started rebuilding the table".
 */
test("holds its frame rate with three hundred pieces and one in motion", async ({
  page,
}) => {
  test.slow();
  await page.goto("/table-preview?pieces=300&measure=1");

  await expect(page.locator(".tabletop__pieces-layer .piece")).toHaveCount(317);
  await expect(page.locator("html")).toHaveAttribute("data-table-fps", /\d/, {
    timeout: 15_000,
  });

  const fps = Number.parseFloat(
    (await page.locator("html").getAttribute("data-table-fps")) ?? "0",
  );
  const worst = Number.parseFloat(
    (await page.locator("html").getAttribute("data-table-worst-frame-ms")) ?? "0",
  );
  test.info().annotations.push({
    type: "measured",
    description: `${fps.toFixed(1)} fps, 95th-percentile frame ${worst.toFixed(1)} ms`,
  });
  expect(fps).toBeGreaterThan(40);
});
