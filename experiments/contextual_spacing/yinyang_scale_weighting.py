"""YinYang scale-weighting probe (stage-2 follow-up): sourced V1 scale weights.

Implements the owning design section "YinYang scale weighting revision".
NumPy only; the frozen stage-1/stage-2 modules and the oriented engine are
never modified here. No scalar placement objective, no training, no optical
claim.

Source chain (see owning design for the freeze):
- Manuscript direct-approximation step 2 prescribes summing V1 complex
  responses over scales "according to the desired contrast sensitivity
  function" but publishes no numeric coefficients; the H-CSF0 uniform
  default stands until a sourced numeric CSF justifies otherwise.
- Site CSF/optical-sizing passages prescribe weight-by-scale and state
  mid-scale signals may outcompete fine-scale signals by default
  (qualitative only, no coefficients).
- Pinned notebook log-Gabor bank is the author-offered alternative
  front end (not adopted); ``NormalizeV1.get_scale_coefficients`` is
  log-normal cross-scale pooling for the deferred divisive-normalization
  path (researched, distinguished, never ported as direct-path weights).

Gain compensation (measured per-scale DoG gain, convention recorded) is kept
separate from perceptual weights: unit weights do not balance gains.
Viewing geometry enters only through explicit ``pixels_per_degree``; CSS
zoom is display-only and never enters geometry. Without viewing inputs the
weights stay a scale-index parameterization with declared study
assumptions, never a universal perceptual default.
"""

import hashlib
import math
from pathlib import Path

import numpy as np

import yinyang_oriented_fields as yf

MODEL_IDENTITY = "yinyangfit-scale-weighting-v1"
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

# H-SCALES: frozen half-octave progression around the stage-1 sigma.
FROZEN_SIGMAS = (0.75, 1.0606601717798212, 1.5, 2.1213203435596424, 3.0)
# H-CSF0: neutral uniform default (ablation, not a human-CSF claim).
FROZEN_WEIGHTS = (1.0, 1.0, 1.0, 1.0, 1.0)

# Gain conventions understood by gain_compensated_weights. "measured" uses
# matched-sine reference gains; the rest index per_scale_gains() records.
GAIN_CONVENTIONS = ("impulse_response_peak", "kernel_l1_mean",
                    "kernel_l2_mean", "kernel_peak", "measured")

# Reference-period study choice for matched-sine gains: fixed multiple of
# sigma at which the sigma^-1 amplitude law is verified (recorded, not a
# universal tuning claim).
MATCHED_PERIOD_FACTOR = 4.0


def support_halfwidth_for_sigma(sigma):
    """Stage-1 rule generalized: ceil(4.sigma) (6 px at sigma = 1.5)."""
    return int(math.ceil(4.0 * float(sigma)))


def validate_weights(weights, n_scales):
    """Owning weight gate: finite, nonnegative, covering every scale.

    All-zero is the legitimate explicit-unsupported vector; anything
    negative, nonfinite, or short/long raises before silent clipping.
    """
    checked = tuple(float(w) for w in weights)
    if len(checked) != int(n_scales):
        raise ValueError(
            "scale weights must cover every scale: %d != %d"
            % (len(checked), int(n_scales)))
    for w in checked:
        if not math.isfinite(w):
            raise ValueError(
                "scale weights must be finite and nonnegative, got %r"
                % (weights,))
        if w < 0.0:
            raise ValueError(
                "scale weights must be finite and nonnegative, got %r"
                % (weights,))
    return checked


def combine_scales(c_per_scale, weights):
    """Direct-path combination T = sum_s w_s C_s (fixed-order loop).

    Separately written cross-check of the stage-2 combination: zero weights
    contribute exact zeros, so a single-active weight reproduces that scale
    exactly. Nonfinite or negative weights raise; all-zero yields explicit
    unsupported downstream.
    """
    c = np.asarray(c_per_scale, dtype=np.float64)
    weights = validate_weights(weights, c.shape[0])
    t = np.zeros_like(c[0])
    for w, cs in zip(weights, c):
        t = t + w * cs
    return t


def grating_image(period_px, orientation_rad, shape, contrast=1.0):
    """Zero-mean sinusoidal grating (DC-free probe stimulus).

    The stage-1 even partner is demeaned to zero DC, so a DC pedestal reads
    identically (verified); zero mean keeps the probe independent of that
    gate.
    """
    if not (math.isfinite(period_px) and period_px > 0.0):
        raise ValueError("grating period must be finite and positive")
    ys, xs = np.mgrid[0:shape[0], 0:shape[1]].astype(np.float64)
    return float(contrast) * 0.5 * np.sin(
        2.0 * math.pi
        * (xs * math.cos(orientation_rad) + ys * math.sin(orientation_rad))
        / float(period_px))


def matched_sine_gains(v1_banks, sigmas, period_factor=MATCHED_PERIOD_FACTOR,
                       n_orientations=8, size=96):
    """Per-scale reference amplitude gains at period_factor * sigma.

    Max over V1 orientations of the quadrature magnitude for a zero-mean
    grating at each scale's reference period. The sigma^-1 amplitude law
    (odd DoG scaling) is verified against these measurements, not assumed.
    """
    if not (math.isfinite(period_factor) and period_factor > 0.0):
        raise ValueError("period factor must be finite and positive")
    gains = []
    for bank, sigma in zip(v1_banks, sigmas):
        img = grating_image(float(period_factor) * float(sigma), 0.0,
                            (size, size))
        best = 0.0
        for g in bank[:int(n_orientations)]:
            best = max(best, float(np.abs(yf.convolve_fft(img, g)).max()))
        gains.append(best)
    return tuple(gains)


def gain_compensated_weights(weights, gains, convention="measured",
                             renormalize="sum"):
    """Divide study weights by measured per-scale gains (gain compensation).

    ``gains`` is either a per-scale gain sequence (convention "measured") or
    per_scale_gains() records (named kernel conventions). ``renormalize``
    is "sum" (preserve total weight), "mean" (mean weight 1), or "none".
    Compensation removes the filter-gain imbalance so remaining differences
    express the perceptual study weights, not DoG scaling.
    """
    if convention == "measured":
        seq = tuple(float(g) for g in gains)
    elif convention in ("impulse_response_peak", "kernel_l1_mean",
                        "kernel_l2_mean", "kernel_peak"):
        seq = tuple(float(g[convention]) for g in gains)
    else:
        raise ValueError("gain convention must be one of %r, got %r"
                         % (GAIN_CONVENTIONS, convention))
    weights = validate_weights(weights, len(seq))
    for g in seq:
        if not math.isfinite(g) or g <= 0.0:
            raise ValueError("gains must be finite and positive")
    out = tuple(w / g for w, g in zip(weights, seq))
    if renormalize == "sum":
        total = sum(out)
        if not (math.isfinite(total) and total > 0.0):
            raise ValueError("renormalization needs positive total weight")
        out = tuple(v * (sum(weights) / total) for v in out)
    elif renormalize == "mean":
        mean = sum(out) / len(out)
        if not (math.isfinite(mean) and mean > 0.0):
            raise ValueError("renormalization needs positive mean weight")
        out = tuple(v / mean for v in out)
    elif renormalize != "none":
        raise ValueError(
            "renormalize must be one of ('sum', 'mean', 'none')")
    return out


def log_gaussian_scale_weights(sigmas, peak_sigma_px, bandwidth_oct=1.0,
                               normalize="sum"):
    """Log-Gaussian bandpass study weights over scale (parameterized).

    Form is analogous to the notebook log-normal cross-scale pooling, but
    that pooling belongs to the deferred divisive-normalization path; using
    the shape for direct-path summation weights is a project hypothesis
    with explicit peak/bandwidth study parameters, not a port.
    """
    if not (math.isfinite(peak_sigma_px) and peak_sigma_px > 0.0):
        raise ValueError("peak sigma must be finite and positive")
    if not (math.isfinite(bandwidth_oct) and bandwidth_oct > 0.0):
        raise ValueError("bandwidth must be finite and positive")
    sigmas = tuple(float(s) for s in sigmas)
    raw = tuple(math.exp(-(math.log2(s / peak_sigma_px) ** 2)
                         / (2.0 * bandwidth_oct ** 2)) for s in sigmas)
    if normalize == "sum":
        return tuple(v * (len(raw) / sum(raw)) for v in raw)
    if normalize == "none":
        return raw
    raise ValueError("normalize must be one of ('sum', 'none')")


def require_pixels_per_degree(pixels_per_degree):
    """Explicit viewing-geometry gate: no silent default, no zoom mapping.

    CSS zoom is display-only and never enters geometry; the caller supplies
    physical pixels-per-degree from display and viewing-distance inputs.
    """
    if pixels_per_degree is None:
        raise ValueError(
            "pixels_per_degree is required for degree units; "
            "no universal perceptual default exists")
    ppd = float(pixels_per_degree)
    if not math.isfinite(ppd) or ppd <= 0.0:
        raise ValueError(
            "pixels_per_degree must be finite and positive, got %r"
            % (pixels_per_degree,))
    return ppd


def cpd_for_period_px(period_px, pixels_per_degree):
    """Dimensional identity: cycles/degree = ppd / period_px."""
    ppd = require_pixels_per_degree(pixels_per_degree)
    if not (math.isfinite(period_px) and period_px > 0.0):
        raise ValueError("period must be finite and positive")
    return ppd / float(period_px)


def period_px_for_cpd(cycles_per_degree, pixels_per_degree):
    """Inverse dimensional identity: period_px = ppd / cpd."""
    ppd = require_pixels_per_degree(pixels_per_degree)
    if not (math.isfinite(cycles_per_degree) and cycles_per_degree > 0.0):
        raise ValueError("cycles/degree must be finite and positive")
    return ppd / float(cycles_per_degree)


def mask_change(supported_full, supported_scaled):
    """Quantify support-mask change between two contrast levels.

    Returns dropout/newcomer pixel counts, both support fractions, and the
    common mask on which homogeneous comparison is legitimate. Scaling
    contrast moves pixels across the eps floor, so end-to-end homogeneity
    across different masks is never claimed; the change is the measurement.
    """
    full = np.asarray(supported_full, dtype=bool)
    scaled = np.asarray(supported_scaled, dtype=bool)
    if full.shape != scaled.shape:
        raise ValueError("support masks must share a lattice")
    return {"dropout": int(np.sum(full & ~scaled)),
            "newcomer": int(np.sum(scaled & ~full)),
            "support_full": float(full.mean()),
            "support_scaled": float(scaled.mean()),
            "common": full & scaled}


def scale_shares(c_per_scale, weights):
    """Measured per-scale shares of the combined response energy.

    share_s = sum(w_s C_s) / sum(T) over the lattice (0 where T sums to 0).
    Reports which scales carry the combination under a weight vector.
    """
    c = np.asarray(c_per_scale, dtype=np.float64)
    weights = validate_weights(weights, c.shape[0])
    parts = np.array([float((w * cs).sum())
                      for w, cs in zip(weights, c)])
    total = float(parts.sum())
    if total <= 0.0 or not math.isfinite(total):
        return tuple(0.0 for _ in parts)
    return tuple(float(p / total) for p in parts)
