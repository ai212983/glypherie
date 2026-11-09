// cspell:words yinyangfit lede borderless valuetext moverflow msize
// Real-browser behavior check for the v3 YinYang oriented spacing page.
// Loads the offline file:// page at desktop and mobile widths, drives the
// real-value sliders, keyboard steps, exact numeric entries (valid, custom,
// outside-band and invalid), reset, profile, zoom, sample switches with rapid
// cancellation, and requires visible comparison output without document
// overflow. Saves screenshots.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const root = dirname(fileURLToPath(import.meta.url));
const directory = resolve(
  root,
  process.argv[2] || "../../out/diagnostics/contextual-spacing/yinyang-browser-integration/main/staging/site-full",
);
const boot = JSON.parse(await readFile(resolve(directory, "boot.json"), "utf8"));

const ALLOWED_NOTES = [
  "",
  "Font's spacing unchanged.",
  "Nothing to space — enter letters to compare placements.",
  "Loading sample data.",
  "Updating spacing…",
];
// Search-v1 concise notices: target-outside names the closest feasible
// count, fallback retains Source with a reason. Counts depend on the
// sample text and setting, so these match by shape, not by number.
const NOTICE_PATTERNS = [
  /^Target outside measured range for \d+ pairs?; showing closest\.$/,
  /^Font's spacing unchanged\. Target outside measured range for \d+ pairs?; showing closest\.$/,
  /^Source retained for \d+ pairs? \([^)]*\)\.$/,
  /^Font's spacing unchanged\. Source retained for \d+ pairs? \([^)]*\)\.$/,
  /^Source retained for \d+ pairs? \([^)]*\)\. Target outside measured range for \d+ pairs?; showing closest\.$/,
  /^Font's spacing unchanged\. Source retained for \d+ pairs? \([^)]*\)\. Target outside measured range for \d+ pairs?; showing closest\.$/,
];

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.setDefaultTimeout(90000);
  await page.addInitScript(() => {
    const NativeWorker = window.Worker;
    window.__yyWorkerPosts = [];
    window.__yyWorkerCancels = [];
    window.__yyWorkerKinds = { score: 0, map: 0, slate: 0 };
    window.Worker = class extends NativeWorker {
      constructor(...args) {
        super(...args);
      }
      postMessage(message, ...rest) {
        if (message.kind === "score") {
          window.__yyWorkerPosts.push({ id: message.jobId, total: message.items.length });
          window.__yyWorkerKinds.score++;
        }
        if (message.kind === "map") window.__yyWorkerKinds.map++;
        if (message.kind === "slate") window.__yyWorkerKinds.slate++;
        if (message.kind === "cancel") {
          window.__yyWorkerCancels.push({ id: message.jobId });
        }
        return super.postMessage(message, ...rest);
      }
    };
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(pathToFileURL(resolve(directory, "index.html")).href);
  await page.waitForFunction(
    () => document.getElementById("yy-sample") && document.getElementById("yy-sample").options.length === 13,
    undefined,
    { timeout: 30000 },
  );
  await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], undefined, {
    timeout: 30000,
  });
  assert.equal(await page.locator("[title]").count(), 0, "no native title tooltips");

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
  // Field layers arrive after the ink paint through the worker;
  // wait for the first full view.
  await page.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.pairLayers !== undefined, undefined, {
    timeout: 180000,
  });

  // Default view: short title, instruction, prominent field preview.
  assert.equal(await page.locator("h1").textContent(), "YinYang spacing");
  const focusTitle = await page.locator("#yy-focus-title").textContent();
  assert.match(focusTitle, /Roboto 16 px/, `default focus is the root default sample: ${focusTitle}`);
  const fieldDefault = await page.locator("#yy-explain-field").evaluate((c) => [c.width, c.height]);
  assert.ok(fieldDefault[0] > 0 && fieldDefault[1] > 0, "field preview renders");
  assert.match(
    await page.locator("label:has(#yy-show-contrib)").textContent(),
    /Pair contributions/,
    "contribution layer is labelled",
  );
  assert.equal(boot.model, "yinyangfit-oriented-engine-v1", "exclusive oriented model entry");

  // Comparison and the spacing explanation start collapsed.
  for (const id of ["#yy-compare-box", "#yy-select-box"]) {
    assert.equal(await page.locator(id).evaluate((d) => d.open), false, `${id} closed by default`);
  }
  assert.equal(await page.locator("#yy-advanced").count(), 0, "no Advanced section");
  assert.equal(await page.locator("#yy-gallery").count(), 0, "no sample gallery");

  // Plain-ink comparison lives one disclosure away, untouched.
  await page.locator("#yy-compare-box > summary").click();
  for (const id of ["#yy-original", "#yy-adjusted"]) {
    const size = await page.locator(id).evaluate((c) => [c.width, c.height]);
    assert.ok(size[0] > 0 && size[1] > 0, `${id} renders`);
  }
  // Source and Adjusted share magnification and alignment.
  const origBox = await page.locator("#yy-original").evaluate((c) => [c.width, c.height]);
  const adjBox = await page.locator("#yy-adjusted").evaluate((c) => [c.width, c.height]);
  assert.deepEqual(origBox, adjBox, "Source/Adjusted matched bounds");
  const assertDisplayPixels = async (target, message) => {
    for (const id of ["#yy-original", "#yy-adjusted"]) {
      const pixels = await target.locator(id).evaluate((c) => ({
        bitmapWidth: c.width,
        bitmapHeight: c.height,
        displayedWidth: c.clientWidth,
        displayedHeight: c.clientHeight,
      }));
      assert.equal(pixels.displayedWidth, pixels.bitmapWidth, `${message}: ${id} horizontal scale`);
      assert.equal(pixels.displayedHeight, pixels.bitmapHeight, `${message}: ${id} vertical scale`);
    }
  };
  await assertDisplayPixels(page, "native size uses one CSS pixel per bitmap pixel");
  const originalTop = await page.locator("#yy-original").boundingBox();
  assert.ok(originalTop.y + originalTop.height < 1000, "opened comparison is visible at laptop height");
  await page.screenshot({ path: resolve(directory, "desktop-default.png") });

  // All 13 root samples available in the dropdown, in catalogue order.
  assert.equal(await page.locator("#yy-sample option").count(), 13, "13 sample options");
  const optionValues = await page
    .locator("#yy-sample option")
    .evaluateAll((opts) => opts.map((o) => [o.value, o.textContent]));
  assert.deepEqual(
    optionValues.map(([v]) => v),
    boot.cases.map((c) => c.id),
    "dropdown follows boot.cases order",
  );
  for (const c of boot.cases) {
    assert.ok(
      optionValues.some(([v, label]) => v === c.id && label === `${c.family_label} ${c.size_px} px`),
      `option for ${c.id}`,
    );
  }
  assert.equal(await page.locator("#yy-sample").inputValue(), "roboto-16", "default sample retained");

  // One selected comparison only.
  assert.equal(await page.locator("#yy-original").count(), 1, "one Source canvas");
  assert.equal(await page.locator("#yy-adjusted").count(), 1, "one Adjusted canvas");

  // All three model controls plus exact entries are visible by default.
  for (const id of ["#yy-spacing", "#yy-reach", "#yy-falloff", "#yy-spacing-n", "#yy-reach-n", "#yy-falloff-n"]) {
    assert.ok(await page.locator(id).isVisible(), `${id} visible by default`);
  }
  // Two opacity sliders are visible by default with their percents.
  for (const id of ["#yy-letter-alpha", "#yy-contrib-alpha"]) {
    assert.ok(await page.locator(id).isVisible(), `${id} visible by default`);
  }
  assert.equal(await page.locator("#yy-letter-alpha").inputValue(), "65");
  assert.equal(await page.locator("#yy-letter-alpha-v").textContent(), "65%");
  assert.equal(await page.locator("#yy-contrib-alpha").inputValue(), "100");
  assert.equal(await page.locator("#yy-contrib-alpha-v").textContent(), "100%");
  assert.match(await page.locator('label[for="yy-letter-alpha"]').textContent(), /Letter fields opacity/);
  assert.match(await page.locator('label[for="yy-contrib-alpha"]').textContent(), /Pair contributions opacity/);
  assert.match(await page.locator('label[for="yy-spacing"]').textContent(), /^Target score/);

  // Sliders carry the approved real numeric bands, linear.
  const bands = await page.evaluate(() =>
    ["yy-spacing", "yy-reach", "yy-falloff"].map((id) => {
      const s = document.getElementById(id);
      return [s.min, s.max, s.step, s.value];
    }),
  );
  assert.deepEqual(
    bands,
    [
      ["0", "128", "0.1", "4"],
      ["4", "24", "1", "12"],
      ["0.5", "10", "0.5", "2"],
    ],
    "approved slider min/max/step/defaults",
  );

  // Rendered canvases carry no border.
  for (const id of ["#yy-original", "#yy-adjusted"]) {
    const border = await page.locator(id).evaluate((c) => getComputedStyle(c).borderWidth);
    assert.equal(border, "0px", `${id} borderless`);
  }

  // No horizontal document overflow at laptop width.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  assert.ok(overflow <= 0, `no horizontal overflow at 1280px (got ${overflow})`);

  // Primary slider moves the visible comparison (fast path, synchronous).
  const before = await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL());
  await page.locator("#yy-spacing").fill("20");
  await settled();
  const afterHigh = await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL());
  await page.locator("#yy-spacing").fill("0");
  await settled();
  const afterLow = await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL());
  assert.ok(afterHigh !== before || afterLow !== before, "target slider changes the adjusted view");

  // Keyboard steps the slider by its numeric step with real narration.
  await page.locator("#yy-spacing").press("ArrowRight");
  await settled();
  assert.equal(await page.locator("#yy-spacing").inputValue(), "0.1");
  const narration = await page.locator("#yy-spacing").getAttribute("aria-valuetext");
  assert.match(narration, /Target score 0\.1/, `aria narrates the real value and starting value: ${narration}`);
  // Reach/falloff show actual values with narration.
  assert.match(await page.locator("#yy-reach-v").textContent(), /12 px/);
  assert.match(await page.locator("#yy-reach").getAttribute("aria-valuetext"), /Edge reach 12 pixels/);
  assert.match(await page.locator("#yy-falloff-v").textContent(), /^2$/);
  assert.match(await page.locator("#yy-falloff").getAttribute("aria-valuetext"), /Distance falloff 2/);

  // Reach keyboard moves whole pixels without rounding the display.
  await page.locator("#yy-reach").press("ArrowRight");
  await settled();
  assert.equal(await page.locator("#yy-reach").inputValue(), "13");
  assert.match(await page.locator("#yy-reach-v").textContent(), /13 px/, "integer reach displays fully");
  await page.locator("#yy-reach").fill("12");

  // Exact numeric entries keep full precision as the model setting.
  await page.locator("#yy-spacing-n").fill("1.125");
  await page.locator("#yy-spacing-n").press("Enter");
  await settled();
  assert.match(
    await page.locator("#yy-spacing-v").textContent(),
    /1\.125/,
    "typed target is the displayed setting, not a grid snap",
  );
  assert.match(await page.locator("#yy-spacing-x").textContent(), /Using 1\.125/, "off-grid value is labelled custom");
  await page.locator("#yy-reach-n").fill("13");
  await page.locator("#yy-reach-n").press("Enter");
  await settled();
  assert.match(await page.locator("#yy-reach-v").textContent(), /13 px/, "typed integer reach applies");
  const beforeFalloffJobs = await page.evaluate(() => window.__yyWorkerPosts.length);
  await page.locator("#yy-falloff-n").fill("4.2");
  await page.locator("#yy-falloff-n").press("Enter");
  await settled();
  assert.match(await page.locator("#yy-falloff-v").textContent(), /4\.2/, "typed falloff keeps its precision");
  assert.equal(
    await page.evaluate(() => window.__yyWorkerPosts.length),
    beforeFalloffJobs + 1,
    "one input change starts one worker job",
  );
  const beforeCstarJobs = await page.evaluate(() => window.__yyWorkerPosts.length);
  await page.locator("#yy-spacing-n").fill("0");
  await page.locator("#yy-spacing-n").press("Enter");
  await settled();
  const lowCstarPixels = await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL());
  await page.locator("#yy-spacing-n").fill("128");
  await page.locator("#yy-spacing-n").press("Enter");
  await settled();
  assert.notEqual(
    await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL()),
    lowCstarPixels,
    "cached geometry still applies the new target choice",
  );
  assert.equal(
    await page.evaluate(() => window.__yyWorkerPosts.length),
    beforeCstarJobs,
    "target changes reuse geometry without worker scoring",
  );
  await page.locator("#yy-spacing-n").fill("1.125");
  await page.locator("#yy-spacing-n").press("Enter");
  await settled();
  // The summary records the actual triple, not a snapped one.
  await page.waitForFunction(
    () =>
      window.YY_SUMMARY &&
      window.YY_SUMMARY.cstar === 1.125 &&
      window.YY_SUMMARY.reach === 13 &&
      window.YY_SUMMARY.falloff === 4.2,
    undefined,
    { timeout: 180000 },
  );
  const summaryTriple = await page.evaluate(() => ({
    cstar: window.YY_SUMMARY.cstar,
    reach: window.YY_SUMMARY.reach,
    falloff: window.YY_SUMMARY.falloff,
  }));
  assert.deepEqual(
    summaryTriple,
    { cstar: 1.125, reach: 13, falloff: 4.2 },
    "summary records the exact entered triple",
  );
  const computedOrigins = await page.evaluate(() => window.YY_SUMMARY.origins.join(" / "));

  // Outside-band entries compute exactly and say so.
  await page.locator("#yy-falloff-n").fill("2");
  await page.locator("#yy-falloff-n").press("Enter");
  await settled();
  await page.locator("#yy-reach-n").fill("30");
  await page.locator("#yy-reach-n").press("Enter");
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent === "Updating spacing…",
    undefined,
    { timeout: 15000 },
  );
  await settled();
  assert.match(
    await page.locator("#yy-reach-x").textContent(),
    /beyond the slider range/,
    "outside-band value is labelled, thumb not misrepresented",
  );

  // Invalid entries keep the last valid render with a clear message.
  const validView = await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL());
  await page.locator("#yy-reach-n").fill("abc");
  await page.locator("#yy-reach-n").press("Enter");
  assert.match(
    await page.locator("#yy-reach-e").textContent(),
    /reach must be a number/,
    "invalid entry message names the parameter",
  );
  assert.equal(
    await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL()),
    validView,
    "invalid entry keeps the last valid render",
  );
  await page.locator("#yy-spacing-n").fill("129");
  await page.locator("#yy-spacing-n").press("Enter");
  assert.match(
    await page.locator("#yy-spacing-e").textContent(),
    /target must be in \[0, 128\]/,
    "out-of-guardrail target is rejected, not clamped",
  );
  assert.equal(
    await page.locator("#yy-reach-n").inputValue(),
    "abc",
    "editing another control preserves the invalid draft",
  );
  assert.match(
    await page.locator("#yy-reach-e").textContent(),
    /reach must be a number/,
    "editing another control preserves its validation message",
  );
  await page.locator("#yy-spacing-n").fill("");
  await page.locator("#yy-spacing-n").press("Enter");
  assert.match(
    await page.locator("#yy-spacing-e").textContent(),
    /Enter a number/,
    "empty entry is rejected, not treated as zero",
  );
  await page.locator("#yy-falloff-n").fill("0");
  await page.locator("#yy-falloff-n").press("Enter");
  assert.match(
    await page.locator("#yy-falloff-e").textContent(),
    /falloff must be in \[0\.25, 16\]/,
    "non-positive falloff is rejected",
  );
  await page.locator("#yy-reach-n").fill("33");
  await page.locator("#yy-reach-n").press("Enter");
  assert.match(
    await page.locator("#yy-reach-e").textContent(),
    /reach must be an integer in \[1, 32\]/,
    "out-of-guardrail reach is rejected, not clamped",
  );
  await page.locator("#yy-reach-n").fill("13.5");
  await page.locator("#yy-reach-n").press("Enter");
  assert.match(
    await page.locator("#yy-reach-e").textContent(),
    /reach must be an integer in \[1, 32\]/,
    "fractional reach errors, never rounds",
  );

  // Reset resolves by value and synchronizes both controls.
  await page.locator("#yy-reset").click();
  await settled();
  assert.equal(await page.locator("#yy-spacing").inputValue(), "4");
  assert.equal(await page.locator("#yy-reach").inputValue(), "12");
  assert.equal(await page.locator("#yy-falloff").inputValue(), "2");
  assert.equal(await page.locator("#yy-spacing-n").inputValue(), "4");
  assert.equal(await page.locator("#yy-reach-n").inputValue(), "12");
  assert.equal(await page.locator("#yy-falloff-n").inputValue(), "2");
  assert.match(await page.locator("#yy-spacing").getAttribute("aria-valuetext"), /Target score 4/);

  // Feedback stays within the approved messages.
  await page.locator("#yy-spacing").fill("0");
  await settled();
  const note = await page.locator("#yy-sample-note").textContent();
  assert.ok(
    ALLOWED_NOTES.includes(note) || NOTICE_PATTERNS.some((re) => re.test(note)),
    `approved feedback only: ${JSON.stringify(note)}`,
  );
  await page.locator("#yy-reset").click();
  await settled();

  // Editable preview text drives ink and fields through guarded compute.
  assert.match(await page.locator("#yy-text").inputValue(), /Pack my box/, "text field seeded from the sample");
  await fillText("AV To og qj");
  await settled();
  assert.equal(await page.locator("#yy-text-restore").isHidden(), false, "restore appears after an edit");
  assert.match(
    await page.locator("label:has(#yy-show-letter)").textContent(),
    /Letter fields/,
    "letter layer is labelled",
  );
  assert.ok(
    await page.evaluate(() => Array.isArray(window.YY_SUMMARY.origins) && window.YY_SUMMARY.origins.length > 0),
    "novel qj lays out beside shipped columns",
  );
  // The draft survives profile switches and still paints.
  await page.locator('input[name="profile"][value="gray"]').check();
  await settled();
  assert.equal(
    await page.evaluate(() => window.YY_SUMMARY.text),
    "AV To og qj",
    "custom text preserved across profile switch",
  );
  await page.locator('input[name="profile"][value="mono"]').check();
  await settled();
  // Unsupported characters name the codepoint and keep the last paint.
  const textPaint = await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL());
  await page.locator("#yy-text").fill("To qjé");
  await page.waitForFunction(() => document.getElementById("yy-text-e").textContent.includes("U+00E9"), undefined, {
    timeout: 30000,
  });
  assert.match(
    await page.locator("#yy-sample-note").textContent(),
    /Showing the last valid text/,
    "stale paint is labelled, not passed off",
  );
  assert.equal(
    await page.locator("#yy-adjusted").evaluate((c) => c.toDataURL()),
    textPaint,
    "unsupported draft keeps the last valid paint",
  );
  // Empty text settles with an explanatory note; restore returns the sample.
  await page.locator("#yy-text").fill("");
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent.includes("Nothing to space"),
    undefined,
    { timeout: 120000 },
  );
  await page.locator("#yy-text-restore").click();
  await settled();
  assert.match(await page.locator("#yy-text").inputValue(), /Pack my box/, "restore returns the sample text");
  // Fourteen explicit lines cap at ten with a truthful note, never silent truncation.
  await fillText(Array(14).fill("word word").join("\n"));
  await page.waitForFunction(
    () => document.getElementById("yy-sample-note").textContent.includes("Showing the first 10 of 14 lines"),
    undefined,
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
    "line cap renders the first ten explicit lines",
  );
  // A 120-character single line stays single and scrolls inside the view.
  assert.equal(
    await page.locator("#yy-text").getAttribute("wrap"),
    "off",
    "textarea disables wrapping so entry matches output",
  );
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
  const longScroll = await page.locator(".plane figure").evaluate((f) => [f.scrollWidth, f.clientWidth]);
  assert.ok(longScroll[0] > longScroll[1], "long line scrolls inside the view");
  assert.ok(
    (await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) <= 0,
    "long line causes no document overflow",
  );
  await page.locator("#yy-text-restore").click();
  await settled();
  assert.equal(await page.locator("#yy-text-restore").isHidden(), true, "restore hides once the sample text is back");

  // Shared profile switch re-renders both comparison columns.
  await page.locator('input[name="profile"][value="gray"]').check();
  await settled();
  await page.waitForFunction(
    () => window.YY_SUMMARY && window.YY_SUMMARY.profile === "gray" && window.YY_SUMMARY.pairLayers > 0,
    undefined,
    { timeout: 180000 },
  );
  assert.match(await page.locator("#yy-focus-title").textContent(), /grayscale/);
  const grayAdj = await page.locator("#yy-adjusted").evaluate((c) => [c.width, c.height]);
  assert.ok(grayAdj[0] > 0 && grayAdj[1] > 0, "grayscale renders");

  // Shared magnification grows the comparison.
  await page.locator("#yy-zoom").selectOption("4");
  const zoomed = await page.locator("#yy-adjusted").evaluate((c) => [c.width, c.height]);
  assert.ok(zoomed[0] >= grayAdj[0] && zoomed[1] >= grayAdj[1], "magnification applies");
  await assertDisplayPixels(page, "magnified pixels retain their requested display size");
  // Zoom and opacity reuse cached layers: no worker traffic of any kind.
  const kindsBeforeDisplay = await page.evaluate(() => ({ ...window.__yyWorkerKinds }));
  await page.locator("#yy-letter-alpha").fill("40");
  await page.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.letterAlpha === 0.4, undefined, {
    timeout: 30000,
  });
  await page.locator("#yy-zoom").selectOption("1");
  await page.waitForFunction(() => window.YY_SUMMARY && window.YY_SUMMARY.zoom === 1, undefined, { timeout: 30000 });
  assert.deepEqual(
    await page.evaluate(() => window.__yyWorkerKinds),
    kindsBeforeDisplay,
    "opacity and zoom repaint from cache without worker traffic",
  );
  // Zooming back out reuses the cached maps (no new map posts).
  assert.ok(kindsBeforeDisplay.map > 0, "map cache populated before reuse check");

  // Dropdown switches the single comparison without touching other controls.
  await page.locator("#yy-spacing").fill("0");
  await settled();
  await page.locator("#yy-sample").selectOption("rouge-script-20");
  await page.waitForFunction(() => document.getElementById("yy-focus-title").textContent.includes("Rouge Script"));
  // The lazy dataset script can still be in flight while the title (set
  // before the table arrives) already matches; the cancel step below must
  // post its job synchronously, so wait for the table itself.
  await page.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["rouge-script-20-gray"], undefined, {
    timeout: 30000,
  });
  const rouge = await page.locator("#yy-adjusted").evaluate((c) => [c.width, c.height]);
  assert.ok(rouge[0] > 0 && rouge[1] > 0, "rouge sample renders");
  assert.equal(await page.locator("#yy-spacing").inputValue(), "0", "spacing value retained across sample switch");
  assert.equal(await page.locator("#yy-sample").inputValue(), "rouge-script-20", "dropdown reflects the chosen sample");

  // Rapid computed changes settle on the latest choice (cancellation).
  const cancelsBefore = await page.evaluate(() => window.__yyWorkerCancels.length);
  await page.locator("#yy-reach-n").fill("13");
  await page.locator("#yy-reach-n").press("Enter");
  await page.locator("#yy-reach-n").fill("15");
  await page.locator("#yy-reach-n").press("Enter");
  await page.waitForFunction(() => document.getElementById("yy-reach-v").textContent.includes("15 px"));
  await settled();
  assert.match(await page.locator("#yy-reach-v").textContent(), /15 px/, "rapid entries settle on the latest value");
  await page.waitForFunction(
    () => window.YY_SUMMARY && window.YY_SUMMARY.reach === 15 && window.YY_SUMMARY.pairLayers > 0,
    undefined,
    { timeout: 180000 },
  );
  assert.equal(await page.evaluate(() => window.YY_SUMMARY.reach), 15, "latest choice paints");
  assert.ok(
    await page.evaluate((n) => window.__yyWorkerCancels.length > n, cancelsBefore),
    "superseded worker scoring is cancelled",
  );
  await page.locator("#yy-sample").selectOption("roboto-8");
  await page.locator("#yy-sample").selectOption("literata-12");
  await page.waitForFunction(
    () =>
      document.getElementById("yy-focus-title").textContent.includes("Literata") &&
      document.getElementById("yy-sample").value === "literata-12",
  );
  await settled();
  const settledView = await page.locator("#yy-adjusted").evaluate((c) => [c.width, c.height]);
  assert.ok(settledView[0] > 0 && settledView[1] > 0, "settled sample renders");
  assert.equal(await page.locator("#yy-sample").inputValue(), "literata-12", "selection reflects the latest choice");
  await page.locator("#yy-reset").click();
  await page.locator("#yy-sample").selectOption("roboto-16");
  await page.waitForFunction(() => document.getElementById("yy-focus-title").textContent.includes("Roboto 16"));
  await settled();

  // Keyboard drives the dropdown via native select type-ahead.
  await page.locator("#yy-sample").focus();
  await page.locator("#yy-sample").press("l");
  assert.equal(await page.locator("#yy-sample").inputValue(), "literata-8", "type-ahead moves to the matching sample");
  await page.waitForFunction(() => document.getElementById("yy-focus-title").textContent.includes("Literata 8"));
  await page.locator("#yy-sample").selectOption("roboto-16");
  await page.waitForFunction(() => document.getElementById("yy-focus-title").textContent.includes("Roboto 16"));
  await settled();

  for (const id of [
    "#yy-pairs",
    "#yy-pair",
    "#yy-pair-metric",
    "#yy-pair-chosen",
    "#yy-pair-field",
    "#yy-scores-box",
    "#yy-explain-scores",
    "#yy-pair-note",
    "#yy-about-box",
    "#yy-about",
  ]) {
    assert.equal(await page.locator(id).count(), 0, `${id} removed`);
  }

  // Diagnostics are gone by design: no dumps, tables, or provenance panels.
  assert.equal(await page.locator("#yy-diagnostics-box").count(), 0, "diagnostics section removed from the user page");
  assert.equal(await page.locator("#yy-diagnostics").count(), 0, "no diagnostics node in the user page");
  assert.equal(await page.locator("#yy-coupling-box").count(), 0, "coupling diagnostics removed from the user page");

  await page.screenshot({ path: resolve(directory, "interaction-check.png") });
  assert.deepEqual(errors, [], `page errors: ${errors.join("; ")}`);

  // Chunked main-thread fallback computes the identical origins.
  const fallback = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  fallback.setDefaultTimeout(90000);
  try {
    await fallback.addInitScript(() => {
      delete window.Worker;
    });
    fallback.on("pageerror", (error) => errors.push(error.message));
    await fallback.goto(pathToFileURL(resolve(directory, "index.html")).href);
    await fallback.waitForFunction(() => window.YY_TABLES && window.YY_TABLES["roboto-16-mono"], undefined, {
      timeout: 30000,
    });
    await fallback.locator("#yy-spacing-n").fill("1.125");
    await fallback.locator("#yy-spacing-n").press("Enter");
    await fallback.locator("#yy-reach-n").fill("13");
    await fallback.locator("#yy-reach-n").press("Enter");
    await fallback.locator("#yy-falloff-n").fill("4.2");
    await fallback.locator("#yy-falloff-n").press("Enter");
    await fallback.waitForFunction(
      () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
      undefined,
      { timeout: 180000 },
    );
    await fallback.waitForFunction(() => window.YY_SUMMARY && Array.isArray(window.YY_SUMMARY.origins), undefined, {
      timeout: 180000,
    });
    const fallbackOrigins = await fallback.evaluate(() => window.YY_SUMMARY.origins.join(" / "));
    assert.equal(fallbackOrigins, computedOrigins, "fallback matches worker origins");
  } finally {
    await fallback.close();
  }
  assert.deepEqual(errors, [], `page errors: ${errors.join("; ")}`);

  // Narrow mobile width: comparison stacks, no document overflow.
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  mobile.setDefaultTimeout(90000);
  try {
    mobile.on("pageerror", (error) => errors.push(error.message));
    await mobile.goto(pathToFileURL(resolve(directory, "index.html")).href);
    await mobile.waitForFunction(
      () => document.getElementById("yy-sample") && document.getElementById("yy-sample").options.length === 13,
      undefined,
      { timeout: 30000 },
    );
    const moverflow = await mobile.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    assert.ok(moverflow <= 0, `no horizontal overflow at 390px (got ${moverflow})`);
    const msize = await mobile.locator("#yy-adjusted").evaluate((c) => [c.width, c.height]);
    assert.ok(msize[0] > 0 && msize[1] > 0, "mobile comparison renders");
    await mobile.locator("#yy-compare-box > summary").click();
    await assertDisplayPixels(mobile, "mobile native size is not shrunk to fit");
    await mobile.locator("#yy-reach-n").fill("13");
    await mobile.locator("#yy-reach-n").press("Enter");
    await mobile.waitForFunction(
      () => document.getElementById("yy-sample-note").textContent !== "Updating spacing…",
      undefined,
      { timeout: 180000 },
    );
    assert.match(await mobile.locator("#yy-reach-v").textContent(), /13 px/, "mobile numeric entry keeps precision");
    await mobile.locator("#yy-zoom").selectOption("4");
    await assertDisplayPixels(mobile, "mobile magnification is not shrunk to fit");
    const zoomOverflow = await mobile.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    assert.ok(zoomOverflow <= 0, "magnified views scroll inside the comparison without document overflow");
    await mobile.locator("#yy-zoom").selectOption("1");
    await mobile.screenshot({ path: resolve(directory, "mobile-check.png") });
  } finally {
    await mobile.close();
  }
  assert.deepEqual(errors, [], `page errors: ${errors.join("; ")}`);
  console.log(JSON.stringify({ status: "passed", errors: 0 }));
} finally {
  await browser.close();
}
