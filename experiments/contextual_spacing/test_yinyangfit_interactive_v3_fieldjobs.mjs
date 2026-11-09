// Field-jobs regression gate (Task A): posted vs executed map/slate work,
// dedupe identity, burst cancel bounds, hide/show, invalid drafts, worker
// fallback, target-only/opacity/zoom zero-work, pixel preservation.
//
// Modes:
//   node test_yinyangfit_interactive_v3_fieldjobs.mjs <siteDir>
//     Behavior gates for the new field-batch protocol plus in-page
//     preservation. Fails on the pre-change baseline (red), passes on the
//     field-jobs stage (green).
//   node test_yinyangfit_interactive_v3_fieldjobs.mjs --pixels <siteA> <siteB>
//     Cross-site final-view pixel identity only (mono/gray/multiline).
//
// Offline file:// only, no HTTP. One full default workload plus short-text
// bursts; no model matrix.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));

const SHORT = "hello world";
const MULTILINE = "hello\nworld\nabc";

function postCounterScript() {
  return `(() => {
    window.__yyPosts = { score: 0, slate: 0, map: 0, fields: 0, cancel: 0 };
    const OrigWorker = window.Worker;
    if (!OrigWorker) return;
    function CountedWorker(url, opts) {
      const w = new OrigWorker(url, opts);
      const origPost = w.postMessage.bind(w);
      w.postMessage = (msg, ...rest) => {
        if (msg && msg.kind && window.__yyPosts[msg.kind] !== undefined) {
          window.__yyPosts[msg.kind]++;
        }
        if (msg && msg.kind === "cancel") window.__yyPosts.cancel++;
        return origPost(msg, ...rest);
      };
      return w;
    }
    CountedWorker.prototype = OrigWorker.prototype;
    window.Worker = CountedWorker;
  })();`;
}

async function newPage(browser, site, extraInit) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String((e && e.message) || e)));
  await page.addInitScript({ content: postCounterScript() });
  if (extraInit) await page.addInitScript({ content: extraInit });
  await page.goto(pathToFileURL(resolve(site, "index.html")).href);
  await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], undefined, {
    timeout: 30000,
  });
  return { page, errors };
}

async function waitInk(page, timeout = 60000) {
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
    undefined,
    { timeout },
  );
}

async function waitFieldsSettled(page, timeout = 120000) {
  await waitInk(page, timeout);
  await page.waitForFunction(
    () => {
      const busy = document.getElementById("yy-explain-field").hasAttribute("aria-busy");
      const note = document.getElementById("yy-explain-note").textContent;
      const s = window.YY_SUMMARY;
      return !busy && note !== "Updating fields…" && !!(s && s.coupling !== undefined);
    },
    undefined,
    { timeout },
  );
}

// Generation-aware wait: the summary is rebuilt wholesale by every field
// paint, so match the expected painted inputs, not just any settle.
async function waitPainted(page, want, timeout = 120000) {
  await waitInk(page, timeout);
  await page.waitForFunction(
    (w) => {
      const busy = document.getElementById("yy-explain-field").hasAttribute("aria-busy");
      const note = document.getElementById("yy-explain-note").textContent;
      const s = window.YY_SUMMARY;
      if (!s || s.coupling === undefined || busy || note === "Updating fields…") return false;
      return Object.keys(w).every((k) => s[k] === w[k]);
    },
    want,
    { timeout },
  );
}

// Ink is painted synchronously right after the tables load, while the first
// field batch is still pending: note updating (or busy) with no field paint.
async function waitInkBeforeFields(page, timeout = 60000) {
  await page.waitForFunction(
    () => {
      const s = window.YY_SUMMARY;
      if (s && s.coupling !== undefined) return true; // already settled: burst anyway
      const note = document.getElementById("yy-explain-field").textContent;
      const busy = document.getElementById("yy-explain-field").hasAttribute("aria-busy");
      const inkNote = document.getElementById("yy-sample-note").textContent;
      return (note === "Updating fields…" || busy) && inkNote !== "Updating spacing…";
    },
    undefined,
    { timeout },
  );
}

async function summary(page) {
  return page.evaluate(() => window.YY_SUMMARY || null);
}

async function lastBatch(page) {
  return page.evaluate(() => window.__yyLastBatch || null);
}

async function fieldBatches(page) {
  return page.evaluate(() => window.__yyFieldBatches || null);
}

async function posts(page) {
  return page.evaluate(() => window.__yyPosts || {});
}

async function fieldURL(page, sel = "#yy-explain-field") {
  return page.locator(sel).evaluate((c) => c.toDataURL());
}

async function setNumeric(page, numSel, value) {
  await page.locator(numSel).fill(String(value));
  await page.locator(numSel).dispatchEvent("change");
}

const results = [];
function gate(name, fn) {
  return fn().then(
    () => {
      results.push([name, "PASS"]);
      console.log(`PASS ${name}`);
    },
    (e) => {
      results.push([name, "FAIL", String((e && e.message) || e)]);
      console.log(`FAIL ${name}: ${(e && e.message) || e}`);
    },
  );
}

async function behaviorGates(site) {
  const browser = await chromium.launch({ headless: true });
  try {
    // G1: full default workload — dedupe identity, all placements render.
    await gate("G1 full-load dedupe+settle", async () => {
      const { page, errors } = await newPage(browser, site);
      try {
        await waitFieldsSettled(page);
        const s = await summary(page);
        assert.ok(s, "summary present");
        assert.equal(s.caseId, "roboto-16");
        assert.ok(s.pairLayers > 0, "field layers painted");
        const b = await lastBatch(page);
        assert.ok(b, "batch record present");
        // Every placed occurrence renders a translated layer (default: 94).
        assert.equal(s.pairLayers, 94, `all 94 placements render (got ${s.pairLayers})`);
        // Unique computations shared across repeats.
        assert.ok(b.mapNeeds <= 78, `unique map computations <= 78 (got ${b.mapNeeds})`);
        const fb = await fieldBatches(page);
        assert.ok(fb && fb.length, "field batch ledger present");
        const settled = fb.filter((x) => x.status === "settled");
        assert.ok(settled.length >= 1, "a batch settled");
        const exec = settled.reduce((n, x) => n + (x.executedMaps || 0), 0);
        assert.ok(exec <= 78, `executed unique maps <= 78 (got ${exec})`);
        const p = await posts(page);
        assert.ok((p.fields || 0) >= 1 || (p.map || 0) + (p.slate || 0) > 0, "field work was posted");
        // Posted flood check: one logical batch, not ~95 independent jobs.
        assert.ok((p.fields || 0) <= 2 && (p.map || 0) === 0, `bounded batch posts (fields=${p.fields} map=${p.map})`);
        assert.deepEqual(errors, [], `no page errors: ${errors.join("; ")}`);
        page.__g1field = await fieldURL(page);
        page.__g1summary = s;
        var keep = page;
        globalThis.__g1 = { url: page.__g1field, pairLayers: s.pairLayers };
        await keep.close();
      } catch (e) {
        try {
          await page.close();
        } catch {}
        throw e;
      }
    });

    // G2: rapid target burst while the first full batch is pending.
    // Baseline reposts ~95 jobs per step; the batch protocol coalesces.
    await gate("G2 burst coalesce+cancel", async () => {
      const { page, errors } = await newPage(browser, site);
      try {
        // Burst immediately: tables are loaded (newPage waits), ink and the
        // first field batch are still in flight, so every step dispatches.
        const before = await posts(page);
        for (const t of ["8.02", "8.04", "8.06", "8.08"]) {
          await setNumeric(page, "#yy-spacing-n", t);
        }
        await waitPainted(page, { target: 8.08 });
        const s = await summary(page);
        assert.equal(s.target, 8.08, "latest generation painted");
        assert.ok(s.coupling !== undefined, "latest fields settled");
        const after = await posts(page);
        const newFields = (after.fields || 0) - (before.fields || 0);
        const newMaps = (after.map || 0) - (before.map || 0);
        assert.ok(
          newFields <= 2 && newMaps === 0,
          `burst coalesced to <=2 batch posts (fields=${newFields} map=${newMaps})`,
        );
        const fb = await fieldBatches(page);
        assert.ok(fb, "ledger present");
        const stale = fb.filter((x) => x.status === "cancelled");
        for (const x of stale) {
          assert.ok(
            (x.executedMaps || 0) <= Math.max(0, (x.postedMaps || 0) - 1) || (x.postedMaps || 0) === 0,
            `cancelled batch stopped early (posted=${x.postedMaps} exec=${x.executedMaps})`,
          );
        }
        assert.deepEqual(errors, [], `no page errors: ${errors.join("; ")}`);
        await page.close();
      } catch (e) {
        try {
          await page.close();
        } catch {}
        throw e;
      }
    });

    // G3a: hide during pending cancels field work; ink stays; no stuck busy.
    await gate("G3a hide-before-pending", async () => {
      const { page, errors } = await newPage(browser, site);
      try {
        await waitInkBeforeFields(page);
        await page.locator("#yy-show-fields").uncheck();
        const p0 = await posts(page);
        await page.waitForTimeout(800);
        const p1 = await posts(page);
        assert.equal(p1.fields || 0, p0.fields || 0, "no field posts after hide");
        assert.equal(p1.map || 0, p0.map || 0, "no map posts after hide");
        const busy = await page.locator("#yy-explain-field").evaluate((c) => c.hasAttribute("aria-busy"));
        assert.equal(busy, false, "no stuck busy while hidden");
        assert.equal(await page.locator("#yy-explain-note").textContent(), "", "no pending note while hidden");
        const ink = await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL());
        assert.ok(ink.length > 1000, "ink painted while hidden");
        // Restore: only missing fields compute, then settle.
        await page.locator("#yy-show-fields").check();
        await waitFieldsSettled(page);
        const s = await summary(page);
        assert.equal(s.pairLayers, 94, "all fields restored");
        const fb = await fieldBatches(page);
        assert.ok(fb && fb.length, "field batch ledger present");
        for (const x of fb.filter((b) => b.status === "cancelled" && (b.postedMaps || 0) > 0)) {
          assert.ok((x.executedMaps || 0) <= 6, `cancelled batch stopped early (exec=${x.executedMaps})`);
        }
        assert.deepEqual(errors, [], `no page errors: ${errors.join("; ")}`);
        await page.close();
      } catch (e) {
        try {
          await page.close();
        } catch {}
        throw e;
      }
    });

    // G3b/c: cached toggle repaint-only; hidden param change; restore missing.
    await gate("G3bc cached-toggle+hidden-params", async () => {
      const { page, errors } = await newPage(browser, site);
      try {
        await page.locator("#yy-text").fill(SHORT);
        await waitPainted(page, { text: SHORT });
        const s0 = await summary(page);
        const sc0 = s0.scoreCalls;
        const p0 = await posts(page);
        const f0 = await fieldURL(page);
        await page.locator("#yy-show-fields").uncheck();
        await page.waitForTimeout(500);
        const p1 = await posts(page);
        assert.deepEqual(p1, p0, "hiding cached view posts nothing");
        const busy = await page.locator("#yy-explain-field").evaluate((c) => c.hasAttribute("aria-busy"));
        assert.equal(busy, false, "no stuck busy after hide");
        await page.locator("#yy-show-fields").check();
        await waitPainted(page, { text: SHORT });
        const s1 = await summary(page);
        assert.equal(s1.scoreCalls, sc0, "reshow scores nothing");
        const p2 = await posts(page);
        assert.deepEqual(p2, p0, "reshow from cache posts nothing");
        assert.equal(await fieldURL(page), f0, "reshow restores cached fields");
        // Params change while hidden: no field posts, ink updates.
        await page.locator("#yy-show-fields").uncheck();
        await setNumeric(page, "#yy-spacing-n", "8.5");
        await waitInk(page);
        const p3 = await posts(page);
        assert.deepEqual(p3, p0, "hidden target move posts no fields");
        await page.locator("#yy-show-fields").check();
        await waitPainted(page, { text: SHORT, target: 8.5 });
        const s2 = await summary(page);
        assert.equal(s2.target, 8.5, "restored view matches hidden move");
        assert.equal(s2.scoreCalls, sc0, "visibility restore scores nothing");
        assert.deepEqual(errors, [], `no page errors: ${errors.join("; ")}`);
        await page.close();
      } catch (e) {
        try {
          await page.close();
        } catch {}
        throw e;
      }
    });

    // G4: invalid draft keeps last valid view; no stuck busy.
    await gate("G4 invalid-draft", async () => {
      const { page, errors } = await newPage(browser, site);
      try {
        await page.locator("#yy-text").fill(SHORT);
        await waitPainted(page, { text: SHORT });
        const goodField = await fieldURL(page);
        const goodInk = await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL());
        await page.locator("#yy-text").fill("ab\tcd");
        await page.waitForTimeout(800);
        const note = await page.locator("#yy-text-e").textContent();
        assert.ok(note.length > 0, "draft error shown");
        assert.equal(await fieldURL(page), goodField, "field view retained");
        assert.equal(await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL()), goodInk, "ink retained");
        const busy = await page.locator("#yy-explain-field").evaluate((c) => c.hasAttribute("aria-busy"));
        assert.equal(busy, false, "no stuck busy on invalid draft");
        await page.locator("#yy-text").fill(SHORT);
        await waitFieldsSettled(page);
        assert.deepEqual(errors, [], `no page errors: ${errors.join("; ")}`);
        await page.close();
      } catch (e) {
        try {
          await page.close();
        } catch {}
        throw e;
      }
    });

    // G5: worker failure falls back to the same Class-L engine and settles.
    await gate("G5 worker-failure fallback", async () => {
      const b2 = await chromium.launch({ headless: true });
      try {
        const page = await b2.newPage({ viewport: { width: 1280, height: 800 } });
        const errs = [];
        page.on("pageerror", (e) => errs.push(String((e && e.message) || e)));
        await page.addInitScript({ content: postCounterScript() });
        await page.addInitScript({ content: "window.Worker = undefined;" });
        await page.goto(pathToFileURL(resolve(site, "index.html")).href);
        await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], undefined, {
          timeout: 30000,
        });
        await waitFieldsSettled(page, 180000);
        const s = await summary(page);
        assert.ok(s && s.pairLayers === 94, `fallback settles all layers (got ${s && s.pairLayers})`);
        if (globalThis.__g1) {
          assert.equal(await fieldURL(page), globalThis.__g1.url, "fallback field pixels match worker path");
        }
        const fb = await fieldBatches(page);
        if (fb) {
          assert.ok(
            fb.some((x) => x.source === "main-thread" && x.status === "settled"),
            "fallback used same-engine main thread",
          );
        }
        assert.deepEqual(errs, [], `no page errors: ${errs.join("; ")}`);
        await page.close();
      } finally {
        await b2.close();
      }
    });

    // G6: target-only / opacity / zoom do zero engine work.
    await gate("G6 cheap controls zero-work", async () => {
      const { page, errors } = await newPage(browser, site);
      try {
        await page.locator("#yy-text").fill(SHORT);
        await waitPainted(page, { text: SHORT });
        const s0 = await summary(page);
        const p0 = await posts(page);
        const f0 = await fieldURL(page);
        await setNumeric(page, "#yy-spacing-n", "8.02");
        await waitPainted(page, { text: SHORT, target: 8.02 });
        const s1pre = await summary(page);
        assert.equal(s1pre.scoreCalls, s0.scoreCalls, "target-only scores nothing");
        const p1 = await posts(page);
        assert.equal(p1.score || 0, p0.score || 0, "target-only posts no score jobs");
        // The layered heatmap removed the palette text entry; the
        // opacity slider is the surviving cached display control.
        await page.locator("#yy-contrib-alpha").fill("50");
        await page.waitForTimeout(400);
        const p2 = await posts(page);
        assert.deepEqual(p2, p0, "opacity posts no field work");
        assert.notEqual(await fieldURL(page), f0, "opacity visibly applies");
        await page.locator("#yy-zoom").selectOption("2");
        await page.waitForTimeout(400);
        const p3 = await posts(page);
        assert.deepEqual(p3, p0, "zoom posts no field work");
        assert.deepEqual(errors, [], `no page errors: ${errors.join("; ")}`);
        await page.close();
      } catch (e) {
        try {
          await page.close();
        } catch {}
        throw e;
      }
    });

    // G7: profile round-trip and multiline stability within the page.
    await gate("G7 profile+multiline stability", async () => {
      const { page, errors } = await newPage(browser, site);
      try {
        await waitFieldsSettled(page);
        const mono1 = await fieldURL(page);
        await page.locator('input[name="profile"][value="gray"]').check();
        await waitPainted(page, { profile: "gray" });
        const gray = await fieldURL(page);
        assert.ok(gray.length > 1000, "gray fields paint");
        assert.notEqual(gray, mono1, "gray differs from mono");
        await page.locator('input[name="profile"][value="mono"]').check();
        await waitPainted(page, { profile: "mono" });
        assert.equal(await fieldURL(page), mono1, "mono round-trip identical");
        await page.locator("#yy-text").fill(MULTILINE);
        await waitPainted(page, { text: MULTILINE });
        const s = await summary(page);
        assert.equal(s.shownLines, 3, "multiline settles");
        assert.deepEqual(errors, [], `no page errors: ${errors.join("; ")}`);
        await page.close();
      } catch (e) {
        try {
          await page.close();
        } catch {}
        throw e;
      }
    });
  } finally {
    await browser.close();
  }
}

async function pixelCompare(siteA, siteB) {
  const browser = await chromium.launch({ headless: true });
  async function capture(site, profile, text) {
    const { page, errors } = await newPage(browser, site);
    try {
      if (text !== null) {
        await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], undefined, {
          timeout: 30000,
        });
        await page.locator("#yy-text").fill(text);
      }
      if (profile === "gray") {
        await page.locator('input[name="profile"][value="gray"]').check();
      }
      await waitFieldsSettled(page);
      const out = {
        field: await fieldURL(page),
        ink: await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL()),
        summary: await summary(page),
        errors,
      };
      await page.close();
      return out;
    } catch (e) {
      try {
        await page.close();
      } catch {}
      throw e;
    }
  }
  try {
    const defText = null; // shipped default
    for (const [name, profile, text] of [
      ["mono-default", "mono", defText],
      ["gray-default", "gray", defText],
      ["mono-multiline", "mono", MULTILINE],
    ]) {
      await gate(`PX ${name} identical`, async () => {
        const a = await capture(siteA, profile, text);
        const b = await capture(siteB, profile, text);
        assert.deepEqual(a.errors, [], `A errors: ${a.errors.join("; ")}`);
        assert.deepEqual(b.errors, [], `B errors: ${b.errors.join("; ")}`);
        assert.equal(b.field, a.field, `${name} field pixels identical`);
        assert.equal(b.ink, a.ink, `${name} ink pixels identical`);
      });
    }
  } finally {
    await browser.close();
  }
}

const repo = resolve(root, "..", "..");
const args = process.argv.slice(2);
if (args[0] === "--pixels") {
  await pixelCompare(resolve(repo, args[1]), resolve(repo, args[2]));
} else {
  await behaviorGates(
    resolve(repo, args[0] || "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/site-reviewed"),
  );
}
const failed = results.filter((r) => r[1] !== "PASS");
console.log(`\n${results.length - failed.length}/${results.length} gates passed`);
process.exit(failed.length ? 1 : 0);
