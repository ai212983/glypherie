"""Experimental native TrueType translation of a complete point-DAG graph.

Caller opts in explicitly by calling compile_native. No fallback to SCFS,
no import or evaluation of the baseline float solver, no glyph/font/size
identities. Input graph is an existing complete point-DAG dict
(constraints/order) from shamir_point_schedule; inputs are treated as
immutable. Continued isolated-equation experimental policy, not recovered
paper defaults. Constant vectors are isotropic only; the caller must
guarantee isotropic vectors (no embedded ppem in the compiler).

Sources: Shamir2003 Table I (Abs~MDAP/PAbs~MIAP/Dist~MDRP/PDist~MIRP/
Ratio~IP), section 4.1 small instruction sequences ordered by resolved
dependencies, Fig.9 MIRP[11101] then ALIGNRP; Microsoft TrueType
instructions
(https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions);
VTT pinned 1bd4ed4383f8390b0140e05d330491fcadd3e8e0 TTGenerator.cpp
Link467+, Interpolate652+, AlmostPerpendicular347-356 (support gate
abs(dot) < 1/16); FreeType (https://www.freetype.org/) 2.13.2 ttinterp
clamp below 0x400 (1/16); stack push encoding via fontTools
(https://github.com/fonttools/fonttools) ttProgram.Program.
The 1/16 gate here is a native support gate on the ideal and on the
F2.14-encoded normalized dots, not a model selection cutoff. Point
independence is a determinant gate (exact zero or within 32*float64
epsilon), never an invented dot threshold.
"""
import math

import numpy as np

from shamir_prototype import push

NATIVE_DOT_CUTOFF = 1.0 / 16.0
_F214 = 16384
_EPS32 = 32 * np.finfo(float).eps

CITED_SOURCES = [
    "Shamir2003 Table I, section 4.1, Fig.9: https://doi.org/10.1145/636886.636887"
    " (see also PAPER in shamir_prototype.py)",
    "https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions",
    "https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L467",
    "https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L652",
    "https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L347-L356",
    "https://download.savannah.gnu.org/releases/freetype/freetype-2.13.2.tar.gz",
    "https://github.com/fonttools/fonttools/blob/4.64.0/Lib/fontTools/ttLib/tables/ttProgram.py",
]


class UnsupportedNativeTranslation(ValueError):
    """Raised when the graph is not natively supported."""

    def __init__(self, diagnostics):
        super().__init__("unsupported native translation: %d point(s)" % len(diagnostics))
        self.diagnostics = list(diagnostics)


def _asvec(v):
    return np.asarray(v, dtype=float).reshape(2)


def _dot(a, b):
    return float(np.dot(a, b))


def _norm(a):
    return math.sqrt(_dot(a, a))


def _perp(v):
    return np.asarray([-float(v[1]), float(v[0])], dtype=float)


def _tolist(v):
    return [float(v[0]), float(v[1])]


def _q14(v):
    return int(round(float(v) * _F214))


def _is_int_fu(v):
    if isinstance(v, (bool, np.bool_)):
        return False
    if isinstance(v, (int, np.integer)):
        return -32768 <= int(v) <= 32767
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return (math.isfinite(f) and f.is_integer()
                and -32768 <= int(f) <= 32767)
    return False


def _is_exact_int(v):
    return (isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_)))


def compile_native(graph, points):
    """Compile a complete point-DAG graph to native TrueType assembly.

    Returns (assembly, metadata). Raises UnsupportedNativeTranslation.
    """
    diags = []

    def reject(point, cid, reason):
        diags.append(dict(point=point, constraint_id=cid, reason=str(reason)))

    # ---- points: finite Nx2, with explicit genuinely-empty acceptance ----
    # Microsoft glyf simple-glyph description allows zero contours with no
    # additional data
    # (https://learn.microsoft.com/en-us/typography/opentype/spec/glyf);
    # advance/lsb stay owned by hmtx. Only [] (1-D zero-length) or
    # shape (0, 2) count as genuinely empty; (0, 3), (2, 0), None,
    # ragged, and non-finite inputs stay rejected below.
    try:
        pts = np.asarray(points, dtype=float)
    except (TypeError, ValueError):
        raise UnsupportedNativeTranslation(
            [dict(point=-1, constraint_id=None, reason="points are not numeric Nx2")])
    if pts.ndim == 1 and pts.shape == (0,):
        pts = pts.reshape(0, 2)
    if pts.ndim != 2 or pts.shape[1] != 2 or not bool(np.all(np.isfinite(pts))):
        raise UnsupportedNativeTranslation(
            [dict(point=-1, constraint_id=None, reason="points must be finite Nx2")])
    n_pts = int(pts.shape[0])

    if not isinstance(graph, dict):
        raise UnsupportedNativeTranslation(
            [dict(point=-1, constraint_id=None, reason="graph must be a dict")])
    constraints = graph.get("constraints", [])
    order = graph.get("order", [])
    try:
        constraints = list(constraints)
        order = list(order)
    except TypeError:
        raise UnsupportedNativeTranslation(
            [dict(point=-1, constraint_id=None, reason="constraints/order must be sequences")])

    # ---- order: exact integers, complete permutation (no silent truncation) ----
    if len(order) != n_pts or any(not _is_exact_int(p) for p in order):
        raise UnsupportedNativeTranslation(
            [dict(point=-1, constraint_id=None, reason="order is not an exact complete permutation")])
    order = [int(p) for p in order]
    if sorted(order) != list(range(n_pts)):
        raise UnsupportedNativeTranslation(
            [dict(point=-1, constraint_id=None, reason="order is not an exact complete permutation")])

    # ---- IDs: exact integers, unique ----
    for c in constraints:
        if not isinstance(c, dict) or not _is_exact_int(c.get("id", None)):
            raise UnsupportedNativeTranslation(
                [dict(point=-1, constraint_id=None, reason="constraint IDs must be exact integers")])
    ids = [int(c["id"]) for c in constraints]
    if len(set(ids)) != len(ids):
        raise UnsupportedNativeTranslation(
            [dict(point=-1, constraint_id=None, reason="duplicate constraint IDs")])
    grouped = {}
    for c in constraints:
        p = c.get("point", None)
        if not _is_exact_int(p):
            reject(-1, int(c["id"]), "point must be an exact integer")
            continue
        grouped.setdefault(int(p), []).append(c)
    if sorted(grouped) != list(range(n_pts)) or any(len(g) != 2 for g in grouped.values()):
        raise UnsupportedNativeTranslation(
            diags + [dict(point=-1, constraint_id=None,
                           reason="each point needs exactly two constraints")])

    # ---- per-constraint validation (no resolver, no added constraints) ----
    for c in constraints:
        cid = int(c["id"])
        p = int(c["point"])
        n = c.get("normal", None)
        try:
            nv = np.asarray(n, dtype=float)
        except (TypeError, ValueError):
            reject(p, cid, "normal must have shape exactly (2,)")
            continue
        if nv.shape != (2,) or not bool(np.all(np.isfinite(nv))):
            reject(p, cid, "normal must have shape exactly (2,) and be finite")
            continue
        if abs(_norm(nv) - 1.0) > _EPS32 * max(1.0, _norm(nv)):
            reject(p, cid, "normal is not unit")
        v = c.get("value", None)
        if not isinstance(v, (int, float, np.integer, np.floating)) or isinstance(v, (bool, np.bool_)) \
                or not math.isfinite(float(v)):
            reject(p, cid, "non-finite value")
        if c.get("kind") not in ("Abs", "PAbs", "Dist", "PDist", "Ratio", "PRatio"):
            reject(p, cid, "unknown kind %r" % (c.get("kind"),))
            continue
        ar = {"Abs": 0, "PAbs": 0, "Dist": 1, "PDist": 1, "Ratio": 2, "PRatio": 2}[c.get("kind")]
        src = c.get("sources", [])
        try:
            src = list(src)
        except TypeError:
            reject(p, cid, "wrong arity for %s" % c.get("kind"))
            continue
        if len(src) != ar:
            reject(p, cid, "wrong arity for %s" % c.get("kind"))
            continue
        for s in src:
            if not _is_exact_int(s) or not 0 <= int(s) < n_pts:
                reject(p, cid, "source %r out of range" % (s,))
    if diags:
        raise UnsupportedNativeTranslation(diags)

    completed = set()
    for p in order:
        for c in grouped[p]:
            for s in c.get("sources", []):
                if _is_exact_int(s) and int(s) not in completed:
                    reject(p, int(c["id"]),
                           "source %d not completed before point %d" % (int(s), p))
        a, b = grouped[p][0], grouped[p][1]
        try:
            na, nb = _asvec(a.get("normal")), _asvec(b.get("normal"))
        except (TypeError, ValueError):
            continue
        det = float(na[0] * nb[1] - na[1] * nb[0])
        if det == 0.0 or abs(det) <= _EPS32:
            reject(p, None, "point normals are not independent (determinant %r)" % det)
        completed.add(p)
    if diags:
        raise UnsupportedNativeTranslation(diags)

    # ---- explicit empty outline: graph already validated above ----
    # Zero-contour simple glyphs carry no point data; hmtx still owns
    # advance/lsb, so the native program is an empty no-op. No
    # phantom-point graph support is invented here.
    if n_pts == 0:
        if len(constraints) != 0 or len(order) != 0:
            raise UnsupportedNativeTranslation(
                [dict(point=-1, constraint_id=None,
                      reason="empty points require empty constraints/order")])
        metadata = dict(
            cvt=[],
            operations=[],
            empty_outline=True,
            n_points=0,
            status=("empty outline no-op: zero contours, no instructions; "
                    "hmtx advance/lsb unchanged"),
            isotropic_vectors_required=True,
            caller_must_guarantee_isotropic_vectors=True,
            no_ppem_embedded=True,
            no_phantom_point_support=True,
            cited_sources=list(CITED_SOURCES) + [
                "https://learn.microsoft.com/en-us/typography/opentype/spec/glyf"
                " (simple glyph description: zero contours allowed with no "
                "additional data; phantom-point instructions are separate "
                "support, not implemented here)",
                "hmtx owns advance/lsb, preserved unchanged for empty outlines",
            ],
        )
        return [], metadata

    # ---- per-point freedom + native gate, preserving given group order ----
    cvt = []
    cvt_index = {}

    def cvt_id(v):
        v = int(v)
        if v not in cvt_index:
            cvt_index[v] = len(cvt)
            cvt.append(v)
        return cvt_index[v]

    assembly = (push(1) + ["SZPS[ ]"] + push(1) + ["SLOOP[ ]"] + ["RTG[ ]"]
                + push(32767) + ["SCVTCI[ ]"]
                + push(0) + ["SSWCI[ ]"] + push(0) + ["SSW[ ]"]
                + push(0) + ["SMD[ ]", "FLIPOFF[ ]"])
    operations = []
    diags = []
    for p in order:  # point completion order preserved
        group = grouped[p]  # given group order preserved
        for slot, c in enumerate(group):
            other = _asvec(group[1 - slot]["normal"])
            cur = _asvec(c["normal"])
            freedom = _perp(other)
            if _dot(freedom, cur) < 0:
                freedom = -freedom
            ff = _norm(freedom)
            if ff == 0.0:
                reject(p, int(c["id"]), "degenerate freedom vector")
                continue
            freedom = freedom / ff
            ideal = abs(_dot(freedom, cur))
            qn = [_q14(cur[0]), _q14(cur[1])]
            qf = [_q14(freedom[0]), _q14(freedom[1])]
            if ideal < NATIVE_DOT_CUTOFF:
                reject(p, int(c["id"]),
                       "singular or too-small native dot (ideal %.5f < 1/16)" % ideal)
                continue
            enc_n = [qn[0] / _F214, qn[1] / _F214]
            enc_f = [qf[0] / _F214, qf[1] / _F214]
            denom = math.sqrt(_dot(enc_n, enc_n)) * math.sqrt(_dot(enc_f, enc_f))
            encoded = abs(_dot(enc_n, enc_f) / denom) if denom > 0 else 0.0
            if encoded < NATIVE_DOT_CUTOFF:
                reject(p, int(c["id"]),
                       "encoded normalized dot %.5f < 1/16 (F2.14 quantization)" % encoded)
                continue
            kind = c["kind"]
            val = float(c["value"])
            op_asm = (push(*qn) + ["SPVFS[ ]"] + push(*qf) + ["SFVFS[ ]"])
            detail = {}
            src = [int(s) for s in c.get("sources", [])]
            if kind in ("Abs", "Dist", "PAbs", "PDist"):
                rnd = bool(c.get("round", True))
            if kind == "Abs":
                expected = _dot(pts[p], cur)
                if abs(val - expected) > _EPS32 * max(1.0, abs(expected), abs(val)):
                    reject(p, int(c["id"]), "Abs value must equal original projection")
                    continue
                op_asm += push(p) + ["MDAP[%d]" % (1 if rnd else 0)]
                detail = {"opcode": "MDAP[%d]" % (1 if rnd else 0), "round": rnd}
            elif kind == "PAbs":
                if not _is_int_fu(c["value"]):
                    reject(p, int(c["id"]),
                           "PAbs needs exact signed-16 integer font-unit CVT value, no silent rounding")
                    continue
                op_asm += push(p, cvt_id(int(val))) + ["MIAP[%d]" % (1 if rnd else 0)]
                detail = {"opcode": "MIAP[%d]" % (1 if rnd else 0),
                          "cvt_index": cvt_index[int(val)], "round": rnd}
            elif kind == "Dist":
                s = src[0]
                expected = _dot(pts[p] - pts[s], cur)
                if abs(val - expected) > _EPS32 * max(1.0, abs(expected), abs(val)):
                    reject(p, int(c["id"]), "Dist value must equal original projected distance")
                    continue
                op_asm += push(s) + ["SRP0[ ]"]
                if val == 0.0 and abs(expected) <= _EPS32 * max(1.0, abs(expected)):
                    op_asm += push(p) + ["ALIGNRP[ ]"]
                    detail = {"opcode": "ALIGNRP", "rp0_source": s, "zero_distance": True,
                              "round": rnd}
                else:
                    op_asm += push(p) + ["MDRP[%s]" % ("10100" if rnd else "10000")]
                    detail = {"opcode": "MDRP[%s]" % ("10100" if rnd else "10000"),
                              "rp0_source": s, "rp0_updated": True,
                              "minimum_distance": False, "round": rnd}
            elif kind == "PDist":
                if not _is_int_fu(c["value"]):
                    reject(p, int(c["id"]),
                           "PDist needs exact signed-16 integer font-unit CVT value, no silent rounding")
                    continue
                s = src[0]
                op_asm += push(s) + ["SRP0[ ]"] + push(p, cvt_id(int(val)))
                op_asm += ["MIRP[%s]" % ("10100" if rnd else "10000")]
                detail = {"opcode": "MIRP[%s]" % ("10100" if rnd else "10000"), "rp0_source": s,
                          "cvt_index": cvt_index[int(val)], "rp0_updated": True,
                          "minimum_distance": False, "round": rnd}
            elif kind == "Ratio":
                if "round" not in c or bool(c["round"]):
                    reject(p, int(c["id"]),
                           "rounded Ratio unsupported (explicit round False required)")
                    continue
                a, b = src
                pa, pb, pp = _dot(pts[a], cur), _dot(pts[b], cur), _dot(pts[p], cur)
                span = pb - pa
                if a == b or span == 0.0 \
                        or abs(span) <= _EPS32 * max(1.0, abs(pa), abs(pb)):
                    reject(p, int(c["id"]), "Ratio needs distinct span")
                    continue
                t = (pp - pa) / span
                if abs(val - t) > _EPS32 * max(1.0, abs(t), abs(val)):
                    reject(p, int(c["id"]),
                           "Ratio only supports original source-derived t "
                           "(PRatio/arbitrary values unsupported)")
                    continue
                op_asm += push(a) + ["SRP1[ ]"] + push(b) + ["SRP2[ ]"] + push(p) + ["IP[ ]"]
                detail = {"opcode": "IP[ ]", "rp1": a, "rp2": b, "t": float(t), "round": False}
            else:  # PRatio or anything else parameterised
                reject(p, int(c["id"]), "PRatio/arbitrary authored values unsupported")
                continue
            start = len(assembly)
            assembly += op_asm
            end_exclusive = len(assembly)
            operations.append(dict(point=p, constraint_id=int(c["id"]), kind=kind,
                                   normal_float=_tolist(cur), freedom_float=_tolist(freedom),
                                   normal_q14=list(qn), freedom_q14=list(qf),
                                   ideal_dot=float(ideal), encoded_dot=float(encoded),
                                   assembly_start=start, assembly_end=end_exclusive,
                                   assembly_end_inclusive=end_exclusive - 1,
                                   detail=detail))
    if diags:
        raise UnsupportedNativeTranslation(diags)
    metadata = dict(
        cvt=list(cvt),
        operations=operations,
        support_policy=dict(
            state=["SZPS[1]", "SLOOP[1]", "RTG", "SCVTCI[32767]", "SSWCI[0]", "SSW[0]",
                   "SMD[0]", "FLIPOFF"],
            scvtci=32767,
            note=("large bounded policy; no universal claim. Continued isolated-equation "
                  "experimental policy, not recovered paper defaults."),
        ),
        status="experimental native sequence path",
        isotropic_vectors_required=True,
        caller_must_guarantee_isotropic_vectors=True,
        no_ppem_embedded=True,
        quantization=("Unit vector encoding quantization documented: F2.14 round-nearest; "
                      "preserved-projection claim is approximate in finite precision, "
                      "never exact. Singular or too-small native dots are rejected."),
        cited_sources=list(CITED_SOURCES),
    )
    return assembly, metadata
