// Verify each visible column uses its fixed, completed Hu model table.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { pathToFileURL } from "node:url";
const require = createRequire(resolve("apps/web/package.json"));
const { chromium } = require("playwright-core");
const file = resolve(process.argv[2]);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 1000 }, offline: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(pathToFileURL(file).href);
  await page.getByRole("status").filter({ hasText: "Complete" }).waitFor();
  await page.evaluate(() => {
    globalThis.__twoModeData =
      globalThis.__inlineSpacingData || JSON.parse(document.getElementById("spacing-data").textContent);
  });
  const models = await page.evaluate(() => globalThis.__twoModeData.comparisonModels);
  assert.equal(models.length, 2);
  const fonts = await page.getByLabel("Captured font").locator("option").count();
  assert.equal(
    await page.locator("#spacing-model").inputValue(),
    await page.evaluate(() => globalThis.__twoModeData.defaultSpacingModel),
  );
  let parity = 0;
  if (!(await page.evaluate(() => Boolean(globalThis.__inlineSpacingData)))) {
    const data = JSON.parse(await readFile(resolve(dirname(file), "page-data.json"), "utf8"));
    for (const font of data.cases)
      for (let start = 0; start < font.verification.length; start += 50) {
        parity += await page.evaluate(
          ({ id, fixtures }) => {
            const font = globalThis.__twoModeData.cases.find((f) => f.id === id);
            const canonical = (v) =>
              JSON.stringify(v, (_k, e) =>
                e && !Array.isArray(e) && typeof e === "object"
                  ? Object.fromEntries(Object.entries(e).sort(([a], [b]) => a.localeCompare(b)))
                  : e,
              );
            for (const f of fixtures) {
              const actual = ContextualSpacing.layout(
                font,
                f.text,
                f.kIndex,
                f.oIndex,
                f.letterSpacing,
                f.wordSpacing,
                f.width,
                f.preserveTabularSpacing,
                f.spacingModel,
              );
              if (canonical(actual) !== canonical(f.expected))
                throw new Error(
                  `Python/browser mismatch: ${font.label}, ${f.spacingModel}, k=${f.kIndex}, o=${f.oIndex}`,
                );
            }
            return fixtures.length;
          },
          { id: font.id, fixtures: font.verification.slice(start, start + 50) },
        );
      }
  }
  let checks = 0;
  const verify = async () => {
    await page.locator("#browser-native[data-state=ready]").waitFor();
    return page.evaluate(() => {
      const d = globalThis.__twoModeData,
        f = d.cases[Number(document.getElementById("family").value)];
      const val = (id) => Number(document.getElementById(id).value);
      const text = document.getElementById("sample").value,
        preserve = document.getElementById("preserve-tabular").checked;
      for (const [id, model] of [
        ["metric", d.comparisonModels[0]],
        ["optical", d.comparisonModels[1]],
      ]) {
        const layout = ContextualSpacing.layout(
          f,
          text,
          val("kerning"),
          val("optical"),
          val("letter"),
          val("word"),
          val("wrap"),
          preserve,
          model,
        );
        const canvas = document.createElement("canvas");
        ContextualSpacing.paint(canvas, f, layout, 1);
        if (canvas.toDataURL() !== document.getElementById(id + "-native").toDataURL())
          throw new Error(`Wrong column model: ${id}, ${model}`);
      }
      return 2;
    });
  };
  const fitted = models.includes("hu_fitted_density_conserved_touch");
  const touching = models.includes("hu_density_conserved_touch");
  const conservation = touching || models.includes("hu_density_conserved");
  const density = models.includes("hu_source_calibrated");
  const headings = {
    hu_source_relative: "Source-relative",
    hu_hersch: density ? "Bitmap reference" : "Shared target",
    hu_source_calibrated: conservation ? "Previous shared target" : "Source reference",
    hu_density_conserved: touching ? "Strict clearance" : "Latest candidate",
    hu_density_conserved_touch: fitted ? "Bitmap walls" : "Latest candidate",
    hu_fitted_density_conserved_touch: "Latest candidate",
  };
  assert.equal(await page.locator("[data-placement=metric] h2").textContent(), headings[models[0]]);
  assert.equal(await page.locator("[data-placement=optical] h2").textContent(), headings[models[1]]);
  if (fitted) {
    assert.deepEqual(models, ["hu_density_conserved_touch", "hu_fitted_density_conserved_touch"]);
    assert.equal(await page.getByLabel("Inspect model").inputValue(), "hu_fitted_density_conserved_touch");
    assert.match(await page.locator("[data-placement=optical]").textContent(), /Fitted-outline walls/);
    assert.match(await page.locator("[data-placement=optical]").textContent(), /original captured bitmaps/);
    assert.match(
      await page.locator("#calibration-summary").textContent(),
      /fitted outlines; displayed ink remains the original captured bitmap cells/,
    );
  } else if (touching) {
    assert.deepEqual(models, ["hu_density_conserved", "hu_density_conserved_touch"]);
    assert.equal(await page.getByLabel("Inspect model").inputValue(), "hu_density_conserved_touch");
    assert.match(await page.locator("[data-placement=optical]").textContent(), /Edge and corner contacts are allowed/);
    assert.match(await page.locator("[data-placement=optical]").textContent(), /occupied-cell overlap is forbidden/);
  } else if (conservation) {
    assert.equal(models[1], "hu_density_conserved");
    assert.match(
      await page.locator("[data-placement=optical]").textContent(),
      /fixed source-alphabet mean|Fixed source-alphabet mean/,
    );
    assert.match(await page.locator("[data-placement=optical]").textContent(), /before rounding and clearance/);
    assert.match(await page.locator("#calibration-summary").textContent(), /unrounded continuous mean origin step/);
    assert.match(await page.locator("#model-provenance").textContent(), /Current text never changes these domains/);
  }
  // Analytic one-cell cases independently establish diagnostic classification.
  const policyCases = touching
    ? await page.evaluate(() => {
        const a = { left: 0, top: 0, width: 1, height: 1, pixels: [1] };
        const cases = [
          ["overlap", a, 0, "forbidden_overlap", "forbidden_overlap"],
          ["edge", a, 1, "forbidden_contact", "allowed_contact"],
          ["corner", { ...a, top: 1 }, 1, "forbidden_contact", "allowed_contact"],
          ["separated", a, 2, "separated", "separated"],
        ];
        return cases.map(([name, b, step, strict, noOverlap]) => {
          const counts = ContextualSpacing.contactPixels(a, b, step);
          return {
            name,
            strict: ContextualSpacing.contactDisposition(counts, "strict"),
            noOverlap: ContextualSpacing.contactDisposition(counts, "no_overlap"),
            expectedStrict: strict,
            expectedNoOverlap: noOverlap,
          };
        });
      })
    : [];
  for (const c of policyCases) {
    assert.equal(c.strict, c.expectedStrict);
    assert.equal(c.noOverlap, c.expectedNoOverlap);
  }
  const touchInspectorChecks = [];
  const presetCount = await page.evaluate(() => globalThis.__twoModeData.presets.length);
  for (let i = 0; i < fonts; i++) {
    await page.getByLabel("Captured font").selectOption(String(i));
    await page.getByRole("button", { name: "Reset text" }).click();
    for (const [k, o] of [
      [4, 4],
      [0, 4],
      [2, 3],
      [4, 2],
      [4, 0],
    ]) {
      await page.locator("#kerning").fill(String(k));
      await page.locator("#optical").fill(String(o));
      checks += await verify();
      assert.equal(await page.getByRole("alert").isVisible(), false);
      if (o === 0)
        assert.equal(
          await page.locator("#metric-native").evaluate((c) => c.toDataURL()),
          await page.locator("#optical-native").evaluate((c) => c.toDataURL()),
        );
    }
    await page.locator("#optical").fill("4");
    const ids = await page.evaluate(() => globalThis.__twoModeData.presets.map((p) => p.id));
    for (const id of ids) {
      await page.getByLabel("Text preset").selectOption(id);
      checks += await verify();
    }
    if (touching) {
      const pairs = await page.evaluate(() => {
        const f = globalThis.__twoModeData.cases[Number(document.getElementById("family").value)];
        return ["al", "ri", "ig", "en", "os", "se", "01"].filter((p) =>
          Array.from(p).every((c) => f.codepoints.includes(c.codePointAt(0))),
        );
      });
      await page.getByLabel("Sample text").fill(pairs.join(" "));
      for (const model of models) {
        await page.getByLabel("Inspect model").selectOption(model);
        for (const pair of pairs) {
          await page.getByLabel("Inspect pair").selectOption(
            Array.from(pair)
              .map((c) => c.codePointAt(0))
              .join(","),
          );
          const results = await page.evaluate(
            ({ pair, model }) => {
              const f = globalThis.__twoModeData.cases[Number(document.getElementById("family").value)],
                cps = Array.from(pair).map((c) => c.codePointAt(0));
              const [a, b] = cps.map((cp) => f.glyphs.find((g) => g.codepoint === cp).bitmap);
              const index = f.codepoints.indexOf(cps[0]) * f.codepoints.length + f.codepoints.indexOf(cps[1]);
              const metadata = f.models[model].pairTargetMetadata[index];
              const policy = metadata.clearance_policy;
              const emittedStep = Number(document.getElementById("pair-selected-label").dataset.step);
              const offset = f.models[model].pairGeometryOffsetsPx[index];
              const measured = document.getElementById("pair-separation"),
                area = document.getElementById("pair-area");
              if (!measured.hidden && offset != null) {
                const expected = emittedStep + offset;
                if (Number(measured.dataset.realized) !== expected)
                  throw new Error("Inspector uses wrong model geometry offset");
                if (!area.hidden && Number(area.dataset.realized) !== expected * metadata.window_height_px)
                  throw new Error("Inspector area uses wrong model geometry offset");
                if (model === "hu_fitted_density_conserved_touch" && measured.dataset.geometry !== "fitted_outline")
                  throw new Error("Fitted measurement mislabeled as bitmap geometry");
              }
              if (
                model === "hu_fitted_density_conserved_touch" &&
                (policy !== "no_overlap" || metadata.candidate_geometry !== "fitted_outline")
              )
                throw new Error("Fitted model measurement/clearance provenance missing");
              if (
                model === "hu_density_conserved_touch" &&
                (policy !== "no_overlap" || (metadata.candidate_geometry && metadata.candidate_geometry !== "bitmap"))
              )
                throw new Error("Bitmap control measurement/clearance provenance incorrect");
              const cells = (bitmap, origin) =>
                bitmap.pixels.flatMap((ink, i) =>
                  ink ? [[origin + bitmap.left + (i % bitmap.width), bitmap.top + Math.floor(i / bitmap.width)]] : [],
                );
              return ["tighter", "selected", "looser"].map((id) => {
                const label = document.getElementById(`pair-${id}-label`),
                  counter = document.getElementById(`pair-${id}-contact-count`),
                  step = Number(label.dataset.step);
                const counts = { overlaps: 0, faces: 0, corners: 0 };
                for (const [ax, ay] of cells(a, 0))
                  for (const [bx, by] of cells(b, step)) {
                    const dx = Math.abs(ax - bx),
                      dy = Math.abs(ay - by);
                    if (dx === 0 && dy === 0) counts.overlaps++;
                    else if (dx + dy === 1) counts.faces++;
                    else if (dx === 1 && dy === 1) counts.corners++;
                  }
                const disposition = counts.overlaps
                  ? "forbidden_overlap"
                  : counts.faces || counts.corners
                    ? policy === "no_overlap"
                      ? "allowed_contact"
                      : "forbidden_contact"
                    : "separated";
                return {
                  id,
                  step,
                  policy,
                  counts,
                  disposition,
                  actualDisposition: label.dataset.disposition,
                  actualPolicy: label.dataset.policy,
                  actualCounts: {
                    overlaps: Number(counter.dataset.overlaps),
                    faces: Number(counter.dataset.faces),
                    corners: Number(counter.dataset.corners),
                  },
                  expectedFeasible:
                    metadata.clearance_min_step_px == null ? "" : String(step >= metadata.clearance_min_step_px),
                  actualFeasible: label.dataset.feasible,
                };
              });
            },
            { pair, model },
          );
          for (const r of results) {
            assert.equal(r.actualDisposition, r.disposition);
            assert.equal(r.actualPolicy, r.policy);
            assert.deepEqual(r.actualCounts, r.counts);
            assert.equal(r.actualFeasible, r.expectedFeasible);
            if (r.id === "selected" && r.policy === "no_overlap" && r.actualFeasible === "true")
              assert.equal(r.counts.overlaps, 0);
          }
          touchInspectorChecks.push({ font: i, model, pair, alternatives: results });
        }
      }
    }
    const before = await page.evaluate(() =>
      ["metric-native", "optical-native"].map((id) => document.getElementById(id).toDataURL()),
    );
    await page.getByLabel("Inspect model").selectOption(models[0]);
    checks += await verify();
    assert.deepEqual(
      await page.evaluate(() =>
        ["metric-native", "optical-native"].map((id) => document.getElementById(id).toDataURL()),
      ),
      before,
      "Inspector does not change either column model",
    );
    await page.getByRole("button", { name: "Reset controls" }).click();
    assert.equal(
      await page.getByLabel("Inspect model").inputValue(),
      await page.evaluate(() => globalThis.__twoModeData.defaultSpacingModel),
    );
  }
  await page.getByLabel("Captured font").selectOption("0");
  await page.getByRole("button", { name: "Reset controls" }).click();
  await page.getByRole("button", { name: "Reset text" }).click();
  const steps = await page.evaluate(() => {
    const f = globalThis.__twoModeData.cases[0],
      r = {};
    for (const m of globalThis.__twoModeData.comparisonModels)
      r[m] = ["ip", "pe"].map(
        (t) => ContextualSpacing.layout(f, t, 4, 4, 0, 0, 280, false, m).lines[0].placements[1].x_px,
      );
    return r;
  });
  if (!density && !conservation) assert.deepEqual(steps, { hu_source_relative: [5, 10], hu_hersch: [5, 11] });
  await page.setViewportSize({ width: 390, height: 844 });
  await verify();
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
    false,
  );
  assert.deepEqual(errors, []);
  const report = {
    status: "passed",
    fonts,
    models,
    pythonBrowserParity: parity,
    columnChecks: checks,
    presets: presetCount,
    contactPolicyCases: policyCases,
    touchInspectorChecks,
    opticalZeroIdentity: true,
    ipPeSteps: steps,
    browserErrors: errors,
  };
  await writeFile(resolve(dirname(file), "two-modes-verification.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
