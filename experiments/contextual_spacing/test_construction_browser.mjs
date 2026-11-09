// Integration checks for complete-text control/candidate/browser comparison.
// No font capture, optical solving or server is started by this checker.
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(resolve("apps/web/package.json"));
const { chromium } = require("playwright-core");
if (!process.argv[2]) throw new Error("usage: node test_construction_browser.mjs PAGE.html [PAGE-DATA.json]");
const path = resolve(process.argv[2]);
const evidence = JSON.parse(
  await readFile(resolve(process.argv[3] || resolve(dirname(path), "page-data.json")), "utf8"),
);
const models = ["hu_fitted_density_conserved_touch", "hu_fitted_full_density_conserved_touch"];
assert.deepEqual(evidence.comparisonModels, models);
assert.ok(!evidence.neighborReview, "construction comparison must not apply manual neighbor offsets");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 1100 }, offline: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(pathToFileURL(path).href);
  await page.getByRole("status").filter({ hasText: "Complete" }).waitFor();
  await page.locator("#browser-native[data-state=ready]").waitFor();
  assert.equal(await page.locator(".construction-comparison > .comparison").count(), 3);
  assert.equal(await page.locator("[data-placement=metric] h2").textContent(), "Current control");
  assert.equal(await page.locator("[data-placement=optical] h2").textContent(), "Construction-order candidate");
  assert.equal(await page.locator("#neighbor-review").isVisible(), false);
  assert.equal(await page.locator("#spacing-model").inputValue(), models[1]);
  await page.evaluate(() => {
    globalThis.__constructionData =
      globalThis.__inlineSpacingData || JSON.parse(document.getElementById("spacing-data").textContent);
  });
  const ids = await page.evaluate(() => globalThis.__constructionData.cases.map((font) => font.id));
  const fixtures = (evidence.wholeTextVerification || []).filter((fixture) => ids.includes(fixture.caseId));
  assert.ok(fixtures.length, "whole-text Python fixtures are required");
  let parity = 0;
  for (let start = 0; start < fixtures.length; start += 25) {
    parity += await page.evaluate(
      (batch) => {
        const canonical = (value) =>
          JSON.stringify(value, (_key, entry) =>
            entry && !Array.isArray(entry) && typeof entry === "object"
              ? Object.fromEntries(Object.entries(entry).sort(([a], [b]) => a.localeCompare(b)))
              : entry,
          );
        for (const fixture of batch) {
          const font = globalThis.__constructionData.cases.find((font) => font.id === fixture.caseId);
          const actual = ContextualSpacing.layout(
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
              `Whole-text Python parity failed: ${font.label}, ${fixture.spacingModel}, width=${fixture.width}`,
            );
        }
        return batch.length;
      },
      fixtures.slice(start, start + 25),
    );
  }
  let canvasChecks = 0,
    presetChecks = 0,
    scrollChecks = 0,
    alignmentChecks = 0;
  const cases = evidence.cases.filter((font) => ids.includes(font.id));
  for (let fontIndex = 0; fontIndex < cases.length; fontIndex++) {
    await page.getByLabel("Captured font").selectOption(String(fontIndex));
    for (const preset of evidence.presets) {
      await page.getByLabel("Text preset").selectOption(preset.id);
      await page.locator("#browser-native[data-state=ready]").waitFor();
      assert.equal(await page.getByLabel("Sample text").inputValue(), preset.text);
      canvasChecks += await page.evaluate((models) => {
        const data = globalThis.__constructionData,
          font = data.cases[Number(document.getElementById("family").value)];
        const text = document.getElementById("sample").value;
        for (const [index, name] of ["metric", "optical"].entries()) {
          const positions = ContextualSpacing.layout(font, text, 4, 4, 0, 0, 280, false, models[index]);
          const expected = document.createElement("canvas");
          ContextualSpacing.paint(expected, font, positions, 1);
          const actual = document.getElementById(name + "-native");
          if (actual.toDataURL() !== expected.toDataURL())
            throw new Error("Main comparison does not display the authoritative model and complete selected text");
          const enlarged = document.getElementById(name + "-enlarged");
          if (
            enlarged.width !== actual.width ||
            enlarged.height !== actual.height ||
            enlarged.toDataURL() !== actual.toDataURL()
          )
            throw new Error("Zoom changed source pixel data or omitted text");
        }
        if (document.getElementById("browser-native").textContent !== text)
          throw new Error("Browser reference omitted selected text");
        const style = getComputedStyle(document.getElementById("browser-native"));
        if (style.letterSpacing !== "normal" || (style.wordSpacing !== "0px" && style.wordSpacing !== "normal"))
          throw new Error("Browser reference received deliberate bitmap spacing");
        return 2;
      }, models);
      presetChecks++;
    }
    await page.getByLabel("Text preset").selectOption("lynx-lowercase");
    await page.locator("#browser-native[data-state=ready]").waitFor();
    for (const scale of ["native", "enlarged"]) {
      const frames = page.locator(".construction-comparison > .comparison ." + scale);
      const fraction = 0.37;
      await frames.first().evaluate((frame, fraction) => {
        frame.scrollTop = (frame.scrollHeight - frame.clientHeight) * fraction;
        frame.scrollLeft = 25;
      }, fraction);
      await page.waitForTimeout(80);
      const progress = await frames.evaluateAll((frames) =>
        frames.map((frame) => ({
          top: frame.scrollTop,
          extent: frame.scrollHeight - frame.clientHeight,
          left: frame.scrollLeft,
        })),
      );
      for (const frame of progress) {
        assert.ok(frame.extent > 0, "whole text remains scrollable");
        assert.ok(
          Math.abs(frame.top / frame.extent - fraction) < 0.01,
          "scroll position tracks normalized reading progress",
        );
      }
      scrollChecks++;
    }
  }
  await page.getByRole("button", { name: "Reset controls", exact: true }).click();
  assert.equal(await page.locator("#spacing-model").inputValue(), models[1]);
  await page.locator("#optical").fill("0");
  const zero = await page.locator("#metric-native").evaluate((canvas) => canvas.toDataURL());
  assert.equal(
    await page.locator("#optical-native").evaluate((canvas) => canvas.toDataURL()),
    zero,
    "optical zero retains identical metric placement",
  );
  for (const width of [390, 640, 728, 1040, 1200]) {
    await page.setViewportSize({ width, height: 1100 });
    const geometry = await page.evaluate(() =>
      [...document.querySelectorAll(".construction-comparison > .comparison")].map((card) => {
        const box = card.getBoundingClientRect(),
          native = card.querySelector(".native").getBoundingClientRect(),
          zoom = card.querySelector(".enlarged").getBoundingClientRect();
        const children = [...card.children].map((node) => node.getBoundingClientRect());
        const footer = card.lastElementChild.getBoundingClientRect();
        return {
          cardTop: box.top,
          cardBottom: box.bottom,
          nativeTop: native.top,
          zoomTop: zoom.top,
          nativeOffset: native.top - box.top,
          zoomOffset: zoom.top - box.top,
          ordered: children.every((node, i) => !i || node.top >= children[i - 1].bottom - 0.01),
          footerInside: footer.bottom <= box.bottom + 0.01,
        };
      }),
    );
    const [control, candidate, reference] = geometry;
    if (width > 540) {
      assert.ok(Math.abs(control.nativeTop - candidate.nativeTop) < 0.01, "binary native panes align");
      assert.ok(Math.abs(control.zoomTop - candidate.zoomTop) < 0.01, "binary zoom panes align");
    }
    // Stacked cards have independent title/hint wrapping, so equal internal
    // offsets would impose unrelated empty space. Check reading order instead;
    // actual pane alignment is required when the cards share a grid row.
    else {
      assert.ok(candidate.cardTop >= control.cardBottom, "stacked candidate follows the control");
      assert.ok(reference.cardTop >= candidate.cardBottom, "stacked reference follows the candidate");
    }
    if (width >= 1040) {
      assert.ok(Math.abs(control.nativeTop - reference.nativeTop) < 0.01, "browser native pane shares the row");
      assert.ok(Math.abs(control.zoomTop - reference.zoomTop) < 0.01, "browser zoom pane shares the row");
    }
    assert.ok(
      geometry.every((card) => card.ordered && card.footerInside),
      "captions, panes and ancillary notes remain ordered inside their cards",
    );
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      "responsive controls do not overflow the page",
    );
    alignmentChecks++;
  }
  assert.equal(await page.locator(".construction-comparison > .comparison").count(), 3);
  assert.deepEqual(errors, []);
  const report = {
    status: "passed",
    fonts: cases.length,
    pythonWholeTextFixtures: parity,
    presetChecks,
    canvasChecks,
    scrollChecks,
    alignmentChecks,
    browserErrors: errors,
  };
  await writeFile(resolve(dirname(path), "construction-verification.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
