"""Literal native dependency chains; no compiler/model changes.

Compare current 26.6 point reads with an explicitly separate Q14 storage
experiment. UPM=ppem=1000 isolates arithmetic, not scalable font generation.
Sources and exact rational expectations are recorded alongside each fixture.
"""
import argparse
import hashlib
import io
import json
from fractions import Fraction
from pathlib import Path

import freetype as ft
from fontTools.ttLib import TTFont
from compare_native_translation import fixture_bytes
from shamir_constraints import push_integer

PROBE = Path(__file__).resolve().parent
ROOT = PROBE.parent.parent
MS = 'https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions'
FT = 'https://github.com/freetype/freetype/blob/VER-2-13-2/src/truetype/ttinterp.c'


def push(*values):
    return [op for value in values for op in push_integer(value)]


def nearest(value):
    """Exact rational half-away rounding, independent of native execution."""
    return (-1 if value < 0 else 1) * ((abs(value).numerator * 2
            + abs(value).denominator) // (2 * abs(value).denominator))


def fixture(n, d, sign, mode):
    points = [[sign * x, y] for x, y in
              [(0, 0), (d, 0), (n, 1), (n+1, 2), (n+3, 3),
               (5, 4), (6, 5), (7, 6)]]
    # Move endpoints to 0 and +/-1px; IP derives the parent from original n/d.
    asm = push(1) + ['SZPS[ ]', 'SVTCA[1]']
    asm += push(0, 0) + ['SCFS[ ]'] + push(1, sign*64) + ['SCFS[ ]']
    asm += push(0) + ['SRP1[ ]'] + push(1) + ['SRP2[ ]']
    asm += push(2) + ['IP[ ]']
    # Expose current and original parent reads in auxiliary points.
    asm += push(5, 2) + ['GC[0]', 'SCFS[ ]']
    asm += push(6, 2) + ['GC[1]', 'SCFS[ ]']
    p6 = nearest(Fraction(sign*n*64, d))
    if mode == 'align':
        asm += push(2) + ['SRP0[ ]'] + push(3) + ['ALIGNRP[ ]']
        asm += push(3) + ['SRP0[ ]'] + push(4) + ['ALIGNRP[ ]']
        axis, expected = 0, [p6, p6]
    elif mode == 'distance':
        asm += push(2) + ['SRP0[ ]'] + push(3) + ['MDRP[10000]']
        asm += push(4) + ['MDRP[10000]']
        axis, expected = 0, [p6+sign*64, p6+sign*192]
    else:
        if mode == 'current-amplified':
            asm += push(2) + ['GC[0]'] + push(20*64) + ['MUL[ ]']
            child = p6*20
        else:
            # A deliberate alternative: derive and retain a latent Q14 parent.
            # This value is NOT returned by GC from the physically placed parent.
            asm += push(sign*n*16384, d*64) + ['DIV[ ]']
            asm += push(0) + ['SWAP[ ]', 'WS[ ]']
            asm += push(7, 0) + ['RS[ ]', 'SCFS[ ]']
            asm += push(0) + ['RS[ ]'] + push(20*64) + ['MUL[ ]']
            asm += ['DUP[ ]', 'ABS[ ]'] + push(128) + ['ADD[ ]']
            asm += push(16384) + ['DIV[ ]', 'SWAP[ ]'] + push(0)
            asm += ['LT[ ]', 'IF[ ]', 'NEG[ ]', 'EIF[ ]']
            latent = sign * (n*16384 // d)
            child = nearest(Fraction(latent*20, 256))
        asm += ['SVTCA[0]'] + push(3) + ['SWAP[ ]', 'SCFS[ ]']
        asm += push(3) + ['SRP0[ ]'] + push(4) + ['ALIGNRP[ ]']
        axis, expected = 1, [child, child]
    font = TTFont(io.BytesIO(fixture_bytes(points, asm, [0])), recalcTimestamp=False)
    font['maxp'].maxStorage = 1
    buf = io.BytesIO()
    font.save(buf)
    data = buf.getvalue()
    face = ft.Face(io.BytesIO(data))
    face.set_pixel_sizes(0, 1000)
    face.load_char('A', ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_NO_AUTOHINT
                   | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_PEDANTIC)
    raw = [list(p) for p in face.glyph.outline.points]
    assert len(raw) == 8, raw
    assert raw[2][0] == raw[5][0] == p6, raw
    assert raw[6][0] == sign*n*64, raw
    assert [raw[3][axis], raw[4][axis]] == expected, raw
    if mode == 'stored-amplified':
        assert raw[7][0] == latent, raw
    return dict(n=n, d=d, sign=sign, mode=mode, parent_q6=p6,
                current_read_q6=raw[5][0], original_read_q6=raw[6][0],
                child_q6=raw[3][axis], grandchild_q6=raw[4][axis],
                expected_child_grandchild_q6=expected,
                ideal_amplified_q6=nearest(Fraction(sign*n*20*64, d)),
                raw_points=raw), asm, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='out/parent-precision-v1')
    out = PROBE / ap.parse_args().output
    if out.exists():
        raise SystemExit('Output exists; choose a fresh directory')
    out.mkdir(parents=True)
    rows, failures = [], []
    for n, d in [(1, 3), (2, 3), (1, 2)]:
        for sign in (-1, 1):
            for mode in ['align', 'distance', 'current-amplified', 'stored-amplified']:
                name = f'{n}-{d}-{sign}-{mode}'
                try:
                    row, asm, data = fixture(n, d, sign, mode)
                    rows.append(row)
                    (out / (name+'.ttf')).write_bytes(data)
                    (out / (name+'.asm.txt')).write_text('\n'.join(asm)+'\n')
                except Exception as exc:
                    failures.append(dict(case=name, error=str(exc)))
    inputs = [Path(__file__), PROBE/'compare_native_translation.py',
              PROBE/'shamir_constraints.py', PROBE/'shamir_prototype.py']
    report = dict(expected=24, passed=len(rows), failures=failures,
                  complete=len(rows)==24 and not failures, cases=rows,
                  freetype_version=ft.version(), sources=[MS, FT],
                  scope='Literal 1:1 dependency fixtures, not font-wide conformance',
                  hashes={str(p.resolve().relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in inputs})
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ['expected', 'passed', 'complete', 'failures']}))
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
