"""Build diagnostic WASM capture adapters and compare complete native/scalar/SIMD reports."""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/diagnostics/wasm-simd-optimization'
REF = pathlib.Path(os.environ.get('SIMD_NATIVE_REFERENCE_DIR', ROOT / 'out/diagnostics/interval-diagnostics-optimization'))


def build(label):
    assert label in ['scalar', 'simd']
    pkg = OUT / f'capture-pkg-{label}'
    assert not pkg.exists(), 'Preserve a frozen capture package.'
    dst = OUT / 'capture-adapter'
    (dst / 'src').mkdir(parents=True, exist_ok=True)
    (dst / 'Cargo.toml').write_text('''[package]
name="simd-capture"
version="0.0.0"
edition="2021"
[lib]
crate-type=["cdylib"]
[dependencies]
font_generator={path=GENERATOR,default-features=false,features=["candidate"]}
wasm-bindgen="=0.2.129"
serde_json={version="1",features=["float_roundtrip"]}
'''.replace('GENERATOR', json.dumps(str(ROOT / 'crates/generator'))))
    locked = (dst / 'Cargo.lock').exists()
    if not locked:
        shutil.copyfile(ROOT / 'crates/wasm/Cargo.lock', dst / 'Cargo.lock')
    (dst / 'src/lib.rs').write_text('''use wasm_bindgen::prelude::*;
#[wasm_bindgen]
pub fn capture(bytes:&[u8],request:&str,pipeline:&str)->String {
 let request=serde_json::from_str(request).unwrap();
 let pipeline=serde_json::from_str(pipeline).unwrap();
 let result=font_generator::candidate::render_with_pipeline(bytes,&request,pipeline);
 match result{Ok(r)=>serde_json::json!({"ok":r}),Err(e)=>serde_json::json!({"error":e.to_string()})}.to_string()
}
''')
    env = dict(os.environ)
    env.pop('RUSTFLAGS', None)
    env.pop('CARGO_ENCODED_RUSTFLAGS', None)
    env['CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUSTFLAGS'] = '-Ctarget-feature=+simd128' if label == 'simd' else ''
    env['PATH'] = '/opt/homebrew/opt/llvm/bin:' + env['PATH']
    with (OUT / f'capture-build-{label}.log').open('w') as log:
        subprocess.run(['cargo', 'build', *(['--locked'] if locked else []), '--release', '--offline', '--target', 'wasm32-unknown-unknown',
                        '--manifest-path', str(dst / 'Cargo.toml'), '--target-dir', str(OUT / 'capture-target')],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([env.get('WASM_BINDGEN', '/tmp/font-generator-wasm-tools/bin/wasm-bindgen'), '--target', 'nodejs',
                    '--out-dir', str(pkg), str(OUT / 'capture-target/wasm32-unknown-unknown/release/simd_capture.wasm')], check=True)
    (pkg / 'package.json').write_text('{"type":"commonjs"}\n')


def run(compare_only=False):
    # Verify that the reused native captures still describe these generator sources.
    frozen = json.loads((REF / 'source-before.json').read_text())
    checked = 0
    for path, sha in frozen.items():
        if path.startswith('crates/generator/'):
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path
            checked += 1
    spec = importlib.util.spec_from_file_location('stage_capture', ROOT / 'experiments/hobby_fitting/stage_capture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = list(module.requests())
    (OUT / 'capture-requests.json').write_text(json.dumps(rows))
    runner = OUT / 'capture-runner.cjs'
    runner.write_text('''const fs=require('node:fs'),path=require('node:path');
const out=__dirname,rows=JSON.parse(fs.readFileSync(path.join(out,'capture-requests.json'))),shard=Number(process.argv[2]);
const fonts=new Map();
for(const label of ['scalar','simd']){
const api=require(path.join(out,'capture-pkg-'+label,'simd_capture.js'));
const fd=fs.openSync(path.join(out,'capture-'+label+'-'+shard+'.jsonl'),'w');
for(let i=shard;i<rows.length;i+=6){const r=rows[i];if(!fonts.has(r.font))fonts.set(r.font,fs.readFileSync(r.font));
const result=api.capture(fonts.get(r.font),JSON.stringify(r.request),JSON.stringify(r.pipeline));
fs.writeSync(fd,'{"cell":'+JSON.stringify(r.cell)+',"output":'+result+'}\\n');
}fs.closeSync(fd);}
''')
    def shard(index):
        with (OUT / f'capture-run-{index}.log').open('w') as log:
            subprocess.run(['node', str(runner), str(index)], stdout=log, stderr=subprocess.STDOUT, check=True)
    if not compare_only:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(shard, range(6)))
    cases = glyphs = 0
    native_differences = []
    for index in range(6):
        files = [REF / f'captures-before-{index}.jsonl', OUT / f'capture-scalar-{index}.jsonl', OUT / f'capture-simd-{index}.jsonl']
        streams = [p.open() for p in files]
        try:
            for lines in zip(*streams, strict=True):
                native, scalar, simd = [json.loads(line) for line in lines]
                assert native['cell'] == scalar['cell'] == simd['cell']
                scalar_json = json.dumps(scalar, sort_keys=True)
                assert scalar_json == json.dumps(simd, sort_keys=True), native['cell']
                if json.dumps(native, sort_keys=True) != scalar_json:
                    native_differences.append(native['cell'])
                cases += 1
                glyphs += len(native['output']['ok']['records'])
        finally:
            for stream in streams:
                stream.close()
    result = {'cases': cases, 'glyphs': glyphs, 'full_report_mismatches': 0,
              'native_reference_generator_files_verified': checked,
              'native_vs_scalar_full_report_differences': native_differences,
              'note': 'Diagnostic WASM adapters exercise the same generator API with each compiler setting; actual delivery packages are checked separately.'}
    (OUT / 'capture-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    if sys.argv[1] in ['run', 'compare']:
        run(compare_only=sys.argv[1] == 'compare')
    else:
        build(sys.argv[1])
