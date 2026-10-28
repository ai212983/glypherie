//! Exact paired polynomial reassembly for coupled fitting.
//!
//! Hersch section 2 gives the Bernstein/derivative identities; Hobby section
//! 6 supplies shared curve variables. Inverting de Casteljau is a project
//! adaptation: both source and upstream must reproduce every original piece
//! at the same parameter. No geometric tolerance merges distinct curves.

use super::{geometry, MAX_COMMANDS};
use crate::probe::FittedCommand;
use num_rational::BigRational as R;
use num_traits::{FromPrimitive, One, ToPrimitive, Zero};
use std::cmp::Ordering;

type P = [R; 2];

#[derive(Clone, Debug, PartialEq, Eq)]
struct Seg(Vec<P>);

impl Seg {
    fn reversed(&self) -> Self {
        Self(self.0.iter().rev().cloned().collect())
    }
    fn cmp(&self, other: &Self) -> Ordering {
        self.0
            .len()
            .cmp(&other.0.len())
            .then_with(|| self.0.cmp(&other.0))
    }
    fn split(&self, t: &R) -> (Self, Self) {
        let a = &self.0[0];
        let b = self.0.last().unwrap();
        if self.0.len() == 2 {
            let m = lerp(a, b, t);
            return (Self(vec![a.clone(), m.clone()]), Self(vec![m, b.clone()]));
        }
        let c = &self.0[1];
        let ca = lerp(a, c, t);
        let cb = lerp(c, b, t);
        let m = lerp(&ca, &cb, t);
        (
            Self(vec![a.clone(), ca, m.clone()]),
            Self(vec![m, cb, b.clone()]),
        )
    }
}

#[derive(Clone)]
enum Tree {
    Leaf(usize),
    Split(R, Box<Tree>, Box<Tree>),
}

pub(super) struct Normalized {
    pub source: Vec<FittedCommand>,
    pub upstream: Vec<FittedCommand>,
    upstream_ring: Vec<Seg>,
    original_upstream: Vec<Seg>,
    trees: Vec<Tree>,
    order: Vec<(usize, bool)>,
}

fn lerp(a: &P, b: &P, t: &R) -> P {
    let m = R::one() - t;
    [&m * &a[0] + t * &b[0], &m * &a[1] + t * &b[1]]
}

fn sub(a: &P, b: &P) -> P {
    [&a[0] - &b[0], &a[1] - &b[1]]
}

fn ratio(u: &P, v: &P) -> Option<R> {
    if u.iter().all(Zero::is_zero) || v.iter().all(Zero::is_zero) {
        return None;
    }
    if &u[0] * &v[1] != &u[1] * &v[0] {
        return None;
    }
    let axis = if !u[0].is_zero() { 0 } else { 1 };
    let total = &u[axis] + &v[axis];
    if total.is_zero() {
        return None;
    }
    let t = &u[axis] / total;
    (t > R::zero() && t < R::one()).then_some(t)
}

fn parent(a: &Seg, b: &Seg, t: &R) -> Option<Seg> {
    if a.0.len() != b.0.len() || a.0.last()? != &b.0[0] {
        return None;
    }
    let start = a.0[0].clone();
    let end = b.0.last()?.clone();
    let result = if a.0.len() == 2 {
        Seg(vec![start, end])
    } else {
        let m = R::one() - t;
        let c = [
            (&a.0[1][0] - &m * &start[0]) / t,
            (&a.0[1][1] - &m * &start[1]) / t,
        ];
        Seg(vec![start, c, end])
    };
    let (left, right) = result.split(t);
    (left == *a && right == *b).then_some(result)
}

fn merge(sa: &Seg, sb: &Seg, ua: &Seg, ub: &Seg) -> Option<(Seg, Seg, R)> {
    if sa.0.len() != sb.0.len() || sa.0.len() != ua.0.len() || sa.0.len() != ub.0.len() {
        return None;
    }
    let t = if sa.0.len() == 2 {
        ratio(&sub(&sa.0[1], &sa.0[0]), &sub(&sb.0[1], &sb.0[0]))?
    } else {
        if sa.0[0] == sa.0[2] || sb.0[0] == sb.0[2] || ua.0[0] == ua.0[2] || ub.0[0] == ub.0[2] {
            return None;
        }
        let t = ratio(&sub(&sa.0[2], &sa.0[1]), &sub(&sb.0[1], &sb.0[0]))?;
        let u = ratio(&sub(&ua.0[2], &ua.0[1]), &sub(&ub.0[1], &ub.0[0]))?;
        if t != u {
            return None;
        }
        t
    };
    Some((parent(sa, sb, &t)?, parent(ua, ub, &t)?, t))
}

fn realize(seg: &Seg, tree: &Tree, out: &mut Vec<(usize, Seg)>) {
    match tree {
        Tree::Leaf(i) => out.push((*i, seg.clone())),
        Tree::Split(t, left, right) => {
            let (a, b) = seg.split(t);
            realize(&a, left, out);
            realize(&b, right, out);
        }
    }
}

fn prove(ring: &[Seg], trees: &[Tree], original: &[Seg]) -> bool {
    let mut parts = Vec::new();
    for (seg, tree) in ring.iter().zip(trees) {
        realize(seg, tree, &mut parts);
    }
    parts.sort_by_key(|p| p.0);
    parts.len() == original.len()
        && parts
            .iter()
            .enumerate()
            .all(|(i, (j, seg))| i == *j && seg == &original[i])
}

fn point(p: [f64; 2]) -> Option<P> {
    if p.iter()
        .any(|v| !v.is_finite() || v.abs() > 32768.0 || f64::from(*v as f32) != *v)
    {
        return None;
    }
    Some([R::from_f64(p[0])?, R::from_f64(p[1])?])
}

fn ring(parsed: &geometry::Parsed) -> Option<Vec<Seg>> {
    if parsed.contours.len() != 1 {
        return None;
    }
    let mut result = Vec::new();
    for seg in &parsed.contours[0] {
        result.push(match *seg {
            geometry::Segment::Line { a, b } => {
                Seg(vec![point(parsed.oncurve[a])?, point(parsed.oncurve[b])?])
            }
            geometry::Segment::Quad { c, a, b } => Seg(vec![
                point(parsed.oncurve[a])?,
                point(parsed.offcurve[c])?,
                point(parsed.oncurve[b])?,
            ]),
            _ => return None,
        });
    }
    // The parser materializes a zero closing edge for a duplicated endpoint.
    if let Some(last) = result.last() {
        if last.0.len() == 2 && last.0[0] == last.0[1] && result.len() > 1 {
            result.pop();
        }
    }
    (!result.is_empty()).then_some(result)
}

fn binary(r: &R) -> Option<f32> {
    let value = r.to_f32()?;
    (value.is_finite() && R::from_f32(value).as_ref() == Some(r)).then_some(value)
}

fn emit(ring: &[Seg]) -> Option<Vec<FittedCommand>> {
    let first = &ring.first()?.0[0];
    let mut out = vec![FittedCommand::MoveTo(
        binary(&first[0])?,
        binary(&first[1])?,
    )];
    for seg in ring {
        let end = seg.0.last()?;
        out.push(if seg.0.len() == 2 {
            FittedCommand::LineTo(binary(&end[0])?, binary(&end[1])?)
        } else {
            FittedCommand::QuadTo(
                binary(&seg.0[1][0])?,
                binary(&seg.0[1][1])?,
                binary(&end[0])?,
                binary(&end[1])?,
            )
        });
    }
    out.push(FittedCommand::Close);
    Some(out)
}

fn strict(commands: &[FittedCommand]) -> bool {
    commands.len() >= 3
        && commands.len() <= MAX_COMMANDS
        && matches!(commands.first(), Some(FittedCommand::MoveTo(..)))
        && matches!(commands.last(), Some(FittedCommand::Close))
        && commands[1..commands.len() - 1]
            .iter()
            .all(|c| matches!(c, FittedCommand::LineTo(..) | FittedCommand::QuadTo(..)))
        && commands.iter().all(|c| match *c {
            FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
                !(x == 0. && x.is_sign_negative() || y == 0. && y.is_sign_negative())
            }
            FittedCommand::QuadTo(a, b, c, d) => [a, b, c, d]
                .iter()
                .all(|v| !(*v == 0. && v.is_sign_negative())),
            _ => true,
        })
}

/// Normalize raw source and the original native fit without rounding either.
pub(super) fn normalize(raw: &geometry::Parsed, preferred: &[FittedCommand]) -> Option<Normalized> {
    if !strict(preferred) {
        return None;
    }
    let up = geometry::parse_commands(preferred).ok()?;
    if raw.contours != up.contours
        || raw.oncurve.len() != up.oncurve.len()
        || raw.offcurve.len() != up.offcurve.len()
    {
        return None;
    }
    let mut src = ring(raw)?;
    let mut fit = ring(&up)?;
    if src.len() != fit.len() {
        return None;
    }
    let original_src = src.clone();
    let original_fit = fit.clone();
    let mut trees: Vec<_> = (0..src.len()).map(Tree::Leaf).collect();
    let mut work = 0usize;
    loop {
        let mut found = None;
        if src.len() < 2 {
            break;
        }
        for i in 0..src.len() {
            work += 1;
            if work > MAX_COMMANDS * 8 {
                return None;
            }
            let j = (i + 1) % src.len();
            if let Some(pair) = merge(&src[i], &src[j], &fit[i], &fit[j]) {
                found = Some((i, j, pair));
                break;
            }
        }
        let Some((i, j, (s, u, t))) = found else {
            break;
        };
        let tree = Tree::Split(t, Box::new(trees[i].clone()), Box::new(trees[j].clone()));
        if j == 0 {
            src = std::iter::once(s)
                .chain(src[1..i].iter().cloned())
                .collect();
            fit = std::iter::once(u)
                .chain(fit[1..i].iter().cloned())
                .collect();
            trees = std::iter::once(tree)
                .chain(trees[1..i].iter().cloned())
                .collect();
        } else {
            src.splice(i..=j, [s]);
            fit.splice(i..=j, [u]);
            trees.splice(i..=j, [tree]);
        }
    }
    if !prove(&src, &trees, &original_src) || !prove(&fit, &trees, &original_fit) {
        return None;
    }
    let n = src.len();
    let mut best: Option<(Vec<Seg>, Vec<(usize, bool)>)> = None;
    for reverse in [false, true] {
        for k in 0..n {
            let order: Vec<_> = (0..n)
                .map(|i| {
                    (
                        if reverse {
                            (k + n - 1 - i) % n
                        } else {
                            (k + i) % n
                        },
                        reverse,
                    )
                })
                .collect();
            let candidate: Vec<_> = order
                .iter()
                .map(|(i, r)| {
                    if *r {
                        src[*i].reversed()
                    } else {
                        src[*i].clone()
                    }
                })
                .collect();
            work += n;
            if work > MAX_COMMANDS * 8 {
                return None;
            }
            let less = best
                .as_ref()
                .map(|(old, _)| {
                    candidate
                        .iter()
                        .zip(old)
                        .map(|(a, b)| a.cmp(b))
                        .find(|o| *o != Ordering::Equal)
                        == Some(Ordering::Less)
                })
                .unwrap_or(true);
            if less {
                best = Some((candidate, order));
            }
        }
    }
    let (source_ring, order) = best?;
    let upstream_ring: Vec<_> = order
        .iter()
        .map(|(i, r)| {
            if *r {
                fit[*i].reversed()
            } else {
                fit[*i].clone()
            }
        })
        .collect();
    Some(Normalized {
        source: emit(&source_ring)?,
        upstream: emit(&upstream_ring)?,
        upstream_ring,
        original_upstream: original_fit,
        trees,
        order,
    })
}

impl Normalized {
    /// Exact original-partition Y ownership and representable expansion.
    pub fn preserves_original_y(&self, candidate: &[FittedCommand]) -> bool {
        let Some(candidate) = geometry::parse_commands(candidate)
            .ok()
            .and_then(|p| ring(&p))
        else {
            return false;
        };
        if candidate.len() != self.order.len()
            || candidate
                .iter()
                .zip(&self.upstream_ring)
                .any(|(a, b)| a.0.len() != b.0.len())
        {
            return false;
        }
        let mut expanded = Vec::new();
        for (seg, (index, reverse)) in candidate.iter().zip(&self.order) {
            let original_direction = if *reverse {
                seg.reversed()
            } else {
                seg.clone()
            };
            realize(&original_direction, &self.trees[*index], &mut expanded);
        }
        expanded.sort_by_key(|x| x.0);
        expanded.len() == self.original_upstream.len()
            && expanded.iter().enumerate().all(|(i, (j, s))| {
                i == *j
                    && s.0.len() == self.original_upstream[i].0.len()
                    && s.0.iter().zip(&self.original_upstream[i].0).all(|(a, b)| {
                        a[1] == b[1]
                            && a.iter()
                                .all(|r| r.to_f64().and_then(R::from_f64).as_ref() == Some(r))
                    })
            })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn eye() -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(0., 0.),
            FittedCommand::QuadTo(4., 6., 8., 0.),
            FittedCommand::QuadTo(4., -6., 0., 0.),
            FittedCommand::Close,
        ]
    }
    #[test]
    fn split_reassembles_and_y_is_owned() {
        let c = eye();
        let raw = geometry::parse_commands(&c).unwrap();
        let a = normalize(&raw, &c).unwrap();
        let split = vec![
            FittedCommand::MoveTo(0., 0.),
            FittedCommand::QuadTo(2., 3., 4., 3.),
            FittedCommand::QuadTo(6., 3., 8., 0.),
            FittedCommand::QuadTo(4., -6., 0., 0.),
            FittedCommand::Close,
        ];
        let b = normalize(&geometry::parse_commands(&split).unwrap(), &split).unwrap();
        assert_eq!(a.source, b.source);
        assert_eq!(a.upstream, b.upstream);
        assert!(b.preserves_original_y(&b.upstream));
        let mut changed = b.upstream.clone();
        if let FittedCommand::MoveTo(_, ref mut y) = changed[0] {
            *y += 1.;
        }
        assert!(!b.preserves_original_y(&changed));
    }
    #[test]
    fn smooth_but_different_curves_are_not_merged() {
        let a = Seg(vec![
            point([0., 0.]).unwrap(),
            point([1., 2.]).unwrap(),
            point([2., 2.]).unwrap(),
        ]);
        let b = Seg(vec![
            point([2., 2.]).unwrap(),
            point([3., 2.]).unwrap(),
            point([4., -1.]).unwrap(),
        ]);
        assert!(merge(&a, &b, &a, &b).is_none());
    }

    #[test]
    fn seam_and_direction_do_not_change_the_canonical_system() {
        let commands = eye();
        let original = ring(&geometry::parse_commands(&commands).unwrap()).unwrap();
        let expected = normalize(&geometry::parse_commands(&commands).unwrap(), &commands).unwrap();
        for reverse in [false, true] {
            let mut parts: Vec<_> = original
                .iter()
                .map(|s| if reverse { s.reversed() } else { s.clone() })
                .collect();
            if reverse {
                parts.reverse();
            }
            for _ in 0..parts.len() {
                parts.rotate_left(1);
                let changed = emit(&parts).unwrap();
                let actual =
                    normalize(&geometry::parse_commands(&changed).unwrap(), &changed).unwrap();
                assert_eq!(actual.source, expected.source);
                assert_eq!(actual.upstream, expected.upstream);
                assert!(actual.preserves_original_y(&actual.upstream));
            }
        }
    }

    #[test]
    fn exact_nonhalf_split_requires_the_same_upstream_polynomial() {
        // Hersch section 2: exact Bernstein subdivision at t=1/3.
        let parent_curve = Seg(vec![
            point([0., 0.]).unwrap(),
            point([9., 18.]).unwrap(),
            point([18., 0.]).unwrap(),
        ]);
        let t = R::new(1.into(), 3.into());
        let (a, b) = parent_curve.split(&t);
        assert_eq!(merge(&a, &b, &a, &b).unwrap().0, parent_curve);
        let mut distorted = b.clone();
        distorted.0[1][0] += R::one();
        assert!(merge(&a, &b, &a, &distorted).is_none());
    }

    #[test]
    fn unsupported_precision_and_command_correspondence_abstain() {
        let commands = eye();
        let mut raw = geometry::parse_commands(&commands).unwrap();
        raw.offcurve[0][0] = 1. / 10.;
        assert!(normalize(&raw, &commands).is_none());
        let raw = geometry::parse_commands(&commands).unwrap();
        let mut changed = commands.clone();
        changed[1] = FittedCommand::LineTo(8., 0.);
        assert!(normalize(&raw, &changed).is_none());
    }
}
