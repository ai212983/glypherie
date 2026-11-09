//! Per-glyph oriented fields: multiscale V1C input, directed ratio stage.
//!
//! Provenance: stage-1 `oriented_fields_for_image` (single-scale V1C,
//! orientation-masked `r^-q` / `r^-(q+1)` convolutions, `d = U1/U2`,
//! notebook `U1*d^(q-1)` primary, manuscript `U1*d^(q+1)` alternate) with
//! the stage-2 direct path `T = sum_s w_s C_s` combined BEFORE the ratio
//! (`multiscale_glyph_fields`). Single scale is a limiting case of the
//! weights, not a second model.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use rustfft::num_complex::Complex;

use crate::bessel::bessel_i0;
use crate::fft::Conv;
use crate::params::EngineParams;
use crate::EngineError;

pub fn directed_angles(n: usize) -> Vec<f64> {
    (0..n)
        .map(|i| i as f64 * 2.0 * std::f64::consts::PI / n as f64)
        .collect()
}

pub fn v1_angles(n: usize) -> Vec<f64> {
    (0..n)
        .map(|i| i as f64 * std::f64::consts::PI / n as f64)
        .collect()
}

/// Manuscript derivative-of-Gaussian quadrature bank at one scale
/// (complex, `n_v1` orientations). The even partner is demeaned to zero DC.
pub fn build_v1_bank(sigma: f64, n_v1: usize) -> (Vec<Vec<Complex<f64>>>, i64) {
    let w = EngineParams::halfwidth_for_sigma(sigma);
    let s2 = sigma * sigma;
    let mut bank = Vec::with_capacity(n_v1);
    for theta in v1_angles(n_v1) {
        let (sn, c) = theta.sin_cos();
        let mut taps = Vec::with_capacity((2 * w + 1) as usize * (2 * w + 1) as usize);
        let mut even_sum = 0.0;
        let mut evens = Vec::new();
        for y in -w..=w {
            for x in -w..=w {
                let xf = x as f64;
                let yf = y as f64;
                let u = xf * c + yf * sn;
                let v = -xf * sn + yf * c;
                let gauss = (-(u * u + v * v) / (2.0 * s2)).exp();
                let odd = u * gauss / (2.0 * std::f64::consts::PI * s2 * s2);
                let even = gauss / (2.0 * std::f64::consts::PI * s2 * sigma)
                    - u * u * gauss / (2.0 * std::f64::consts::PI * s2 * s2 * sigma);
                evens.push(even);
                even_sum += even;
                taps.push(Complex::new(odd, even));
            }
        }
        let mean = even_sum / evens.len() as f64;
        for (t, e) in taps.iter_mut().zip(evens.iter()) {
            t.im = e - mean;
        }
        bank.push(taps);
    }
    (bank, w)
}

/// Von Mises directed masks times origin-zeroed `r^-q` / `r^-(q+1)` over
/// the SQUARE tap grid `[-R, R]^2` (no circular crop). Returns per-channel
/// kernels plus retained (truncated) mass.
#[allow(clippy::type_complexity)]
pub fn build_oriented_kernels(
    q: f64,
    kappa: f64,
    radius: u32,
    n_directed: usize,
) -> (Vec<Vec<f64>>, Vec<Vec<f64>>, Vec<f64>, Vec<f64>) {
    let r = radius as i64;
    let norm = 2.0 * std::f64::consts::PI * bessel_i0(kappa);
    let thetas = directed_angles(n_directed);
    let mut h1 = Vec::with_capacity(n_directed);
    let mut h2 = Vec::with_capacity(n_directed);
    let mut mass1 = Vec::with_capacity(n_directed);
    let mut mass2 = Vec::with_capacity(n_directed);
    for theta in thetas {
        let mut k1 = Vec::with_capacity((2 * r + 1) as usize * (2 * r + 1) as usize);
        let mut k2 = Vec::with_capacity((2 * r + 1) as usize * (2 * r + 1) as usize);
        let mut m1 = 0.0;
        let mut m2 = 0.0;
        for y in -r..=r {
            for x in -r..=r {
                let xf = x as f64;
                let yf = y as f64;
                let rad = xf.hypot(yf);
                let (f1, f2) = if rad == 0.0 {
                    (0.0, 0.0)
                } else {
                    (rad.powf(-q), rad.powf(-(q + 1.0)))
                };
                let phi = yf.atan2(xf);
                let mask = (kappa * (phi - theta).cos()).exp() / norm;
                k1.push(mask * f1);
                k2.push(mask * f2);
                m1 += mask * f1;
                m2 += mask * f2;
            }
        }
        mass1.push(m1);
        mass2.push(m2);
        h1.push(k1);
        h2.push(k2);
    }
    (h1, h2, mass1, mass2)
}

/// Cached per-scale V1 banks plus half-widths.
pub struct V1Banks {
    pub banks: Vec<Vec<Vec<Complex<f64>>>>,
    pub halfwidths: Vec<i64>,
}

/// Cached oriented kernels plus retained mass.
pub struct OrientedKernels {
    pub h1: Vec<Vec<f64>>,
    pub h2: Vec<Vec<f64>>,
    pub mass1: Vec<f64>,
    pub mass2: Vec<f64>,
    pub taps: usize,
}

/// Per-glyph fields over the zero-padded lattice.
pub struct GlyphFields {
    /// Padded lattice width/height.
    pub w: usize,
    pub h: usize,
    pub pad: i64,
    /// Per-scale V1 magnitudes `[scale][v1][px]`.
    pub c_per_scale: Vec<Vec<Vec<f64>>>,
    /// Combined input `[v1][px]`.
    pub t_combined: Vec<Vec<f64>>,
    /// Channel arrays `[directed][px]`.
    pub u1: Vec<Vec<f64>>,
    pub u2: Vec<Vec<f64>>,
    pub distance: Vec<Vec<f64>>,
    pub conf_nb: Vec<Vec<f64>>,
    pub arc: Vec<Vec<f64>>,
    pub supported: Vec<Vec<bool>>,
}

fn check_cancel(cancel: Option<&Arc<AtomicBool>>) -> Result<(), EngineError> {
    if let Some(flag) = cancel {
        if flag.load(Ordering::Relaxed) {
            return Err(EngineError::Cancelled);
        }
    }
    Ok(())
}

/// Multiscale direct-path fields for one glyph cover buffer (row-major).
#[allow(clippy::too_many_arguments)]
pub fn glyph_fields(
    cover: &[f64],
    w: usize,
    h: usize,
    params: &EngineParams,
    banks: &V1Banks,
    kernels: &OrientedKernels,
    conv: &mut Conv,
    cancel: Option<&Arc<AtomicBool>>,
) -> Result<GlyphFields, EngineError> {
    if cover.len() != w * h {
        return Err(EngineError::Invalid(format!(
            "cover length {} != {}x{}",
            cover.len(),
            w,
            h
        )));
    }
    if cover.iter().any(|v| !v.is_finite()) {
        return Err(EngineError::Invalid(
            "glyph cover must be finite (no NaN/Inf)".to_string(),
        ));
    }
    let pad = params.pad();
    let pw = w + 2 * pad as usize;
    let ph = h + 2 * pad as usize;
    if pw > 2048 || ph > 2048 {
        return Err(EngineError::Invalid(format!(
            "padded lattice {pw}x{ph} exceeds the 2048 resource guard"
        )));
    }
    let mut padded = vec![Complex::new(0.0, 0.0); pw * ph];
    for y in 0..h {
        for x in 0..w {
            padded[(y + pad as usize) * pw + x + pad as usize] =
                Complex::new(cover[y * w + x], 0.0);
        }
    }
    let kside = 2 * params.radius as usize + 1;
    let n_v1 = params.n_v1;
    let n_dir = params.n_directed;

    let mut c_per_scale: Vec<Vec<Vec<f64>>> = Vec::with_capacity(banks.banks.len());
    for (s, bank) in banks.banks.iter().enumerate() {
        let hw = banks.halfwidths[s] as usize;
        let side = 2 * hw + 1;
        // One input spectrum per scale: all V1 kernels at this scale
        // share the identical padded shape and input bytes.
        let padded_spec = conv.forward_padded(&padded, pw, ph, side, side);
        let mut per_ori = Vec::with_capacity(n_v1);
        for g in bank.iter() {
            check_cancel(cancel)?;
            let out = conv.conv_same_with_input(&padded_spec, g, side, side);
            per_ori.push(out.iter().map(|c| c.norm()).collect::<Vec<f64>>());
        }
        c_per_scale.push(per_ori);
    }
    // Direct path: T = sum_s w_s C_s per orientation (fixed order loop).
    let mut t_combined = vec![vec![0.0f64; pw * ph]; n_v1];
    for (s, per_ori) in c_per_scale.iter().enumerate() {
        let wt = params.weights[s];
        for o in 0..n_v1 {
            let dst = &mut t_combined[o];
            for (d, c) in dst.iter_mut().zip(per_ori[o].iter()) {
                *d += wt * c;
            }
        }
    }
    // Directed inputs repeat per V1 orientation (`t_combined[o % n_v1]`,
    // cloned per channel above): one shared spectrum per orientation
    // group covers both its channels and both kernels (h1/h2).
    let mut tre_specs = Vec::with_capacity(n_v1);
    for t_row in t_combined.iter().take(n_v1) {
        check_cancel(cancel)?;
        let tre: Vec<Complex<f64>> = t_row
            .iter()
            .map(|c| Complex::new(c.max(0.0), 0.0))
            .collect();
        tre_specs.push(conv.forward_padded(&tre, pw, ph, kside, kside));
    }
    let mut u1: Vec<Vec<f64>> = Vec::with_capacity(n_dir);
    let mut u2: Vec<Vec<f64>> = Vec::with_capacity(n_dir);
    for (o, (k1_row, k2_row)) in kernels.h1.iter().zip(kernels.h2.iter()).enumerate() {
        check_cancel(cancel)?;
        let tre_spec = &tre_specs[o % n_v1];
        let hk1: Vec<Complex<f64>> = k1_row.iter().map(|v| Complex::new(*v, 0.0)).collect();
        let hk2: Vec<Complex<f64>> = k2_row.iter().map(|v| Complex::new(*v, 0.0)).collect();
        let o1 = conv.conv_same_with_input(tre_spec, &hk1, kside, kside);
        let o2 = conv.conv_same_with_input(tre_spec, &hk2, kside, kside);
        u1.push(o1.iter().map(|c| c.re.max(0.0)).collect());
        u2.push(o2.iter().map(|c| c.re.max(0.0)).collect());
    }
    let npx = pw * ph;
    let mut distance = vec![vec![f64::NAN; npx]; n_dir];
    let mut conf_nb = vec![vec![0.0; npx]; n_dir];
    let mut arc = vec![vec![0.0; npx]; n_dir];
    let mut supported = vec![vec![false; npx]; n_dir];
    let exp_nb = params.notebook_exponent();
    let exp_ms = params.manuscript_exponent();
    for o in 0..n_dir {
        for i in 0..npx {
            let a = u1[o][i];
            let b = u2[o][i];
            if a.is_finite() && b.is_finite() && b > params.eps {
                let d = a / b;
                supported[o][i] = true;
                distance[o][i] = d;
                conf_nb[o][i] = a * d.powf(exp_nb);
                arc[o][i] = a * d.powf(exp_ms);
            }
        }
    }
    Ok(GlyphFields {
        w: pw,
        h: ph,
        pad,
        c_per_scale,
        t_combined,
        u1,
        u2,
        distance,
        conf_nb,
        arc,
        supported,
    })
}
