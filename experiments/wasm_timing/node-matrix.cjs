const { spawnSync } = require('node:child_process');
const path = require('node:path');
const mode = process.argv[2] ?? 'default';
if (mode === 'legacy') {
  for (let round = 0; round < Number(process.env.ROUNDS ?? 6); round++) {
    const comparison = round % 3 === 0 ? 'AA' : 'AB';
    const config = { tier: 'legacy-default', comparison, reverse: false, round,
      requireLoader: true, noCold: true, legacyOrder: true, id: `node-legacy-default-${comparison}-forward-${round}` };
    const result = spawnSync(process.execPath, [path.join(__dirname, 'node-case.cjs'), JSON.stringify(config)],
      { stdio: 'inherit', env: { ...process.env, WARMUPS: process.env.WARMUPS ?? '1', REPEATS: process.env.REPEATS ?? '15' } });
    if (result.status !== 0) process.exit(result.status ?? 1);
    console.log(JSON.stringify({ finished: config.id, at: new Date().toISOString() }));
  }
  process.exit(0);
}
const tiers = mode === 'fixed' ? [
  ['baseline-only', ['--liftoff-only']], ['optimized-only', ['--no-liftoff', '--no-wasm-tier-up']],
] : [['default', []]];
const rounds = Number(process.env.ROUNDS ?? (mode === 'fixed' ? 2 : 3));
for (let round = 0; round < rounds; round++) {
  const comparisons = mode === 'fixed' ? ['AA', 'AB'] : ['AA', 'SS', 'AB'];
  if (round % 2) comparisons.reverse();
  for (const [tier, flags] of tiers) for (const comparison of comparisons) for (const reverse of [false, true]) {
    const config = { tier, comparison, reverse, round, id: `node-${tier}-${comparison}-${reverse ? 'reverse' : 'forward'}-${round}` };
    const result = spawnSync(process.execPath, [...flags, path.join(__dirname, 'node-case.cjs'), JSON.stringify(config)],
      { stdio: 'inherit', env: process.env });
    if (result.status !== 0) process.exit(result.status ?? 1);
    console.log(JSON.stringify({ finished: config.id, at: new Date().toISOString() }));
  }
}
