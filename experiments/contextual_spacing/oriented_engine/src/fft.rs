//! Centered linear convolution matching the frozen FFT path.
//!
//! Provenance: `yinyang_oriented_fields.convolve_fft` computes the full
//! linear convolution (`irfft2(rfft2(a) * rfft2(b))` over the summed shape)
//! and crops `[kh//2 : kh//2+fh, kw//2 : kw//2+fw]` (`same` mode with the
//! kernel center at `(kh//2, kw//2)`; all kernels here are odd). This module
//! reproduces that convention with rustfft complex FFTs; agreement with the
//! frozen path is up to fp reassociation only (gated at 1e-9 relative G2).

use std::collections::HashMap;
use std::sync::Arc;

use rustfft::num_complex::Complex;
use rustfft::{Fft, FftPlanner};

/// Planner cache: one forward/inverse plan per 1D length.
///
/// `scratch`/`col_tmp` are reused across transforms (zeroed before each
/// reuse; scratch is planner workspace and never affects output values).
/// `fwd_calls`/`inv_calls` count 2D transforms for benchmarking only.
pub struct Conv {
    planner: FftPlanner<f64>,
    fwd: HashMap<usize, Arc<dyn Fft<f64>>>,
    inv: HashMap<usize, Arc<dyn Fft<f64>>>,
    scratch: Vec<Complex<f64>>,
    col_tmp: Vec<Complex<f64>>,
    fwd_calls: u64,
    inv_calls: u64,
}

/// Forward spectrum of one zero-padded input over the summed shape
/// (`m = iw + kw - 1`, `n = ih + kh - 1`). Reusable across kernels that
/// share the identical padded shape and input bytes. Never mutated by
/// [`Conv::conv_same_with_input`].
pub struct PaddedSpectrum {
    spec: Vec<Complex<f64>>,
    iw: usize,
    ih: usize,
    kw: usize,
    kh: usize,
}

impl Conv {
    // FftPlanner has no Default; new() builds the empty plan cache.
    #[allow(clippy::new_without_default)]
    pub fn new() -> Self {
        Self {
            planner: FftPlanner::new(),
            fwd: HashMap::new(),
            inv: HashMap::new(),
            scratch: Vec::new(),
            col_tmp: Vec::new(),
            fwd_calls: 0,
            inv_calls: 0,
        }
    }

    /// (forward 2D transforms, inverse 2D transforms) performed so far.
    pub fn fft_counts(&self) -> (u64, u64) {
        (self.fwd_calls, self.inv_calls)
    }

    /// Reset the transform counters (plans and buffers are retained).
    pub fn reset_counts(&mut self) {
        self.fwd_calls = 0;
        self.inv_calls = 0;
    }

    /// Reused workspace extent: (scratch len, column-tmp len).
    pub fn scratch_extent(&self) -> (usize, usize) {
        (self.scratch.len(), self.col_tmp.len())
    }

    fn plan_fwd(&mut self, len: usize) -> Arc<dyn Fft<f64>> {
        if let Some(p) = self.fwd.get(&len) {
            return Arc::clone(p);
        }
        let p = self.planner.plan_fft_forward(len);
        self.fwd.insert(len, Arc::clone(&p));
        p
    }

    fn plan_inv(&mut self, len: usize) -> Arc<dyn Fft<f64>> {
        if let Some(p) = self.inv.get(&len) {
            return Arc::clone(p);
        }
        let p = self.planner.plan_fft_inverse(len);
        self.inv.insert(len, Arc::clone(&p));
        p
    }

    fn use_scratch(&mut self, need: usize) {
        if self.scratch.len() < need {
            self.scratch.resize(need, Complex::new(0.0, 0.0));
        }
        for v in self.scratch.iter_mut().take(need) {
            *v = Complex::new(0.0, 0.0);
        }
    }

    fn use_col_tmp(&mut self, h: usize) {
        if self.col_tmp.len() < h {
            self.col_tmp.resize(h, Complex::new(0.0, 0.0));
        }
        for v in self.col_tmp.iter_mut().take(h) {
            *v = Complex::new(0.0, 0.0);
        }
    }

    fn fft_2d_forward(&mut self, buf: &mut [Complex<f64>], w: usize, h: usize) {
        let row = self.plan_fwd(w);
        let col = self.plan_fwd(h);
        let need = row
            .get_inplace_scratch_len()
            .max(col.get_inplace_scratch_len());
        self.use_scratch(need);
        self.use_col_tmp(h);
        // Split borrows: plans are Arcs, buffers are disjoint fields.
        let (scratch, col_tmp) = (&mut self.scratch, &mut self.col_tmp);
        for r in 0..h {
            row.process_with_scratch(&mut buf[r * w..(r + 1) * w], scratch);
        }
        let tmp = &mut col_tmp[..h];
        for c in 0..w {
            for r in 0..h {
                tmp[r] = buf[r * w + c];
            }
            col.process_with_scratch(tmp, scratch);
            for r in 0..h {
                buf[r * w + c] = tmp[r];
            }
        }
        self.fwd_calls += 1;
    }

    fn fft_2d_inverse(&mut self, buf: &mut [Complex<f64>], w: usize, h: usize) {
        let row = self.plan_inv(w);
        let col = self.plan_inv(h);
        let need = row
            .get_inplace_scratch_len()
            .max(col.get_inplace_scratch_len());
        self.use_scratch(need);
        self.use_col_tmp(h);
        let (scratch, col_tmp) = (&mut self.scratch, &mut self.col_tmp);
        for r in 0..h {
            row.process_with_scratch(&mut buf[r * w..(r + 1) * w], scratch);
        }
        let tmp = &mut col_tmp[..h];
        for c in 0..w {
            for r in 0..h {
                tmp[r] = buf[r * w + c];
            }
            col.process_with_scratch(tmp, scratch);
            for r in 0..h {
                buf[r * w + c] = tmp[r];
            }
        }
        let scale = 1.0 / (w as f64 * h as f64);
        for v in buf.iter_mut() {
            *v *= scale;
        }
        self.inv_calls += 1;
    }

    /// Zero-padded forward spectrum of one input over the summed shape.
    /// Same padding, shape and transform order as [`Conv::conv_same`];
    /// the returned spectrum is owned by the caller (bounded per-call).
    pub fn forward_padded(
        &mut self,
        image: &[Complex<f64>],
        iw: usize,
        ih: usize,
        kw: usize,
        kh: usize,
    ) -> PaddedSpectrum {
        assert!(iw > 0 && ih > 0 && kw > 0 && kh > 0);
        assert_eq!(image.len(), iw * ih);
        let m = iw + kw - 1;
        let n = ih + kh - 1;
        let mut a = vec![Complex::new(0.0, 0.0); n * m];
        for r in 0..ih {
            a[r * m..r * m + iw].copy_from_slice(&image[r * iw..(r + 1) * iw]);
        }
        self.fft_2d_forward(&mut a, m, n);
        PaddedSpectrum {
            spec: a,
            iw,
            ih,
            kw,
            kh,
        }
    }

    /// Full linear convolution cropped to `same` reusing a compatible
    /// input spectrum: identical kernel padding/transform, complex
    /// product in the original association (`input * kernel`), identical
    /// inverse scaling and crop. The cached spectrum is never mutated.
    pub fn conv_same_with_input(
        &mut self,
        input: &PaddedSpectrum,
        kernel: &[Complex<f64>],
        kw: usize,
        kh: usize,
    ) -> Vec<Complex<f64>> {
        assert_eq!(kernel.len(), kw * kh);
        assert_eq!(input.kw, kw);
        assert_eq!(input.kh, kh);
        let (iw, ih) = (input.iw, input.ih);
        let m = iw + kw - 1;
        let n = ih + kh - 1;
        let mut b = vec![Complex::new(0.0, 0.0); n * m];
        for r in 0..kh {
            b[r * m..r * m + kw].copy_from_slice(&kernel[r * kw..(r + 1) * kw]);
        }
        self.fft_2d_forward(&mut b, m, n);
        let mut prod = vec![Complex::new(0.0, 0.0); n * m];
        for ((p, x), y) in prod.iter_mut().zip(input.spec.iter()).zip(b.iter()) {
            *p = *x * *y;
        }
        self.fft_2d_inverse(&mut prod, m, n);
        let oy = kh / 2;
        let ox = kw / 2;
        let mut out = Vec::with_capacity(iw * ih);
        for r in 0..ih {
            out.extend_from_slice(&prod[(r + oy) * m + ox..(r + oy) * m + ox + iw]);
        }
        out
    }

    /// Full linear convolution cropped to `same`, complex in/out.
    pub fn conv_same(
        &mut self,
        image: &[Complex<f64>],
        iw: usize,
        ih: usize,
        kernel: &[Complex<f64>],
        kw: usize,
        kh: usize,
    ) -> Vec<Complex<f64>> {
        let input = self.forward_padded(image, iw, ih, kw, kh);
        self.conv_same_with_input(&input, kernel, kw, kh)
    }

    /// Explicit-summation oracle (`same` mode). Independent reference for
    /// the FFT path: identical padding/centering convention, no shared FFT
    /// code. Odd kernel dims required (all stage kernels are odd).
    pub fn conv_direct(
        image: &[Complex<f64>],
        iw: usize,
        ih: usize,
        kernel: &[Complex<f64>],
        kw: usize,
        kh: usize,
    ) -> Vec<Complex<f64>> {
        assert!(
            kw % 2 == 1 && kh % 2 == 1,
            "direct oracle needs odd kernels"
        );
        // True convolution: correlate with the flipped kernel.
        let mut kf = vec![Complex::new(0.0, 0.0); kw * kh];
        for r in 0..kh {
            for c in 0..kw {
                kf[r * kw + c] = kernel[(kh - 1 - r) * kw + (kw - 1 - c)];
            }
        }
        let ph = kh / 2;
        let pw = kw / 2;
        let pw2 = kw - 1 - pw;
        let ph2 = kh - 1 - ph;
        let gw = iw + pw + pw2;
        let mut pad = vec![Complex::new(0.0, 0.0); (ih + ph + ph2) * gw];
        for r in 0..ih {
            pad[(r + ph) * gw + pw..(r + ph) * gw + pw + iw]
                .copy_from_slice(&image[r * iw..(r + 1) * iw]);
        }
        let mut out = vec![Complex::new(0.0, 0.0); iw * ih];
        for r in 0..kh {
            let row = &pad[r * gw..(r + ih) * gw];
            for c in 0..kw {
                let k = kf[r * kw + c];
                for y in 0..ih {
                    let src = &row[y * gw + c..y * gw + c + iw];
                    let dst = &mut out[y * iw..(y + 1) * iw];
                    for x in 0..iw {
                        dst[x] += k * src[x];
                    }
                }
            }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fft_matches_direct_on_v1_sized_inputs() {
        let mut conv = Conv::new();
        // Deterministic pseudo-random image and kernel.
        let (iw, ih, kw, kh) = (37, 29, 13, 13);
        let mut rng: u64 = 0x12345678;
        let mut next = move || {
            rng = rng
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            ((rng >> 33) as f64) / ((1u64 << 31) as f64) - 0.5
        };
        let image: Vec<Complex<f64>> = (0..iw * ih).map(|_| Complex::new(next(), next())).collect();
        let kernel: Vec<Complex<f64>> =
            (0..kw * kh).map(|_| Complex::new(next(), next())).collect();
        let a = conv.conv_same(&image, iw, ih, &kernel, kw, kh);
        let b = Conv::conv_direct(&image, iw, ih, &kernel, kw, kh);
        let mut worst: f64 = 0.0;
        for (x, y) in a.iter().zip(b.iter()) {
            worst = worst.max((x - y).norm());
        }
        assert!(worst < 1e-12, "fft/direct worst = {worst}");
    }

    #[test]
    fn reused_input_matches_direct_call_bitwise() {
        let mut conv = Conv::new();
        let (iw, ih, kw, kh) = (37, 29, 13, 13);
        let mut rng: u64 = 0x9e3779b9;
        let mut next = move || {
            rng = rng
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            ((rng >> 33) as f64) / ((1u64 << 31) as f64) - 0.5
        };
        let image: Vec<Complex<f64>> = (0..iw * ih).map(|_| Complex::new(next(), next())).collect();
        let k1: Vec<Complex<f64>> = (0..kw * kh).map(|_| Complex::new(next(), next())).collect();
        let k2: Vec<Complex<f64>> = (0..kw * kh).map(|_| Complex::new(next(), next())).collect();
        let before = conv.fft_counts();
        let input = conv.forward_padded(&image, iw, ih, kw, kh);
        let before_bytes: Vec<(u64, u64)> = input
            .spec
            .iter()
            .map(|c| (c.re.to_bits(), c.im.to_bits()))
            .collect();
        let r1 = conv.conv_same_with_input(&input, &k1, kw, kh);
        let r2 = conv.conv_same_with_input(&input, &k2, kw, kh);
        // Cached input spectrum is never mutated by reuse.
        for (c, b) in input.spec.iter().zip(before_bytes.iter()) {
            assert_eq!((c.re.to_bits(), c.im.to_bits()), *b);
        }
        let d1 = conv.conv_same(&image, iw, ih, &k1, kw, kh);
        let d2 = conv.conv_same(&image, iw, ih, &k2, kw, kh);
        for (x, y) in r1.iter().zip(d1.iter()) {
            assert_eq!(
                (x.re.to_bits(), x.im.to_bits()),
                (y.re.to_bits(), y.im.to_bits())
            );
        }
        for (x, y) in r2.iter().zip(d2.iter()) {
            assert_eq!(
                (x.re.to_bits(), x.im.to_bits()),
                (y.re.to_bits(), y.im.to_bits())
            );
        }
        // One shared input forward + two kernel forwards + two inverses
        // beyond the spectrum build (which itself cost one forward).
        let (f0, i0) = before;
        let (f1, i1) = conv.fft_counts();
        assert_eq!((f1 - f0, i1 - i0), (1 + 2 + 4, 2 + 2));
    }
}
