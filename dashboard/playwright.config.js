import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const rootDir = path.resolve("..");
const dbPath = path.join(rootDir, "tmp", "playwright-autoreach.db");
const dbUrl = `sqlite:///${dbPath}`;
const jwtSecret = "playwright-local-jwt-secret-000000000000000000000000";

export default defineConfig({
  testDir: "./e2e/playwright",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8777/app",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: [
      "cd ..",
      "mkdir -p tmp",
      `rm -f ${JSON.stringify(dbPath)} ${JSON.stringify(`${dbPath}-shm`)} ${JSON.stringify(`${dbPath}-wal`)}`,
      `PYTHONPATH=. AUTOREACH_JWT_SECRET=${JSON.stringify(jwtSecret)} .venv/bin/python scripts/seed_demo_tenant.py --db ${JSON.stringify(dbUrl)} --reset`,
      `PYTHONPATH=. AUTOREACH_DB=${JSON.stringify(dbUrl)} AUTOREACH_JWT_SECRET=${JSON.stringify(jwtSecret)} PORT=8777 .venv/bin/python scripts/run_cockpit.py`,
    ].join(" && "),
    url: "http://127.0.0.1:8777/app/login",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
