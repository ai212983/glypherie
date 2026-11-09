//! Stage-3 SCORE-v2 interpreter over frozen-oriented fields.
//!
//! Provenance: `yinyang_oriented_score` — `G2(s) = sum_{a,b} F(a,b) N(a,b;s)
//! / sqrt(E_L[a] E_R[b])` with `N` summed over both-supported pixels and
//! `E[g,o] = sum c^2` computed ONCE per glyph over its own lattice
//! (H-NORM: candidate/neighbor/domain-independent). Facing weights
//! `F(a,b) = sin^2((theta_a - theta_b)/2)` sum to 128 over 16x16 channels.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use crate::fields::{directed_angles, GlyphFields};
use crate::params::{ScoreParams, FLOOR_U2, G2_BOUND, TIE_TOL_FACTOR};
use crate::EngineError;

/// Strength variant: notebook primary (`U1*d^(q-1)`) or manuscript
/// alternate (`U1*d^(q+1)`). The caller names it explicitly on every call.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Strength {
    Notebook,
    Manuscript,
}

impl Strength {
    pub fn parse(s: &str) -> Result<Self, EngineError> {
        match s {
            "notebook" => Ok(Strength::Notebook),
            "manuscript" => Ok(Strength::Manuscript),
            _ => Err(EngineError::Invalid(format!(
                "score strength variant must be one of (\"notebook\", \"manuscript\"), got {s:?}"
            ))),
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Strength::Notebook => "notebook",
            Strength::Manuscript => "manuscript",
        }
    }
}

fn strength_of(fields: &GlyphFields, s: Strength) -> &Vec<Vec<f64>> {
    match s {
        Strength::Notebook => &fields.conf_nb,
        Strength::Manuscript => &fields.arc,
    }
}

/// Symmetric facing weights `F(a,b) = sin^2((theta_a - theta_b)/2)`.
pub fn facing_matrix(n_directed: usize) -> Vec<Vec<f64>> {
    let thetas = directed_angles(n_directed);
    (0..n_directed)
        .map(|a| {
            (0..n_directed)
                .map(|b| ((thetas[a] - thetas[b]) / 2.0).sin().powi(2))
                .collect()
        })
        .collect()
}

/// Isolated per-channel self-energy over the glyph's own padded lattice.
pub fn self_energy(fields: &GlyphFields, s: Strength) -> Vec<f64> {
    let arr = strength_of(fields, s);
    arr.iter()
        .zip(fields.supported.iter())
        .map(|(c, sup)| {
            c.iter()
                .zip(sup.iter())
                .map(|(v, m)| if *m { v * v } else { 0.0 })
                .sum()
        })
        .collect()
}

/// Fixed union canvas over all swept steps (embedding only; widening the
/// sweep never changes shared-step G2).
pub fn union_canvas(
    lw: usize,
    lh: usize,
    lo: (i64, i64),
    rw: usize,
    rh: usize,
    ros: &[(i64, i64)],
) -> ((i64, i64), (usize, usize)) {
    let mut cx = lo.0;
    let mut cy = lo.1;
    let mut ex = lo.0 + lw as i64;
    let mut ey = lo.1 + lh as i64;
    for ro in ros {
        cx = cx.min(ro.0);
        cy = cy.min(ro.1);
        ex = ex.max(ro.0 + rw as i64);
        ey = ey.max(ro.1 + rh as i64);
    }
    ((cx, cy), ((ey - cy) as usize, (ex - cx) as usize))
}

fn embed_float(
    arr: &[f64],
    w: usize,
    h: usize,
    origin: (i64, i64),
    canvas_origin: (i64, i64),
    canvas_w: usize,
    canvas_h: usize,
) -> Vec<f64> {
    let mut out = vec![0.0; canvas_w * canvas_h];
    let ox = (origin.0 - canvas_origin.0) as usize;
    let oy = (origin.1 - canvas_origin.1) as usize;
    for y in 0..h {
        let dst = (oy + y) * canvas_w + ox;
        out[dst..dst + w].copy_from_slice(&arr[y * w..(y + 1) * w]);
    }
    out
}

fn embed_bool(
    arr: &[bool],
    w: usize,
    h: usize,
    origin: (i64, i64),
    canvas_origin: (i64, i64),
    canvas_w: usize,
    canvas_h: usize,
) -> Vec<bool> {
    let mut out = vec![false; canvas_w * canvas_h];
    let ox = (origin.0 - canvas_origin.0) as usize;
    let oy = (origin.1 - canvas_origin.1) as usize;
    for y in 0..h {
        let dst = (oy + y) * canvas_w + ox;
        out[dst..dst + w].copy_from_slice(&arr[y * w..(y + 1) * w]);
    }
    out
}

/// One channel row embedded on the union canvas: strength (zero where
/// unsupported), distance (zero where unsupported), support, `U2` (+inf
/// where unsupported, matching the frozen floor gate).
struct EmbeddedRow {
    c: Vec<f64>,
    d: Vec<f64>,
    s: Vec<bool>,
    u: Vec<f64>,
}

fn embed_side(
    fields: &GlyphFields,
    strength: Strength,
    origin: (i64, i64),
    canvas_origin: (i64, i64),
    canvas_w: usize,
    canvas_h: usize,
) -> Vec<EmbeddedRow> {
    let arr = strength_of(fields, strength);
    (0..fields.supported.len())
        .map(|o| {
            let sup = &fields.supported[o];
            let c: Vec<f64> = arr[o]
                .iter()
                .zip(sup.iter())
                .map(|(v, m)| if *m { *v } else { 0.0 })
                .collect();
            let d: Vec<f64> = fields.distance[o]
                .iter()
                .zip(sup.iter())
                .map(|(v, m)| if *m { *v } else { 0.0 })
                .collect();
            let u: Vec<f64> = fields.u2[o]
                .iter()
                .zip(sup.iter())
                .map(|(v, m)| if *m { *v } else { f64::INFINITY })
                .collect();
            EmbeddedRow {
                c: embed_float(
                    &c,
                    fields.w,
                    fields.h,
                    origin,
                    canvas_origin,
                    canvas_w,
                    canvas_h,
                ),
                d: embed_float(
                    &d,
                    fields.w,
                    fields.h,
                    origin,
                    canvas_origin,
                    canvas_w,
                    canvas_h,
                ),
                s: embed_bool(
                    sup,
                    fields.w,
                    fields.h,
                    origin,
                    canvas_origin,
                    canvas_w,
                    canvas_h,
                ),
                u: embed_float(
                    &u,
                    fields.w,
                    fields.h,
                    origin,
                    canvas_origin,
                    canvas_w,
                    canvas_h,
                ),
            }
        })
        .collect()
}

/// Per-step score record.
#[derive(Debug, Clone)]
pub struct StepScore {
    pub g2: f64,
    pub raw: f64,
    /// Weak-band share AFTER same-G2-channel normalization (diagnostic,
    /// never a stability proof).
    pub floor_share: f64,
    /// Raw weak-band share, kept separate.
    pub raw_floor_share: f64,
    pub both_supported_pairpx: u64,
    /// Abstain: no both-supported pixel carried finite energy.
    pub abstain: bool,
}

/// G2 at one integer step on the fixed union canvas.
#[allow(clippy::too_many_arguments)]
pub fn score_step(
    lf: &GlyphFields,
    rf: &GlyphFields,
    lo: (i64, i64),
    ro: (i64, i64),
    canvas_origin: (i64, i64),
    canvas_w: usize,
    canvas_h: usize,
    el: &[f64],
    er: &[f64],
    tau: f64,
    strength: Strength,
    facing: &[Vec<f64>],
    cancel: Option<&Arc<AtomicBool>>,
) -> Result<StepScore, EngineError> {
    let n = lf.supported.len();
    let tau2 = 2.0 * tau * tau;
    let left = embed_side(lf, strength, lo, canvas_origin, canvas_w, canvas_h);
    let right = embed_side(rf, strength, ro, canvas_origin, canvas_w, canvas_h);
    let mut raw = 0.0;
    let mut norm = 0.0;
    let mut floor_num = 0.0;
    let mut normalized_floor_num = 0.0;
    let mut both_count: u64 = 0;
    for a in 0..n {
        if let Some(flag) = cancel {
            if flag.load(Ordering::Relaxed) {
                return Err(EngineError::Cancelled);
            }
        }
        for b in 0..n {
            let wgt = facing[a][b];
            if wgt == 0.0 {
                continue;
            }
            let den = (el[a] * er[b]).sqrt();
            if !den.is_finite() || den <= 0.0 {
                continue;
            }
            let (la, rb) = (&left[a], &right[b]);
            let mut s = 0.0;
            let mut weak = 0.0;
            let mut any = false;
            for (i, (lval, rval)) in la.s.iter().zip(rb.s.iter()).enumerate() {
                if *lval && *rval {
                    any = true;
                    let dd = (la.d[i] - rb.d[i]).abs();
                    let t = la.c[i] * rb.c[i] * (-dd * dd / tau2).exp();
                    s += t;
                    if la.u[i] < FLOOR_U2 || rb.u[i] < FLOOR_U2 {
                        weak += t;
                    }
                    both_count += 1;
                }
            }
            if !any {
                continue;
            }
            raw += wgt * s;
            norm += wgt * s / den;
            floor_num += wgt * weak;
            normalized_floor_num += wgt * weak / den;
        }
    }
    let floor_share = if norm > 0.0 {
        normalized_floor_num / norm
    } else {
        0.0
    };
    let raw_floor_share = if raw > 0.0 { floor_num / raw } else { 0.0 };
    Ok(StepScore {
        g2: norm,
        raw,
        floor_share,
        raw_floor_share,
        both_supported_pairpx: both_count,
        abstain: raw == 0.0 && both_count == 0,
    })
}

/// Exact normalized per-pixel G2 summands for one step (sums to the step
/// G2): `sum_{a,b} F cL cR kval / sqrt(EL ER)` over both-supported pixels,
/// zero elsewhere.
#[allow(clippy::too_many_arguments)]
pub fn contribution_map(
    lf: &GlyphFields,
    rf: &GlyphFields,
    lo: (i64, i64),
    ro: (i64, i64),
    canvas_origin: (i64, i64),
    canvas_w: usize,
    canvas_h: usize,
    el: &[f64],
    er: &[f64],
    tau: f64,
    strength: Strength,
    facing: &[Vec<f64>],
    cancel: Option<&Arc<AtomicBool>>,
) -> Result<Vec<f64>, EngineError> {
    let n = lf.supported.len();
    let tau2 = 2.0 * tau * tau;
    let left = embed_side(lf, strength, lo, canvas_origin, canvas_w, canvas_h);
    let right = embed_side(rf, strength, ro, canvas_origin, canvas_w, canvas_h);
    let mut out = vec![0.0; canvas_w * canvas_h];
    for a in 0..n {
        if let Some(flag) = cancel {
            if flag.load(Ordering::Relaxed) {
                return Err(EngineError::Cancelled);
            }
        }
        for b in 0..n {
            let wgt = facing[a][b];
            if wgt == 0.0 {
                continue;
            }
            let den = (el[a] * er[b]).sqrt();
            if !den.is_finite() || den <= 0.0 {
                continue;
            }
            let (la, rb) = (&left[a], &right[b]);
            for (i, (lval, rval)) in la.s.iter().zip(rb.s.iter()).enumerate() {
                if *lval && *rval {
                    let dd = (la.d[i] - rb.d[i]).abs();
                    out[i] += wgt * la.c[i] * rb.c[i] * (-dd * dd / tau2).exp() / den;
                }
            }
        }
    }
    Ok(out)
}

/// TIE-v2: indices within `m* + tol`, `tol = 1e-9 * max(1, m*)`.
pub fn tie_set(deviations: &[f64]) -> (Vec<usize>, f64) {
    let mstar = deviations.iter().cloned().fold(f64::INFINITY, f64::min);
    let tol = TIE_TOL_FACTOR * 1.0f64.max(mstar);
    let idx: Vec<usize> = deviations
        .iter()
        .enumerate()
        .filter(|(_, d)| **d <= mstar + tol)
        .map(|(i, _)| i)
        .collect();
    (idx, mstar)
}

/// Exact occupied-cell overlap and face/corner contact at an integer step
/// (origins truncated toward zero like the frozen `int()` casts). Faces and
/// corners count per right cell per neighboring left cell, as frozen.
#[allow(clippy::too_many_arguments)]
pub fn contact_counts(
    left_cover: &[f64],
    lw: usize,
    lh: usize,
    left_origin: (f64, f64),
    right_cover: &[f64],
    rw: usize,
    rh: usize,
    right_origin: (f64, f64),
    offset: i64,
) -> (usize, usize, usize) {
    let occupied = |cover: &[f64], w: usize, h: usize, ox: i64, oy: i64| -> Vec<(i64, i64)> {
        let mut cells = Vec::new();
        for y in 0..h {
            for x in 0..w {
                if cover[y * w + x] > 0.0 {
                    cells.push((ox + x as i64, oy + y as i64));
                }
            }
        }
        cells
    };
    let left = occupied(
        left_cover,
        lw,
        lh,
        left_origin.0.trunc() as i64,
        left_origin.1.trunc() as i64,
    );
    let right = occupied(
        right_cover,
        rw,
        rh,
        right_origin.0.trunc() as i64 + offset,
        right_origin.1.trunc() as i64,
    );
    let overlaps = right.iter().filter(|c| left.contains(c)).count();
    if overlaps > 0 {
        return (overlaps, 0, 0);
    }
    let (mut faces, mut corners) = (0, 0);
    for (x, y) in right.iter() {
        for dx in -1..=1 {
            for dy in -1..=1 {
                if dx == 0 && dy == 0 {
                    continue;
                }
                if left.contains(&(*x + dx, *y + dy)) {
                    if dx == 0 || dy == 0 {
                        faces += 1;
                    } else {
                        corners += 1;
                    }
                }
            }
        }
    }
    (0, faces, corners)
}

/// Pixel rounding matching the frozen `pixel_round` (halves away from zero;
/// agrees with the native surface invariant for nonneg pens).
pub fn pixel_round(value: f64) -> i64 {
    if value >= 0.0 {
        (value + 0.5).floor() as i64
    } else {
        (value - 0.5).ceil() as i64
    }
}

/// Validate a score request (finite integer metric, bounded deltas, valid tau).
pub fn validate_score_request(
    metric: f64,
    deltas: &[i64],
    score: &ScoreParams,
) -> Result<(), EngineError> {
    score.validate()?;
    if !metric.is_finite() || metric.fract() != 0.0 {
        return Err(EngineError::Invalid(format!(
            "metric must be a finite integer step, got {metric}"
        )));
    }
    if deltas.is_empty() || deltas.len() > 512 {
        return Err(EngineError::Invalid(format!(
            "need 1..=512 candidate deltas, got {}",
            deltas.len()
        )));
    }
    Ok(())
}

/// Score-unit bound check (Cauchy-Schwarz): finite G2 sits in `0..=128`.
/// Nonfinite G2 is reported, never clamped.
pub fn check_g2_bound(g2: f64) -> Result<(), EngineError> {
    if g2.is_nan() {
        return Err(EngineError::Invalid("G2 is NaN".to_string()));
    }
    if !(0.0..=G2_BOUND).contains(&g2) {
        return Err(EngineError::Invalid(format!(
            "G2 {g2} outside 0..={G2_BOUND}"
        )));
    }
    Ok(())
}
