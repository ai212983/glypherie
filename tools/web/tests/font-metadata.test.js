import assert from "node:assert/strict";
import test from "node:test";
import { createSpecimenImporter, validateManifest } from "../lib/specimens.js";
import { fontMetadataView } from "../lib/font-metadata.js";
import { build, fixture, fontMetadata } from "./helpers.js";

test("imports extracted metadata and renders it beneath each family heading", async (t) => {
  const f = await fixture(t);
  const result = await createSpecimenImporter(f.root).load();
  assert.deepEqual(result.families[0].metadata, f.manifest.families[0].metadata);
  const html = await build(f.root, f.output);
  assert.match(html, /<h2[^>]*>Fixture font<\/h2>\s*<dl class="font-metadata"/);
  assert.match(html, /<dt>Kerning<\/dt><dd>Yes<\/dd>/);
  assert.match(html, /Weight \(wght\): 100–900 \(default 400\)/);
  assert.doesNotMatch(html, /<dt>Style/);
  assert.match(html, /Sans serif · Proportional/);
});

test("static fonts, vertical kerning and unknown classifications have distinct labels", () => {
  const metadata = fontMetadata();
  metadata.axes = [];
  metadata.kerning = { horizontal: false, vertical: false, sources: [] };
  metadata.classification = { family_class: 0, panose: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], monospaced: null };
  const view = fontMetadataView(metadata);
  assert.equal(view.axesLabel, "None · static font");
  assert.equal(view.kerningLabel, "No");
  assert.equal(view.classificationLabel, "");
  metadata.kerning = { horizontal: false, vertical: true, sources: ["GPOS vkrn"] };
  assert.equal(fontMetadataView(metadata).kerningLabel, "Vertical only");
  metadata.kerning.horizontal = true;
  metadata.kerning.sources.push("GPOS kern");
  assert.equal(fontMetadataView(metadata).kerningLabel, "Yes · horizontal and vertical");
});

test("classification uses embedded IBM/PANOSE values in their family context", () => {
  const metadata = fontMetadata();
  metadata.classification.monospaced = true;
  metadata.classification.family_class = 0x0502;
  assert.equal(fontMetadataView(metadata).classificationLabel, "Slab serif · Monospaced");
  metadata.classification.family_class = 0;
  metadata.classification.panose[1] = 6;
  assert.equal(fontMetadataView(metadata).classificationLabel, "Serif · Monospaced");
  // The second digit of handwritten PANOSE describes tools, not serifs.
  metadata.classification.panose[0] = 3;
  metadata.classification.panose[1] = 11;
  assert.equal(fontMetadataView(metadata).classificationLabel, "Handwritten · Monospaced");
  metadata.classification.panose[0] = 0;
  assert.equal(fontMetadataView(metadata).classificationLabel, "Monospaced");
});

test("older immutable manifests remain readable without claiming absent metadata", async (t) => {
  const f = await fixture(t);
  delete f.manifest.families[0].metadata;
  await f.save();
  const result = await createSpecimenImporter(f.root).load();
  assert.equal(result.state, "ready");
  assert.equal(result.families[0].metadata, null);
  const html = await build(f.root, f.output);
  assert.match(html, /<dt>Kerning<\/dt><dd>Unknown<\/dd>/);
  assert.match(html, /<dt>Axes<\/dt><dd>Unknown<\/dd>/);
  assert.doesNotMatch(html, /<dt>Classification<\/dt>/);
});

test("custom axis labels are HTML escaped and style names are not displayed", async (t) => {
  const f = await fixture(t);
  f.manifest.families[0].metadata.axes.push({ tag: "TEST", name: "<script>axis</script>", min: -1, default: 0, max: 1, hidden: true });
  f.manifest.families[0].metadata.names.style = "<img src=x onerror=alert(1)>";
  await f.save();
  const html = await build(f.root, f.output);
  assert.match(html, /&lt;script&gt;axis&lt;\/script&gt; \(TEST\)/);
  assert.doesNotMatch(html, /onerror=alert/);
  assert.doesNotMatch(html, /<script>axis|<img src=x/);
});

test("invalid extracted metadata fails manifest validation", async (t) => {
  const f = await fixture(t);
  for (const mutate of [
    (m) => { m.kerning.horizontal = "yes"; },
    (m) => { m.kerning.sources = []; },
    (m) => { m.axes[0].default = 901; },
    (m) => { m.axes.push({ ...m.axes[0] }); },
    (m) => { m.axes[0].tag = "weight"; },
    (m) => { m.names.style = {}; },
    (m) => { m.style.slope = "serif"; },
    (m) => { m.classification.panose = [2]; },
    (m) => { m.coverage.character_count = 4; },
    (m) => { m.coverage.ranges = [[0xd800, 0xd802]]; },
    (m) => { m.declared_unicode_ranges = [-1, 0, 0, 0]; },
  ]) {
    const manifest = structuredClone(f.manifest);
    mutate(manifest.families[0].metadata);
    assert.throws(() => validateManifest(manifest, f.pointer), /Invalid extracted font metadata/);
  }
});
