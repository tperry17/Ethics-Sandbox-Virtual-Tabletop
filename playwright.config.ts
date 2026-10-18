import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "client/tests",
  use: {
    baseURL: "http://127.0.0.1:8765",
  },
  webServer: {
    command: "uv run uvicorn sandbox.web.app:app --host 127.0.0.1 --port 8765",
    // The fixture games (tests/games), so the browser tests have a game to play.
    env: { SANDBOX_EXTRA_GAMES: "tests/games" },
    url: "http://127.0.0.1:8765",
    reuseExistingServer: false,
  },
});
