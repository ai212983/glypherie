// Freeze actual delivery pixels for the scoped fast-math visual assessment.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..'), out = path.join(root, 'out/diagnostics/fast-math-optimization');
const labels = ['app', 'fast'], sha = b => crypto.createHash('sha256').update(b).digest('hex');
const original = Array.from({ length: 6 }, (_, i) => JSON.parse(fs.readFileSync(path.join(out, `delivery-${i}.json`))).rows).flat();
const matrix = original.filter(r => r.cell[0] === 'matrix' && r.cell.at(-1)).sort((a, b) => JSON.stringify(a.cell).localeCompare(JSON.stringify(b.cell)));
assert.equal(matrix.length, 144);
const packageHashes = Object.fromEntries(labels.map(label => [label, sha(fs.readFileSync(path.join(out, `pkg-nodejs-${label}/font_wasm_bg.wasm`)))]));
const identities = JSON.parse(fs.readFileSync(path.join(out, 'identities.json')));
labels.forEach(label => assert.equal(packageHashes[label], identities[label].wasm_sha));

function mask(result) {
  const bytes = result.pixels(), bits = new Uint8Array(bytes.length / 4);
  for (let i = 0; i < bits.length; i++) {
    assert.equal(bytes[i * 4 + 3], 255);
    const value = bytes[i * 4];
    assert.ok(value === 0 || value === 255);
    assert.equal(bytes[i * 4 + 1], value); assert.equal(bytes[i * 4 + 2], value);
    bits[i] = value === 0 ? 1 : 0;
  }
  return { bits, hash: sha(bytes), width: result.width(), height: result.height(), layout: result.layout() };
}
function pair(fonts, spec) {
  return labels.map(label => {
    const result = fonts[label].render(spec);
    try { return mask(result); } finally { result.free(); }
  });
}
function packet(pair) {
  const [a, b] = pair; assert.equal(a.width, b.width); assert.equal(a.height, b.height); assert.deepEqual(a.layout, b.layout);
  let left = a.width, top = a.height, right = 0, bottom = 0, changed = 0;
  for (let i = 0; i < a.bits.length; i++) {
    if (a.bits[i] !== b.bits[i]) changed++;
    if (a.bits[i] || b.bits[i]) {
      const x = i % a.width, y = Math.floor(i / a.width);
      left = Math.min(left, x); right = Math.max(right, x + 1); top = Math.min(top, y); bottom = Math.max(bottom, y + 1);
    }
  }
  if (!right) { left = top = 0; right = bottom = 1; }
  left = Math.max(0, left - 2); top = Math.max(0, top - 2);
  right = Math.min(a.width, right + 2); bottom = Math.min(a.height, bottom + 2);
  const width = right - left, height = bottom - top;
  const encoded = pair.map(value => {
    const bytes = Buffer.alloc(Math.ceil(width * height / 8));
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const i = y * width + x, bit = value.bits[(y + top) * a.width + x + left];
      if (bit) bytes[i >> 3] |= 1 << (i & 7);
    }
    // Independent replay: the cropped packet must reconstruct every input pixel.
    for (let y = 0; y < a.height; y++) for (let x = 0; x < a.width; x++) {
      let actual = 0;
      if (x >= left && x < right && y >= top && y < bottom) {
        const i = (y - top) * width + x - left; actual = bytes[i >> 3] >> (i & 7) & 1;
      }
      assert.equal(actual, value.bits[y * a.width + x]);
    }
    return bytes.toString('base64');
  });
  return { width, height, origin: [left, top], pixels: encoded, sourceHashes: pair.map(v => v.hash), changed };
}

function capture() {
  const shard = Number(process.env.COMPARE_SHARD ?? 0), shards = 6;
  const target = path.join(out, `review-capture-${shard}.json`); assert.ok(!fs.existsSync(target), 'Preserve captures.');
  const apis = Object.fromEntries(labels.map(label => [label, require(path.join(out, `pkg-nodejs-${label}/font_wasm.js`))]));
  const cache = new Map(), fontHashes = {}, cells = [];
  try {
    matrix.forEach((row, index) => {
      if (index % shards !== shard) return;
      const family = row.cell[1], bytes = fs.readFileSync(path.join(root, 'fonts', family + '.ttf'));
      fontHashes[family] = sha(bytes);
      if (!cache.has(family)) cache.set(family, Object.fromEntries(labels.map(label => [label, new apis[label].Font(bytes)])));
      const fonts = cache.get(family), full = pair(fonts, row.spec);
      const expected = row.comparisons.find(c => c.pair.join('/') === 'app/fast');
      assert.deepEqual(full.map(v => v.hash), expected.pixelHashes, 'Frozen matrix pixel identity');
      assert.deepEqual(full[0].layout, full[1].layout);
      const glyphs = [];
      for (let cp = 32; cp <= 126; cp++) {
        const character = String.fromCodePoint(cp), value = packet(pair(fonts, { ...row.spec, text: character, width: 64, height: 64 }));
        if (value.changed) glyphs.push({ character, codepoint: cp, ...value });
      }
      const texts = ['Pack my box with five dozen liquor jugs.', glyphs.map(g => g.character).join(' ')];
      const lines = texts.filter(Boolean).map(text => ({ text, ...packet(pair(fonts, { ...row.spec, text, width: 800, height: 128 })) }));
      cells.push({ id: `case-${index}`, family, size: row.spec.size_px, weight: row.spec.axes.wght,
        fitting: row.spec.pipeline.fitting, scanner: row.spec.pipeline.rasterization, spec: row.spec,
        glyphs, lines, matrixHashes: full.map(v => v.hash) });
    });
  } finally { for (const fonts of cache.values()) Object.values(fonts).forEach(font => font.free()); }
  fs.writeFileSync(target, JSON.stringify({ shard, packageHashes, fontHashes, cells }));
  console.log(JSON.stringify({ shard, cells: cells.length, changedGlyphs: cells.reduce((n, c) => n + c.glyphs.length, 0) }));
}
function assemble() {
  const target = path.join(out, 'review-v1'); assert.ok(!fs.existsSync(target), 'Preserve review packets.');
  const captures = Array.from({ length: 6 }, (_, i) => JSON.parse(fs.readFileSync(path.join(out, `review-capture-${i}.json`))));
  const cells = captures.flatMap(c => c.cells).sort((a, b) => Number(a.id.slice(5)) - Number(b.id.slice(5)));
  assert.equal(cells.length, 144); assert.equal(new Set(cells.map(c => c.id)).size, 144);
  captures.forEach(c => assert.deepEqual(c.packageHashes, packageHashes));
  const defaults = JSON.parse(fs.readFileSync(path.join(out, 'default-glyph-differences.json')));
  for (const family of Object.keys(defaults)) {
    const cell = cells.find(c => c.family === family && c.size === 16 && c.weight === 400 && c.fitting === 'font_hints_auto' && c.scanner === 'free_type_mono');
    assert.deepEqual(cell.glyphs.map(g => ({ character: g.character, changed_pixels: g.changed })), defaults[family]);
  }
  fs.mkdirSync(target);
  const manifest = { families: ['Roboto', 'SourceSans3'], sizes: [12, 14, 16, 18, 20, 24], weights: [300, 400, 700],
    cells: cells.map(({ glyphs, lines, spec, matrixHashes, ...c }) => ({ ...c, changed: glyphs.length, file: `${c.id}.json` })) };
  for (const cell of cells) fs.writeFileSync(path.join(target, cell.id + '.json'), JSON.stringify(cell));
  fs.writeFileSync(path.join(target, 'matrix.json'), JSON.stringify(manifest));
  fs.copyFileSync(path.join(__dirname, 'fast-math-review.html'), path.join(target, 'index.html'));
  const files = Object.fromEntries(fs.readdirSync(target).sort().map(name => [name, sha(fs.readFileSync(path.join(target, name)))]));
  const audit = { cells: cells.length, changedGlyphCases: cells.reduce((n, c) => n + c.glyphs.length, 0),
    defaultChangedGlyphs: 18, allOriginalMatrixHashesVerified: true, allCropsReplayExactly: true,
    allLayoutsIdentical: true, packageHashes, fontHashes: Object.assign({}, ...captures.map(c => c.fontHashes)), files };
  fs.writeFileSync(path.join(out, 'review-audit.json'), JSON.stringify(audit, null, 2));
  console.log(JSON.stringify({ cells: audit.cells, changedGlyphCases: audit.changedGlyphCases, files: Object.keys(files).length }));
}
if (process.argv[2] === 'assemble') assemble(); else capture();
