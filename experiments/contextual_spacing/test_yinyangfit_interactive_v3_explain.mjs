// cspell:words multiword yinyang yinyangfit
// Real-browser check for the whole-text field view: two fixed-ramp
// layer roles with visibility checkboxes and opacity sliders reshaping
// the layers without rescaling the view, editable preview text (novel
// pairs, repertoire errors, restore), profile/sample/zoom/reset repaint,
// coupling diagnostics, and the self-contained editable demo matching
// the engine. Desktop + mobile, no document overflow, zero page errors.
// Saves screenshots.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve, dirname, join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const directory = resolve(
  root,
  process.argv[2] || "../../out/diagnostics/contextual-spacing/yinyang-browser-integration/main/staging/site-full",
);
const demoPath = resolve(
  root,
  "../../out/diagnostics/contextual-spacing/yinyang-editable-preview/yinyang-live-demo.html",
);

// Reference choices for the separate editable demo's own scorer (that demo
// ships its own B2 engine, untouched by this task): one batched Python B2
// call over every pair the demo section asserts. The main page reference
// lives in the coupling and page checks.
import { execFileSync } from "node:child_process";
const DEMO_PAIRS = ["AV", "To", "og", "qj", "Pa", "ac", "ck", "my", "bo", "ox"];
const DEMO_WANT = JSON.parse(
  execFileSync(
    "python3",
    [
      "-c",
      `
import json, sys
from types import SimpleNamespace
sys.path.insert(0, "experiments/contextual_spacing")
import yinyangfit_interactive as yy
import yinyangfit_interactive_b2 as b2
import yinyangfit_interactive_v3 as v3
from pathlib import Path
caps = Path("out/diagnostics/contextual-spacing/yinyangfit-interactive-v3/captures").resolve()
ds = v3.load_case_dataset("roboto-16", "mono", caps)
scorer = b2.PairScorer(ds)
# Plain carrier past the frozen v1 control band: the demo evaluates
# outside it, where the validated YYControls dataclass does not reach,
# so the reference scores the uncached B2 core directly and derives the
# choice through the shared choose_from_costs rule.
cohesion = 1.123
controls = SimpleNamespace(cohesion=cohesion, feature_scale=2.125,
                           proximity_falloff=4.2)
out = {}
for name in ${JSON.stringify([...DEMO_PAIRS, "To", "qj", "AV"])}:
    left, right = ord(name[0]), ord(name[1])
    metric = yy.metric_step(ds, left, right)
    steps = [metric + d for d in yy.CANDIDATE_DELTAS]
    geos = [scorer._score_geometry_uncached(left, right, step, controls)
            for step in steps]
    costs = [abs(g["interaction"] - cohesion) if g["valid"] else None
             for g in geos]
    valids = [g["valid"] for g in geos]
    chosen, _, _ = yy.choose_from_costs(steps, costs, valids, metric)
    out[name] = chosen
print(json.dumps(out))
`,
    ],
    { encoding: "utf8", maxBuffer: 1 << 24 },
  ),
);
function refChoice(pair) {
  return DEMO_WANT[pair];
}
const html = readFileSync(join(directory, "index.html"), "utf8");
const boot = JSON.parse(html.match(/<script type="application\/json" id="yy-boot">([\s\S]*?)<\/script>/)[1]);

const browser = await chromium.launch({ headless: true });
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on("pageerror", (error) => errors.push("desktop: " + error.message));
  await page.goto(pathToFileURL(resolve(directory, "index.html")).href);
  await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], { timeout: 30000 });
  const settled = () =>
    page.waitForFunction(
      () =>
        document.getElementById("yy-sample-note").textContent !== "Updating spacing…" &&
        window.YY_SUMMARY?.pairLayers !== undefined,
      undefined,
      { timeout: 180000 },
    );
  // Exact input identity and completed field paint distinguish spaces,
  // blank lines and text beyond the displayed line cap.
  const fillText = async (text, target = page) => {
    await target.locator("#yy-text").fill(text);
    await target.waitForFunction(
      (want) => window.YY_SUMMARY?.text === want && window.YY_SUMMARY.pairLayers !== undefined,
      text,
      { timeout: 180000 },
    );
  };
  await settled();
  // Field layers arrive after the ink paint; wait for the first full view.
  await page.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.pairLayers !== undefined, {
    timeout: 180000,
  });
  // Same pair and placement can occur in different fonts; their maps must
  // still reduce to the selected font's score after sample switches.
  await fillText("um og To AV rt nn");
  const sampleIds = await page
    .locator("#yy-sample option")
    .evaluateAll((options) => options.map((option) => option.value));
  for (const profile of ["mono", "gray"]) {
    await page.locator(`input[name="profile"][value="${profile}"]`).check();
    for (const caseId of sampleIds) {
      await page.locator("#yy-sample").selectOption(caseId);
      await page.waitForFunction(
        ({ caseId, profile }) =>
          window.YY_SUMMARY?.caseId === caseId &&
          window.YY_SUMMARY.profile === profile &&
          window.YY_SUMMARY.pairLayers !== undefined &&
          document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
        { caseId, profile },
      );
      const switched = await page.evaluate(() => (window.YY_SUMMARY.coupling || []).join("\n"));
      assert.ok(!/MISMATCH/.test(switched), `interaction maps match scores after switching to ${caseId}/${profile}`);
    }
  }
  await page.locator("#yy-sample").selectOption("roboto-16");
  await page.locator('input[name="profile"][value="mono"]').check();
  await page.locator("#yy-text-restore").click();
  await settled();
  // Field view renders by default with two labelled roles; no ruler.
  const fieldSize = await page.locator("#yy-explain-field").evaluate((c) => [c.width, c.height]);
  assert.ok(fieldSize[0] > 0 && fieldSize[1] > 0, "field canvas renders");
  assert.equal(await page.locator("#yy-explain-source").count(), 0, "Source blob strip removed");
  // Layered heatmap display: the master switch plus one checkbox per
  // fixed ramp, each with its own weak-to-strong legend. The
  // single-color pickers and RGBA rows are gone.
  assert.match(
    await page.locator("label:has(#yy-show-letter)").textContent(),
    /Letter fields/,
    "letter layer labelled",
  );
  assert.match(
    await page.locator("label:has(#yy-show-contrib)").textContent(),
    /Pair contributions/,
    "contribution layer labelled",
  );
  assert.equal(await page.locator("#yy-show-fields").isChecked(), true, "master on by default");
  assert.equal(await page.locator("#yy-show-letter").isChecked(), true, "letter layer on by default");
  assert.equal(await page.locator("#yy-show-contrib").isChecked(), true, "contribution layer on by default");
  assert.equal(await page.locator(".yy-ramp-cool").count(), 1, "cool ramp legend present");
  assert.equal(await page.locator(".yy-ramp-warm").count(), 1, "warm ramp legend present");
  await page.waitForFunction(() => document.getElementById("yy-explain-note").textContent !== "Updating fields…", {
    timeout: 180000,
  });
  assert.equal(
    await page.locator("#yy-explain-note").textContent(),
    "",
    "completed preview has no repetitive status text",
  );
  // Preview text field follows the sample until edited.
  assert.match(await page.locator("#yy-text").inputValue(), /Pack my box/, "text field seeded from the sample");
  assert.equal(await page.locator("#yy-text-restore").isHidden(), true, "restore hidden without an edit");
  // Opacity controls carry the approved defaults.
  assert.equal(await page.locator("#yy-letter-alpha").inputValue(), "65", "letter opacity default");
  assert.equal(await page.locator("#yy-contrib-alpha").inputValue(), "100", "contribution opacity default");
  // Tinted-pixel count: reach spreads, falloff reshapes, frame fixed.
  const tinted = () =>
    page.locator("#yy-explain-field").evaluate((c) => {
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 0; i < d.length; i += 4) {
        const spread = Math.max(d[i], d[i + 1], d[i + 2]) - Math.min(d[i], d[i + 1], d[i + 2]);
        if (spread > 40) n++;
      }
      return [n, c.width, c.height];
    });
  const before = await tinted();
  assert.ok(before[0] > 0, "interaction layer paints tinted pixels");
  const fieldSettled = (reach, falloff) =>
    page.waitForFunction(
      ({ reach, falloff }) =>
        window.YY_SUMMARY &&
        window.YY_SUMMARY.reach === reach &&
        window.YY_SUMMARY.falloff === falloff &&
        window.YY_SUMMARY.pairLayers > 0,
      { reach, falloff },
      { timeout: 180000 },
    );
  await page.locator("#yy-reach").fill("4");
  await settled();
  await fieldSettled(4, 2);
  const afterReach = await tinted();
  assert.deepEqual(
    [afterReach[1], afterReach[2]],
    [before[1], before[2]],
    "frame backing size fixed across reach moves",
  );
  assert.ok(afterReach[0] !== before[0], "reach reshapes the layers");
  await page.locator("#yy-falloff-n").fill("10");
  await page.locator("#yy-falloff-n").press("Enter");
  await settled();
  await fieldSettled(4, 10);
  const afterFall = await tinted();
  assert.ok(afterFall[0] !== afterReach[0], "falloff reshapes layers");
  assert.deepEqual(
    [afterFall[1], afterFall[2]],
    [before[1], before[2]],
    "frame backing size fixed across falloff moves",
  );
  // Coupling maps converge: every shown pair sums within 1e-9 (machine-side).
  const diag = await page.evaluate(() => (window.YY_SUMMARY.coupling || []).join("\n"));
  assert.match(diag, /gain 4 fixed/, "gain is display-only and fixed");
  assert.ok(diag.includes(" ok"), "shown pairs converge to their scores");
  assert.ok(!diag.includes("MISMATCH"), "no reduction mismatch");
  await page.locator('input[name="profile"][value="gray"]').check();
  await settled();
  assert.ok((await tinted())[0] > 0, "gray layers render");
  await page.locator("#yy-sample").selectOption("literata-16");
  await page.waitForFunction(() => document.getElementById("yy-focus-title").textContent.includes("Literata"));
  await settled();
  // Novel preview text paints through the same guarded path.
  await page.locator("#yy-sample").selectOption("roboto-16");
  await page.waitForFunction(() => document.getElementById("yy-focus-title").textContent.includes("Roboto 16"));
  await settled();
  await fillText("AV To og qj");
  await settled();
  assert.match(await page.locator("#yy-focus-title").textContent(), /Roboto 16/, "custom text keeps the dataset");
  const customSummary = await page.evaluate(() => window.YY_SUMMARY);
  assert.deepEqual(customSummary.shownText, ["AV To og qj"], "novel pairs remain part of the full-text preview");
  assert.ok(customSummary.pairLayers > 0, "custom text paints contribution maps");
  assert.equal(await page.locator("#yy-text-restore").isHidden(), false, "restore appears after an edit");
  // Unsupported characters report the codepoint and keep the last paint.
  const painted = await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL());
  await page.locator("#yy-text").fill("caf\u00e9");
  await page.waitForFunction(() => document.getElementById("yy-text-e").textContent.includes("U+00E9"), {
    timeout: 30000,
  });
  assert.match(
    await page.locator("#yy-sample-note").textContent(),
    /Showing the last valid text/,
    "stale paint is labelled",
  );
  assert.equal(
    await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL()),
    painted,
    "invalid draft keeps the last valid paint",
  );
  await page.locator("#yy-text-restore").click();
  await settled();
  assert.match(await page.locator("#yy-text").inputValue(), /Pack my box/, "restore returns the sample text");
  // Empty text settles cleanly with an explanatory note.
  await page.locator("#yy-text").fill("   ");
  await page.waitForFunction(() => document.getElementById("yy-sample-note").textContent.includes("Nothing to space"), {
    timeout: 120000,
  });
  await settled();
  assert.match(
    await page.locator("#yy-sample-note").textContent(),
    /Nothing to space/,
    "space-only text settles with a note",
  );
  await page.locator("#yy-text-restore").click();
  await settled();
  await page.locator("#yy-sample").selectOption("roboto-16");
  await page.locator("#yy-zoom").selectOption("4");
  await page.locator("#yy-reset").click();
  await settled();
  assert.ok(
    (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0,
    "no desktop overflow",
  );
  // Screenshot a short text: the full sample canvas is wider than the
  // viewport by design (long lines scroll), and an element capture of
  // the overflowed box would composite the page beneath it.
  await fillText("AV To");
  await settled();
  await page.locator("#yy-explain-field").screenshot({ path: resolve(directory, "explain-desktop.png") });

  // Opacity editing: a slider move repaints with zero score/map rebuild work.
  const fieldBefore = await page.locator("#yy-explain-field").evaluate((c) => c.toDataURL());
  const workBefore = await page.evaluate(() => ({ ...window.YY_SUMMARY }));
  assert.ok(workBefore.pairLayers > 0, "layers present for repaint checks");
  await page.locator("#yy-contrib-alpha").fill("50");
  const workAfter = await page.evaluate(() => ({ ...window.YY_SUMMARY }));
  assert.equal(workAfter.contribHits, workBefore.contribHits, "opacity edit reuses coupling maps");
  assert.equal(workAfter.contribMisses, workBefore.contribMisses, "opacity edit builds no maps");
  assert.equal(workAfter.scoreCalls, workBefore.scoreCalls, "opacity edit rescores nothing");
  assert.equal(workAfter.contribAlpha, 0.5, "contribution opacity updates");
  const halfPixels = await page.locator("#yy-explain-field").evaluate((c) => c.toDataURL());
  assert.notEqual(halfPixels, fieldBefore, "contribution opacity changes pixels");
  // Layer checkboxes: hiding one ramp repaints with zero engine work
  // and keeps the other; rechecking restores the combined view.
  await page.uncheck("#yy-show-letter");
  const letterHidden = await page.evaluate(() => ({ ...window.YY_SUMMARY }));
  assert.equal(letterHidden.showLetter, false, "letter choice retained while hidden");
  assert.equal(letterHidden.contribHits, workAfter.contribHits, "letter hide reuses coupling maps");
  assert.equal(letterHidden.scoreCalls, workAfter.scoreCalls, "letter hide rescores nothing");
  assert.notEqual(
    await page.locator("#yy-explain-field").evaluate((c) => c.toDataURL()),
    halfPixels,
    "letter hide changes pixels",
  );
  await page.check("#yy-show-letter");
  assert.equal(
    await page.locator("#yy-explain-field").evaluate((c) => c.toDataURL()),
    halfPixels,
    "letter reshow restores the combined pixels",
  );
  // Master visibility: hiding paints ink alone with zero engine work
  // and retains the individual choices; reshow restores the layers.
  const visWork = await page.evaluate(() => ({ ...window.YY_SUMMARY }));
  await page.uncheck("#yy-show-fields");
  assert.equal(await page.locator("#yy-show-letter").isChecked(), true, "master hide retains letter choice");
  assert.equal(await page.locator("#yy-show-contrib").isChecked(), true, "master hide retains contribution choice");
  const visHidden = await page.evaluate(() => ({ ...window.YY_SUMMARY }));
  assert.equal(visHidden.scoreCalls, visWork.scoreCalls, "master hide rescores nothing");
  assert.notEqual(
    await page.locator("#yy-explain-field").evaluate((c) => c.toDataURL()),
    halfPixels,
    "master hide paints ink alone",
  );
  await page.check("#yy-show-fields");
  assert.equal(
    await page.locator("#yy-explain-field").evaluate((c) => c.toDataURL()),
    halfPixels,
    "master reshow restores the layered pixels",
  );
  // Opacity survives profile, zoom and control moves.
  await page.locator("#yy-contrib-alpha").fill("50");
  await page.locator('input[name="profile"][value="gray"]').check();
  await settled();
  assert.equal(await page.locator("#yy-contrib-alpha").inputValue(), "50", "opacity survives profile switch");
  assert.equal(
    (await page.evaluate(() => ({ ...window.YY_SUMMARY }))).contribAlpha,
    0.5,
    "opacity value survives profile switch",
  );
  await page.locator("#yy-zoom").selectOption("4");
  assert.equal(await page.locator("#yy-contrib-alpha").inputValue(), "50", "opacity survives zoom");
  await page.locator("#yy-reach").fill("5");
  await settled();
  assert.equal(await page.locator("#yy-contrib-alpha").inputValue(), "50", "opacity survives control moves");
  assert.match(
    await page.locator("label:has(#yy-show-contrib)").textContent(),
    /Pair contributions/,
    "contribution role keeps its label",
  );
  assert.equal(await page.locator(".yy-ramp-warm").count(), 1, "warm ramp legend retained");
  await page.locator('input[name="profile"][value="mono"]').check();
  await page.locator("#yy-zoom").selectOption("1");
  await page.locator("#yy-reset").click();
  await settled();
  await fieldSettled(12, 2);
  assert.match(
    await page.locator('label[for="yy-letter-alpha"]').textContent(),
    /Letter fields opacity/,
    "letter slider labelled",
  );
  assert.match(
    await page.locator('label[for="yy-contrib-alpha"]').textContent(),
    /Pair contributions opacity/,
    "contribution slider labelled",
  );
  // Sliders are independent controls: restore both defaults explicitly.
  await page.locator("#yy-letter-alpha").fill("65");
  await page.locator("#yy-contrib-alpha").fill("100");
  assert.equal(await page.locator("#yy-letter-alpha").inputValue(), "65", "letter opacity default 65%");
  assert.equal(await page.locator("#yy-letter-alpha-v").textContent(), "65%", "letter percent shown");
  assert.equal(await page.locator("#yy-contrib-alpha").inputValue(), "100", "contribution opacity default 100%");
  assert.equal(await page.locator("#yy-contrib-alpha-v").textContent(), "100%", "contribution percent shown");
  // Full sweep on the interaction layer paints 0/25/100 distinctly.
  const tintN = () =>
    page.locator("#yy-explain-field").evaluate((c) => {
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 0; i < d.length; i += 4) {
        const spread = Math.max(d[i], d[i + 1], d[i + 2]) - Math.min(d[i], d[i + 1], d[i + 2]);
        if (spread > 40) n++;
      }
      return n;
    });
  const interWork = () => page.evaluate(() => ({ ...window.YY_SUMMARY }));
  const w0 = await interWork();
  await page.locator("#yy-contrib-alpha").fill("0");
  const n0 = await tintN();
  await page.locator("#yy-contrib-alpha").fill("25");
  assert.equal(
    (await page.evaluate(() => ({ ...window.YY_SUMMARY }))).contribAlpha,
    0.25,
    "slider edits the contribution opacity",
  );
  const n25 = await tintN();
  await page.locator("#yy-contrib-alpha").fill("100");
  const n100 = await tintN();
  assert.ok(n100 > n0 && n25 >= n0 && n100 >= n25, `opacity sweep paints 0/25/100 distinctly (${n0}/${n25}/${n100})`);
  const w1 = await interWork();
  assert.equal(w1.contribHits, w0.contribHits, "opacity reuses coupling maps");
  assert.equal(w1.contribMisses, w0.contribMisses, "opacity builds no maps");
  assert.equal(w1.scoreCalls, w0.scoreCalls, "opacity rescores nothing");
  assert.equal(w1.pairLayers, w0.pairLayers, "opacity keeps the shown pairs");
  // Readout follows the slider exactly.
  await page.locator("#yy-contrib-alpha").fill("33");
  assert.equal(await page.locator("#yy-contrib-alpha").inputValue(), "33", "thumb shows the nearest step");
  assert.equal(await page.locator("#yy-contrib-alpha-v").textContent(), "33%", "readout shows the exact opacity");
  // Keyboard steps the slider and the readout together.
  await page.locator("#yy-letter-alpha").focus();
  await page.locator("#yy-letter-alpha").press("ArrowRight");
  assert.equal(await page.locator("#yy-letter-alpha-v").textContent(), "66%", "keyboard steps the opacity");
  // Spacing reset leaves the display controls alone.
  await page.locator("#yy-letter-alpha").fill("10");
  await page.locator("#yy-contrib-alpha").fill("25");
  await page.locator("#yy-reset").click();
  await settled();
  assert.equal(await page.locator("#yy-letter-alpha").inputValue(), "10", "spacing reset preserves letter opacity");
  assert.equal(await page.locator("#yy-contrib-alpha").inputValue(), "25", "spacing reset preserves contrib opacity");
  assert.equal(await page.locator("#yy-show-letter").isChecked(), true, "spacing reset preserves letter choice");
  assert.equal(await page.locator("#yy-show-contrib").isChecked(), true, "spacing reset preserves contrib choice");

  // Shared magnification rescales the field view natively: CSS dimensions
  // scale exactly with the zoom, cached display repaints with no rescore
  // or map rebuild, and returning to 1x restores identical pixels.
  const cssSize = () =>
    page
      .locator("#yy-explain-field")
      .evaluate((c) => [c.getBoundingClientRect().width, c.getBoundingClientRect().height]);
  const workOf = () =>
    page.evaluate(() => {
      const s = { ...window.YY_SUMMARY };
      return { score: s.scoreCalls, hits: s.contribHits, misses: s.contribMisses, layers: s.pairLayers, zoom: s.zoom };
    });
  const shotOf = () => page.locator("#yy-explain-field").evaluate((c) => c.toDataURL());
  const size1 = await cssSize();
  const work1 = await workOf();
  const url1 = await shotOf();
  assert.equal(work1.zoom, 1, "summary records the zoom");
  await page.locator("#yy-zoom").selectOption("2");
  assert.deepEqual(await cssSize(), [size1[0] * 2, size1[1] * 2], "2x doubles the field CSS dimensions");
  await page.locator("#yy-zoom").selectOption("4");
  assert.deepEqual(await cssSize(), [size1[0] * 4, size1[1] * 4], "4x quadruples the field CSS dimensions");
  const work4 = await workOf();
  assert.equal(work4.zoom, 4, "summary follows the zoom");
  assert.equal(work4.score, work1.score, "zoom rescores nothing");
  assert.equal(work4.hits, work1.hits, "zoom reuses maps without rereading");
  assert.equal(work4.misses, work1.misses, "zoom rebuilds no maps");
  assert.equal(work4.layers, work1.layers, "zoom keeps the shown pairs");
  assert.ok(
    (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0,
    "no desktop overflow at 4x",
  );
  await page.locator("#yy-zoom").selectOption("1");
  assert.deepEqual(await cssSize(), size1, "1x restores the dimensions");
  assert.equal(await shotOf(), url1, "1x restores identical pixels");

  // The field view shows every shown line, not a letter cutoff: a second
  // line past 32 letters paints ink below the single-line view.
  const darkBelow = (cssY) =>
    page.locator("#yy-explain-field").evaluate((c, y) => {
      const scale = c.height / c.getBoundingClientRect().height;
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      const y0 = Math.floor(y * scale);
      for (let yy = y0; yy < c.height; yy++) {
        for (let x = 0; x < c.width; x++) {
          const i = (yy * c.width + x) * 4;
          if (Math.max(d[i], d[i + 1], d[i + 2]) < 80) n++;
        }
      }
      return n;
    }, cssY);
  await fillText("n".repeat(32));
  const singleH = (await cssSize())[1];
  await fillText("n".repeat(32) + "\nAV");
  assert.deepEqual(
    await page.evaluate(() => ({
      letters: window.YY_SUMMARY.shownLetters,
      lines: window.YY_SUMMARY.shownLines,
      text: window.YY_SUMMARY.shownText,
    })),
    { letters: 34, lines: 2, text: ["n".repeat(32), "AV"] },
    "second line remains complete past 32 letters",
  );
  assert.ok((await cssSize())[1] > singleH, "second line grows the frame");
  assert.ok((await darkBelow(singleH)) > 0, "second-line ink paints pixels");
  assert.match(
    await page.evaluate(() => (window.YY_SUMMARY.coupling || []).join("\n")),
    /AV .* ok/,
    "second-line pair converges to its score",
  );
  const tall1 = await cssSize();
  const work2 = await workOf();
  await page.locator("#yy-zoom").selectOption("4");
  assert.deepEqual(await cssSize(), [tall1[0] * 4, tall1[1] * 4], "multiline view keeps exact ratios");
  const workZoom = await workOf();
  assert.equal(workZoom.score, work2.score, "multiline zoom rescores nothing");
  assert.equal(workZoom.hits, work2.hits, "multiline zoom rereads no maps");
  assert.equal(workZoom.misses, work2.misses, "multiline zoom rebuilds no maps");
  await fillText("n".repeat(32));
  const singleH4 = (await cssSize())[1];
  await fillText("n".repeat(32) + "\nAV");
  assert.deepEqual(await cssSize(), [tall1[0] * 4, tall1[1] * 4], "multiline frame identical at 4x");
  assert.ok((await darkBelow(singleH4)) > 0, "zoom keeps the second line");
  await page.locator("#yy-contrib-alpha").fill("50");
  assert.deepEqual(await cssSize(), [tall1[0] * 4, tall1[1] * 4], "opacity edits keep the zoom");
  assert.ok((await darkBelow(singleH4)) > 0, "opacity edits keep all lines");
  assert.equal(await page.locator("#yy-contrib-alpha").inputValue(), "50", "opacity survives zoom with all lines");
  await page.locator("#yy-zoom").selectOption("1");

  // Blank lines offset later lines; explicit newlines start new lines
  // while long single lines never wrap.
  await fillText("AV\nTo");
  const joinedH = (await cssSize())[1];
  await fillText("AV\n\nTo");
  assert.deepEqual(
    await page.evaluate(() => window.YY_SUMMARY.shownText),
    ["AV", "", "To"],
    "blank line survives in rendered lines",
  );
  await settled();
  assert.ok((await cssSize())[1] > joinedH, "blank line offsets later lines");
  assert.ok((await darkBelow(joinedH)) > 0, "line after the blank paints");
  await fillText("word word");
  const oneWordH = (await cssSize())[1];
  await fillText("word word\nword word");
  assert.ok((await cssSize())[1] > oneWordH, "explicit newline starts a new line");
  // A 120-character single line stays on one line and scrolls inside
  // the view: one-line height, extra width, no document overflow.
  // (Same glyph throughout, so the ink extents match exactly.)
  await fillText("n".repeat(8));
  const oneLineH = (await cssSize())[1];
  const oneLineW = (await cssSize())[0];
  await fillText("n".repeat(120));
  assert.deepEqual(
    await page.evaluate(() => ({
      letters: window.YY_SUMMARY.shownLetters,
      lines: window.YY_SUMMARY.shownLines,
      text: window.YY_SUMMARY.shownText,
    })),
    { letters: 120, lines: 1, text: ["n".repeat(120)] },
    "long input renders every letter on one line",
  );
  await settled();
  const longSize = await cssSize();
  assert.equal(longSize[1], oneLineH, "long single line keeps one-line height");
  assert.ok(longSize[0] > oneLineW, "long single line widens instead of wrapping");
  const scroller = await page.locator(".plane figure").evaluate((f) => [f.scrollWidth, f.clientWidth]);
  assert.ok(scroller[0] > scroller[1], "long line scrolls inside the figure");
  assert.ok(
    (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0,
    "long line causes no document overflow",
  );

  // The existing 10-line policy bounds full text: ten ink lines all paint,
  // and text past the cap reuses the same frame with its visible note.
  await fillText("word word");
  const lineH = (await cssSize())[1];
  await fillText(Array(10).fill("word word").join("\n"));
  assert.deepEqual(
    await page.evaluate(() => ({
      letters: window.YY_SUMMARY.shownLetters,
      lines: window.YY_SUMMARY.shownLines,
      text: window.YY_SUMMARY.shownText,
    })),
    { letters: 80, lines: 10, text: Array(10).fill("word word") },
    "ten explicit lines render completely",
  );
  await settled();
  const tenSize = await cssSize();
  assert.ok(tenSize[1] > lineH, "ten lines all paint");
  assert.ok((await darkBelow(lineH)) > 0, "tenth-line region carries ink");
  // The displayed lines stay bounded while input identity retains all 14.
  await fillText(Array(14).fill("word word").join("\n"));
  await page.waitForFunction(
    () =>
      document.getElementById("yy-sample-note").textContent.includes("10 of 14") ||
      document.getElementById("yy-explain-note").textContent.includes("10 of 14"),
    { timeout: 120000 },
  );
  await settled();
  assert.deepEqual(
    await page.evaluate(() => ({
      letters: window.YY_SUMMARY.shownLetters,
      lines: window.YY_SUMMARY.shownLines,
      text: window.YY_SUMMARY.shownText,
    })),
    { letters: 80, lines: 10, text: Array(10).fill("word word") },
    "capped input renders only the first ten lines",
  );
  assert.deepEqual(await cssSize(), tenSize, "capped text reuses the frame");

  // Both profiles and other font sizes keep exact ratios and all lines.
  await fillText("n".repeat(32) + "\nAV");
  // Below-line ink is always measured against a single-line view at the
  // same zoom, since CSS heights scale with the zoom.
  const twoLineProof = async (label) => {
    await page.locator("#yy-zoom").selectOption("1");
    await fillText("n".repeat(32));
    const h1 = (await cssSize())[1];
    await fillText("n".repeat(32) + "\nAV");
    const full = await cssSize();
    await page.locator("#yy-zoom").selectOption("4");
    assert.deepEqual(await cssSize(), [full[0] * 4, full[1] * 4], `exact ratios on ${label}`);
    await fillText("n".repeat(32));
    const h1z = (await cssSize())[1];
    assert.deepEqual(h1z, h1 * 4, `single-line frame scales on ${label}`);
    await fillText("n".repeat(32) + "\nAV");
    assert.deepEqual(await cssSize(), [full[0] * 4, full[1] * 4], `multiline frame scales on ${label}`);
    assert.ok((await darkBelow(h1z)) > 0, `all lines on ${label}`);
    await page.locator("#yy-zoom").selectOption("1");
  };
  for (const profile of ["gray", "mono"]) {
    await page.locator(`input[name="profile"][value="${profile}"]`).check();
    await settled();
    await twoLineProof(profile);
  }
  for (const caseId of ["literata-20", "roboto-8"]) {
    await page.locator("#yy-sample").selectOption(caseId);
    await page.waitForFunction(
      ({ caseId }) =>
        window.YY_SUMMARY?.caseId === caseId &&
        document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
      { caseId },
    );
    await twoLineProof(caseId);
  }
  await page.locator("#yy-sample").selectOption("roboto-16");
  await page.locator('input[name="profile"][value="mono"]').check();
  await page.locator("#yy-text-restore").click();
  await settled();

  // Mobile keeps the shared grid readable without overflow.
  const mob = await browser.newPage({ viewport: { width: 390, height: 844 } });
  mob.on("pageerror", (error) => errors.push("mobile: " + error.message));
  await mob.goto(pathToFileURL(resolve(directory, "index.html")).href);
  await mob.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], { timeout: 30000 });
  await mob.waitForFunction(() => document.getElementById("yy-sample-note").textContent !== "Updating spacing…", {
    timeout: 120000,
  });
  await mob.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.pairLayers !== undefined, { timeout: 180000 });
  const mobSize = await mob.locator("#yy-explain-field").evaluate((c) => [c.width, c.height]);
  assert.ok(mobSize[0] > 0 && mobSize[1] > 0, "mobile field canvas renders");
  assert.ok(
    (await mob.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0,
    "no mobile overflow",
  );
  const mobCss = await mob
    .locator("#yy-explain-field")
    .evaluate((c) => [c.getBoundingClientRect().width, c.getBoundingClientRect().height]);
  await mob.locator("#yy-zoom").selectOption("4");
  await mob.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.zoom === 4, { timeout: 180000 });
  assert.deepEqual(
    await mob
      .locator("#yy-explain-field")
      .evaluate((c) => [c.getBoundingClientRect().width, c.getBoundingClientRect().height]),
    [mobCss[0] * 4, mobCss[1] * 4],
    "mobile magnification scales natively",
  );
  assert.ok(
    (await mob.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0,
    "no mobile overflow at 4x",
  );
  await mob.locator("#yy-zoom").selectOption("1");
  await fillText("AV To", mob);
  await mob.locator("#yy-explain-field").screenshot({ path: resolve(directory, "explain-mobile.png") });
  await mob.close();

  // Self-contained editable demo: same engine, off-grid values match.
  const demo = await browser.newPage({ viewport: { width: 900, height: 900 } });
  demo.on("pageerror", (error) => errors.push("demo: " + error.message));
  await demo.goto(pathToFileURL(demoPath).href);
  await demo.waitForFunction(
    () => window.DEMO_SUMMARY && document.getElementById("demo-note").textContent.includes("widths"),
    { timeout: 30000 },
  );
  const dSize = await demo.locator("#demo-field").evaluate((c) => [c.width, c.height]);
  assert.ok(dSize[0] > 0 && dSize[1] > 0, "demo field canvas renders");
  for (const id of ["#demo-source", "#demo-field-ink"]) {
    const size = await demo.locator(id).evaluate((c) => [c.width, c.height]);
    assert.ok(size[0] > 0 && size[1] > 0, `demo ${id} renders`);
  }
  assert.ok((await demo.locator("#demo-legend span").count()) > 0, "demo legend shows letter swatches");
  const dTint = () =>
    demo.locator("#demo-field").evaluate((c) => {
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 0; i < d.length; i += 4) {
        const spread = Math.max(d[i], d[i + 1], d[i + 2]) - Math.min(d[i], d[i + 1], d[i + 2]);
        if (spread > 40) n++;
      }
      return [n, c.width, c.height];
    });
  const dTint0 = await dTint();
  await demo.locator("#demo-r-in").fill("4");
  await demo.waitForFunction(() => window.DEMO_SUMMARY && window.DEMO_SUMMARY.reach === 4, { timeout: 30000 });
  const dTint1 = await dTint();
  assert.ok(dTint1[0] > dTint0[0], "demo reach spreads blobs");
  assert.deepEqual([dTint1[1], dTint1[2]], [dTint0[1], dTint0[2]], "demo frame fixed");
  await demo.locator("#demo-r-num").fill("2.125");
  await demo.locator("#demo-r-num").dispatchEvent("change");
  await demo.locator("#demo-f-num").fill("4.2");
  await demo.locator("#demo-f-num").dispatchEvent("change");
  await demo.locator("#demo-c-num").fill("1.123");
  await demo.locator("#demo-c-num").dispatchEvent("change");
  await demo.waitForFunction(
    () => window.DEMO_SUMMARY && window.DEMO_SUMMARY.cohesion === 1.123 && window.DEMO_SUMMARY.reach === 2.125,
    { timeout: 30000 },
  );
  const summary = await demo.evaluate(() => window.DEMO_SUMMARY);
  for (const pair of DEMO_PAIRS) {
    const want = refChoice(pair);
    assert.equal(summary.choices[pair].step, want, `demo off-grid choice matches engine for ${pair} (want ${want})`);
  }
  // Novel text edits score on demand through the same core.
  await demo.locator("#demo-text").fill("To qj AV");
  await demo.waitForFunction(
    () =>
      window.DEMO_SUMMARY &&
      window.DEMO_SUMMARY.choices.To &&
      window.DEMO_SUMMARY.choices.qj &&
      !window.DEMO_SUMMARY.choices.Pa,
    { timeout: 30000 },
  );
  const edited = await demo.evaluate(() => window.DEMO_SUMMARY);
  for (const pair of ["To", "qj", "AV"]) {
    assert.equal(edited.choices[pair].step, refChoice(pair), `demo edited choice matches engine for ${pair}`);
  }
  await demo.locator("#demo-text").fill("caf\u00e9");
  await demo.waitForFunction(() => document.getElementById("demo-text-e").textContent.includes("U+00E9"), {
    timeout: 30000,
  });
  assert.ok(
    (await demo.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0,
    "no demo overflow",
  );
  await demo.locator("#demo-field").screenshot({
    path: resolve(directory, "../../yinyang-editable-preview/demo-check.png"),
  });
  await demo.close();
} finally {
  await browser.close();
}
assert.deepEqual(errors, [], `zero page errors: ${JSON.stringify(errors.slice(0, 4))}`);
console.log(JSON.stringify({ status: "passed" }));
