"""Stage-3 SCORE-v2 interpreter over frozen oriented fields.

G2(s) = sum_{a,b} F(a,b) N(a,b;s) / sqrt(E_L[a] E_R[b]),
N = sum_{p in Omega} cL cR exp(-dD^2/(2 tau^2)) over both-supported pixels,
E[g,o] = sum_{q in own lattice} c[g,o,q]^2 computed ONCE per glyph+channel.

H-NORM/H-FACE/H-TARGET source-founded hypotheses, not upstream prescribed.
See owning design section "YinYang stage-3 SCORE-v2 hypothesis experiment".
"""

import math
import weakref

import numpy as np

import yinyang_oriented_fields as yf

TAU_PX = 0.5
FLOOR_U2 = 1e-6
CSTAR_GRID = (0.0, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 20.0,
              24.0, 32.0, 48.0, 64.0, 96.0, 128.0)
TIE_TOL_FACTOR = 1e-9
G2_BOUND = 128.0

STRENGTH_VARIANTS = ("notebook", "manuscript")
STRENGTH_FIELD_BY_VARIANT = {
    "notebook": "confidence_notebook",
    "manuscript": "arc_strength",
}


def resolve_strength(strength):
    """Name a strength variant to its field key (ValueError otherwise)."""
    if strength not in STRENGTH_FIELD_BY_VARIANT:
        raise ValueError(
            "score strength variant must be one of %r, got %r"
            % (STRENGTH_VARIANTS, strength))
    return STRENGTH_FIELD_BY_VARIANT[strength]


def facing_matrix(n_directed=16):
    """Symmetric facing weights F(a,b) = sin^2((theta_a-theta_b)/2)."""
    thetas = yf.directed_angles(n_directed)
    return np.sin((thetas[:, None] - thetas[None, :]) / 2.0) ** 2


def self_energy(fields, strength="notebook"):
    """Isolated per-channel self-energy over the glyph's own lattice."""
    field = resolve_strength(strength)
    sup = fields["supported"]
    arr = np.where(sup, fields[field], 0.0)
    return np.array([float(np.sum(arr[o] ** 2))
                     for o in range(arr.shape[0])])


def glyph_padded_origin(cell, pad):
    """Native bearing-origin embedding: padded-lattice origin in ink plane."""
    return (float(cell["left"]) - int(pad), float(cell["top"]) - int(pad))


def union_canvas(ls, lo, rs, ro_list):
    """Fixed union canvas over all swept steps (embedding only)."""
    lo = (int(lo[0]), int(lo[1]))
    ros = [(int(ro[0]), int(ro[1])) for ro in ro_list]
    cx = min([lo[0]] + [ro[0] for ro in ros])
    cy = min([lo[1]] + [ro[1] for ro in ros])
    ex = max([lo[0] + ls[1]] + [ro[0] + rs[1] for ro in ros])
    ey = max([lo[1] + ls[0]] + [ro[1] + rs[0] for ro in ros])
    return (cx, cy), (ey - cy, ex - cx)


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


def score_step(lf, rf, lo, ro, canvas_origin, canvas_shape, EL, ER,
               tau=TAU_PX, strength="notebook"):
    """G2 at one integer step on the fixed union canvas."""
    field = resolve_strength(strength)
    n = int(lf["supported"].shape[0])
    F = facing_matrix(n)
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
    raw = 0.0
    norm = 0.0
    floor_num = 0.0
    normalized_floor_num = 0.0
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
            dd = np.abs(dL[a] - dR[b])
            term = np.zeros(canvas_shape, dtype=np.float64)
            kval = np.exp(-dd[both] ** 2 / (2.0 * float(tau) * float(tau)))
            term[both] = cL[a][both] * cR[b][both] * kval
            s = float(np.sum(term))
            raw += w * s
            norm += w * s / den
            floormask = both & ((uL[a] < FLOOR_U2) | (uR[b] < FLOOR_U2))
            weak = w * float(np.sum(term[floormask]))
            floor_num += weak
            normalized_floor_num += weak / den
            both_count += int(np.sum(both))
    floor_share = (normalized_floor_num / norm) if norm > 0.0 else 0.0
    raw_floor_share = (floor_num / raw) if raw > 0.0 else 0.0
    return {"g2": float(norm), "raw": float(raw),
            "floor_share": float(floor_share),
            "raw_floor_share": float(raw_floor_share),
            "both_supported_pairpx": int(both_count)}


class EnergyCache:
    """Per-glyph energies; source strength and support arrays are immutable."""

    def __init__(self):
        self._cache = {}

    def energy(self, key, fields, strength="notebook"):
        ck = (key, str(strength))
        source = fields[resolve_strength(strength)]
        support = fields["supported"]
        hit = self._cache.get(ck)
        if hit is not None and hit[0]() is source and hit[1]() is support:
            return hit[2]
        vec = self_energy(fields, strength)
        # A caller key can recur across captures. Weak references verify
        # the actual field arrays without retaining whole capture tensors.
        self._cache[ck] = (weakref.ref(source), weakref.ref(support), vec)
        return vec


def tie_set(deviations, tol_factor=TIE_TOL_FACTOR):
    """Indices within m* + tol (tol = tol_factor * max(1, m*))."""
    devs = [float(d) for d in deviations]
    mstar = min(devs)
    tol = float(tol_factor) * max(1.0, mstar)
    return [i for i, d in enumerate(devs) if d <= mstar + tol], float(mstar)
