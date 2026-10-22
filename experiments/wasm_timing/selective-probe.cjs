const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const out = process.argv[2];
const instances = Object.fromEntries(['strict', 'fast'].map(label => {
  const module = new WebAssembly.Module(fs.readFileSync(path.join(out, `probe-${label}.wasm`)));
  const imports = {};
  for (const entry of WebAssembly.Module.imports(module)) {
    assert.equal(entry.kind, 'function');
    assert(entry.name.includes('panic_bounds_check'));
    (imports[entry.module] ??= {})[entry.name] = () => { throw new Error('Unexpected probe bounds panic'); };
  }
  return [label, new WebAssembly.Instance(module, imports).exports];
}));
const hex = x => { const bytes = Buffer.alloc(8); bytes.writeDoubleLE(x); return bytes.toString('hex'); };
let state = 314159;
const random = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state / 2**32; };
const cases = [
  [[1, 2], [3, 4]], [[1, 1], [1, -1]], [[1e16, 1, -1e16], [1, 1, 1]],
  [[0, -0], [1, 1]], [[Infinity], [1]], [[NaN], [1]], [[1e308], [1e308]],
  [[Number.MIN_VALUE], [0.5]], [[], []], [[1e-300], [1]],
];
for (const exponentRange of [40, 2000]) {
  for (const n of [1, 2, 3, 4, 7, 8, 15, 32, 127]) for (let i = 0; i < 32; i++) {
    const vector = () => Array.from({ length: n }, () => (random() - 0.5) * 2**Math.floor(random() * exponentRange - exponentRange / 2));
    cases.push([vector(), vector()]);
  }
}
const rows = cases.map(([a, b]) => {
  const row = { a: a.map(hex), b: b.map(hex) };
  for (const [label, api] of Object.entries(instances)) {
    const base = api.input(), second = base + 256 * 8;
    new Float64Array(api.memory.buffer, base, a.length).set(a);
    new Float64Array(api.memory.buffer, second, b.length).set(b);
    row[label] = { bounded: hex(api.bounded(base, second, a.length)), proposal: hex(api.proposal(base, second, a.length)) };
  }
  return row;
});
const knownAbstentions = [1, 2, 3, 4, 5, 6, 7, 8];
for (const i of knownAbstentions) for (const label of ['strict', 'fast']) {
  assert(Number.isNaN(Buffer.from(rows[i][label].bounded, 'hex').readDoubleLE()));
}
const witness = Object.fromEntries(Object.entries(instances).map(([label, api]) => [label, api.witness(1, 2**-53)]));
fs.writeFileSync(path.join(out, 'probe-results.json'), JSON.stringify({ rows, witness, knownAbstentions }, null, 2));
