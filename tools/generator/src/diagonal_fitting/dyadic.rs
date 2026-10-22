//! Checked-integer exact tier for binary-fraction geometry.
//!
//! Source architecture: adaptive exact computation with certified filtering ([Shewchuk predicates](https://www.cs.cmu.edu/~quake/robust.html))
//! and layered exact representation ([CGAL `Lazy_exact_nt`](https://doc.cgal.org/latest/Number_types/classCGAL_1_1Lazy__exact__nt.html)).
//! Project adaptation: `Dy` (`i128` mantissa with binary exponent) proves
//! orientation, separation and chord predicates with checked integer
//! arithmetic. Overflow, non-dyadic or oversized input returns `None` to
//! the existing exact rational fallback. Never resnaps input.

#[cfg(test)]
use num_bigint::{BigInt, Sign};
#[cfg(test)]
use num_rational::BigRational;
#[cfg(test)]
use num_traits::{ToPrimitive, Zero};

/// Exact binary fraction `m * 2^e` in canonical form (zero, or odd `m`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Dy {
    pub(crate) m: i128,
    pub(crate) e: i32,
}

/// Exact dyadic point with per-coordinate values.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct DyPt {
    pub(crate) x: Dy,
    pub(crate) y: Dy,
}

/// Canonical zero.
const ZERO: Dy = Dy { m: 0, e: 0 };

/// Remove factors of two from the mantissa, widening the exponent.
fn normalize(m: i128, e: i32) -> Option<Dy> {
    if m == 0 {
        return Some(ZERO);
    }
    let mut m = m;
    let mut e = e;
    // At most 127 halvings; the increment cannot overflow a live exponent.
    while m & 1 == 0 {
        m >>= 1;
        e = e.checked_add(1)?;
    }
    Some(Dy { m, e })
}

/// Binary logarithm of a denominator, or `None` for non-powers of two
/// and oversized inputs.
#[cfg(test)]
fn denom_log2(d: &BigInt) -> Option<i32> {
    let (sign, bytes) = d.to_bytes_be();
    if matches!(sign, Sign::Minus) || bytes.is_empty() || bytes.len() > 4096 {
        return None;
    }
    let mut found: Option<i32> = None;
    for (i, b) in bytes.iter().enumerate() {
        if *b == 0 {
            continue;
        }
        if !b.is_power_of_two() || found.is_some() {
            return None;
        }
        found = Some((bytes.len() - 1 - i) as i32 * 8 + b.trailing_zeros() as i32);
    }
    found
}

/// Exact dyadic value of one rational, or `None` for non-dyadic,
/// oversized or extreme-exponent input.
#[cfg(test)]
pub(crate) fn from_rational(r: &BigRational) -> Option<Dy> {
    if r.is_zero() {
        return Some(ZERO);
    }
    let m = r.numer().to_i128()?;
    // Reduced rationals carry an odd numerator over a dyadic denominator.
    let e = denom_log2(r.denom())?.checked_neg()?;
    normalize(m, e)
}

/// Exact dyadic point from borrowed coordinates, without cloning the
/// underlying integers.
#[cfg(test)]
pub(crate) fn point_from_refs(p: (&BigRational, &BigRational)) -> Option<DyPt> {
    Some(DyPt {
        x: from_rational(p.0)?,
        y: from_rational(p.1)?,
    })
}

/// Exact dyadic images of one immutable hull, or `None` when any vertex
/// falls outside the tier. Prepared once per hull and reused across
/// every predicate on it, so ordinary dyadic input never rebuilds
/// `BigRational` determinants per triple.
#[cfg(test)]
pub(crate) fn slice(ps: &[(BigRational, BigRational)]) -> Option<Vec<DyPt>> {
    ps.iter().map(|p| point_from_refs((&p.0, &p.1))).collect()
}

/// Exact `m * 2^k`, or `None` on overflow. `checked_shl` only checks the
/// shift count, so the shift-back comparison proves no value bit was lost.
fn scale_up(m: i128, k: u32) -> Option<i128> {
    if m == 0 || k == 0 {
        return Some(m);
    }
    if k >= 128 {
        return None;
    }
    let s = m.checked_shl(k)?;
    if s.checked_shr(k) != Some(m) {
        return None;
    }
    Some(s)
}

/// Exact sum, or `None` on overflow or extreme exponent spread.
pub(crate) fn add(a: Dy, b: Dy) -> Option<Dy> {
    if a.m == 0 {
        return Some(b);
    }
    if b.m == 0 {
        return Some(a);
    }
    let e = a.e.min(b.e);
    let da = u32::try_from(a.e.checked_sub(e)?).ok()?;
    let db = u32::try_from(b.e.checked_sub(e)?).ok()?;
    normalize(scale_up(a.m, da)?.checked_add(scale_up(b.m, db)?)?, e)
}

/// Exact negation, or `None` for `i128::MIN`.
fn neg(a: Dy) -> Option<Dy> {
    if a.m == 0 {
        return Some(ZERO);
    }
    Some(Dy {
        m: a.m.checked_neg()?,
        e: a.e,
    })
}

/// Exact difference, or `None` on overflow.
pub(crate) fn sub(a: Dy, b: Dy) -> Option<Dy> {
    add(a, neg(b)?)
}

/// Exact product, or `None` on overflow.
pub(crate) fn mul(a: Dy, b: Dy) -> Option<Dy> {
    if a.m == 0 || b.m == 0 {
        return Some(ZERO);
    }
    normalize(a.m.checked_mul(b.m)?, a.e.checked_add(b.e)?)
}

/// Exact sign: -1, 0 or +1.
pub(crate) fn sign(a: Dy) -> i8 {
    if a.m == 0 {
        0
    } else if a.m > 0 {
        1
    } else {
        -1
    }
}

/// Exact ordering, or `None` on overflow.
pub(crate) fn cmp(a: Dy, b: Dy) -> Option<std::cmp::Ordering> {
    Some(sign(sub(a, b)?).cmp(&0))
}

/// Exact dot product of two displacements, or `None` on overflow.
pub(crate) fn dot(ax: Dy, ay: Dy, bx: Dy, by: Dy) -> Option<Dy> {
    add(mul(ax, bx)?, mul(ay, by)?)
}

/// Exact orientation sign of `(o, a, b)`, including true zero from
/// checked integers. `None` on overflow or non-dyadic input.
pub(crate) fn orient(o: &DyPt, a: &DyPt, b: &DyPt) -> Option<i8> {
    if o == a || a == b || o == b {
        return Some(0);
    }
    let x1 = sub(a.x, o.x)?;
    let y1 = sub(a.y, o.y)?;
    let x2 = sub(b.x, o.x)?;
    let y2 = sub(b.y, o.y)?;
    Some(sign(sub(mul(x1, y2)?, mul(y1, x2)?)?))
}

/// Exact orientation directly on rationals: dyadic images first, so no
/// `BigRational` determinant is built. `None` falls back.
#[cfg(test)]
pub(crate) fn orient_rats(
    o: (&BigRational, &BigRational),
    a: (&BigRational, &BigRational),
    b: (&BigRational, &BigRational),
) -> Option<i8> {
    orient(
        &point_from_refs((o.0, o.1))?,
        &point_from_refs((a.0, a.1))?,
        &point_from_refs((b.0, b.1))?,
    )
}

/// Exact chord-monotone verdict over rationals, or `None` on overflow
/// or non-dyadic input. Matches the existing exact predicate, including
/// degenerate `Some(false)`.
#[cfg(test)]
pub(crate) fn chord_monotone(ctrls: &[(BigRational, BigRational)]) -> Option<bool> {
    if ctrls.len() < 2 {
        return Some(false);
    }
    let c = slice(ctrls)?;
    if c.first() == c.last() {
        return Some(false);
    }
    let (cx, cy) = (
        sub(c[c.len() - 1].x, c[0].x)?,
        sub(c[c.len() - 1].y, c[0].y)?,
    );
    if cx.m == 0 && cy.m == 0 {
        return Some(false);
    }
    for w in c.windows(2) {
        let (lx, ly) = (sub(w[1].x, w[0].x)?, sub(w[1].y, w[0].y)?);
        if sign(dot(lx, ly, cx, cy)?) != 1 {
            return Some(false);
        }
    }
    Some(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use num_bigint::BigInt;
    use num_traits::{Signed, Zero};

    fn int_rat(n: i128) -> BigRational {
        BigRational::from_integer(n.into())
    }

    fn rat(n: i128, d: i128) -> BigRational {
        BigRational::new(n.into(), d.into())
    }

    fn dpt(p: &(BigRational, BigRational)) -> DyPt {
        point_from_refs((&p.0, &p.1)).unwrap()
    }

    fn exact_orient(
        a: &(BigRational, BigRational),
        b: &(BigRational, BigRational),
        c: &(BigRational, BigRational),
    ) -> i8 {
        let v = (&b.0 - &a.0) * (&c.1 - &a.1) - (&b.1 - &a.1) * (&c.0 - &a.0);
        if v.is_zero() {
            0
        } else if v.is_positive() {
            1
        } else {
            -1
        }
    }

    #[test]
    fn from_rational_classifies_dyadic_and_other() {
        // Dyadic integers and fractions land exactly, already reduced.
        assert_eq!(from_rational(&int_rat(7)), Some(Dy { m: 7, e: 0 }));
        assert_eq!(from_rational(&rat(3, 4)), Some(Dy { m: 3, e: -2 }));
        assert_eq!(from_rational(&rat(6, 8)), Some(Dy { m: 3, e: -2 }));
        assert_eq!(from_rational(&int_rat(0)), Some(ZERO));
        // Non-dyadic denominators never enter the tier.
        for (n, d) in [(1, 3), (2, 6), (1, 10), (355, 113)] {
            assert_eq!(from_rational(&rat(n, d)), None);
        }
        // Oversized numerators fall through to the rational fallback.
        let huge = BigRational::new(BigInt::from(1) << 200, 1.into());
        assert_eq!(from_rational(&huge), None);
        let neg_bits: BigInt = BigInt::from(1) << 200;
        let huge_neg = BigRational::new(-neg_bits, 1.into());
        assert_eq!(from_rational(&huge_neg), None);
        // Oversized non-dyadic denominators fall through as well.
        let wide = BigRational::new(1.into(), BigInt::from(10).pow(5000).into());
        assert_eq!(from_rational(&wide), None);
    }

    #[test]
    fn min_zero_and_subnormal_inputs_stay_exact() {
        // `i128::MIN` normalizes by halving, never by negating.
        let min = BigRational::from_integer(i128::MIN.into());
        assert_eq!(from_rational(&min), Some(Dy { m: -1, e: 127 }));
        assert_eq!(from_rational(&int_rat(0)), Some(ZERO));
        // Extreme dyadic magnitudes are representable; normalization
        // keeps pure powers exact, so 2^100 squares to 2^200 exactly.
        let tiny = BigRational::new(1.into(), BigInt::from(2).pow(1074));
        let t = from_rational(&tiny).expect("tiny dyadic fits");
        assert_eq!((t.m, t.e), (1, -1074));
        assert_eq!(mul(t, t).map(sign), Some(1));
        let big = BigRational::new(BigInt::from(2).pow(100), 1.into());
        let b = from_rational(&big).expect("2^100 fits");
        assert_eq!((b.m, b.e), (1, 100));
        assert_eq!(mul(b, b), Some(Dy { m: 1, e: 200 }));
    }

    #[test]
    fn scale_alignment_overflow_returns_none() {
        // A 2000-binary-order spread cannot align in `i128`.
        let hi = Dy { m: 1, e: 1000 };
        let lo = Dy { m: 1, e: -1000 };
        assert!(add(hi, lo).is_none());
        assert!(sub(hi, lo).is_none());
        // Exponent sums past `i32::MAX` fail closed.
        let wide = Dy { m: 1, e: i32::MAX };
        assert!(mul(wide, Dy { m: 1, e: 1 }).is_none());
        // Same-exponent addition stays exact: (1 + 2) * 2^MAX.
        assert_eq!(
            add(wide, Dy { m: 2, e: i32::MAX }),
            Some(Dy { m: 3, e: i32::MAX })
        );
        // `MIN` negation and wrap-prone shifts fail closed.
        assert!(neg(Dy { m: i128::MIN, e: 0 }).is_none());
        assert!(add(Dy { m: 1, e: 0 }, Dy { m: 1, e: -128 }).is_none());
        // `i128::MIN` differences can legitimately defer: 2^127 - (-2^-1)
        // needs 129 significant bits.
        assert!(sub(Dy { m: 1, e: 127 }, Dy { m: -1, e: -1 }).is_none());
        assert_eq!(
            sub(Dy { m: 1, e: 127 }, Dy { m: 1, e: 127 }),
            Some(Dy { m: 0, e: 0 })
        );
    }

    #[test]
    fn scale_up_guards_value_overflow_not_just_count() {
        // `checked_shl` only checks the shift count; the shift-back
        // comparison proves no value bit was lost.
        assert_eq!(scale_up(1, 127), None);
        assert_eq!(scale_up(i128::MAX, 1), None);
        assert_eq!(scale_up(-1, 127), Some(i128::MIN));
        assert_eq!(scale_up(i128::MIN, 1), None);
        assert_eq!(scale_up(3, 0), Some(3));
        assert_eq!(scale_up(0, 200), Some(0));
    }

    #[test]
    fn orient_matches_oracle_with_true_zero() {
        let p = |x: BigRational, y: BigRational| (x, y);
        // True exact zero from checked integers is legitimate.
        let a = p(int_rat(0), int_rat(0));
        let b = p(int_rat(2), int_rat(2));
        let c = p(int_rat(5), int_rat(5));
        let da = dpt(&a);
        assert_eq!(orient(&da, &dpt(&b), &dpt(&c)), Some(0));
        assert_eq!(exact_orient(&a, &b, &c), 0);
        // Clear dyadic signs agree.
        let cases = [
            (
                p(int_rat(0), int_rat(0)),
                p(int_rat(1), int_rat(0)),
                p(int_rat(0), int_rat(1)),
            ),
            (
                p(rat(1, 8), rat(3, 4)),
                p(rat(-5, 2), rat(1, 16)),
                p(rat(7, 4), rat(-9, 8)),
            ),
            (
                p(int_rat(i128::MIN), int_rat(0)),
                p(int_rat(0), int_rat(1)),
                p(int_rat(1), int_rat(0)),
            ),
        ];
        for (index, (a, b, c)) in cases.iter().enumerate() {
            let got = orient(&dpt(&a), &dpt(&b), &dpt(&c));
            if index == 2 {
                // Subtracting MIN needs the unrepresentable +2^127
                // mantissa before the later determinant could cancel it.
                assert_eq!(got, None);
                assert_eq!(exact_orient(a, b, c), -1);
            } else {
                assert_eq!(got, Some(exact_orient(a, b, c)));
            }
        }
        // Cancellation at 2^60 scale stays exact; overflow defers.
        let big = int_rat(1i128 << 60);
        let a = p(int_rat(0), int_rat(0));
        let b = p(big.clone(), big.clone());
        let c = p(big.clone() + int_rat(1), big.clone());
        let got = orient(&dpt(&a), &dpt(&b), &dpt(&c));
        assert_eq!(got, Some(-1));
        assert_eq!(exact_orient(&a, &b, &c), -1);
        // Pure powers stay exact through normalization: 2^100 on both
        // legs gives determinant 2^200, still one mantissa bit.
        let h = BigRational::new(BigInt::from(2).pow(100), 1.into());
        let a = p(int_rat(0), int_rat(0));
        let b = p(h.clone(), int_rat(0));
        let c = p(int_rat(0), h.clone());
        assert_eq!(orient(&dpt(&a), &dpt(&b), &dpt(&c)), Some(1));
        assert_eq!(exact_orient(&a, &b, &c), 1);
        // Repeated points are algebraic zero without any products.
        assert_eq!(orient(&da, &da, &dpt(&c)), Some(0));
        // Non-dyadic input never enters the tier.
        let t = p(rat(1, 3), rat(0, 1));
        assert_eq!(point_from_refs((&t.0, &t.1)), None);
    }

    #[test]
    fn dyadic_transforms_preserve_oracle_signs() {
        // Translation by a dyadic shift plus positive scaling by two keeps
        // dyadic inputs dyadic and preserves exact orientation signs.
        let shift = BigRational::new(BigInt::from(1) << 100, 1.into());
        let t = |p: (&BigRational, &BigRational)| {
            (p.0 * &int_rat(2) + &shift, p.1 * &int_rat(2) + &shift)
        };
        let triples = [
            (
                (int_rat(0), int_rat(0)),
                (int_rat(3), rat(1, 2)),
                (rat(-1, 4), int_rat(7)),
            ),
            (
                (int_rat(1), int_rat(1)),
                (int_rat(2), int_rat(2)),
                (int_rat(3), int_rat(3)),
            ),
        ];
        for (a, b, c) in &triples {
            let (ta, tb, tc) = (t((&a.0, &a.1)), t((&b.0, &b.1)), t((&c.0, &c.1)));
            // Differences cancel the shift exactly, so the tier still
            // decides with the translated oracle sign.
            let shifted = orient(&dpt(&ta), &dpt(&tb), &dpt(&tc));
            assert_eq!(shifted, Some(exact_orient(&ta, &tb, &tc)));
            assert_eq!(exact_orient(&ta, &tb, &tc), exact_orient(a, b, c));
            let got = orient(&dpt(&a), &dpt(&b), &dpt(&c));
            assert_eq!(got, Some(exact_orient(a, b, c)));
        }
        // Small dyadic shifts preserve decidability and signs.
        let small = int_rat(3);
        let t = |p: (&BigRational, &BigRational)| {
            (p.0 * &int_rat(2) + &small, p.1 * &int_rat(2) + &small)
        };
        for (a, b, c) in &triples {
            let (ta, tb, tc) = (t((&a.0, &a.1)), t((&b.0, &b.1)), t((&c.0, &c.1)));
            let got = orient(&dpt(&ta), &dpt(&tb), &dpt(&tc));
            assert_eq!(got, Some(exact_orient(&ta, &tb, &tc)));
            assert_eq!(exact_orient(&ta, &tb, &tc), exact_orient(a, b, c));
        }
    }

    fn rng_next(s: &mut u64) -> u64 {
        *s ^= *s << 13;
        *s ^= *s >> 7;
        *s ^= *s << 17;
        *s
    }

    #[test]
    fn generated_dyadic_predicates_match_oracles() {
        let mut s = 0x243F_6A88_85A3_08D3u64;
        let (mut decided, mut overflowed) = (0usize, 0usize);
        for _ in 0..2000 {
            // Dyadic-only pool: integers, 64ths and 4096ths keep every
            // coordinate inside the tier; huge magnitudes still defer.
            let r = |s: &mut u64| {
                let v = rng_next(s) as i128;
                match rng_next(s) % 4 {
                    0 => int_rat(v),
                    1 => rat(v, 64),
                    2 => rat(v.wrapping_mul(3).wrapping_add(1), 4096),
                    // Huge dyadic magnitudes: images fit, determinants do not.
                    _ => int_rat(v.checked_mul(1i128 << 100).unwrap_or(i128::MAX)),
                }
            };
            let a = (r(&mut s), r(&mut s));
            let b = (r(&mut s), r(&mut s));
            let c = (r(&mut s), r(&mut s));
            let triple = orient_rats((&a.0, &a.1), (&b.0, &b.1), (&c.0, &c.1));
            match triple {
                Some(got) => {
                    decided += 1;
                    assert_eq!(got, exact_orient(&a, &b, &c));
                }
                None => overflowed += 1,
            }
            // Dot and comparison oracles on the same pool.
            let (pa, pb) = (dpt(&a), dpt(&b));
            let d = dot(pa.x, pa.y, pb.x, pb.y);
            let want = (&a.0 * &b.0 + &a.1 * &b.1).is_positive() as i8
                - (&a.0 * &b.0 + &a.1 * &b.1).is_negative() as i8;
            match d {
                Some(d) => assert_eq!(sign(d), want),
                None => overflowed += 1,
            }
            match cmp(pa.x, pb.x) {
                Some(ord) => assert_eq!(ord, (&a.0).cmp(&b.0)),
                None => overflowed += 1,
            }
        }
        assert!(decided > 0 && overflowed > 0);
    }
}
