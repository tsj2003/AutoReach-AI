# Browser E2E Testing

AutoReach is a web Cockpit, so browser automation belongs here. Use Appium only
after there is a real iOS/Android app or mobile wrapper.

## Playwright

Playwright is the CI-style browser test runner. It can start AutoReach against a
fresh seeded SQLite database and verify the product in a real browser.

From `dashboard/`:

```bash
npm run test:e2e:playwright
```

Useful interactive modes:

```bash
npm run test:e2e:playwright:ui
npm run test:e2e:playwright:codegen
```

`codegen` opens a browser and records your clicks into test code. Use it when you
want to explore a new workflow and turn it into a repeatable spec.

## Cypress

Cypress is the visual, time-travel-style local runner. It expects AutoReach to
already be running on `http://127.0.0.1:8766/app`.

Start AutoReach first:

```bash
PYTHONPATH=. AUTOREACH_DB=sqlite:///autoreach_demo.db PORT=8766 .venv/bin/python scripts/run_cockpit.py
```

Then, from `dashboard/`:

```bash
npm run test:e2e:cypress
```

For a headless run:

```bash
npm run test:e2e:cypress:run
```

If Cypress says its binary is missing, run:

```bash
npx cypress install
```

The npm scripts explicitly unset `ELECTRON_RUN_AS_NODE`. If that variable is set,
Cypress's Electron app behaves like plain Node and fails with `bad option:
--smoke-test`.

## Current Coverage

- `/app/login` deep link serves the React app.
- stale auth tokens are cleared on the login page.
- demo account login works.
- dashboard loads seeded campaign data.
- anonymous dashboard access redirects to the landing screen.
