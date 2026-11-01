import { defineConfig, devices } from "@playwright/test";

/** Tests that put three windows on a thirty-six-card table. */
const HEAVY = /a trade is offered|a card goes out of the hand/;

export default defineConfig({
  testDir: "client/tests",
  // WebKit on a shared Linux runner is several times slower than Chromium, and
  // a test here runs three browser windows at once.
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://127.0.0.1:8765",
  },
  projects: [
    { name: "browser", testIgnore: /performance\.spec\.ts/ },
    // Safari's engine, on a laptop and on an iPad in both orientations: the
    // iPad and the laptop are the devices the sandbox is run on.
    // The three-window trading tests deal thirty-six cards into three windows of
    // one browser; WebKit on a shared runner throttles the two in the
    // background and cannot finish them reliably, so those run in Chromium only.
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
      testMatch: /(access|resilience|macros|home)\.spec\.ts/,
      grepInvert: HEAVY,
    },
    {
      name: "ipad-portrait",
      use: { ...devices["iPad (gen 7)"] },
      testMatch: /access\.spec\.ts/,
      grepInvert: HEAVY,
    },
    {
      name: "ipad-landscape",
      use: { ...devices["iPad (gen 7) landscape"] },
      testMatch: /access\.spec\.ts/,
      grepInvert: HEAVY,
    },
    // The frame-rate test measures the renderer, so it runs on its own once
    // every other browser test has finished. Run alongside them, it measures
    // how busy the machine is instead.
    {
      name: "frame-rate",
      testMatch: /performance\.spec\.ts/,
      dependencies: ["browser"],
    },
  ],
  webServer: {
    command: "uv run uvicorn sandbox.web.app:app --host 127.0.0.1 --port 8765",
    // The fixture games (tests/games), so the browser tests have a game to play.
    env: { SANDBOX_EXTRA_GAMES: "tests/games" },
    url: "http://127.0.0.1:8765",
    reuseExistingServer: false,
  },
});
