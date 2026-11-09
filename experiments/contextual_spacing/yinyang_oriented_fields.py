"""YinYang oriented field stage 1: single-scale V1C + directional ratio (cost-free).


Implements the manuscript direct-approximation chain with a frozen single-scale
V1 complex-response input and paired orientation-masked ``r^-q`` / ``r^-(q+1)``
convolutions, producing oriented distance and arc-strength fields plus the four
pair diagnostics. No scalar placement objective, no pair argmin, no cohesion
retuning, no training.

Source foundation (see owning design section "YinYang oriented field stage"):
``docs/source/algorithms.markdown`` direct-approximation steps, V1 complex
response ``S = F^-1(F(I).F(G))`` with ``C = |S|``, and pinned notebook cells 15
and 19 (radial exponent 2, von Mises angular masks doubled to directed
orientations, origin-zeroed radial filters, FFT convolution with ReLU,
``distances = f/d`` where defined, ``confidences = f.(f/d)^(k-1)``).

Symbol disambiguation (upstream ``k`` is overloaded): ``q`` is the radial
exponent, ``a`` the arc strength, ``kappa`` the von Mises concentration. The
hyperbolic-ratio ``(k_{s,gamma}, beta)`` activation is deferred, not used here.

Equation notes (provenance, not narration):
- V1 quadrature uses the manuscript derivative-of-Gaussian pair at scale ``s``.
  The even filter is demeaned over its support so its DC is exactly zero.
- Radial filters are origin-zeroed (source DistanceEst sets the origin to 0),
  so on-support queries draw only on their neighborhood, never on themselves.
- Kernels are raw truncated at radius ``R`` with retained mass recorded; no
  independent numerator/denominator normalization (that would rescale ``d``).
- ``d = U1/U2`` where ``U2 > eps``; elsewhere unsupported (NaN, mask 0).
- Strength branches (both retained, neither optically approved): the
  executable notebook ``confidences = U1 * d^(q-1)`` (cells 15/19) is the
  PRIMARY reference, recorded as ``confidence_notebook``; the manuscript
  ``a = U1 * d^(q+1)`` is retained explicitly as the alternate diagnostic,
  recorded as ``arc_strength``. Provenance status only; values unchanged.
"""

import hashlib
import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_IDENTITY = "yinyangfit-oriented-fields-v1"
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

# Strength-variant selection (source equations, not narration):
# - notebook primary: ``confidences = U1 * d^(q-1)`` (executable cells 15/19).
# - manuscript alternate: ``a = U1 * d^(q+1)`` (direct-approximation step 5).
# Pair diagnostics consume exactly one variant per call; the caller names it
# explicitly so a manuscript diagnostic can never masquerade as primary.
STRENGTH_VARIANTS = ("notebook", "manuscript")
STRENGTH_FIELD_BY_VARIANT = {
    "notebook": "confidence_notebook",
    "manuscript": "arc_strength",
}


@dataclass(frozen=True)
class OrientedFieldParams:
    """Frozen stage-1 parameters (see owning design for the freeze declaration).

    ``radial_exponent_q`` is the source ``k`` in ``f1 = 1/r^q``; ``arc strength``
    is spelled ``a`` (never ``k``); ``angular_concentration_kappa`` is the von
    Mises width (notebook mask width 4), unrelated to either.
    """

    radial_exponent_q: float = 2.0
    angular_concentration_kappa: float = 4.0
    v1_sigma_px: float = 1.5
    v1_support_halfwidth_px: int = 6
    n_v1_orientations: int = 8
    n_directed: int = 16
    kernel_radius_px: int = 12
    denominator_eps: float = 1e-12


DEFAULT_PARAMS = OrientedFieldParams()


def directed_angles(n_directed):
    """Directed channel centers over the full circle."""
    return np.arange(n_directed, dtype=np.float64) * (2.0 * math.pi / n_directed)


def v1_angles(n_orientations):
    """Undirected V1 channel centers over the half circle (0 == 180 deg)."""
    return np.arange(n_orientations, dtype=np.float64) * (math.pi / n_orientations)


def build_v1_bank(params=DEFAULT_PARAMS):
    """Manuscript derivative-of-Gaussian quadrature bank (complex, one scale).

    Returns ``(n_orientations, H, W)`` complex kernels with the even (real-part
    partner) component demeaned to zero DC. Orientation ``j`` rotates the base
    ``gamma = 0`` filter by ``theta = j * pi / n``.
    """
    s = float(params.v1_sigma_px)
    w = int(params.v1_support_halfwidth_px)
    ys, xs = np.mgrid[-w:w + 1, -w:w + 1].astype(np.float64)
    bank = []
    for theta in v1_angles(params.n_v1_orientations):
        c, sn = math.cos(theta), math.sin(theta)
        u = xs * c + ys * sn
        v = -xs * sn + ys * c
        gauss = np.exp(-(u * u + v * v) / (2.0 * s * s))
        odd = u * gauss / (2.0 * math.pi * s ** 4)
        even = gauss / (2.0 * math.pi * s ** 3) - u * u * gauss / (2.0 * math.pi * s ** 5)
        even = even - np.mean(even)
        bank.append(odd + 1j * even)
    return np.asarray(bank)


def convolve_fft(image, kernel):
    """Centered linear convolution via FFT (zero padding, ``same`` mode)."""
    image = np.asarray(image, dtype=np.float64)
    kernel = np.asarray(kernel)
    fh, fw = image.shape
    kh, kw = kernel.shape
    shape = (fh + kh - 1, fw + kw - 1)

    def _fft_conv(a, b):
        return np.fft.irfft2(np.fft.rfft2(a, s=shape) * np.fft.rfft2(b, s=shape), s=shape)

    if np.iscomplexobj(kernel):
        out = _fft_conv(image, kernel.real) + 1j * _fft_conv(image, kernel.imag)
    else:
        out = _fft_conv(image, kernel)
    return np.real_if_close(out[kh // 2:kh // 2 + fh, kw // 2:kw // 2 + fw], tol=1000)


def convolve_direct(image, kernel):
    """Centered linear convolution by explicit summation (oracle, ``same`` mode).

    Independent reference for the FFT path: identical padding/centering
    convention, no shared FFT code.
    """
    image = np.asarray(image, dtype=np.float64)
    kernel = np.asarray(kernel)
    if kernel.shape[0] % 2 == 0 or kernel.shape[1] % 2 == 0:
        raise ValueError("direct oracle requires odd kernel dims (all stage-1 kernels are odd)")
    kernel = kernel[::-1, ::-1]  # true convolution (FFT path parity)
    fh, fw = image.shape
    kh, kw = kernel.shape
    ph, pw = kh // 2, kw // 2
    padded = np.pad(image, ((ph, kh - 1 - ph), (pw, kw - 1 - pw)), mode="constant")
    out = np.zeros((fh, fw), dtype=np.complex128 if np.iscomplexobj(kernel) else np.float64)
    for i in range(kh):
        row = padded[i:i + fh, :]
        for j in range(kw):
            out += kernel[i, j] * row[:, j:j + fw]
    return np.real_if_close(out, tol=1000)


def v1_complex_responses(image, bank=None, params=DEFAULT_PARAMS, method="fft"):
    """Source V1 complex responses ``S`` (one scale, ``n`` orientations)."""
    if bank is None:
        bank = build_v1_bank(params)
    conv = convolve_fft if method == "fft" else convolve_direct
    return np.asarray([conv(np.asarray(image, dtype=np.float64), g) for g in bank])


def v1_magnitudes(image, bank=None, params=DEFAULT_PARAMS, method="fft"):
    """Source V1 complex magnitudes ``C = |S|`` (stage-1 scale-summed tensor)."""
    return np.abs(v1_complex_responses(image, bank=bank, params=params, method=method))


def build_oriented_kernels(params=DEFAULT_PARAMS):
    """Von Mises directed masks times origin-zeroed ``r^-q`` / ``r^-(q+1)``.

    Returns ``(h1, h2, mass1, mass2)`` with ``(n_directed, H, W)`` kernels and
    per-channel retained (truncated) mass. The origin sample is exactly zero,
    following the source DistanceEst filter construction.
    """
    q = float(params.radial_exponent_q)
    kappa = float(params.angular_concentration_kappa)
    rmax = int(params.kernel_radius_px)
    ys, xs = np.mgrid[-rmax:rmax + 1, -rmax:rmax + 1].astype(np.float64)
    r = np.hypot(xs, ys)
    phi = np.arctan2(ys, xs)
    with np.errstate(divide="ignore"):
        f1 = np.where(r == 0.0, 0.0, r ** (-q))
        f2 = np.where(r == 0.0, 0.0, r ** (-(q + 1.0)))
    norm = 2.0 * math.pi * float(np.i0(kappa))
    h1, h2 = [], []
    for theta in directed_angles(params.n_directed):
        mask = np.exp(kappa * np.cos(phi - theta)) / norm
        h1.append(mask * f1)
        h2.append(mask * f2)
    h1, h2 = np.asarray(h1), np.asarray(h2)
    return h1, h2, h1.sum(axis=(1, 2)), h2.sum(axis=(1, 2))


def stage_pad(params=DEFAULT_PARAMS):
    """Field margin: V1 half-support plus kernel radius (gap-covering)."""
    return int(params.v1_support_halfwidth_px) + int(params.kernel_radius_px)


def oriented_fields_for_image(image, params=DEFAULT_PARAMS, v1_bank=None,
                              kernels=None, method="fft", pad=None):
    """Per-glyph oriented fields on a padded pixel lattice (cost-free).

    ``T`` is the single-scale V1 magnitude mapped to directed channels as
    ``T[o] = C[o mod n_v1]`` (adaptation A5). The input is zero-padded by
    ``pad`` (default: V1 half-support plus kernel radius) so gap pixels beside
    the ink carry supported values from both letters at overlay time; padding
    leaves values on the original lattice unchanged. Returns channel arrays
    ``U1, U2, distance, arc_strength, confidence_notebook, supported`` over
    ``n_directed`` channels plus ``C`` (V1 magnitudes), kernel masses, the pad
    and the frozen parameter record. Strength-primary rule: downstream stages
    consume ``confidence_notebook`` (executable notebook reference) first and
    ``arc_strength`` (manuscript alternate diagnostic) only for comparison.
    Callers overlay integer-shifted copies of the padded lattice exactly for
    pair steps, subtracting ``pad`` from the input origin to obtain
    padded-lattice coordinates.
    """
    image = np.asarray(image, dtype=np.float64)
    if not np.isfinite(image).all():
        raise ValueError("oriented_fields_for_image requires a finite image (no NaN/Inf)")
    if pad is None:
        pad = stage_pad(params)
    pad = int(pad)
    conv = convolve_fft if method == "fft" else convolve_direct
    if v1_bank is None:
        v1_bank = build_v1_bank(params)
    if kernels is None:
        kernels = build_oriented_kernels(params)
    h1, h2, mass1, mass2 = kernels
    if pad:
        image = np.pad(image, pad, mode="constant")
    c = np.abs(np.asarray([conv(image, g) for g in v1_bank]))
    t = np.asarray([c[o % params.n_v1_orientations] for o in range(params.n_directed)])
    u1 = np.asarray([conv(np.maximum(t[o], 0.0), h1[o]) for o in range(params.n_directed)])
    u2 = np.asarray([conv(np.maximum(t[o], 0.0), h2[o]) for o in range(params.n_directed)])
    u1 = np.maximum(u1, 0.0)
    u2 = np.maximum(u2, 0.0)
    eps = float(params.denominator_eps)
    supported = np.isfinite(u1) & np.isfinite(u2) & (u2 > eps)
    distance = np.full_like(u1, np.nan)
    distance[supported] = u1[supported] / u2[supported]
    arc_strength = np.zeros_like(u1)
    arc_strength[supported] = u1[supported] * distance[supported] ** (params.radial_exponent_q + 1.0)
    confidence_notebook = np.zeros_like(u1)
    confidence_notebook[supported] = (u1[supported]
                                      * distance[supported] ** (params.radial_exponent_q - 1.0))
    return {
        "model": MODEL_IDENTITY,
        "C": c,
        "T_directed_index": "T[o] = C[o mod %d]" % params.n_v1_orientations,
        "U1": u1,
        "U2": u2,
        "distance": distance,
        "arc_strength": arc_strength,
        "confidence_notebook": confidence_notebook,
        "supported": supported,
        "kernel_mass_1": mass1,
        "kernel_mass_2": mass2,
        "params": params,
        "pad": pad,
        "image_shape": image.shape,
    }


def embed_on_canvas(field, origin, canvas_origin, canvas_shape):
    """Exact integer-offset embedding of a field onto a shared pair canvas."""
    out = np.full(canvas_shape, np.nan, dtype=np.float64)
    ox, oy = int(origin[0]), int(origin[1])
    cx, cy = int(canvas_origin[0]), int(canvas_origin[1])
    h, w = field.shape
    out[oy - cy:oy - cy + h, ox - cx:ox - cx + w] = field
    return out


def _strength_variant_config(strength, params):
    """Resolve a named strength variant to (field key, exponent).

    ``notebook`` selects ``confidence_notebook`` (``U1.d^(q-1)``, primary);
    ``manuscript`` selects ``arc_strength`` (``U1.d^(q+1)``, alternate).
    Raises ``ValueError`` naming both valid variants otherwise.
    """
    if strength not in STRENGTH_FIELD_BY_VARIANT:
        raise ValueError(
            "pair strength variant must be one of %r, got %r"
            % (STRENGTH_VARIANTS, strength))
    q = float(params.radial_exponent_q)
    field = STRENGTH_FIELD_BY_VARIANT[strength]
    exponent = (q - 1.0) if strength == "notebook" else (q + 1.0)
    return field, exponent


def pair_diagnostics(left_fields, right_fields, left_origin, right_origin,
                     params=DEFAULT_PARAMS, *, strength="notebook"):
    """Four source pair quantities per directed channel on the union canvas.

    Reports ``|dL-dR|``, per-variant ``sL.sR``, ``dL+dR`` and the
    orientation-channel pair ``(oL*, oR*)`` with circular agreement, plus
    strength-weighted pooled summaries. ``strength`` selects which per-glyph
    strength array is consumed all the way through (``notebook`` primary by
    default, ``manuscript`` explicitly labeled alternate); distance and mask
    quantities are variant-independent. The returned mapping carries
    ``strength_variant``/``strength_field``/``strength_exponent`` identity so
    an alternate diagnostic cannot masquerade as primary. Diagnostics only:
    no cost, no choice, no minimum is computed.
    """
    strength_field, strength_exponent = _strength_variant_config(strength, params)
    n = int(params.n_directed)
    thetas = directed_angles(n)
    ls, rs = left_fields["image_shape"], right_fields["image_shape"]
    lo = (int(left_origin[0]), int(left_origin[1]))
    ro = (int(right_origin[0]), int(right_origin[1]))
    cx = min(lo[0], ro[0])
    cy = min(lo[1], ro[1])
    ex = max(lo[0] + ls[1], ro[0] + rs[1])
    ey = max(lo[1] + ls[0], ro[1] + rs[0])
    shape = (ey - cy, ex - cx)
    canvas = ((cx, cy), shape)
    dd, prod, psum = [], [], []
    for o in range(n):
        dl = embed_on_canvas(left_fields["distance"][o], lo, (cx, cy), shape)
        dr = embed_on_canvas(right_fields["distance"][o], ro, (cx, cy), shape)
        al = embed_on_canvas(np.where(left_fields["supported"][o],
                                      left_fields[strength_field][o], 0.0),
                             lo, (cx, cy), shape)
        ar = embed_on_canvas(np.where(right_fields["supported"][o],
                                      right_fields[strength_field][o], 0.0),
                             ro, (cx, cy), shape)
        sl = embed_on_canvas(left_fields["supported"][o].astype(float), lo, (cx, cy), shape)
        sr = embed_on_canvas(right_fields["supported"][o].astype(float), ro, (cx, cy), shape)
        both = (sl > 0.5) & (sr > 0.5)
        dd_o = np.full(shape, np.nan)
        dd_o[both] = np.abs(dl[both] - dr[both])
        ps_o = np.full(shape, np.nan)
        ps_o[both] = dl[both] + dr[both]
        pr_o = np.zeros(shape)
        pr_o[both] = al[both] * ar[both]
        dd.append(dd_o)
        prod.append(pr_o)
        psum.append(ps_o)
    dd, prod, psum = map(np.asarray, (dd, prod, psum))
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        # All-unsupported columns yield NaN/-inf reductions; the `both_any`
        # gate below excludes them from every pooled summary.
        warnings.simplefilter("ignore", RuntimeWarning)
        amax_l = np.nanmax(np.where(left_fields["supported"],
                                    left_fields[strength_field], np.nan), axis=0)
        amax_r = np.nanmax(np.where(right_fields["supported"],
                                    right_fields[strength_field], np.nan), axis=0)
        arg_l = np.nanargmax(np.where(left_fields["supported"],
                                      left_fields[strength_field], -np.inf), axis=0)
        arg_r = np.nanargmax(np.where(right_fields["supported"],
                                      right_fields[strength_field], -np.inf), axis=0)
    el = embed_on_canvas(arg_l.astype(float), lo, (cx, cy), shape)
    er = embed_on_canvas(arg_r.astype(float), ro, (cx, cy), shape)
    agreement = np.full(shape, np.nan)
    valid_arg = (~np.isnan(el)) & (~np.isnan(er))
    agreement[valid_arg] = np.cos(thetas[el[valid_arg].astype(int)]
                                 - thetas[er[valid_arg].astype(int)])
    both_any = np.zeros(shape, dtype=bool)
    for o in range(n):
        sl = embed_on_canvas(left_fields["supported"][o], lo, (cx, cy), shape) > 0
        sr = embed_on_canvas(right_fields["supported"][o], ro, (cx, cy), shape) > 0
        both_any |= sl & sr
    pooled = {}
    for name, arr in (("distance_disagreement", dd), ("distance_sum", psum)):
        pooled[name] = {}
        for o in range(n):
            sel = both_any & np.isfinite(arr[o])
            pooled[name][str(o)] = float(np.mean(arr[o][sel])) if np.any(sel) else float("nan")
    pooled["strength_product_total"] = {str(o): float(np.sum(prod[o][both_any])) for o in range(n)}
    pooled["orientation_agreement_mean"] = (float(np.nanmean(agreement[both_any]))
                                           if np.any(both_any) else float("nan"))
    pooled["both_supported_fraction"] = float(np.mean(both_any)) if both_any.size else 0.0
    return {
        "model": MODEL_IDENTITY,
        "strength_variant": strength,
        "strength_field": strength_field,
        "strength_exponent": float(strength_exponent),
        "radial_exponent_q": float(params.radial_exponent_q),
        "canvas_origin": (cx, cy),
        "canvas_shape": shape,
        "distance_disagreement": dd,
        "strength_product": prod,
        "distance_sum": psum,
        "orientation_argmax_left": el,
        "orientation_argmax_right": er,
        "orientation_agreement": agreement,
        "pooled": pooled,
    }
