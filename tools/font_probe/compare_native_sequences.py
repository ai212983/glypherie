"""Runner: native vs independent hand-authored reference vs SCFS (owned by this task).

Reference programs are literal per-fixture assemblies keyed ONLY by fixture key
(never built from compiler metadata). Native programs come from compile_native.
Both run through actual FreeType at 5 ppems; SCFS via compile_baseline.
"""
import argparse
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np

from compare_native_translation import fixture_bytes, run_ft_raw
from shamir_baseline_solver import compile_baseline, evaluate_baseline
from shamir_constraints import relation
from shamir_native_translation import UnsupportedNativeTranslation, compile_native
from shamir_point_schedule import schedule
from shamir_prototype import push

EM = 1000
PPEMS = [14, 16, 18, 20, 125]
SRC = [[100, 0], [500, 200], [300, 100], [100, 700]]
MS = "https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions"
VTT = "VTT pinned 1bd4ed4383f8390b0140e05d330491fcadd3e8e0 TTGenerator.cpp"
X = [1.0, 0.0]
Y = [0.0, 1.0]
N = [0.6, 0.8]
N2 = [-0.8, 0.6]
F = [0.8, -0.6]


def q14(v):
    return [int(round(float(a) * 16384)) for a in v]


def vec(n, f):
    return push(*q14(n)) + ["SPVFS[ ]"] + push(*q14(f)) + ["SFVFS[ ]"]


def state():
    return (push(1) + ["SZPS[ ]"] + push(1) + ["SLOOP[ ]"] + ["RTG[ ]"]
            + push(32767) + ["SCVTCI[ ]"] + push(0) + ["SSWCI[ ]"]
            + push(0) + ["SSW[ ]"] + push(0) + ["SMD[ ]", "FLIPOFF[ ]"])


def miap(p, idx, rnd=True):
    return push(p, idx) + ["MIAP[%d]" % (1 if rnd else 0)]


def mdap(p, rnd=False):
    return push(p) + ["MDAP[%d]" % (1 if rnd else 0)]


def mirp(src, p, idx, rnd=True):
    return push(src) + ["SRP0[ ]"] + push(p, idx) + ["MIRP[%s]" % ("10100" if rnd else "10000")]


def mdrp(src, p, rnd=False):
    return push(src) + ["SRP0[ ]"] + push(p) + ["MDRP[%s]" % ("10100" if rnd else "10000")]


def alignrp(src, p):
    return push(src) + ["SRP0[ ]"] + push(p) + ["ALIGNRP[ ]"]


def ip(a, b, p):
    return push(a) + ["SRP1[ ]"] + push(b) + ["SRP2[ ]"] + push(p) + ["IP[ ]"]


def svtca(axis):
    return ["SVTCA[%d]" % (1 if axis == 0 else 0)]


def ref_cardinal_chain():
    cvt = [200, 100, 250, 300]
    a = state()
    a += svtca(0) + miap(0, 0) + svtca(1) + miap(0, 1)
    a += svtca(0) + mirp(0, 1, 2) + svtca(1) + miap(1, 3)
    a += svtca(0) + mdrp(1, 2) + alignrp(0, 3)
    return a, cvt


def ref_paired():
    cvt = [200, 250]
    a = state() + vec(X, F) + miap(2, 0) + vec(N, Y) + miap(2, 1)
    return a, cvt


def ref_swapped():
    cvt = [250, 200]
    a = state() + vec(N, Y) + miap(2, 0) + vec(X, F) + miap(2, 1)
    return a, cvt


def ref_rotated():
    cvt = [200, 150]
    a = state() + vec(N, N) + miap(2, 0) + vec(N2, N2) + miap(2, 1)
    return a, cvt


def ref_ratio_mid():
    cvt = [200, 600]
    return state() + svtca(0) + miap(0, 0) + svtca(0) + miap(1, 1) + svtca(0) + ip(0, 1, 2), cvt


def ref_ratio_extrap():
    cvt = [100, 300]
    return state() + svtca(1) + miap(0, 0) + svtca(1) + miap(1, 1) + svtca(1) + ip(0, 1, 3), cvt


def ref_signed():
    cvt = [-4]
    return state() + svtca(0) + miap(0, 0) + svtca(0) + mirp(0, 1, 0), cvt


def ref_source_round():
    a = state()
    for p in range(4):
        a += svtca(0) + mdap(p, True)
    for p in range(4):
        a += svtca(1) + mdap(p, True)
    return a, []


REFS = {
    "cardinal-chain": ref_cardinal_chain,
    "paired": ref_paired,
    "swapped-order": ref_swapped,
    "rotated": ref_rotated,
    "ratio-mid": ref_ratio_mid,
    "ratio-extrapolation": ref_ratio_extrap,
    "signed": ref_signed,
    "source-round": ref_source_round,
}


def other_abs(chosen, pts, skip=()):
    for i in range(len(pts)):
        if i in skip or i in chosen:
            continue
        chosen[i] = [relation("Abs", i, list(X), value=float(pts[i][0]), round=False, id=100 + 2 * i),
                     relation("Abs", i, list(Y), value=float(pts[i][1]), round=False, id=101 + 2 * i)]


def fixtures():
    P = np.asarray(SRC, float)
    out = []
    c = {0: [relation("PAbs", 0, list(X), value=200, round=True, id=1),
             relation("PAbs", 0, list(Y), value=100, round=True, id=2)],
         1: [relation("PDist", 1, list(X), sources=[0], value=250, round=True, id=3),
             relation("PAbs", 1, list(Y), value=300, round=True, id=4)],
         2: [relation("Dist", 2, list(X), sources=[1], value=float((P[2] - P[1]) @ np.array(X)), round=False, id=5),
             relation("Abs", 2, list(Y), value=float(P[2][1]), round=False, id=6)],
         3: [relation("Dist", 3, list(X), sources=[0], value=0.0, round=False, id=7),
             relation("Abs", 3, list(Y), value=float(P[3][1]), round=False, id=8)]}
    out.append(("cardinal-chain", SRC, c))
    c = {2: [relation("PAbs", 2, list(X), value=200, round=True, id=1),
             relation("PAbs", 2, list(N), value=250, round=True, id=2)]}
    other_abs(c, SRC); out.append(("paired", SRC, c))
    c = {2: [relation("PAbs", 2, list(N), value=250, round=True, id=1),
             relation("PAbs", 2, list(X), value=200, round=True, id=2)]}
    other_abs(c, SRC); out.append(("swapped-order", SRC, c))
    c = {2: [relation("PAbs", 2, list(N), value=200, round=True, id=1),
             relation("PAbs", 2, list(N2), value=150, round=True, id=2)]}
    other_abs(c, SRC); out.append(("rotated", SRC, c))
    c = {0: [relation("PAbs", 0, list(X), value=200, round=True, id=1),
             relation("Abs", 0, list(Y), value=float(P[0][1]), round=False, id=2)],
         1: [relation("PAbs", 1, list(X), value=600, round=True, id=3),
             relation("Abs", 1, list(Y), value=float(P[1][1]), round=False, id=4)],
         2: [relation("Ratio", 2, list(X), sources=[0, 1], value=0.5, round=False, id=5),
             relation("Abs", 2, list(Y), value=float(P[2][1]), round=False, id=6)]}
    other_abs(c, SRC); out.append(("ratio-mid", SRC, c))
    c = {0: [relation("Abs", 0, list(X), value=float(P[0][0]), round=False, id=1),
             relation("PAbs", 0, list(Y), value=100, round=True, id=2)],
         1: [relation("Abs", 1, list(X), value=float(P[1][0]), round=False, id=3),
             relation("PAbs", 1, list(Y), value=300, round=True, id=4)],
         3: [relation("Abs", 3, list(X), value=float(P[3][0]), round=False, id=5),
             relation("Ratio", 3, list(Y), sources=[0, 1], value=3.5, round=False, id=6)]}
    other_abs(c, SRC); out.append(("ratio-extrapolation", SRC, c))
    pts7 = [[-4, 0], [-8, 200], [300, 100], [100, 700]]
    P7 = np.asarray(pts7, float)
    c = {0: [relation("PAbs", 0, list(X), value=-4, round=True, id=1),
             relation("Abs", 0, list(Y), value=float(P7[0][1]), round=False, id=2)],
         1: [relation("PDist", 1, list(X), sources=[0], value=-4.0, round=True, id=3),
             relation("Abs", 1, list(Y), value=float(P7[1][1]), round=False, id=4)]}
    other_abs(c, pts7); out.append(("signed", pts7, c))
    c = {i: [relation("Abs", i, list(X), value=float(P[i][0]), round=True, id=10 + 2 * i),
             relation("Abs", i, list(Y), value=float(P[i][1]), round=True, id=11 + 2 * i)] for i in range(4)}
    out.append(("source-round", SRC, c))
    return out


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _code_hashes():
    names = ["shamir_native_translation.py", "compare_native_translation.py",
             "shamir_baseline_solver.py", "shamir_point_schedule.py",
             "shamir_constraints.py"]
    here = Path(__file__).resolve().parent
    return {n: _sha256_bytes((here / n).read_bytes()) for n in names}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    out = Path(a.output)
    if out.exists() and any(out.iterdir() if out.is_dir() else [out]):
        sys.exit("refusing to overwrite non-empty output: %s" % out)
    out.mkdir(parents=True, exist_ok=True)
    import freetype as ft
    try:
        ft_ver = list(ft.version())
    except Exception:
        ft_ver = "unknown"
    cases = []
    errors = []
    runner_hash = _sha256_bytes(Path(__file__).read_bytes())
    code_hashes = _code_hashes()

    def fail(fixture, phase, e, extra=None):
        rec = dict(fixture=fixture, phase=phase,
                   error="%s: %s" % (type(e).__name__, e))
        if extra:
            rec.update(extra)
        errors.append(rec)
        return rec

    for key, pts, chosen in fixtures():
        pts = [list(map(float, p)) for p in pts]
        ihash = _sha256_bytes(json.dumps(pts).encode())
        P = np.asarray(pts, float)
        case = dict(fixture=key, supported=True, input_hash=ihash)
        try:
            graph = schedule(P, {k: list(v) for k, v in chosen.items()}, [], [])
            nasm, nmeta = compile_native(graph, pts)
        except Exception as e:
            fail(key, "compile-native", e)
            case["supported"] = False
            case["ppem_rows"] = [dict(ppem=p, error="compile-native failed") for p in PPEMS]
            case["prefix_observation"] = []
            cases.append(case)
            continue
        try:
            rasm, rcvt = REFS[key]()
        except Exception as e:
            fail(key, "build-reference", e)
            case["supported"] = False
            case["ppem_rows"] = [dict(ppem=p, error="build-reference failed") for p in PPEMS]
            case["prefix_observation"] = []
            cases.append(case)
            continue
        ncvt = list(nmeta["cvt"])
        case["native_cvt"] = ncvt
        case["reference_cvt"] = list(rcvt)
        case["native_meta"] = nmeta
        (out / (key + ".native.asm")).write_text("\n".join(nasm))
        (out / (key + ".ref.asm")).write_text("\n".join(rasm))
        (out / (key + ".graph.json")).write_text(json.dumps(graph, indent=1, default=str))
        (out / (key + ".native.meta.json")).write_text(json.dumps(nmeta, indent=1, default=str))
        nbytes0 = fixture_bytes(pts, nasm, ncvt or [0])
        rbytes0 = fixture_bytes(pts, rasm, list(rcvt) or [0])
        (out / (key + ".native.ttf")).write_bytes(nbytes0)
        (out / (key + ".ref.ttf")).write_bytes(rbytes0)
        case["hashes"] = {
            "native_asm": _sha256_bytes("\n".join(nasm).encode()),
            "ref_asm": _sha256_bytes("\n".join(rasm).encode()),
            "graph": _sha256_bytes(json.dumps(graph, sort_keys=True, default=str).encode()),
            "native_meta": _sha256_bytes(json.dumps(nmeta, sort_keys=True, default=str).encode()),
            "native_ttf": _sha256_bytes(nbytes0),
            "ref_ttf": _sha256_bytes(rbytes0),
        }
        per = []
        for ppem in PPEMS:
            row = dict(ppem=ppem)
            try:
                nraw, _, _ = run_ft_raw(pts, nasm, ppem, ncvt or [0])
                rraw, _, _ = run_ft_raw(pts, rasm, ppem, list(rcvt) or [0])
                exact = bool(np.array_equal(np.asarray(nraw), np.asarray(rraw)))
                row["exact_native_vs_ref"] = exact
                row["native_raw"] = np.asarray(nraw).tolist()
                row["ref_raw"] = np.asarray(rraw).tolist()
                if not exact:
                    errors.append(dict(fixture=key, phase="mismatch-ppem-%d" % ppem,
                                       native=row["native_raw"], reference=row["ref_raw"]))
                try:
                    ideal, _ = evaluate_baseline(graph, P, ppem, EM)
                    row["ideal_px"] = np.asarray(ideal, float).tolist()
                except Exception as e:
                    row["ideal_error"] = "%s: %s" % (type(e).__name__, e)
                    fail(key, "baseline-ppem-%d" % ppem, e)
                sasm, _ = compile_baseline(graph, P, ppem, EM)
                (out / ("%s.scfs-%d.asm" % (key, ppem))).write_text("\n".join(sasm))
                sraw, _, sdata = run_ft_raw(pts, sasm, ppem, ncvt or [0])
                (out / ("%s.scfs-%d.ttf" % (key, ppem))).write_bytes(sdata)
                row["scfs_raw"] = np.asarray(sraw).tolist()
                row["max_native_scfs_delta_px"] = float(
                    np.abs(np.asarray(nraw, float) - np.asarray(sraw, float)).max() / 64.0)
                case["hashes"]["scfs-%d-asm" % ppem] = _sha256_bytes("\n".join(sasm).encode())
                case["hashes"]["scfs-%d-ttf" % ppem] = _sha256_bytes(sdata)
            except Exception as e:
                row["error"] = "%s: %s" % (type(e).__name__, e)
                errors.append(dict(fixture=key, phase="run-ppem-%d" % ppem, error=row["error"]))
            per.append(row)
        case["ppem_rows"] = per
        prefix = []
        ops = list(nmeta.get("operations", []))
        by_point = {}
        for o in ops:
            by_point.setdefault(o["point"], []).append(o)
        for p in sorted(by_point):
            pair = by_point[p]
            if len(pair) != 2:
                errors.append(dict(fixture=key, phase="prefix-point-%d" % p,
                                   error="expected exactly two native ops, saw %d" % len(pair)))
                continue
            o1, o2 = pair[0], pair[1]
            try:
                n1 = np.asarray(o1["normal_float"], float)
                nn = float(np.linalg.norm(n1))
                if not np.isfinite(nn) or nn == 0.0:
                    raise ValueError("degenerate first normal")
                n1 = n1 / nn
            except Exception as e:
                errors.append(dict(fixture=key, phase="prefix-point-%d" % p,
                                   error="%s: %s" % (type(e).__name__, e)))
                continue
            for ppem in PPEMS:
                obs = dict(point=p, ppem=ppem)
                try:
                    c1, _, _ = run_ft_raw(pts, nasm[:o1["assembly_end"]], ppem, ncvt or [0])
                    c2, _, _ = run_ft_raw(pts, nasm[:o2["assembly_end"]], ppem, ncvt or [0])
                    obs["first_px"] = (np.asarray(c1, float) / 64.0).tolist()[p]
                    obs["second_px"] = (np.asarray(c2, float) / 64.0).tolist()[p]
                    move = (np.asarray(c2, float) - np.asarray(c1, float))[p] / 64.0
                    obs["second_on_first_normal_px"] = float(move @ n1)
                except Exception as e:
                    obs["error"] = "%s: %s" % (type(e).__name__, e)
                    errors.append(dict(fixture=key, phase="prefix-ppem-%d-point-%d" % (ppem, p),
                                       error=obs["error"]))
                prefix.append(obs)
        for p in range(len(pts)):
            if p not in by_point:
                errors.append(dict(fixture=key, phase="prefix-point-%d" % p,
                                   error="no native ops recorded"))
        case["prefix_observation"] = prefix
        order_note = None
        if key == "swapped-order":
            order_note = "group order swapped vs paired; values identical; FT equality checked, not asserted blanket"
        case["order_note"] = order_note
        cases.append(case)
    total = sum(len(c.get("ppem_rows", [])) for c in cases)
    passed = (total == 40 and not errors
              and all(c.get("supported") for c in cases)
              and all(r.get("exact_native_vs_ref") for c in cases for r in c.get("ppem_rows", [])))
    report = dict(ms_table1=MS, vtt=VTT, ft_version=ft_ver, strict_freetype=True,
                  required_cases=40, actual_cases=total, verification_passed=bool(passed),
                  runner_hash=runner_hash, code_hashes=code_hashes,
                  cases=cases, unexpected_errors=errors)
    (out / "report.json").write_text(json.dumps(report, indent=1))
    buf = io.StringIO()
    with redirect_stdout(buf):
        print(json.dumps({c["fixture"]: [r.get("exact_native_vs_ref") for r in c.get("ppem_rows", [])] for c in cases}))
    sys.stdout.write(buf.getvalue())
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
