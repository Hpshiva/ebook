import { defineConfig } from "@playwright/test";

// The end-to-end test runs the real backend (serving the built frontend) on a
// throwaway database in demo mode. No external provider is ever called.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:8010", trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: {
    command:
      "rm -rf e2e/.tmp && mkdir -p e2e/.tmp && npm run build && cd ../backend && " +
      "DATABASE_URL=sqlite:///../frontend/e2e/.tmp/e2e.db APIFY_TOKEN= .venv/bin/python -m uvicorn app.main:app --port 8010",
    url: "http://127.0.0.1:8010/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
