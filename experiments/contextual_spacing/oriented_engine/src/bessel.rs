//! Modified Bessel I0 for the von Mises mask normalization `2*pi*I0(kappa)`.
//!
//! Direct Taylor series `I0(x) = sum_k (x^2/4)^k / (k!)^2` with the term
//! recurrence `t_{k+1} = t_k * (x^2/4) / (k+1)^2`. All terms are positive,
//! so forward summation is stable; the guarded `kappa <= 20` range peaks
//! near `1e7` with no overflow. Verified against `numpy.i0(4.0)` in tests.

/// I0(x) for finite x >= 0.
pub fn bessel_i0(x: f64) -> f64 {
    debug_assert!(x.is_finite() && x >= 0.0);
    let z = x * x / 4.0;
    let mut term = 1.0;
    let mut sum = 1.0;
    for k in 1..1000 {
        term *= z / (k as f64 * k as f64);
        sum += term;
        if term < 1e-17 * sum {
            break;
        }
    }
    sum
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn i0_matches_numpy_at_frozen_kappa() {
        // numpy.i0(4.0) to full double printout.
        let got = bessel_i0(4.0);
        assert!((got - 11.30192195213633).abs() <= 1e-12, "i0(4) = {got}");
    }
}
