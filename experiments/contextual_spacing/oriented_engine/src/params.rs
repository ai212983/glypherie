//! Frozen-model parameters with validation.
//!
//! Provenance: `yinyang_oriented_fields.OrientedFieldParams` (stage 1) and
//! `yinyang_multiscale_fields.MultiscaleFieldParams` (stage 2). The radial
//! exponent `q` is the source `k` in `1/r^q`; arc strength is `a` (never
//! `k`); `kappa` is the von Mises concentration (notebook mask width 4).

use crate::EngineError;

/// Radius `R` is the square kernel half-width: taps over `[-R, R]^2` with
/// radial `1/r^q` falloff and the origin zeroed (source DistanceEst sets the
/// origin to 0). Never a circular crop or a hard Euclidean cutoff.
#[derive(Debug, Clone)]
pub struct EngineParams {
    /// Radial exponent in `f1 = 1/r^q`, `f2 = 1/r^-(q+1)` (frozen: 2.0).
    pub q: f64,
    /// Von Mises angular concentration (frozen: 4.0).
    pub kappa: f64,
    /// Per-scale V1 Gaussian sigmas in px, ascending (frozen: half-octave
    /// five-scale progression around 1.5).
    pub sigmas: Vec<f64>,
    /// Per-scale combination weights (frozen: neutral uniform, H-CSF0
    /// ablation, not a CSF claim). Length must match `sigmas`.
    pub weights: Vec<f64>,
    /// Square kernel half-width in px (frozen: 12).
    pub radius: u32,
    /// Denominator floor: `U2 > eps` required for support (frozen: 1e-12).
    pub eps: f64,
    /// Undirected V1 orientations (frozen: 8).
    pub n_v1: usize,
    /// Directed channels (frozen: 16).
    pub n_directed: usize,
}

impl EngineParams {
    /// Exact frozen defaults (numeric parity target).
    pub fn frozen() -> Self {
        Self {
            q: 2.0,
            kappa: 4.0,
            sigmas: vec![0.75, 1.0606601717798212, 1.5, 2.1213203435596424, 3.0],
            weights: vec![1.0, 1.0, 1.0, 1.0, 1.0],
            radius: 12,
            eps: 1e-12,
            n_v1: 8,
            n_directed: 16,
        }
    }

    /// Guarded validation: every failure names the invariant (never silent
    /// clamping). Custom `q`/`R`/scales are genuine formula parameters, not
    /// aliases of retired controls.
    pub fn validate(&self) -> Result<(), EngineError> {
        if !self.q.is_finite() || self.q < 0.25 || self.q > 32.0 {
            return Err(EngineError::Invalid(format!(
                "q must be finite in [0.25, 32], got {}",
                self.q
            )));
        }
        if !self.kappa.is_finite() || self.kappa < 0.0 || self.kappa > 20.0 {
            return Err(EngineError::Invalid(format!(
                "kappa must be finite in [0, 20], got {}",
                self.kappa
            )));
        }
        if self.sigmas.is_empty() || self.sigmas.len() > 16 {
            return Err(EngineError::Invalid(format!(
                "need 1..=16 scales, got {}",
                self.sigmas.len()
            )));
        }
        for (i, s) in self.sigmas.iter().enumerate() {
            if !s.is_finite() || *s <= 0.0 || *s > 64.0 {
                return Err(EngineError::Invalid(format!(
                    "sigma[{i}] must be finite in (0, 64], got {s}"
                )));
            }
            if i > 0 && *s < self.sigmas[i - 1] {
                return Err(EngineError::Invalid("sigmas must be ascending".to_string()));
            }
        }
        if self.weights.len() != self.sigmas.len() {
            return Err(EngineError::Invalid(format!(
                "weights cover every scale: {} != {}",
                self.weights.len(),
                self.sigmas.len()
            )));
        }
        for (i, w) in self.weights.iter().enumerate() {
            if !w.is_finite() || *w < 0.0 {
                return Err(EngineError::Invalid(format!(
                    "weights must be finite and nonnegative, got weights[{i}] = {w}"
                )));
            }
        }
        if self.radius < 1 || self.radius > 64 {
            return Err(EngineError::Invalid(format!(
                "R must be an integer in 1..=64, got {}",
                self.radius
            )));
        }
        if !self.eps.is_finite() || self.eps <= 0.0 || self.eps > 1e-3 {
            return Err(EngineError::Invalid(format!(
                "eps must be finite in (0, 1e-3], got {}",
                self.eps
            )));
        }
        if self.n_v1 == 0 || self.n_v1 > 64 {
            return Err(EngineError::Invalid(format!(
                "n_v1 must be in 1..=64, got {}",
                self.n_v1
            )));
        }
        if self.n_directed == 0
            || self.n_directed > 128
            || !self.n_directed.is_multiple_of(self.n_v1)
        {
            return Err(EngineError::Invalid(format!(
                "n_directed must be a multiple of n_v1 in 1..=128, got {} over {}",
                self.n_directed, self.n_v1
            )));
        }
        Ok(())
    }

    /// V1 support half-width generalizing the stage-1 rule: `ceil(4*sigma)`.
    pub fn halfwidth_for_sigma(sigma: f64) -> i64 {
        (4.0 * sigma).ceil() as i64
    }

    /// Field margin: largest V1 half-support plus the square half-width.
    /// `R` enters the pad, so distant-ink support is exact, not cropped.
    pub fn pad(&self) -> i64 {
        let w = self
            .sigmas
            .iter()
            .map(|s| Self::halfwidth_for_sigma(*s))
            .max()
            .unwrap_or(0);
        w + self.radius as i64
    }

    /// Notebook-primary strength exponent derives from the active `q`
    /// (`q - 1`); never reuses the frozen `q = 2` exponent under custom `q`.
    pub fn notebook_exponent(&self) -> f64 {
        self.q - 1.0
    }

    /// Manuscript-alternate strength exponent derives from the active `q`.
    pub fn manuscript_exponent(&self) -> f64 {
        self.q + 1.0
    }
}

/// Score-time parameters (frozen: `tau = 0.5`, notebook primary,
/// `normalization_radius = 12` for Class L).
#[derive(Debug, Clone)]
pub struct ScoreParams {
    pub tau: f64,
    pub normalization_radius: u32,
}

impl ScoreParams {
    pub fn frozen() -> Self {
        Self {
            tau: 0.5,
            normalization_radius: FROZEN_NORMALIZATION_RADIUS,
        }
    }

    pub fn validate(&self) -> Result<(), EngineError> {
        if !self.tau.is_finite() || self.tau <= 0.0 || self.tau > 64.0 {
            return Err(EngineError::Invalid(format!(
                "tau must be finite in (0, 64], got {}",
                self.tau
            )));
        }
        if self.normalization_radius < 1 || self.normalization_radius > 64 {
            return Err(EngineError::Invalid(format!(
                "normalization_radius must be an integer in [1, 64], got {}",
                self.normalization_radius
            )));
        }
        Ok(())
    }
}

/// Tie rule TIE-v2: minimizing set within `tol = 1e-9 * max(1, m*)`.
pub const TIE_TOL_FACTOR: f64 = 1e-9;
/// Score unit bound from Cauchy-Schwarz.
pub const G2_BOUND: f64 = 128.0;
/// Weak-band `U2` floor (diagnostic only, separate from `eps`).
pub const FLOOR_U2: f64 = 1e-6;
/// Model identity for this runtime.
pub const MODEL_IDENTITY: &str = "yinyangfit-oriented-engine-v1";
/// Score-model identity for the experimental Class-L local normalization
/// (v1 G2 stays a frozen oracle; no UI selector, no fallback).
pub const LOCAL_ENERGY_MODEL_IDENTITY: &str = "yinyangfit-local-energy-v2";
/// Frozen normalizer window radius for Class L (role hypothesis:
/// source-inherited reference R = 12, not an optical default).
pub const FROZEN_NORMALIZATION_RADIUS: u32 = 12;
