#!/usr/bin/env python3
"""Prepare a filtered solver in a frozen source copy; reuse the LLVM harness."""
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/diagnostics/selective-math-optimization'
SOURCE = OUT / 'source'

SOLVE = '''    fn solve(&self, b: &DVector<f64>) -> DVector<f64> {
        let Some((u, vt, values, tol)) = &self.factors else {
            return self.solve_ordered(b);
        };
        // Truncated modes retain the original solve. Rank selection and
        // division are strict; only two post-factorization products change.
        if values.iter().any(|s| !s.is_finite() || *s <= *tol) {
            return self.solve_ordered(b);
        }
        let mut coefficients = Vec::with_capacity(values.len());
        for (i, &s) in values.iter().enumerate() {
            let column = u.column(i);
            let Some(value) = bounded_dot(column.as_slice(), b.as_slice()) else {
                return self.solve_ordered(b);
            };
            let c = value / s;
            if !c.is_finite() {
                return self.solve_ordered(b);
            }
            coefficients.push(c);
        }
        let mut x = Vec::with_capacity(self.n);
        for j in 0..self.n {
            let column = vt.column(j);
            let Some(value) = bounded_dot(column.as_slice(), &coefficients) else {
                return self.solve_ordered(b);
            };
            x.push(value);
        }
        DVector::from_vec(x)
    }

'''


def prepare():
    assert not SOURCE.exists(), 'Preserve frozen experiment source.'
    for name in ['generator', 'wasm']:
        base = ROOT / 'crates' / name
        target = SOURCE / 'crates' / name
        target.mkdir(parents=True)
        for filename in ['Cargo.toml', 'Cargo.lock', 'build.rs']:
            if (base / filename).exists():
                shutil.copyfile(base / filename, target / filename)
        shutil.copytree(base / 'src', target / 'src')
        if (base / 'vendor').exists():
            shutil.copytree(base / 'vendor', target / 'vendor')
    qp = SOURCE / 'crates/generator/src/diagonal_fitting/qp.rs'
    original = qp.read_text()
    needle = '    fn solve(&self, b: &DVector<f64>) -> DVector<f64> {'
    assert original.count(needle) == 1
    changed = original.replace(needle, SOLVE + needle.replace('fn solve(', 'fn solve_ordered('))
    helper = (ROOT / 'experiments/wasm_timing/selective-dot.rs').read_text()
    qp.write_text(changed + '\n' + helper)
    prior = ROOT / 'out/diagnostics/fast-math-optimization'
    for kind in ['web', 'nodejs']:
        shutil.copytree(prior / f'pkg-{kind}-app', OUT / f'pkg-{kind}-app')
    (OUT / 'source-manifest.json').write_text(json.dumps({str(p.relative_to(SOURCE)):
        hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCE.rglob('*') if p.is_file()}, indent=2) + '\n')


def probe():
    # Exercise the actual reassociated kernel, not just a strict source test.
    source = '''#![no_std]
#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! { loop {} }
static mut INPUT: [f64; 512] = [0.0; 512];
#[no_mangle]
pub extern "C" fn input() -> *mut f64 { core::ptr::addr_of_mut!(INPUT).cast() }
#[no_mangle]
pub unsafe extern "C" fn bounded(a: *const f64, b: *const f64, n: usize) -> f64 {
    bounded_dot(core::slice::from_raw_parts(a,n), core::slice::from_raw_parts(b,n)).unwrap_or(f64::NAN)
}
#[no_mangle]
pub unsafe extern "C" fn proposal(a: *const f64, b: *const f64, n: usize) -> f64 {
    selective_dot_proposal(core::slice::from_raw_parts(a,n), core::slice::from_raw_parts(b,n))
}
#[no_mangle]
pub extern "C" fn witness(a: f64, b: f64) -> f64 { (a - (a+b)) + b }
'''
    source += (ROOT / 'experiments/wasm_timing/selective-dot.rs').read_text()
    (OUT / 'probe.rs').write_text(source)
    subprocess.run(['rustc', '--crate-type=cdylib', '--target=wasm32-unknown-unknown',
                    '-Ctarget-feature=+simd128', '-Copt-level=3', '-Clto=fat', '-Ccodegen-units=1',
                    '-Cpanic=abort', '-Cno-prepopulate-passes', '--emit=llvm-ir',
                    OUT / 'probe.rs', '-o', OUT / 'probe.ll'], check=True)
    spec = importlib.util.spec_from_file_location('math_build', ROOT / 'experiments/wasm_timing/fast-math.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    os.environ['MATH_KERNEL'] = 'selective_dot_proposal'
    os.environ['MATH_AUDIT_PREFIX'] = 'probe-'
    for label in ['probe-strict', 'probe-fast']:
        src = OUT / f'{label}-input.ll'
        ir = (OUT / 'probe.ll').read_text()
        if label.endswith('fast'):
            ir, counts = module.mark(ir)
            (OUT / 'probe-flags.json').write_text(json.dumps(counts) + '\n')
        src.write_text(ir)
        optimized = OUT / f'{label}-optimized.ll'
        obj = OUT / f'{label}.o'
        module.run([module.LLVM / 'opt', '-passes=default<O3>', '-S', src, '-o', optimized])
        module.run([module.LLVM / 'llc', '-O3', '-filetype=obj', optimized, '-o', obj])
        module.run([module.rust_lld(), '-flavor', 'wasm', '--no-entry', '--export-all', '--allow-undefined',
                    obj, '-o', OUT / f'{label}.wasm'])
    subprocess.run(['node', ROOT / 'experiments/wasm_timing/selective-probe.cjs', str(OUT)], check=True)
    # Fraction is an independent exact-rational oracle, including subnormals.
    from fractions import Fraction as F
    import struct
    def value(hexadecimal):
        return struct.unpack('<d', bytes.fromhex(hexadecimal))[0]
    data = json.loads((OUT / 'probe-results.json').read_text())
    accepted = 0
    for row in data['rows']:
        aa, bb = [[value(x) for x in row[k]] for k in ['a', 'b']]
        for label in ['strict', 'fast']:
            result = value(row[label]['bounded'])
            if not __import__('math').isfinite(result):
                continue
            accepted += 1
            a, b = [[F(x) for x in v] for v in [aa, bb]]
            exact = sum((x*y for x,y in zip(a,b)), F(0))
            n = len(a)
            u = F(1, 2**53)
            gamma = (2*n*u)/(1-2*n*u)
            bound = gamma*n*max(map(abs,a))*max(map(abs,b)) + 2*n*F(1,2**1074)
            assert abs(F(result)-exact) <= bound, row
            assert F(result)*exact > 0, row
    assert data['witness'] == {'strict': 2**-53, 'fast': 2**-53}
    (OUT / 'probe-summary.json').write_text(json.dumps({'cases': len(data['rows']),
        'accepted_checks': accepted, 'exact_error_bounds': 'passed', 'protected_compensation': 'passed',
        'known_abstentions': data['knownAbstentions']}, indent=2) + '\n')


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare()
    elif sys.argv[1] == 'probe':
        probe()
    else:
        assert sys.argv[1] in ['strict', 'fast']
        subprocess.run([sys.executable, ROOT / 'experiments/wasm_timing/fast-math.py', sys.argv[1]],
                       env={**os.environ, 'MATH_OUTPUT_DIR': str(OUT), 'MATH_SOURCE_ROOT': str(SOURCE),
                            'MATH_KERNEL': 'selective_dot_proposal'}, check=True)
