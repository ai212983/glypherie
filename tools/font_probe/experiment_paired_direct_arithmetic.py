"""Isolated native DIRECT-arithmetic prototype on frozen v2 pair corpus.

Direct 2x2 solve n1.p=b1, n2.p=b2 compiled to linear x/y expressions over
runtime parent coordinates and scalar distance/absolute terms.  The float
reference solution NEVER enters native bytecode; only normals, the inverse
matrix are compile-time geometry. Scalar d and parent setup values are
requested-size fixture inputs, not scalable CVT/original-coordinate capture.

Scale sequence (documented, exact):
  Q14 = value*16384, Q6 = value*64 (TrueType 26.6 units as integers).
  MUL(a,b) = round-half-away(a*b/64)      (probed on FreeType 2.13.2)
  DIV(a,b) = trunc-toward-zero(a*64/b)    (probed; b>0 throughout)
  Parent input v (26.6 integer q6 from cardinal GC[0]) has residual 0, so a
  parent term is a single MUL(c14,q6) = round(c*q) in Q14.
  Scalar input d (unrounded) is split at compile time into signed q6 =
  trunc(d14/256) and residual r14 = d14-256*q6 (|r14|<256).  The term is
  MUL(c14,q6) + DIV(MUL(c14,r14),16384); the DIV divides the rounded
  product by 256 (DIV multiplies by 64 first), truncating from Q22 to Q14.
  Each MUL rounds to nearest, so every product carries at most 0.5 LSB of
  Q14 (1/32768 px) quantization error; the residual DIV truncates (<1 LSB).
  The integer reference replicates both exactly, so native and reference
  agree bit-for-bit or the case fails.
  Rounded scalars (round=True) are pixel-rounded IN native arithmetic from
  the materialized d14 with ABS/+8192/DIV1048576/restore-sign, giving
  integer pixels P; Q=64P (=MUL(P,4096), exact) feeds one MUL(c14,Q) per
  axis term.  The final point is rounded once to 26.6 with
  ABS/+128/DIV16384/restore-sign (128 = half of the 256 divisor).
  Signed rounding uses ABS/+half/trunc/restore-sign via IF/NEG, never
  TrueType grid rounding compensation.
  Shared-parent coefficients are combined BEFORE quantization, so exact
  cancellation (e.g. cy_px = 0) emits a single zero term with no large
  intermediate products.
  Range safety is static and per-fixture only: every materialized operand,
  MUL/DIV return, ADD/SUB, and final-round addition is checked against
  +/-(2^31-1) before any fixture is built.  A violation REJECTS the case;
  it is inventoried, never passed, and is not a runtime protection claim.

Corpus: tools/font_probe/out/paired-native-iteration-v2/cases/*.json
(kind == "corpus", 124 pairs).  No compiler/production edits.
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
IN_V2 = PROBE / "out/paired-native-iteration-v2"
IN_REPORT = IN_V2 / "report.json"
IN_CASES = IN_V2 / "cases"

DIAG = 1.0 / 64.0  # diagnostic (NOT conformance) tolerance, px
CRAMER_TOL = 1e-9  # S0 vs frozen v2 cramer_solution, px
INT32 = 2 ** 31 - 1

# Storage slots in the fixture. 0/1 hold final Q6 results; 2..5 hold the
# captured parent coordinates; 6/7 hold rounded-scalar Q values.
SX, SY = 0, 1
ACC_SLOTS = (8, 9)
PSLOT = {(0, 0): 2, (0, 1): 3, (1, 0): 4, (1, 1): 5}
QSLOT = {0: 6, 1: 7}


class Reject(Exception):
    """Anticipated refusal (singular/unsupported/range): inventoried only."""


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
    """Round half away from zero to int."""
    x = float(x)
    if x >= 0:
        return int(math.floor(x + 0.5))
    return int(math.ceil(x - 0.5))


from shamir_constraints import push_integer


def push(*values):
    asm = []
    for v in values:
        asm += push_integer(v)
    return asm


def mul_ref(a, b):
    """Exact replica of native MUL: round-half-away(a*b/64)."""
    p = int(a) * int(b)
    s = -1 if p < 0 else 1
    return s * ((abs(p) + 32) // 64)


def div_ref(a, b):
    """Exact replica of native DIV with b > 0: trunc(a*64/b) toward zero."""
    if b <= 0:
        raise Reject("DIV divisor must be positive, got %r" % (b,))
    s = -1 if int(a) < 0 else 1
    return s * ((abs(int(a)) * 64) // int(b))


def cramer(n1, b1, n2, b2):
    """Independent float 2x2 solution of n1.p=b1, n2.p=b2."""
    det = n1[0] * n2[1] - n1[1] * n2[0]
    if det == 0.0:
        raise Reject("singular pair (zero determinant)")
    return [(b1 * n2[1] - b2 * n1[1]) / det,
            (n1[0] * b2 - n2[0] * b1) / det]


def inverse2(n1, n2):
    det = n1[0] * n2[1] - n1[1] * n2[0]
    if det == 0.0:
        raise Reject("singular pair (zero determinant)")
    return [[n2[1] / det, -n1[1] / det], [-n2[0] / det, n1[0] / det]]


def freeze_pair(cons, parents_model, scale):
    """Split frozen equations into parent coords + scalar d (float px).

    Returns (normals, pm[2], d[2], rnd[2], src_ids[2], b_orig[2]).
    d comes from value*scale only, never from b or solved positions.
    pm entries are [x, y, src] or [None, None, None].
    """
    if len(cons) != 2:
        raise Reject("pair needs exactly two equations, got %d" % len(cons))
    normals, pm, d, rnd, src_ids = [], [], [], [], []
    for k, e in enumerate(cons):
        kind = e.get("kind")
        if kind not in ("Dist", "PDist", "Abs", "PAbs"):
            raise Reject("unsupported constraint kind: %r" % (kind,))
        normals.append([float(e["normal"][0]), float(e["normal"][1])])
        rnd.append(bool(e.get("round", True)))
        dj = float(e["value"]) * scale
        d.append(dj)
        if kind in ("Dist", "PDist"):
            src = list(e.get("sources", []))
            if len(src) != 1:
                raise Reject("Dist/PDist needs exactly one parent, got %r"
                              % (src,))
            mp = parents_model[k]
            if mp is None:
                raise Reject("Dist/PDist equation %d has no parent" % k)
            pm.append([float(mp[0]), float(mp[1]), src[0]])
            src_ids.append(src[0])
        else:
            pm.append([None, None, None])
            src_ids.append(None)
    b = []
    for j in (0, 1):
        s = half_away(d[j]) if rnd[j] else d[j]
        if pm[j][0] is None:
            b.append(float(s))
        else:
            b.append(normals[j][0] * pm[j][0] + normals[j][1] * pm[j][1]
                     + float(s))
    return normals, pm, d, rnd, src_ids, b


def checked(v, maximum, what):
    if abs(int(v)) > INT32:
        raise Reject("range: %s=%d exceeds signed32" % (what, int(v)))
    maximum[0] = max(maximum[0], abs(int(v)))
    return int(v)


def compile_terms(normals, pm, rnd, winv):
    """Expand x/y into combined parent + scalar terms (float coefficients).

    Shared parents (same source id) are combined BEFORE quantization.
    Returns per-axis term lists [(kind, aux, coeff)] where kind is 'p'
    (parent coord slot key) or 's' (scalar index), plus slot assignment.
    """
    src = [p[2] for p in pm]  # source id or None per equation
    # distinct parent slots in first-use order
    slot_of, order = {}, []
    for j in (0, 1):
        if src[j] is not None and src[j] not in slot_of:
            slot_of[src[j]] = len(order)
            order.append(src[j])
    if len(order) > 2:
        raise Reject("more than two distinct parents")
    axes = []
    for row in (0, 1):
        terms = []
        # parent terms, combined when both equations share the source
        if src[0] is not None and src[0] == src[1]:
            s = slot_of[src[0]]
            cx = winv[row][0] * normals[0][0] + winv[row][1] * normals[1][0]
            cy = winv[row][0] * normals[0][1] + winv[row][1] * normals[1][1]
            terms.append(("p", (s, 0), cx))
            terms.append(("p", (s, 1), cy))
        else:
            for j in (0, 1):
                if src[j] is None:
                    continue
                s = slot_of[src[j]]
                terms.append(("p", (s, 0), winv[row][j] * normals[j][0]))
                terms.append(("p", (s, 1), winv[row][j] * normals[j][1]))
        for j in (0, 1):
            terms.append(("s", j, winv[row][j]))
        axes.append(terms)
    return axes, order


def simulate(normals, pm, d, rnd, src_ids, maximum):
    """Static checked integer simulation; returns reference + program data.

    Raises Reject on any out-of-range intermediate.  No cancellation-based
    safety: every MUL/DIV/ADD and the final-round addition is checked.
    pm entries are [x, y, src] or [None, None, None].
    """
    winv = inverse2(normals[0], normals[1])
    # parent 26.6 quanta (fixture setup values; native reads these via GC)
    pq = []
    for p in pm:
        if p[0] is None:
            pq.append(None)
        else:
            qx = checked(half_away(p[0] * 64), maximum, "parent q6x")
            qy = checked(half_away(p[1] * 64), maximum, "parent q6y")
            pq.append([qx, qy])
    # shared-source parents must agree: native reads a single point
    for j in (0, 1):
        for k in (0, 1):
            if src_ids[j] is not None and src_ids[j] == src_ids[k] \
                    and pq[j] != pq[k]:
                raise Reject("shared parent coordinates differ")
    # scalar Q14 + native-equivalent rounded pixels P =
    # sign(d14)*((|d14|+8192)//16384), exactly what the native
    # ABS/+8192/DIV1048576/restore-sign sequence computes
    d14, prow = [], []
    for j in (0, 1):
        v = checked(half_away(d[j] * 16384), maximum, "scalar d14")
        d14.append(v)
        if rnd[j]:
            checked(abs(v) + 8192, maximum, "scalar round add")
            checked(1048576, maximum, "scalar round divisor")
        prow.append(-((abs(v) + 8192) // 16384) if v < 0 else
                    (abs(v) + 8192) // 16384)
    axes, order = compile_terms(normals, pm, rnd, winv)
    parent_eq = []
    for s in range(len(order)):
        parent_eq.append(next(j for j in (0, 1) if src_ids[j] == order[s]))
    # quantize coefficients
    qaxes = []
    for terms in axes:
        qt = []
        for kind, aux, c in terms:
            c14 = checked(half_away(c * 16384), maximum, "coeff c14")
            qt.append((kind, aux, c14))
        qaxes.append(qt)
    # scalar splits for unrounded equations: trunc + residual
    split = {}
    for j in (0, 1):
        if not rnd[j]:
            q = checked(math.trunc(d14[j] / 256), maximum, "scalar q6")
            r = checked(d14[j] - 256 * q, maximum, "scalar r14")
            split[j] = (q, r)
    ref_q6, acc14 = [], []
    for terms in qaxes:
        acc = None
        for kind, aux, c14 in terms:
            if kind == "p":
                s, xy = aux
                t = checked(mul_ref(c14, pq[parent_eq[s]][xy]),
                            maximum, "MUL parent")
            elif rnd[aux]:
                q = checked(64 * prow[aux], maximum, "scalar Q=64P")
                t = checked(mul_ref(c14, q), maximum, "MUL rounded scalar")
            else:
                q, r = split[aux]
                t1 = checked(mul_ref(c14, q), maximum, "MUL scalar q6")
                m2 = checked(mul_ref(c14, r), maximum, "MUL scalar r14")
                t2 = checked(div_ref(m2, 16384), maximum, "DIV scalar /256")
                t = checked(t1 + t2, maximum, "ADD scalar parts")
            acc = t if acc is None else checked(acc + t, maximum, "ADD acc")
        checked(abs(acc) + 128, maximum, "final round add")
        mag = (abs(acc) + 128) // 256
        ref_q6.append(-mag if acc < 0 else mag)
        acc14.append(acc)
    return {"winv": winv, "pq": pq, "d14": d14, "prow": prow,
            "qaxes": qaxes, "split": split, "order": order,
            "parent_eq": parent_eq, "acc14": acc14, "ref_q6": ref_q6,
            "maxabs": maximum[0]}


def axis_asm(terms, rnd, split, accumulator_slot):
    """Native code for one axis; leaves rounded Q6 value on the stack.

    terms use storage slots for parents: ('p', slot, c14); scalars stay
    ('s', j, c14).  split maps unrounded equation j -> (q6, r14).
    """
    asm, first = [], True
    for kind, aux, c14 in terms:
        if kind == "p":
            frag = push(aux) + ["RS[ ]"] + push(c14) + ["MUL[ ]"]
        elif rnd[aux]:
            frag = push(QSLOT[aux]) + ["RS[ ]"] + push(c14) + ["MUL[ ]"]
        else:
            q, r = split[aux]
            frag = (push(q) + push(c14) + ["MUL[ ]"] + push(r) + push(c14)
                    + ["MUL[ ]"] + push(16384) + ["DIV[ ]", "ADD[ ]"])
        asm += frag
        if not first:
            asm += ["ADD[ ]"]
        first = False
    asm += ["DUP[ ]"] + push(accumulator_slot) + ["SWAP[ ]", "WS[ ]"]
    asm += (["DUP[ ]", "ABS[ ]"] + push(128) + ["ADD[ ]"] + push(16384)
            + ["DIV[ ]", "SWAP[ ]"] + push(0)
            + ["LT[ ]", "IF[ ]", "NEG[ ]", "EIF[ ]"])
    return asm


def scalar_asm(j, d14, rnd):
    """Native code producing rounded-scalar Q=64P for equation j."""
    if not rnd:
        return []
    return (push(d14) + ["DUP[ ]", "ABS[ ]"] + push(8192) + ["ADD[ ]"]
            + push(1048576) + ["DIV[ ]", "SWAP[ ]"] + push(0)
            + ["LT[ ]", "IF[ ]", "NEG[ ]", "EIF[ ]"]
            + push(4096) + ["MUL[ ]"] + push(QSLOT[j]) + ["SWAP[ ]", "WS[ ]"])


def build_fixture(prog, rnd):
    """Assemble the standalone 1:1 (UPM1000/ppem1000) cardinal fixture."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
    from fontTools.ttLib.tables.ttProgram import Program

    order = prog["order"]
    n_par = len(order)
    n_pts = 3 + n_par
    asm = push(1) + ["SZPS[ ]"] + push(1) + ["SLOOP[ ]"]
    # Fixture setup only: place parents at exact 26.6 quanta (outline
    # coordinates are integers, so fractional 26.6 needs SCFS).  The
    # evaluator below only READS these through cardinal GC.
    for s in range(n_par):
        pj = prog["parent_eq"][s]
        asm += (["SVTCA[1]"] + push(1 + s, prog["pq"][pj][0]) + ["SCFS[ ]"])
        asm += (["SVTCA[0]"] + push(1 + s, prog["pq"][pj][1]) + ["SCFS[ ]"])
    # capture parents through cardinal GC before moving the child
    for s in range(n_par):
        asm += (["SVTCA[1]"] + push(1 + s) + ["GC[0]"]
                + push(PSLOT[(s, 0)]) + ["SWAP[ ]", "WS[ ]"])
        asm += (["SVTCA[0]"] + push(1 + s) + ["GC[0]"]
                + push(PSLOT[(s, 1)]) + ["SWAP[ ]", "WS[ ]"])
    for j in (0, 1):
        asm += scalar_asm(j, prog["d14"][j], rnd[j])
    for row in (0, 1):
        terms = []
        for kind, aux, c14 in prog["qaxes"][row]:
            if kind == "p":
                terms.append(("p", PSLOT[aux], c14))
            else:
                terms.append(("s", aux, c14))
        asm += axis_asm(terms, rnd, prog["split"], ACC_SLOTS[row])
        asm += push(SX if row == 0 else SY) + ["SWAP[ ]", "WS[ ]"]
    asm += (["SVTCA[1]"] + push(0, SX) + ["RS[ ]", "SCFS[ ]"])
    asm += (["SVTCA[0]"] + push(0, SY) + ["RS[ ]", "SCFS[ ]"])
    # Auxiliary outline coordinates expose the unrounded native Q14 integers.
    for row, slot in enumerate(ACC_SLOTS):
        asm += ["SVTCA[1]"] + push(1 + n_par + row, slot) + ["RS[ ]", "SCFS[ ]"]
    prog_obj = Program()
    prog_obj.fromAssembly(asm)
    code = prog_obj.getBytecode()
    if len(code) >= 65536:
        raise Reject("program length %d exceeds maxp limit" % len(code))
    check = Program()
    check.fromBytecode(code)
    if not any(s.startswith("SCFS[ ]") for s in check.getAssembly()):
        raise Reject("assembly round-trip lost SCFS")

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({65: "A"})
    coords = [(0, 0)] * n_pts
    g = Glyph()
    g.numberOfContours = 1
    g.coordinates = GlyphCoordinates(coords)
    g.endPtsOfContours = [n_pts - 1]
    g.flags = [1] * n_pts
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
    mp.maxSizeOfInstructions = max(int(getattr(mp, "maxSizeOfInstructions",
                                               0)), len(code))
    buf = io.BytesIO()
    fb.save(buf)
    return buf.getvalue(), asm, len(code)


def run_case(cons, parents_model, scale):
    """Full pipeline: freeze, simulate, build, execute, compare stages."""
    normals, pm, d, rnd, src_ids, b0 = freeze_pair(cons, parents_model,
                                                  scale)
    s0 = cramer(normals[0], b0[0], normals[1], b0[1])
    # S1: parent 26.6 only (scalars original float)
    pqf = [None if p[0] is None else [half_away(p[0] * 64) / 64.0,
                                      half_away(p[1] * 64) / 64.0]
           for p in pm]
    b1 = []
    for j in (0, 1):
        s = half_away(d[j]) if rnd[j] else d[j]
        if pqf[j] is None:
            b1.append(float(s))
        else:
            b1.append(normals[j][0] * pqf[j][0] + normals[j][1] * pqf[j][1]
                      + float(s))
    s1 = cramer(normals[0], b1[0], normals[1], b1[1])
    # static checked simulation (Reject on singular/unsupported/range)
    maximum = [0]
    prog = simulate(normals, pm, d, rnd, src_ids, maximum)
    # S2: parent 26.6 + Q14 scalars with native-equivalent rounding
    s_used = [float(prog["prow"][j]) if rnd[j]
              else prog["d14"][j] / 16384.0 for j in (0, 1)]
    b2 = []
    for j in (0, 1):
        if pqf[j] is None:
            b2.append(s_used[j])
        else:
            b2.append(normals[j][0] * pqf[j][0] + normals[j][1] * pqf[j][1]
                      + s_used[j])
    s2 = cramer(normals[0], b2[0], normals[1], b2[1])
    # S3: encoded-coefficient prediction from the same runtime inputs
    s3 = []
    for row in (0, 1):
        acc = 0.0
        for kind, aux, c14 in prog["qaxes"][row]:
            c = c14 / 16384.0
            if kind == "p":
                s, xy = aux
                acc += c * pqf[prog["parent_eq"][s]][xy]
            else:
                acc += c * s_used[aux]
        s3.append(acc)
    s4 = [prog["acc14"][0] / 16384.0, prog["acc14"][1] / 16384.0]
    # native execution
    font_bytes, asm, plen = build_fixture(prog, rnd)
    pts = run_native(font_bytes)
    need = 3 + len(prog["order"])
    if len(pts) != need:
        raise RuntimeError("native returned %d points, need %d" % (len(pts),
                                                              need))
    for s in range(len(prog["order"])):
        pj = prog["parent_eq"][s]
        if pts[1 + s] != (prog["pq"][pj][0], prog["pq"][pj][1]):
            raise Exception("unexpected: parent point %d moved "
                            "native=%r setup=%r"
                            % (s, pts[1 + s],
                               (prog["pq"][pj][0], prog["pq"][pj][1])))
    native_acc14 = [int(pt[0]) for pt in pts[-2:]]
    if native_acc14 != prog["acc14"]:
        raise RuntimeError("native pre-final accumulator/reference mismatch: %r != %r"
                           % (native_acc14, prog["acc14"]))
    native_q6 = [int(pts[0][0]), int(pts[0][1])]
    if native_q6 != prog["ref_q6"]:
        raise Exception("unexpected: native/reference mismatch "
                        "native=%r ref=%r" % (native_q6, prog["ref_q6"]))
    s5 = [native_q6[0] / 64.0, native_q6[1] / 64.0]

    def res(pt, bb):
        return max(abs(normals[j][0] * pt[0] + normals[j][1] * pt[1]
                       - bb[j]) for j in (0, 1))

    def err(pt):
        return max(abs(pt[0] - s0[0]), abs(pt[1] - s0[1]))

    drift = 0.0
    for j in (0, 1):
        if pm[j][0] is not None:
            drift = max(drift, abs(pqf[j][0] - pm[j][0]),
                        abs(pqf[j][1] - pm[j][1]))
    stages = {"s0": s0, "s1": s1, "s2": s2, "s3": s3, "s4": s4, "s5": s5}
    out = {"stages": {k: list(map(float, v)) for k, v in stages.items()},
           "res_orig": {k: res(v, b0) for k, v in stages.items()},
           "res_runtime": {k: res(v, b2) for k, v in stages.items()},
           "err_vs_s0": {k: err(v) for k, v in stages.items()},
           "parent_drift": drift,
           "scalar_err": max(abs(s_used[j] - (half_away(d[j]) if rnd[j]
                                                else d[j]))
                             for j in (0, 1)),
           "coeff_err": max(abs(s3[0] - s2[0]), abs(s3[1] - s2[1])),
           "arith_err": max(abs(s4[0] - s3[0]), abs(s4[1] - s3[1])),
           "final_err": max(abs(s5[0] - s4[0]), abs(s5[1] - s4[1])),
           "native_q6": native_q6, "ref_q6": list(prog["ref_q6"]),
           "acc14": list(prog["acc14"]), "native_acc14": native_acc14,
           "err_runtime_s5": max(abs(s5[k] - s2[k]) for k in (0, 1)),
           "b_orig": list(map(float, b0)), "b_runtime": list(map(float, b2)),
           "d_used": list(map(float, s_used)),
           "c14": [[c for (_, _, c) in terms] for terms in prog["qaxes"]],
           "max_intermediate": prog["maxabs"], "program_len": plen}
    return out, asm, font_bytes, prog


def synthetics():
    """Constraint-level synthetic controls (scale 1: value == px)."""
    deg = math.pi / 180.0
    c3, s3 = math.cos(3 * deg), math.sin(3 * deg)
    ceps, seps = math.cos(0.005 * deg), math.sin(0.005 * deg)
    abs_eq = lambda v, r=True: {"kind": "Abs", "normal": [0.0, 0.0],
                                "sources": [], "value": v, "round": r}
    syns = []
    syns.append({"name": "syn-cardinal-abs",
                 "cons": [dict(abs_eq(3.0), normal=[1.0, 0.0]),
                          dict(abs_eq(5.0), normal=[0.0, 1.0])],
                 "parents": [None, None], "scale": 1.0,
                 "expect": "native_q6 == [192, 320]"})
    syns.append({"name": "syn-signed-dist",
                 "cons": [{"kind": "Dist", "normal": [0.6, 0.8],
                           "sources": [11], "value": -3.6, "round": False},
                          {"kind": "Dist", "normal": [-0.6, 0.8],
                           "sources": [17], "value": 10.2, "round": False}],
                 "parents": [[1.0, 2.0], [4.0, -1.0]], "scale": 1.0,
                 "expect": "s2 near [-7, 3.5]; native == ref exactly"})
    syns.append({"name": "syn-shared-cancel",
                 "cons": [{"kind": "Dist", "normal": [1.0, 0.0],
                           "sources": [5], "value": 2.0, "round": True},
                          {"kind": "Dist", "normal": [1.0, 0.01],
                           "sources": [5], "value": 1.0, "round": True}],
                 "parents": [[10.0, 4.0], [10.0, 4.0]], "scale": 1.0,
                 "expect": "combined y parent coeff 0; "
                           "native_q6 == [768, -6144]"})
    syns.append({"name": "syn-shallow-3deg",
                 "cons": [dict(abs_eq(10.0), normal=[1.0, 0.0]),
                          dict(abs_eq(10.0 * c3 + 2.0 * s3),
                               normal=[c3, s3])],
                 "parents": [None, None], "scale": 1.0,
                 "expect": "res_runtime(s5) <= 1/64; native == ref"})
    syns.append({"name": "syn-halfway-pos",
                 "cons": [dict(abs_eq(2.5), normal=[1.0, 0.0]),
                          dict(abs_eq(4.0), normal=[0.0, 1.0])],
                 "parents": [None, None], "scale": 1.0,
                 "expect": "native_q6 == [192, 256] (2.5 -> 3)"})
    syns.append({"name": "syn-halfway-neg",
                 "cons": [dict(abs_eq(-2.5), normal=[1.0, 0.0]),
                          dict(abs_eq(-0.5), normal=[0.0, 1.0])],
                 "parents": [None, None], "scale": 1.0,
                 "expect": "native_q6 == [-192, -64]"})
    syns.append({"name": "syn-unrounded",
                 "cons": [dict(abs_eq(2.5, False), normal=[1.0, 0.0]),
                          dict(abs_eq(0.1, False), normal=[0.0, 1.0])],
                 "parents": [None, None], "scale": 1.0,
                 "expect": "native_q6 == [160, 6]; Q14 preserved"})
    syns.append({"name": "syn-zero-det",
                 "cons": [dict(abs_eq(1.0), normal=[1.0, 0.0]),
                          dict(abs_eq(2.0), normal=[2.0, 0.0])],
                 "parents": [None, None], "scale": 1.0,
                 "expect": "Reject singular"})
    syns.append({"name": "syn-overflow-cancel",
                 "cons": [{"kind": "Dist", "normal": [1.0, 0.0],
                           "sources": [5], "value": 0.0, "round": True},
                          {"kind": "Dist", "normal": [ceps, seps],
                           "sources": [6], "value": 0.0, "round": True}],
                 "parents": [[20.0, 0.0], [20.0, 0.0]], "scale": 1.0,
                 "expect": "Reject range (intermediate exceeds signed32 "
                           "despite cancelling final; distinct ids defeat "
                           "shared-parent combination)"})
    return syns


def load_corpus():
    files = sorted(IN_CASES.glob("*.json"))
    corpus = []
    for f in files:
        rec = json.loads(f.read_text())
        if rec.get("kind") == "corpus":
            corpus.append((f, rec))
    upstream = json.loads(IN_REPORT.read_text())
    expected = [r["id"] for r in upstream["cases"] if r["kind"] == "corpus"]
    actual = [f.stem for f, _ in corpus]
    if (not upstream.get("audit_complete") or not expected
            or len(expected) != upstream["corpus_pairs_total"]
            or len(expected) != len(set(expected))
            or set(actual) != set(expected)
            or any(r.get("id", f.stem) != f.stem for f, r in corpus)):
        raise ValueError("frozen corpus differs from complete upstream manifest")
    return corpus


def classify_reject(msg):
    m = str(msg)
    if "singular" in m or "zero determinant" in m:
        return "singular"
    if "unsupported" in m:
        return "unsupported"
    if "range" in m or "signed32" in m or " Differ" in m or "differ" in m:
        return "range"
    return "rejected"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Isolated paired direct solve")
    ap.add_argument("--output", default="out/paired-direct-arithmetic-v1")
    args = ap.parse_args(argv)
    out = Path(args.output)
    outdir = out if out.is_absolute() else (PROBE / out)
    if outdir.exists():
        print("refusing: exists (rerun with a new --output, never overwrite)",
              file=sys.stderr)
        return 2
    try:
        corpus = load_corpus()
    except Exception as exc:
        outdir.mkdir(parents=True)
        (outdir / "report.json").write_text(json.dumps({
            "audit_complete": False, "corpus_executed": 0,
            "failures": [{"kind": "input", "reason": str(exc)}]}, indent=1))
        print("incomplete frozen input: %s" % exc, file=sys.stderr)
        return 1
    cases_dir = outdir / "cases"
    cases_dir.mkdir(parents=True)
    inputs = {rel(IN_REPORT): sha256_file(IN_REPORT)}
    for f, _ in corpus:
        inputs[rel(f)] = sha256_file(f)
    for helper in ("shamir_constraints.py", "shamir_prototype.py",
                   "experiment_paired_native_iteration.py"):
        inputs[rel(PROBE / helper)] = sha256_file(PROBE / helper)
    code_sha = sha256_file(Path(__file__).resolve())

    summaries, rejections, failures = [], [], []
    n_exec = 0
    for f, rec in corpus:
        cid = f.stem
        cons = rec["constraints"]
        parents_model = rec["parents"]
        try:
            scale = float(rec["ppem"]) / float(rec["em"])
            out_st, asm, fb, prog = run_case(cons, parents_model, scale)
        except Reject as e:
            rejections.append({"id": cid, "kind": "corpus",
                               "class": classify_reject(e),
                               "reason": str(e)})
            continue
        except Exception as e:  # noqa: BLE001 - unexpected inventoried
            failures.append({"id": cid, "kind": "corpus",
                             "reason": "unexpected: %s: %s"
                             % (type(e).__name__, e)})
            continue
        drift0 = max(abs(out_st["stages"]["s0"][k]
                         - rec["cramer_solution"][k]) for k in (0, 1))
        if drift0 > CRAMER_TOL:
            failures.append({"id": cid, "kind": "corpus",
                             "reason": "unexpected: S0 vs frozen cramer "
                                       "diff %.3g" % drift0})
            continue
        ev = {"id": cid, "kind": "corpus", "case": rec.get("case"),
              "point": rec.get("point"), "char": rec.get("char"),
              "stem": rec.get("stem"), "ppem": rec.get("ppem"),
              "em": rec.get("em"), "constraints": cons,
              "parents_model": parents_model,
              "frozen_cramer": rec.get("cramer_solution"),
              "s0_vs_frozen_diff": drift0}
        ev.update(out_st)
        (cases_dir / (cid + ".json")).write_text(json.dumps(ev, indent=1))
        (cases_dir / (cid + ".ttf")).write_bytes(fb)
        (cases_dir / (cid + ".asm.txt")).write_text("\n".join(asm) + "\n")
        summaries.append({"id": cid, "kind": "corpus",
                          "native_q6": out_st["native_q6"],
                          "res_orig_s5": out_st["res_orig"]["s5"],
                          "res_runtime_s5": out_st["res_runtime"]["s5"],
                          "err_s5": out_st["err_vs_s0"]["s5"],
                          "err_runtime_s5": out_st["err_runtime_s5"],
                          "max_intermediate": out_st["max_intermediate"],
                          "program_len": out_st["program_len"]})
        n_exec += 1

    syn_exec, syn_ok = 0, 0
    for syn in synthetics():
        cid = syn["name"]
        try:
            out_st, asm, fb, prog = run_case(syn["cons"], syn["parents"],
                                             syn["scale"])
        except Reject as e:
            if cid in ("syn-zero-det", "syn-overflow-cancel"):
                syn_ok += 1
                rejections.append({"id": cid, "kind": "synthetic",
                                   "class": classify_reject(e),
                                   "reason": str(e),
                                   "expected": syn["expect"]})
            else:
                failures.append({"id": cid, "kind": "synthetic",
                                 "reason": "unexpected Reject: %s" % e})
            continue
        except Exception as e:  # noqa: BLE001
            failures.append({"id": cid, "kind": "synthetic",
                             "reason": "unexpected: %s: %s"
                             % (type(e).__name__, e)})
            continue
        if cid in ("syn-zero-det", "syn-overflow-cancel"):
            failures.append({"id": cid, "kind": "synthetic",
                             "reason": "unexpected: should have rejected"})
            continue
        ev = {"id": cid, "kind": "synthetic", "expect": syn["expect"],
              "constraints": syn["cons"], "parents_model": syn["parents"]}
        ev.update(out_st)
        (cases_dir / (cid + ".json")).write_text(json.dumps(ev, indent=1))
        (cases_dir / (cid + ".ttf")).write_bytes(fb)
        (cases_dir / (cid + ".asm.txt")).write_text("\n".join(asm) + "\n")
        summaries.append({"id": cid, "kind": "synthetic",
                          "native_q6": out_st["native_q6"],
                          "res_orig_s5": out_st["res_orig"]["s5"],
                          "res_runtime_s5": out_st["res_runtime"]["s5"],
                          "err_s5": out_st["err_vs_s0"]["s5"],
                          "err_runtime_s5": out_st["err_runtime_s5"],
                          "max_intermediate": out_st["max_intermediate"],
                          "program_len": out_st["program_len"]})
        syn_exec += 1
        syn_ok += 1

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
    exec_rows = [s for s in summaries if s["kind"] == "corpus"]
    rej_corpus = [r for r in rejections if r["kind"] == "corpus"]
    report = {
        "meta": {
            "tool": rel(Path(__file__).resolve()),
            "code_sha256": code_sha,
            "inputs": inputs,
            "design": ("direct 2x2 solve compiled to parent/scalar linear "
                       "forms; reference float never in bytecode; parents "
                       "read via cardinal GC; final cardinal SCFS; signed "
                       "half-away rounding natively; static per-fixture "
                       "range rejection only"),
            "versions": {"python": platform.python_version(),
                         "platform": platform.platform(),
                         "fontTools": fonttools_ver,
                         "freetype_lib": ft_lib, "freetype_py": ft_pkg},
            "output": rel(outdir),
            "diag_note": "1/64 is a diagnostic tolerance, NOT conformance",
        },
        "corpus_pairs_total": len(corpus),
        "corpus_executed": n_exec,
        "corpus_rejected": len(rej_corpus),
        "synthetic_total": len(synthetics()),
        "synthetic_resolved": syn_ok,
        "aggregate_corpus": {
            "max_res_orig_s5": max([s["res_orig_s5"] for s in exec_rows])
            if exec_rows else None,
            "max_res_runtime_s5": max([s["res_runtime_s5"] for s in exec_rows])
            if exec_rows else None,
            "max_err_s5": max([s["err_s5"] for s in exec_rows])
            if exec_rows else None,
            "max_intermediate": max([s["max_intermediate"] for s in exec_rows])
            if exec_rows else None,
            "n_res_runtime_le_diag": sum(1 for s in exec_rows
                                        if s["res_runtime_s5"] <= DIAG),
            "max_err_runtime_s5": max([s["err_runtime_s5"] for s in exec_rows])
            if exec_rows else None,
            "n_runtime_accurate": sum(s["err_runtime_s5"] <= DIAG
                                      and s["res_runtime_s5"] <= DIAG for s in exec_rows),
            "n_original_accurate": sum(s["err_s5"] <= DIAG
                                       and s["res_orig_s5"] <= DIAG for s in exec_rows),
            "n_err_le_diag": sum(1 for s in exec_rows
                                 if s["err_s5"] <= DIAG),
        },
        "cases": summaries,
        "rejections": rejections,
        "failures": failures,
        "audit_complete": (n_exec + len(rej_corpus) == len(corpus)
                           and not failures
                           and syn_ok == len(synthetics())),
    }
    (outdir / "report.json").write_text(json.dumps(report, indent=1))
    print("corpus %d/%d rejected %d synthetic %d/%d failures %d "
          "audit_complete=%s" % (n_exec, len(corpus), len(rej_corpus),
                                 syn_ok, len(synthetics()), len(failures),
                                 report["audit_complete"]))
    return 0 if report["audit_complete"] else 1


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
        return [(int(x), int(y)) for (x, y) in face.glyph.outline.points]


if __name__ == "__main__":
    sys.exit(main())
