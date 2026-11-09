"""Minimal grouping-score revision using local grouping scale (experiment only).

G3(s;m) = sum_{a,b} F(a,b) N_m(a,b;s) / sqrt(EL[a] ER[b])
N_m(a,b;s) = sum_{p in Omega(s)} cL cR kval(p) sigma(p)^(-m)
sigma(p) = (dL(p) + dR(p)) / 2, kval = exp(-dd^2 / (2 tau^2)).

Article step 6 lists dL+dR as local G-cell scale alongside |dL-dR|,
kL*kR and (oL,oR); the mm/ll argument motivates discounting large-scale
agreements. The sigma^(-m) density form is a project hypothesis, not an
upstream formula. On finite, positive-distance support, m = 0 reproduces
frozen SCORE-v2 G2 exactly. Degenerate non-positive scales abstain instead.
"""

import math

import numpy as np

import yinyang_oriented_score as sc

MODEL_IDENTITY = "yinyangfit-scale-grouping-v1"
SCALE_EXPONENT_PRIMARY = 1.0
TAU_PX = sc.TAU_PX
FLOOR_U2 = sc.FLOOR_U2
TIE_TOL_FACTOR = sc.TIE_TOL_FACTOR

# Predeclared dimensional guess in 1/px, not fitted to any source metric.
T3_GRID = (0.0, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4)


def _check_args(tau, scale_exponent):
    if not math.isfinite(float(tau)) or float(tau) <= 0.0:
        raise ValueError("tau must be finite and positive, got %r" % (tau,))
    if not math.isfinite(float(scale_exponent)) or float(scale_exponent) < 0.0:
        raise ValueError("scale_exponent m must be finite and >= 0, got %r"
                         % (scale_exponent,))


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


def score_step_scale(lf, rf, lo, ro, canvas_origin, canvas_shape, EL, ER,
                     tau=TAU_PX, strength="notebook", scale_exponent=1.0):
    """Scale-discounted agreement G3 plus agreement-weighted mean scale S."""
    _check_args(tau, scale_exponent)
    field = sc.resolve_strength(strength)
    m = float(scale_exponent)
    n = int(lf["supported"].shape[0])
    F = sc.facing_matrix(n)
    cL = [_embed_float(np.where(lf["supported"][o], lf[field][o], 0.0),
                       lo, canvas_origin, canvas_shape) for o in range(n)]
    dL = [_embed_float(np.where(lf["supported"][o], lf["distance"][o], 0.0),
                       lo, canvas_origin, canvas_shape) for o in range(n)]
    sL = [_embed_bool(lf["supported"][o], lo, canvas_origin, canvas_shape)
          for o in range(n)]
    uL = [_embed_float(np.where(lf["supported"][o], lf["U2"][o], np.inf),
                       lo, canvas_origin, canvas_shape) for o in range(n)]
    cR = [_embed_float(np.where(rf["supported"][o], rf[field][o], 0.0),
                       ro, canvas_origin, canvas_shape) for o in range(n)]
    dR = [_embed_float(np.where(rf["supported"][o], rf["distance"][o], 0.0),
                       ro, canvas_origin, canvas_shape) for o in range(n)]
    sR = [_embed_bool(rf["supported"][o], ro, canvas_origin, canvas_shape)
          for o in range(n)]
    uR = [_embed_float(np.where(rf["supported"][o], rf["U2"][o], np.inf),
                       ro, canvas_origin, canvas_shape) for o in range(n)]
    raw2 = 0.0
    raw3 = 0.0
    norm2 = 0.0
    norm3 = 0.0
    floor_num = 0.0
    normalized_floor_num = 0.0
    wsum = 0.0
    ssum = 0.0
    near_ink_raw3 = 0.0
    near_ink_norm3 = 0.0
    sigma_min = float("inf")
    sigma_max = 0.0
    both_count = 0
    for a in range(n):
        for b in range(n):
            w = float(F[a, b])
            if w == 0.0:
                continue
            den = math.sqrt(float(EL[a]) * float(ER[b]))
            if not math.isfinite(den) or den <= 0.0:
                continue
            both = sL[a] & sR[b]
            if not np.any(both):
                continue
            # Pixels with nonfinite distances or non-positive local scale
            # are excluded from every reduction (never zero-wins).
            ds = dL[a] + dR[b]
            ok = both & np.isfinite(dL[a]) & np.isfinite(dR[b]) & (ds > 0.0)
            if not np.any(ok):
                continue
            dd = np.abs(dL[a] - dR[b])
            kval = np.zeros(canvas_shape, dtype=np.float64)
            kval[ok] = np.exp(-dd[ok] ** 2 / (2.0 * float(tau) * float(tau)))
            base = np.zeros(canvas_shape, dtype=np.float64)
            base[ok] = cL[a][ok] * cR[b][ok] * kval[ok]
            if m == 0.0:
                disc = base
            else:
                disc = np.zeros(canvas_shape, dtype=np.float64)
                disc[ok] = base[ok] * (ds[ok] / 2.0) ** (-m)
            s2 = float(np.sum(base))
            s3 = float(np.sum(disc))
            raw2 += w * s2
            raw3 += w * s3
            norm2 += w * s2 / den
            norm3 += w * s3 / den
            floormask = ok & ((uL[a] < FLOOR_U2) | (uR[b] < FLOOR_U2))
            weak = w * float(np.sum(disc[floormask]))
            floor_num += weak
            normalized_floor_num += weak / den
            # Agreement-weighted scale readout (cell-22-style mean scale).
            sig = (ds[ok] / 2.0)
            t = w * base[ok] / den
            wsum += float(np.sum(t))
            ssum += float(np.sum(t * sig))
            near = ok & (ds / 2.0 < 1.0)
            near_raw = w * float(np.sum(disc[near]))
            near_ink_raw3 += near_raw
            near_ink_norm3 += near_raw / den
            if np.any(ok):
                sigma_min = min(sigma_min, float(np.min(sig)))
                sigma_max = max(sigma_max, float(np.max(sig)))
            both_count += int(np.sum(ok))
    floor_share = (normalized_floor_num / norm3) if norm3 > 0.0 else 0.0
    raw_floor_share = (floor_num / raw3) if raw3 > 0.0 else 0.0
    return {"g3": float(norm3), "raw3": float(raw3),
            "g2": float(norm2), "raw2": float(raw2),
            "g3_over_g2": (float(norm3) / float(norm2)
                           if norm2 > 0.0 else float("nan")),
            "scale_mean_px": (float(ssum / wsum)
                              if wsum > 0.0 else float("nan")),
            "scale_min_px": (float(sigma_min)
                             if both_count else float("nan")),
            "scale_max_px": (float(sigma_max)
                             if both_count else float("nan")),
            "near_ink_share": (float(near_ink_norm3 / norm3)
                               if norm3 > 0.0 else 0.0),
            "raw_near_ink_share": (float(near_ink_raw3 / raw3)
                                   if raw3 > 0.0 else 0.0),
            "floor_share": float(floor_share),
            "raw_floor_share": float(raw_floor_share),
            "both_supported_pairpx": int(both_count),
            "abstain": bool(raw3 == 0.0 and both_count == 0)}


def contribution_map_scale(lf, rf, lo, ro, canvas_origin, canvas_shape,
                           EL, ER, tau=TAU_PX, strength="notebook",
                           scale_exponent=1.0):
    """Exact per-pixel G3 summands for one step (sums to the step G3)."""
    _check_args(tau, scale_exponent)
    field = sc.resolve_strength(strength)
    m = float(scale_exponent)
    n = int(lf["supported"].shape[0])
    F = sc.facing_matrix(n)
    out = np.zeros(canvas_shape, dtype=np.float64)
    for a in range(n):
        cLa = _embed_float(np.where(lf["supported"][a], lf[field][a], 0.0),
                           lo, canvas_origin, canvas_shape)
        dLa = _embed_float(np.where(lf["supported"][a], lf["distance"][a], 0.0),
                           lo, canvas_origin, canvas_shape)
        sLa = _embed_bool(lf["supported"][a], lo, canvas_origin, canvas_shape)
        cRb = [_embed_float(np.where(rf["supported"][b], rf[field][b], 0.0),
                            ro, canvas_origin, canvas_shape) for b in range(n)]
        dRb = [_embed_float(np.where(rf["supported"][b], rf["distance"][b], 0.0),
                            ro, canvas_origin, canvas_shape) for b in range(n)]
        sRb = [_embed_bool(rf["supported"][b], ro, canvas_origin, canvas_shape)
               for b in range(n)]
        for b in range(n):
            w = float(F[a, b])
            if w == 0.0:
                continue
            den = math.sqrt(float(EL[a]) * float(ER[b]))
            if not math.isfinite(den) or den <= 0.0:
                continue
            ds = dLa + dRb[b]
            ok = (sLa & sRb[b] & np.isfinite(dLa) & np.isfinite(dRb[b])
                  & (ds > 0.0))
            if not np.any(ok):
                continue
            dd = np.abs(dLa - dRb[b])
            kval = np.exp(-dd[ok] ** 2 / (2.0 * float(tau) * float(tau)))
            if m == 0.0:
                out[ok] += w * cLa[ok] * cRb[b][ok] * kval / den
            else:
                out[ok] += (w * cLa[ok] * cRb[b][ok] * kval
                            * (ds[ok] / 2.0) ** (-m) / den)
    return out


def apply_t3(valid_g3, t3):
    """Deviation-from-scale-target selection (TIE-v2 rule, T3 in 1/px)."""
    if not math.isfinite(float(t3)):
        raise ValueError("T3 target must be finite, got %r" % (t3,))
    devs = [abs(float(g) - float(t3)) for g in valid_g3]
    idx, mstar = sc.tie_set(devs)
    return {"deviations": devs, "mstar": float(mstar), "tie_idx": idx,
            "tie_pick_lowest": min(idx)}
