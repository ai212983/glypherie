const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { stripTypeScriptTypes } = require('node:module');
const root = path.resolve(__dirname, '../..');
const output = path.resolve(process.env.OUTPUT_DIR ?? path.join(root, 'out/diagnostics/wasm-timing-investigation'));
fs.mkdirSync(output, { recursive: true });
const { chromium } = require(path.join(root, 'apps/web/node_modules/playwright-core'));
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const source = fs.readFileSync(path.join(root, 'apps/web/src/app/renderer/font-worker.ts'), 'utf8');
const instrumented = source
  .replace('import initWasm, { Font } from "./wasm/font_wasm.js";', 'import initWasm, { Font } from "./packages/VARIANT/font_wasm.js";')
  .replace('import wasmBinaryUrl from "./wasm/font_wasm_bg.wasm?url";', 'const wasmBinaryUrl = new URL("./packages/VARIANT/font_wasm_bg.wasm", import.meta.url);')
  .replace('import staged from "./wasm/staged.json";', 'const staged = { available: true };')
  .replace('const result = font.render(msg.spec);', 'const renderStart = performance.now();\n      const result = font.render(msg.spec);\n      const workerRenderMs = performance.now() - renderStart;')
  .replace('value: { width, height, pixels: buffer, layout }', 'value: { width, height, pixels: buffer, layout, workerRenderMs }');
assert.notEqual(source, instrumented);
assert.ok(instrumented.includes('const workerRenderMs'));
const generated = stripTypeScriptTypes(instrumented, { mode: 'strip' });
fs.writeFileSync(path.join(output, 'instrumented-app-worker.js'), generated);
const packages = {
  baseline: path.resolve(process.env.BASELINE_WEB_PACKAGE ?? path.join(root, 'crates/wasm/pkg-web-preview')),
  sparse: path.resolve(process.env.CANDIDATE_WEB_PACKAGE ?? path.join(root, 'out/diagnostics/qp-objective-optimization/pkg-web-sparse-trial')),
};
const identities = Object.fromEntries(Object.entries(packages).map(([name, folder]) => [name, {
  wasm: sha(fs.readFileSync(path.join(folder, 'font_wasm_bg.wasm'))),
  glue: sha(fs.readFileSync(path.join(folder, 'font_wasm.js'))),
}]));
const mime = { '.js': 'text/javascript', '.wasm': 'application/wasm', '.ttf': 'font/ttf' };
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  let bytes;
  if (url.pathname === '/') bytes = Buffer.from('<!doctype html><meta charset="utf-8"><title>Worker timing controls</title>');
  else if (/^\/(baseline|sparse)-worker\.js$/.test(url.pathname)) {
    bytes = Buffer.from(generated.replaceAll('VARIANT', url.pathname.includes('sparse') ? 'sparse' : 'baseline'));
  } else if (/^\/packages\/(baseline|sparse)\/font_wasm(\.js|_bg\.wasm)$/.test(url.pathname)) {
    const [, name, filename] = url.pathname.split('/').slice(1);
    bytes = fs.readFileSync(path.join(packages[name], filename));
  } else if (/^\/fonts\/(Roboto|SourceSans3)\.ttf$/.test(url.pathname)) {
    bytes = fs.readFileSync(path.join(root, url.pathname.slice(1)));
  } else { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'Content-Type': url.pathname === '/' ? 'text/html' : mime[path.extname(url.pathname)], 'Cache-Control': 'no-store' });
  res.end(bytes);
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const executablePath = process.env.WEB_TEST_BROWSER ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const mode = process.argv[2] ?? 'default';
  const tiers = mode === 'fixed' ? [
    ['baseline-only', ['--js-flags=--liftoff-only']],
    ['optimized-only', ['--js-flags=--no-liftoff --no-wasm-tier-up']],
  ] : [['default', []]];
  const rounds = Number(process.env.ROUNDS ?? (mode === 'fixed' ? 2 : 3));
  const repeats = Number(process.env.REPEATS ?? 12), warmups = Number(process.env.WARMUPS ?? 3);
  try {
    for (let round = 0; round < rounds; round++) {
      const comparisons = process.env.COMPARISONS ? process.env.COMPARISONS.split(',')
        : mode === 'fixed' ? ['AA', 'AB'] : round % 2 ? ['AB', 'SS', 'AA'] : ['AA', 'SS', 'AB'];
      for (const [tier, args] of tiers) for (const comparison of comparisons) for (const reverse of [false, true]) {
        const variants = { AA: ['baseline', 'baseline'], SS: ['sparse', 'sparse'], AB: ['baseline', 'sparse'] }[comparison];
        const config = { tier, comparison, reverse, round, variants, repeats, warmups, caseFilter: process.env.CASE_FILTER,
          compareOutputDifferences: process.env.COMPARE_OUTPUT_DIFFERENCES === '1',
          variedRequests: process.env.VARIED_REQUESTS === '1',
          interactionReplay: process.env.INTERACTION_REPLAY === '1',
          id: `browser-${tier}-${comparison}-${reverse ? 'reverse' : 'forward'}-${round}` };
        const browser = await chromium.launch({ executablePath, headless: true, args });
        try {
          const page = await browser.newPage();
          await page.goto(origin);
          const errors = [];
          page.on('pageerror', e => errors.push(e.message));
          const result = await page.evaluate(async config => {
            const rows = [], cold = [], workers = [], loadMs = [], outputDifferences = [];
            let seq = 0;
            const rpc = (worker, message) => new Promise((resolve, reject) => {
              const id = ++seq;
              const timer = setTimeout(() => reject(new Error('worker timeout')), 60000);
              const listener = event => {
                if (event.data.seq !== id) return;
                worker.removeEventListener('message', listener); clearTimeout(timer);
                if (event.data.ok) resolve(event.data); else reject(new Error(event.data.error));
              };
              worker.addEventListener('message', listener);
              worker.postMessage({ ...message, seq: id });
            });
            const hash = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
              .map(n => n.toString(16).padStart(2, '0')).join('');
            for (const label of config.reverse ? [1, 0] : [0, 1]) {
              const start = performance.now();
              const worker = new Worker(`/${config.variants[label]}-worker.js`, { type: 'module' });
              workers[label] = worker;
              await rpc(worker, { kind: 'ping' });
              loadMs[label] = performance.now() - start;
            }
            try {
              for (const family of config.reverse ? ['SourceSans3', 'Roboto'] : ['Roboto', 'SourceSans3']) {
                const bytes = await (await fetch(`/fonts/${family}.ttf`)).arrayBuffer();
                for (const worker of workers) await rpc(worker, { kind: 'load', fontId: family, bytes });
                const cases = config.interactionReplay ? [
                  ['repeat', 'Pack my box with five dozen liquor jugs.', true],
                  ['resize', 'Pack my box with five dozen liquor jugs.', true],
                  ['spacing', 'Pack my box with five dozen liquor jugs.', true],
                  ['append', 'Pack my box with five dozen liquor jugs. é', true],
                  ['delete', 'Pack my box', true],
                  ['kerning', 'Pack my box with five dozen liquor jugs.', true],
                  ['new-weight', 'Pack my box with five dozen liquor jugs.', true],
                  ['return-weight', 'Pack my box with five dozen liquor jugs.', true],
                  ['new-size', 'Pack my box with five dozen liquor jugs.', true],
                  ['return-size', 'Pack my box with five dozen liquor jugs.', true],
                  ['color', 'Pack my box with five dozen liquor jugs.', true],
                ] : [
                  ['pangram', 'Pack my box with five dozen liquor jugs.', true],
                  ['disabled', 'Pack my box with five dozen liquor jugs.', false],
                  ['stress', 's x X 2 A y W', true],
                ];
                if (config.reverse) cases.reverse();
                for (const [caseName, text, diagonal] of cases) {
                  if (config.caseFilter && config.caseFilter !== caseName) continue;
                  const spec = { text, width: caseName === 'resize' ? 160 : 600, height: 160, size_px: 16,
                    axes: family === 'Roboto' ? { wght: 400, wdth: 100 } : { wght: 400 }, output_bits: 1,
                    ...(caseName === 'spacing' ? { letter_spacing_px: 1 } : {}),
                    ...(caseName === 'kerning' ? { kerning: false } : {}),
                    ...(caseName === 'color' ? { foreground: [100, 50, 0, 255] } : {}),
                    pipeline: { fitting: 'font_hints_auto', rasterization: config.interactionReplay
                      ? 'free_type_mono_terminals' : 'free_type_mono', diagonal_fitting: diagonal } };
                  const expected = new Map();
                  const crossOutputs = new Map(), changedRequests = new Set();
                  for (let i = -1; i < config.warmups + config.repeats; i++) {
                    const step = Math.max(0, i - config.warmups);
                    let actualSpec = config.variedRequests ? { ...spec,
                      size_px: [12, 16, 20, 24][step % 4],
                      axes: family === 'Roboto'
                        ? { wght: [300, 400, 700][step % 3], wdth: [75, 90, 100][step % 3] }
                        : { wght: [300, 400, 700][step % 3] } } : spec;
                    // Every request in these two cases is a fresh fitting key,
                    // including warm-up calls. Revisits have separate cases.
                    if (caseName === 'new-weight') actualSpec = { ...spec, axes: { ...spec.axes, wght: 401 + (i + 1) * 0.25 } };
                    if (caseName === 'new-size') actualSpec = { ...spec, size_px: 17 + (i + 1) * 0.125 };
                    const key = JSON.stringify(actualSpec);
                    const order = ((i + 1 + Number(config.reverse)) % 2) ? [1, 0] : [0, 1];
                    for (let ordinal = 0; ordinal < order.length; ordinal++) {
                      const label = order[ordinal];
                      const start = performance.now();
                      const response = await rpc(workers[label], { kind: 'render', fontId: family, token: seq + 1, spec: actualSpec });
                      const roundTripMs = performance.now() - start;
                      const value = response.value;
                      const identity = JSON.stringify({ pixels: await hash(value.pixels), layout: value.layout,
                        width: value.width, height: value.height });
                      const identityKey = config.compareOutputDifferences ? `${label}/${key}` : key;
                      if (expected.has(identityKey) && expected.get(identityKey) !== identity) throw new Error(`output differs: ${family}/${caseName}/${label}`);
                      expected.set(identityKey, identity);
                      if (config.compareOutputDifferences) {
                        const pair = crossOutputs.get(key) ?? {};
                        pair[label] = identity;
                        crossOutputs.set(key, pair);
                        if (pair[0] && pair[1] && pair[0] !== pair[1] && !changedRequests.has(key)) {
                          changedRequests.add(key);
                          outputDifferences.push({ family, caseName, spec: actualSpec, outputs: { ...pair } });
                        }
                      }
                      const row = { family, caseName, label, ordinal, repeat: i - config.warmups,
                        phase: i === -1 ? 'cold' : i < config.warmups ? 'warmup' : 'measured',
                        ms: value.workerRenderMs, roundTripMs, sizePx: actualSpec.size_px, axes: actualSpec.axes };
                      if (row.phase === 'measured') rows.push(row); else cold.push(row);
                    }
                  }
                }
                for (const worker of workers) await rpc(worker, { kind: 'unload', fontId: family });
              }
            } finally { workers.forEach(worker => worker.terminate()); }
            return { rows, cold, loadMs, outputDifferences, userAgent: navigator.userAgent };
          }, config);
          assert.deepEqual(errors, []);
          fs.writeFileSync(path.join(output, config.id + '.json'), JSON.stringify({ config, identities,
            packagePaths: packages,
            workerSource: sha(source), instrumentedSource: sha(generated), browser: browser.version(), flags: args, ...result }, null, 2));
          console.log(JSON.stringify({ finished: config.id, at: new Date().toISOString() }));
        } finally { await browser.close(); }
      }
    }
  } finally { server.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; server.close(); });
