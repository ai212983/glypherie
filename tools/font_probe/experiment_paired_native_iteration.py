"""BOUNDED DIAGNOSTIC: alternating native projection iteration on frozen pairs.

Maps the worked alternating-constraint procedure of US7187382B2
(apply one constraint, then the other; stop on movement tolerance or
iteration cap; termination may precede accuracy) onto our fixed-normal
two-equation pairs.  That mapping is our interpretation, not recovered
code.  Diagnostic only: the 1/64 rule below is labelled diagnostic, NOT
a conformance threshold.  No compiler integration, no glyph fixes, no
gallery output.  Frozen prior artifacts only; no baseline regeneration.
"""
import argparse
import hashlib
import io
import json
import math
import platform
import sys
import tempfile
from pathlib import Path

PROBE = Path(__file__).resolve().parent
ROOT = PROBE.parent.parent
IN_REPORT = PROBE / "out/paired-vector-investigation-v1/report.json"
IN_COV = PROBE / "out/native-font-coverage-v2"

ROUNDS = 512
CHECKPOINTS = (1, 10, 100, 512)
DIAG = 1.0 / 64.0  # diagnostic (NOT conformance) tolerance, px
CRAMER_TOL = 1e-8  # absolute px tolerance, Cramer vs frozen baseline
MAX_PROG = 65536
PATENT = "https://patents.google.com/patent/US7187382B2"


class Reject(Exception):
    """Unsupported input: record it, never invent a substitute."""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return Path(path).name


def half_away(x):
    """Round half away from zero to int (signed 26.6 / pixel helper)."""
    x = float(x)
    if x >= 0:
        return int(math.floor(x + 0.5))
    return int(math.ceil(x - 0.5))


def cramer(n1, b1, n2, b2):
    """Independent 2x2 solution of n1.p=b1, n2.p=b2."""
    det = n1[0] * n2[1] - n1[1] * n2[0]
    if det == 0.0:
        raise Reject("singular pair (zero determinant)")
    x = (b1 * n2[1] - b2 * n1[1]) / det
    y = (n1[0] * b2 - n2[0] * b1) / det
    return [x, y]


def push_asm(*values):
    """Compact grouped PUSHB/PUSHW for in-range operands.

    Larger signed32 operands use shamir_constraints.push_integer per
    argument in order; outside the signed32 safe range is rejected.
    """
    ints = [int(v) for v in values]
    for v in ints:
        if abs(v) > 2 ** 31 - 1:
            raise Reject("operand exceeds signed32 safe range: %d" % v)
    if all(0 <= v <= 255 for v in ints):
        return ["PUSHB[ ]"] + [str(v) for v in ints]
    if all(-32768 <= v <= 32767 for v in ints):
        return ["PUSHW[ ]"] + [str(v) for v in ints]
    from shamir_constraints import push_integer
    asm = []
    for v in ints:
        asm += push_integer(v)
    return asm


def freeze_rhs(eq, parents_px, scale):
    """Freeze one equation RHS once (float px).  eq/parents never mutated."""
    kind = eq.get("kind")
    n = [float(eq["normal"][0]), float(eq["normal"][1])]
    rnd = eq.get("round", True)
    if kind in ("Abs", "PAbs"):
        raw = float(eq["value"]) * scale
        b = float(half_away(raw)) if rnd else raw
        return {"normal": n, "b": b, "parent": None, "rounded": bool(rnd)}
    if kind in ("Dist", "PDist"):
        src = list(eq.get("sources", []))
        if len(src) != 1:
            raise Reject("Dist/PDist needs exactly one parent, got %r" % (src,))
        parent = [float(parents_px[src[0]][0]), float(parents_px[src[0]][1])]
        d = float(eq["value"]) * scale
        b = n[0] * parent[0] + n[1] * parent[1] + (half_away(d) if rnd else d)
        return {"normal": n, "b": float(b), "parent": parent,
                "raw_dist": d, "rounded": bool(rnd)}
    raise Reject("unsupported constraint kind: %r" % (kind,))


def reference_run(n1, b1, n2, b2, start, rounds=ROUNDS):
    """High-precision alternating projections p += n*(b-n.p)/|n|^2."""
    p = [float(start[0]), float(start[1])]
    snaps, first_small = {}, None
    prev = list(p)
    for r in range(1, rounds + 1):
        for (n, b) in ((n1, b1), (n2, b2)):
            nn = n[0] * n[0] + n[1] * n[1]
            step = (b - (n[0] * p[0] + n[1] * p[1])) / nn
            p[0] += n[0] * step
            p[1] += n[1] * step
        if first_small is None:
            if max(abs(p[0] - prev[0]), abs(p[1] - prev[1])) < DIAG:
                first_small = r
        prev = list(p)
        if r in CHECKPOINTS:
            snaps[r] = list(p)
    return {"checkpoints": snaps, "final": list(p),
            "first_small_round": first_small}


def res_err(p, n1, b1, n2, b2, oracle):
    r = max(abs(n1[0] * p[0] + n1[1] * p[1] - b1),
            abs(n2[0] * p[0] + n2[1] * p[1] - b2))
    e = max(abs(p[0] - oracle[0]), abs(p[1] - oracle[1]))
    return r, e


def build_fixture(start266, eqs, rounds=ROUNDS, use_gpv=True):
    """Standalone 1:1 (UPM1000/ppem1000) isolation scaffold, not a translator.

    target=point0; trace points 1..rounds hold every full-round position;
    four aux points hold the two raw GPV vectors (x of eq0, y of eq0,
    x of eq1, y of eq1).  GPV yields x below, y on top; WS pops value
    (top) then location; RS pops location; SCFS pops value (top) then
    point.
    """
    from fontTools.fontBuilder import FontBuilder
    from fontTools.ttLib import newTable
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
    from fontTools.ttLib.tables.ttProgram import Program

    n_trace = rounds
    aux_base = 1 + n_trace
    n_pts = 1 + n_trace + 4
    asm = push_asm(1) + ["SZPS[ ]"] + push_asm(1) + ["SLOOP[ ]"]
    asm += ["SVTCA[1]"] + push_asm(0, start266[0]) + ["SCFS[ ]"]
    asm += ["SVTCA[0]"] + push_asm(0, start266[1]) + ["SCFS[ ]"]
    for r in range(rounds):
        for j, e in enumerate(eqs):
            asm += push_asm(e["nx214"], e["ny214"]) + ["SPVFS[ ]", "SFVTPV[ ]"]
            if use_gpv and r == 0:
                ax, ay = aux_base + 2 * j, aux_base + 2 * j + 1
                asm += ["GPV[ ]", "SWAP[ ]"]
                asm += push_asm(0) + ["SWAP[ ]", "WS[ ]"]
                asm += push_asm(1) + ["SWAP[ ]", "WS[ ]"]
                asm += ["SVTCA[1]"] + push_asm(ax, 0) + ["RS[ ]", "SCFS[ ]"]
                asm += ["SVTCA[0]"] + push_asm(ay, 1) + ["RS[ ]", "SCFS[ ]"]
                asm += push_asm(e["nx214"], e["ny214"])
                asm += ["SPVFS[ ]", "SFVTPV[ ]"]
            asm += push_asm(0, e["b266"]) + ["SCFS[ ]"]
        tr = 1 + r
        asm += ["SVTCA[1]"] + push_asm(tr, 0) + ["GC[0]"] + ["SCFS[ ]"]
        asm += ["SVTCA[0]"] + push_asm(tr, 0) + ["GC[0]"] + ["SCFS[ ]"]
    prog = Program()
    prog.fromAssembly(asm)
    code = prog.getBytecode()
    if len(code) >= MAX_PROG:
        raise Reject("program length %d exceeds maxp limit" % len(code))
    check = Program()
    check.fromBytecode(code)
    dasm = check.getAssembly()
    if not any(s.startswith("SCFS[ ]") for s in dasm):
        raise Reject("assembly round-trip lost SCFS")

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({65: "A"})
    g = Glyph()
    g.numberOfContours = 1
    g.coordinates = GlyphCoordinates([(0, 0)] * n_pts)
    g.endPtsOfContours = [n_pts - 1]
    g.flags = [1] * n_pts
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
                       "uniqueFontIdentifier": "P",
                       "fullName": "P R", "psName": "P-R"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.setupMaxp()
    mp = fb.font["maxp"]
    mp.maxStackElements = max(int(getattr(mp, "maxStackElements", 0)), 32)
    mp.maxStorage = max(int(getattr(mp, "maxStorage", 0)), 16)
    mp.maxZones = max(int(getattr(mp, "maxZones", 0)), 2)
    mp.maxSizeOfInstructions = max(int(getattr(mp, "maxSizeOfInstructions", 0)),
                                   len(code))
    buf = io.BytesIO()
    fb.save(buf)
    return buf.getvalue(), asm, len(code)


def run_native(font_bytes, ppem=1000):
    """Execute the fixture under FreeType; return outline points in 26.6."""
    import freetype as ft
    flags = (ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_NO_AUTOHINT
             | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_PEDANTIC)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.ttf"
        path.write_bytes(font_bytes)
        face = ft.Face(str(path))
        face.set_pixel_sizes(0, ppem)
        face.load_char("A", flags)
        pts = [(int(x), int(y)) for (x, y) in face.glyph.outline.points]
    return pts


def analyze_case(frozen, ref, trace266, gpv_raw, start_px):
    """Score the native full-round trace against both Cramer oracles.

    original oracle: float normals + float frozen RHS.
    encoded oracle: actual GPV normals + once-quantized RHS.
    Accuracy (diagnostic, NOT conformance): max residual AND Linf error <= 1/64.
    """
    n1, b1 = frozen["n"][0], frozen["b"][0]
    n2, b2 = frozen["n"][1], frozen["b"][1]
    oracle_o = cramer(n1, b1, n2, b2)
    gn = [[g / 16384.0 for g in v] for v in gpv_raw]
    oracle_e = cramer(gn[0], frozen["b266"][0] / 64.0,
                      gn[1], frozen["b266"][1] / 64.0)
    pos = [(x / 64.0, y / 64.0) for (x, y) in trace266]
    moves, acc_o, acc_e = [], {}, {}
    first_small, first_fixed, first_2cycle = None, None, None
    prev = list(start_px)
    for i, p in enumerate(pos):
        r = i + 1
        mv = max(abs(p[0] - prev[0]), abs(p[1] - prev[1]))
        moves.append(mv)
        if first_small is None and mv < DIAG:
            first_small = r
        prev = list(p)
    # exact fixed points / period-2 cycles in 26.6 integers (measured)
    seq = [(int(x), int(y)) for (x, y) in trace266]
    start_i = (half_away(start_px[0] * 64), half_away(start_px[1] * 64))
    ext = [start_i] + seq
    for i in range(1, len(ext)):
        if first_fixed is None and ext[i] == ext[i - 1]:
            first_fixed = i
        if first_2cycle is None and i >= 2 and ext[i] == ext[i - 2] \
                and ext[i] != ext[i - 1]:
            first_2cycle = i
    tail_2 = len(ext) >= 5 and ext[-1] == ext[-3] and ext[-2] == ext[-4] \
        and ext[-1] != ext[-2]
    cps = [c for c in CHECKPOINTS if c <= len(pos)]
    for cp in cps:
        p = pos[cp - 1]
        ro, eo = res_err(p, n1, b1, n2, b2, oracle_o)
        re_, ee = res_err(p, gn[0], frozen["b266"][0] / 64.0,
                          gn[1], frozen["b266"][1] / 64.0, oracle_e)
        acc_o[cp] = bool(ro <= DIAG and eo <= DIAG)
        acc_e[cp] = bool(re_ <= DIAG and ee <= DIAG)
    pf = pos[-1]
    ro_f, eo_f = res_err(pf, n1, b1, n2, b2, oracle_o)
    re_f, ee_f = res_err(pf, gn[0], frozen["b266"][0] / 64.0,
                        gn[1], frozen["b266"][1] / 64.0, oracle_e)
    if first_small is not None:
        ps = pos[first_small - 1]
        ros, eos = res_err(ps, n1, b1, n2, b2, oracle_o)
        res_, ees = res_err(ps, gn[0], frozen["b266"][0] / 64.0,
                            gn[1], frozen["b266"][1] / 64.0, oracle_e)
        acc_o_s = bool(ros <= DIAG and eos <= DIAG)
        acc_e_s = bool(res_ <= DIAG and ees <= DIAG)
    else:
        acc_o_s = acc_e_s = False
    return {
        "oracle_original": oracle_o, "oracle_encoded": oracle_e,
        "gpv_float": gn,
        "moves": moves,
        "first_small_round": first_small,
        "acc_original_at_first_small": acc_o_s,
        "acc_encoded_at_first_small": acc_e_s,
        "acc_original": {str(k): v for k, v in acc_o.items()},
        "acc_encoded": {str(k): v for k, v in acc_e.items()},
        "first_exact_fixed_round": first_fixed,
        "first_period2_round": first_2cycle,
        "tail_period2": bool(tail_2),
        "final_res_original": ro_f, "final_err_original": eo_f,
        "final_res_encoded": re_f, "final_err_encoded": ee_f,
        "max_res_original": max(res_err(p, n1, b1, n2, b2, oracle_o)[0]
                                for p in pos),
        "max_err_original": max(res_err(p, n1, b1, n2, b2, oracle_o)[1]
                                for p in pos),
    }


def load_corpus():
    rep = json.loads(IN_REPORT.read_text())
    stems = sorted(p.name.replace("-build.json", "")
                   for p in IN_COV.glob("*-build.json"))
    builds = {}
    for stem in stems:
        builds[stem] = json.loads((IN_COV / (stem + "-build.json")).read_text())
    return rep, builds, stems


def prepare_corpus_case(pair, builds, stems, ttf_cache):
    """Freeze one report pair: verbatim constraints, frozen parents, TTF start.

    Returns (frozen, evidence).  Raises Reject instead of inventing data.
    """
    from fontTools.ttLib import TTFont
    case = pair["case"]
    stem = next((s for s in stems if case.startswith(s + "-U+")), None)
    if stem is None:
        raise Reject("no build stem matches case %r" % case)
    char = pair.get("char", "")
    build = builds[stem]
    glyphname = None
    if char:
        try:
            cmap = ttf_cache[(stem, "cmap")]
        except KeyError:
            ttf_path = IN_COV / (stem + "-baseline.ttf")
            font = TTFont(str(ttf_path), recalcTimestamp=False)
            ttf_cache[(stem, "cmap")] = font.getBestCmap()
            ttf_cache[(stem, "upm")] = int(font["head"].unitsPerEm)
            ttf_cache[(stem, "glyf")] = (font["glyf"], font.getGlyphOrder())
            cmap = ttf_cache[(stem, "cmap")]
        glyphname = cmap.get(ord(char), char)
    rec = build["records"].get(glyphname or "")
    if rec is None:
        rec = build["records"].get(char or "")
    if rec is None:
        raise Reject("glyph %r not in build %s" % (char, stem))
    be = rec["graph"]["baseline_execution"]
    ppem, em = int(be["ppem"]), int(be["em"])
    scale = ppem / em
    model = be["model_points_px"]
    fr = [freeze_rhs(dict(c), model, scale) for c in pair["constraints"]]
    if len(fr) != 2:
        raise Reject("pair needs exactly two equations")
    n = [f["normal"] for f in fr]
    b = [f["b"] for f in fr]
    oracle = cramer(n[0], b[0], n[1], b[1])
    base = pair.get("original_model_position")
    if base is None:
        raise Reject("missing frozen baseline solution")
    diff = max(abs(oracle[0] - base[0]), abs(oracle[1] - base[1]))
    if diff >= CRAMER_TOL:
        raise Reject("cramer/baseline mismatch %.3g" % diff)
    glyf, order = ttf_cache[(stem, "glyf")]
    if (glyphname or char) not in order:
        raise Reject("glyph missing from TTF")
    gname = glyphname if (glyphname or "") in order else char
    coords, _, _ = glyf[gname].getCoordinates(glyf)
    idx = int(pair["point"])
    if not 0 <= idx < len(coords):
        raise Reject("point %d outside %d TTF points" % (idx, len(coords)))
    fu = [float(coords[idx][0]), float(coords[idx][1])]
    start = [fu[0] * scale, fu[1] * scale]
    start266 = [half_away(start[0] * 64), half_away(start[1] * 64)]
    frozen = {"n": n, "b": b,
              "b266": [half_away(v * 64) for v in b],
              "start_px": [start266[0] / 64.0, start266[1] / 64.0]}
    evidence = {"kind": "corpus", "case": case, "point": idx, "char": char,
                "stem": stem, "ppem": ppem, "em": em,
                "upm": ttf_cache[(stem, "upm")],
                "constraints": pair["constraints"],
                "parents": [f["parent"] for f in fr],
                "raw_dist": [f.get("raw_dist") for f in fr],
                "rounded": [f["rounded"] for f in fr],
                "b": b, "b266": frozen["b266"],
                "baseline_solution": list(base),
                "cramer_solution": oracle,
                "cramer_baseline_diff": diff,
                "start_fu": fu, "start_px": start,
                "start266": start266}
    return frozen, evidence


def synthetics():
    """Eight hand-specified controls with known solutions; same algorithm."""
    deg = math.pi / 180.0
    return [
        {"name": "syn-cardinal", "n": [[1.0, 0.0], [0.0, 1.0]],
         "sol": [3.0, 5.0], "start": [0.0, 0.0]},
        {"name": "syn-oblique", "n": [[0.6, 0.8], [0.8, -0.6]],
         "sol": [4.0, -2.0], "start": [0.0, 0.0]},
        {"name": "syn-shallow-0.12deg",
         "n": [[1.0, 0.0], [math.cos(0.12 * deg), math.sin(0.12 * deg)]],
         "sol": [10.0, 2.0], "start": [0.0, 0.0]},
        {"name": "syn-shallow-1deg",
         "n": [[1.0, 0.0], [math.cos(1.0 * deg), math.sin(1.0 * deg)]],
         "sol": [10.0, 2.0], "start": [0.0, 0.0]},
        {"name": "syn-shallow-3deg",
         "n": [[1.0, 0.0], [math.cos(3.0 * deg), math.sin(3.0 * deg)]],
         "sol": [10.0, 2.0], "start": [0.0, 0.0]},
        {"name": "syn-zero", "n": [[1.0, 0.0], [0.0, 1.0]],
         "sol": [0.0, 0.0], "start": [0.0, 0.0]},
        {"name": "syn-signed", "n": [[0.6, 0.8], [-0.6, 0.8]],
         "sol": [-7.0, 3.5], "start": [5.0, -5.0]},
        {"name": "syn-rot30-far",
         "n": [[math.cos(30 * deg), math.sin(30 * deg)],
               [-math.sin(30 * deg), math.cos(30 * deg)]],
         "sol": [2.25, -1.5], "start": [100.0, 100.0]},
    ]


def run_case(frozen, rounds=ROUNDS):
    """Reference + native execution + analysis for frozen equations."""
    n = frozen["n"]
    nn = [[half_away(v * 16384) for v in row] for row in n]
    eqs = [{"nx214": nn[j][0], "ny214": nn[j][1], "b266": frozen["b266"][j]}
           for j in (0, 1)]
    start266 = [half_away(frozen["start_px"][0] * 64),
                half_away(frozen["start_px"][1] * 64)]
    ref = reference_run(n[0], frozen["b"][0], n[1], frozen["b"][1],
                        [start266[0] / 64.0, start266[1] / 64.0],
                        rounds=rounds)
    font_bytes, asm, prog_len = build_fixture(start266, eqs, rounds=rounds)
    pts = run_native(font_bytes)
    need = 1 + rounds + 4
    if len(pts) != need:
        raise Reject("native returned %d points, need %d" % (len(pts), need))
    trace = pts[1:1 + rounds]
    aux = pts[1 + rounds:]
    gpv_raw = [[aux[0][0], aux[1][1]], [aux[2][0], aux[3][1]]]
    ana = analyze_case(frozen, ref, trace, gpv_raw,
                       [start266[0] / 64.0, start266[1] / 64.0])
    return ref, trace, gpv_raw, ana, asm, prog_len, font_bytes, nn


def aggregate(rows):
    """Corpus/synthetic summary counts; rows are per-case analysis dicts."""
    tot = len(rows)
    out = {"total": tot, "executed": tot}
    for cp in CHECKPOINTS:
        k = str(cp)
        out["original_accurate_at_%d" % cp] = sum(
            1 for r in rows if r["acc_original"].get(k, False))
        out["encoded_accurate_at_%d" % cp] = sum(
            1 for r in rows if r["acc_encoded"].get(k, False))
    out["ever_small_movement"] = sum(1 for r in rows
                                     if r["first_small_round"] is not None)
    out["false_early_original"] = sum(
        1 for r in rows if r["first_small_round"] is not None
        and not r["acc_original_at_first_small"])
    out["false_early_encoded"] = sum(
        1 for r in rows if r["first_small_round"] is not None
        and not r["acc_encoded_at_first_small"])
    out["false_early10_original"] = sum(
        1 for r in rows if r["first_small_round"] is not None
        and r["first_small_round"] <= 10
        and not r["acc_original_at_first_small"])
    out["exact_fixed_point"] = sum(1 for r in rows
                                   if r["first_exact_fixed_round"] is not None)
    out["tail_period2"] = sum(1 for r in rows if r["tail_period2"])
    for m in ("final_res_original", "final_err_original",
              "final_res_encoded", "final_err_encoded",
              "max_res_original", "max_err_original"):
        out["max_" + m] = max([r[m] for r in rows]) if rows else None
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bounded paired native iteration")
    ap.add_argument("--output", default="out/paired-native-iteration-v1")
    args = ap.parse_args(argv)
    outdir = (PROBE / args.output).resolve()
    if outdir.exists():
        print("refusing: exists (rerun with a new --output, never overwrite)",
              file=sys.stderr)
        return 2
    rep, builds, stems = load_corpus()
    cases_dir = outdir / "cases"
    cases_dir.mkdir(parents=True)
    code_sha = sha256_file(Path(__file__).resolve())
    inputs = {rel(IN_REPORT): sha256_file(IN_REPORT)}
    for stem in stems:
        inputs[rel(IN_COV / (stem + "-build.json"))] = sha256_file(
            IN_COV / (stem + "-build.json"))
        inputs[rel(IN_COV / (stem + "-baseline.ttf"))] = sha256_file(
            IN_COV / (stem + "-baseline.ttf"))
    for helper in ("shamir_constraints.py", "shamir_prototype.py"):
        inputs[rel(PROBE / helper)] = sha256_file(PROBE / helper)

    ttf_cache, summaries, failures, corpus_rows, syn_rows = {}, [], [], [], []
    pairs = list(rep.get("pairs", []))
    for i, pair in enumerate(pairs):
        cid = "%03d-%s-p%d" % (i, pair.get("case", "?"), pair.get("point", -1))
        try:
            frozen, ev = prepare_corpus_case(pair, builds, stems, ttf_cache)
            ref, trace, gpv_raw, ana, asm, plen, fb, nn = run_case(frozen)
        except Reject as e:
            failures.append({"id": cid, "kind": "corpus",
                             "reason": str(e),
                             "case": pair.get("case"), "point": pair.get("point"),
                             "char": pair.get("char")})
            continue
        except Exception as e:  # noqa: BLE001 - unexpected goes to inventory
            failures.append({"id": cid, "kind": "corpus",
                             "reason": "unexpected: %s: %s"
                             % (type(e).__name__, e),
                             "case": pair.get("case"), "point": pair.get("point"),
                             "char": pair.get("char")})
            continue
        ev.update({"normals_f214": nn, "gpv_raw": gpv_raw,
                   "gpv_float": ana["gpv_float"],
                   "ref_checkpoints": ref["checkpoints"],
                   "ref_final": ref["final"],
                   "ref_first_small_round": ref["first_small_round"],
                   "program_len": plen,
                   "trace266": [[int(x), int(y)] for (x, y) in trace]})
        ev.update({k: ana[k] for k in ana if k != "moves"})
        (cases_dir / (cid + ".json")).write_text(json.dumps(ev, indent=1))
        (cases_dir / (cid + ".ttf")).write_bytes(fb)
        (cases_dir / (cid + ".asm.txt")).write_text("\n".join(asm) + "\n")
        summaries.append({"id": cid, "kind": "corpus",
                          **{k: ana[k] for k in ana if k != "moves"}})
        corpus_rows.append(ana)
        print("[%d/%d] %s prog=%d res512=%.4g err512=%.4g" % (
            i + 1, len(pairs), cid, plen,
            ana["final_res_original"], ana["final_err_original"]))

    for syn in synthetics():
        cid = syn["name"]
        try:
            n = [list(map(float, row)) for row in syn["n"]]
            b = [n[j][0] * syn["sol"][0] + n[j][1] * syn["sol"][1]
                 for j in (0, 1)]
            frozen = {"n": n, "b": b,
                      "b266": [half_away(v * 64) for v in b],
                      "start_px": list(map(float, syn["start"]))}
            if max(abs(cramer(n[0], b[0], n[1], b[1])[k] - syn["sol"][k])
                   for k in (0, 1)) > 1e-9:
                raise Reject("synthetic solution inconsistent")
            ref, trace, gpv_raw, ana, asm, plen, fb, nn = run_case(frozen)
        except Reject as e:
            failures.append({"id": cid, "kind": "synthetic",
                             "reason": str(e)})
            continue
        except Exception as e:  # noqa: BLE001
            failures.append({"id": cid, "kind": "synthetic",
                             "reason": "unexpected: %s: %s"
                             % (type(e).__name__, e)})
            continue
        ev = {"kind": "synthetic", "name": syn["name"], "normals": n,
              "solution": syn["sol"], "b": b, "b266": frozen["b266"],
              "start_px": frozen["start_px"], "normals_f214": nn,
              "gpv_raw": gpv_raw, "gpv_float": ana["gpv_float"],
              "ref_checkpoints": ref["checkpoints"], "ref_final": ref["final"],
              "ref_first_small_round": ref["first_small_round"],
              "program_len": plen,
              "trace266": [[int(x), int(y)] for (x, y) in trace]}
        ev.update({k: ana[k] for k in ana if k != "moves"})
        (cases_dir / (cid + ".json")).write_text(json.dumps(ev, indent=1))
        (cases_dir / (cid + ".ttf")).write_bytes(fb)
        (cases_dir / (cid + ".asm.txt")).write_text("\n".join(asm) + "\n")
        summaries.append({"id": cid, "kind": "synthetic",
                          **{k: ana[k] for k in ana if k != "moves"}})
        syn_rows.append(ana)
        print("[syn] %s prog=%d res512=%.4g err512=%.4g" % (
            cid, plen, ana["final_res_original"], ana["final_err_original"]))

    try:
        import fontTools
        fonttools_ver = getattr(fontTools, "version", "?")
    except Exception:  # noqa: BLE001
        fonttools_ver = "?"
    try:
        import freetype
        ft_lib = ".".join(str(c) for c in freetype.version())
    except Exception:  # noqa: BLE001
        ft_lib = "?"
    try:
        from importlib.metadata import version as pkg_version
        ft_pkg = pkg_version("freetype-py")
    except Exception:  # noqa: BLE001
        ft_pkg = "?"
    report = {
        "meta": {
            "tool": rel(Path(__file__).resolve()),
            "code_sha256": code_sha,
            "inputs": inputs,
            "rounds": ROUNDS,
            "diag_tolerance_px": DIAG,
            "diag_note": "diagnostic, NOT a conformance threshold",
            "cramer_tolerance_px": CRAMER_TOL,
            "mapping_note": ("Alternating native SCFS projection of "
                             "fixed-normal pairs interprets the worked "
                             "procedure of %s; not recovered code." % PATENT),
            "sources": [PATENT],
            "versions": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "fontTools": fonttools_ver,
                "freetype_lib": ft_lib,
                "freetype_py": ft_pkg,
            },
            "output": rel(outdir),
        },
        "corpus_pairs_total": len(pairs),
        "corpus_executed": len(corpus_rows),
        "synthetic_total": len(synthetics()),
        "synthetic_executed": len(syn_rows),
        "aggregate_corpus": aggregate(corpus_rows),
        "aggregate_synthetic": aggregate(syn_rows),
        "cases": summaries,
        "failures": failures,
        "audit_complete": (len(corpus_rows) == len(pairs)
                           and not any(f["kind"] == "corpus"
                                       for f in failures)
                           and len(syn_rows) == len(synthetics())),
    }
    (outdir / "report.json").write_text(json.dumps(report, indent=1))
    print("corpus %d/%d synthetic %d/%d failures %d audit_complete=%s" % (
        len(corpus_rows), len(pairs), len(syn_rows), len(synthetics()),
        len(failures), report["audit_complete"]))
    return 0 if report["audit_complete"] else 1


if __name__ == "__main__":
    sys.exit(main())



