//! Unbounded exact scalar for diagonal geometry.
//!
//! Source architecture: adaptive exact computation with certified filtering
//! ([Shewchuk predicates](https://www.cs.cmu.edu/~quake/robust.html)) and
//! layered exact representation
//! ([CGAL `MP_Float`](https://doc.cgal.org/latest/Number_types/classCGAL_1_1MP__Float.html),
//! [CGAL `Lazy_exact_nt`](https://doc.cgal.org/latest/Number_types/classCGAL_1_1Lazy__exact__nt.html)).
//! Project adaptation: `Small` keeps the checked `i128` dyadic tier
//! ([dyadic](super::dyadic)); overflow promotes to `Big` (`BigInt` mantissa
//! with binary exponent, normalized by bit operations, never by generic
//! rational GCD); genuinely non-dyadic quotients live in `Rat`. No
//! approximation and no finite-size rejection: every operation is exact.

use super::dyadic::Dy;
use num_bigint::BigInt;
use num_rational::BigRational;
use num_traits::{Signed, ToPrimitive, Zero};
use std::cmp::Ordering;
use std::iter::Sum;
use std::ops::{Add, AddAssign, Div, DivAssign, Mul, MulAssign, Neg, Sub, SubAssign};

/// Unbounded exact scalar: checked small dyadic, big dyadic, or rational.
///
/// Canonical form: zero is always `Small` with `m == 0`; every nonzero
/// dyadic has an odd mantissa.
#[derive(Clone, Debug)]
pub(crate) struct Exact(Repr);

#[derive(Clone, Debug)]
enum Repr {
    Small(Dy),
    Big(Box<BigDy>),
    Rat(Box<BigRational>),
}

/// Nonzero `m * 2^e` with odd `m`; zero never lives here.
#[derive(Clone, Debug)]
struct BigDy {
    m: BigInt,
    e: i32,
}

/// Canonical zero.
const ZERO: Dy = Dy { m: 0, e: 0 };

/// Exact `m * 2^e` as a reduced rational. Uses `new_raw` only when the
/// odd-mantissa invariant proves coprimality with the power-of-two
/// denominator; the general path reduces normally.
fn dy_to_rational(m: &BigInt, e: i32) -> BigRational {
    if e >= 0 {
        return BigRational::from_integer(m << (e as u32 as usize));
    }
    let denom = BigInt::from(1) << e.unsigned_abs() as usize;
    if m.bit(0) {
        BigRational::new_raw(m.clone(), denom)
    } else {
        BigRational::new(m.clone(), denom)
    }
}

/// Binary logarithm of a positive denominator, or `None` for non-powers
/// of two and magnitudes past `u32`. Bit identities only, no byte vector.
fn denom_log2(d: &BigInt) -> Option<u32> {
    let tz = d.trailing_zeros()?;
    if d.bits() != tz + 1 {
        return None;
    }
    u32::try_from(tz).ok()
}

/// Canonical dyadic from a big mantissa: strip powers of two by low-bit count,
/// demote to `Small` whenever the reduced value fits.
fn big(m: BigInt, e: i32) -> Exact {
    if m.is_zero() {
        return Exact::from_small(ZERO);
    }
    // Magnitude trailing zeros: exact halving without any GCD.
    let tz = m.trailing_zeros().unwrap_or(0);
    let e = match i32::try_from(tz).ok().and_then(|t| e.checked_add(t)) {
        Some(e) => e,
        None => return Exact::from_ratio_repr(dy_to_rational(&m, e)),
    };
    let m = m >> tz.min(u64::from(u32::MAX));
    if let Some(s) = m.to_i128() {
        return Exact::from_small(Dy { m: s, e });
    }
    Exact::from_big(BigDy { m, e })
}

/// Canonical dyadic from a small mantissa; exponent overflow past `i32`
/// (only from hand-built extremes) keeps the exact value as a rational.
fn small(m: i128, e: i32) -> Exact {
    if m == 0 {
        return Exact::from_small(ZERO);
    }
    match e.checked_add(m.trailing_zeros() as i32) {
        Some(e) => Exact::from_small(Dy {
            m: m >> m.trailing_zeros(),
            e,
        }),
        None => Exact::from_ratio_repr(dy_to_rational(&BigInt::from(m), e)),
    }
}

impl Exact {
    fn from_small(d: Dy) -> Self {
        Self(Repr::Small(d))
    }
    fn from_big(d: BigDy) -> Self {
        Self(Repr::Big(Box::new(d)))
    }
    fn from_ratio_repr(r: BigRational) -> Self {
        Self(Repr::Rat(Box::new(r)))
    }

    pub(crate) fn integer(n: i128) -> Self {
        small(n, 0)
    }

    /// Exact zero (canonical signed-zero sink).
    pub(crate) fn zero() -> Self {
        Exact::from_small(ZERO)
    }

    /// Exact one.
    #[cfg(test)]
    pub(crate) fn one() -> Self {
        Exact::from_small(Dy { m: 1, e: 0 })
    }

    /// Exact zero test.
    pub(crate) fn is_zero(&self) -> bool {
        match &self.0 {
            Repr::Small(d) => d.m == 0,
            Repr::Big(b) => b.m.is_zero(),
            Repr::Rat(r) => r.is_zero(),
        }
    }

    /// Exact positivity test.
    pub(crate) fn is_positive(&self) -> bool {
        match &self.0 {
            Repr::Small(d) => d.m > 0,
            Repr::Big(b) => b.m.is_positive(),
            Repr::Rat(r) => r.is_positive(),
        }
    }

    /// Exact negativity test.
    pub(crate) fn is_negative(&self) -> bool {
        match &self.0 {
            Repr::Small(d) => d.m < 0,
            Repr::Big(b) => b.m.is_negative(),
            Repr::Rat(r) => r.is_negative(),
        }
    }

    /// Exact absolute value.
    pub(crate) fn abs(&self) -> Self {
        if self.is_negative() {
            -self
        } else {
            self.clone()
        }
    }

    /// Exact value of a finite IEEE-754 input, decoded from raw bits
    /// (signed zeros canonicalize). `None` for NaN and infinities.
    pub(crate) fn from_f64(f: f64) -> Option<Self> {
        if !f.is_finite() {
            return None;
        }
        let bits = f.to_bits();
        if bits & 0x7fff_ffff_ffff_ffff == 0 {
            return Some(Self::zero());
        }
        let exp = ((bits >> 52) & 0x7ff) as i32;
        let frac = bits & ((1u64 << 52) - 1);
        let (m, e) = if exp == 0 {
            (frac, -1074)
        } else {
            (frac | (1u64 << 52), exp - 1075)
        };
        // `m != 0`: normals carry the implicit bit, nonzero subnormals
        // carry fraction bits.
        let tz = m.trailing_zeros();
        let neg = bits >> 63 == 1;
        let m = (m >> tz) as i128;
        small(if neg { -m } else { m }, e + tz as i32).into_some()
    }

    /// Exact value of an integer.
    #[cfg(test)]
    pub(crate) fn from_integer(n: BigInt) -> Self {
        if n.is_zero() {
            return Self::zero();
        }
        let tz = n.trailing_zeros().unwrap_or(0);
        match i32::try_from(tz) {
            Ok(e) => big(n >> tz, e),
            Err(_) => Exact::from_ratio_repr(BigRational::from_integer(n)),
        }
    }

    /// Exact quotient `num / den`, panicking on a zero denominator like
    /// `BigRational::new`. A dyadic result stays on a dyadic tier.
    #[cfg(test)]
    pub(crate) fn new(num: BigInt, den: BigInt) -> Self {
        Self::from_rational(BigRational::new(num, den))
    }

    /// Canonical image of a rational: dyadic values stay on a dyadic
    /// tier, everything else is the reduced rational itself.
    pub(crate) fn from_rational(r: BigRational) -> Self {
        if r.is_zero() {
            return Self::zero();
        }
        let (n, d): (BigInt, BigInt) = r.into();
        if d.is_negative() {
            return Self::from_rational(BigRational::new(-n, -d));
        }
        match denom_log2(&d) {
            Some(k) => match i32::try_from(k).ok().and_then(|k| k.checked_neg()) {
                Some(e) => big(n, e),
                None => Exact::from_ratio_repr(BigRational::new_raw(n, d)),
            },
            None => Exact::from_ratio_repr(BigRational::new_raw(n, d)),
        }
    }

    /// Exact rational value. Dyadic tiers use `new_raw` only under the
    /// proven odd-mantissa invariant.
    pub(crate) fn to_rational(&self) -> BigRational {
        match &self.0 {
            Repr::Small(d) => {
                if d.m == 0 {
                    BigRational::from_integer(BigInt::from(0))
                } else {
                    dy_to_rational(&BigInt::from(d.m), d.e)
                }
            }
            Repr::Big(b) => dy_to_rational(&b.m, b.e),
            Repr::Rat(r) => r.as_ref().clone(),
        }
    }

    /// Nearest `f64`, delegating float-boundary rounding (overflow to
    /// infinity, subnormal edges) to the `num-rational` conversion rather
    /// than scaling a float mantissa by `powi`.
    pub(crate) fn to_f64(&self) -> Option<f64> {
        self.to_rational().to_f64()
    }

    /// Checked-tier image for prepared filter metadata, or `None` for
    /// general-rational storage and oversized dyadics. Out-of-tier values
    /// keep their exact value and use the remaining predicate tiers.
    pub(crate) fn small_dyadic(&self) -> Option<Dy> {
        match &self.0 {
            Repr::Small(d) => Some(*d),
            Repr::Big(b) => Some(Dy {
                m: b.m.to_i128()?,
                e: b.e,
            }),
            Repr::Rat(_) => None,
        }
    }

    /// Helper: wrap a value that is always `Some`.
    fn into_some(self) -> Option<Self> {
        Some(self)
    }
}

/// Lift a canonical small dyadic to its big image.
fn lift(d: &Dy) -> BigDy {
    BigDy {
        m: BigInt::from(d.m),
        e: d.e,
    }
}

/// Exact dyadic sum over big images with an `i64` exponent spread, so a
/// `u32`-wide gap stays exact on 64-bit platforms.
fn add_big(a: &BigDy, b: &BigDy) -> Exact {
    let e = a.e.min(b.e);
    let da = usize::try_from((a.e as i64 - e as i64) as u64).ok();
    let db = usize::try_from((b.e as i64 - e as i64) as u64).ok();
    match (da, db) {
        (Some(da), Some(db)) => big((&a.m << da) + (&b.m << db), e),
        _ => Exact::from_ratio_repr(dy_to_rational(&a.m, a.e) + dy_to_rational(&b.m, b.e)),
    }
}

/// Exact dyadic product; exponent overflow past `i32` keeps the exact
/// value as a rational.
fn mul_big(a: &BigDy, b: &BigDy) -> Exact {
    match a.e.checked_add(b.e) {
        Some(e) => big(&a.m * &b.m, e),
        None => Exact::from_rational(dy_to_rational(&a.m, a.e) * dy_to_rational(&b.m, b.e)),
    }
}

/// Exact dyadic quotient when the odd mantissas divide (then the result
/// is dyadic), otherwise the exact rational. Zero dividend is zero;
/// zero divisors panic like `BigRational` division.
fn div_big(a: &BigDy, b: &BigDy) -> Exact {
    if b.m.is_zero() {
        panic!("exact division by zero");
    }
    if a.m.is_zero() {
        return Exact::zero();
    }
    if (&a.m % &b.m).is_zero() {
        if let Some(e) = a.e.checked_sub(b.e) {
            return big(&a.m / &b.m, e);
        }
    }
    Exact::from_rational(dy_to_rational(&a.m, a.e) / dy_to_rational(&b.m, b.e))
}

/// Shared addition over references; overflow in the checked tier
/// promotes to big integers, non-dyadic input computes on rationals.
fn add_ref(a: &Exact, b: &Exact) -> Exact {
    match (&a.0, &b.0) {
        (Repr::Small(x), Repr::Small(y)) => match super::dyadic::add(*x, *y) {
            Some(d) => Exact::from_small(d),
            None => add_big(&lift(x), &lift(y)),
        },
        (Repr::Small(x), Repr::Big(y)) => add_big(&lift(x), y),
        (Repr::Big(x), Repr::Small(y)) => add_big(x, &lift(y)),
        (Repr::Big(x), Repr::Big(y)) => add_big(x, y),
        _ => Exact::from_rational(a.to_rational() + b.to_rational()),
    }
}

/// Shared negation over a reference.
fn neg_ref(a: &Exact) -> Exact {
    match &a.0 {
        // Canonical mantissas are zero or odd, so small negation cannot
        // overflow (`i128::MIN` is even and unrepresentable here).
        Repr::Small(d) => Exact::from_small(Dy { m: -d.m, e: d.e }),
        Repr::Big(b) => big(-&b.m, b.e),
        Repr::Rat(r) => Exact::from_ratio_repr(-r.as_ref()),
    }
}

/// Shared product over references.
fn mul_ref(a: &Exact, b: &Exact) -> Exact {
    match (&a.0, &b.0) {
        (Repr::Small(x), Repr::Small(y)) => match super::dyadic::mul(*x, *y) {
            Some(d) => Exact::from_small(d),
            None => mul_big(&lift(x), &lift(y)),
        },
        (Repr::Small(x), Repr::Big(y)) => mul_big(&lift(x), y),
        (Repr::Big(x), Repr::Small(y)) => mul_big(x, &lift(y)),
        (Repr::Big(x), Repr::Big(y)) => mul_big(x, y),
        _ => Exact::from_rational(a.to_rational() * b.to_rational()),
    }
}

/// Shared quotient over references.
fn div_ref(a: &Exact, b: &Exact) -> Exact {
    if b.is_zero() {
        panic!("exact division by zero");
    }
    match (&a.0, &b.0) {
        (Repr::Small(x), Repr::Small(y)) => {
            if x.m == 0 {
                return Exact::zero();
            }
            if let Some(e) = x.e.checked_sub(y.e) {
                if x.m.checked_rem(y.m) == Some(0) {
                    if let Some(m) = x.m.checked_div(y.m) {
                        return small(m, e);
                    }
                }
            }
            div_big(&lift(x), &lift(y))
        }
        (Repr::Small(x), Repr::Big(y)) => div_big(&lift(x), y),
        (Repr::Big(x), Repr::Small(y)) => div_big(x, &lift(y)),
        (Repr::Big(x), Repr::Big(y)) => div_big(x, y),
        _ => Exact::from_rational(a.to_rational() / b.to_rational()),
    }
}

impl PartialEq for Exact {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other).is_eq()
    }
}

impl Eq for Exact {}

impl PartialOrd for Exact {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// Compare magnitudes by top exponent before aligning integer bits.
/// Equal top exponents bound alignment by the existing mantissa widths.
fn cmp_small(a: &Dy, b: &Dy) -> Ordering {
    let signs = a.m.signum().cmp(&b.m.signum());
    if signs != Ordering::Equal {
        return signs;
    }
    if a.m == 0 {
        return Ordering::Equal;
    }
    let (a_m, b_m) = (a.m.unsigned_abs(), b.m.unsigned_abs());
    let (a_w, b_w) = (128 - a_m.leading_zeros(), 128 - b_m.leading_zeros());
    let top = (i64::from(a.e) + i64::from(a_w)).cmp(&(i64::from(b.e) + i64::from(b_w)));
    let magnitude = if top != Ordering::Equal {
        top
    } else if a_w < b_w {
        (a_m << (b_w - a_w)).cmp(&b_m)
    } else {
        a_m.cmp(&(b_m << (a_w - b_w)))
    };
    if a.m < 0 {
        magnitude.reverse()
    } else {
        magnitude
    }
}

fn cmp_big(a: &BigDy, b: &BigDy) -> Ordering {
    if a.m.is_negative() != b.m.is_negative() {
        return if a.m.is_negative() {
            Ordering::Less
        } else {
            Ordering::Greater
        };
    }
    if a.m.is_zero() || b.m.is_zero() {
        return a.m.cmp(&b.m);
    }
    let (a_m, b_m) = (a.m.magnitude(), b.m.magnitude());
    let (a_w, b_w) = (a_m.bits(), b_m.bits());
    let top = (i128::from(a.e) + i128::from(a_w)).cmp(&(i128::from(b.e) + i128::from(b_w)));
    let magnitude = if top != Ordering::Equal {
        top
    } else if a_w < b_w {
        (a_m << (b_w - a_w)).cmp(b_m)
    } else {
        a_m.cmp(&(b_m << (a_w - b_w)))
    };
    if a.m.is_negative() {
        magnitude.reverse()
    } else {
        magnitude
    }
}

impl Ord for Exact {
    fn cmp(&self, other: &Self) -> Ordering {
        match (&self.0, &other.0) {
            (Repr::Small(a), Repr::Small(b)) => cmp_small(a, b),
            (Repr::Big(a), Repr::Big(b)) => cmp_big(a, b),
            (Repr::Small(a), Repr::Big(b)) => cmp_big(&lift(a), b),
            (Repr::Big(a), Repr::Small(b)) => cmp_big(a, &lift(b)),
            _ => self.to_rational().cmp(&other.to_rational()),
        }
    }
}

macro_rules! fwd_binop {
    ($tr:ident, $m:ident, $core:ident) => {
        impl $tr<Exact> for Exact {
            type Output = Exact;
            fn $m(self, rhs: Exact) -> Exact {
                $core(&self, &rhs)
            }
        }
        impl<'a> $tr<&'a Exact> for Exact {
            type Output = Exact;
            fn $m(self, rhs: &'a Exact) -> Exact {
                $core(&self, rhs)
            }
        }
        impl<'a> $tr<Exact> for &'a Exact {
            type Output = Exact;
            fn $m(self, rhs: Exact) -> Exact {
                $core(self, &rhs)
            }
        }
        impl<'a, 'b> $tr<&'b Exact> for &'a Exact {
            type Output = Exact;
            fn $m(self, rhs: &'b Exact) -> Exact {
                $core(self, rhs)
            }
        }
    };
}

fwd_binop!(Add, add, add_ref);
fwd_binop!(Mul, mul, mul_ref);
fwd_binop!(Div, div, div_ref);

impl Sub<Exact> for Exact {
    type Output = Exact;
    fn sub(self, rhs: Exact) -> Exact {
        add_ref(&self, &neg_ref(&rhs))
    }
}
impl<'a> Sub<&'a Exact> for Exact {
    type Output = Exact;
    fn sub(self, rhs: &'a Exact) -> Exact {
        add_ref(&self, &neg_ref(rhs))
    }
}
impl<'a> Sub<Exact> for &'a Exact {
    type Output = Exact;
    fn sub(self, rhs: Exact) -> Exact {
        add_ref(self, &neg_ref(&rhs))
    }
}
impl<'a, 'b> Sub<&'b Exact> for &'a Exact {
    type Output = Exact;
    fn sub(self, rhs: &'b Exact) -> Exact {
        add_ref(self, &neg_ref(rhs))
    }
}

impl Neg for Exact {
    type Output = Exact;
    fn neg(self) -> Exact {
        neg_ref(&self)
    }
}

impl<'a> Neg for &'a Exact {
    type Output = Exact;
    fn neg(self) -> Exact {
        neg_ref(self)
    }
}

macro_rules! fwd_assign {
    ($tr:ident, $m:ident, $op:tt) => {
        impl $tr<Exact> for Exact {
            fn $m(&mut self, rhs: Exact) {
                *self = &*self $op &rhs;
            }
        }
        impl<'a> $tr<&'a Exact> for Exact {
            fn $m(&mut self, rhs: &'a Exact) {
                *self = &*self $op rhs;
            }
        }
    };
}

fwd_assign!(AddAssign, add_assign, +);
fwd_assign!(SubAssign, sub_assign, -);
fwd_assign!(MulAssign, mul_assign, *);
fwd_assign!(DivAssign, div_assign, /);

impl Sum<Exact> for Exact {
    fn sum<I: Iterator<Item = Exact>>(iter: I) -> Self {
        iter.fold(Self::zero(), |a, b| a + b)
    }
}

impl<'a> Sum<&'a Exact> for Exact {
    fn sum<I: Iterator<Item = &'a Exact>>(iter: I) -> Self {
        iter.fold(Self::zero(), |a, b| a + b)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use num_traits::FromPrimitive;

    fn rat(n: i128, d: i128) -> BigRational {
        BigRational::new(n.into(), d.into())
    }

    fn big_pow2(e: i32) -> Exact {
        if e >= 0 {
            Exact::from_integer(BigInt::from(1) << (e as usize))
        } else {
            Exact::new(
                BigInt::from(1),
                BigInt::from(1) << e.unsigned_abs() as usize,
            )
        }
    }

    #[test]
    fn from_f64_matches_bits_and_rational_oracle() {
        for f in [
            0.0,
            1.0,
            -1.5,
            0.1,
            f64::MAX,
            f64::MIN_POSITIVE,
            f64::from_bits(1),
            f64::from_bits((1023 - 52) << 52 | 1),
            f64::from_bits(0x8000_0000_0000_0005),
        ] {
            let e = Exact::from_f64(f).expect("finite converts");
            assert_eq!(e.to_rational(), BigRational::from_f64(f).unwrap());
            assert_eq!(e.to_f64().unwrap().to_bits(), f.to_bits());
        }
        for f in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert!(Exact::from_f64(f).is_none());
        }
        // Signed zeros canonicalize to one exact zero.
        let z = Exact::from_f64(-0.0).unwrap();
        assert!(z.is_zero() && !z.is_positive() && !z.is_negative());
        assert!(z.to_rational().is_zero());
        assert_eq!(z.to_f64().unwrap().to_bits(), 0);
        assert_eq!(z, Exact::zero());
    }

    #[test]
    fn integers_and_overflow_promotion_match_oracle() {
        for n in [0i128, 1, -1, 7, i128::MAX, i128::MIN, i128::MIN + 1] {
            let e = Exact::from_integer(BigInt::from(n));
            assert_eq!(e.to_rational(), BigRational::from_integer(n.into()));
        }
        // `i128::MAX * 2` and `i128::MIN - 1` leave the checked tier
        // exactly, without any finite-size rejection.
        let big = Exact::from_integer(BigInt::from(i128::MAX));
        let two = Exact::from_integer(BigInt::from(2));
        assert_eq!(
            (&big * &two).to_rational(),
            BigRational::from_integer(BigInt::from(i128::MAX) * 2)
        );
        let min = Exact::from_integer(BigInt::from(i128::MIN));
        let one = Exact::one();
        assert_eq!(
            (&min - &one).to_rational(),
            BigRational::from_integer(BigInt::from(i128::MIN) - 1)
        );
        // `MIN` normalizes by halving (odd target), never by negating.
        assert_eq!(min.small_dyadic(), Some(Dy { m: -1, e: 127 }));
        assert_eq!(Exact::zero().small_dyadic(), Some(Dy { m: 0, e: 0 }));
        // Huge integers stay exact on the big tier.
        let h = BigInt::from(1) << 200usize;
        assert_eq!(
            Exact::from_integer(h.clone()).to_rational(),
            BigRational::from_integer(h)
        );
    }

    #[test]
    fn dyadic_division_stays_dyadic_non_dyadic_stays_rational() {
        // 6/4 reduces through the constructor to 3/2 on the small tier.
        let e = Exact::new(6.into(), 8.into());
        assert_eq!(e.to_rational(), rat(3, 4));
        assert!(e.small_dyadic().is_some());
        // Exact dyadic quotients never touch rationals: (1/2)/(1/4) = 2.
        let half = Exact::new(1.into(), 2.into());
        let quarter = Exact::new(1.into(), 4.into());
        assert_eq!((&half / &quarter).to_rational(), rat(2, 1));
        // Genuinely non-dyadic quotients are exact rationals.
        let third = Exact::one() / Exact::from_integer(BigInt::from(3));
        assert_eq!(third.to_rational(), BigRational::new(1.into(), 3.into()));
        assert_eq!(third.small_dyadic(), None);
        // Back to dyadic through rational arithmetic: (1/3) * 3 == 1.
        let back = &third * &Exact::from_integer(BigInt::from(3));
        assert_eq!(back.to_rational(), rat(1, 1));
        assert!(back.small_dyadic().is_some());
    }

    #[test]
    fn subnormal_cancellation_and_ordering_match_oracle() {
        // Subnormal inputs decode from bits, never via float scaling.
        let tiny = Exact::from_f64(f64::from_bits(1)).unwrap();
        assert_eq!(
            tiny.to_rational(),
            BigRational::from_f64(f64::from_bits(1)).unwrap()
        );
        assert_eq!(tiny.to_f64().unwrap().to_bits(), 1);
        // Cancellation at 2^60 and past the checked tier at 2^200.
        for shift in [60u32, 200] {
            let h = BigInt::from(1) << shift as usize;
            let a = Exact::from_integer(h.clone() + 1);
            let b = Exact::from_integer(h.clone());
            assert_eq!((&a - &b).to_rational(), rat(1, 1));
            assert_eq!(
                (&a - &b).to_rational(),
                BigRational::from_integer(h.clone() + 1) - BigRational::from_integer(h)
            );
        }
        // Cross-tier ordering equals the rational ordering.
        let pairs = [
            (
                Exact::new(1.into(), 3.into()),
                Exact::new(1.into(), 2.into()),
            ),
            (
                Exact::from_f64(0.5).unwrap(),
                Exact::new(1.into(), 2.into()),
            ),
            (
                Exact::from_integer(BigInt::from(1) << 200usize),
                Exact::one(),
            ),
            (
                Exact::new((-1).into(), 2.into()),
                Exact::new((-1).into(), 3.into()),
            ),
        ];
        for (a, b) in &pairs {
            assert_eq!(a.cmp(b), a.to_rational().cmp(&b.to_rational()));
            assert_eq!(a == b, a.to_rational() == b.to_rational());
        }
        assert!(Exact::from_f64(0.5).unwrap() == Exact::new(1.into(), 2.into()));
        // Signs and absolute values track the oracle.
        let neg = Exact::new((-7).into(), 3.into());
        assert!(neg.is_negative() && !neg.is_positive() && !neg.is_zero());
        assert_eq!(neg.abs().to_rational(), rat(7, 3));
        assert!((-&neg).is_positive());
        assert!(Exact::zero().abs().is_zero());
    }

    #[test]
    fn large_exponents_stay_exact() {
        let big = big_pow2(2000);
        let small = big_pow2(-2000);
        // Pure powers demote to the small tier even at extreme exponents.
        assert_eq!(big.small_dyadic(), Some(Dy { m: 1, e: 2000 }));
        assert_eq!(small.small_dyadic(), Some(Dy { m: 1, e: -2000 }));
        assert_eq!((&big * &small).to_rational(), rat(1, 1));
        assert_eq!(
            (&big + &small).to_rational(),
            BigRational::from_integer(BigInt::from(1) << 2000usize)
                + BigRational::new(1.into(), BigInt::from(1) << 2000usize)
        );
        assert_eq!((&big * &big).to_rational(), big_pow2(4000).to_rational());
        assert_eq!(
            big_pow2(2000).to_f64(),
            BigRational::from_integer(BigInt::from(1) << 2000usize).to_f64()
        );
        // to_f64 delegates boundary rounding to num-rational, never
        // scales a float mantissa by powi.
        assert_eq!(
            (&big + &big).to_f64(),
            (&big.to_rational() + &big.to_rational()).to_f64()
        );
    }

    #[test]
    fn assign_and_sum_match_oracle() {
        let mut a = Exact::from_integer(BigInt::from(5));
        a += Exact::new(1.into(), 3.into());
        assert_eq!(a.to_rational(), rat(5, 1) + rat(1, 3));
        a -= &Exact::one();
        assert_eq!(a.to_rational(), rat(5, 1) + rat(1, 3) - rat(1, 1));
        a *= Exact::from_integer(BigInt::from(6));
        assert_eq!(
            a.to_rational(),
            (rat(5, 1) + rat(1, 3) - rat(1, 1)) * rat(6, 1)
        );
        a /= Exact::new(2.into(), 7.into());
        assert_eq!(
            a.to_rational(),
            (rat(5, 1) + rat(1, 3) - rat(1, 1)) * rat(6, 1) / rat(2, 7)
        );
        let items = [
            Exact::one(),
            Exact::new(1.into(), 3.into()),
            Exact::from_integer(BigInt::from(2)),
        ];
        let s: Exact = items.iter().sum();
        assert_eq!(s.to_rational(), rat(1, 1) + rat(1, 3) + rat(2, 1));
        let owned: Exact = items.into_iter().sum();
        assert_eq!(owned.to_rational(), rat(1, 1) + rat(1, 3) + rat(2, 1));
    }

    fn rng_next(s: &mut u64) -> u64 {
        *s ^= *s << 13;
        *s ^= *s >> 7;
        *s ^= *s << 17;
        *s
    }

    #[test]
    fn generated_sweep_matches_rational_oracle() {
        let mut s = 0x243F_6A88_85A3_08D3u64;
        let mut decided = 0usize;
        for _ in 0..3000 {
            // Mix small integers, dyadic fractions, promoted magnitudes,
            // non-dyadic rationals and float-decoded values on both sides
            // through independent BigRational oracles.
            let mk = |s: &mut u64| -> (Exact, BigRational) {
                let v = rng_next(s) as i64 as i128 % 1_000_003;
                match rng_next(s) % 6 {
                    0 => (
                        Exact::from_integer(BigInt::from(v)),
                        BigRational::from_integer(v.into()),
                    ),
                    1 => {
                        let r = rat(v.wrapping_mul(7).wrapping_add(1), 64);
                        (Exact::from_rational(r.clone()), r)
                    }
                    2 => {
                        let h = BigInt::from(v) + (BigInt::from(1) << 130usize);
                        (Exact::from_integer(h.clone()), BigRational::from_integer(h))
                    }
                    3 => {
                        let r = BigRational::new((v * 3 + 1).into(), 7.into());
                        (Exact::from_rational(r.clone()), r)
                    }
                    4 => {
                        let f = f64::from_bits(rng_next(s) & 0xffef_ffff_ffff_ffff);
                        if !f.is_finite() {
                            return (Exact::zero(), rat(0, 1));
                        }
                        (
                            Exact::from_f64(f).unwrap(),
                            BigRational::from_f64(f).unwrap(),
                        )
                    }
                    _ => {
                        let r = BigRational::new((v + 5).into(), (v * v + 11).into());
                        (Exact::new(r.numer().clone(), r.denom().clone()), r)
                    }
                }
            };
            let (a, ra) = mk(&mut s);
            let (b, rb) = mk(&mut s);
            assert_eq!((&a + &b).to_rational(), &ra + &rb);
            assert_eq!((&a - &b).to_rational(), &ra - &rb);
            assert_eq!((&a * &b).to_rational(), &ra * &rb);
            if !rb.is_zero() {
                assert_eq!((&a / &b).to_rational(), &ra / &rb);
            }
            assert_eq!(a.cmp(&b), ra.cmp(&rb));
            assert_eq!((a == b), ra == rb);
            assert_eq!(a.to_f64().map(f64::to_bits), ra.to_f64().map(f64::to_bits));
            decided += 1;
        }
        assert!(decided > 0);
    }

    #[test]
    fn promoted_negative_ordering_and_signed_denominators_match_oracle() {
        let mut values = vec![rat(0, 1), rat(1, 3), rat(-1, 3)];
        for exponent in [0usize, 60, 127, 130, 200, 1074] {
            for sign in [-1i32, 1] {
                let n: BigInt = (BigInt::from(sign) << exponent) + sign;
                values.push(BigRational::new(n.clone(), 1.into()));
                values.push(BigRational::new(n, BigInt::from(1) << 140usize));
            }
        }
        for a in &values {
            for b in &values {
                let (x, y) = (
                    Exact::from_rational(a.clone()),
                    Exact::from_rational(b.clone()),
                );
                assert_eq!(x.cmp(&y), a.cmp(b));
                assert_eq!((&x - &y).to_rational(), a - b);
            }
        }
        for (n, d) in [(1, -2), (6, -9), (-6, -9)] {
            assert_eq!(
                Exact::from_rational(BigRational::new_raw(n.into(), d.into())).to_rational(),
                rat(n, d)
            );
        }
    }
}
