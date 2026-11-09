//! Experimental Class-L local normalization (score model
//! `yinyangfit-local-energy-v2`).
//!
//! The v1 G2 scorer in `score.rs` stays a frozen oracle; this module owns
//! the local-energy path only. Per-pixel normalized agreement
//! `w * cL * cR * K / sqrt(EL * ER)` over both-supported pixels, with the
//! per-glyph local-energy maps `EL = disc(R) (*) c^2` computed on the
//! glyph's own padded lattice. Raw FFT energies are kept (no silent
//! clipping); non-positive or nonfinite denominators skip the summand
//! and are counted, and the center-inclusive shortfall is reported per
//! step for the stated numeric bound.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use rustfft::num_complex::Complex;

use crate::fft::Conv;
use crate::fields::GlyphFields;
use crate::params::FLOOR_U2;
use crate::score::Strength;
use crate::EngineError;

/// Abstain reasons for the local path (intentional new rule; see
/// contract). A valid zero agreement (`gl == 0` with eligible terms) is
/// NOT abstain.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LocalAbstain {
    /// Empty both-union (same condition as the G2 abstain path).
    NoSharedSupport,
    /// Both-supported pixels exist but no eligible normalized
    /// contribution (all local energies non-positive/nonfinite, all
    /// strengths zero, or float underflow).
    ZeroLocalEvidence,
}

impl LocalAbstain {
    pub fn as_str(&self) -> &'static str {
        match self {
            LocalAbstain::NoSharedSupport => "no_shared_support",
            LocalAbstain::ZeroLocalEvidence => "zero_local_evidence",
        }
    }
}

/// One Class-L scored step.
#[derive(Debug, Clone)]
pub struct LocalStepScore {
    pub gl: f64,
    pub both_supported_pairpx: u64,
    pub weak_normalized_share: f64,
    pub max_term_cosine: f64,
    pub abstain: bool,
    pub abstain_reason: Option<LocalAbstain>,
    pub skipped_nonpositive: u64,
    pub conditioning_shortfall: f64,
    pub honest_bound: f64,
}

/// L/R-symmetric agreement readout over the support union (informational).
/// Masses are raw strength sums (NOT normalized-score mass in gl units,
/// NOT pooled energies); confidence never gates and never reads EL.
/// Every count here is support-only: canvas pixels and raw masses over
/// the support overlap, never the energy-eligible scored sets.
#[derive(Debug, Clone)]
pub struct LocalConfidence {
    pub support_mass_l: f64,
    pub support_mass_r: f64,
    pub support_weak_mass_l: f64,
    pub support_weak_mass_r: f64,
    pub support_share: f64,
    /// Union canvas pixels with overlapping support (support-only count,
    /// NOT the energy-gated scored pair-px of `LocalStepScore`).
    pub support_union_pairpx: u64,
}

/// Uniform-disc applicability window (odd side `2*radius+1`).
pub fn disc_kernel(radius: u32) -> (Vec<f64>, usize) {
    let r = radius as usize;
    let side = 2 * r + 1;
    let mut k = vec![0.0; side * side];
    for y in 0..side {
        for x in 0..side {
            let dx = x as i64 - r as i64;
            let dy = y as i64 - r as i64;
            if dx * dx + dy * dy <= (r as i64) * (r as i64) {
                k[y * side + x] = 1.0;
            }
        }
    }
    (k, side)
}

/// Per-channel local-energy maps on the glyph's own padded lattice.
///
/// Stable nonnegative direct summation of the center-inclusive disc
/// (same formula, same padding/centering as the retired FFT path —
/// symmetric disc, so kernel flip is identity). No FFT rounding, no
/// clipping, no floor: sums of nonnegative f64 terms in fixed order
/// are nonnegative by construction, and center inclusion holds up to
/// the stated summation bound (`ntaps * eps * max`, derived from the
/// tap count, never tuned). Summation order is fixed in code, so the
/// maps are bitwise identical across build profiles and targets.
/// Cached once per glyph per (strength, radius) by the caller.
pub fn local_energy_maps(
    fields: &GlyphFields,
    radius: u32,
    strength: Strength,
) -> Vec<Vec<f64>> {
    let (kernel, side) = disc_kernel(radius);
    let r = radius as usize;
    // Fixed tap order; zero taps skipped (exact, not an approximation).
    let mut taps = Vec::new();
    for ky in 0..side {
        for kx in 0..side {
            if kernel[ky * side + kx] != 0.0 {
                taps.push((ky, kx));
            }
        }
    }
    let n = fields.supported.len();
    let mut out = Vec::with_capacity(n);
    for o in 0..n {
        let src_field: &[f64] = match strength {
            Strength::Notebook => &fields.conf_nb[o],
            Strength::Manuscript => &fields.arc[o],
        };
        let src: Vec<f64> = src_field
            .iter()
            .zip(fields.supported[o].iter())
            .map(|(v, s)| if *s { v * v } else { 0.0 })
            .collect();
        // Pad like `conv_direct`: image at offset (r, r), same output.
        let gw = fields.w + side - 1;
        let mut pad = vec![0.0; (fields.h + side - 1) * gw];
        for y in 0..fields.h {
            pad[(y + r) * gw + r..(y + r) * gw + r + fields.w]
                .copy_from_slice(&src[y * fields.w..(y + 1) * fields.w]);
        }
        let mut map = vec![0.0; fields.w * fields.h];
        for y in 0..fields.h {
            for x in 0..fields.w {
                let mut acc = 0.0;
                for (ky, kx) in &taps {
                    acc += pad[(y + ky) * gw + x + kx];
                }
                map[y * fields.w + x] = acc;
            }
        }
        out.push(map);
    }
    out
}

/// Independent direct-convolution reference for one channel map: explicit
/// Complex summation in tap-outer order (a different summation order from
/// the production path), same centering. Cross-checks the production
/// maps within the operator-derived agreement bound.
pub fn local_energy_direct(
    channel_c2: &[f64],
    w: usize,
    h: usize,
    radius: u32,
) -> Vec<f64> {
    let (kernel, side) = disc_kernel(radius);
    let kc: Vec<Complex<f64>> = kernel.iter().map(|v| Complex::new(*v, 0.0)).collect();
    let img: Vec<Complex<f64>> = channel_c2.iter().map(|v| Complex::new(*v, 0.0)).collect();
    Conv::conv_direct(&img, w, h, &kc, side, side)
        .iter()
        .map(|c| c.re)
        .collect()
}

struct Embedded {
    c: Vec<f64>,
    d: Vec<f64>,
    s: Vec<bool>,
    u: Vec<f64>,
}

fn strength_of(fields: &GlyphFields, o: usize, strength: Strength) -> &[f64] {
    match strength {
        Strength::Notebook => &fields.conf_nb[o],
        Strength::Manuscript => &fields.arc[o],
    }
}

fn embed_side(
    fields: &GlyphFields,
    o: usize,
    strength: Strength,
    lo: (i64, i64),
    origin: (i64, i64),
    cw: usize,
    ch: usize,
) -> Embedded {
    let n = cw * ch;
    let mut e = Embedded {
        c: vec![0.0; n],
        d: vec![0.0; n],
        s: vec![false; n],
        u: vec![f64::INFINITY; n],
    };
    let ox = lo.0 - origin.0;
    let oy = lo.1 - origin.1;
    for y in 0..fields.h {
        for x in 0..fields.w {
            let cx = ox + x as i64;
            let cy = oy + y as i64;
            if cx < 0 || cy < 0 || cx >= cw as i64 || cy >= ch as i64 {
                continue;
            }
            let i = cy as usize * cw + cx as usize;
            let j = y * fields.w + x;
            if fields.supported[o][j] {
                e.s[i] = true;
                e.c[i] = strength_of(fields, o, strength)[j];
                e.d[i] = fields.distance[o][j];
                e.u[i] = fields.u2[o][j];
            }
        }
    }
    e
}

#[allow(clippy::too_many_arguments)]
pub fn score_step_local(
    lf: &GlyphFields,
    rf: &GlyphFields,
    lo: (i64, i64),
    ro: (i64, i64),
    canvas_origin: (i64, i64),
    canvas_w: usize,
    canvas_h: usize,
    local_l: &[Vec<f64>],
    local_r: &[Vec<f64>],
    facing: &[Vec<f64>],
    tau: f64,
    strength: Strength,
    cancel: Option<&Arc<AtomicBool>>,
) -> Result<LocalStepScore, EngineError> {
    let n = lf.supported.len();
    let tau2 = 2.0 * tau * tau;
    // Glyph-lattice rectangles in canvas coordinates (i64: origins may be
    // negative and extents may exceed the canvas). A both-supported pixel
    // needs both sides in-lattice AND in-canvas, i.e. it lies in the
    // lattice intersection clipped to the caller canvas. Outside that box
    // at least one side is out of lattice, so the old embedded `s` mask
    // was false there and those iterations were provably skipped. The box
    // below visits the same both-supported pixels in the same row-major
    // order as the old union sweep; only dead canvas is never visited.
    // i64 clamping (never a negative `as usize` wrap) also keeps empty /
    // clipped / negative-origin canvases panic-free with identical
    // abstain semantics. Direct lattice indexing replaces the per-step
    // full-canvas embeddings, so no step allocates canvas-sized vectors.
    let lx0 = lo.0 - canvas_origin.0;
    let ly0 = lo.1 - canvas_origin.1;
    let rx0 = ro.0 - canvas_origin.0;
    let ry0 = ro.1 - canvas_origin.1;
    let ix0 = lx0.max(rx0).max(0);
    let iy0 = ly0.max(ry0).max(0);
    let ix1 = (lx0 + lf.w as i64)
        .min(rx0 + rf.w as i64)
        .min(canvas_w as i64);
    let iy1 = (ly0 + lf.h as i64)
        .min(ry0 + rf.h as i64)
        .min(canvas_h as i64);
    let mut gl = 0.0;
    let mut weak_num = 0.0;
    let mut both_count: u64 = 0;
    let mut scored_pixels: u64 = 0;
    let mut skipped: u64 = 0;
    let mut shortfall = 0.0f64;
    let mut max_term = 0.0f64;
    let mut bound = 0.0f64;
    let mut any_both = false;
    for a in 0..n {
        if let Some(flag) = cancel {
            if flag.load(Ordering::Relaxed) {
                return Err(EngineError::Cancelled);
            }
        }
        // Left-side lattice rows (fixed for this `a`; no canvas embedding).
        let lc = strength_of(lf, a, strength);
        let (ls, ld, lu) = (&lf.supported[a], &lf.distance[a], &lf.u2[a]);
        let le = &local_l[a];
        for b in 0..n {
            let w = facing[a][b];
            if w == 0.0 {
                continue;
            }
            // Right-side lattice rows (fixed for this `b`).
            let rc = strength_of(rf, b, strength);
            let (rs, rd, ru) = (&rf.supported[b], &rf.distance[b], &rf.u2[b]);
            let re = &local_r[b];
            let mut n_ab = 0.0;
            let mut ql = 0.0;
            let mut qr = 0.0;
            let mut both_ab: u64 = 0;
            // Single fused pass over the clipped lattice intersection.
            // Per pixel the old first-pass overlap statistics run first,
            // then the old second-pass guarded normalized summand, in the
            // same row-major, (a, b)-outer order; each accumulator sees
            // the identical value sequence, so all sums are bit-identical
            // while the shared Gaussian K is evaluated once per pixel.
            for cy in iy0..iy1 {
                let li_row = (cy - ly0) as usize * lf.w;
                let ri_row = (cy - ry0) as usize * rf.w;
                for cx in ix0..ix1 {
                    let li = li_row + (cx - lx0) as usize;
                    let ri = ri_row + (cx - rx0) as usize;
                    if !(ls[li] && rs[ri]) {
                        continue;
                    }
                    both_ab += 1;
                    let dd = ld[li] - rd[ri];
                    let k = (-dd * dd / tau2).exp();
                    let lci = lc[li];
                    let rci = rc[ri];
                    n_ab += lci * rci * k;
                    ql += lci * lci;
                    qr += rci * rci;
                    let elv = le[li];
                    let erv = re[ri];
                    if !(elv > 0.0 && elv.is_finite() && erv > 0.0 && erv.is_finite()) {
                        skipped += 1;
                        continue;
                    }
                    both_count += 1;
                    scored_pixels += 1;
                    let contrib = w * lci * rci * k / (elv * erv).sqrt();
                    gl += contrib;
                    // Weak-band share in the same locally-normalized units
                    // (pilot parity; guard-skipped pixels excluded, which
                    // matches the pilot wherever EL/ER stay positive).
                    if lu[li] < FLOOR_U2 || ru[ri] < FLOOR_U2 {
                        weak_num += contrib;
                    }
                    // Center-inclusive shortfall on both sides.
                    let cl2 = lci * lci;
                    if cl2 > 0.0 {
                        let s = (cl2 - elv) / cl2;
                        if s > shortfall {
                            shortfall = s;
                        }
                    }
                    let cr2 = rci * rci;
                    if cr2 > 0.0 {
                        let s = (cr2 - erv) / cr2;
                        if s > shortfall {
                            shortfall = s;
                        }
                    }
                }
            }
            if both_ab == 0 {
                continue;
            }
            any_both = true;
            bound += w * both_ab as f64;
            let den = (ql * qr).sqrt();
            if den.is_finite() && den > 0.0 {
                let t = n_ab / den;
                if t > max_term {
                    max_term = t;
                }
            }
        }
    }
    let weak_share = if gl > 0.0 { weak_num / gl } else { 0.0 };
    if scored_pixels == 0 {
        let reason = if any_both {
            LocalAbstain::ZeroLocalEvidence
        } else {
            LocalAbstain::NoSharedSupport
        };
        return Ok(LocalStepScore {
            gl: 0.0,
            both_supported_pairpx: both_count,
            weak_normalized_share: 0.0,
            max_term_cosine: max_term,
            abstain: true,
            abstain_reason: Some(reason),
            skipped_nonpositive: skipped,
            conditioning_shortfall: shortfall,
            honest_bound: bound,
        });
    }
    // A finite nonnegative gl with scored terms is eligible, including an
    // exact zero (valid zero agreement and float underflow are value-level
    // indistinguishable). Negative or nonfinite gl is unphysical rounding
    // fallout and abstains as zero local evidence.
    if !gl.is_finite() || gl < 0.0 {
        return Ok(LocalStepScore {
            gl: 0.0,
            both_supported_pairpx: both_count,
            weak_normalized_share: 0.0,
            max_term_cosine: max_term,
            abstain: true,
            abstain_reason: Some(LocalAbstain::ZeroLocalEvidence),
            skipped_nonpositive: skipped,
            conditioning_shortfall: shortfall,
            honest_bound: bound,
        });
    }
    Ok(LocalStepScore {
        gl,
        both_supported_pairpx: both_count,
        weak_normalized_share: weak_share,
        max_term_cosine: max_term,
        abstain: false,
        abstain_reason: None,
        skipped_nonpositive: skipped,
        conditioning_shortfall: shortfall,
        honest_bound: bound,
    })
}

/// Geometry-dependent bound check: `gl <= bound * (1 + allowance)`.
/// Never the G2 `[0, 128]` clamp.
pub fn check_local_bound(gl: f64, bound: f64, allowance: f64) -> Result<(), EngineError> {
    if !(gl.is_finite() && bound.is_finite() && allowance.is_finite()) {
        return Err(EngineError::Invalid(
            "local bound check needs finite gl/bound/allowance".to_string(),
        ));
    }
    if gl <= bound * (1.0 + allowance) {
        Ok(())
    } else {
        Err(EngineError::Invalid(format!(
            "local bound violated: gl={gl} bound={bound} allowance={allowance}"
        )))
    }
}

#[allow(clippy::too_many_arguments)]
pub fn contribution_map_local(
    lf: &GlyphFields,
    rf: &GlyphFields,
    lo: (i64, i64),
    ro: (i64, i64),
    canvas_origin: (i64, i64),
    canvas_w: usize,
    canvas_h: usize,
    local_l: &[Vec<f64>],
    local_r: &[Vec<f64>],
    facing: &[Vec<f64>],
    tau: f64,
    strength: Strength,
    cancel: Option<&Arc<AtomicBool>>,
) -> Result<Vec<f64>, EngineError> {
    let n = lf.supported.len();
    let tau2 = 2.0 * tau * tau;
    let mut out = vec![0.0; canvas_w * canvas_h];
    // Same clipped lattice-intersection box as `score_step_local`: a
    // contributing pixel needs both sides in-lattice and in-canvas.
    // Direct lattice indexing keeps the per-pixel (a, b)-outer
    // contribution order and the dense map geometry/origin, without the
    // old per-(a, b) full-canvas embeddings (the right-side rebuild
    // inside the orientation loop is gone with them).
    let lx0 = lo.0 - canvas_origin.0;
    let ly0 = lo.1 - canvas_origin.1;
    let rx0 = ro.0 - canvas_origin.0;
    let ry0 = ro.1 - canvas_origin.1;
    let ix0 = lx0.max(rx0).max(0);
    let iy0 = ly0.max(ry0).max(0);
    let ix1 = (lx0 + lf.w as i64)
        .min(rx0 + rf.w as i64)
        .min(canvas_w as i64);
    let iy1 = (ly0 + lf.h as i64)
        .min(ry0 + rf.h as i64)
        .min(canvas_h as i64);
    for a in 0..n {
        if let Some(flag) = cancel {
            if flag.load(Ordering::Relaxed) {
                return Err(EngineError::Cancelled);
            }
        }
        let lc = strength_of(lf, a, strength);
        let (ls, ld) = (&lf.supported[a], &lf.distance[a]);
        let le = &local_l[a];
        for b in 0..n {
            let w = facing[a][b];
            if w == 0.0 {
                continue;
            }
            let rc = strength_of(rf, b, strength);
            let (rs, rd) = (&rf.supported[b], &rf.distance[b]);
            let re = &local_r[b];
            for cy in iy0..iy1 {
                let li_row = (cy - ly0) as usize * lf.w;
                let ri_row = (cy - ry0) as usize * rf.w;
                let orow = cy as usize * canvas_w;
                for cx in ix0..ix1 {
                    let li = li_row + (cx - lx0) as usize;
                    let ri = ri_row + (cx - rx0) as usize;
                    if !(ls[li] && rs[ri]) {
                        continue;
                    }
                    let elv = le[li];
                    let erv = re[ri];
                    if !(elv > 0.0 && elv.is_finite() && erv > 0.0 && erv.is_finite()) {
                        continue;
                    }
                    let dd = ld[li] - rd[ri];
                    let i = orow + cx as usize;
                    out[i] += w * lc[li] * rc[ri] * (-dd * dd / tau2).exp() / (elv * erv).sqrt();
                }
            }
        }
    }
    Ok(out)
}

/// L/R-symmetric agreement readout over the both-union (informational).
#[allow(clippy::too_many_arguments)]
pub fn confidence_local(
    lf: &GlyphFields,
    rf: &GlyphFields,
    lo: (i64, i64),
    ro: (i64, i64),
    canvas_origin: (i64, i64),
    canvas_w: usize,
    canvas_h: usize,
    strength: Strength,
) -> LocalConfidence {
    let n = lf.supported.len();
    let mut union = vec![false; canvas_w * canvas_h];
    let mut left = Vec::with_capacity(n);
    let mut right = Vec::with_capacity(n);
    for o in 0..n {
        left.push(embed_side(lf, o, strength, lo, canvas_origin, canvas_w, canvas_h));
        right.push(embed_side(rf, o, strength, ro, canvas_origin, canvas_w, canvas_h));
    }
    for a in 0..n {
        for b in 0..n {
            for i in 0..union.len() {
                if left[a].s[i] && right[b].s[i] {
                    union[i] = true;
                }
            }
        }
    }
    let union_count: u64 = union.iter().filter(|&&v| v).count() as u64;
    let mut support_mass_l = 0.0;
    let mut support_mass_r = 0.0;
    let mut support_weak_l = 0.0;
    let mut support_weak_r = 0.0;
    for a in 0..n {
        for b in 0..n {
            for i in 0..union.len() {
                if left[a].s[i] && right[b].s[i] {
                    support_mass_l += left[a].c[i];
                    support_mass_r += right[b].c[i];
                    if left[a].u[i] < FLOOR_U2 || right[b].u[i] < FLOOR_U2 {
                        support_weak_l += left[a].c[i];
                        support_weak_r += right[b].c[i];
                    }
                }
            }
        }
    }
    let domain = (canvas_w * canvas_h) as f64;
    LocalConfidence {
        support_mass_l,
        support_mass_r,
        support_weak_mass_l: support_weak_l,
        support_weak_mass_r: support_weak_r,
        support_share: union_count as f64 / domain,
        support_union_pairpx: union_count,
    }
}
