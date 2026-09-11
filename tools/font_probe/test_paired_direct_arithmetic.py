"""Focused tests for the isolated paired direct-arithmetic prototype.

Hand-derived expectations plus actual native (FreeType) results.  Run with
the project environment: `.venv/bin/python tools/font_probe/
test_paired_direct_arithmetic.py` (also pytest-compatible).
"""

import io
import json
import sys
import tempfile
from pathlib import Path

PROBE = Path(__file__).resolve().parent
sys.path.insert(0, str(PROBE))
ROOT = PROBE.parent.parent

from experiment_paired_direct_arithmetic import (  # noqa: E402
    Reject, cramer, div_ref, freeze_pair, half_away, main, mul_ref,
    push, push_integer, run_case, synthetics,
)

PASS = []


def check(name, cond, detail=""):
    assert cond, "%s: %s" % (name, detail)
    PASS.append((name, bool(cond), detail))
    print(("ok  " if cond else "FAIL") + " " + name
          + ("" if cond else " :: " + str(detail)))


def syn(name):
    return next(s for s in synthetics() if s["name"] == name)


def test_half_away_ties():
    check("half_away(2.5)==3", half_away(2.5) == 3, half_away(2.5))
    check("half_away(-2.5)==-3", half_away(-2.5) == -3, half_away(-2.5))
    check("half_away(-0.5)==-1", half_away(-0.5) == -1, half_away(-0.5))
    check("half_away(0.5)==1", half_away(0.5) == 1, half_away(0.5))
    check("half_away(1407.5942661671559*14/2048)==10",
          half_away(1407.5942661671559 * 14.0 / 2048.0) == 10,
          half_away(1407.5942661671559 * 14.0 / 2048.0))


def test_mul_div_reference_hand_table():
    # Hand-derived from the probed FreeType semantics: MUL rounds half away
    # from zero, DIV truncates toward zero.
    cases = [((100, 3), 5), ((-100, 3), -5), ((32, 1), 1), ((-32, 1), -1),
             ((96, 1), 2), ((-96, 1), -2), ((1, 1), 0), ((-1, 1), 0),
             ((63, 1), 1), ((-63, 1), -1), ((16384, 640), 163840)]
    for (a, b), want in cases:
        got = mul_ref(a, b)
        check("mul_ref(%d,%d)==%d" % (a, b, want), got == want, got)
    dcases = [((7, 2), 224), ((-7, 3), -149), ((7, 3), 149),
              ((-1, 128), 0), ((1, 128), 0), ((-16385, 16384), -64)]
    for (a, b), want in dcases:
        got = div_ref(a, b)
        check("div_ref(%d,%d)==%d" % (a, b, want), got == want, got)


def eval_snippet(body):
    """Evaluate snippet asm natively; snippet leaves one value on stack."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
    from fontTools.ttLib.tables.ttProgram import Program
    import freetype as ft
    prog = Program()
    prog.fromAssembly(push(1) + list(body) + ["SVTCA[1]", "SCFS[ ]"])
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({65: "A"})
    g = Glyph()
    g.numberOfContours = 1
    g.coordinates = GlyphCoordinates([(0, 0)] * 4)
    g.endPtsOfContours = [3]
    g.flags = [1] * 4
    g.program = prog
    empty = Glyph()
    empty.numberOfContours = 0
    empty.coordinates = GlyphCoordinates([])
    empty.endPtsOfContours = []
    empty.flags = []
    empty.program = Program()
    fb.setupGlyf({".notdef": empty, "A": g})
    fb.setupHorizontalMetrics({"A": (4000, 0), ".notdef": (4000, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "P", "styleName": "R",
                       "uniqueFontIdentifier": "P", "fullName": "P R",
                       "psName": "P-R"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.setupMaxp()
    buf = io.BytesIO()
    fb.save(buf)
    flags = (ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_NO_AUTOHINT
             | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_PEDANTIC)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "s.ttf"
        path.write_bytes(buf.getvalue())
        face = ft.Face(str(path))
        face.set_pixel_sizes(0, 1000)
        face.load_char("A", flags)
        return int(face.glyph.outline.points[1][0])


def test_native_matches_reference_ops():
    """mul_ref/div_ref reproduce actual native MUL/DIV/rounding results."""
    for a, b in [(100, 3), (-100, 3), (32, 1), (-32, 1), (96, 1),
                 (-160, 1), (16384, 640), (-16384, 640), (63, 1),
                 (-63, 1)]:
        got = eval_snippet(push(a, b) + ["MUL[ ]"])
        check("native MUL(%d,%d)==mul_ref" % (a, b), got == mul_ref(a, b),
              (got, mul_ref(a, b)))
    for a, b in [(7, 3), (-7, 3), (-1, 128), (1, 128), (-16385, 16384),
                 (100, 3)]:
        got = eval_snippet(push(a, b) + ["DIV[ ]"])
        check("native DIV(%d,%d)==div_ref" % (a, b), got == div_ref(a, b),
              (got, div_ref(a, b)))
    # native signed half-away pixel rounding of d14 = +/-2.5px
    for d14, want in [(40960, 3), (-40960, -3), (-8192, -1), (8192, 1),
                      (0, 0)]:
        body = (push(d14) + ["DUP[ ]", "ABS[ ]"] + push(8192) + ["ADD[ ]"]
                + push(1048576) + ["DIV[ ]", "SWAP[ ]"] + push(0)
                + ["LT[ ]", "IF[ ]", "NEG[ ]", "EIF[ ]"])
        got = eval_snippet(body)
        check("native sround(%d)==%d" % (d14, want), got == want, got)
    # canonical push_integer round-trips a large value through native
    got = eval_snippet(push_integer(1000000))
    check("native push_integer(1000000)", got == 1000000, got)
    got = eval_snippet(push_integer(-187743117))
    check("native push_integer(-187743117)", got == -187743117, got)


def test_cardinal_hand_derived():
    s = syn("syn-cardinal-abs")
    out, _, _, _ = run_case(s["cons"], s["parents"], s["scale"])
    check("cardinal native_q6==[192,320]", out["native_q6"] == [192, 320],
          out["native_q6"])
    check("cardinal err 0", out["err_vs_s0"]["s5"] == 0.0,
          out["err_vs_s0"]["s5"])
    check("cardinal res_runtime 0", out["res_runtime"]["s5"] == 0.0,
          out["res_runtime"]["s5"])


def test_halfway_rounding_native():
    s = syn("syn-halfway-pos")
    out, _, _, _ = run_case(s["cons"], s["parents"], s["scale"])
    check("halfway-pos native==[192,256]", out["native_q6"] == [192, 256],
          out["native_q6"])
    s = syn("syn-halfway-neg")
    out, _, _, _ = run_case(s["cons"], s["parents"], s["scale"])
    check("halfway-neg native==[-192,-64]", out["native_q6"] == [-192, -64],
          out["native_q6"])


def test_unrounded_scalar_preserved():
    s = syn("syn-unrounded")
    out, _, _, _ = run_case(s["cons"], s["parents"], s["scale"])
    check("unrounded native==[160,6]", out["native_q6"] == [160, 6],
          out["native_q6"])
    # 0.1px -> d14=1638 -> (1638+128)//256 = 6
    check("unrounded d_used==[2.5,1638/16384]",
          out["d_used"] == [2.5, 1638 / 16384.0], out["d_used"])


def test_signed_dist_hand_solution():
    s = syn("syn-signed-dist")
    out, _, _, _ = run_case(s["cons"], s["parents"], s["scale"])
    check("signed native==[-448,224]", out["native_q6"] == [-448, 224],
          out["native_q6"])
    check("signed s2 near [-7,3.5]",
          max(abs(out["stages"]["s2"][0] + 7.0),
              abs(out["stages"]["s2"][1] - 3.5)) < 1e-3,
          out["stages"]["s2"])


def test_shared_parent_combination():
    s = syn("syn-shared-cancel")
    out, _, _, prog = run_case(s["cons"], s["parents"], s["scale"])
    yterms = prog["qaxes"][1]
    px = [c for k, a, c in yterms if k == "p" and a[1] == 0]
    py = [c for k, a, c in yterms if k == "p" and a[1] == 1]
    check("shared-cancel single combined x-term==0", px == [0], px)
    check("shared-cancel single combined y-term==16384", py == [16384], py)
    check("shared-cancel native==[768,-6144]",
          out["native_q6"] == [768, -6144], out["native_q6"])


def test_shallow_native_matches_ref():
    s = syn("syn-shallow-3deg")
    out, _, _, _ = run_case(s["cons"], s["parents"], s["scale"])
    check("shallow native==ref", out["native_q6"] == out["ref_q6"],
          (out["native_q6"], out["ref_q6"]))
    check("shallow res_runtime<=1/64", out["res_runtime"]["s5"] <= 1 / 64.0,
          out["res_runtime"]["s5"])


def test_zero_det_rejects():
    s = syn("syn-zero-det")
    try:
        run_case(s["cons"], s["parents"], s["scale"])
        check("zero-det rejects", False, "ran without Reject")
    except Reject as e:
        check("zero-det rejects", "singular" in str(e), str(e))


def test_overflow_rejects_despite_cancelling_final():
    s = syn("syn-overflow-cancel")
    try:
        run_case(s["cons"], s["parents"], s["scale"])
        check("overflow rejects", False, "ran without Reject")
    except Reject as e:
        check("overflow rejects", "signed32" in str(e), str(e)[:100])


def test_reference_solution_absent_from_bytecode():
    """Every literal PUSHW operand must come from the allowed compile-time
    set (parent quanta, scalar Q14/splits, Q14 coefficients, rounding
    constants, slots/points); float solution values never appear."""
    s = syn("syn-shared-cancel")
    out, asm, _, prog = run_case(s["cons"], s["parents"], s["scale"])
    allowed = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 8192, 128, 16384, 1048576, 4096}
    allowed.update(prog["d14"])
    for q, r in prog["split"].values():
        allowed.update((q, r))
    for terms in prog["qaxes"]:
        for _, _, c in terms:
            allowed.add(c)
    for terms in prog["qaxes"]:
        for k, a, _ in terms:
            if k == "p":
                allowed.add(a)
    for s_ in range(len(prog["order"])):
        allowed.add(1 + s_)
        for v in prog["pq"][prog["parent_eq"][s_]]:
            allowed.add(v)
    for v in prog["prow"]:
        allowed.add(64 * v)
    bad = []
    for i, op in enumerate(asm):
        if op == "PUSHW[ ]":
            v = int(asm[i + 1])
            if v not in allowed:
                bad.append(v)
    check("bytecode operands all compile-time", bad == [], bad[:8])
    sol = out["stages"]["s0"]
    check("s0 sane ([12,-96])",
          abs(sol[0] - 12.0) < 1e-9 and abs(sol[1] + 96.0) < 1e-9, sol)


def test_freeze_rejects_unsupported():
    try:
        freeze_pair([{"kind": "Ratio", "normal": [1, 0], "sources": [],
                      "value": 1.0},
                     {"kind": "Abs", "normal": [0, 1], "sources": [],
                      "value": 1.0}], [None, None], 1.0)
        check("unsupported kind rejects", False, "no Reject")
    except Reject as e:
        check("unsupported kind rejects", "unsupported" in str(e), str(e))
    try:
        cramer([1.0, 0.0], 1.0, [2.0, 0.0], 2.0)
        check("cramer singular rejects", False, "no Reject")
    except Reject as e:
        check("cramer singular rejects", True, str(e))


def test_fresh_output_guard(tmp=None):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "r")
        rc = main(["--output", out])
        check("first run completes", rc == 0, rc)
        rep = json.loads((Path(out) / "report.json").read_text())
        check("report has 124 corpus total",
              rep["corpus_pairs_total"] == 124, rep["corpus_pairs_total"])
        rc2 = main(["--output", out])
        check("second run refused (no overwrite)", rc2 == 2, rc2)


def test_corpus_spot_s0_and_native_match():
    files = sorted((PROBE / "out/paired-native-iteration-v2/cases").glob(
        "*.json"))
    corpus = [f for f in files
              if json.loads(f.read_text()).get("kind") == "corpus"][:3]
    check("corpus has 124 pairs", len(
        [f for f in files
         if json.loads(f.read_text()).get("kind") == "corpus"]) == 124,
        len(files))
    for f in corpus:
        rec = json.loads(f.read_text())
        out, _, _, _ = run_case(rec["constraints"], rec["parents"],
                                float(rec["ppem"]) / float(rec["em"]))
        diff = max(abs(out["stages"]["s0"][k] - rec["cramer_solution"][k])
                   for k in (0, 1))
        check("spot %s S0==frozen" % f.stem, diff <= 1e-9, diff)
        check("spot %s native==ref" % f.stem,
              out["native_q6"] == out["ref_q6"], out["native_q6"])


def test_review_guards():
    import math
    from unittest.mock import patch
    import experiment_paired_direct_arithmetic as E
    n = math.sqrt(0.5)
    for sign in (-1, 1):
        cons = [{"kind": "Abs", "normal": [n, n], "sources": [],
                 "value": sign * 131071.75, "round": True},
                {"kind": "Abs", "normal": [-n, n], "sources": [],
                 "value": 0, "round": True}]
        try:
            E.run_case(cons, [None, None], 1)
        except Reject as exc:
            check("rounding overflow rejected before font build", "scalar round add" in str(exc))
        else:
            raise AssertionError("rounding overflow was accepted")
    s = syn("syn-shared-cancel")
    out, _, _, _ = run_case(s["cons"], s["parents"], s["scale"])
    check("native accumulator measured", out["native_acc14"] == out["acc14"])
    with patch.object(E, "run_native", return_value=[]):
        try:
            run_case(s["cons"], s["parents"], s["scale"])
        except RuntimeError:
            check("bad native point count is unexpected", True)
        else:
            raise AssertionError("bad native point count accepted")
    with tempfile.TemporaryDirectory() as tmp:
        case_dir = Path(tmp) / "cases"
        case_dir.mkdir()
        # Empty input, then a manifest with exactly one missing case.
        files = sorted(E.IN_CASES.glob("*.json"))
        for mode in ("empty", "missing"):
            if mode == "missing":
                import shutil
                for f in files[1:]:
                    shutil.copy2(f, case_dir / f.name)
            output = Path(tmp) / mode
            with patch.object(E, "IN_CASES", case_dir):
                rc = E.main(["--output", str(output)])
            report = json.loads((output / "report.json").read_text())
            check(mode + " corpus fails explicitly", rc == 1 and not report["audit_complete"])


if __name__ == "__main__":
    test_review_guards()
    test_half_away_ties()
    test_mul_div_reference_hand_table()
    test_native_matches_reference_ops()
    test_cardinal_hand_derived()
    test_halfway_rounding_native()
    test_unrounded_scalar_preserved()
    test_signed_dist_hand_solution()
    test_shared_parent_combination()
    test_shallow_native_matches_ref()
    test_zero_det_rejects()
    test_overflow_rejects_despite_cancelling_final()
    test_reference_solution_absent_from_bytecode()
    test_freeze_rejects_unsupported()
    test_corpus_spot_s0_and_native_match()
    test_fresh_output_guard()
    bad = [p for p in PASS if not p[1]]
    print("passed %d/%d" % (len(PASS) - len(bad), len(PASS)))
    sys.exit(1 if bad else 0)
