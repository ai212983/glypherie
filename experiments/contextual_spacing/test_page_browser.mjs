// Real browser check of the generated offline page and Python placement parity.
// Uses the web component's installed Playwright dependency; starts no server.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright-core");
const directory = resolve(process.argv[2] ?? "");
if (!process.argv[2]) throw new Error("usage: node test_page_browser.mjs EXPORTED_PAGE_DIRECTORY");
const data = JSON.parse(await readFile(resolve(directory, "page-data.json"), "utf8"));
const readingSample = (
  await readFile(new URL("./tests/fixtures/reading-sample.txt", import.meta.url), "utf8")
).trimEnd();
const readingSampleCodepoints = [
  ...new Set(
    Array.from(readingSample)
      .filter((character) => character !== "\n")
      .map((character) => character.codePointAt(0)),
  ),
].sort((a, b) => a - b);
const browser = await chromium.launch({
  executablePath:
    process.env.WEB_TEST_BROWSER ?? (process.platform === "darwin" ? undefined : "/opt/google/chrome/chrome"),
  headless: true,
});
try {
  const context = await browser.newContext({ viewport: { width: 1200, height: 1000 }, offline: true });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(pathToFileURL(resolve(directory, "index.html")).href);
  await page.getByRole("status").filter({ hasText: "Complete" }).waitFor();
  await page.locator("#custom-grayscale-details").evaluate((details) => {
    details.open = true;
  });
  assert.equal(await page.getByLabel("Captured font").locator("option").count(), data.cases.length);
  assert.equal(await page.locator("[title]").count(), 0, "no native title tooltips");
  // The runtime already contains every table. Sending the full ~100MB capture
  // bundle through Playwright duplicates its object graph in the transport and
  // can exhaust Node's heap. Transfer bounded fixture batches, not table copies.
  await page.evaluate(() => {
    globalThis.__spacingVerificationData = JSON.parse(document.getElementById("spacing-data").textContent);
  });
  let parity = 0;
  for (const font of data.cases)
    for (let start = 0; start < font.verification.length; start += 50) {
      parity += await page.evaluate(
        ({ id, fixtures }) => {
          const font = globalThis.__spacingVerificationData.cases.find((entry) => entry.id === id);
          if (!font) throw new Error("Missing browser verification font");
          // Object key insertion order differs across the two languages.
          const canonical = (value) =>
            JSON.stringify(value, (_key, entry) =>
              entry && !Array.isArray(entry) && typeof entry === "object"
                ? Object.fromEntries(Object.entries(entry).sort(([a], [b]) => a.localeCompare(b)))
                : entry,
            );
          for (const fixture of fixtures) {
            const actual = globalThis.ContextualSpacing.layout(
              font,
              fixture.text,
              fixture.kIndex,
              fixture.oIndex,
              fixture.letterSpacing,
              fixture.wordSpacing,
              fixture.width,
              fixture.preserveTabularSpacing,
              fixture.spacingModel,
            );
            if (canonical(actual) !== canonical(fixture.expected))
              throw new Error(
                `Python/browser layout mismatch: ${font.label}, model=${fixture.spacingModel}, k=${fixture.kIndex}, o=${fixture.oIndex}, width=${fixture.width}`,
              );
          }
          return fixtures.length;
        },
        { id: font.id, fixtures: font.verification.slice(start, start + 50) },
      );
    }
  await page.evaluate(() => {
    globalThis.__grayscaleVerificationFonts = globalThis.__spacingVerificationData.cases.map((font) => font.grayscale);
    globalThis.__sourceMonoVerificationFonts = globalThis.__spacingVerificationData.cases.map(
      ContextualSpacing.sourceLinearMono,
    );
    delete globalThis.__spacingVerificationData;
  });
  const grayscaleChecks = [],
    sourceMonoChecks = [];
  for (const [index, font] of data.cases.entries()) {
    if (!font.grayscale) continue;
    const source = JSON.parse(await readFile(resolve(font.grayscale.capturePath), "utf8")).font;
    const glyphs = new Map(source.glyphs.map((glyph) => [glyph.codepoint, glyph]));
    const pairs = new Map(source.kerning.map((pair) => [`${pair.left},${pair.right}`, pair.adjustment_26_6 / 64]));
    // Independent expectations read native records, bypassing the page exporter.
    for (const text of [font.defaultText, ...(data.presets || []).map((preset) => preset.text)]) {
      const expected = [];
      let line = { width_px: 0, placements: [] };
      for (const [position, character] of Array.from(text).entries()) {
        if (character === "\n") {
          expected.push(line);
          line = { width_px: 0, placements: [] };
          continue;
        }
        const cp = character.codePointAt(0),
          glyph = glyphs.get(cp);
        const previous = line.placements.at(-1)?.codepoint;
        let origin = line.width_px + (pairs.get(`${previous},${cp}`) || 0);
        if (line.placements.length && origin + glyph.advance_26_6 / 64 > 280) {
          expected.push(line);
          line = { width_px: 0, placements: [] };
          origin = 0;
        }
        line.placements.push({
          index: position,
          codepoint: cp,
          glyph_id: glyph.glyph_id,
          variant: "original",
          x_px: origin,
          advance_px: glyph.advance_26_6 / 64,
        });
        line.width_px = origin + glyph.advance_26_6 / 64;
      }
      expected.push(line);
      const actual = await page.evaluate(
        ({ index, text }) => {
          return ContextualSpacing.layoutGrayscale(globalThis.__grayscaleVerificationFonts[index], text, 280);
        },
        { index, text },
      );
      assert.deepEqual(actual.lines, expected);
      if (font.sourceLayout) {
        const sourceMono = await page.evaluate(
          ({ index, text }) =>
            ContextualSpacing.layoutGrayscale(globalThis.__sourceMonoVerificationFonts[index], text, 280),
          { index, text },
        );
        assert.deepEqual(sourceMono, actual, `${font.label}: Mono and Gray use identical vanilla placements`);
        sourceMonoChecks.push({ font: font.label, characters: Array.from(text).length, lines: expected.length });
      }
      grayscaleChecks.push({ font: font.label, characters: Array.from(text).length, lines: expected.length });
    }
    await page.getByLabel("Captured font").selectOption(String(index));
    await page.getByLabel("Sample text").fill(
      Array.from("AV noé")
        .filter((c) => font.codepoints.includes(c.codePointAt(0)))
        .join(""),
    );
    assert.equal(await page.locator("#grayscale-comparison").isVisible(), true);
    const grayscaleBefore = await page.locator("#grayscale-native").evaluate((canvas) => canvas.toDataURL());
    const sourceMonoBefore = font.sourceLayout
      ? await page.locator("#source-mono-native").evaluate((canvas) => canvas.toDataURL())
      : null;
    for (const [id, value] of [
      ["kerning", "0"],
      ["optical", "0"],
      ["letter", "2"],
      ["word", "3"],
    ]) {
      await page.locator(`#${id}`).evaluate((element, value) => {
        element.value = value;
        element.dispatchEvent(new Event("input", { bubbles: true }));
      }, value);
    }
    assert.equal(await page.locator("#grayscale-native").evaluate((canvas) => canvas.toDataURL()), grayscaleBefore);
    if (sourceMonoBefore) {
      assert.equal(
        await page.locator("#source-mono-native").evaluate((canvas) => canvas.toDataURL()),
        sourceMonoBefore,
      );
      assert.equal(
        await page.locator("#source-mono-native").evaluate((canvas) => {
          const rgba = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
          return rgba.every((v, i) => (i % 4 === 3 ? v === 255 : v === 0 || v === 255));
        }),
        true,
        "source-linear Mono draws original binary cells without interpolation",
      );
    }
    const shades = await page.locator("#grayscale-native").evaluate((canvas) => {
      const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      return [...new Set(Array.from(pixels).filter((_v, i) => i % 4 === 0))];
    });
    assert.ok(
      shades.some((shade) => shade > 0 && shade < 255),
      "grayscale retains intermediate ink levels",
    );
    // A single non-overlapping glyph checks the exact level-to-display mapping.
    await page.getByLabel("Sample text").fill("A");
    const actualPixels = await page.locator("#grayscale-native").evaluate((canvas) => {
      const rgba = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      const histogram = {};
      for (let i = 0; i < rgba.length; i += 4) if (rgba[i] < 255) histogram[rgba[i]] = (histogram[rgba[i]] || 0) + 1;
      return histogram;
    });
    const expectedPixels = {};
    for (const ink of glyphs.get(65).pixels)
      if (ink) {
        const shade = 255 - Math.round((ink * 255) / 7);
        expectedPixels[shade] = (expectedPixels[shade] || 0) + 1;
      }
    assert.deepEqual(
      actualPixels,
      expectedPixels,
      `${font.label}: captured grayscale levels reach the canvas unchanged`,
    );
    await page.getByLabel("Sample text").fill("A A A");
    const repeatedPixels = await page.locator("#grayscale-native").evaluate((canvas) => {
      const rgba = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      const histogram = {};
      for (let i = 0; i < rgba.length; i += 4) if (rgba[i] < 255) histogram[rgba[i]] = (histogram[rgba[i]] || 0) + 1;
      return histogram;
    });
    assert.deepEqual(
      repeatedPixels,
      Object.fromEntries(Object.entries(expectedPixels).map(([shade, count]) => [shade, count * 3])),
      `${font.label}: fractional accumulated origins draw complete glyph cells without interpolation`,
    );
    await page.getByRole("button", { name: "Reset controls" }).click();
  }
  await page.evaluate(() => {
    delete globalThis.__grayscaleVerificationFonts;
    delete globalThis.__sourceMonoVerificationFonts;
  });
  const contactChecks = [];
  const contactOracle = (a, b, step) => {
    const cells = (bitmap, origin) =>
      bitmap.pixels.flatMap((ink, i) =>
        ink ? [[origin + bitmap.left + (i % bitmap.width), bitmap.top + Math.floor(i / bitmap.width)]] : [],
      );
    const expected = { overlaps: 0, faces: 0, corners: 0 },
      marked = new Set();
    for (const [ax, ay] of cells(a, 0))
      for (const [bx, by] of cells(b, step)) {
        const dx = Math.abs(ax - bx),
          dy = Math.abs(ay - by);
        const kind =
          dx === 0 && dy === 0 ? "overlaps" : dx + dy === 1 ? "faces" : dx === 1 && dy === 1 ? "corners" : null;
        if (kind) {
          expected[kind]++;
          marked.add(`${ax},${ay}`);
          marked.add(`${bx},${by}`);
        }
      }
    return { ...expected, markedCells: marked.size };
  };
  for (const [index, font] of data.cases.entries()) {
    if (!font.models.hu_source_relative || ![116, 121].every((cp) => font.codepoints.includes(cp))) continue;
    await page.getByLabel("Captured font").selectOption(String(index));
    await page.getByRole("button", { name: "Reset controls" }).click();
    await page.locator("#spacing-model").selectOption("hu_source_relative");
    await page.getByLabel("Sample text").fill("ty type type type\nyp pe");
    await page.getByLabel("Inspect pair").selectOption("116,121");
    const left = font.glyphs.find((g) => g.codepoint === 116),
      right = font.glyphs.find((g) => g.codepoint === 121);
    const pairIndex = font.codepoints.indexOf(116) * font.codepoints.length + font.codepoints.indexOf(121);
    const emitted = left.advancePx + font.models.hu_source_relative.pairTables[24][pairIndex];
    for (const [id, delta] of [
      ["tighter", -1],
      ["selected", 0],
      ["looser", 1],
    ]) {
      const step = emitted + delta,
        expected = contactOracle(left.bitmap, right.bitmap, step);
      const counts = await page.locator(`#pair-${id}-contact-count`).evaluate((el) => ({
        overlaps: Number(el.dataset.overlaps),
        faces: Number(el.dataset.faces),
        corners: Number(el.dataset.corners),
      }));
      for (const key of ["overlaps", "faces", "corners"]) assert.equal(counts[key], expected[key]);
      const colored = await page.locator(`#pair-${id}-contacts`).evaluate((canvas) => {
        const rgba = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
        let count = 0;
        for (let i = 0; i < rgba.length; i += 4) if (rgba[i] !== rgba[i + 1] || rgba[i + 1] !== rgba[i + 2]) count++;
        return count;
      });
      assert.equal(colored, expected.markedCells, "every actual touching cell is highlighted exactly once");
      contactChecks.push({ font: font.label, pair: "ty", step, ...expected });
    }
  }
  await page.getByRole("button", { name: "Reset controls" }).click();
  const setRange = async (id, value) =>
    page.locator(`#${id}`).evaluate((element, next) => {
      element.value = String(next);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    }, value);
  const numericRegressions = [];
  assert.equal(await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).isChecked(), false);
  assert.equal(await page.locator("#spacing-model").inputValue(), data.defaultSpacingModel);
  for (const [index, font] of data.cases.entries()) {
    if (![48, 49, 50, 51].every((cp) => font.codepoints.includes(cp)) || font.monospace) continue;
    await page.getByLabel("Captured font").selectOption(String(index));
    await page.getByLabel("Sample text").fill("01 12 23");
    await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).uncheck();
    const measurements = {};
    for (const modelName of Object.keys(font.models)) {
      await page.locator("#spacing-model").selectOption(modelName);
      measurements[modelName] = [];
      for (const [left, right] of [
        [48, 49],
        [49, 50],
        [50, 51],
      ]) {
        await page.getByLabel("Inspect pair").selectOption(`${left},${right}`);
        const pairIndex = font.codepoints.indexOf(left) * font.codepoints.length + font.codepoints.indexOf(right);
        const model = font.models[modelName];
        const expected = data.diagnosticLabels[model.pairDiagnostics[24][pairIndex]];
        assert.equal(
          await page.locator("#pair-outcome").getAttribute("data-diagnostic"),
          expected,
          `${font.label} ${modelName}`,
        );
        if (modelName.startsWith("counterspace")) {
          const target = model.pairTargetScores[24][pairIndex];
          assert.equal(
            await page.locator("#pair-separation").isVisible(),
            false,
            "CounterSpace scores are not pixel separations",
          );
          const score = await page.locator("#pair-score").evaluate((element) => ({
            target: element.dataset.target === undefined ? null : Number(element.dataset.target),
            realized: element.dataset.realized === undefined ? null : Number(element.dataset.realized),
            error: element.dataset.error === undefined ? null : Number(element.dataset.error),
          }));
          assert.equal(score.target, target);
          assert.equal(score.realized, model.pairRealizedScores[24][pairIndex]);
          assert.equal(score.error, model.pairScoreErrors[24][pairIndex]);
          const metadata = model.pairTargetMetadata[pairIndex];
          assert.equal(await page.locator("#pair-search").getAttribute("data-outcome"), metadata.search_outcome || "");
          assert.equal(await page.locator("#pair-search").getAttribute("data-policy"), metadata.search_policy || "");
          assert.equal(
            await page.locator("#pair-search").getAttribute("data-geometry"),
            metadata.calibration_geometry || "",
          );
          if (
            ["target_below_feasible_scores", "target_above_feasible_scores", "peak_without_crossing"].includes(
              metadata.search_outcome,
            )
          )
            assert.match(
              await page.locator("#pair-search").textContent(),
              /unreachable/,
              "unreachable targets remain explicit",
            );
          if (
            ["contextual-spacing-page-v7", "contextual-spacing-page-v8", "contextual-spacing-page-v9"].includes(
              data.schema_version,
            )
          ) {
            assert.equal(
              model.calibration.calibration_geometry,
              modelName === "counterspace_source_first" ? "source" : "delivered",
            );
            assert.equal(
              model.calibration.search_policy,
              modelName === "counterspace" ? "closest_feasible" : "first_crossing",
            );
          }
          measurements[modelName].push({
            ...score,
            searchOutcome: metadata.search_outcome,
            calibrationGeometry: metadata.calibration_geometry,
            searchPolicy: metadata.search_policy,
          });
          continue;
        }
        const measurement = await page.locator("#pair-separation").evaluate((element) => ({
          target: Number(element.dataset.target),
          realized: Number(element.dataset.realized),
          residual: Number(element.dataset.residual),
        }));
        const target = model.pairTargetsPx[4][pairIndex];
        assert.equal(await page.locator("#pair-separation").isVisible(), target !== null);
        if (target !== null) {
          assert.equal(measurement.target, target);
          const offset = model.pairGeometryOffsetsPx[pairIndex];
          const step =
            font.glyphs.find((glyph) => glyph.codepoint === left).advancePx + model.pairTables[24][pairIndex];
          assert.equal(
            measurement.realized,
            step + offset,
            "measurement uses authoritative geometry and emitted placement",
          );
          if (expected !== "clearance_limited") {
            assert.ok(
              Math.abs(measurement.residual) <= 0.5 + 1e-9,
              "unconstrained full optical target is rounded within half a pixel",
            );
          }
          if (model.pairClearanceAdjustmentsPx) {
            const adjustment = model.pairClearanceAdjustmentsPx[24][pairIndex];
            assert.equal(await page.locator("#pair-clearance").getAttribute("data-limited"), String(adjustment > 0));
            assert.equal(Number(await page.locator("#pair-clearance").getAttribute("data-adjustment")), adjustment);
            assert.equal(await page.locator("#pair-area").isVisible(), true);
            if (expected === "clearance_limited")
              assert.ok(adjustment > 0, "constraint is explicit, rather than claimed target convergence");
          }
        }
        const metadata = model.pairTargetMetadata[pairIndex];
        assert.equal(
          await page.locator("#pair-calibration").getAttribute("data-provenance"),
          metadata.target_provenance || "",
        );
        assert.equal(
          await page.locator("#pair-calibration").getAttribute("data-basis"),
          metadata.calibration_basis || "",
        );
        measurements[modelName].push({ ...measurement, target });
      }
    }
    if (measurements.balanced) {
      assert.equal(
        measurements.balanced[0].target,
        measurements.balanced[1].target,
        "digit pairs share the fixed balance target",
      );
      assert.equal(measurements.balanced[0].target, font.sizePx * data.targetSeparationEm);
    }
    if (font.models.font_calibrated) {
      const digitReference = font.models.font_calibrated.calibration.classes.digits;
      assert.equal(measurements.font_calibrated[0].target, digitReference.target_px);
      assert.ok(
        measurements.font_calibrated.every((pair) => pair.target === digitReference.target_px),
        "FontForge digit pairs use the same source 00 target",
      );
    }
    let readingPair = null,
      preserved = null;
    if (font.models.filtered_walls) {
      const filteredDigitReference = font.models.filtered_walls.calibration.classes.digits;
      if (filteredDigitReference.status === "available") {
        assert.ok(
          measurements.filtered_walls.every((pair) => pair.target === filteredDigitReference.target_px),
          "filtered-wall digit pairs share a target measured with the candidate method",
        );
      }
      await page.locator("#spacing-model").selectOption("filtered_walls");
      const fullOptical = await page.locator("#optical-native").evaluate((canvas) => canvas.toDataURL());
      await setRange("kerning", 0);
      assert.equal(
        await page.locator("#optical-native").evaluate((canvas) => canvas.toDataURL()),
        fullOptical,
        "full filtered-wall optical is independent of source kerning",
      );
      await setRange("kerning", 4);
      await page.getByLabel("Inspect pair").selectOption("49,50");
      await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).check();
      const pairIndex = font.codepoints.indexOf(49) * font.codepoints.length + font.codepoints.indexOf(50);
      preserved = data.diagnosticLabels[font.models.filtered_walls.preservedPairDiagnostics[24][pairIndex]];
      assert.equal(await page.locator("#pair-outcome").getAttribute("data-diagnostic"), preserved, font.label);
      if (font.tabularDigits) {
        assert.equal(preserved, "source_tabular_digits");
        assert.equal(await page.locator("#pair-separation").isVisible(), false);
        assert.equal(
          await page.evaluate(
            () =>
              document.getElementById("metric-native").toDataURL() ===
              document.getElementById("optical-native").toDataURL(),
          ),
          true,
        );
      }
      if ([114, 101].every((cp) => font.codepoints.includes(cp))) {
        await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).uncheck();
        await page.getByLabel("Sample text").fill("re");
        assert.equal(await page.getByLabel("Inspect pair").inputValue(), "114,101");
        const lower = font.models.filtered_walls.calibration.classes.lowercase;
        assert.match(await page.locator("#calibration-targets").textContent(), /nn:/);
        if (lower.status === "available") {
          assert.equal(await page.locator("#pair-calibration").getAttribute("data-basis"), "lowercase");
          readingPair = await page.locator("#pair-separation").evaluate((element) => ({
            target: Number(element.dataset.target),
            residual: Number(element.dataset.residual),
          }));
          assert.equal(readingPair.target, lower.target_px);
          const outcome = await page.locator("#pair-outcome").getAttribute("data-diagnostic");
          if (outcome !== "clearance_limited") assert.ok(Math.abs(readingPair.residual) <= 0.5 + 1e-9);
        } else {
          assert.equal(await page.locator("#pair-outcome").getAttribute("data-diagnostic"), "calibration_unavailable");
        }
      }
    }
    numericRegressions.push({ font: font.label, measurements, preserved, readingPair });
  }
  const counterspaceChecks = [];
  for (const [fontIndex, font] of data.cases.entries()) {
    for (const modelName of Object.keys(font.models).filter((name) => name.startsWith("counterspace"))) {
      await page.getByRole("button", { name: "Reset controls", exact: true }).click();
      await page.getByLabel("Captured font").selectOption(String(fontIndex));
      await page.locator("#spacing-model").selectOption(modelName);
      const nIndex = font.codepoints.indexOf(110);
      if (nIndex < 0) continue;
      const pairIndex = nIndex * font.codepoints.length + nIndex;
      const model = font.models[modelName];
      assert.equal(
        (await page.locator("#model-target").textContent()).includes("Calibration fit did not converge"),
        model.calibration.fit_status === "upstream_optimizer_did_not_converge",
        "failed fitting is visible beside the model selector",
      );
      await page.getByLabel("Sample text").fill("nn");
      const full = await page.locator("#optical-native").evaluate((canvas) => canvas.toDataURL());
      const supported = model.pairTargetScores[24][pairIndex] !== null;
      await setRange("kerning", 0);
      if (supported)
        assert.equal(
          await page.locator("#optical-native").evaluate((canvas) => canvas.toDataURL()),
          full,
          "full CounterSpace endpoint is independent of source kerning",
        );
      await setRange("kerning", 4);
      for (const preserve of [false, true]) {
        await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).setChecked(preserve);
        for (let strength = 0; strength < 5; strength++) {
          await setRange("optical", strength);
          const prefix = preserve ? "preservedPair" : "pair";
          const expected = model[`${prefix}RealizedScores`][20 + strength][pairIndex];
          const actual = await page.locator("#pair-score").getAttribute("data-realized");
          assert.equal(
            actual === null ? null : Number(actual),
            expected,
            "CounterSpace scores come from the selected completed Python table",
          );
          if (strength === 0)
            assert.equal(
              await page.evaluate(
                () =>
                  document.getElementById("metric-native").toDataURL() ===
                  document.getElementById("optical-native").toDataURL(),
              ),
              true,
            );
        }
      }
      if (!font.monospace && supported) {
        await page.getByLabel("Letter spacing (px)").fill("1");
        assert.equal(
          await page.locator("#pair-score").getAttribute("data-realized"),
          null,
          "tracking does not invent an affine CounterSpace score",
        );
        assert.equal(await page.locator("#pair-score").getAttribute("data-tracked"), "true");
      }
      counterspaceChecks.push({
        font: font.label,
        model: modelName,
        supported,
        calibrationStatus: model.calibration.fit_status || model.calibration.status,
      });
    }
  }
  await page.getByRole("button", { name: "Reset controls", exact: true }).click();
  const huChecks = [];
  for (const [fontIndex, font] of data.cases.entries()) {
    if (!font.models.hu_hersch) continue;
    await page.getByLabel("Captured font").selectOption(String(fontIndex));
    await page.locator("#spacing-model").selectOption("hu_hersch");
    await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).uncheck();
    await setRange("kerning", 4);
    await setRange("optical", 4);
    await page.getByLabel("Letter spacing (px)").fill("0");
    await page.getByLabel("Word spacing (px)").fill("0");
    assert.match(await page.locator("#model-target").textContent(), /Hu\/Hersch.*delivered bitmap/);
    const parameters = font.models.hu_hersch.calibration;
    if (parameters.fit?.status === "published_parameters") {
      assert.match(
        await page.locator("#model-target").textContent(),
        /published depth coefficients: 0\.21 \/ 0\.25 \(US5768490A\); no parameter fitting/,
      );
      assert.doesNotMatch(await page.locator("#model-target").textContent(), /boundary|underidentified|provisional/);
      assert.match(
        await page.locator("#calibration-summary").textContent(),
        /published in US5768490A; no optimizer or parameter fit/,
      );
      assert.match(
        await page.locator("#calibration-targets").textContent(),
        /Published depth coefficients: aperture-relative 0\.21 · character-height 0\.25/,
      );
    }
    const candidates = [
      "ff",
      "cc",
      "zz",
      "nn",
      "oo",
      "no",
      "on",
      "bd",
      "ct",
      "ab",
      "du",
      "jo",
      "yd",
      "le",
      "pi",
      "ip",
      "te",
      "tp",
      "OE",
      "OR",
      "oe",
      "kh",
      "rn",
      "xn",
      "co",
      "01",
      "12",
      "23",
    ];
    const pairs = candidates.filter((pair) =>
      Array.from(pair).every((c) => font.codepoints.includes(c.codePointAt(0))),
    );
    if (!pairs.length) continue;
    await page.getByLabel("Sample text").fill(pairs.join(" "));
    for (const pair of pairs) {
      const [left, right] = Array.from(pair).map((c) => c.codePointAt(0));
      await page.getByLabel("Inspect pair").selectOption(`${left},${right}`);
      const pairIndex = font.codepoints.indexOf(left) * font.codepoints.length + font.codepoints.indexOf(right);
      const bundle = font.models.hu_hersch,
        metadata = bundle.pairTargetMetadata[pairIndex];
      const step = font.glyphs.find((g) => g.codepoint === left).advancePx + bundle.pairTables[24][pairIndex];
      const alternativeSteps = [];
      for (const [id, delta] of [
        ["tighter", -1],
        ["selected", 0],
        ["looser", 1],
      ]) {
        const label = page.locator(`#pair-${id}-label`);
        assert.equal(
          Number(await label.getAttribute("data-step")),
          step + delta,
          "comparison changes only second origin",
        );
        assert.equal(
          await label.getAttribute("data-feasible"),
          metadata.clearance_min_step_px == null ? "" : String(step + delta >= metadata.clearance_min_step_px),
        );
        assert.equal(await page.locator(`#pair-${id}`).isVisible(), true);
        const pixelsMatch = await page.evaluate(
          ({ id, font, left, right, step }) => {
            const glyphs = new Map(font.glyphs.map((glyph) => [glyph.codepoint, glyph]));
            const positions = {
              lines: [
                {
                  width_px: step + glyphs.get(right).advancePx,
                  placements: [
                    { codepoint: left, x_px: 0, advance_px: glyphs.get(left).advancePx },
                    { codepoint: right, x_px: step, advance_px: glyphs.get(right).advancePx },
                  ],
                },
              ],
            };
            const canvas = document.createElement("canvas");
            globalThis.ContextualSpacing.paint(canvas, font, positions, 1);
            return canvas.toDataURL() === document.getElementById(`pair-${id}`).toDataURL();
          },
          {
            id,
            font: {
              glyphs: font.glyphs.filter((g) => g.codepoint === left || g.codepoint === right),
              sizePx: font.sizePx,
              metricsAscent: font.metricsAscent,
              metricsDescent: font.metricsDescent,
              metricsLineGap: font.metricsLineGap,
            },
            left,
            right,
            step: step + delta,
          },
        );
        assert.equal(pixelsMatch, true, "native alternative paints the retained cells at the declared origin");
        alternativeSteps.push(step + delta);
      }
      const diagnostic = data.diagnosticLabels[bundle.pairDiagnostics[24][pairIndex]];
      const target = bundle.pairTargetsPx[4][pairIndex];
      if (target !== null) {
        const offset = bundle.pairGeometryOffsetsPx[pairIndex],
          realizedArea = (step + offset) * metadata.window_height_px;
        assert.equal(Number(await page.locator("#pair-area").getAttribute("data-target")), metadata.target_area_px2);
        assert.equal(Number(await page.locator("#pair-area").getAttribute("data-realized")), realizedArea);
        assert.equal(
          Number(await page.locator("#pair-area").getAttribute("data-residual")),
          realizedArea - metadata.target_area_px2,
        );
        assert.equal(await page.locator("#pair-hu-details").isVisible(), Boolean(metadata.hu_hersch));
        assert.equal(await page.locator("#pair-hu-policy").textContent(), JSON.stringify(metadata.hu_hersch));
      }
      huChecks.push({
        font: font.label,
        pair,
        diagnostic,
        target,
        reference: metadata.reference_pair,
        alternativeSteps,
      });
    }
    for (const preserve of [false, true]) {
      await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).setChecked(preserve);
      await setRange("optical", 0);
      assert.equal(
        await page.evaluate(
          () =>
            document.getElementById("metric-native").toDataURL() ===
            document.getElementById("optical-native").toDataURL(),
        ),
        true,
        "Hu optical zero is bitmap identity under either tabular policy",
      );
      await setRange("optical", 4);
    }
    await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).uncheck();
  }
  const huSourceChecks = [];
  for (const [fontIndex, font] of data.cases.entries()) {
    const model = font.models.hu_source_relative;
    if (!model || font.monospace) continue;
    await page.getByLabel("Captured font").selectOption(String(fontIndex));
    await page.locator("#spacing-model").selectOption("hu_source_relative");
    await page.getByLabel("Letter spacing (px)").fill("0");
    await page.getByLabel("Word spacing (px)").fill("0");
    assert.match(await page.locator("#kerning-help").textContent(), /source-relative optical target/);
    const pairs = [
      "ly",
      "yn",
      "nx",
      "tu",
      "uf",
      "ft",
      "oe",
      "kh",
      "rn",
      "xn",
      "co",
      "AV",
      "yp",
      "pe",
      "ty",
      "ff",
      "cc",
      "zz",
    ].filter((pair) => Array.from(pair).every((c) => font.codepoints.includes(c.codePointAt(0))));
    await page.getByLabel("Sample text").fill(pairs.join(" "));
    for (const pair of pairs) {
      const [left, right] = Array.from(pair).map((c) => c.codePointAt(0));
      const index = font.codepoints.indexOf(left) * font.codepoints.length + font.codepoints.indexOf(right);
      await page.getByLabel("Inspect pair").selectOption(`${left},${right}`);
      for (const preserve of [false, true]) {
        await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).setChecked(preserve);
        const prefix = preserve ? "preservedPair" : "pair";
        for (let k = 0; k < 5; k++) {
          await setRange("kerning", k);
          const baseline = model[prefix + "TargetMetadata"][index],
            overlay = model[prefix + "TargetMetadataByKerning"][k][index];
          const metadata = {
            ...baseline,
            ...overlay,
            hu_hersch: overlay.hu_hersch === null ? null : { ...baseline.hu_hersch, ...overlay.hu_hersch },
          };
          for (const o of [0, 2, 4]) {
            await setRange("optical", o);
            const active = o !== 0 && metadata.source_target_px != null;
            assert.equal(await page.locator("#pair-source-target").isVisible(), active);
            if (!active) continue;
            assert.equal(
              Number(await page.locator("#pair-source-target").getAttribute("data-target")),
              metadata.source_target_px,
            );
            assert.equal(
              Number(await page.locator("#pair-source-target").getAttribute("data-source-step")),
              metadata.source_step_px,
            );
            assert.equal(
              Number(await page.locator("#pair-source-target").getAttribute("data-source-offset")),
              metadata.source_hu_offset_px,
            );
            assert.equal(
              Number(await page.locator("#pair-source-target").getAttribute("data-delivered-offset")),
              metadata.delivered_hu_offset_px,
            );
            assert.equal(
              Number(await page.locator("#pair-area").getAttribute("data-target")),
              metadata.target_area_px2,
            );
            const step =
              font.glyphs.find((g) => g.codepoint === left).advancePx + model[prefix + "Tables"][k * 5 + o][index];
            assert.equal(
              Number(await page.locator("#pair-separation").getAttribute("data-realized")),
              step + model.pairGeometryOffsetsPx[index],
            );
            assert.equal(await page.locator("#pair-hu-policy").textContent(), JSON.stringify(metadata.hu_hersch));
            assert.equal(
              Number(await page.locator("#pair-clearance").getAttribute("data-adjustment")),
              model[prefix + "ClearanceAdjustmentsPx"][k * 5 + o][index],
            );
          }
          huSourceChecks.push({
            font: font.label,
            pair,
            sourceKerning: data.strengths[k],
            preserveTabularSpacing: preserve,
            sourceTargetPx: metadata.source_target_px,
            sourceStepPx: metadata.source_step_px,
          });
        }
      }
    }
    await setRange("kerning", 4);
    await setRange("optical", 4);
    await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).uncheck();
  }
  const readingSampleFonts = [];
  const accentRegressions = [];
  const canvasInk = (canvas) => {
    const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0;
    for (let index = 0; index < pixels.length; index += 4) if (pixels[index] === 0) ink++;
    return ink;
  };
  const presetChecks = [];
  const presets = data.presets || [];
  assert.equal(await page.getByLabel("Text preset").locator("option").count(), presets.length + 2);
  assert.equal(
    await page.getByLabel("Sample text").getAttribute("maxlength"),
    null,
    "preset text is never truncated at an input character limit",
  );
  for (const [index, font] of data.cases.entries()) {
    await page.getByLabel("Captured font").selectOption(String(index));
    for (const preset of presets) {
      const missing = [
        ...new Set(
          Array.from(preset.text).filter(
            (character) => character !== "\n" && !font.codepoints.includes(character.codePointAt(0)),
          ),
        ),
      ];
      assert.deepEqual(missing, [], `${font.label} captures the complete ${preset.label} preset`);
      await page.getByLabel("Text preset").selectOption(preset.id);
      assert.equal(
        await page.getByLabel("Sample text").inputValue(),
        preset.text,
        `${preset.label} retains every character and line break`,
      );
      for (const modelName of Object.keys(font.models)) {
        await page.locator("#spacing-model").selectOption(modelName);
        assert.equal(
          await page.getByRole("alert").isVisible(),
          false,
          `${font.label}, ${preset.label}, ${modelName} has no render error`,
        );
        assert.equal(await page.locator(".comparisons").isVisible(), true);
        for (const placement of ["metric", "optical"])
          for (const size of ["native", "enlarged"]) {
            assert.ok(
              (await page.locator(`#${placement}-${size}`).evaluate(canvasInk)) > 0,
              `${font.label}, ${preset.label}, ${modelName}, ${placement} ${size} contains ink`,
            );
          }
        presetChecks.push({
          font: font.label,
          preset: preset.id,
          model: modelName,
          characters: Array.from(preset.text).length,
        });
      }
    }
  }
  await page.getByLabel("Sample text").fill("custom");
  assert.equal(await page.getByLabel("Text preset").inputValue(), "custom", "manual editing marks custom text");
  await page.getByRole("button", { name: "Reset text", exact: true }).click();
  assert.equal(
    await page.getByLabel("Text preset").inputValue(),
    presets.find((preset) => preset.text === data.cases.at(-1).defaultText)?.id || "default",
  );
  assert.equal(
    await page.getByLabel("Sample text").inputValue(),
    data.cases.at(-1).defaultText,
    "reset restores the current font's default text",
  );
  await page.getByRole("button", { name: "Reset controls", exact: true }).click();
  for (const [index, font] of data.cases.entries()) {
    await page.getByLabel("Captured font").selectOption(String(index));
    if (readingSampleCodepoints.every((cp) => font.codepoints.includes(cp))) {
      await page.getByLabel("Sample text").fill(readingSample);
      assert.equal(
        await page.getByRole("alert").isVisible(),
        false,
        `${font.label} reading sample has no unsupported characters`,
      );
      assert.equal(await page.locator(".comparisons").isVisible(), true, `${font.label} reading sample is visible`);
      for (const placement of ["metric", "optical"]) {
        const measurement = await page.locator(`#${placement}-measure`).textContent();
        assert.ok(Number.parseInt(measurement, 10) > 1, `${font.label} ${placement} reading sample wraps`);
        for (const size of ["native", "enlarged"]) {
          assert.ok(
            (await page.locator(`#${placement}-${size}`).evaluate(canvasInk)) > 0,
            `${font.label} ${placement} ${size} reading sample contains ink`,
          );
        }
      }
      readingSampleFonts.push(font.label);
    }
    // Old diagnostic exports may predate these captures. New reading exports
    // report every participating family so their full coverage is reviewable.
    for (const character of ["ä", "ê"]) {
      if (!font.codepoints.includes(character.codePointAt(0))) continue;
      await page.getByLabel("Sample text").fill(character);
      assert.equal(await page.getByRole("alert").isVisible(), false);
      assert.equal(await page.locator(".comparisons").isVisible(), true);
      for (const placement of ["metric", "optical"]) {
        assert.ok(
          (await page.locator(`#${placement}-native`).evaluate(canvasInk)) > 0,
          `${font.label} renders captured ${character}`,
        );
      }
      accentRegressions.push({ font: font.label, character });
    }
  }
  await page.getByLabel("Captured font").selectOption("0");
  await page.getByRole("button", { name: "Reset text", exact: true }).click();
  await setRange("optical", 0);
  assert.equal(await page.locator("#optical-value").textContent(), "0%");
  assert.equal(await page.locator("#pair-outcome").getAttribute("data-diagnostic"), "optical_disabled");
  assert.deepEqual(
    await page.evaluate(() =>
      ["native", "enlarged"]
        .map((suffix) => [
          document.getElementById(`metric-${suffix}`).toDataURL(),
          document.getElementById(`optical-${suffix}`).toDataURL(),
        ])
        .map(([metric, optical]) => metric === optical),
    ),
    [true, true],
    "disabled optical is pixel identity",
  );
  await page.getByLabel("Letter spacing (px)").fill("2");
  await page.getByLabel("Word spacing (px)").fill("3");
  await setRange("kerning", 0);
  assert.equal(await page.locator("#kerning").getAttribute("aria-valuetext"), "0%");
  for (let index = 0; index < data.cases.length; index++) {
    await page.getByLabel("Captured font").selectOption(String(index));
    await page.getByRole("status").filter({ hasText: "Complete" }).waitFor();
  }
  await page.getByLabel("Sample text").fill("\u{1F642}");
  assert.equal(await page.getByRole("alert").isVisible(), true);
  assert.equal(
    await page.locator(".comparisons").isVisible(),
    false,
    "unsupported text never leaves a stale comparison visible",
  );
  await page.getByRole("button", { name: "Reset text", exact: true }).click();
  await page.getByRole("button", { name: "Reset controls", exact: true }).click();
  await page.getByLabel("Captured font").selectOption("0");
  await page.getByRole("status").filter({ hasText: "Complete" }).waitFor();
  assert.equal(await page.getByLabel("Letter spacing (px)").inputValue(), "0");
  assert.equal(await page.getByLabel("Word spacing (px)").inputValue(), "0");
  assert.equal(await page.getByLabel("Wrap width (px)").inputValue(), "280");
  assert.equal(await page.getByRole("checkbox", { name: "Preserve tabular spacing" }).isChecked(), false);
  assert.equal(await page.locator("#spacing-model").inputValue(), data.defaultSpacingModel);
  const ink = await page.locator("#optical-native").evaluate((canvas) => {
    const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    return Array.from(pixels).filter((value, index) => index % 4 === 0 && value === 0).length;
  });
  assert.ok(ink > 0, "delivered bitmap ink is rendered");
  await page.screenshot({ path: resolve(directory, "desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
    false,
    "no horizontal page overflow on mobile",
  );
  await page.screenshot({ path: resolve(directory, "mobile.png"), fullPage: true });
  assert.deepEqual(errors, []);
  const report = {
    status: "passed",
    pythonLayoutFixtures: parity,
    cases: data.cases.length,
    numericRegressions,
    grayscaleChecks,
    sourceMonoChecks,
    contactChecks,
    readingSampleCases: readingSampleFonts.length,
    readingSampleFonts,
    readingSampleCharacters: Array.from(readingSample).length,
    readingSampleCodepoints,
    accentRegressions,
    presets: presets.length,
    presetRenderChecks: presetChecks.length,
    presetChecks,
    models: Object.keys(data.cases[0].models),
    counterspaceChecks,
    huChecks,
    huSourceChecks,
    fixedDiagnosticTargetEm: data.targetSeparationEm,
    opticalDisabledPixelIdentity: true,
    unsupportedTextClearsComparison: true,
    offline: true,
    nativeInkPixels: ink,
    mobileOverflow: false,
    browserErrors: errors,
  };
  await writeFile(resolve(directory, "browser-verification.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
