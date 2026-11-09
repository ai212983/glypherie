// Real-browser interaction check for the interactive feasibility page.
// Loads the offline file:// page, drives every control, and requires the
// displayed choices to match the embedded Python table. Saves a screenshot.
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
  process.argv[2] || "../../out/diagnostics/contextual-spacing/yinyangfit-interactive-v2/site",
);
const data = JSON.parse(await readFile(resolve(directory, "page-data.json"), "utf8"));

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(pathToFileURL(resolve(directory, "index.html")).href);
  await page.locator("#yy-table table").waitFor();
  assert.equal(await page.locator("[title]").count(), 0, "no native title tooltips");

  const readIdentity = () => page.locator("#yy-identity").textContent();
  const readRows = () => page.locator("#yy-table table tr").count();
  const readChosenDelta = () => page.locator("#yy-chosen1-cap").textContent();

  // Default state: tables present, identity shown.
  assert.match(await readIdentity(), /Setting [0-9a-f]{12}/);
  assert.equal(await readRows(), 6); // header + five candidates

  // Drive every dataset and all three sliders to non-default grid points.
  const datasets = await page.locator("#yy-dataset option").count();
  assert.equal(datasets, data.datasets.length);
  const checked = [];
  // Slider sequence per dataset: cohesion->0 (combo 10), scale->0 (combo 2),
  // falloff->0 (combo 0); other sliders hold their current values.
  const sequence = [
    ["#yy-cohesion", "0", 10],
    ["#yy-scale", "0", 2],
    ["#yy-falloff", "0", 0],
  ];
  for (let d = 0; d < data.datasets.length; d++) {
    await page.locator("#yy-dataset").selectOption(String(d));
    await page.locator("#yy-reset").click(); // sliders to 4/2/2, combo 74
    for (const [slider, value, comboIdx] of sequence) {
      await page.locator(slider).fill(value);
      await page.locator("#yy-table table").waitFor();
      const combo = data.combos[comboIdx];
      const ds = data.datasets[d];
      const pair = await page.locator("#yy-pair").inputValue();
      const pairName = data.pairs[Number(pair)];
      const entry = ds.pairs[pairName].table[combo.id];
      const caption = await readChosenDelta();
      assert.ok(
        caption.includes(`step ${entry.ch}`),
        `${ds.label} ${pairName} ${combo.id}: caption ${caption} vs choice ${entry.ch}`,
      );
      checked.push(`${ds.label}/${pairName}/${combo.id}=${entry.ch}`);
    }
  }

  // Reset restores defaults and the default identity.
  await page.locator("#yy-reset").click();
  assert.equal(await page.locator("#yy-cohesion").inputValue(), "4");
  assert.equal(await page.locator("#yy-scale").inputValue(), "2");
  assert.equal(await page.locator("#yy-falloff").inputValue(), "2");
  assert.equal(await readRows(), 6);

  // Word view renders native and magnified canvases with nonzero size.
  await page.locator("#yy-word").selectOption("1");
  const w1 = await page.locator("#yy-word1").evaluate((c) => [c.width, c.height]);
  const wN = await page.locator("#yy-wordN").evaluate((c) => [c.width, c.height]);
  assert.ok(w1[0] > 0 && w1[1] > 0 && wN[0] > w1[0], "word canvases render");

  // Captured-source baseline row renders beside the experiment word: the
  // displayed draws match the embedded baseline for the current dataset.
  const cword = await page.locator("#yy-cword-gaps").textContent();
  assert.match(cword, /Captured-source draws \[/);
  const d = data.datasets[Number(await page.locator("#yy-dataset").inputValue())];
  const word = data.words[Number(await page.locator("#yy-word").inputValue())];
  assert.ok(
    cword.includes(`[${d.captured_words[word].origins.join(", ")}]`),
    `captured caption matches embedded baseline for ${d.label} ${word}`,
  );
  const cw1 = await page.locator("#yy-cword1").evaluate((c) => [c.width, c.height]);
  const cwN = await page.locator("#yy-cwordN").evaluate((c) => [c.width, c.height]);
  assert.ok(cw1[0] > 0 && cw1[1] > 0 && cwN[0] > cw1[0], "captured word canvases render");

  await page.screenshot({ path: resolve(directory, "interaction-check.png") });
  assert.deepEqual(errors, [], `page errors: ${errors.join("; ")}`);
  console.log(JSON.stringify({ status: "passed", datasets, checks: checked.length, errors: 0 }));
} finally {
  await browser.close();
}
