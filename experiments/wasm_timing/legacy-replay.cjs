// Replay the archived benchmark body, changing only package/output paths.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const trial = path.join(root, 'out/diagnostics/qp-objective-optimization');
const output = path.join(root, 'out/diagnostics/wasm-timing-investigation');
const original = fs.readFileSync(path.join(trial, 'benchmark.cjs'), 'utf8');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
for (let round = 0; round < Number(process.env.ROUNDS ?? 4); round++) {
  const comparison = round === 0 ? 'AA' : 'AB';
  const id = `node-exact-legacy-${comparison}-forward-${round}`;
  const replacementPaths = { before: path.join(trial, 'pkg-nodejs-before'), after: comparison === 'AA'
    ? path.join(root, 'tools/wasm/pkg-nodejs-preview') : path.join(trial, 'pkg-nodejs-sparse-trial') };
  const replacements = [
    ["const root=path.resolve(__dirname,'../../..');", `const root=${JSON.stringify(root)};`],
    ["const paths={before:path.join(__dirname,'pkg-nodejs-before'),after:path.join(root,'tools/wasm/pkg-nodejs-preview')};", `const paths=${JSON.stringify(replacementPaths)};`],
    ["path.join(__dirname,process.env.OUTPUT??'timing.json')", 'process.env.OUTPUT'],
  ];
  let generated = original;
  for (const [before, after] of replacements) {
    assert.equal(generated.split(before).length, 2);
    generated = generated.replace(before, after);
  }
  const script = path.join(output, id + '.cjs');
  fs.writeFileSync(script, generated);
  const rawPath = path.join(output, id + '-raw.json');
  const fd = fs.openSync(path.join(output, id + '.log'), 'w');
  const result = spawnSync(process.execPath, [script], { stdio: ['ignore', fd, fd], env: {
    ...process.env, OUTPUT: rawPath, WARMUPS: process.env.WARMUPS ?? '1', REPEATS: process.env.REPEATS ?? '15',
  } });
  fs.closeSync(fd);
  if (result.status !== 0) process.exit(result.status ?? 1);
  const raw = JSON.parse(fs.readFileSync(rawPath, 'utf8'));
  const data = { ...raw, config: { tier: 'exact-legacy', comparison, reverse: false, round, id },
    sourceSha: sha(original), adaptedSha: sha(generated), cold: [],
    rows: raw.rows.map(row => ({ ...row, legacyLabel: row.label, label: row.label === 'before' ? 0 : 1 })) };
  fs.writeFileSync(path.join(output, id + '.json'), JSON.stringify(data, null, 2));
  console.log(JSON.stringify({ finished: id, at: new Date().toISOString() }));
}
