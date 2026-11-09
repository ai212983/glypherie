"""YinYang multiscale field stage (stage 2): direct-path scale-summed V1C input.

Implements the owning design section "YinYang multiscale field stage": the
manuscript direct path sums V1 complex magnitudes over frequency scales
BEFORE the oriented ratio (``T = sum_s w_s . C_s`` per orientation), then
runs the unchanged stage-1 ratio stage (same ``q``, ``kappa``, ``R``,
``eps``). Per-scale responses are retained and the single-scale limiting
case reproduces stage 1 exactly. No scalar placement objective, no pair
argmin, no cohesion retuning, no training.

Equation/provenance notes only (see owning design for the freeze):
- Manuscript step 2: sum V1C over scales per the desired CSF. The article
  prescribes no numeric weights; the frozen default is neutral uniform
  (H-CSF0 ablation, not a human-CSF claim). Custom explicit weight vectors
  are function input for declared ablations only.
- Per-scale V1 is the manuscript derivative-of-Gaussian quadrature instance
  at ``sigma_s`` (odd = -dG/du, even = -s.d2G/du2, even demeaned to zero
  DC), with support half-width ``ceil(4.sigma_s)`` generalizing stage 1.
- Notebook cross-scale phase coherence / divisive normalization /
  scale-axis-through-ratio / confidence-weighted pooling are NOT inputs
  here (deferred distinct path, never mixed in).
- Strength-primary rule inherited from stage 1: ``confidence_notebook``
  (executable notebook cells 15/19) is the PRIMARY reference;
  ``arc_strength`` (manuscript step 5) is the alternate diagnostic.
- Kernels and pair diagnostics are reused from stage 1 without
  duplication; this module owns only the multiscale V1C input and the
  weighted combination.
"""

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import yinyang_oriented_fields as yf

MODEL_IDENTITY = "yinyangfit-multiscale-fields-v1"
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

# H-SCALES: half-octave geometric progression around the frozen stage-1
# sigma (1.5 px). Fixed a priori; no per-font/per-pair tuning.
CENTER_SIGMA_PX = 1.5
SCALE_STEPS = (-2, -1, 0, 1, 2)


def default_sigmas():
    """Frozen five-scale progression in px (H-SCALES)."""
    return tuple(CENTER_SIGMA_PX * 2.0 ** (k / 2.0) for k in SCALE_STEPS)


def support_halfwidth_for_sigma(sigma):
    """Stage-1 rule generalized: ceil(4.sigma) (6 px at sigma = 1.5)."""
    return int(math.ceil(4.0 * float(sigma)))


@dataclass(frozen=True)
class MultiscaleFieldParams:
    """Frozen stage-2 parameters (see owning design for the freeze).

    ``scale_sigmas_px`` is the H-SCALES progression; ``scale_weights`` is
    the H-CSF0 neutral-uniform default. Both are explicit tuples so any
    ablation records exactly what ran; overrides pass through the
    ``weights`` argument of :func:`multiscale_glyph_fields`.
    """

    scale_sigmas_px: tuple = (0.75, 1.0606601717798212, 1.5,
                              2.1213203435596424, 3.0)
    scale_weights: tuple = (1.0, 1.0, 1.0, 1.0, 1.0)
    n_v1_orientations: int = 8
    n_directed: int = 16


DEFAULT_PARAMS = MultiscaleFieldParams()


def build_multiscale_v1_bank(params=DEFAULT_PARAMS):
    """Per-scale manuscript DoG quadrature banks (complex, one per scale).

    Returns ``(n_scales, n_orientations, H_s, W_s)`` object array of complex
    banks plus the per-scale half-widths; support varies by scale. Bank
    ``s`` at the frozen center sigma with ``ceil(4.sigma)`` support is
    bitwise identical to the stage-1 bank.
    """
    banks, halfwidths = [], []
    for sigma in params.scale_sigmas_px:
        w = support_halfwidth_for_sigma(sigma)
        halfwidths.append(w)
        ys, xs = np.mgrid[-w:w + 1, -w:w + 1].astype(np.float64)
        bank = []
        for theta in yf.v1_angles(params.n_v1_orientations):
            c, sn = math.cos(theta), math.sin(theta)
            u = xs * c + ys * sn
            v = -xs * sn + ys * c
            gauss = np.exp(-(u * u + v * v) / (2.0 * sigma * sigma))
            odd = u * gauss / (2.0 * math.pi * sigma ** 4)
            even = (gauss / (2.0 * math.pi * sigma ** 3)
                    - u * u * gauss / (2.0 * math.pi * sigma ** 5))
            even = even - np.mean(even)
            bank.append(odd + 1j * even)
        banks.append(np.asarray(bank))
    out = np.empty(len(banks), dtype=object)
    out[:] = banks
    return out, tuple(halfwidths)


def per_scale_gains(banks):
    """Recorded per-scale filter gains (interpretation of weights).

    Per scale: kernel L1/L2/peak over the quadrature bank plus the unit
    impulse response peak (max over orientations of |conv| at the impulse
    site neighborhood). Uniform weights emphasize fine scales by peak
    gain; recorded here, not corrected.
    """
    gains = []
    for bank in banks:
        mods = np.abs(np.asarray(bank))
        l1 = float(mods.sum() / mods.shape[0])
        l2 = float(np.sqrt((np.abs(
            np.asarray(bank)) ** 2).sum() / mods.shape[0]))
        peak = float(mods.max())
        probe = np.zeros((31, 31))
        probe[15, 15] = 1.0
        resp = max(float(np.abs(
            yf.convolve_fft(probe, g)).max()) for g in bank)
        gains.append({"kernel_l1_mean": l1, "kernel_l2_mean": l2,
                      "kernel_peak": peak, "impulse_response_peak": resp})
    return gains


def stage_pad_multiscale(params=DEFAULT_PARAMS):
    """Field margin: largest V1 half-support plus kernel radius."""
    return (max(support_halfwidth_for_sigma(s)
                for s in params.scale_sigmas_px)
            + int(yf.DEFAULT_PARAMS.kernel_radius_px))


def _validate_weights(weights):
    """Owning weight gate: finite and nonnegative (all-zero allowed).

    All-zero is the legitimate explicit-unsupported vector (``T = 0`` yields
    no supported pixels downstream); anything negative or nonfinite raises
    before silent clipping or support drop.
    """
    checked = tuple(float(w) for w in weights)
    for w in checked:
        if not math.isfinite(w):
            raise ValueError(
                "scale weights must be finite and nonnegative, got %r" % (weights,))
        if w < 0.0:
            raise ValueError(
                "scale weights must be finite and nonnegative, got %r" % (weights,))
    return checked


def combine_scales(c_per_scale, weights):
    """Direct-path combination: T = sum_s w_s . C_s (fixed order loop).

    ``c_per_scale`` is ``(n_scales, n_orientations, H, W)`` nonnegative.
    Zero weights contribute exact zeros, so a single-active weight vector
    reproduces that scale exactly (limiting-case gate). Nonfinite or
    negative weights raise; the all-zero vector is allowed and yields
    explicit unsupported downstream.
    """
    weights = _validate_weights(weights)
    t = np.zeros_like(c_per_scale[0])
    for w, c in zip(weights, c_per_scale):
        t = t + w * c
    return t


def multiscale_glyph_fields(image, params=DEFAULT_PARAMS, v1_banks=None,
                            kernels=None, weights=None, method="fft",
                            pad=None):
    """Per-glyph multiscale oriented fields (cost-free).

    V1 complex magnitudes are computed per scale, combined by
    :func:`combine_scales`, mapped to directed channels as
    ``T[o] = T_combined[o mod n_v1]`` (stage-1 A5 unchanged), then run
    through the unchanged stage-1 ratio stage. Returns per-scale ``C``,
    combined ``T``, channel ``U1/U2/distance``, primary
    ``confidence_notebook``, alternate ``arc_strength``, ``supported``,
    per-scale gains, weights, sigmas, pad and frozen parameter records.
    Pair diagnostics reuse :func:`yinyang_oriented_fields.pair_diagnostics`
    unchanged. No cost, no choice, no minimum is computed.
    """
    image = np.asarray(image, dtype=np.float64)
    if not np.isfinite(image).all():
        raise ValueError("multiscale_glyph_fields requires a finite image (no NaN/Inf)")
    if weights is None:
        weights = params.scale_weights
    weights = _validate_weights(weights)
    if len(weights) != len(params.scale_sigmas_px):
        raise ValueError("weights must cover every declared scale")
    if v1_banks is None:
        v1_banks, _ = build_multiscale_v1_bank(params)
    if kernels is None:
        kernels = yf.build_oriented_kernels(yf.DEFAULT_PARAMS)
    h1, h2, mass1, mass2 = kernels
    if pad is None:
        pad = stage_pad_multiscale(params)
    pad = int(pad)
    conv = yf.convolve_fft if method == "fft" else yf.convolve_direct
    padded = np.pad(image, pad, mode="constant") if pad else image
    c_per_scale = []
    for bank in v1_banks:
        c_per_scale.append(np.abs(np.asarray(
            [conv(padded, g) for g in bank])))
    c_per_scale = np.asarray(c_per_scale)
    t_combined = combine_scales(c_per_scale, weights)
    t = np.asarray([t_combined[o % params.n_v1_orientations]
                    for o in range(params.n_directed)])
    u1 = np.asarray([conv(np.maximum(t[o], 0.0), h1[o])
                     for o in range(params.n_directed)])
    u2 = np.asarray([conv(np.maximum(t[o], 0.0), h2[o])
                     for o in range(params.n_directed)])
    u1 = np.maximum(u1, 0.0)
    u2 = np.maximum(u2, 0.0)
    q = float(yf.DEFAULT_PARAMS.radial_exponent_q)
    eps = float(yf.DEFAULT_PARAMS.denominator_eps)
    supported = np.isfinite(u1) & np.isfinite(u2) & (u2 > eps)
    distance = np.full_like(u1, np.nan)
    distance[supported] = u1[supported] / u2[supported]
    arc_strength = np.zeros_like(u1)
    arc_strength[supported] = u1[supported] * distance[supported] ** (q + 1.0)
    confidence_notebook = np.zeros_like(u1)
    confidence_notebook[supported] = (
        u1[supported] * distance[supported] ** (q - 1.0))
    banks_list = [np.asarray(b) for b in v1_banks]
    return {
        "model": MODEL_IDENTITY,
        "C_per_scale": c_per_scale,
        "T_combined": t_combined,
        "T_directed_index": "T[o] = T_combined[o mod %d]"
                            % params.n_v1_orientations,
        "U1": u1,
        "U2": u2,
        "distance": distance,
        "arc_strength": arc_strength,
        "confidence_notebook": confidence_notebook,
        "supported": supported,
        "kernel_mass_1": mass1,
        "kernel_mass_2": mass2,
        "per_scale_gains": per_scale_gains(banks_list),
        "scale_sigmas_px": tuple(params.scale_sigmas_px),
        "scale_weights": weights,
        "params": params,
        "stage1_params": yf.DEFAULT_PARAMS,
        "pad": pad,
        "image_shape": padded.shape,
    }


# Re-exported unchanged stage-1 pair quantities (no cost, no choice).
pair_diagnostics = yf.pair_diagnostics
