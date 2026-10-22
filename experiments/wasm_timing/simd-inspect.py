"""Count standard/relaxed SIMD instructions and owning functions in a saved WASM build."""
import collections
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/diagnostics/wasm-simd-optimization'
label = sys.argv[1]
path = OUT / f'pkg-web-{label}/font_wasm_bg.wasm'
counts = collections.Counter()
functions = collections.defaultdict(collections.Counter)
function = ''
proc = subprocess.Popen(['/opt/homebrew/opt/llvm/bin/llvm-objdump', '-d', '--no-show-raw-insn', str(path)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
for line in proc.stdout:
    header = re.match(r'^[0-9a-f]+ <(.+)>:', line)
    if header:
        function = re.sub(r'\[[0-9a-f]+\]', '', header[1])
    match = re.search(r'\b((?:v128|i8x16|i16x8|i32x4|i64x2|f32x4|f64x2)\.[a-z0-9_]+)', line)
    if match:
        counts[match[1]] += 1
        functions[function][match[1]] += 1
error = proc.stderr.read()
assert proc.wait() == 0, error
assert not any('relaxed' in name for name in counts), 'Unexpected relaxed SIMD.'
report = {'label': label, 'wasm_sha': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size,
          'simd_instructions': sum(counts.values()), 'instructions': dict(counts),
          'functions': [{'name': name, 'instructions': dict(ops), 'count': sum(ops.values())}
                        for name, ops in sorted(functions.items(), key=lambda v: -sum(v[1].values()))]}
(OUT / f'instructions-{label}.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: report[key] for key in ['label', 'wasm_sha', 'bytes', 'simd_instructions']}))
