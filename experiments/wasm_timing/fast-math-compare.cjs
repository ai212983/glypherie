// Exhaustive delivery comparison that records differences rather than accepting them.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), vm = require('node:vm');
const root = path.resolve(__dirname, '../..'), out = path.resolve(process.env.MATH_OUTPUT_DIR ?? path.join(root, 'out/diagnostics/fast-math-optimization'));
const shard = Number(process.env.COMPARE_SHARD ?? 0), shards = Number(process.env.COMPARE_SHARDS ?? 6);
const packagePaths = process.env.MATH_PACKAGES ? JSON.parse(process.env.MATH_PACKAGES)
  : Object.fromEntries(['app', 'strict', 'fast'].map(label => [label, path.join(out, `pkg-nodejs-${label}`)]));
const labels = Object.keys(packagePaths);
const apis = Object.fromEntries(labels.map(label => [label, require(path.join(packagePaths[label], 'font_wasm.js'))]));
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const pairs = process.env.MATH_PACKAGES ? labels.flatMap((a, i) => labels.slice(i + 1).map(b => [a, b]))
  : [['app', 'strict'], ['strict', 'fast'], ['app', 'fast']];
const rows = [], fonts = new Map();
function font(file, label) {
  const key = label + file;
  if (!fonts.has(key)) fonts.set(key, new apis[label].Font(fs.readFileSync(file)));
  return fonts.get(key);
}
function render(file, spec, label) {
  let value;
  try {
    value = font(file, label).render(spec);
    return { pixels: Buffer.from(value.pixels()), width: value.width(), height: value.height(), layout: value.layout() };
  } catch (error) { return { error: String(error) }; }
  finally { value?.free(); }
}
function compare(cell, file, spec) {
  const results = Object.fromEntries(labels.map(label => [label, render(file, spec, label)]));
  if (cell[0] === 'error' && !results.app.error) throw new Error(`Invalid control unexpectedly succeeded: ${JSON.stringify(cell)}`);
  const comparisons = pairs.map(([a, b]) => {
    const x = results[a], y = results[b];
    const errorsEqual = x.error === y.error;
    if (x.error || y.error) return { pair: [a, b], errorsEqual, errors: [x.error ?? null, y.error ?? null], identical: errorsEqual };
    let changedPixels = 0;
    const samples = [];
    for (let i = 0; i < Math.max(x.pixels.length, y.pixels.length); i += 4) {
      if (!x.pixels.subarray(i, i + 4).equals(y.pixels.subarray(i, i + 4))) {
        changedPixels++;
        if (samples.length < 12) samples.push([i / 4 % x.width, Math.floor(i / 4 / x.width)]);
      }
    }
    const layoutEqual = JSON.stringify(x.layout) === JSON.stringify(y.layout);
    const dimensionsEqual = x.width === y.width && x.height === y.height;
    return { pair: [a, b], identical: changedPixels === 0 && layoutEqual && dimensionsEqual,
      changedPixels, samples, layoutEqual, dimensionsEqual, pixelHashes: [sha(x.pixels), sha(y.pixels)] };
  });
  rows.push({ cell, spec, comparisons });
}
let index = 0;
try {
  for (const family of ['Roboto', 'SourceSans3']) {
    const file = path.join(root, 'fonts', family + '.ttf');
    if (shard === 0) {
      const values = Object.fromEntries(labels.map(label => [label, font(file, label).metadata()]));
      rows.push({ cell: ['metadata', family], comparisons: pairs.map(([a, b]) => ({ pair: [a, b], identical: JSON.stringify(values[a]) === JSON.stringify(values[b]) })) });
    }
    for (const size_px of [12, 14, 16, 18, 20, 24]) for (const wght of [300, 400, 700])
      for (const fitting of ['font_hints_auto', 'upstream_mono']) for (const rasterization of ['free_type_mono', 'free_type_mono_terminals'])
        for (const diagonal_fitting of [false, true]) {
          if (index++ % shards !== shard) continue;
          const spec = { text: Array.from({ length: 95 }, (_, i) => String.fromCodePoint(i + 32)).join(' '),
            width: 800, height: 384, size_px, axes: family === 'Roboto' ? { wght, wdth: 100 } : { wght }, output_bits: 1,
            mono_raster: { dropout: 'smart', include_stubs: true, font_instructions: true },
            pipeline: { fitting, rasterization, diagonal_fitting } };
          compare(['matrix', family, size_px, wght, fitting, rasterization, diagonal_fitting], file, spec);
          if (size_px === 16 && wght === 400 && fitting === 'font_hints_auto' && rasterization === 'free_type_mono' && diagonal_fitting) {
            for (let cp = 32; cp <= 126; cp++) compare(['glyph', family, String.fromCodePoint(cp)], file,
              { ...spec, text: String.fromCodePoint(cp), width: 64, height: 64 });
          }
        }
    if (shard === 0) {
      for (const spec of [
        { text: '', width: 64, height: 32, axes: { XXXX: 1 } },
        { text: 'x', width: 0, height: 32 },
        { text: '', width: 64, height: 32, pipeline: { fitting: 'font_hints_auto', rasterization: 'coverage', diagonal_fitting: true } },
        { text: 'x', width: 64, height: 32, renderer: 'candidate', pipeline: { fitting: 'upstream_mono', rasterization: 'free_type_mono' } },
      ]) compare(['error', family, rows.length], file, spec);
      for (const fitting of ['font_hints_auto', 'upstream_mono']) for (const diagonal_fitting of [false, true]) {
        const request = { config: { characters: 'kyxzvAW sX2 M^ We walked by the river.', size_px: 16,
          axes: family === 'Roboto' ? { wght: 400, wdth: 100 } : { wght: 400 }, output_bits: 1, kerning: true,
          mono_raster: { dropout: 'smart', include_stubs: true, font_instructions: true } }, letter_spacing_px: 0,
          pipeline: { fitting, rasterization: 'free_type_mono_terminals', diagonal_fitting } };
        const values = Object.fromEntries(labels.map(label => {
          try { return [label, { bytes: Buffer.from(font(file, label).export_playdate(request)) }]; }
          catch (error) { return [label, { error: String(error) }]; }
        }));
        rows.push({ cell: ['export', family, fitting, diagonal_fitting], comparisons: pairs.map(([a, b]) => {
          const x = values[a], y = values[b];
          return { pair: [a, b], identical: x.error || y.error ? x.error === y.error : x.bytes.equals(y.bytes),
            errors: [x.error ?? null, y.error ?? null], hashes: [x.bytes && sha(x.bytes), y.bytes && sha(y.bytes)] };
        }) });
      }
    }
  }
  // Consume the maintained general API matrix without changing its inputs.
  const smoke = fs.readFileSync(path.join(root, 'tools/wasm/smoke/parity.mjs'), 'utf8');
  const general = vm.runInNewContext(smoke.slice(smoke.indexOf('const cases = [];'), smoke.indexOf('const native = spawnSync')) + '\ncases;', { root, path });
  general.forEach((row, i) => { if (i % shards === shard) compare(['general', row.id], row.font_file, row.spec); });
} finally { for (const value of fonts.values()) value.free(); }
fs.writeFileSync(path.join(out, `delivery-${shard}.json`), JSON.stringify({ shard, shards, rows }, null, 2));
console.log(JSON.stringify({ shard, rows: rows.length,
  differences: Object.fromEntries(pairs.map(pair => [pair.join('/'), rows.filter(row => row.comparisons.some(c => c.pair.join('/') === pair.join('/') && !c.identical)).length])) }));
