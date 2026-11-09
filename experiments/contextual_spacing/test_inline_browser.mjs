import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve, dirname } from "node:path";
import { pathToFileURL } from "node:url";
const require = createRequire(resolve("apps/web/package.json"));
const { chromium } = require("playwright-core");
const presets = JSON.parse(await readFile("experiments/contextual_spacing/presets.json", "utf8"));
const manifest = JSON.parse(await readFile(resolve(dirname(process.argv[2]), "manifest.json"), "utf8"));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 728, height: 1000 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(pathToFileURL(resolve(process.argv[2])).href);
  await page.getByRole("status").filter({ hasText: "Complete" }).waitFor();
  const browserTypedSha256 = await page.evaluate(async () => {
    const typed = (value) => {
      if (value === null) return ["null"];
      if (typeof value === "boolean") return ["bool", value];
      if (typeof value === "number") {
        const bytes = new Uint8Array(8);
        new DataView(bytes.buffer).setFloat64(0, value, true);
        return ["number", Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")];
      }
      if (typeof value === "string") return ["string", value];
      if (Array.isArray(value)) return ["array", value.map(typed)];
      return [
        "object",
        Object.keys(value)
          .sort()
          .map((key) => [key, typed(value[key])]),
      ];
    };
    const bytes = new TextEncoder().encode(JSON.stringify(typed(globalThis.__inlineSpacingData)));
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  });
  assert.equal(
    browserTypedSha256,
    manifest.projectedTypedSha256,
    "Every restored value, including exact floating-point bits, matches the Python projection",
  );
  assert.equal(
    await page.getByLabel("Text preset").locator("option").count(),
    presets.length + 2,
    "Inline comparison must retain all seven presets",
  );
  let checks = 0;
  const modelNames = await page
    .locator("#spacing-model")
    .locator("option")
    .evaluateAll((items) => items.map((item) => item.value));
  for (const preset of presets) {
    await page.getByLabel("Text preset").selectOption(preset.id);
    assert.equal(await page.getByLabel("Sample text").inputValue(), preset.text);
    for (const model of modelNames) {
      await page.locator("#spacing-model").selectOption(model);
      assert.equal(await page.getByRole("alert").isVisible(), false);
      for (const name of ["metric", "optical", "source-mono", "grayscale"]) {
        const ink = await page.locator(`#${name}-native`).evaluate((canvas) => {
          const rgba = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
          return rgba.some((value, index) => index % 4 === 0 && value < 255);
        });
        assert.equal(ink, true, `${preset.label} / ${model} / ${name}`);
      }
      checks++;
    }
  }
  assert.deepEqual(errors, []);
  const report = {
    status: "passed",
    presets: presets.length,
    models: modelNames,
    renderChecks: checks,
    browserTypedSha256,
    browserErrors: errors,
  };
  if (process.argv[3]) await writeFile(process.argv[3], JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
}
