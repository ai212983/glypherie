// Experimental filtered dot product. This file is copied into an isolated
// generator checkout; maintained runtime never imports experiments.
// Rump (2015), https://www.tuhh.de/ti3/paper/rump/Ru14c.pdf:
// matrix products admit order-independent absolute rounding bounds.
// We use the looser gamma_(2n) max-product bound, with outward-rounded
// evaluation and 2n minimum-subnormal units for gradual underflow. Only
// the proposal's fadd/fmul instructions may receive LLVM reassoc; guards,
// finite tests, error arithmetic and every caller remain strict.

#[inline(never)]
fn selective_dot_proposal(a: &[f64], b: &[f64]) -> f64 {
    let mut value = 0.0;
    for i in 0..a.len() {
        value += a[i] * b[i];
    }
    value
}

fn bounded_dot(a: &[f64], b: &[f64]) -> Option<f64> {
    assert_eq!(a.len(), b.len());
    if a.is_empty() {
        return None;
    }
    let mut amax = 0.0_f64;
    let mut bmax = 0.0_f64;
    for (&x, &y) in a.iter().zip(b) {
        if !x.is_finite() || !y.is_finite() {
            return None;
        }
        amax = amax.max(x.abs());
        bmax = bmax.max(y.abs());
    }
    // Conversion is exact for all WASM slice lengths. Upward rounding also
    // covers larger host lengths. No near-one gamma denominator is used.
    let n = (a.len() as f64).next_up();
    let operations = (2.0 * n).next_up();
    let nu = (operations * (f64::EPSILON / 2.0)).next_up();
    if nu >= 0.5 {
        return None;
    }
    let gamma = (nu / (1.0 - nu).next_down()).next_up();
    let magnitude = (n * (amax * bmax).next_up()).next_up();
    // Reserve space for roundoff in any partial sum. No finite-value or
    // no-underflow assumptions are passed to the compiler.
    if !magnitude.is_finite() || magnitude > f64::MAX / 4.0 {
        return None;
    }
    let underflow = (operations * f64::from_bits(1)).next_up();
    let error = ((gamma * magnitude).next_up() + underflow).next_up();
    let value = selective_dot_proposal(a, b);
    // This certifies only the sign of the local dot, not the least-squares
    // solution or active set. Strict solver delivery checks remain required.
    if value.is_finite() && error.is_finite() && value.abs() > error {
        Some(value)
    } else {
        None
    }
}

#[cfg(test)]
mod selective_tests {
    use super::*;

    #[test]
    fn ordinary_products_and_cancellation() {
        assert_eq!(bounded_dot(&[1.0, 2.0], &[3.0, 4.0]), Some(11.0));
        assert_eq!(bounded_dot(&[1.0, 1.0], &[1.0, -1.0]), None);
        assert_eq!(bounded_dot(&[1e16, 1.0, -1e16], &[1.0; 3]), None);
        assert_eq!(bounded_dot(&[0.0, -0.0], &[1.0, 1.0]), None);
    }

    #[test]
    fn exceptional_and_extreme_operands_abstain() {
        for x in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(bounded_dot(&[x], &[1.0]), None);
        }
        assert_eq!(bounded_dot(&[1e308], &[1e308]), None);
        assert_eq!(bounded_dot(&[f64::from_bits(1)], &[0.5]), None);
        assert_eq!(bounded_dot(&[], &[]), None);
        assert_eq!(bounded_dot(&[1e-300], &[1.0]), Some(1e-300));
    }
}
