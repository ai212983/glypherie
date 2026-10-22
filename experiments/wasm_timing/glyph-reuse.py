#!/usr/bin/env python3
"""Isolated interaction census and ordinary SIMD builds for completed-fit reuse."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/diagnostics/glyph-reuse-optimization'


def clone(destination):
    assert not destination.exists()
    for name in ['generator', 'wasm']:
        base, target = ROOT / 'tools' / name, destination / 'tools' / name
        target.mkdir(parents=True)
        for filename in ['Cargo.toml', 'Cargo.lock', 'build.rs']:
            if (base / filename).exists():
                shutil.copyfile(base / filename, target / filename)
        shutil.copytree(base / 'src', target / 'src')
        if (base / 'vendor').exists():
            shutil.copytree(base / 'vendor', target / 'vendor')
        for dirname in ['tests', 'examples']:
            if (base / dirname).exists():
                shutil.copytree(base / dirname, target / dirname)
    (destination / 'fonts').symlink_to(ROOT / 'fonts', target_is_directory=True)


def census():
    source = OUT / 'source-census'
    clone(source)
    qp = source / 'tools/generator/src/candidate.rs'
    text = qp.read_text()
    needle = '        let Ok(fit) = crate::diagonal_fitting::approved::fit('
    if needle not in text:
        needle = '        let compute = || {'
        session = source / 'tools/generator/src/reference.rs'
        session.write_text(session.read_text().replace('diagonal_fits: Some(&font.diagonal_fits)',
                                                     'diagonal_fits: None'))
    assert text.count(needle) == 1
    text = text.replace(needle, '''        let reuse_key = serde_json::to_vec(&(
            &raw_features, &raw.fitted_commands, &record.fitted_commands,
            size_px, &donors, native_axes,
        )).unwrap();
        eprintln!("REUSE_KEY {:x}", sha2::Sha256::digest(&reuse_key));
''' + needle)
    qp.write_text(text)
    shutil.copyfile(ROOT / 'experiments/wasm_timing/glyph-reuse-probe.rs',
                    source / 'tools/generator/src/bin/glyph_reuse_probe.rs')
    command = ['cargo', 'run', '--locked', '--offline', '--release', '--manifest-path',
               source / 'tools/generator/Cargo.toml', '--target-dir', OUT / 'target-native',
               '--bin', 'glyph_reuse_probe', '--', ROOT / 'fonts']
    with (OUT / 'census.jsonl').open('w') as output, (OUT / 'census.log').open('w') as log:
        subprocess.run(command, stdout=output, stderr=log, check=True)
    seen, rows, current = {}, [], None
    for line in (OUT / 'census.log').read_text().splitlines():
        if line.startswith('REUSE_REQUEST '):
            current = json.loads(line.removeprefix('REUSE_REQUEST '))
            current.update(calls=0, repeated=0)
            rows.append(current)
        elif line.startswith('REUSE_KEY '):
            key = line.removeprefix('REUSE_KEY ')
            current['calls'] += 1
            keys = seen.setdefault(current['family'], set())
            current['repeated'] += int(key in keys)
            keys.add(key)
    (OUT / 'census-summary.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(rows))


def build(label):
    assert label == 'cache'
    env = dict(os.environ)
    env.pop('RUSTFLAGS', None)
    env.pop('CARGO_ENCODED_RUSTFLAGS', None)
    env['CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUSTFLAGS'] = '-Ctarget-feature=+simd128'
    env['PATH'] = '/opt/homebrew/opt/llvm/bin:' + env['PATH']
    env.setdefault('AR_wasm32_unknown_unknown', '/opt/homebrew/opt/llvm/bin/llvm-ar')
    env.setdefault('RANLIB_wasm32_unknown_unknown', '/opt/homebrew/opt/llvm/bin/llvm-ranlib')
    source = OUT / 'source-cache'
    clone(source)
    with (OUT / f'build-{label}.log').open('w') as log:
        subprocess.run(['cargo', 'build', '--locked', '--offline', '--release', '--target',
                        'wasm32-unknown-unknown', '--features', 'preview', '--manifest-path',
                        source / 'tools/wasm/Cargo.toml', '--target-dir', OUT / 'target-wasm'],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    wasm = OUT / 'target-wasm/wasm32-unknown-unknown/release/font_wasm.wasm'
    bindgen = env.get('WASM_BINDGEN', '/tmp/font-generator-wasm-tools/bin/wasm-bindgen')
    for kind in ['web', 'nodejs']:
        target = OUT / f'pkg-{kind}-{label}'
        assert not target.exists()
        subprocess.run([bindgen, '--target', kind, '--out-dir', target, wasm], check=True)
        for filename in ['LICENSE-FreeType.txt', 'LICENSE-Skrifa-scan.txt']:
            shutil.copyfile(OUT / 'pkg-web-app' / filename, target / filename)
        if kind == 'nodejs':
            (target / 'package.json').write_text('{"type":"commonjs"}\n')
    (OUT / f'identity-{label}.json').write_text(json.dumps({'wasm_sha': hashlib.sha256(
        (OUT / f'pkg-web-{label}/font_wasm_bg.wasm').read_bytes()).hexdigest()}, indent=2) + '\n')


def stats():
    source = OUT / 'source-stats'
    clone(source)
    module = source / 'tools/generator/src/diagonal_fitting/reuse.rs'
    module.write_text(module.read_text().replace('#[cfg(test)]', '') + '''
impl FitCache {
    pub(crate) fn snapshot(&self) -> serde_json::Value {
        serde_json::json!({"hits":self.hits,"misses":self.misses,"evictions":self.evictions,
            "entries":self.entries.len(),"payload_bytes":self.bytes})
    }
}
''')
    font = source / 'tools/generator/src/source.rs'
    font.write_text(font.read_text() + '''
impl PreparedFont {
    pub fn diagnostic_cache_stats(&self) -> serde_json::Value {
        self.diagonal_fits.borrow().snapshot()
    }
}
''')
    probe = (ROOT / 'experiments/wasm_timing/glyph-reuse-probe.rs').read_text()
    probe = probe.replace('"ms":', '"cache": font.diagnostic_cache_stats(), "ms":')
    (source / 'tools/generator/src/bin/glyph_reuse_probe.rs').write_text(probe)
    with (OUT / 'cache-stats.jsonl').open('w') as output, (OUT / 'cache-stats.log').open('w') as log:
        subprocess.run(['cargo', 'run', '--locked', '--offline', '--release', '--manifest-path',
                        source / 'tools/generator/Cargo.toml', '--target-dir', OUT / 'target-native',
                        '--bin', 'glyph_reuse_probe', '--', ROOT / 'fonts'], stdout=output, stderr=log, check=True)
    baseline = [json.loads(line) for line in (OUT / 'census.jsonl').read_text().splitlines()]
    rows = [json.loads(line) for line in (OUT / 'cache-stats.jsonl').read_text().splitlines()]
    assert [(r['family'], r['case'], r['sha']) for r in rows] == [(r['family'], r['case'], r['sha']) for r in baseline]
    assert all(r['cache']['payload_bytes'] <= 2*1024*1024 and r['cache']['entries'] <= 256 for r in rows)
    (OUT / 'cache-stats-summary.json').write_text(json.dumps({'rows': rows, 'delivery_equal': True,
        'payload_bound': True}, indent=2) + '\n')


if __name__ == '__main__':
    if sys.argv[1] == 'census':
        census()
    elif sys.argv[1] == 'stats':
        stats()
    else:
        build(sys.argv[1])
