// B2 focused Chromium check for the full-window working entry.
// Loads the real offline page, asserts the B2 identity, reproduces the
// repaired `um` choice (metric 8, chosen 9 at 1.10/2.0/2.0) through the
// page's own engine on Mono and Gray, cross-checks repaired Python outcomes
// for the motivating pairs, exercises the worker on-demand path and the
// workerless main-thread fallback, records cold/warm/wide-reach latencies,
// and saves a `um` capture plus timings into the full-window evidence dir.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve, dirname, join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const dir = dirname(fileURLToPath(import.meta.url));
const root = join(dir, "../..");
const site = resolve(
  root,
  process.argv[2] || "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed",
);
const evidence = resolve(root, process.argv[3] || "out/diagnostics/contextual-spacing/yinyang-full-window");
const boot = JSON.parse(readFileSync(join(site, "boot.json"), "utf8"));
const parity = JSON.parse(readFileSync(join(evidence, "parity-corpus-b2.json"), "utf8"));
function wantChoice(dataset, pair, scale, falloff, cohesion) {
  const entry = parity.entries.find(
    (e) => e.dataset === dataset && e.pair === pair && e.scale === scale && e.falloff === falloff,
  );
  assert.ok(entry, `parity entry for ${dataset} ${pair}`);
  return { metric: entry.metric, ...entry.choices[String(cohesion)] };
}

const EXPECTED_MODEL = "yinyangfit-interactive-b2-fullwindow-v1";
assert.equal(boot.model, EXPECTED_MODEL, "working entry boots the B2 model");
assert.match(boot.implementation, /^[0-9a-f]{64}$/, "implementation identity");

// In-page engine check through the same code the worker, the fallback and
// the cached columns all share. Cells decode exactly as the page does from
// the embedded boot catalogue (packed cover strings per case and profile).
const DECODE_CELLS = `
  const boot = JSON.parse(document.getElementById("yy-boot").textContent);
  function decode(profile, g) {
    if (profile === "mono") {
      return { w: g.w, h: g.h, left: g.left, top: g.top,
        cover: Array.from(g.cover).map((s) => (s === "1" ? 1 : 0)) };
    }
    return { w: g.w, h: g.h, left: g.left, top: g.top,
      cover: Array.from(g.cover).map((s) => (s.charCodeAt(0) - 48) / 7) };
  }
  const roboto = boot.cases.find((c) => c.id === "roboto-16");
  window.__cells = {};
  for (const [cp, g] of Object.entries(roboto.profiles.mono.glyphs)) {
    window.__cells[cp] = decode("mono", g);
  }
  window.__grayCells = {};
  for (const [cp, g] of Object.entries(roboto.profiles.gray.glyphs)) {
    window.__grayCells[cp] = decode("gray", g);
  }
  window.__mono = YYCompute.createSession(window.__cells);
  window.__gray = YYCompute.createSession(window.__grayCells);
`;
async function engineChoice(page, dataset, pair, scale, falloff, cohesion) {
  return page.evaluate(
    ({ dataset, pair, scale, falloff, cohesion }) => {
      const table = window.YY_TABLES[dataset];
      const adv = table.advances,
        kern = table.kern || {};
      const left = pair.charCodeAt(0),
        right = pair.charCodeAt(1);
      const key = left + "/" + right;
      const adj = Object.prototype.hasOwnProperty.call(kern, key) ? kern[key] : 0;
      const round = (v) => (v >= 0 ? Math.floor(v + 0.5) : Math.ceil(v - 0.5));
      const metric = round(adv[String(left)] + adj);
      const isGray = dataset.endsWith("gray");
      const raw = isGray ? window.__grayCells : window.__cells;
      const session = isGray ? window.__gray : window.__mono;
      const out = session.scorePair(pair, String(left), String(right), metric, scale, falloff, cohesion);
      return { metric, chosen: out.chosen, fallback: out.fallback };
    },
    { dataset, pair, scale, falloff, cohesion },
  );
}

const timings = {};
const browser = await chromium.launch({ headless: true });
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(() => {
    window.__yyWorkerJobs = 0;
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      constructor(...args) {
        super(...args);
        this.addEventListener("message", (event) => {
          if (event.data.kind === "pair") window.__yyWorkerJobs++;
        });
      }
    };
  });
  const t0 = Date.now();
  await page.goto(pathToFileURL(join(site, "index.html")).href);
  await page.waitForFunction(
    () => document.getElementById("yy-sample") && document.getElementById("yy-sample").options.length === 13,
    null,
    { timeout: 30000 },
  );
  await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], null, { timeout: 30000 });
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
    null,
    { timeout: 120000 },
  );
  timings.coldLoadMs = Date.now() - t0;

  // Decode cells once through the page's own boot catalogue.
  await page.evaluate(`(() => {${DECODE_CELLS}})()`);
  // Force both profile tables to load so engine metrics mirror the page.
  await page.locator('input[name="profile"][value="gray"]').check();
  await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-gray"], null, { timeout: 30000 });
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
    null,
    { timeout: 120000 },
  );
  await page.locator('input[name="profile"][value="mono"]').check();
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
    null,
    { timeout: 120000 },
  );

  // The repaired choice through the live page engine, both profiles.
  // Mono repairs 6 (contact) to 9 (source+1); Gray's fractional Source step
  // is 9 and B2 chooses 8, both matching the repaired Python outcomes.
  for (const dataset of ["roboto-16-mono", "roboto-16-gray"]) {
    const want = wantChoice(dataset, "um", 2, 2, 1.1);
    const got = await engineChoice(page, dataset, "um", 2, 2, 1.1);
    assert.equal(got.metric, want.metric, `${dataset} um metric matches Python`);
    assert.equal(got.chosen, want.chosen, `${dataset} um choice matches Python`);
    assert.equal(got.fallback, false, `${dataset} um scores without fallback`);
  }
  {
    const mono = await engineChoice(page, "roboto-16-mono", "um", 2, 2, 1.1);
    assert.equal(mono.metric, 8, "mono um metric is the Source step");
    assert.equal(mono.chosen, 9, "mono um chooses source+1, not contact");
  }
  // Motivating and novel pairs match the repaired Python outcomes exactly.
  for (const pair of ["og", "AV", "To", "qj"]) {
    const want = wantChoice("roboto-16-mono", pair, 2, 2, 1.1);
    const got = await engineChoice(page, "roboto-16-mono", pair, 2, 2, 1.1);
    assert.equal(got.metric, want.metric, `${pair} metric matches Python`);
    assert.equal(got.chosen, want.chosen, `${pair} choice matches Python`);
    assert.equal(got.fallback, want.fallback, `${pair} fallback matches Python`);
  }

  // Warm derivation: cohesion-only change reuses geometry quickly.
  const t1 = Date.now();
  await page.locator("#yy-spacing").fill("1.5");
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
    null,
    { timeout: 120000 },
  );
  timings.warmCohesionMs = Date.now() - t1;
  await page.locator("#yy-spacing").fill("1.1");
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
    null,
    { timeout: 120000 },
  );

  // Wide-reach on-demand compute through the worker path.
  const jobsBefore = await page.evaluate(() => window.__yyWorkerJobs);
  const t2 = Date.now();
  await page.locator("#yy-reach-n").fill("12");
  await page.locator("#yy-reach-n").press("Enter");
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
    null,
    { timeout: 180000 },
  );
  timings.wideReachMs = Date.now() - t2;
  const jobsAfter = await page.evaluate(() => window.__yyWorkerJobs);
  assert.ok(jobsAfter > jobsBefore, "wide reach scores through the worker");
  const wide = await engineChoice(page, "roboto-16-mono", "um", 12, 2, 1.1);
  assert.ok(wide.chosen >= 6 && wide.chosen <= 10, "wide reach stays in range");
  await page.locator("#yy-reset").click();
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
    null,
    { timeout: 120000 },
  );

  // Pair inspector on `um` with a saved capture.
  await page.locator("#yy-pairs > summary").click();
  await page.locator("#yy-pair").selectOption("um");
  await page.waitForFunction(() => document.getElementById("yy-pair-note").textContent.length > 0, null, {
    timeout: 30000,
  });
  const pairNote = await page.locator("#yy-pair-note").textContent();
  assert.match(pairNote, /wider|Source/, `um pair feedback: ${pairNote}`);
  mkdirSync(evidence, { recursive: true });
  await page.locator("#yy-pairs").screenshot({ path: join(evidence, "um-browser.png") });

  // Workerless main-thread fallback reaches the same repaired choice.
  const fallback = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  try {
    await fallback.addInitScript(() => {
      delete window.Worker;
    });
    fallback.on("pageerror", (e) => errors.push(e.message));
    await fallback.goto(pathToFileURL(join(site, "index.html")).href);
    await fallback.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], null, {
      timeout: 30000,
    });
    await fallback.evaluate(`(() => {${DECODE_CELLS}})()`);
    const out = await fallback.evaluate(() => window.__mono.scorePair("um", "117", "109", 8, 2, 2, 1.1));
    assert.equal(out.chosen, 9, "fallback path chooses source+1 for um");
  } finally {
    await fallback.close();
  }

  // Narrow mobile width renders without document overflow.
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    mobile.on("pageerror", (e) => errors.push(e.message));
    await mobile.goto(pathToFileURL(join(site, "index.html")).href);
    await mobile.waitForFunction(
      () => document.getElementById("yy-sample") && document.getElementById("yy-sample").options.length === 13,
      null,
      { timeout: 30000 },
    );
    const overflow = await mobile.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    assert.ok(overflow <= 0, `no overflow at 390px (got ${overflow})`);
  } finally {
    await mobile.close();
  }

  assert.deepEqual(errors, [], `page errors: ${errors.join("; ")}`);
  timings.errors = 0;
  writeFileSync(
    join(evidence, "timings.json"),
    JSON.stringify({ ...timings, model: boot.model, implementation: boot.implementation }, null, 1) + "\n",
  );
  console.log(JSON.stringify({ status: "passed", ...timings }));
} finally {
  await browser.close();
}
