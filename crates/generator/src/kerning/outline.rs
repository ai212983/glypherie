//! Raw monotonic Bézier geometry and continuous same-row wall-order feasibility.
//!
//! No perceptual filters, coverage threshold or method settings live here.
//! Curves split at derivative extrema; endpoint ranges enclose every x on a
//! shared y interval. Integer feasibility is certified by interval subdivision.
use crate::{fail, probe::FittedCommand, Error};
const MAX_SEGMENTS: usize = 131_072;
// Allocation policies, independent of the geometric/optical calculation.
const MAX_PORTIONS: usize = 131_072;
const MAX_PAIR_INTERVALS: usize = 131_072;
const MAX_VISITS: usize = 2_000_000;
const MAX_TOTAL_VISITS: usize = 100_000_000;
fn finite(value: f64) -> Result<f64, Error> {
    if value.is_finite() && value.abs() < 1e12 {
        Ok(value)
    } else {
        Err(fail("kerning requires bounded finite outline geometry"))
    }
}
type Point = [f64; 2];
#[derive(Clone, Copy, Debug)]
pub(super) struct Bounds {
    pub(super) minx: f64,
    pub(super) miny: f64,
    pub(super) maxx: f64,
    pub(super) maxy: f64,
}
#[derive(Clone, Debug)]
pub(super) struct Portion {
    x: [f64; 4],
    y: [f64; 4],
    ta: f64,
    tb: f64,
    pub(super) a: Point,
    pub(super) b: Point,
}
#[derive(Clone, Debug)]
pub(super) struct Outline {
    pub(super) bounds: Option<Bounds>,
    pub(super) portions: Vec<Portion>,
}

fn coefficients(points: &[Point], axis: usize) -> [f64; 4] {
    let d = points[0][axis];
    let (a, b, c) = match points.len() {
        2 => (0., 0., points[1][axis] - d),
        3 => {
            let c = 2. * (points[1][axis] - d);
            (0., points[2][axis] - d - c, c)
        }
        4 => {
            let c = 3. * (points[1][axis] - d);
            let b = 3. * (points[2][axis] - points[1][axis]) - c;
            (points[3][axis] - d - c - b, b, c)
        }
        _ => unreachable!(),
    };
    [a, b, c, d]
}

fn roots(points: &[Point], axis: usize) -> Vec<f64> {
    let differences: Vec<_> = points.windows(2).map(|p| p[1][axis] - p[0][axis]).collect();
    if differences.len() == 1 {
        return vec![];
    }
    let scale = differences.iter().map(|v| v.abs()).fold(0., f64::max);
    if scale == 0. {
        return vec![];
    }
    let c = differences[0] / scale;
    let last = differences[differences.len() - 1] / scale;
    let values = if differences.len() == 2 {
        let a = last - c;
        if a == 0. {
            vec![]
        } else {
            vec![-c / a]
        }
    } else {
        let middle = differences[1] / scale;
        let b = 2. * (middle - c);
        let a = c - 2. * middle + last;
        if a == 0. {
            if b == 0. {
                vec![]
            } else {
                vec![-c / b]
            }
        } else {
            let discriminant = b * b - 4. * a * c;
            if discriminant < 0. {
                vec![]
            } else {
                let q = -0.5 * (b + discriminant.sqrt().copysign(b));
                if q == 0. {
                    vec![-b / (2. * a)]
                } else {
                    vec![q / a, c / q]
                }
            }
        }
    };
    values
        .into_iter()
        .filter(|t| t.is_finite() && *t > 0. && *t < 1.)
        .collect()
}

fn evaluate(points: &[Point], t: f64) -> Point {
    if t == 0. {
        return points[0];
    }
    if t == 1. {
        return points[points.len() - 1];
    }
    let mut work = points.to_vec();
    for n in (1..points.len()).rev() {
        for i in 0..n {
            for axis in 0..2 {
                work[i][axis] = (1. - t) * work[i][axis] + t * work[i + 1][axis];
            }
        }
    }
    work[0]
}

fn horner(c: &[f64; 4], t: f64) -> f64 {
    ((c[0] * t + c[1]) * t + c[2]) * t + c[3]
}

impl Portion {
    pub(super) fn at_y(&self, y: f64) -> Result<f64, Error> {
        if y == self.a[1] {
            return Ok(self.a[0]);
        }
        if y == self.b[1] {
            return Ok(self.b[0]);
        }
        if self.y[0] == 0. && self.y[1] == 0. {
            return finite(horner(&self.x, (y - self.y[3]) / self.y[2]));
        }
        let (mut lo, mut hi) = (self.ta, self.tb);
        let increasing = self.b[1] > self.a[1];
        for _ in 0..1100 {
            let t = lo + (hi - lo) / 2.;
            if t == lo || t == hi {
                return finite(horner(&self.x, t));
            }
            let value = horner(&self.y, t);
            if value == y {
                return finite(horner(&self.x, t));
            }
            if (value < y) == increasing {
                lo = t;
            } else {
                hi = t;
            }
        }
        Err(fail("Hu/Hersch root work limit exceeded"))
    }

    pub(super) fn y_range(&self) -> (f64, f64) {
        (self.a[1].min(self.b[1]), self.a[1].max(self.b[1]))
    }
}

impl Outline {
    pub(super) fn new(commands: &[FittedCommand]) -> Result<Self, Error> {
        if commands.len() > MAX_SEGMENTS {
            return Err(fail("Hu/Hersch command limit exceeded"));
        }
        let mut current = None;
        let mut start = None;
        let mut segments: Vec<Vec<Point>> = vec![];
        let point = |x: f32, y: f32| -> Result<Point, Error> {
            Ok([finite(f64::from(x))?, finite(f64::from(y))?])
        };
        for command in commands {
            match *command {
                FittedCommand::MoveTo(x, y) => {
                    current = Some(point(x, y)?);
                    start = current;
                }
                FittedCommand::Close => {
                    let a = current.ok_or_else(|| fail("Hu/Hersch close without contour"))?;
                    let b = start.ok_or_else(|| fail("Hu/Hersch close without start"))?;
                    if a != b {
                        segments.push(vec![a, b]);
                    }
                    current = Some(b);
                }
                FittedCommand::LineTo(x, y) => {
                    let a = current.ok_or_else(|| fail("Hu/Hersch segment without contour"))?;
                    let b = point(x, y)?;
                    segments.push(vec![a, b]);
                    current = Some(b);
                }
                FittedCommand::QuadTo(x1, y1, x, y) => {
                    let a = current.ok_or_else(|| fail("Hu/Hersch segment without contour"))?;
                    let b = point(x, y)?;
                    segments.push(vec![a, point(x1, y1)?, b]);
                    current = Some(b);
                }
                FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                    let a = current.ok_or_else(|| fail("Hu/Hersch segment without contour"))?;
                    let b = point(x, y)?;
                    segments.push(vec![a, point(x1, y1)?, point(x2, y2)?, b]);
                    current = Some(b);
                }
            }
        }
        let mut vertices = vec![];
        let mut portions = vec![];
        for points in segments {
            let mut ts = vec![0., 1.];
            ts.extend(roots(&points, 0));
            ts.extend(roots(&points, 1));
            ts.sort_by(f64::total_cmp);
            ts.dedup();
            let evaluated: Vec<_> = ts.iter().map(|t| evaluate(&points, *t)).collect();
            vertices.extend(evaluated.iter().copied());
            let x = coefficients(&points, 0);
            let y = coefficients(&points, 1);
            for i in 0..ts.len() - 1 {
                if portions.len() >= MAX_PORTIONS {
                    return Err(fail("kerning outline portion allocation limit exceeded"));
                }
                portions.push(Portion {
                    x,
                    y,
                    ta: ts[i],
                    tb: ts[i + 1],
                    a: evaluated[i],
                    b: evaluated[i + 1],
                });
            }
        }
        let bounds = vertices.first().map(|p| {
            vertices.iter().fold(
                Bounds {
                    minx: p[0],
                    miny: p[1],
                    maxx: p[0],
                    maxy: p[1],
                },
                |b, p| Bounds {
                    minx: b.minx.min(p[0]),
                    miny: b.miny.min(p[1]),
                    maxx: b.maxx.max(p[0]),
                    maxy: b.maxy.max(p[1]),
                },
            )
        });
        Ok(Self { bounds, portions })
    }
}

/// A prepared raw outline for the concrete continuous same-row ordering guard.
/// This is feasibility, not a Hu perceptual wall or a coverage approximation.
pub(super) struct OutlineGeometry(pub(super) Outline);
impl OutlineGeometry {
    pub(super) fn new(commands: &[FittedCommand]) -> Result<Self, Error> {
        Ok(Self(Outline::new(commands)?))
    }
    #[cfg(test)]
    pub(super) fn minimum(&self, other: &Self) -> Result<Option<i32>, Error> {
        self.minimum_with_budget(other, &mut 0)
    }

    pub(super) fn minimum_with_budget(
        &self,
        other: &Self,
        total: &mut usize,
    ) -> Result<Option<i32>, Error> {
        let mut visits = 0;
        let mut maximum = None::<i32>;
        let mut intervals = vec![];
        for a in &self.0.portions {
            for b in &other.0.portions {
                *total = total
                    .checked_add(1)
                    .ok_or_else(|| fail("geometric kerning feasibility work limit"))?;
                if *total > MAX_TOTAL_VISITS {
                    return Err(fail("geometric kerning feasibility work limit exceeded"));
                }
                let (amin, amax) = a.y_range();
                let (bmin, bmax) = b.y_range();
                let lo = amin.max(bmin);
                let hi = amax.min(bmax);
                if lo > hi {
                    continue;
                }
                let witness = ceil_integer(difference_at(a, b, lo)?.max(difference_at(a, b, hi)?))?;
                maximum = Some(maximum.map_or(witness, |v| v.max(witness)));
                let (_, right) = range_at(a, lo, hi)?;
                let (left, _) = range_at(b, lo, hi)?;
                if intervals.len() >= MAX_PAIR_INTERVALS {
                    return Err(fail("geometric kerning interval allocation limit exceeded"));
                }
                intervals.push((ceil_integer(right - left)?, a, b, lo, hi));
            }
        }
        let Some(mut maximum) = maximum else {
            return Ok(None);
        };
        // A witness belongs to the complete glyph pair, not a single curve
        // fragment. Fragments whose upper enclosure cannot exceed it need no
        // further certification. Without this pruning, identical interior
        // contours can consume exponential work despite an exterior wall
        // already fixing the required origin.
        intervals.sort_by_key(|(upper, _, _, _, _)| std::cmp::Reverse(*upper));
        for (upper, a, b, lo, hi) in intervals {
            if upper <= maximum {
                continue;
            }
            certified_maximum(a, b, lo, hi, 0, &mut visits, total, &mut maximum)?;
        }
        Ok(Some(maximum))
    }
}

#[cfg(test)]
fn outline_minimum(a: &[FittedCommand], b: &[FittedCommand]) -> Result<Option<i32>, Error> {
    OutlineGeometry::new(a)?.minimum(&OutlineGeometry::new(b)?)
}

fn ceil_integer(value: f64) -> Result<i32, Error> {
    if !value.is_finite() || value.abs() > f64::from(i32::MAX / 64) {
        return Err(fail("geometric kerning feasibility exceeds layout range"));
    }
    Ok(value.ceil() as i32)
}

fn range_at(portion: &Portion, lo: f64, hi: f64) -> Result<(f64, f64), Error> {
    if portion.a[1] == portion.b[1] {
        return Ok((
            portion.a[0].min(portion.b[0]),
            portion.a[0].max(portion.b[0]),
        ));
    }
    let a = portion.at_y(lo)?;
    let b = portion.at_y(hi)?;
    Ok((a.min(b), a.max(b)))
}

fn difference_at(a: &Portion, b: &Portion, y: f64) -> Result<f64, Error> {
    let (_, right) = range_at(a, y, y)?;
    let (left, _) = range_at(b, y, y)?;
    Ok(right - left)
}

fn common_linear_y_maximum(a: &Portion, b: &Portion, lo: f64, hi: f64) -> Option<f64> {
    if a.y != b.y || a.y[0] != 0. || a.y[1] != 0. || a.y[2] == 0. {
        return None;
    }
    // With the same linear y parameter, the wall difference is itself a
    // cubic polynomial. Its derivative roots give an analytic certificate,
    // including an exact integer interior tangent where independent x
    // interval enclosures would otherwise converge forever from above.
    let coefficients = [
        a.x[0] - b.x[0],
        a.x[1] - b.x[1],
        a.x[2] - b.x[2],
        a.x[3] - b.x[3],
    ];
    let ta = (lo - a.y[3]) / a.y[2];
    let tb = (hi - a.y[3]) / a.y[2];
    let tlo = ta.min(tb);
    let thi = ta.max(tb);
    let mut ts = vec![tlo, thi];
    let aa = 3. * coefficients[0];
    let bb = 2. * coefficients[1];
    let cc = coefficients[2];
    if aa == 0. {
        if bb != 0. {
            ts.push(-cc / bb);
        }
    } else {
        let discriminant = bb * bb - 4. * aa * cc;
        if discriminant >= 0. {
            let q = -0.5 * (bb + discriminant.sqrt().copysign(bb));
            if q == 0. {
                ts.push(-bb / (2. * aa));
            } else {
                ts.extend([q / aa, cc / q]);
            }
        }
    }
    Some(
        ts.into_iter()
            .filter(|t| *t >= tlo && *t <= thi)
            .map(|t| horner(&coefficients, t))
            .fold(f64::NEG_INFINITY, f64::max),
    )
}

fn certified_maximum(
    a: &Portion,
    b: &Portion,
    lo: f64,
    hi: f64,
    depth: u8,
    visits: &mut usize,
    total: &mut usize,
    known: &mut i32,
) -> Result<i32, Error> {
    *visits += 1;
    *total = total
        .checked_add(1)
        .ok_or_else(|| fail("geometric kerning feasibility work limit"))?;
    if *visits > MAX_VISITS || *total > MAX_TOTAL_VISITS {
        return Err(fail("geometric kerning feasibility work limit exceeded"));
    }
    let endpoint = difference_at(a, b, lo)?.max(difference_at(a, b, hi)?);
    *known = (*known).max(ceil_integer(endpoint)?);
    if let Some(maximum) = common_linear_y_maximum(a, b, lo, hi) {
        *known = (*known).max(ceil_integer(maximum)?);
        return Ok(*known);
    }
    // Linear x(y), a constant x wall, or opposite monotonic directions make
    // the difference itself monotonic. Exact translated parameterizations
    // have a constant difference. These cases include coincident/slanted
    // straight strokes and integer tangencies at their endpoints.
    let linear = |p: &Portion| p.x[0] == 0. && p.x[1] == 0. && p.y[0] == 0. && p.y[1] == 0.;
    let constant = |p: &Portion| p.x[0] == 0. && p.x[1] == 0. && p.x[2] == 0.;
    let same_shape = a.y == b.y && a.x[..3] == b.x[..3] && a.ta == b.ta && a.tb == b.tb;
    let ra = range_at(a, lo, hi)?;
    let rb = range_at(b, lo, hi)?;
    let a_up = a.at_y(lo)? <= a.at_y(hi)?;
    let b_up = b.at_y(lo)? <= b.at_y(hi)?;
    if same_shape || (linear(a) && linear(b)) || constant(a) || constant(b) || a_up != b_up {
        return Ok(*known);
    }
    let (_, right) = ra;
    let (left, _) = rb;
    let upper = ceil_integer(right - left)?;
    if upper <= *known {
        return Ok(*known);
    }
    let mid = lo + (hi - lo) / 2.;
    if depth >= 64 || mid == lo || mid == hi {
        // At an exact integer interior tangent the independent endpoint
        // enclosure can remain just above that integer at every finite
        // subdivision. Keep its certified upper bound rather than guessing
        // with an epsilon or accepting a sampled lower bound. This is a
        // conservative Gray feasibility adapter, not an exact minimal-gap
        // solver, and can reserve one extra pixel in that degenerate case.
        *known = (*known).max(upper);
        return Ok(*known);
    }
    Ok(
        certified_maximum(a, b, lo, mid, depth + 1, visits, total, known)?.max(certified_maximum(
            a,
            b,
            mid,
            hi,
            depth + 1,
            visits,
            total,
            known,
        )?),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use FittedCommand as C;

    fn rectangle(left: f32, right: f32, bottom: f32, top: f32) -> Vec<C> {
        vec![
            C::MoveTo(left, bottom),
            C::LineTo(right, bottom),
            C::LineTo(right, top),
            C::LineTo(left, top),
            C::Close,
        ]
    }

    #[test]
    fn analytic_touching_disjoint_and_parallel_walls() {
        let a = rectangle(0., 2., 0., 4.);
        assert_eq!(outline_minimum(&a, &a).unwrap(), Some(2));
        assert_eq!(
            outline_minimum(&a, &rectangle(0., 2., 5., 6.)).unwrap(),
            None
        );
        assert_eq!(
            outline_minimum(&a, &rectangle(3., 5., 0., 4.)).unwrap(),
            Some(-1)
        );
        let slanted = vec![
            C::MoveTo(0., 0.),
            C::LineTo(2., 0.),
            C::LineTo(4., 4.),
            C::LineTo(2., 4.),
            C::Close,
        ];
        assert_eq!(outline_minimum(&slanted, &slanted).unwrap(), Some(2));
        let quadratic = vec![C::MoveTo(0., 0.), C::QuadTo(1., 2., 4., 4.)];
        assert_eq!(outline_minimum(&quadratic, &quadratic).unwrap(), Some(0));
    }

    #[test]
    fn exact_integer_interior_tangent_is_safe_and_bounded() {
        // xA(t)=2+4t, xB(t)=1+4t², y=4t. Their difference
        // 2-(2t-1)² has the exact interior maximum 2 at t=.5.
        // Independent interval extrema may enclose that point just above 2;
        // the conservative policy can reserve 3, but can never accept 1.
        let a = vec![C::MoveTo(2., 0.), C::LineTo(6., 4.)];
        let b = vec![C::MoveTo(1., 0.), C::QuadTo(1., 2., 5., 4.)];
        let ga = OutlineGeometry::new(&a).unwrap();
        let gb = OutlineGeometry::new(&b).unwrap();
        let mut budget = 0;
        let bound = ga.minimum_with_budget(&gb, &mut budget).unwrap().unwrap();
        assert!((2..=3).contains(&bound));
        assert!(
            budget < 10_000,
            "global witness must prune irrelevant fragments"
        );
        for i in 0..=16_384 {
            let t = i as f64 / 16_384.;
            let delta = 2. + 4. * t - (1. + 4. * t * t);
            assert!(delta <= f64::from(bound));
        }
    }

    #[test]
    fn dense_independent_quadratic_oracle_never_crosses_walls() {
        // Linear y(t) gives an independent polynomial oracle for xA-xB:
        // neither production monotonic decomposition nor its bisection is
        // reused by the analytic maximum or dense samples below.
        let mut seed = 0x7a98_5312u32;
        let mut next = || {
            seed = seed.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
            ((seed >> 24) as i32 - 128) as f32 / 16.
        };
        for _ in 0..64 {
            let a = [next(), next(), next()];
            let b = [next(), next(), next()];
            let ca = vec![C::MoveTo(a[0], 0.), C::QuadTo(a[1], 2., a[2], 4.)];
            let cb = vec![C::MoveTo(b[0], 0.), C::QuadTo(b[1], 2., b[2], 4.)];
            let bound = outline_minimum(&ca, &cb).unwrap().unwrap();
            let d = [
                f64::from(a[0] - b[0]),
                f64::from(a[1] - b[1]),
                f64::from(a[2] - b[2]),
            ];
            let q = d[0] - 2. * d[1] + d[2];
            let linear = 2. * (d[1] - d[0]);
            let mut exact = d[0].max(d[2]);
            if q != 0. {
                let t = -linear / (2. * q);
                if t > 0. && t < 1. {
                    exact = exact.max((q * t + linear) * t + d[0]);
                }
            }
            assert!(f64::from(bound) >= exact, "{a:?} {b:?}: {bound} < {exact}");
            assert!(
                f64::from(bound) <= exact.ceil() + 1.,
                "unbounded conservative excess"
            );
            for i in 0..=4096 {
                let t = i as f64 / 4096.;
                let delta = d[0] * (1. - t) * (1. - t) + 2. * d[1] * t * (1. - t) + d[2] * t * t;
                assert!(delta <= f64::from(bound));
            }
        }
    }

    #[test]
    fn interval_and_aggregate_work_allocations_are_explicitly_bounded() {
        let mut commands = vec![];
        for _ in 0..400 {
            commands.extend([C::MoveTo(0., 0.), C::LineTo(1., 1.)]);
        }
        let outline = OutlineGeometry::new(&commands).unwrap();
        let error = outline.minimum(&outline).unwrap_err();
        assert!(error.0.contains("interval allocation limit"));
        let simple = OutlineGeometry::new(&rectangle(0., 2., 0., 4.)).unwrap();
        assert!(simple
            .minimum_with_budget(&simple, &mut MAX_TOTAL_VISITS.clone())
            .is_err());
    }
}
