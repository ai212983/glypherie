//! Reference norm arithmetic, adapted from CPython 3.14 `vector_norm`.
//! PSF license: `vendor/cpython-math/LICENSE`; provenance: its `PATCH.md`.
//! Error-free products and compensated sums follow Ogita, Rump and Oishi
//! (2005), Algorithms 1.1 and 3.2–3.5. The guarded WASM product follows
//! https://www.tuhh.de/ti3/paper/rump/OgRuOi05.pdf without changing the
//! product/correction bits or compensated norm's operation sequence.

fn fast_sum(a: f64, b: f64) -> (f64, f64) {
    let hi = a + b;
    (hi, (a - hi) + b)
}

fn product(a: f64, b: f64) -> (f64, f64) {
    let hi = a * b;
    #[cfg(target_arch = "wasm32")]
    if let Some(error) = split_product_error(a, b, hi) {
        return (hi, error);
    }
    (hi, a.mul_add(b, -hi))
}

/// Dekker/Veltkamp TwoProduct (Ogita et al., algorithms 3.2–3.4).
/// On WASM the ordinary FMA is software-emulated. These conservative
/// exponent guards prove all split/product intermediates stay in range:
/// nonzero low parts are at least 2^-502, so their product is at least
/// 2^-1004 (normal); splitting magnitudes at most 2^450 reaches below
/// 2^478 and partial products below 2^902. Thus the residual is exact,
/// representable, and equal to FMA(a, b, -(a*b)). These are arithmetic
/// safety guards, not geometric tolerances. Other inputs retain FMA.
#[cfg(any(target_arch = "wasm32", test))]
fn split_product_error(a: f64, b: f64, hi: f64) -> Option<f64> {
    if (a == 0.0 && b.is_finite()) || (b == 0.0 && a.is_finite()) {
        // Exact cancellation has positive zero in round-to-nearest,
        // including when the rounded product itself has negative zero.
        return Some(0.0);
    }
    const LOW: f64 = f64::from_bits((1023 - 450) << 52);
    const HIGH: f64 = f64::from_bits((1023 + 450) << 52);
    let (aa, bb) = (a.abs(), b.abs());
    if !(aa >= LOW && aa <= HIGH && bb >= LOW && bb <= HIGH) {
        return None;
    }
    let split = |x: f64| {
        let c = 134_217_729.0 * x; // 2^27 + 1, algorithm 3.2.
        let high = c - (c - x);
        (high, x - high)
    };
    let (a1, a2) = split(a);
    let (b1, b2) = split(b);
    let error = a2 * b2 - (((hi - a1 * b1) - a2 * b1) - a1 * b2);
    // A zero exact residual has FMA's positive-zero representation.
    Some(if error == 0.0 { 0.0 } else { error })
}

fn pow2(exponent: i32) -> f64 {
    if exponent >= -1022 {
        f64::from_bits(((exponent + 1023) as u64) << 52)
    } else {
        f64::from_bits(1_u64 << (exponent + 1074))
    }
}

/// Two-coordinate specialization of the reference's scaled, compensated norm.
pub(crate) fn hypot(x: f64, y: f64) -> f64 {
    let coords = [x.abs(), y.abs()];
    let max = coords[0].max(coords[1]);
    if max.is_infinite() {
        return max;
    }
    if coords.iter().any(|v| v.is_nan()) {
        return f64::NAN;
    }
    if max == 0.0 {
        return 0.0;
    }
    let bits = max.to_bits();
    let biased = ((bits >> 52) & 0x7ff) as i32;
    let exponent = if biased == 0 {
        (63 - bits.leading_zeros() as i32) - 1073
    } else {
        biased - 1022
    };
    if exponent < -1023 {
        return f64::MIN_POSITIVE
            * hypot(coords[0] / f64::MIN_POSITIVE, coords[1] / f64::MIN_POSITIVE);
    }
    let scale = pow2(-exponent);
    let (mut sum, mut products, mut additions) = (1.0, 0.0, 0.0);
    for coordinate in coords {
        let value = coordinate * scale;
        let (square, error) = product(value, value);
        let (total, tail) = fast_sum(sum, square);
        sum = total;
        products += error;
        additions += tail;
    }
    let mut root = (sum - 1.0 + (products + additions)).sqrt();
    let (square, error) = product(-root, root);
    let (total, tail) = fast_sum(sum, square);
    sum = total;
    products += error;
    additions += tail;
    let remainder = sum - 1.0 + (products + additions);
    root += remainder / (2.0 * root);
    root / scale
}

#[cfg(test)]
mod tests {
    use super::{hypot, split_product_error};

    #[test]
    fn split_product_matches_exact_rational_residuals() {
        use num_rational::BigRational;
        use num_traits::{FromPrimitive, ToPrimitive};

        // Independent rational arithmetic checks the result, including
        // exponent guards, carry boundaries and both signs. The theorem's
        // range proof is the basis; these witnesses guard its adaptation.
        let low = f64::from_bits((1023 - 450) << 52);
        let high = f64::from_bits((1023 + 450) << 52);
        let values = [
            low,
            f64::from_bits(low.to_bits() + 1),
            0.1,
            f64::from_bits(1.0f64.to_bits() - 1),
            1.0,
            f64::from_bits(1.0f64.to_bits() + 1),
            f64::from_bits(high.to_bits() - 1),
            high,
        ];
        for a in values {
            for b in values {
                for (a, b) in [(a, b), (-a, b), (a, -b), (-a, -b)] {
                    let hi = a * b;
                    let error = split_product_error(a, b, hi).expect("proved safe range");
                    let exact = BigRational::from_f64(a).unwrap()
                        * BigRational::from_f64(b).unwrap()
                        - BigRational::from_f64(hi).unwrap();
                    assert_eq!(error.to_bits(), exact.to_f64().unwrap().to_bits());
                    assert_eq!(error.to_bits(), a.mul_add(b, -hi).to_bits());
                }
            }
        }
    }

    #[test]
    fn split_product_guards_extremes_and_signed_zero() {
        let low = f64::from_bits((1023 - 450) << 52);
        let high = f64::from_bits((1023 + 450) << 52);
        for a in [
            f64::from_bits(low.to_bits() - 1),
            f64::from_bits(high.to_bits() + 1),
            f64::from_bits(1),
            f64::MAX,
            f64::INFINITY,
            f64::NAN,
        ] {
            assert!(split_product_error(a, 1.0, a).is_none());
            assert!(split_product_error(1.0, a, a).is_none());
        }
        for a in [0.0, -0.0] {
            for b in [0.0, -0.0, 1.0, -1.0, f64::MAX, f64::from_bits(1)] {
                let hi = a * b;
                assert_eq!(split_product_error(a, b, hi).unwrap().to_bits(), 0);
                assert_eq!(a.mul_add(b, -hi).to_bits(), 0);
                assert_eq!(split_product_error(b, a, hi).unwrap().to_bits(), 0);
            }
            assert!(split_product_error(a, f64::INFINITY, a).is_none());
        }
    }

    #[test]
    fn compensated_rounding_matches_reference_witnesses() {
        // CPython 3.14.7 results from a seeded binary64 differential run;
        // platform hypot differs by one ulp on these finite inputs.
        for (x, y, expected) in [
            (0xcae0857d003e15f3, 0xcb42d48cd887e36c, 0x4b42d500ce526c47),
            (0xdcb824a66839693d, 0xde591daa466a1f60, 0x5e591daa466a1f61),
            (0x40a62453b9b6c214, 0xc231bdf812ff89f3, 0x4231bdf812ff89f6),
            (0xd19d4845d6640782, 0xd0b681628e2cf659, 0x519d4845d6ee6793),
            (0x186ce2e00d642be8, 0x99f84e3d1291fcfa, 0x19f84e3d1291fcfe),
        ] {
            let (x, y) = (f64::from_bits(x), f64::from_bits(y));
            assert_eq!(hypot(x, y).to_bits(), expected);
            assert_eq!(hypot(y, x).to_bits(), expected);
        }
    }

    #[test]
    fn preserves_scale_sign_and_special_values() {
        for scale in [2.0_f64.powi(-900), 1.0, 2.0_f64.powi(900)] {
            for (x, y) in [(3.0, 4.0), (-3.0, 4.0), (4.0, -3.0)] {
                assert_eq!(hypot(x * scale, y * scale), 5.0 * scale);
            }
        }
        assert_eq!(hypot(-0.0, 0.0).to_bits(), 0);
        assert_eq!(hypot(f64::from_bits(1), 0.0).to_bits(), 1);
        assert_eq!(hypot(f64::from_bits(3), f64::from_bits(4)).to_bits(), 5);
        assert_eq!(hypot(f64::INFINITY, f64::NAN), f64::INFINITY);
        assert!(hypot(1.0, f64::NAN).is_nan());
        assert_eq!(hypot(f64::MAX, f64::MAX), f64::INFINITY);
    }
}
