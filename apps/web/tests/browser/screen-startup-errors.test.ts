import assert from "node:assert/strict";
import test from "node:test";
import { browserAvailable, buildApp, launch, servePrefix } from "../helpers/spa-helpers.ts";

test(
  "Screen hides technical schema failures behind a user-facing startup error",
  { skip: !browserAvailable },
  async (t) => {
    const output = await buildApp(t);
    const url = await servePrefix(t, output);
    const browser = await launch(t);
    const context = await browser.newContext();
    t.after(() => context.close());
    const details =
      "Schema migration required: MIGRATE RenderingProfile /nodes/RenderingProfile/kerning. Use migrateSchema() to apply.";
    await context.addInitScript((message) => {
      class FailingDomainOwner {
        port = {
          onmessage: null as ((event: { data: unknown }) => void) | null,
          onmessageerror: null,
          start() {},
          close() {},
          postMessage: (request: { id: number }) => {
            queueMicrotask(() =>
              this.port.onmessage?.({
                data: {
                  id: request.id,
                  ok: false,
                  error: { code: "MIGRATION_ERROR", message },
                },
              }),
            );
          },
        };
      }
      Object.defineProperty(window, "SharedWorker", { configurable: true, value: FailingDomainOwner });
    }, details);
    const page = await context.newPage();
    await page.goto(`${url}screen/`, { waitUntil: "domcontentloaded" });
    const error = page.locator("[data-screen-default-error]");
    await error.waitFor();
    assert.equal(await error.innerText(), "Couldn’t open the default composition.");
    assert.doesNotMatch(
      await page.locator("body").innerText(),
      /Schema migration|MIGRATE|RenderingProfile|migrateSchema|\/nodes\//,
    );
  },
);
