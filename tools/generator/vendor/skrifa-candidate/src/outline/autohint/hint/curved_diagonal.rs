//! Curved slants: Shamir 2003 §§3.2–3.6 and VTT relative shift/interpolation foundations.
//! Automatic gates and bounded width transfer are project hypotheses.
use super::super::super::{metrics::ScaledAxisMetrics, outline::Outline};
use super::{round, stem_relative_width, Border, Ink, Pair};
use alloc::{vec, vec::Vec};
#[cfg(feature = "libm")]
#[allow(unused_imports)]
use core_maths::*;
use raw::tables::glyf::PointMarker;

#[derive(Clone)]
struct Arc {
    points: Vec<usize>,
    direction: i32,
    axis: usize,
}
#[derive(Default)]
pub(super) struct CurvedPairs {
    arcs: Vec<Arc>,
    pairs: Vec<(usize, usize)>,
}
// Retain each interval's direction even when a neighbor becomes flat. A
// product-only check misses a reversed interval followed by a zero interval.
fn preserves_role(a: i64, b: i64, c: i64, d: i64) -> bool {
    if a * b < 0 {
        return true;
    }
    let sign = (a + b).signum();
    if sign == 0 {
        c * d >= 0
    } else {
        c * sign >= 0 && d * sign >= 0
    }
}

impl Arc {
    fn is_line(&self) -> bool {
        self.points.len() == 2
    }

    fn transverse_cap(&self, outline: &Outline, a: usize, b: usize) -> bool {
        let a = &outline.points[a];
        let b = &outline.points[b];
        if self.axis == 0 {
            a.fy == b.fy && a.y == b.y
        } else {
            a.fx == b.fx && a.x == b.x
        }
    }

    fn sample(
        &self,
        outline: &Outline,
        y: f64,
        fitted: bool,
    ) -> Option<(f64, f64, Vec<(usize, f64)>)> {
        let xy = |p: usize| {
            let p = &outline.points[p];
            let xy = if fitted {
                (p.x as f64, p.y as f64)
            } else {
                (p.ox as f64, p.oy as f64)
            };
            if self.axis == 0 {
                xy
            } else {
                (xy.1, xy.0)
            }
        };
        let direction = (xy(*self.points.last()?).1 - xy(self.points[0]).1).signum();
        if direction == 0.0
            || self
                .points
                .windows(2)
                .any(|p| (xy(p[1]).1 - xy(p[0]).1) * direction < 0.0)
        {
            return None;
        }
        if self.is_line() {
            let a = xy(self.points[0]);
            let b = xy(self.points[1]);
            if y < a.1.min(b.1) || y > a.1.max(b.1) {
                return None;
            }
            let t = (y - a.1) / (b.1 - a.1);
            return Some((
                a.0 + t * (b.0 - a.0),
                (b.0 - a.0) / (b.1 - a.1),
                vec![(self.points[0], 1.0 - t), (self.points[1], t)],
            ));
        }
        let mut start = xy(self.points[0]);
        let mut start_basis = vec![(self.points[0], 1.0)];
        for i in 1..self.points.len() - 1 {
            let c = xy(self.points[i]);
            let end = if i == self.points.len() - 2 {
                xy(*self.points.last()?)
            } else {
                let q = xy(self.points[i + 1]);
                ((c.0 + q.0) * 0.5, (c.1 + q.1) * 0.5)
            };
            let end_basis = if i == self.points.len() - 2 {
                vec![(*self.points.last()?, 1.0)]
            } else {
                vec![(self.points[i], 0.5), (self.points[i + 1], 0.5)]
            };
            if y >= start.1.min(end.1) && y <= start.1.max(end.1) && start.1 != end.1 {
                let (mut low, mut high) = (0.0f64, 1.0f64);
                for _ in 0..40 {
                    let t = (low + high) * 0.5;
                    let v = (1.0 - t).powi(2) * start.1 + 2.0 * t * (1.0 - t) * c.1 + t * t * end.1;
                    if (v < y) == (end.1 > start.1) {
                        low = t
                    } else {
                        high = t
                    }
                }
                let t = (low + high) * 0.5;
                let dx = 2.0 * ((1.0 - t) * (c.0 - start.0) + t * (end.0 - c.0));
                let dy = 2.0 * ((1.0 - t) * (c.1 - start.1) + t * (end.1 - c.1));
                if dy.abs() < 1e-7 {
                    return None;
                }
                let mut basis = Vec::new();
                for (p, w) in &start_basis {
                    basis.push((*p, w * (1.0 - t).powi(2)))
                }
                basis.push((self.points[i], 2.0 * t * (1.0 - t)));
                for (p, w) in &end_basis {
                    basis.push((*p, w * t * t))
                }
                return Some((
                    (1.0 - t).powi(2) * start.0 + 2.0 * t * (1.0 - t) * c.0 + t * t * end.0,
                    dx / dy,
                    basis,
                ));
            }
            start = end;
            start_basis = end_basis;
        }
        None
    }
    fn at(&self, outline: &Outline, y: f64, fitted: bool) -> Option<(f64, f64)> {
        self.sample(outline, y, fitted).map(|(x, s, _)| (x, s))
    }
    fn span(&self, outline: &Outline, fitted: bool) -> (f64, f64) {
        let y = |p: usize| {
            let p = &outline.points[p];
            if self.axis == 0 {
                if fitted {
                    p.y as f64
                } else {
                    p.oy as f64
                }
            } else if fitted {
                p.x as f64
            } else {
                p.ox as f64
            }
        };
        let a = y(self.points[0]);
        let b = y(*self.points.last().unwrap());
        (a.min(b), a.max(b))
    }
}
impl CurvedPairs {
    pub(super) fn new(outline: &Outline, ink: &Ink) -> Self {
        let mut arcs = Vec::new();
        for (a, p) in outline.points.iter().enumerate() {
            if !p.is_on_curve() {
                continue;
            }
            let mut points = vec![a];
            let mut q = p.next();
            while !outline.points[q].is_on_curve() && points.len() <= outline.points.len() {
                points.push(q);
                q = outline.points[q].next();
            }
            points.push(q);
            if (points.len() != 2 && points.len() < 4)
                || points.len() > outline.points.len()
                || points[1..points.len() - 1]
                    .iter()
                    .any(|p| !outline.points[*p].flags.is_off_curve_quad())
            {
                continue;
            }
            let last = &outline.points[q];
            let dx = last.fx - p.fx;
            let dy = last.fy - p.fy;
            let length = (dx as f64).hypot(dy as f64);
            // Angle-independent extent, finite monotone curved slants. The upper
            // extent excludes long bowl arcs; the lower extent excludes ornaments.
            if length < (outline.units_per_em / 8) as f64
                || length > outline.units_per_em as f64 / 3.0
                || dy == 0
                || dx.abs() * 10 < dy.abs()
                || dx.abs() > 10 * dy.abs()
            {
                continue;
            }
            if points.windows(2).any(|ps| {
                let a = &outline.points[ps[0]];
                let b = &outline.points[ps[1]];
                (b.fx - a.fx) * dx < 0 || (b.fy - a.fy) * dy < 0
            }) {
                continue;
            }
            if points.iter().any(|q| {
                let q = &outline.points[*q];
                ((q.fx - p.fx) as f64 * dy as f64 - (q.fy - p.fy) as f64 * dx as f64).abs() / length
                    > outline.units_per_em as f64 / 16.0
            }) {
                continue;
            }
            // Shamir §3.3 distinguishes axial extrema/bows from slanted tangent
            // roles. A quarter-bowl with axial tangents at both ends is not a
            // curved slant. Reuse the existing 14:1 axial-support tolerance.
            let diagonal_tangent = |a: usize, b: usize| {
                let x = (outline.points[b].fx - outline.points[a].fx).abs();
                let y = (outline.points[b].fy - outline.points[a].fy).abs();
                x * 14 > y && y * 14 > x
            };
            if !diagonal_tangent(points[0], points[1])
                && !diagonal_tangent(points[points.len() - 2], *points.last().unwrap())
            {
                continue;
            }
            let axis = usize::from(dx.abs() > dy.abs());
            arcs.push(Arc {
                points,
                direction: if axis == 0 { dy.signum() } else { dx.signum() },
                axis,
            });
        }
        let mut best: Vec<Option<(usize, f64)>> = vec![None; arcs.len()];
        for (i, a) in arcs.iter().enumerate() {
            for (j, b) in arcs.iter().enumerate().skip(i + 1) {
                // Two two-control borders have no interior shape variable once
                // terminal tangents and cap offsets are preserved. This model
                // requires an independent interior control on at least one side,
                // so local width is not fitted only by sliding the terminal cap.
                // This supported-role restriction is a project hypothesis based
                // on Shamir's feature/dependency classification, not a glyph rule.
                // Shamir §§3.3–3.6: match the supported border roles, then
                // resolve their actual degrees of freedom. Project hypothesis:
                // a line may oppose a two-control curve; its free translation
                // supplies a width variable without relaxing the two-curve bow
                // restriction. A constrained hybrid must reject atomically.
                let hybrid = a.is_line() != b.is_line();
                if (a.is_line() && b.is_line())
                    || (!hybrid && a.points.len() < 5 && b.points.len() < 5)
                    || a.axis != b.axis
                    || a.direction == b.direction
                    || a.points.iter().any(|p| b.points.contains(p))
                {
                    continue;
                }
                let (al, ah) = a.span(outline, false);
                let (bl, bh) = b.span(outline, false);
                let low = al.max(bl);
                let high = ah.min(bh);
                if high - low < 0.5 * (ah - al).min(bh - bl) {
                    continue;
                }
                let mut widths = Vec::new();
                let mut valid = true;
                for t in [0.25, 0.5, 0.75] {
                    let y = low + t * (high - low);
                    let Some((ax, sa)) = a.at(outline, y, false) else {
                        valid = false;
                        break;
                    };
                    let Some((bx, sb)) = b.at(outline, y, false) else {
                        valid = false;
                        break;
                    };
                    let angle = (sa.atan() - sb.atan()).abs();
                    let scale = (ah - al) / {
                        let pa = &outline.points[a.points[0]];
                        let pb = &outline.points[*a.points.last().unwrap()];
                        if a.axis == 0 {
                            (pb.fy - pa.fy).abs() as f64
                        } else {
                            (pb.fx - pa.fx).abs() as f64
                        }
                    };
                    valid &= angle < 0.45
                        && (bx - ax).abs() > outline.units_per_em as f64 * scale / 50.0
                        && (bx - ax).abs() < outline.units_per_em as f64 * scale / 5.0;
                    for t in [0.25, 0.5, 0.75] {
                        valid &= if a.axis == 0 {
                            ink.contains(ax + t * (bx - ax), y)
                        } else {
                            ink.contains(y, ax + t * (bx - ax))
                        }
                    }
                    widths.push(bx - ax);
                }
                if !valid || widths.iter().any(|w| w.signum() != widths[1].signum()) {
                    continue;
                }
                let score = widths[1].abs() + (widths[2] - widths[0]).abs();
                for (from, to) in [(i, j), (j, i)] {
                    if best[from].is_none_or(|(_, old)| score < old) {
                        best[from] = Some((to, score))
                    }
                }
            }
        }
        let pairs = best
            .iter()
            .enumerate()
            .filter_map(|(i, b)| {
                let (j, _) = (*b)?;
                (j > i && best[j].map(|(k, _)| k) == Some(i)).then_some((i, j))
            })
            .collect();
        Self { arcs, pairs }
    }
    pub(super) fn len(&self) -> usize {
        self.pairs.len()
    }
    pub(super) fn affected(&self, p: usize) -> bool {
        self.pairs
            .iter()
            .any(|(a, b)| self.arcs[*a].points.contains(&p) || self.arcs[*b].points.contains(&p))
    }
    pub(super) fn apply(
        &self,
        outline: &mut Outline,
        metrics: &[ScaledAxisMetrics; 2],
        hard_x: &[Option<i32>],
        hard_y: &[bool],
        joined: &[[bool; 2]],
        reserved: &mut [bool],
        reserved_y: &mut [bool],
    ) -> u32 {
        let mut visited = vec![false; self.pairs.len()];
        let mut applied = 0;
        for root in 0..self.pairs.len() {
            if visited[root] {
                continue;
            }
            visited[root] = true;
            let mut members = vec![root];
            let axis = self.arcs[self.pairs[root].0].axis;
            let mut next = 0;
            while next < members.len() {
                let (a, b) = self.pairs[members[next]];
                next += 1;
                for j in 0..self.pairs.len() {
                    let (c, d) = self.pairs[j];
                    if !visited[j]
                        && self.arcs[c].axis == axis
                        && [&self.arcs[a], &self.arcs[b]].iter().any(|x| {
                            [&self.arcs[c], &self.arcs[d]].iter().any(|y| {
                                x.points.iter().any(|p| y.points.contains(p))
                                    || ((x.is_line() || y.is_line())
                                        && [x.points[0], *x.points.last().unwrap()].iter().any(
                                            |p| {
                                                [y.points[0], *y.points.last().unwrap()].iter().any(
                                                    |q| {
                                                        (outline.points[*p].next() == *q
                                                            || outline.points[*p].prev() == *q)
                                                            && x.transverse_cap(outline, *p, *q)
                                                    },
                                                )
                                            },
                                        ))
                            })
                        })
                    {
                        visited[j] = true;
                        members.push(j);
                    }
                }
            }
            let mut arcs: Vec<_> = members
                .iter()
                .flat_map(|i| {
                    let (a, b) = self.pairs[*i];
                    [a, b]
                })
                .collect();
            arcs.sort_unstable();
            arcs.dedup();
            let hybrid = arcs.iter().any(|i| self.arcs[*i].is_line());
            let mut points: Vec<_> = arcs
                .iter()
                .flat_map(|i| self.arcs[*i].points.iter().copied())
                .collect();
            points.sort_unstable();
            points.dedup();
            let own = points.clone();
            // Full local ownership: retain endpoint tangents and stationary
            // opposite neighbors, including shared endpoints and straight caps.
            let mut links = Vec::new();
            let mut stationary = Vec::new();
            let mut caps = Vec::new();
            let mut valid = true;
            for arc in arcs.iter().map(|i| &self.arcs[*i]) {
                if arc.is_line() {
                    // VTT Shift and Shamir segment roles: a supported line
                    // translates as a whole in the control axis; its prepared
                    // longitudinal coordinates and tangent remain intact.
                    links.push((arc.points[1], arc.points[0], 1.0));
                }
                for (parent, near, forward) in [
                    (arc.points[0], arc.points[1], false),
                    (
                        *arc.points.last().unwrap(),
                        arc.points[arc.points.len() - 2],
                        true,
                    ),
                ] {
                    if !arc.is_line() {
                        links.push((near, parent, 1.0));
                    }
                    let mut q = if forward {
                        outline.points[parent].next()
                    } else {
                        outline.points[parent].prev()
                    };
                    if own.contains(&q) {
                        if hybrid
                            && outline.points[q].is_on_curve()
                            && arc.transverse_cap(outline, parent, q)
                        {
                            caps.push((parent, q));
                        }
                        if outline.points[q].is_on_curve()
                            && !(hybrid && arc.transverse_cap(outline, parent, q))
                        {
                            links.push((q, parent, 1.0));
                        }
                        continue;
                    }
                    if hybrid && outline.points[q].is_on_curve() {
                        // Shamir Dist distinguishes stroke thickness from
                        // placement. Project hypothesis: a transverse cap keeps
                        // its longitudinal offset, while its thickness follows
                        // the paired width fit. The other coordinate is already
                        // stationary. Unmodeled non-transverse neighbors retain
                        // their full offset; no independently owned point moves.
                        points.push(q);
                        stationary.push(q);
                        if !arc.transverse_cap(outline, parent, q) {
                            links.push((q, parent, 1.0));
                        } else {
                            caps.push((parent, q));
                        }
                        continue;
                    }
                    let mut controls = Vec::new();
                    while !outline.points[q].is_on_curve() && controls.len() < outline.points.len()
                    {
                        controls.push(q);
                        q = if forward {
                            outline.points[q].next()
                        } else {
                            outline.points[q].prev()
                        };
                    }
                    if controls.len() < 2
                        || controls
                            .iter()
                            .any(|p| !outline.points[*p].flags.is_off_curve_quad())
                        || own.contains(&q)
                    {
                        valid = false;
                        continue;
                    }
                    points.extend(&controls);
                    points.push(q);
                    stationary.push(q);
                    for (i, p) in controls.iter().enumerate() {
                        links.push((*p, parent, 1.0 - i as f64 / (controls.len() - 1) as f64));
                    }
                }
            }
            if !valid {
                continue;
            }
            points.sort_unstable();
            points.dedup();
            let free: Vec<_> = points
                .iter()
                .map(|p| {
                    !stationary.contains(p)
                        && !joined[*p][axis]
                        && !reserved[*p]
                        && !reserved_y[*p]
                        && (if axis == 0 {
                            hard_x[*p].is_none() && !reserved[*p]
                        } else {
                            !hard_y[*p] && !reserved_y[*p]
                        })
                })
                .collect();
            let mut rows = Vec::new();
            let mut rhs = Vec::new();
            let tangent_links = links.clone();
            for (child, parent, weight) in links {
                let mut row = vec![0.0; points.len()];
                row[points.binary_search(&child).unwrap()] += 1.0;
                row[points.binary_search(&parent).unwrap()] -= weight;
                rows.push(row);
                rhs.push(0.0);
            }
            for i in &members {
                let (ai, bi) = self.pairs[*i];
                let a = &self.arcs[ai];
                let b = &self.arcs[bi];
                let (al, ah) = a.span(outline, true);
                let (bl, bh) = b.span(outline, true);
                let low = al.max(bl);
                let high = ah.min(bh);
                let (sl, sh) = a.span(outline, false);
                let (tl, th) = b.span(outline, false);
                if high <= low {
                    valid = false;
                    break;
                }
                for t in [0.5] {
                    let y = low + t * (high - low);
                    let sy = sl.max(tl) + t * (sh.min(th) - sl.max(tl));
                    let Some((ax, sa, aw)) = a.sample(outline, y, true) else {
                        valid = false;
                        break;
                    };
                    let Some((bx, sb, bw)) = b.sample(outline, y, true) else {
                        valid = false;
                        break;
                    };
                    let Some((sx, sca)) = a.at(outline, sy, false) else {
                        valid = false;
                        break;
                    };
                    let Some((tx, scb)) = b.at(outline, sy, false) else {
                        valid = false;
                        break;
                    };
                    let border = Border {
                        a: 0,
                        b: 0,
                        slope: (sca + scb) * 0.5,
                        intercept: 0.0,
                        low: 0.0,
                        high: 0.0,
                        direction: 0,
                    };
                    let pair = Pair {
                        left: border,
                        right: border,
                        width: (tx - sx).abs(),
                    };
                    let slope = (sa + sb) * 0.5;
                    // Shamir §§3.3–3.4: characteristic widths belong to feature
                    // classes. VTT separates diagonal CVT selection from X/Y
                    // projection. Project hypothesis: curved and straight
                    // diagonals share the horizontal stem reference; changing
                    // the movement axis does not turn a slant into a bar role.
                    let target = stem_relative_width(&pair, &metrics[0], slope);
                    let mut row = vec![0.0; points.len()];
                    for (p, w) in aw {
                        row[points.binary_search(&p).unwrap()] -= w
                    }
                    for (p, w) in bw {
                        row[points.binary_search(&p).unwrap()] += w
                    }
                    rows.push(row);
                    rhs.push((bx - ax).signum() * (target - (bx - ax).abs()));
                }
            }
            if !valid {
                continue;
            }
            for row in &mut rows {
                for (r, f) in row.iter_mut().zip(&free) {
                    if !f {
                        *r = 0.0
                    }
                }
            }
            let before = |p: usize| {
                if axis == 0 {
                    outline.points[p].x
                } else {
                    outline.points[p].y
                }
            };
            let mut solution = None;
            // Shamir §3.6: global anchors and shape dependencies outrank local
            // width. Project hypothesis: back off the width residual, then bound
            // minimum motion to half a pixel. This is a bounded fit, not a claim
            // that every font-standard target can be attained at every size.
            for attempt in 0..8 {
                let fraction = 1.0 / (1u32 << attempt) as f64;
                let mut active_rows = rows.clone();
                let mut active_rhs: Vec<_> = rhs.iter().map(|r| r * fraction).collect();
                let mut found = None;
                // Preserve monotone control neighborhoods through active bounds.
                // Each violated inequality is replaced by its boundary relation.
                for _ in 0..=points.len() * 2 {
                    let Some(delta) = super::minimum_norm(&active_rows, &active_rhs) else {
                        break;
                    };
                    if delta.iter().any(|d| !d.is_finite()) {
                        break;
                    }
                    let d = |p: usize| {
                        points
                            .binary_search(&p)
                            .ok()
                            .map(|i| delta[i])
                            .unwrap_or(0.0)
                    };
                    let mut bound = None;
                    // A cap may change transverse extent, but its ordered ends
                    // must not cross. This role is independent of the adjacent
                    // curve extrema, which may legitimately change direction.
                    for (lo, hi) in &caps {
                        let old = (before(*hi) - before(*lo)) as f64;
                        if old != 0.0 && (old + d(*hi) - d(*lo)) * old.signum() < -1e-7 {
                            bound = Some((*lo, *hi, old));
                            break;
                        }
                    }
                    for p in &points {
                        if bound.is_some() {
                            break;
                        }
                        let prev = outline.points[*p].prev();
                        let next = outline.points[*p].next();
                        let a = (before(*p) - before(prev)) as f64;
                        let b = (before(next) - before(*p)) as f64;
                        let sign = (a + b).signum();
                        if a * b < 0.0 || sign == 0.0 {
                            continue;
                        }
                        for (lo, hi, old) in [(prev, *p, a), (*p, next, b)] {
                            if (old + d(hi) - d(lo)) * sign < -1e-7 {
                                bound = Some((lo, hi, old));
                                break;
                            }
                        }
                        if bound.is_some() {
                            break;
                        }
                    }
                    let Some((lo, hi, old)) = bound else {
                        found = Some(delta);
                        break;
                    };
                    let mut row = vec![0.0; points.len()];
                    for (p, w) in [(lo, -1.0), (hi, 1.0)] {
                        if let Ok(i) = points.binary_search(&p) {
                            if free[i] {
                                row[i] += w
                            }
                        }
                    }
                    active_rows.push(row);
                    active_rhs.push(-old);
                }
                let Some(delta) = found else { continue };
                let max = delta.iter().map(|d| d.abs()).fold(0.0f64, f64::max);
                let scale = if max > 32.0 { 32.0 / max } else { 1.0 };
                let delta: Vec<_> = delta.iter().map(|d| round(*d * scale)).collect();
                if active_rows.iter().zip(&active_rhs).any(|(row, target)| {
                    (row.iter()
                        .zip(&delta)
                        .map(|(w, d)| w * (*d as f64))
                        .sum::<f64>()
                        - target * scale)
                        .abs()
                        > 0.5 * row.iter().map(|w| w.abs()).sum::<f64>() + 1e-7
                }) {
                    continue;
                }
                // Whole-offset terminal/cap links must remain exact after 26.6
                // rounding. Fractional Ratio dependents retain rounding tolerance.
                if tangent_links.iter().any(|(child, parent, w)| {
                    *w == 1.0
                        && delta[points.binary_search(child).unwrap()]
                            != delta[points.binary_search(parent).unwrap()]
                }) {
                    continue;
                }
                let after = |p: usize| {
                    before(p) + points.binary_search(&p).ok().map(|i| delta[i]).unwrap_or(0)
                };
                if caps.iter().any(|(lo, hi)| {
                    let old = (before(*hi) - before(*lo)) as i64;
                    let new = (after(*hi) - after(*lo)) as i64;
                    old != 0 && new * old.signum() < 0
                }) {
                    continue;
                }
                if points.iter().any(|p| {
                    let prev = outline.points[*p].prev();
                    let next = outline.points[*p].next();
                    let a = (before(*p) - before(prev)) as i64;
                    let b = (before(next) - before(*p)) as i64;
                    let c = (after(*p) - after(prev)) as i64;
                    let d = (after(next) - after(*p)) as i64;
                    !preserves_role(a, b, c, d)
                }) {
                    continue;
                }
                solution = Some(delta);
                break;
            }
            let Some(delta) = solution else { continue };
            applied += members.len() as u32;
            for (p, d) in points.iter().zip(delta) {
                if axis == 0 {
                    outline.points[*p].x += d;
                    outline.points[*p].flags.set_marker(PointMarker::TOUCHED_X);
                    reserved[*p] = true;
                } else {
                    outline.points[*p].y += d;
                    outline.points[*p].flags.set_marker(PointMarker::TOUCHED_Y);
                    reserved_y[*p] = true;
                }
            }
        }
        applied
    }
}

#[cfg(test)]
mod tests {
    use super::super::super::super::topo::Axis;
    use super::super::{tests::outline, Plan};
    use super::*;
    use raw::tables::glyf::PointFlags;

    #[test]
    fn rounded_monotone_roles_reject_reversal_next_to_flat_intervals() {
        assert!(!preserves_role(1, 1, -1, 0));
        assert!(!preserves_role(0, 1, -1, 2));
        assert!(!preserves_role(0, 0, 1, -1));
        assert!(preserves_role(1, 1, 0, 2));
        assert!(preserves_role(-1, 1, -2, 2));
    }

    fn ribbon(rotated: bool, reflected: bool) -> Outline {
        let coords = [
            (0, 0),
            (35, 60),
            (70, 125),
            (115, 200),
            (140, 240),
            (180, 240),
            (155, 200),
            (110, 125),
            (75, 60),
            (40, 0),
        ];
        let coords: Vec<_> = coords
            .iter()
            .map(|(x, y)| {
                let x = if reflected { -x } else { *x };
                if rotated {
                    (*y, x)
                } else {
                    (x, *y)
                }
            })
            .collect();
        let mut glyph = outline(&[&coords]);
        for p in [1, 2, 3, 6, 7, 8] {
            glyph.points[p].flags = PointFlags::off_curve_quad();
        }
        glyph
    }

    fn mixed_ribbon(rotated: bool, reflected: bool) -> Outline {
        let coords: Vec<_> = [
            (0, 0),
            (140, 240),
            (240, 240),
            (170, 130),
            (135, 60),
            (100, 0),
        ]
        .iter()
        .map(|(x, y)| {
            let x = if reflected { -*x } else { *x };
            if rotated {
                (*y, x)
            } else {
                (x, *y)
            }
        })
        .collect();
        let mut glyph = outline(&[&coords]);
        for p in [3, 4] {
            glyph.points[p].flags = PointFlags::off_curve_quad();
        }
        glyph
    }

    #[test]
    fn mixed_borders_retain_reference_class_tangents_and_cap_order_under_transforms() {
        // Shamir Dist/Ratio and VTT diagonal CVT/projection separation ground
        // the mixed-role hypothesis. Deliberately unequal axis references must
        // not change the normal-weight class when the same ribbon is rotated.
        let mut normal_widths = Vec::new();
        for rotated in [false, true] {
            for reflected in [false, true] {
                let mut glyph = mixed_ribbon(rotated, reflected);
                let old = glyph.points.to_vec();
                let plan = Plan::new(&glyph);
                assert_eq!(plan.curves.len(), 1);
                let mut horizontal = ScaledAxisMetrics::default();
                horizontal
                    .widths
                    .push(super::super::super::super::metrics::ScaledWidth {
                        scaled: 96,
                        fitted: 128,
                    });
                let mut vertical = ScaledAxisMetrics::default();
                vertical
                    .widths
                    .push(super::super::super::super::metrics::ScaledWidth {
                        scaled: 32,
                        fitted: 64,
                    });
                let (a, b) = plan.curves.pairs[0];
                let aa = &plan.curves.arcs[a];
                let bb = &plan.curves.arcs[b];
                let (low, high) = aa.span(&glyph, true);
                let mid = (low + high) * 0.5;
                let (x, s) = aa.at(&glyph, mid, false).unwrap();
                let (y, t) = bb.at(&glyph, mid, false).unwrap();
                let expected = (y - x).abs() / (1.0 + ((s + t) * 0.5).powi(2)).sqrt() * 4.0 / 3.0;
                let (counts, _) = plan.apply(
                    &mut glyph,
                    &[horizontal, vertical],
                    &Axis::default(),
                    &[false; 6],
                    true,
                );
                assert_eq!(counts, [1, 1, 0]);
                let at = |points: &[super::super::super::super::outline::Point], p: usize| {
                    if rotated {
                        points[p].y
                    } else {
                        points[p].x
                    }
                };
                for (p, q) in [(0, 1), (2, 3), (4, 5)] {
                    assert_eq!(
                        at(&glyph.points, q) - at(&glyph.points, p),
                        at(&old, q) - at(&old, p)
                    );
                }
                for (p, q) in [(1, 2), (5, 0)] {
                    let before = at(&old, q) - at(&old, p);
                    let after = at(&glyph.points, q) - at(&glyph.points, p);
                    assert!(after * before.signum() >= 0);
                    assert_ne!(after, before);
                }
                for p in 0..6 {
                    assert!((at(&glyph.points, p) - at(&old, p)).abs() <= 32);
                    if rotated {
                        assert_eq!(glyph.points[p].x, old[p].x);
                    } else {
                        assert_eq!(glyph.points[p].y, old[p].y);
                    }
                }
                let (x, s) = aa.at(&glyph, mid, true).unwrap();
                let (y, t) = bb.at(&glyph, mid, true).unwrap();
                let normal = (y - x).abs() / (1.0 + ((s + t) * 0.5).powi(2)).sqrt();
                assert!((normal - expected).abs() < 18.0);
                normal_widths.push(normal);
            }
        }
        assert!(normal_widths
            .iter()
            .all(|w| (w - normal_widths[0]).abs() < 2.0));
    }

    #[test]
    fn mixed_component_with_fixed_border_roles_rejects_atomically() {
        let mut glyph = mixed_ribbon(false, false);
        let old = glyph.points.to_vec();
        let plan = Plan::new(&glyph);
        let hard_x: Vec<_> = glyph.points.iter().map(|p| Some(p.x)).collect();
        let mut reserved = vec![false; 6];
        let mut reserved_y = vec![false; 6];
        assert_eq!(plan.curves.len(), 1);
        assert_eq!(
            plan.curves.apply(
                &mut glyph,
                &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
                &hard_x,
                &[false; 6],
                &[[false; 2]; 6],
                &mut reserved,
                &mut reserved_y,
            ),
            0
        );
        assert_eq!(glyph.points.as_slice(), old.as_slice());
        assert!(reserved.iter().chain(&reserved_y).all(|r| !*r));
    }

    #[test]
    fn curved_slants_fit_in_both_axes_and_reflections_preserving_caps_and_tangents() {
        // Shamir representative-feature widths and VTT dependent point offsets.
        // These geometric invariants, rather than preferred raster ink counts,
        // justify the classifier and fitting model for generic curved ribbons.
        for rotated in [false, true] {
            for reflected in [false, true] {
                let mut glyph = ribbon(rotated, reflected);
                let old = glyph.points.to_vec();
                let plan = Plan::new(&glyph);
                assert_eq!(plan.curves.len(), 1);
                let axis = usize::from(rotated);
                let mut hard_x = vec![None; 10];
                let mut hard_y = vec![false; 10];
                for p in [0, 4, 5, 9] {
                    if rotated {
                        hard_y[p] = true
                    } else {
                        hard_x[p] = Some(glyph.points[p].x)
                    }
                }
                let curve = &plan.curves.arcs[plan.curves.pairs[0].0];
                let (low, high) = curve.span(&glyph, true);
                let mid = (low + high) * 0.5;
                let before = curve.at(&glyph, mid, true).unwrap().0;
                let mut reserved = vec![false; 10];
                let mut reserved_y = vec![false; 10];
                assert_eq!(
                    plan.curves.apply(
                        &mut glyph,
                        &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
                        &hard_x,
                        &hard_y,
                        &[[false; 2]; 10],
                        &mut reserved,
                        &mut reserved_y
                    ),
                    1
                );
                let after = curve.at(&glyph, mid, true).unwrap().0;
                assert!((after - before).abs() > 1.0);
                let coordinate = |p: usize| {
                    if axis == 0 {
                        glyph.points[p].x
                    } else {
                        glyph.points[p].y
                    }
                };
                let original = |p: usize| if axis == 0 { old[p].x } else { old[p].y };
                for p in 0..10 {
                    assert!((coordinate(p) - original(p)).abs() <= 32);
                    if axis == 0 {
                        assert_eq!(glyph.points[p].y, old[p].y)
                    } else {
                        assert_eq!(glyph.points[p].x, old[p].x)
                    }
                }
                for p in [0, 4, 5, 9] {
                    assert_eq!(coordinate(p), original(p));
                }
                for p in 0..10 {
                    let prev = glyph.points[p].prev();
                    let next = glyph.points[p].next();
                    let a = (original(p) - original(prev)) as i64;
                    let b = (original(next) - original(p)) as i64;
                    if a * b >= 0 {
                        let c = (coordinate(p) - coordinate(prev)) as i64;
                        let d = (coordinate(next) - coordinate(p)) as i64;
                        assert!(
                            preserves_role(a, b, c, d),
                            "new control reversal or extremum"
                        );
                    }
                }
                for (p, c) in [(0, 1), (4, 3), (5, 6), (9, 8)] {
                    assert_eq!(coordinate(c) - coordinate(p), original(c) - original(p));
                }
                let prepared = glyph.points.to_vec();
                super::super::super::outline::align_weak_points(
                    &mut glyph,
                    super::super::super::super::topo::Dimension::Horizontal,
                );
                super::super::super::outline::align_weak_points(
                    &mut glyph,
                    super::super::super::super::topo::Dimension::Vertical,
                );
                for p in 0..10 {
                    assert_eq!(glyph.points[p].x, prepared[p].x);
                    assert_eq!(glyph.points[p].y, prepared[p].y);
                }
            }
        }
    }

    #[test]
    fn unowned_geometry_is_rejected_and_protected_features_are_atomic() {
        for invalid in 0..4 {
            let mut glyph = ribbon(false, false);
            match invalid {
                0 => {
                    glyph.points[2].flags = PointFlags::off_curve_cubic();
                }
                1 => {
                    glyph.points[2].fx = -10;
                }
                2 => {
                    for p in &mut glyph.points {
                        p.fx /= 4;
                        p.fy /= 4;
                    }
                }
                _ => {
                    // Two axial tangent roles define a bowl, not a slant.
                    glyph.points[1].fx = 0;
                    glyph.points[3].fy = 240;
                    glyph.points[6].fy = 240;
                    glyph.points[8].fx = 40;
                }
            }
            assert_eq!(Plan::new(&glyph).curves.len(), 0);
        }
        // With two controls on both borders, tangent and cap dependencies leave
        // no independent interior role for this model's curved-width correction.
        let mut two = outline(&[&[
            (0, 0),
            (50, 90),
            (105, 180),
            (140, 240),
            (180, 240),
            (145, 180),
            (90, 90),
            (40, 0),
        ]]);
        for p in [1, 2, 5, 6] {
            two.points[p].flags = PointFlags::off_curve_quad();
        }
        assert_eq!(Plan::new(&two).curves.len(), 0);
        let mut glyph = ribbon(false, false);
        let plan = Plan::new(&glyph);
        let old = glyph.points.to_vec();
        let hard_x: Vec<_> = glyph.points.iter().map(|p| Some(p.x)).collect();
        let mut reserved = vec![false; 10];
        let mut reserved_y = vec![false; 10];
        assert_eq!(
            plan.curves.apply(
                &mut glyph,
                &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
                &hard_x,
                &[false; 10],
                &[[false; 2]; 10],
                &mut reserved,
                &mut reserved_y
            ),
            0
        );
        assert_eq!(glyph.points.as_slice(), old.as_slice());
        assert!(reserved.iter().all(|p| !*p));
        assert!(reserved_y.iter().all(|p| !*p));
    }

    #[test]
    fn curved_sample_basis_is_affine_and_keeps_source_thickness_contrast() {
        let mut glyph = ribbon(false, false);
        let plan = Plan::new(&glyph);
        let arc = &plan.curves.arcs[plan.curves.pairs[0].0];
        let (low, high) = arc.span(&glyph, true);
        let y = (low + high) * 0.5;
        let (x, slope, basis) = arc.sample(&glyph, y, true).unwrap();
        assert!((basis.iter().map(|(_, w)| w).sum::<f64>() - 1.0).abs() < 1e-9);
        for p in &mut glyph.points {
            p.x += 17;
        }
        let (shifted, shifted_slope, _) = arc.sample(&glyph, y, true).unwrap();
        assert!((shifted - x - 17.0).abs() < 1e-9);
        assert!((shifted_slope - slope).abs() < 1e-9);
        // The bounded source-relative fit never establishes optical acceptance.
        // Independently check that a wider source ribbon retains greater normal
        // thickness, rather than assigning both strokes the same pixel target.
        let mut thin = ribbon(false, false);
        let mut thick = ribbon(false, false);
        for p in &mut thick.points[5..] {
            p.fx += 70;
            p.ox += 63;
            p.x += 63;
        }
        let mut widths = Vec::new();
        for g in [&mut thin, &mut thick] {
            let p = Plan::new(g);
            let (counts, _) = p.apply(
                g,
                &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
                &Axis::default(),
                &[true; 10],
                true,
            );
            assert_eq!(counts, [1, 1, 0]);
            let (a, b) = p.curves.pairs[0];
            let aa = &p.curves.arcs[a];
            let bb = &p.curves.arcs[b];
            let (l, h) = aa.span(g, true);
            let (x, s) = aa.at(g, (l + h) * 0.5, true).unwrap();
            let (z, t) = bb.at(g, (l + h) * 0.5, true).unwrap();
            widths.push((z - x).abs() / (1.0 + ((s + t) * 0.5).powi(2)).sqrt());
        }
        assert!(widths[1] > widths[0] + 16.0);
    }
}
