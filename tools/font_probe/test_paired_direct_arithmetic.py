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


def test_direct_solver_consumes_moved_parent():
    # Dependency-graph check for the direct solver (plan Phase 2, B12
    # "direct-solver dependencies"): the pair's shared parent is moved by
    # a real preceding native op -- IP between SCFS-moved anchors, per
    # Shamir 2003 section 3.6 dependency order -- and GC[0] captures its
    # CURRENT 26.6 position (Microsoft TT spec: GC[0] reads current,
    # GC[1] reads original) for the direct-solve terms. The direct solve
    # itself remains our documented translation choice, not a recovered
    # paper implementation (see shamir-native-paired-arithmetic.md).
    # FreeType execution is the oracle; the integer simulate() reference
    # never enters native bytecode.
    from fontTools.fontBuilder import FontBuilder
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
    from fontTools.ttLib.tables.ttProgram import Program
    import freetype as ft
    from experiment_paired_direct_arithmetic import (
        ACC_SLOTS, PSLOT, SX, SY, axis_asm, simulate,
    )
    n1, n2 = [0.6, 0.8], [-0.6, 0.8]
    # Parent P starts at FU (1,0). A1 is SCFS-moved to raw 300, so IP
    # places P at ratio (64-0)/(192-0) = 1/3: 300/3 = 100 raw exactly
    # (1.5625px, off-grid by construction).
    pm_cur = [[100 / 64.0, 0.0, 1], [100 / 64.0, 0.0, 1]]
    maximum = [0]
    prog = simulate([n1, n2], pm_cur, [1.0, 2.0],
                    [False, False], [1, 1], maximum)
    # Points: 0=child, 1=parent, 2/3=IP anchors, 4/5=accumulators.
    asm = push(1) + ["SZPS[ ]"] + push(1) + ["SLOOP[ ]"]
    asm += ["SVTCA[1]"] + push(3, 300) + ["SCFS[ ]"]
    asm += (["SVTCA[1]"] + push(2) + ["SRP1[ ]"] + push(3)
            + ["SRP2[ ]"] + push(1) + ["IP[ ]"])
    asm += (["SVTCA[1]"] + push(1) + ["GC[0]"]
            + push(PSLOT[(0, 0)]) + ["SWAP[ ]", "WS[ ]"])
    asm += (["SVTCA[0]"] + push(1) + ["GC[0]"]
            + push(PSLOT[(0, 1)]) + ["SWAP[ ]", "WS[ ]"])
    for row in (0, 1):
        terms = [(k, PSLOT[a] if k == "p" else a, c)
                 for k, a, c in prog["qaxes"][row]]
        asm += axis_asm(terms, [False, False], prog["split"],
                        ACC_SLOTS[row])
        asm += push(SX if row == 0 else SY) + ["SWAP[ ]", "WS[ ]"]
    asm += ["SVTCA[1]"] + push(0, SX) + ["RS[ ]", "SCFS[ ]"]
    asm += ["SVTCA[0]"] + push(0, SY) + ["RS[ ]", "SCFS[ ]"]
    asm += ["SVTCA[1]"] + push(4, ACC_SLOTS[0]) + ["RS[ ]", "SCFS[ ]"]
    asm += ["SVTCA[1]"] + push(5, ACC_SLOTS[1]) + ["RS[ ]", "SCFS[ ]"]
    prog_obj = Program()
    prog_obj.fromAssembly(asm)
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({65: "A"})
    g = Glyph()
    g.numberOfContours = 1
    g.coordinates = GlyphCoordinates(
        [(0, 0), (1, 0), (0, 0), (3, 0), (0, 0), (0, 0)])
    g.endPtsOfContours = [5]
    g.flags = [1] * 6
    g.program = prog_obj
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
    mp = fb.font["maxp"]
    mp.maxStackElements = max(int(getattr(mp, "maxStackElements", 0)), 32)
    mp.maxStorage = max(int(getattr(mp, "maxStorage", 0)), 16)
    mp.maxZones = max(int(getattr(mp, "maxZones", 0)), 2)
    buf = io.BytesIO()
    fb.save(buf)
    flags = (ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_NO_AUTOHINT
             | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_PEDANTIC)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "c.ttf"
        path.write_bytes(buf.getvalue())
        face = ft.Face(str(path))
        face.set_pixel_sizes(0, 1000)
        face.load_char("A", flags)
        pts = [(int(p[0]), int(p[1]))
               for p in face.glyph.outline.points]
    check("IP moved parent to (100,0), off original (64,0)",
          pts[1] == (100, 0), pts[1])
    check("chained child == current-parent reference",
          (pts[0][0], pts[0][1]) == tuple(prog["ref_q6"]),
          (pts[0], prog["ref_q6"]))
    check("chained accumulators match bit-for-bit",
          [pts[4][0], pts[5][0]] == prog["acc14"],
          ([pts[4][0], pts[5][0]], prog["acc14"]))
    # Sensitivity: the float-ideal solution from ORIGINAL parents must
    # differ, proving current-state (not original/float) consumption.
    b0 = [n1[0] * 1.0 + 1.0, n2[0] * 1.0 + 2.0]
    s0 = cramer(n1, b0[0], n2, b0[1])
    gap = max(abs(pts[0][0] / 64.0 - s0[0]),
              abs(pts[0][1] / 64.0 - s0[1]))
    check("moved-parent solution differs from original-parent float "
          "solution by > 1/64px", gap > 1 / 64.0, (gap, s0))


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


def test_domain_bound_accepts_fitting_domain():
    # Execution-domain range contract: domain_bound() lifts the static
    # per-fixture check to worst-case magnitudes over a declared domain
    # (max |parent 26.6|, max |scalar Q14|). A fitting domain passes and
    # covers the observed fixture maximum.
    from experiment_paired_direct_arithmetic import domain_bound, simulate
    s = syn("syn-signed-dist")
    normals, pm, d, rnd, src_ids, _ = freeze_pair(
        s["cons"], s["parents"], s["scale"])
    maximum = [0]
    prog = simulate(normals, pm, d, rnd, src_ids, maximum)
    bound = domain_bound(normals, src_ids, rnd, 128000, 16384 * 2000)
    check("domain bound covers fixture max",
          bound >= prog["maxabs"], (bound, prog["maxabs"]))
    check("domain bound within signed32", bound <= 2 ** 31 - 1, bound)
    maximum2 = [0]
    prog2 = simulate(normals, pm, d, rnd, src_ids, maximum2,
                     domain=(128000, 16384 * 2000))
    check("simulate accepts fitting domain",
          prog2["ref_q6"] == prog["ref_q6"],
          (prog2["ref_q6"], prog["ref_q6"]))


def test_domain_bound_rejects_beyond_fixture():
    # A near-parallel pair fits its single fixture (zero scalars) but its
    # domain-wide worst case overflows signed32: compile-time Reject with
    # a "domain" reason, never a silent runtime overflow. This is why the
    # projection/freedom support gate must stay for any arithmetic path.
    import math
    from experiment_paired_direct_arithmetic import domain_bound, simulate
    eps = math.radians(0.05)
    cons = [{"kind": "Abs", "normal": [1.0, 0.0],
             "sources": [], "value": 0.0, "round": True},
            {"kind": "Abs", "normal": [math.cos(eps), math.sin(eps)],
             "sources": [], "value": 0.0, "round": True}]
    normals, pm, d, rnd, src_ids, _ = freeze_pair(cons, [None, None], 1.0)
    maximum = [0]
    prog = simulate(normals, pm, d, rnd, src_ids, maximum)
    check("near-parallel zero fixture fits", prog["ref_q6"] == [0, 0],
          prog["ref_q6"])
    try:
        domain_bound(normals, src_ids, rnd, 64000, 16384 * 100)
    except Reject as e:
        check("domain rejects beyond-fixture overflow",
              "domain" in str(e), str(e))
    else:
        raise AssertionError("domain overflow was accepted")
    try:
        simulate(normals, pm, d, rnd, src_ids, [0],
                 domain=(64000, 16384 * 100))
    except Reject as e:
        check("simulate enforces domain", "domain" in str(e), str(e))
    else:
        raise AssertionError("simulate accepted out-of-domain pair")


def test_scalable_cvt_capture_multi_size():
    # Scalable target capture: CVT-held scalars, one program shape, run at
    # 8/16/20ppem (UPM 1000). Every design value is a multiple of 125fu so
    # each size scales onto the 26.6 grid exactly (probed RCVT behavior):
    # the float reference is then exact and any deviation is real error.
    # FreeType execution is the oracle; no per-size scalar constants enter
    # the capture/solve bytecode.
    from experiment_paired_direct_arithmetic import run_scalable
    cons = [{"kind": "Dist", "normal": [0.6, 0.8], "sources": [11],
             "value": 125, "round": True},
            {"kind": "Dist", "normal": [-0.6, 0.8], "sources": [17],
             "value": 250, "round": True}]
    parents_fu = [[125, 250], [375, 125]]
    outs = {}
    for ppem in (8, 16, 20):
        outs[ppem] = run_scalable(cons, parents_fu, [125, 250],
                                  upm=1000, ppem=ppem)
    for ppem, out in outs.items():
        check("ppem %d native==ref" % ppem,
              out["native_q6"] == out["ref_q6"],
              (ppem, out["native_q6"], out["ref_q6"]))
        check("ppem %d res_runtime<=1/64" % ppem,
              out["res_runtime"] <= 1 / 64.0, out["res_runtime"])
        check("ppem %d err_runtime<=1/64" % ppem,
              out["err_runtime"] <= 1 / 64.0, out["err_runtime"])
    check("child scales with size (not baked)",
          outs[8]["native_q6"] != outs[20]["native_q6"],
          (outs[8]["native_q6"], outs[20]["native_q6"]))
    tails = [out["asm"][out["setup_len"]:] for out in outs.values()]
    check("capture+solve asm identical across sizes",
          tails[0] == tails[1] == tails[2],
          [len(t) for t in tails])


def test_scalable_unrounded_runtime_split():
    # The runtime q6/r14 split (RQSLOT/RRSLOT/SUB path) executes correctly:
    # exact on-grid inputs give r=0 (nonzero residuals stay covered by the
    # baked-fixture unrounded test) while native==ref proves the plumbing.
    from experiment_paired_direct_arithmetic import run_scalable
    cons = [{"kind": "Abs", "normal": [1.0, 0.0],
             "sources": [], "value": 250, "round": False},
            {"kind": "Abs", "normal": [0.0, 1.0],
             "sources": [], "value": 125, "round": False}]
    out = run_scalable(cons, [None, None], [250, 125], upm=1000, ppem=16)
    check("unrounded scalable native==ref",
          out["native_q6"] == out["ref_q6"],
          (out["native_q6"], out["ref_q6"]))
    check("unrounded scalable native==[256,128]",
          out["native_q6"] == [256, 128], out["native_q6"])


def test_graphics_state_preamble_and_vector_domination():
    # Graphics-state guarantee, audited from emitted bytes (both builders):
    # an explicit preamble establishes zones/loop/reference points first;
    # every GC/SCFS is dominated by an SVTCA naming its axis; no
    # reference-point-dependent op appears, so the pinned RP init suffices.
    from experiment_paired_direct_arithmetic import (
        establish_state_asm, run_scalable,
    )
    pre = establish_state_asm()
    for name in ("SZPS[ ]", "SLOOP[ ]", "SRP0[ ]", "SRP1[ ]", "SRP2[ ]"):
        check("preamble contains " + name, name in pre, pre)
    check("zones established before reference points",
          pre.index("SZPS[ ]") < pre.index("SRP0[ ]"), pre)

    def audit(asm, tag):
        check(tag + " starts with preamble",
              asm[:len(pre)] == pre, asm[:len(pre) + 2])
        axes = []
        cur = None
        for op in asm:
            if op in ("SVTCA[0]", "SVTCA[1]"):
                cur = int(op[6])
            elif op in ("GC[0]", "GC[1]", "SCFS[ ]"):
                check(tag + " op has vector state", cur is not None, op)
                axes.append(cur)
            elif op in ("MIRP[ ]", "MDRP[ ]", "ALIGNRP[ ]", "IP[ ]"):
                raise AssertionError(tag + " has RP-dependent op " + op)
        n_gc = sum(1 for op in asm if op in ("GC[0]", "GC[1]"))
        n_par = n_gc // 2
        check(tag + " even GC pairs", n_gc == 2 * n_par, n_gc)
        # harness setup alternates x,y per parent; captures alternate x,y
        # per parent; child x,y; both acc writes x.
        check(tag + " vector pattern",
              axes == [1, 0] * (2 * n_par) + [1, 0, 1, 1], axes)

    s = syn("syn-signed-dist")
    _, fixture_asm, _, _ = run_case(s["cons"], s["parents"], s["scale"])
    audit(fixture_asm, "fixture")
    out = run_scalable(
        [{"kind": "Dist", "normal": [0.6, 0.8], "sources": [11],
          "value": 125, "round": True},
         {"kind": "Dist", "normal": [-0.6, 0.8], "sources": [17],
          "value": 250, "round": True}],
        [[125, 250], [375, 125]], [125, 250], upm=1000, ppem=16)
    audit(out["asm"], "scalable")


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
    test_direct_solver_consumes_moved_parent()
    test_domain_bound_accepts_fitting_domain()
    test_domain_bound_rejects_beyond_fixture()
    test_scalable_cvt_capture_multi_size()
    test_scalable_unrounded_runtime_split()
    test_graphics_state_preamble_and_vector_domination()
    test_zero_det_rejects()
    test_overflow_rejects_despite_cancelling_final()
    test_reference_solution_absent_from_bytecode()
    test_freeze_rejects_unsupported()
    test_corpus_spot_s0_and_native_match()
    test_fresh_output_guard()
    bad = [p for p in PASS if not p[1]]
    print("passed %d/%d" % (len(PASS) - len(bad), len(PASS)))
    sys.exit(1 if bad else 0)
