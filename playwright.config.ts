import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "client/tests",
  use: {
    baseURL: "http://127.0.0.1:8765",
  },
  projects: [
    { name: "browser", testIgnore: /performance\.spec\.ts/ },
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
