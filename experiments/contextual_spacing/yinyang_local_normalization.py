"""YinYang local normalization repair pilot (research only, no live change).

Compares normalization classes for the SCORE-v2 whole-glyph dilution defect
(far-stem trio moves MORE than G2; G3 rejected):

- Class O (overlap-only cosine): per channel-pair denominator restricted to
  both-supported pixels, with a per-channel vs all-channel switch. Adapts
  normalized cross-correlation (Lewis 1995: statistics over the overlap
  region, not whole images).
- Class L (local energy): per-glyph local-energy maps with a uniform-disc
  applicability window of inherited radius R. Adapts normalized convolution
  (Knutsson-Westin 1993: signal/certainty split, applicability localizes).
- Class P (pooled scalar, diagnostic comparison only): mean Gaussian-pooled
  c^2 density over the candidate both-union, sigma from the sourced set.
  Present to test the independent spec-review conditional-GO variant; NOT
  adopted (tau-as-pool-width is a new hypothesis: shared px units do not
  justify the role). Its denominator is pooled per glyph on the glyph's own
  lattice (independently cached) but averaged over the CANDIDATE both-union,
  so it stays support-dependent: B2-style contact/support-deletion and
  overlap-area effects are reproduced here, never declared resolved.

Each adaptation is a project hypothesis, NOT a claimed upstream port
(upstream 609d17e8 publishes no completed scalar) and NOT a match to the
independent oracle (which is corroborating research, not a production
formula). See owning design section "YinYang local normalization repair"
for the predeclared falsifiers.
"""

import hashlib
import math
import weakref
from pathlib import Path

import numpy as np

import yinyang_oriented_fields as yf
import yinyang_oriented_score as sc

MODEL_IDENTITY = "yinyangfit-local-normalization-pilot-v1"
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

# Inherited (never tuned here): support floor, kernel width, window radius,
# facing weights, Gaussian kernel width.
EPS = float(yf.DEFAULT_PARAMS.denominator_eps)
RADIUS = int(yf.DEFAULT_PARAMS.kernel_radius_px)
TAU_PX = float(sc.TAU_PX)
FLOOR_U2 = float(sc.FLOOR_U2)
G2_BOUND = float(sc.G2_BOUND)

# Sourced lengthscale set for pools (px): H-TAU2 tau, V1 sigma, kernel
# radius, stage pad. Sigma is frozen from this set a priori, never selected
# on corpus behavior. Tau-as-pool-width is a NEW hypothesis (role), even
# though tau-as-agreement-width is frozen (H-TAU2).
SOURCED_SIGMAS = {"tau": float(sc.TAU_PX),
                  "v1_sigma": float(yf.DEFAULT_PARAMS.v1_sigma_px),
                  "kernel_radius": float(yf.DEFAULT_PARAMS.kernel_radius_px),
                  "pad": float(yf.stage_pad())}

OVERLAP_MODES = ("per-channel", "all-channel")


def gauss_kernel(sigma_px, truncate=4.0):
    """Truncated Gaussian pool kernel normalized to unit sum."""
    r = int(math.ceil(float(truncate) * float(sigma_px)))
    ax = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-(ax ** 2) / (2.0 * float(sigma_px) ** 2))
    k = np.outer(k, k)
    return k / k.sum()


def _embed_float(arr, origin, canvas_origin, canvas_shape):
    out = np.zeros(canvas_shape, dtype=np.float64)
    ox, oy = int(origin[0]) - canvas_origin[0], int(origin[1]) - canvas_origin[1]
    hh, ww = arr.shape
    out[oy:oy + hh, ox:ox + ww] = arr
    return out


def _embed_bool(arr, origin, canvas_origin, canvas_shape):
    out = np.zeros(canvas_shape, dtype=bool)
    ox, oy = int(origin[0]) - canvas_origin[0], int(origin[1]) - canvas_origin[1]
    hh, ww = arr.shape
    out[oy:oy + hh, ox:ox + ww] = np.asarray(arr, dtype=bool)
    return out


def _disc_kernel(radius=RADIUS):
    r = int(radius)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy <= r * r).astype(np.float64)


class LocalEnergyCache:
    """Per-glyph local-energy maps; source arrays immutable (weakref-checked)."""

    def __init__(self, radius=RADIUS):
        self._cache = {}
        self.radius = int(radius)
        self._disc = _disc_kernel(self.radius)

    def maps(self, key, fields, strength="notebook"):
        ck = (key, str(strength), self.radius)
        field = sc.resolve_strength(strength)
        source = fields[field]
        support = fields["supported"]
        hit = self._cache.get(ck)
        if hit is not None and hit[0]() is source and hit[1]() is support:
            return hit[2]
        c2 = np.where(support, np.asarray(source, dtype=np.float64) ** 2, 0.0)
        loc = np.asarray([yf.convolve_fft(c2[o], self._disc)
                          for o in range(c2.shape[0])])
        vec = np.maximum(loc, 0.0)
        self._cache[ck] = (weakref.ref(source), weakref.ref(support), vec)
        return vec


def _per_pair_overlays(lf, rf, lo, ro, canvas_origin, canvas_shape,
                       strength="notebook"):
    """Embed per-channel strengths/distances/supports on the shared canvas."""
    field = sc.resolve_strength(strength)
    n = int(lf["supported"].shape[0])
    out = []
    for o in range(n):
        cL = _embed_float(np.where(lf["supported"][o], lf[field][o], 0.0),
                          lo, canvas_origin, canvas_shape)
        dL = _embed_float(np.where(lf["supported"][o], lf["distance"][o], 0.0),
                          lo, canvas_origin, canvas_shape)
        sL = _embed_bool(lf["supported"][o], lo, canvas_origin, canvas_shape)
        uL = _embed_float(np.where(lf["supported"][o], lf["U2"][o], np.inf),
                          lo, canvas_origin, canvas_shape)
        cR = _embed_float(np.where(rf["supported"][o], rf[field][o], 0.0),
                          ro, canvas_origin, canvas_shape)
        dR = _embed_float(np.where(rf["supported"][o], rf["distance"][o], 0.0),
                          ro, canvas_origin, canvas_shape)
        sR = _embed_bool(rf["supported"][o], ro, canvas_origin, canvas_shape)
        uR = _embed_float(np.where(rf["supported"][o], rf["U2"][o], np.inf),
                          ro, canvas_origin, canvas_shape)
        out.append((cL, dL, sL, uL, cR, dR, sR, uR))
    return out


def _step_record(g, both_count, max_term, weak_norm, n_terms):
    abstain = not bool(n_terms) or not (math.isfinite(g) and g > 0.0)
    return {"g": float(g) if math.isfinite(g) else 0.0,
            "both_supported_pairpx": int(both_count),
            "max_term_cosine": float(max_term),
            "weak_normalized_share": float(weak_norm),
            "eligible_terms": int(n_terms),
            "abstain": bool(abstain)}


def _overlap_terms(chans, tau):
    """Shared per-facing-pair accumulators: (w, N_ab, QL_ab, QR_ab, both)."""
    F = sc.facing_matrix(len(chans))
    terms = []
    for a in range(len(chans)):
        cLa, dLa, sLa, uLa = chans[a][0], chans[a][1], chans[a][2], chans[a][3]
        for b in range(len(chans)):
            w = float(F[a, b])
            if w == 0.0:
                continue
            cRb, dRb, sRb, uRb = chans[b][4], chans[b][5], chans[b][6], chans[b][7]
            both = sLa & sRb
            if not np.any(both):
                continue
            kval = np.exp(-((dLa[both] - dRb[both]) ** 2)
                            / (2.0 * float(tau) * float(tau)))
            n_ab = float(np.sum(cLa[both] * cRb[both] * kval))
            ql = float(np.sum(cLa[both] ** 2))
            qr = float(np.sum(cRb[both] ** 2))
            terms.append({"w": w, "n": n_ab, "ql": ql, "qr": qr,
                          "both": both, "a": a, "b": b,
                          "cL": cLa, "cR": cRb, "uL": uLa, "uR": uRb,
                          "dL": dLa, "dR": dRb})
    return terms


def _weak_normalized_share(terms, g, tau):
    weak_num = 0.0
    for t in terms:
        den = math.sqrt(t["ql"] * t["qr"])
        if not math.isfinite(den) or den <= 0.0:
            continue
        floormask = t["both"] & ((t["uL"] < FLOOR_U2) | (t["uR"] < FLOOR_U2))
        if not np.any(floormask):
            continue
        kval_w = np.exp(-((t["dL"][floormask] - t["dR"][floormask]) ** 2)
                        / (2.0 * float(tau) * float(tau)))
        weak_num += (t["w"] * float(np.sum(t["cL"][floormask]
                                           * t["cR"][floormask] * kval_w))
                     / den)
    return (weak_num / g) if g > 0.0 else 0.0


def score_overlap_cosine(lf, rf, lo, ro, canvas_origin, canvas_shape,
                         tau=TAU_PX, strength="notebook",
                         mode="per-channel"):
    """Class O: overlap-restricted cosine, per-channel or all-channel.

    per-channel: G = sum_ab w_ab N_ab/sqrt(QL_ab QR_ab), in [0, sum w].
    all-channel: G = (sum w) N_tot/sqrt(QL_tot QR_tot) with facing-weighted
    totals, in [0, sum w]. Uniform fields give the flat value sum w in both
    modes (no area bias); they differ only on nonuniform fields.
    """
    if mode not in OVERLAP_MODES:
        raise ValueError("mode must be one of %r, got %r"
                         % (OVERLAP_MODES, mode))
    chans = _per_pair_overlays(lf, rf, lo, ro, canvas_origin, canvas_shape,
                               strength)
    terms = _overlap_terms(chans, tau)
    both_count = sum(int(np.sum(t["both"])) for t in terms)
    max_term = 0.0
    for t in terms:
        den = math.sqrt(t["ql"] * t["qr"])
        if math.isfinite(den) and den > 0.0:
            c = t["n"] / den
            if c > max_term:
                max_term = c
    if mode == "per-channel":
        g = 0.0
        for t in terms:
            den = math.sqrt(t["ql"] * t["qr"])
            if math.isfinite(den) and den > 0.0:
                g += t["w"] * t["n"] / den
    else:
        n_tot = sum(t["w"] * t["n"] for t in terms)
        ql_tot = sum(t["w"] * t["ql"] for t in terms)
        qr_tot = sum(t["w"] * t["qr"] for t in terms)
        w_sum = sum(t["w"] for t in terms)
        den = math.sqrt(ql_tot * qr_tot)
        g = (w_sum * n_tot / den
             if math.isfinite(den) and den > 0.0 else 0.0)
    return _step_record(g, both_count, max_term,
                        _weak_normalized_share(terms, g, tau), len(terms))


def score_local_energy(lf, rf, lo, ro, canvas_origin, canvas_shape,
                       EL, ER, tau=TAU_PX, strength="notebook"):
    """Class L: per-pixel division by independently cached local energies."""
    chans = _per_pair_overlays(lf, rf, lo, ro, canvas_origin, canvas_shape,
                               strength)
    F = sc.facing_matrix(len(chans))
    ELc = [_embed_float(EL[o], lo, canvas_origin, canvas_shape)
           for o in range(len(chans))]
    ERc = [_embed_float(ER[o], ro, canvas_origin, canvas_shape)
           for o in range(len(chans))]
    g = 0.0
    weak_num = 0.0
    both_count = 0
    max_term = 0.0
    n_terms = 0
    for a in range(len(chans)):
        cLa, dLa, sLa, uLa = chans[a][0], chans[a][1], chans[a][2], chans[a][3]
        for b in range(len(chans)):
            w = float(F[a, b])
            if w == 0.0:
                continue
            cRb, dRb, sRb, uRb = chans[b][4], chans[b][5], chans[b][6], chans[b][7]
            both = sLa & sRb & (ELc[a] > 0.0) & np.isfinite(ELc[a]) \
                & (ERc[b] > 0.0) & np.isfinite(ERc[b])
            if not np.any(both):
                continue
            kval = np.exp(-((dLa[both] - dRb[both]) ** 2)
                            / (2.0 * float(tau) * float(tau)))
            contrib = (cLa[both] * cRb[both] * kval
                       / np.sqrt(ELc[a][both] * ERc[b][both]))
            s = float(np.sum(contrib))
            g += w * s
            n_terms += 1
            # Per-term cosine diagnostic on the same support (evidence only).
            n_ab = float(np.sum(cLa[both] * cRb[both] * kval))
            den_ab = math.sqrt(float(np.sum(cLa[both] ** 2))
                               * float(np.sum(cRb[both] ** 2)))
            if den_ab > 0.0 and math.isfinite(den_ab):
                t = n_ab / den_ab
                if t > max_term:
                    max_term = t
            floormask = both & ((uLa < FLOOR_U2) | (uRb < FLOOR_U2))
            weak_num += w * float(np.sum(
                cLa[floormask] * cRb[floormask]
                * np.exp(-((dLa[floormask] - dRb[floormask]) ** 2)
                         / (2.0 * float(tau) * float(tau)))
                / np.sqrt(ELc[a][floormask] * ERc[b][floormask])))
            both_count += int(np.sum(both))
    weak_share = (weak_num / g) if g > 0.0 else 0.0
    # Declared L abstain rule (matches the runtime port): eligible iff at
    # least one term scored and gl is finite and nonnegative. A finite
    # zero with eligible terms is valid zero agreement (eligible); float
    # underflow to zero is value-level indistinguishable and rides the
    # same way. Negative or nonfinite gl is unphysical rounding fallout
    # and abstains as zero local evidence. Class O keeps _step_record.
    if not n_terms or not (math.isfinite(g) and g >= 0.0):
        return {"g": 0.0, "both_supported_pairpx": both_count,
                "max_term_cosine": float(max_term),
                "weak_normalized_share": 0.0,
                "eligible_terms": int(n_terms), "abstain": True}
    return {"g": float(g), "both_supported_pairpx": both_count,
            "max_term_cosine": float(max_term),
            "weak_normalized_share": float(weak_share),
            "eligible_terms": int(n_terms), "abstain": False}


class PooledEnergyCache:
    """Per-glyph Gaussian-pooled c^2 density; sigma from SOURCED_SIGMAS.

    Pooling runs on the glyph's OWN padded lattice, so maps are
    candidate-independent and cacheable (weakref-verified). The per-step
    denominator still averages over the CANDIDATE both-union, so Class P
    stays support-dependent by construction.
    """

    def __init__(self, sigma_px):
        self.sigma_px = float(sigma_px)
        self._kernel = gauss_kernel(self.sigma_px)
        self._cache = {}

    def maps(self, key, fields, strength="notebook"):
        ck = (key, str(strength), self.sigma_px)
        field = sc.resolve_strength(strength)
        source = fields[field]
        support = fields["supported"]
        hit = self._cache.get(ck)
        if hit is not None and hit[0]() is source and hit[1]() is support:
            return hit[2]
        density = np.sum(np.where(support,
                                  np.asarray(source, dtype=np.float64) ** 2,
                                  0.0), axis=0)
        vec = np.maximum(yf.convolve_fft(density, self._kernel), 0.0)
        self._cache[ck] = (weakref.ref(source), weakref.ref(support), vec)
        return vec


def both_union_of(chans):
    """Union over all facing-pair both-sets on the shared canvas."""
    union = None
    for a in range(len(chans)):
        for b in range(len(chans)):
            both = chans[a][2] & chans[b][6]
            union = both if union is None else (union | both)
    return union


def score_pooled(lf, rf, lo, ro, canvas_origin, canvas_shape,
                 ELp, ERp, sigma_px, tau=TAU_PX, strength="notebook"):
    """Class P (diagnostic): scalar pooled denominator over both-union.

    Ebar_L = mean of pooled c^2 over the candidate both-union (same for R);
    G = raw/sqrt(Ebar_L Ebar_R) with raw = sum_ab w_ab N_ab. Dimensionless
    but UNBOUNDED: it scales with overlap area (area bias, tested). Sigma
    must come from SOURCED_SIGMAS; tau-as-pool-width is a new hypothesis.
    Abstains on an empty both-union (no unsupported-zero wins).
    """
    chans = _per_pair_overlays(lf, rf, lo, ro, canvas_origin, canvas_shape,
                               strength)
    union = both_union_of(chans)
    if union is None or not np.any(union):
        return {"g": 0.0, "both_supported_pairpx": 0,
                "max_term_cosine": 0.0, "weak_normalized_share": 0.0,
                "eligible_terms": 0, "abstain": True,
                "ELbar": 0.0, "ERbar": 0.0, "raw": 0.0,
                "sigma_px": float(sigma_px)}
    terms = _overlap_terms(chans, tau)
    ELc = _embed_float(ELp, lo, canvas_origin, canvas_shape)
    ERc = _embed_float(ERp, ro, canvas_origin, canvas_shape)
    el = float(np.mean(ELc[union]))
    er = float(np.mean(ERc[union]))
    den = math.sqrt(el * er)
    raw = sum(t["w"] * t["n"] for t in terms)
    both_count = int(np.sum(union))
    if not (math.isfinite(den) and den > 0.0):
        return {"g": 0.0, "both_supported_pairpx": both_count,
                "max_term_cosine": 0.0, "weak_normalized_share": 0.0,
                "eligible_terms": 0, "abstain": True,
                "ELbar": el, "ERbar": er, "raw": float(raw),
                "sigma_px": float(sigma_px)}
    g = float(raw) / den
    max_term = 0.0
    for t in terms:
        d = math.sqrt(t["ql"] * t["qr"])
        if math.isfinite(d) and d > 0.0:
            c = t["n"] / d
            if c > max_term:
                max_term = c
    # Weak share for the scalar-pooled score: fraction of the RAW numerator
    # from weak-band pixels (same unnormalized units top and bottom).
    weak_raw = 0.0
    for t in terms:
        floormask = t["both"] & ((t["uL"] < FLOOR_U2) | (t["uR"] < FLOOR_U2))
        if not np.any(floormask):
            continue
        kval_w = np.exp(-((t["dL"][floormask] - t["dR"][floormask]) ** 2)
                        / (2.0 * float(tau) * float(tau)))
        weak_raw += t["w"] * float(np.sum(t["cL"][floormask]
                                          * t["cR"][floormask] * kval_w))
    weak_share = (weak_raw / raw) if raw > 0.0 else 0.0
    return {"g": g, "both_supported_pairpx": both_count,
            "max_term_cosine": float(max_term),
            "weak_normalized_share": float(weak_share),
            "eligible_terms": len(terms), "abstain": False,
            "ELbar": el, "ERbar": er, "raw": float(raw),
            "sigma_px": float(sigma_px)}


def confidence_readout(lf, rf, lo, ro, canvas_origin, canvas_shape,
                       strength="notebook"):
    """L/R-symmetric companion readout with stated units (never a selector).

    mass_L/R: sum of per-channel strengths over the both-union, in stage-1
    strength units times px^2 (agreement mass, NOT normalized).
    support_share: |both-union| / |scored domain canvas|, dimensionless.
    Symmetric by construction: identical L/R inputs give identical masses.
    Weak-band mass (U2 < FLOOR) rides alongside with the same units.
    """
    chans = _per_pair_overlays(lf, rf, lo, ro, canvas_origin, canvas_shape,
                               strength)
    union = both_union_of(chans)
    domain = int(canvas_shape[0]) * int(canvas_shape[1])
    if union is None or not np.any(union):
        return {"mass_L": 0.0, "mass_R": 0.0, "weak_mass_L": 0.0,
                "weak_mass_R": 0.0, "support_share": 0.0,
                "both_supported_pairpx": 0, "domain_pairpx": domain}
    mass_L = mass_R = weak_L = weak_R = 0.0
    for a in range(len(chans)):
        for b in range(len(chans)):
            cLa, uLa = chans[a][0], chans[a][3]
            cRb, uRb = chans[b][4], chans[b][7]
            sel = (chans[a][2] & chans[b][6]) & union
            if not np.any(sel):
                continue
            mass_L += float(np.sum(cLa[sel]))
            mass_R += float(np.sum(cRb[sel]))
            wsel = sel & ((uLa < FLOOR_U2) | (uRb < FLOOR_U2))
            weak_L += float(np.sum(cLa[wsel]))
            weak_R += float(np.sum(cRb[wsel]))
    return {"mass_L": mass_L, "mass_R": mass_R,
            "weak_mass_L": weak_L, "weak_mass_R": weak_R,
            "support_share": float(np.sum(union)) / float(domain),
            "both_supported_pairpx": int(np.sum(union)),
            "domain_pairpx": domain}
