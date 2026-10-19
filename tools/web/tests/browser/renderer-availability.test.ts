import assert from "node:assert/strict";
import test from "node:test";
import {
  bootLibrary,
  browserAvailable,
  buildApp,
  cardIds,
  launch,
  servePrefix,
} from "../helpers/spa-helpers.ts";

// A dead renderer must not take the stored library down with it: boot settles
// past the failed ping and the seeded fonts stay browsable. Service workers
// are blocked at the context level (page routes cannot intercept
// service-worker-handled fetches), so the WASM abort below is deterministic
// rather than racing service-worker registration.
test("stored library stays accessible when the renderer is unavailable", { skip: !browserAvailable }, async (t) => {
  const output = await buildApp(t);
  const url = await servePrefix(t, output);
  const browser = await launch(t);
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    serviceWorkers: "block",
  });
  const seed = await context.newPage();
  await bootLibrary(seed, url);
  const ids = await cardIds(seed);
  assert.equal(ids.length, 5, "seed phase stores five fonts");
  await seed.close();

  let wasmIntercepts = 0;
  await context.route("**/*.wasm", (route) => {
    wasmIntercepts += 1;
    return route.abort();
  });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelectorAll("[data-font-card]").length > 0, null, {
    timeout: 30000,
  });
  assert.deepEqual(await cardIds(page), ids, "stored fonts list without a live renderer");
  // Boot must settle past the failed ping first: the library notice carries
  // the renderer's availability error, so the zero rendered-canvas assertion
  // below is about a dead renderer, not a slow boot. (Card loads stay idle
  // while unavailable; they never attempt, so no per-card error appears.)
  await page.waitForFunction(() => document.querySelector("[data-route-notice]") !== null, null, {
    timeout: 60000,
  });
  assert.ok(wasmIntercepts >= 1, `the WASM abort actually intercepted requests, got ${wasmIntercepts}`);
  assert.equal(
    await page.evaluate(() => document.querySelectorAll("[data-card-canvas][data-rendered]").length),
    0,
    "no canvas paints without a renderer",
  );
  assert.deepEqual(errors, []);

  await page.goto(`${url}#/font/${ids[0]}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(
    () => document.querySelector("section[role='alert'] h2")?.textContent === "Preview renderer unavailable.",
    null,
    { timeout: 20000 },
  );
  await context.close();
});
