"""Restricted segment-site Voronoi dominance intervals for straight pairs.

Hobby section 3.2: the medial axis is the Voronoi diagram of boundary
sites; opposition pruning removes corner branches. Along one straight
bisector center and radius are affine in the overlap parameter. Working
in canonical f in [0,1] over translated and scaled coordinates keeps
every epsilon relative, so translation or uniform scaling cannot change
a verdict. Positive radius, open interior feet and distance to every
other segment bound the intervals; foot-projection endpoints split the
point/line distance pieces, whose equality events are quadratic in
global f. Only open interval interiors are sampled and every sampled
disk is rechecked. Parabolic branches are not traced: contacts with
endpoint feet never qualify, and vertex-dominated cells are unsupported.
Uncertain degree or root abstains the pair instead of guessing.
"""

import math

# Relative float guard in normalized space; never a model gate. Exact
# zero stays exact; only the noise band abstains as uncertain.
EPS = 1e-9

# Single-stage opposition pruning from Hobby section 3.2, Figure 18b: a
# published conservative project choice, not a fitted value. The angle
# is constant on a segment/segment bisector; pairs opposed by less than
# 157 degrees are corner branches, not strokes.
OPP_COS = math.cos(math.radians(157.0))


def corridor(seg_a, seg_b):
    """Shared corridor direction and overlap of two segments.

    Segments are ((x0, y0), (x1, y1)). Directions follow the edges' own
    orientation. Returns None when the overlap is empty.
    """
    (ax0, ay0), (ax1, ay1) = seg_a
    (bx0, by0), (bx1, by1) = seg_b
    adx, ady = ax1 - ax0, ay1 - ay0
    bdx, bdy = bx1 - bx0, by1 - by0
    alen = math.hypot(adx, ady)
    blen = math.hypot(bdx, bdy)
    if alen == 0 or blen == 0:
        return None
    t1 = (adx / alen, ady / alen)
    t2 = (bdx / blen, bdy / blen)
    t2c = t2
    if t1[0] * t2[0] + t1[1] * t2[1] < 0:
        t2c = (-t2[0], -t2[1])
    dx, dy = t1[0] + t2c[0], t1[1] + t2c[1]
    norm = math.hypot(dx, dy)
    if norm == 0:
        return None
    d = (dx / norm, dy / norm)
    t1p = sorted((d[0] * p[0] + d[1] * p[1] for p in ((ax0, ay0), (ax1, ay1))))
    t2p = sorted((d[0] * p[0] + d[1] * p[1] for p in ((bx0, by0), (bx1, by1))))
    lo, hi = max(t1p[0], t2p[0]), min(t1p[1], t2p[1])
    if hi <= lo:
        return None
    return {"d": d, "u": (-d[1], d[0]), "lo": lo, "hi": hi,
            "t1": t1, "t2": t2, "L0": hi - lo}


def frame(seg_a, seg_b, cor):
    """Bisector constants, opposition angle and uncertainty verdict.

    Exact zero stays exact; near-zero sides or determinant in the noise
    band cannot certify the geometry and abstain the pair. The 157
    degree opposition gate is constant on the bisector.
    """
    (ax0, ay0), (ax1, ay1) = seg_a
    (bx0, by0), (bx1, by1) = seg_b
    t1, t2 = cor["t1"], cor["t2"]
    n1 = (-t1[1], t1[0])
    n2 = (-t2[1], t2[0])
    c1 = n1[0] * ax0 + n1[1] * ay0
    c2 = n2[0] * bx0 + n2[1] * by0
    m1 = ((ax0 + ax1) / 2, (ay0 + ay1) / 2)
    m2 = ((bx0 + bx1) / 2, (by0 + by1) / 2)
    s1 = (n1[0] * m2[0] + n1[1] * m2[1]) - c1
    s2 = (n2[0] * m1[0] + n2[1] * m1[1]) - c2
    if s1 == 0 or s2 == 0:
        return {"status": "degenerate-side"}
    L0 = cor.get("L0", 0.0)
    if not L0 > 0:
        return {"status": "degenerate-side"}
    if abs(s1) <= EPS * L0 or abs(s2) <= EPS * L0:
        return {"status": "uncertain-side"}
    s1 = 1.0 if s1 > 0 else -1.0
    s2 = 1.0 if s2 > 0 else -1.0
    opp = (s1 * n1[0]) * (s2 * n2[0]) + (s1 * n1[1]) * (s2 * n2[1])
    if opp > OPP_COS:
        return {"status": "opposition-pruned", "opp": opp}
    u = cor["u"]
    a11 = n1[0] * u[0] + n1[1] * u[1]
    a12 = -s1
    a21 = n2[0] * u[0] + n2[1] * u[1]
    a22 = -s2
    det = a11 * a22 - a12 * a21
    if det == 0:
        return {"status": "degenerate-bisector"}
    if abs(det) <= EPS:
        return {"status": "uncertain-bisector"}
    return {"status": "ok", "n1": n1, "n2": n2, "c1": c1, "c2": c2,
            "s1": s1, "s2": s2, "a11": a11, "a12": a12, "a21": a21,
            "a22": a22, "det": det, "d": cor["d"], "u": u, "t1": t1,
            "t2": t2, "lo": cor["lo"], "hi": cor["hi"], "L0": L0,
            "opp": opp}


def _linear_root(p, q):
    """Root of p*f+q on (0,1): value, uncertain flag, or none.

    Exact zero slope with exact zero value pins the bound and stays
    out of open interiors; a noise-scale slope cannot certify either
    side, so the pair abstains instead of guessing.
    """
    if abs(p) <= EPS:
        if abs(q) <= EPS:
            return ("uncertain", None)
        return ("none", None)
    t = -q / p
    if 0 < t < 1:
        return ("root", t)
    return ("none", None)


def _quad_roots(a, b, c):
    """Roots of a*f^2+b*f+c on (0,1) with explicit degenerate cases.

    Exact zero stays exact. A near-negative discriminant inside the
    uncertainty band abstains before any no-roots decision; tangency at
    exactly zero splits the interval there.
    """
    scale = max(abs(a), abs(b), abs(c))
    if scale <= EPS:
        return [], True
    # Hobby's segment-site equality pieces use g in [0, 1]. In the
    # quadratic Bernstein basis the coefficients are c, c+b/2, c+b+a;
    # their convex hull bounds the polynomial. A strict common sign
    # certifies no local root even when a distant root is near tangent.
    # Round outward and retain the existing relative arithmetic band;
    # this does not relax genuine near-zero/tangency uncertainty.
    middle = math.fsum((c, b / 2.0))
    end = math.fsum((c, b, a))
    lower = min(c, middle, end)
    upper = max(c, middle, end)
    lower = math.nextafter(math.nextafter(lower, -math.inf), -math.inf)
    upper = math.nextafter(math.nextafter(upper, math.inf), math.inf)
    if lower > EPS * scale or upper < -EPS * scale:
        return [], False
    if abs(a) <= EPS * scale:
        if abs(b) <= EPS * scale:
            # Constant sign; the piece midpoint test decides keep/drop.
            return [], False
        t = -c / b
        return ([t] if 0 < t < 1 else []), False
    disc = b * b - 4 * a * c
    if disc == 0.0:
        t = -b / (2 * a)
        return ([t] if 0 < t < 1 else []), False
    if abs(disc) <= EPS * scale * scale:
        return [], True
    if disc < 0:
        return [], False
    root = math.sqrt(disc)
    q = -0.5 * (b + math.copysign(root, b))
    out = []
    for t in (q / a, c / q):
        if 0 < t < 1:
            out.append(t)
    return out, False


def _seg_dist(pt, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    if denom == 0:
        return math.hypot(pt[0] - a[0], pt[1] - a[1]), 0.0
    s = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / denom
    c = min(1.0, max(0.0, s))
    return math.hypot(pt[0] - (a[0] + c * dx), pt[1] - (a[1] + c * dy)), s


def _winding(pt, loops):
    x, y = pt
    total = 0
    for loop in loops:
        a = loop[-1]
        for b in loop:
            if (a[1] <= y) != (b[1] <= y):
                xi = a[0] + (y - a[1]) / (b[1] - a[1]) * (b[0] - a[0])
                if xi > x:
                    total += 1 if b[1] > a[1] else -1
            a = b
    return total


def _affine_system(fr, lo, hi):
    """Center/radius affine coefficients over the frame overlap.

    Solves the pair bisector in translated and scaled coordinates, so
    exact zero stays exact and every later epsilon is relative. The
    parallel case falls on the midpoint line, which is also affine.
    """
    t1, t2 = fr["t1"], fr["t2"]
    par = abs(t1[0] * t2[1] - t1[1] * t2[0]) <= EPS
    if par:
        # Opposed parallel lines share the midpoint line; radius is
        # the half gap. Line 2 sits at n1-coordinate sig_nn*c2 with
        # sig_nn = n1.n2 = +/-1. Zero gap or a degenerate across
        # direction yields no positive radius, hence no intervals.
        n1, n2, u = fr["n1"], fr["n2"], fr["u"]
        sig_nn = n1[0] * n2[0] + n1[1] * n2[1]
        center = (fr["c1"] + sig_nn * fr["c2"]) / 2
        half = abs(fr["c1"] - sig_nn * fr["c2"]) / 2
        a = n1[0] * u[0] + n1[1] * u[1]
        if abs(a) <= EPS:
            return (0.0, 0.0), (0.0, 0.0)
        lam0 = (center - (n1[0] * fr["d"][0] + n1[1] * fr["d"][1]) * lo) / a
        lam_p = -(n1[0] * fr["d"][0] + n1[1] * fr["d"][1]) * (hi - lo) / a
        return (lam0, half), (lam_p, 0.0)
    a11, a12, a21, a22 = fr["a11"], fr["a12"], fr["a21"], fr["a22"]
    det = fr["det"]
    n1, c1, c2 = fr["n1"], fr["c1"], fr["c2"]
    d, u = fr["d"], fr["u"]
    k1 = n1[0] * d[0] + n1[1] * d[1]
    k2 = fr["n2"][0] * d[0] + fr["n2"][1] * d[1]
    b10 = c1 - k1 * lo
    b20 = c2 - k2 * lo
    lam0 = (a22 * b10 - a12 * b20) / det
    sig0 = (a11 * b20 - a21 * b10) / det
    lam_p = (a22 * (-k1) - a12 * (-k2)) / det * (hi - lo)
    sig_p = (a11 * (-k2) - a21 * (-k1)) / det * (hi - lo)
    return (lam0, sig0), (lam_p, sig_p)


def _coincides(pt, ends):
    """Exact shared-vertex test on common normalized coordinates."""
    return any(pt[0] == e[0] and pt[1] == e[1] for e in ends)


def _foot_frac(c, p0, p1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    den = dx * dx + dy * dy
    if den == 0:
        return None
    return ((c[0] - p0[0]) * dx + (c[1] - p0[1]) * dy) / den


def _center_at(fr, lam0, lam_p, t):
    d, u = fr["d"], fr["u"]
    f = (t - fr["lo"]) / (fr["hi"] - fr["lo"])
    lam = lam0 + lam_p * f
    return (d[0] * t + u[0] * lam, d[1] * t + u[1] * lam)


def _contact_eval(fr, lam_sig, seg_a, seg_b, t, others, loops):
    """Normalized medial contact at corridor parameter t.

    Endpoint-dominated contacts never qualify: vertex-dominated cells
    and parabolic branches are unsupported. Clearance holds against
    every other segment; equality within the relative band abstains as
    near-tangent instead of passing.
    """
    (lam0, sig0), (lam_p, sig_p) = lam_sig
    f = (t - fr["lo"]) / (fr["hi"] - fr["lo"])
    sig = sig0 + sig_p * f
    if not sig > 0:
        return {"hit": None, "stage": "nonpositive-radius", "tag": None}
    c = _center_at(fr, lam0, lam_p, t)
    sa = _foot_frac(c, seg_a[0], seg_a[1])
    sb = _foot_frac(c, seg_b[0], seg_b[1])
    if sa is None or sb is None:
        return {"hit": None, "stage": "degenerate-pair", "tag": None}
    if not 0 < sa < 1:
        return {"hit": None, "stage": "endpoint-foot-a", "tag": None}
    if not 0 < sb < 1:
        return {"hit": None, "stage": "endpoint-foot-b", "tag": None}
    if loops is not None and _winding(c, loops) == 0:
        return {"hit": None, "stage": "outside-fill", "tag": None}
    band = EPS * max(1.0, sig)
    for o in others:
        (ax, ay), (bx, by) = o["seg"]
        dist, _ = _seg_dist(c, (ax, ay), (bx, by))
        if dist < sig - band:
            return {"hit": None, "stage": "third-contact",
                    "tag": o["tag"]}
        if abs(dist - sig) <= band:
            return {"hit": None, "stage": "uncertain-clearance",
                    "tag": o["tag"]}
    (ax0, ay0), (ax1, ay1) = seg_a
    (bx0, by0), (bx1, by1) = seg_b
    qa = (ax0 + sa * (ax1 - ax0), ay0 + sa * (ay1 - ay0))
    qb = (bx0 + sb * (bx1 - bx0), by0 + sb * (by1 - by0))
    return {"hit": {"center": c, "r": sig, "width": 2 * sig,
                    "qa": qa, "qb": qb, "sa": sa, "sb": sb},
            "stage": "clear", "tag": None}


def _setup(seg_a, seg_b):
    """Raw corridor plus translation/scale normalization bundle.

    O is an input vertex and L0 the raw overlap length, so translating
    or uniformly scaling every input leaves the canonical verdict
    unchanged. Canonical f in [0,1] maps to raw t by lo+L0*f.
    """
    cor = corridor(seg_a, seg_b)
    if cor is None:
        return {"status": "no-overlap"}
    L0 = cor["hi"] - cor["lo"]
    O = seg_a[0]

    def xf(p):
        return ((p[0] - O[0]) / L0, (p[1] - O[1]) / L0)

    a = (xf(seg_a[0]), xf(seg_a[1]))
    b = (xf(seg_b[0]), xf(seg_b[1]))
    d = cor["d"]
    base = d[0] * O[0] + d[1] * O[1]
    nlo = (cor["lo"] - base) / L0
    nhi = (cor["hi"] - base) / L0
    cor_n = {"d": d, "u": cor["u"], "lo": nlo, "hi": nhi,
             "t1": cor["t1"], "t2": cor["t2"], "L0": nhi - nlo}
    fr = frame(a, b, cor_n)
    if fr["status"] != "ok":
        return {"status": fr["status"], "opp": fr.get("opp")}
    lam_sig = _affine_system(fr, nlo, nhi)
    return {"status": "ok", "A": a, "B": b, "fr": fr, "lam_sig": lam_sig,
            "O": O, "L0": L0, "lo": cor["lo"], "hi": cor["hi"],
            "nlo": nlo, "nhi": nhi}


def _norm_seg(seg, O, L0):
    (ax, ay), (bx, by) = seg
    return (((ax - O[0]) / L0, (ay - O[1]) / L0),
            ((bx - O[0]) / L0, (by - O[1]) / L0))


def _norm_loops(loops, O, L0):
    if loops is None:
        return None
    return [[((p[0] - O[0]) / L0, (p[1] - O[1]) / L0) for p in loop]
            for loop in loops]


def contact(seg_a, seg_b, t, others, loops):
    """Medial contact at corridor parameter t with full guards.

    t is the actual corridor projection in caller units. others
    exclude the pair's own segments; each entry carries an opaque tag
    reported on third contact.
    """
    setup = _setup(seg_a, seg_b)
    if setup["status"] != "ok":
        stage = ("outside-overlap" if setup["status"] == "no-overlap"
                 else "degenerate-frame")
        return {"hit": None, "stage": stage, "tag": None,
                "status": setup["status"]}
    lo, hi, L0, O = setup["lo"], setup["hi"], setup["L0"], setup["O"]
    if not lo < t < hi:
        return {"hit": None, "stage": "outside-overlap", "tag": None,
                "status": "ok"}
    fr = setup["fr"]
    f = (t - lo) / (hi - lo)
    tn = setup["nlo"] + (setup["nhi"] - setup["nlo"]) * f
    on = [{"seg": _norm_seg(o["seg"], O, L0), "tag": o["tag"]}
          for o in others]
    out = _contact_eval(fr, setup["lam_sig"], setup["A"], setup["B"], tn,
                        on, _norm_loops(loops, O, L0))
    hit = out["hit"]
    if hit is not None:
        hit = dict(hit)
        hit["center"] = (O[0] + L0 * hit["center"][0],
                         O[1] + L0 * hit["center"][1])
        hit["r"] = L0 * hit["r"]
        hit["width"] = L0 * hit["width"]
        hit["qa"] = (O[0] + L0 * hit["qa"][0], O[1] + L0 * hit["qa"][1])
        hit["qb"] = (O[0] + L0 * hit["qb"][0], O[1] + L0 * hit["qb"][1])
    return {"hit": hit, "stage": out["stage"], "tag": out["tag"],
            "status": "ok"}


def _eval_f_c(fr, lam_sig, seg_a, seg_b, f, nlo, nhi):
    (lam0, sig0), (lam_p, sig_p) = lam_sig
    tn = nlo + (nhi - nlo) * f
    c = _center_at(fr, lam0, lam_p, tn)
    sig = sig0 + sig_p * f
    sa = _foot_frac(c, seg_a[0], seg_a[1])
    sb = _foot_frac(c, seg_b[0], seg_b[1])
    return c, sig, sa, sb


def dominance(seg_a, seg_b, others, loops):
    """Open dominance intervals of the pair over canonical f in [0,1].

    Splits at open foot interiors, positive radius, competitor
    projection endpoints on both sides, and quadratic equality events
    in global f; every sampled midpoint is rechecked. Returns raw
    corridor endpoints, the medial speed per corridor unit, and the
    per-piece stage/tag reasons.
    """
    setup = _setup(seg_a, seg_b)
    if setup["status"] != "ok":
        return {"status": setup["status"], "intervals": [],
                "spans": [], "speed": None, "opp": setup.get("opp")}
    fr, lam_sig = setup["fr"], setup["lam_sig"]
    A, B = setup["A"], setup["B"]
    O, L0 = setup["O"], setup["L0"]
    lo, hi = setup["lo"], setup["hi"]
    nlo, nhi = setup["nlo"], setup["nhi"]
    on = [{"seg": _norm_seg(o["seg"], O, L0), "tag": o["tag"]}
          for o in others]
    ln = _norm_loops(loops, O, L0)
    (lam0, sig0), (lam_p, sig_p) = lam_sig

    def center(f):
        return _center_at(fr, lam0, lam_p, nlo + (nhi - nlo) * f)

    splits = {0.0, 1.0}
    # Foot bounds and radius bound are linear in f by the affine
    # bisector; two-point values give global-f roots directly.
    for get in (lambda f: _foot_frac(center(f), A[0], A[1]),
                lambda f: _foot_frac(center(f), B[0], B[1])):
        v0, v1 = get(0.0), get(1.0)
        if v0 is None or v1 is None:
            return {"status": "degenerate-pair", "intervals": [],
                    "spans": [], "speed": None, "opp": setup.get("opp")}
        for edge in (0.0, 1.0):
            kind, root = _linear_root(v1 - v0, v0 - edge)
            if kind == "uncertain":
                return {"status": "uncertain-foot", "intervals": [],
                        "spans": [], "speed": None, "opp": setup.get("opp")}
            if kind == "root":
                splits.add(root)
    for edge in (0.0,):
        kind, root = _linear_root(sig_p, sig0 - edge)
        if kind == "uncertain":
            return {"status": "uncertain-radius", "intervals": [],
                    "spans": [], "speed": None, "opp": setup.get("opp")}
        if kind == "root":
            splits.add(root)
    # Competitor projection endpoints split point/line pieces on both
    # sides; equality events are quadratics in global f.
    for o in on:
        (ax, ay), (bx, by) = o["seg"]
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        if den == 0:
            continue
        c0, c1 = center(0.0), center(1.0)
        s0 = ((c0[0] - ax) * dx + (c0[1] - ay) * dy) / den
        s1 = ((c1[0] - ax) * dx + (c1[1] - ay) * dy) / den
        for edge in (0.0, 1.0):
            kind, root = _linear_root(s1 - s0, s0 - edge)
            if kind == "uncertain":
                return {"status": "uncertain-projection",
                        "intervals": [], "spans": [],
                        "speed": None, "opp": setup.get("opp")}
            if kind == "root":
                splits.add(root)
    pts = sorted(splits)
    cuts = []
    for i in range(len(pts) - 1):
        l, r = pts[i], pts[i + 1]
        if r - l <= 1e-12:
            continue
        cuts.append((l, r))
    intervals, spans = [], []
    d, u = fr["d"], fr["u"]
    for (l, r) in cuts:
        m = (l + r) / 2
        cm, _, _, _ = _eval_f_c(fr, lam_sig, A, B, m, nlo, nhi)
        branch = {}
        for o in on:
            (ax, ay), (bx, by) = o["seg"]
            dx, dy = bx - ax, by - ay
            den = dx * dx + dy * dy
            if den == 0:
                branch[o["tag"]] = ("point", (ax, ay))
            else:
                sm = ((cm[0] - ax) * dx + (cm[1] - ay) * dy) / den
                if sm <= 0:
                    branch[o["tag"]] = ("point", (ax, ay))
                elif sm >= 1:
                    branch[o["tag"]] = ("point", (bx, by))
                else:
                    ex = ax + sm * dx
                    ey = ay + sm * dy
                    branch[o["tag"]] = ("line", (ax, ay, dx, dy, ex, ey))
        # Three-point interpolation gives global-f quadratic
        # coefficients; tangency and near-tangent bands abstain. A
        # point branch at a shared paired endpoint is never re-solved:
        # |C-V|^2-r^2 = |foot-V|^2 by Pythagoras, so the only zero is
        # the already-split foot event and solving reads float noise.
        for o in on:
            kind, data = branch[o["tag"]]
            if kind == "point" and _coincides(
                    data, (A[0], A[1], B[0], B[1])):
                continue
            qs = []
            for f in (l, m, r):
                cf, sigf, _, _ = _eval_f_c(fr, lam_sig, A, B, f, nlo, nhi)
                if kind == "point":
                    (ex, ey) = data
                else:
                    (ax_b, ay_b, dx, dy, _, _) = data
                    sm = ((cf[0] - ax_b) * dx +
                          (cf[1] - ay_b) * dy) / (dx * dx + dy * dy)
                    ex = ax_b + sm * dx
                    ey = ay_b + sm * dy
                qs.append((cf[0] - ex) ** 2 + (cf[1] - ey) ** 2
                          - sigf * sigf)
            q0, q1, q2 = qs
            qa = 2 * (q0 - 2 * q1 + q2)
            qb = 4 * q1 - 3 * q0 - q2
            qc = q0
            roots, uncertain = _quad_roots(qa, qb, qc)
            if uncertain:
                return {"status": "uncertain-equality",
                        "intervals": [], "spans": [],
                        "speed": None, "opp": setup.get("opp")}
            for g in roots:
                splits.add(l + g * (r - l))
    # Second pass after equality splits: every piece midpoint decides
    # its own span, so constant-sign pieces keep or drop on evidence.
    pts = sorted(splits)
    cuts = []
    for i in range(len(pts) - 1):
        l, r = pts[i], pts[i + 1]
        if r - l <= 1e-12:
            continue
        cuts.append((l, r))
    (_, _), (lam_pb, _) = lam_sig
    speed = math.hypot(d[0] * (nhi - nlo) + u[0] * lam_pb,
                       d[1] * (nhi - nlo) + u[1] * lam_pb)
    kept = []
    for (l, r) in cuts:
        m = (l + r) / 2
        tn = nlo + (nhi - nlo) * m
        out = _contact_eval(fr, lam_sig, A, B, tn, on, ln)
        span = {"f0": l, "f1": r, "kept": out["hit"] is not None,
                "stage": out["stage"], "tag": out["tag"]}
        spans.append(span)
        if out["hit"] is not None:
            kept.append((l, r))
    # Merge adjacent kept cells whose shared boundary itself passes the
    # strict contact guard: projection splits can cut one valid branch,
    # and sampling wants the uncut interval. A third-contact boundary
    # never merges.
    merged = []
    for (l, r) in kept:
        if merged and merged[-1][1] == l:
            tn = nlo + (nhi - nlo) * l
            if _contact_eval(fr, lam_sig, A, B, tn, on, ln)["hit"] \
                    is not None:
                merged[-1] = (merged[-1][0], r)
                continue
        merged.append((l, r))
    for (l, r) in merged:
        intervals.append({"lo": lo + L0 * l, "hi": lo + L0 * r,
                          "speed": speed})
    return {"status": "ok", "intervals": intervals, "spans": spans,
            "speed": speed, "opp": setup.get("opp")}


def core_intervals(seg_a, seg_b, kept, others, loops, margin=EPS):
    """Certified core of retained dominance intervals.

    Kept boundaries are float equality events with arithmetic
    uncertainty; ownership is certified only away from them. Each end
    retreats by margin of the corridor span, using the module's own
    relative guard rather than any fitted value. Emptied intervals
    drop, and every surviving midpoint is rechecked with full guards.
    """
    setup = _setup(seg_a, seg_b)
    if setup["status"] != "ok":
        return None
    span = setup["hi"] - setup["lo"]
    if not span > 0:
        return None
    trim = margin * span
    out = []
    for iv in kept:
        lo, hi = iv["lo"] + trim, iv["hi"] - trim
        if not hi > lo:
            continue
        seen = contact(seg_a, seg_b, (lo + hi) / 2, others, loops)
        if seen.get("status") != "ok" or seen.get("hit") is None:
            continue
        out.append({"lo": lo, "hi": hi})
    return out


def foot_ranges(seg_a, seg_b, kept):
    """Affine contact-foot ranges over retained dominance intervals.

    Hobby 3.2 assigns each medial point to its nearest boundary sites;
    center and feet are affine in the corridor parameter, so each kept
    interval maps to foot ranges bounded by its endpoint values. Any
    degenerate evaluation fails closed with None instead of guessing.
    """
    setup = _setup(seg_a, seg_b)
    if setup["status"] != "ok":
        return None
    fr, lam_sig = setup["fr"], setup["lam_sig"]
    A, B = setup["A"], setup["B"]
    lo, hi = setup["lo"], setup["hi"]
    nlo, nhi = setup["nlo"], setup["nhi"]
    span = hi - lo
    if not span > 0:
        return None
    (lam0, _), (lam_p, _) = lam_sig
    out = []
    for iv in kept:
        fas, fbs = [], []
        for t in (iv["lo"], iv["hi"]):
            f = (t - lo) / span
            if not 0 <= f <= 1:
                return None
            tn = nlo + (nhi - nlo) * f
            c = _center_at(fr, lam0, lam_p, tn)
            fa = _foot_frac(c, A[0], A[1])
            fb = _foot_frac(c, B[0], B[1])
            if fa is None or fb is None:
                return None
            fas.append(fa)
            fbs.append(fb)
        out.append({"a": (min(fas), max(fas)),
                    "b": (min(fbs), max(fbs))})
    return out
