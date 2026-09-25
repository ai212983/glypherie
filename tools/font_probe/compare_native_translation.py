"""B12 bounded numerical comparison: native TrueType op vs SCFS baseline."""
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from array import array as _array
from shamir_baseline_solver import evaluate_baseline, compile_baseline
from shamir_constraints import relation
from shamir_point_schedule import schedule
from shamir_prototype import push

SRC = [[100, 0], [500, 200], [300, 100], [100, 700]]
EM = 1000
TARGET, REF0, REF1 = 2, 0, 1
NORMALS = {'x': [1.0, 0.0], 'y': [0.0, 1.0], 'oblique': [0.6, 0.8]}
PPEMS = [14, 16, 20, 125]
PARAM_ABS, PARAM_DIST = 73, 91
SIGNED_PARAMS = [-4, 0, 4]
KINDS = ['Abs', 'PAbs', 'Dist', 'PDist', 'Ratio']
MS = 'https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions'
EXPECTED_MATRIX = 114


def q14(n):
    return [int(round(float(v) * 16384)) for v in n]


def fixture_bytes(points, asm, cvt_vals):
    b = FontBuilder(EM, isTTF=True)
    b.setupGlyphOrder(['.notdef', 'A'])
    b.setupCharacterMap({65: 'A'})
    pen = TTGlyphPen(None)
    pen.moveTo(tuple(points[0]))
    for p in points[1:]:
        pen.lineTo(tuple(p))
    pen.closePath()
    b.setupGlyf({'A': pen.glyph(), '.notdef': TTGlyphPen(None).glyph()})
    b.setupHorizontalMetrics({'A': (600, int(min(p[0] for p in points))), '.notdef': (600, 0)})
    b.setupHorizontalHeader(ascent=800, descent=-200)
    b.setupNameTable({'familyName': 'T', 'styleName': 'R', 'uniqueFontIdentifier': 'T',
                      'fullName': 'T R', 'psName': 'T-R'})
    b.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    b.setupPost()
    b.setupMaxp()
    f = b.font
    cvt = newTable('cvt ')
    cvt.values = _array('h', [int(v) for v in cvt_vals])
    f['cvt '] = cvt
    g = f['glyf']['A']
    g.coordinates = GlyphCoordinates(points)
    prog = Program()
    prog.fromAssembly(asm)
    g.program = prog
    f['maxp'].maxStackElements = 64
    # Storage slots 0..13 back the opt-in direct lowering (harmless otherwise).
    f['maxp'].maxStorage = max(int(f['maxp'].maxStorage or 0), 16)
    f['maxp'].maxSizeOfInstructions = max(f['maxp'].maxSizeOfInstructions, len(prog.getBytecode()))
    import io
    buf = io.BytesIO()
    f.save(buf)
    return buf.getvalue()


def run_ft_raw(points, asm, ppem, cvt_vals):
    import tempfile
    data = fixture_bytes(points, asm, cvt_vals)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'f.ttf'
        path.write_bytes(data)
        face = ft.Face(str(path))
        face.set_pixel_sizes(0, ppem)
        face.load_char('A', ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_NO_AUTOHINT |
                       ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_PEDANTIC)
        raw = np.asarray(face.glyph.outline.points, dtype=np.int64)
        return raw, (raw / 64.0).tolist(), data


def state_asm():
    return (['RTG[ ]'] + push(32767) + ['SCVTCI[ ]'] + push(0) + ['SSWCI[ ]']
            + push(0) + ['SSW[ ]'] + push(0) + ['SMD[ ]'] + ['FLIPOFF[ ]'])


def vec_asm(n):
    q = q14(n)
    return push(*q) + ['SPVFS[ ]'] + push(*q) + ['SFVFS[ ]'], q


def ref_move_asm(ppem, src):
    scale = ppem / EM
    asm, declared = [], {}
    for r, off in ((REF0, (1.0, 0.0)), (REF1, (0.0, 1.0))):
        for axis in (0, 1):
            asm.append('SVTCA[1]' if axis == 0 else 'SVTCA[0]')
            asm += push(r, int(round((src[r][axis] * scale + off[axis]) * 64))) + ['SCFS[ ]']
        declared[r] = (src[r][0] * scale + off[0], src[r][1] * scale + off[1])
    return asm, declared


def target_op_asm(kind, rounded, cvt_idx=0, mirp_flag=None):
    asm, extra = [], {}
    if kind in ('Abs', 'PAbs'):
        op = 'MDAP[%d]' % (1 if rounded else 0) if kind == 'Abs' else 'MIAP[%d]' % (1 if rounded else 0)
        asm += push(TARGET, cvt_idx) + [op] if kind == 'PAbs' else push(TARGET) + [op]
        extra = {'cvt': cvt_idx if kind == 'PAbs' else None}
    elif kind in ('Dist', 'PDist'):
        flag = mirp_flag or ('00100' if rounded else '00000')
        op = 'MDRP[%s]' % flag if kind == 'Dist' else 'MIRP[%s]' % flag
        asm += push(REF0) + ['SRP0[ ]']
        asm += push(TARGET, cvt_idx) + [op] if kind == 'PDist' else push(TARGET) + [op]
        extra = {'cvt': cvt_idx if kind == 'PDist' else None}
    else:
        asm += push(REF0) + ['SRP1[ ]'] + push(REF1) + ['SRP2[ ]'] + push(TARGET) + ['IP[ ]']
    return asm, extra


def build_graph(kind, n, rounded, src, declared_fu, cvt_val=None):
    n = np.asarray(n, float)
    perp = np.array([-n[1], n[0]])
    pts = np.asarray(src, float)
    if kind == 'Abs':
        val = float(pts[TARGET] @ n)
    elif kind == 'PAbs':
        val = float(cvt_val)
    elif kind == 'Dist':
        val = float((pts[TARGET] - pts[REF0]) @ n)
    elif kind == 'PDist':
        val = float(cvt_val)
    else:
        a, b = pts[REF0] @ n, pts[REF1] @ n
        val = float(((pts[TARGET] @ n) - a) / (b - a)) if b != a else 0.0
    chosen = {}
    for r in (REF0, REF1):
        chosen.setdefault(r, []).append(relation('Abs', r, [1, 0], value=float(declared_fu[r][0]), round=False, id=100 + 2 * r))
        chosen.setdefault(r, []).append(relation('Abs', r, [0, 1], value=float(declared_fu[r][1]), round=False, id=101 + 2 * r))
    tgt = [relation(kind, TARGET, n,
                    sources=[] if kind in ('Abs', 'PAbs') else [REF0] if kind in ('Dist', 'PDist') else [REF0, REF1],
                    value=val, round=rounded if kind != 'Ratio' else False, id=1)]
    tgt.append(relation('Abs', TARGET, perp, value=float(pts[TARGET] @ perp), round=False, id=2))
    chosen[TARGET] = tgt
    for p in range(len(pts)):
        if p in chosen:
            continue
        chosen[p] = [relation('Abs', p, [1, 0], value=float(pts[p][0]), round=False, id=200 + 2 * p),
                     relation('Abs', p, [0, 1], value=float(pts[p][1]), round=False, id=201 + 2 * p)]
    return schedule(np.asarray(src, float), chosen, [], []), val


def one_case(kind, nname, ppem, rounded, param=None):
    n = NORMALS[nname]
    src = [list(map(float, p)) for p in SRC]
    scale = ppem / EM
    cvt_val = param if kind in ('PAbs', 'PDist') else None
    cvt = [32766, int(cvt_val or 0)]
    cvt_idx = 1 if kind in ('PAbs', 'PDist') else 0
    vasm, q = vec_asm(n)
    rasm, declared_px = ref_move_asm(ppem, src)
    declared_fu = {r: (declared_px[r][0] / scale, declared_px[r][1] / scale) for r in declared_px}
    tasm, extra = target_op_asm(kind, rounded, cvt_idx)
    native_asm = state_asm() + vasm + ['SVTCA[1]', 'SVTCA[0]'] + rasm + vasm + tasm
    graph, relval = build_graph(kind, n, rounded, src, declared_fu, cvt_val)
    ideal, _ = evaluate_baseline(graph, np.asarray(src, float), ppem, EM)
    scfs_asm, _ = compile_baseline(graph, np.asarray(src, float), ppem, EM)
    native_raw = scfs_raw = None
    native_data = scfs_data = None
    native_error = scfs_error = None
    try:
        native_raw, native_px_all, native_data = run_ft_raw(src, native_asm, ppem, cvt)
    except Exception as e:
        native_error = '%s: %s' % (type(e).__name__, e)
    try:
        scfs_cvt = [int(cvt_val or 0)] if kind in ('PAbs', 'PDist') else cvt
        scfs_raw, scfs_px_all, scfs_data = run_ft_raw(src, scfs_asm, ppem, scfs_cvt)
        _, meta = evaluate_baseline(graph, np.asarray(src, float), ppem, EM)
        expect_raw = np.rint(np.asarray(meta['native_points_px']) * 64).astype(np.int64)
        inv_ok = bool(np.array_equal(np.asarray(scfs_raw, dtype=np.int64), expect_raw))
    except Exception as e:
        scfs_error = '%s: %s' % (type(e).__name__, e)
        inv_ok = False
    native_pt = (np.asarray(native_raw)[TARGET] / 64.0).tolist() if native_raw is not None else None
    scfs_pt = (np.asarray(scfs_raw)[TARGET] / 64.0).tolist() if scfs_raw is not None else None
    delta = float(max(abs(native_pt[0] - scfs_pt[0]), abs(native_pt[1] - scfs_pt[1]))) if native_pt and scfs_pt else None
    return dict(kind=kind, normal=nname, n=n, qvec=q, ppem=ppem, scale=scale, rounded=rounded,
                relation_value=relval, source=src, declared_ref_targets_px={str(k): list(v) for k, v in declared_px.items()},
                state=dict(RTG=True, SCVTCI=32767, SSWCI=0, SSW=0, SMD=0, FLIPOFF=True,
                           flags='00100' if rounded and kind in ('Dist', 'PDist') else '00000' if kind in ('Dist', 'PDist') else (1 if rounded else 0)),
                cvt=cvt, cvt_index=cvt_idx, native_assembly=native_asm, scfs_assembly=scfs_asm,
                opcode=native_asm[-1], ideal_target_px=np.asarray(ideal).tolist()[TARGET],
                scfs_target_px=scfs_pt, native_target_px=native_pt,
                max_delta_px=delta, exact_match=bool(delta == 0.0),
                within_1_64px=bool(delta is not None and delta <= 1 / 64 + 1e-12),
                native_error=native_error, scfs_error=scfs_error, scfs_invariant_ok=inv_ok,
                _native_data=native_data, _scfs_data=scfs_data)


def flag_rp0_sequence(mirp_flag):
    # SAME initial state (SMD0: minimum-distance test inactive), then reference
    # setup, then vectors, then MIRP target with the given flag, then ALIGNRP
    # follower point 3 to expose rp0 update.
    src = [list(map(float, p)) for p in SRC]
    ppem, n = 125, NORMALS['x']
    vasm, _ = vec_asm(n)
    rasm, _ = ref_move_asm(ppem, src)
    asm = (state_asm() + rasm + vasm
           + push(REF0) + ['SRP0[ ]'] + push(TARGET, 1) + ['MIRP[%s]' % mirp_flag]
           + push(3) + ['ALIGNRP[ ]'])
    raw, px, _ = run_ft_raw(src, asm, ppem, [32766, PARAM_DIST])
    return {'flag': mirp_flag, 'target_px': px[TARGET], 'follower_px': px[3], 'ref0_px': px[REF0]}


def flag_comparison():
    a = flag_rp0_sequence('11101')
    b = flag_rp0_sequence('00100')
    import math
    dist = math.dist(a['follower_px'], b['follower_px'])
    return {'11101': a, '00100': b, 'follower_distance_px': dist,
            'note': ('paper Fig.9 uses MIRP[11101]; harness 00100/00000 isolate the rounding '
                     'relation only and are NOT a Fig.9 reproduction (initial graphics state '
                     'unspecified). SMD0 leaves the minimum-distance test inactive; the flags '
                     'differ in rp0 update, minimum-distance handling, and distance-type/engine '
                     'compensation. '
                     'ALIGNRP point3 follows the moved target only when rp0 was updated (11101).')}


def unsupported_examples():
    return [dict(case='Abs value differs source/current projection', kind='Abs',
                 reason='MDAP rounds CURRENT point; cannot carry arbitrary v', target_relation='Abs target=current, not authored'),
            dict(case='Dist authored value differs source original distance', kind='Dist',
                 reason='MDRP measures ORIGINAL distance to rp0, not authored d', target_relation='Dist to ref0=original'),
            dict(case='Ratio authored t differs source geometry', kind='Ratio',
                 reason='IP uses original ratio of refs0/1; authored t unrepresentable', target_relation='Ratio refs0/1=original t'),
            dict(case='PRatio has no mapping', kind='PRatio',
                 reason='no literal Table I parameterised-ratio op', target_relation='none')]


def file_hash(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    out = Path(a.output)
    if out.exists() and any(out.iterdir() if out.is_dir() else [out]):
        sys.exit('refusing to overwrite non-empty output: %s' % out)
    out.mkdir(parents=True, exist_ok=True)
    cases = []
    for kind in KINDS:
        for nname in NORMALS:
            for ppem in PPEMS:
                for rounded in ([True, False] if kind != 'Ratio' else [False]):
                    param = PARAM_ABS if kind == 'PAbs' else PARAM_DIST if kind == 'PDist' else None
                    cases.append((kind, nname, ppem, rounded, param))
    for p in SIGNED_PARAMS:
        cases.append(('PAbs', 'x', 125, True, p))
        cases.append(('PDist', 'x', 125, True, p))
    assert len(cases) == EXPECTED_MATRIX, len(cases)
    results = []
    for i, (kind, nname, ppem, rounded, param) in enumerate(cases):
        r = one_case(kind, nname, ppem, rounded, param)
        r['id'] = 'c%03d' % i
        (out / ('%s.native.asm' % r['id'])).write_text('\n'.join(r['native_assembly']))
        (out / ('%s.scfs.asm' % r['id'])).write_text('\n'.join(r['scfs_assembly']))
        native_data = r.pop('_native_data')
        scfs_data = r.pop('_scfs_data')
        if native_data is not None:
            (out / ('%s.native.ttf' % r['id'])).write_bytes(native_data)
        if scfs_data is not None:
            (out / ('%s.scfs.ttf' % r['id'])).write_bytes(scfs_data)
        names = ['native.asm', 'scfs.asm']
        if native_data is not None:
            names.append('native.ttf')
        if scfs_data is not None:
            names.append('scfs.ttf')
        r['artifacts'] = {k: file_hash(out / ('%s.%s' % (r['id'], k))) for k in names}
        results.append(r)
    try:
        flags = flag_comparison()
    except Exception as e:
        flags = {'error': '%s: %s' % (type(e).__name__, e)}
    (out / 'flag-comparison.json').write_text(json.dumps(flags, indent=1))
    diffs = sum(1 for r in results if r['max_delta_px'] not in (None, 0.0))
    nerrs = sum(1 for r in results if r['native_error'])
    serrs = sum(1 for r in results if r['scfs_error'])
    inv_fail = sum(1 for r in results if not r['scfs_invariant_ok'])
    try:
        ft_ver = list(ft.version())
    except Exception:
        ft_ver = 'unknown'
    here = Path(__file__).parent
    flag_error = bool(isinstance(flags, dict) and 'error' in flags)
    report = dict(ms_table1=MS, ft_version=ft_ver,
                  precision_scope=('float64 end-quantization of the SCFS baseline vs native '
                                   'per-step instruction quantization; no visual/full-graph claim'),
                  input_hash=hashlib.sha256(json.dumps(SRC).encode()).hexdigest(),
                  code_hash=file_hash(__file__),
                  solver_hash=file_hash(here / 'shamir_baseline_solver.py'),
                  schedule_hash=file_hash(here / 'shamir_point_schedule.py'),
                  constraints_hash=file_hash(here / 'shamir_constraints.py'),
                  counts=dict(cases=len(results), expected=EXPECTED_MATRIX, differences=diffs,
                              native_errors=nerrs, scfs_errors=serrs, scfs_invariant_failures=inv_fail,
                              flag_error=flag_error),
                  verification_passed=bool(nerrs == 0 and serrs == 0 and inv_fail == 0 and not flag_error
                                            and len(results) == EXPECTED_MATRIX),
                  unsupported=unsupported_examples(), flag_comparison=flags, cases=results)
    (out / 'report.json').write_text(json.dumps(report, indent=1))
    print(json.dumps(report['counts']))
    if not report['verification_passed']:
        sys.exit(1)


if __name__ == '__main__':
    main()
