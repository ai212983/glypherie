const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const Module = require('node:module');
const os = require('node:os');
const root = path.resolve(__dirname, '../..');
const trial = path.join(root, 'out/diagnostics/qp-objective-optimization');
const output = path.join(root, 'out/diagnostics/wasm-timing-investigation');
const config = JSON.parse(process.argv[2]);
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const packages = { baseline: 'pkg-nodejs-before', sparse: 'pkg-nodejs-sparse-trial' };
const variants = { AA: ['baseline', 'baseline'], SS: ['sparse', 'sparse'], AB: ['baseline', 'sparse'] }[config.comparison];
const loads = config.reverse ? [1, 0] : [0, 1];
const modules = [], identities = [], moduleMs = [];
for (const label of loads) {
  const folder = path.join(trial, packages[variants[label]]);
  const filename = path.join(folder, 'font_wasm.js');
  const bytes = fs.readFileSync(path.join(folder, 'font_wasm_bg.wasm'));
  identities[label] = { variant: variants[label], wasm: sha(bytes), glue: sha(fs.readFileSync(filename)) };
  // A fresh JS wrapper and WASM instance for each label, even when bytes are identical.
  // V8 may share compiled code for identical modules; the A/A control intentionally retains that engine behavior.
  const wrapper = new Module(filename, module);
  wrapper.filename = filename;
  wrapper.paths = Module._nodeModulePaths(folder);
  const start = performance.now();
  if (config.requireLoader) {
    delete require.cache[require.resolve(filename)];
    wrapper.exports = require(filename);
  } else wrapper._compile(fs.readFileSync(filename, 'utf8'), filename);
  moduleMs[label] = performance.now() - start;
  modules[label] = wrapper.exports;
}
const rows = [], cold = [];
const repeats = Number(process.env.REPEATS ?? 12), warmups = Number(process.env.WARMUPS ?? 3);
const families = config.reverse ? ['SourceSans3', 'Roboto'] : ['Roboto', 'SourceSans3'];
for (const family of families) {
  const bytes = fs.readFileSync(path.join(root, 'fonts', family + '.ttf'));
  const fonts = modules.map(pkg => new pkg.Font(bytes));
  try {
    const cases = [
      ['pangram', 'Pack my box with five dozen liquor jugs.', true],
      ['disabled', 'Pack my box with five dozen liquor jugs.', false],
      ['stress', 's x X 2 A y W', true],
    ];
    if (config.reverse) cases.reverse();
    for (const [caseName, text, diagonal] of cases) {
      if (process.env.CASE_FILTER && process.env.CASE_FILTER !== caseName) continue;
      const spec = { text, width: 600, height: 160, size_px: 16,
        axes: family === 'Roboto' ? { wght: 400, wdth: 100 } : { wght: 400 }, output_bits: 1,
        pipeline: { fitting: 'font_hints_auto', rasterization: 'free_type_mono', diagonal_fitting: diagonal } };
      let expected;
      function run(label, phase, repeat, ordinal) {
        const start = performance.now();
        const result = fonts[label].render(spec);
        const ms = performance.now() - start;
        try {
          const identity = { pixels: sha(result.pixels()), layout: result.layout() };
          if (expected) assert.deepEqual(identity, expected); else expected = identity;
          const record = { family, caseName, label, phase, repeat, ordinal, ms };
          if (phase === 'measured') rows.push(record); else cold.push(record);
        } finally { result.free(); }
      }
      for (let i = config.noCold ? 0 : -1; i < warmups + repeats; i++) {
        const parity = config.legacyOrder ? (i < warmups ? i : i - warmups) : i + 1;
        const order = ((parity + Number(config.reverse)) % 2) ? [1, 0] : [0, 1];
        for (let j = 0; j < order.length; j++)
          run(order[j], i === -1 ? 'cold' : i < warmups ? 'warmup' : 'measured', i - warmups, j);
      }
    }
  } finally { fonts.forEach(font => font.free()); }
}
fs.writeFileSync(path.join(output, config.id + '.json'), JSON.stringify({ config, identities, moduleMs,
  repeats, warmups, flags: process.execArgv, node: process.version, v8: process.versions.v8,
  cpu: os.cpus()[0].model, rows, cold }, null, 2));
