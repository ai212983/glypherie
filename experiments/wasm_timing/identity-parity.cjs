const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '../..');
const output = path.resolve(process.env.PARITY_OUTPUT_DIR ?? path.join(root, 'out/diagnostics/font-identity-optimization'));
const paths = process.env.PARITY_PACKAGES ? JSON.parse(process.env.PARITY_PACKAGES) : {
  dense: path.join(root, 'out/diagnostics/qp-objective-optimization/pkg-nodejs-before'),
  sparse: path.join(output, 'pkg-nodejs-sparse'),
  identity: path.join(output, 'pkg-nodejs-identity'),
};
const packages = Object.fromEntries(Object.entries(paths).map(([name, folder]) => [name, require(path.join(folder, 'font_wasm.js'))]));
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const identities = Object.fromEntries(Object.entries(paths).map(([name, folder]) => [name, sha(fs.readFileSync(path.join(folder, 'font_wasm_bg.wasm')))]));
const shard = Number(process.env.COMPARE_SHARD ?? 0), shards = Number(process.env.COMPARE_SHARDS ?? 1);
let index = 0, cases = 0, glyphs = 0, errors = 0;
const exportShas = [];
for (const family of ['Roboto', 'SourceSans3']) {
  const bytes = fs.readFileSync(path.join(root, 'fonts', family + '.ttf'));
  const fonts = Object.fromEntries(Object.entries(packages).map(([name, pkg]) => [name, new pkg.Font(bytes)]));
  try {
    assert.deepEqual(fonts.identity.metadata(), fonts.dense.metadata());
    for (const size_px of [12, 14, 16, 18, 20, 24]) for (const wght of [300, 400, 700])
      for (const fitting of ['font_hints_auto', 'upstream_mono']) for (const rasterization of ['free_type_mono', 'free_type_mono_terminals'])
        for (const diagonal_fitting of [false, true]) {
          if (index++ % shards !== shard) continue;
          const text = Array.from({ length: 95 }, (_, i) => String.fromCodePoint(i + 32)).join(' ');
          const spec = { text, width: 800, height: 384, size_px, axes: family === 'Roboto' ? { wght, wdth: 100 } : { wght },
            output_bits: 1, mono_raster: { dropout: 'smart', include_stubs: true, font_instructions: true },
            pipeline: { fitting, rasterization, diagonal_fitting } };
          let expected;
          for (const [name, font] of Object.entries(fonts)) {
            const result = font.render(spec);
            try {
              const actual = { pixels: sha(result.pixels()), layout: result.layout(), width: result.width(), height: result.height() };
              if (expected) assert.deepEqual(actual, expected, JSON.stringify({ family, name, spec })); else expected = actual;
            } finally { result.free(); }
          }
          cases++; glyphs += 95;
        }
    // Reuse the same warmed font through invalid requests and recovery.
    if (shard === 0) {
      for (const spec of [
        { text: '', width: 64, height: 32, axes: { XXXX: 1 } },
        { text: 'x', width: 0, height: 32 },
        { text: '', width: 64, height: 32, pipeline: { fitting: 'font_hints_auto', rasterization: 'coverage', diagonal_fitting: true } },
        { text: 'x', width: 64, height: 32, renderer: 'candidate', pipeline: { fitting: 'upstream_mono', rasterization: 'free_type_mono' } },
      ]) {
        const results = Object.values(fonts).map(font => { try { const result = font.render(spec); result.free(); return null; } catch (e) { return String(e); } });
        assert.ok(results[0]); assert.deepEqual(results, results.map(() => results[0])); errors++;
      }
      const request = { config: { characters: 'kyxzvAW sX2 M^ We walked by the river.', size_px: 16,
        axes: family === 'Roboto' ? { wght: 400, wdth: 100 } : { wght: 400 }, output_bits: 1, kerning: true,
        mono_raster: { dropout: 'smart', include_stubs: true, font_instructions: true } }, letter_spacing_px: 0 };
      for (const fitting of ['font_hints_auto', 'upstream_mono']) for (const diagonal_fitting of [false, true]) {
        const spec = { ...request, pipeline: { fitting, rasterization: 'free_type_mono_terminals', diagonal_fitting } };
        const encoded = Object.values(fonts).map(font => Buffer.from(font.export_playdate(spec)));
        encoded.slice(1).forEach(value => assert.deepEqual(value, encoded[0])); exportShas.push(sha(encoded[0]));
      }
    }
  } finally { Object.values(fonts).forEach(font => font.free()); }
}
const summary = { shard, shards, cases, glyphs, errors, exports: exportShas, identities };
fs.writeFileSync(path.join(output, `parity-${shard}.json`), JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary));
