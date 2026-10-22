#!/usr/bin/env python3
"""Isolated matched strict/fast LLVM experiment; never edits or stages app packages."""
import collections
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(os.environ.get('MATH_OUTPUT_DIR', ROOT / 'out/diagnostics/fast-math-optimization'))
SOURCE_ROOT = pathlib.Path(os.environ.get('MATH_SOURCE_ROOT', ROOT))
LLVM = pathlib.Path('/opt/homebrew/opt/llvm/bin')
FLAGS = r'(?:(?:reassoc|nnan|ninf|nsz|arcp|contract|afn|fast)\s+)*'
FP = r'(?:double|float|half|bfloat|fp128|x86_fp80|<\d+ x (?:double|float|half)>)'


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mark(source):
    # LLVM's documented fast flag is the union of all seven FP permissions.
    # https://llvm.org/docs/LangRef.html#fast-math-flags
    # This intentionally tests broad unsafe semantics, including comparisons;
    # it does not assert that their preconditions hold in the renderer.
    counts = collections.Counter()
    lines = []
    selector = os.environ.get('MATH_KERNEL')
    selected = False
    functions = []
    for line in source.splitlines(True):
        if selector:
            if line.startswith('define '):
                selected = selector in line.split('(', 1)[0]
                if selected:
                    functions.append(line.split('(', 1)[0])
            if not selected or not re.match(r'^\s*%.*?=\s*(?:fadd|fmul)\b', line):
                lines.append(line)
                continue
            pattern = r'\b(fadd|fmul)\s+' + FLAGS
            def replace_kernel(match):
                counts[match[1]] += 1
                return match[1] + ' reassoc '
            lines.append(re.sub(pattern, replace_kernel, line, count=1))
            continue
        if re.match(r'^\s*%.*?=\s*(?:fadd|fsub|fmul|fdiv|frem|fneg|fcmp|fptrunc|fpext)\b', line):
            pattern = r'\b(fadd|fsub|fmul|fdiv|frem|fneg|fcmp|fptrunc|fpext)\s+' + FLAGS
        elif re.match(r'^\s*%.*?=\s*(?:(?:tail|musttail|notail)\s+)?(?:call|invoke)\s+' + FLAGS + FP + r'\s', line):
            pattern = r'\b(call|invoke)\s+' + FLAGS
        elif re.match(r'^\s*%.*?=\s*phi\s+' + FLAGS + FP + r'\s', line):
            pattern = r'\b(phi)\s+' + FLAGS
        elif re.match(r'^\s*%.*?=\s*select\s+', line) and re.search(r',\s*' + FP + r'\s', line):
            pattern = r'\b(select)\s+' + FLAGS
        else:
            lines.append(line)
            continue
        def replace(match):
            counts[match[1]] += 1
            return match[1] + ' fast '
        lines.append(re.sub(pattern, replace, line, count=1))
    if selector:
        assert len(functions) == 1 and counts, (functions, counts)
        (OUT / (os.environ.get('MATH_AUDIT_PREFIX', '') + 'selected-functions.json')).write_text(json.dumps(functions, indent=2) + '\n')
    return ''.join(lines), dict(counts)


def rust_lld():
    sysroot = pathlib.Path(subprocess.check_output(['rustc', '--print', 'sysroot'], text=True).strip())
    host = next(s.split(': ', 1)[1] for s in subprocess.check_output(['rustc', '-Vv'], text=True).splitlines() if s.startswith('host:'))
    return sysroot / 'lib/rustlib' / host / 'bin/rust-lld'


def optimize(label, source):
    src = OUT / f'{label}-input.ll'
    if label == 'fast':
        text, counts = mark(source.read_text())
        src.write_text(text)
        (OUT / 'fast-flags.json').write_text(json.dumps(counts, indent=2) + '\n')
    else:
        shutil.copyfile(source, src)
    opt = OUT / f'{label}-optimized.ll'
    obj = OUT / f'{label}.o'
    run([LLVM / 'opt', '-passes=default<O3>', '-S', src, '-o', opt])
    run([LLVM / 'llc', '-O3', '-filetype=obj', opt, '-o', obj])
    return obj


def link(label, args=None):
    if args is not None:
        # Preserve rustc's complete link inputs, including temporary symbol objects.
        saved = OUT / 'link-inputs'
        saved.mkdir(exist_ok=True)
        mapped = []
        for arg in args:
            path = pathlib.Path(arg)
            if path.is_file() and path.suffix in ['.o', '.rlib', '.a']:
                dst = saved / path.name
                shutil.copyfile(path, dst)
                mapped.append(str(dst))
            else:
                mapped.append(arg)
        (OUT / 'link-args.json').write_text(json.dumps(mapped, indent=2) + '\n')
        sources = list((OUT / 'target/wasm32-unknown-unknown/release/deps').glob('font_wasm.ll'))
        assert len(sources) == 1, sources
        shutil.copyfile(sources[0], OUT / 'merged.ll')
    else:
        mapped = json.loads((OUT / 'link-args.json').read_text())
    objects = [i for i, a in enumerate(mapped) if pathlib.Path(a).suffix == '.o' and 'font_wasm' in pathlib.Path(a).name and 'symbols' not in a]
    assert len(objects) == 1, [mapped[i] for i in objects]
    mapped[objects[0]] = str(optimize(label, OUT / 'merged.ll'))
    if args is None:
        mapped[mapped.index('-o') + 1] = str(OUT / f'linked-{label}.wasm')
    run([rust_lld(), *([] if '-flavor' in mapped else ['-flavor', 'wasm']), *mapped])
    produced = pathlib.Path(mapped[mapped.index('-o') + 1])
    if args is not None:
        shutil.copyfile(produced, OUT / f'linked-{label}.wasm')


def package(label):
    bindgen = os.environ.get('WASM_BINDGEN', '/tmp/font-generator-wasm-tools/bin/wasm-bindgen')
    for kind in ['web', 'nodejs']:
        dst = OUT / f'pkg-{kind}-{label}'
        assert not dst.exists(), 'Preserve frozen packages.'
        run([bindgen, '--target', kind, '--out-name', 'font_wasm', '--out-dir', dst, OUT / f'linked-{label}.wasm'])
        for name in ['LICENSE-FreeType.txt', 'LICENSE-Skrifa-scan.txt']:
            shutil.copyfile(OUT / 'pkg-web-app' / name, dst / name)
        if kind == 'nodejs':
            (dst / 'package.json').write_text('{"type":"commonjs"}\n')
    wasm = OUT / f'pkg-web-{label}/font_wasm_bg.wasm'
    identity = {'label': label, 'wasm_sha': sha(wasm), 'bytes': wasm.stat().st_size,
                'merged_ir_sha': sha(OUT / 'merged.ll'),
                'optimizer': subprocess.check_output([LLVM / 'opt', '--version'], text=True).splitlines()[0]}
    assert wasm.read_bytes() == (OUT / f'pkg-nodejs-{label}/font_wasm_bg.wasm').read_bytes()
    (OUT / f'identity-{label}.json').write_text(json.dumps(identity, indent=2) + '\n')
    print(json.dumps(identity))


def build(label):
    assert label in ['strict', 'fast']
    for kind in ['web', 'nodejs']:
        assert not (OUT / f'pkg-{kind}-{label}').exists(), 'Preserve frozen packages.'
    if label == 'strict':
        wrapper = OUT / 'linker.py'
        wrapper.write_text('#!/usr/bin/env python3\nimport runpy,sys\nsys.argv.insert(1,"link")\nrunpy.run_path(' + repr(str(pathlib.Path(__file__).resolve())) + ',run_name="__main__")\n')
        wrapper.chmod(0o755)
        env = dict(os.environ)
        env.pop('RUSTFLAGS', None)
        env.pop('CARGO_ENCODED_RUSTFLAGS', None)
        env['CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUSTFLAGS'] = '-Ctarget-feature=+simd128 -Cembed-bitcode=yes -Cno-prepopulate-passes'
        env['PATH'] = str(LLVM) + ':' + env['PATH']
        subprocess.run(['cargo', 'rustc', '--locked', '--offline', '--release', '--target', 'wasm32-unknown-unknown',
                        '--manifest-path', str(SOURCE_ROOT / 'tools/wasm/Cargo.toml'), '--target-dir', str(OUT / 'target'),
                        '--features', 'preview', '--lib', '--crate-type', 'cdylib', '--', '-Clto=fat', '-Ccodegen-units=1',
                        '--emit=llvm-ir,obj,link', '-Clinker-flavor=wasm-ld', '-Clinker=' + str(wrapper)], env=env, check=True)
    else:
        link(label)
    package(label)


if __name__ == '__main__':
    if sys.argv[1] == 'link':
        link('strict', sys.argv[2:])
    else:
        build(sys.argv[1])
