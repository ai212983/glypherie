"""Build isolated strict scalar/SIMD WASM preview packages with locked dependencies."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/diagnostics/wasm-simd-optimization'
label = sys.argv[1]
assert label in ['scalar', 'simd']
flags = '-Ctarget-feature=+simd128' if label == 'simd' else ''
env = dict(os.environ)
for name in ['RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS']:
    env.pop(name, None)
env['CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUSTFLAGS'] = flags
env['PATH'] = '/opt/homebrew/opt/llvm/bin:' + env['PATH']
bindgen = env.get('WASM_BINDGEN', '/tmp/font-generator-wasm-tools/bin/wasm-bindgen')
for kind in ['web', 'nodejs']:
    assert not (OUT / f'pkg-{kind}-{label}').exists(), 'Preserve the frozen package.'
with (OUT / f'build-{label}.log').open('w') as log:
    subprocess.run(['cargo', 'build', '--locked', '--offline', '--release', '--target', 'wasm32-unknown-unknown',
                    '--manifest-path', str(ROOT / 'crates/wasm/Cargo.toml'), '--target-dir', str(OUT / 'target'),
                    '--features', 'preview'], env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
wasm = OUT / 'target/wasm32-unknown-unknown/release/font_wasm.wasm'
for kind in ['web', 'nodejs']:
    dst = OUT / f'pkg-{kind}-{label}'
    subprocess.run([bindgen, '--target', kind, '--out-dir', str(dst), str(wasm)], check=True)
    for name in ['LICENSE-FreeType.txt', 'LICENSE-Skrifa-scan.txt']:
        shutil.copyfile(OUT / 'pkg-web-before' / name, dst / name)
    if kind == 'nodejs':
        (dst / 'package.json').write_text('{"type":"commonjs"}\n')
identity = {'label': label, 'rust_target_flags': flags,
            'wasm_sha': hashlib.sha256((OUT / f'pkg-web-{label}/font_wasm_bg.wasm').read_bytes()).hexdigest()}
assert (OUT / f'pkg-web-{label}/font_wasm_bg.wasm').read_bytes() == (OUT / f'pkg-nodejs-{label}/font_wasm_bg.wasm').read_bytes()
(OUT / f'identity-{label}.json').write_text(json.dumps(identity, indent=2) + '\n')
print(json.dumps(identity))
