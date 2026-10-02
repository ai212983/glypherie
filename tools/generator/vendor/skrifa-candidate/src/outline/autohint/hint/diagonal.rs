//! Experimental diagonal-border constraints; foundation and policy in PATCH.md.

use super::super::{metrics::ScaledAxisMetrics, outline::Outline};
use crate::outline::{pen::PathStyle, OutlinePen};
use alloc::{vec, vec::Vec};
#[cfg(feature = "libm")]
#[allow(unused_imports)]
use core_maths::*;
use raw::tables::glyf::PointMarker;

#[path = "curved_diagonal.rs"]
mod curved_diagonal;
use curved_diagonal::CurvedPairs;

type Line = ((f64, f64), (f64, f64));

#[derive(Clone, Copy)]
struct Border {
    a: usize,
    b: usize,
    slope: f64,
    intercept: f64,
    low: f64,
    high: f64,
    direction: i32,
}

struct Pair {
    left: Border,
    right: Border,
    width: f64,
}

struct CurveJoin {
    controls: Vec<usize>,
    stationary: usize,
}

fn grid_width(pair: &Pair, metrics: &ScaledAxisMetrics) -> i32 {
    let slope = (pair.left.slope + pair.right.slope) * 0.5;
    let mut width = pair.width / (1.0 + slope * slope).sqrt();
    if let Some(standard) = metrics
        .widths()
        .iter()
        .min_by_key(|w| round((w.scaled as f64 - width).abs()))
    {
        if (standard.scaled as f64 - width).abs() <= width * 0.1 {
            width = standard.scaled as f64;
        }
    }
    ((round(width) + 32) / 64).max(1) * 64
}

// Shamir 2003 §§3.2/3.4: shared font widths and relative feature dimensions;
// VTT TTGenerator.cpp RectilinearDistanceOfDiagonal/DStroke: project across X
// for steep strokes and Y for shallow ones, then control an integer axial width.
// The specific source/standard ratio transfer is a project hypothesis: preserve
// thick/thin design ratios while following the shared standard's fitted width.
// Quantize only after projection, never reuse a perpendicular integer as an axis distance.
fn stem_relative_width(pair: &Pair, metrics: &ScaledAxisMetrics, fitted_slope: f64) -> f64 {
    let source_slope = (pair.left.slope + pair.right.slope) * 0.5;
    let source_normal = pair.width / (1.0 + source_slope * source_slope).sqrt();
    let normal = metrics
        .widths()
        .iter()
        .filter(|w| w.scaled > 0)
        .min_by_key(|w| round((w.scaled as f64 - source_normal).abs()))
        .map(|standard| {
            // Shamir 2003 §§3.2/3.4 shared font widths: transfer the actual
            // fitted standard from the horizontal width policy (smooth
            // stem_width via ScaledWidth.fitted) instead of reconstructing an
            // integer. Extra-light fitted equals scaled under that same
            // policy, preserving the unit ratio there; dropout control keeps
            // subpixel-visibility responsibility (Hersch 1993 §7). PROJECT
            // HYPOTHESIS: this fitted/scaled transfer, not integer rebuild.
            source_normal * standard.fitted as f64 / standard.scaled as f64
        })
        .unwrap_or(source_normal);
    let dominant = fitted_slope.abs().max(1.0);
    let projected = normal * (1.0 + fitted_slope * fitted_slope).sqrt() / dominant;
    let rounded = ((round(projected) + 32) / 64).max(1) * 64;
    // FreeType/Skrifa smooth horizontal stem_width bounds snapping distortion
    // to less than 1/4 pixel. Applying that geometric guard to diagonal Mono
    // targets is an explicit project hypothesis; it avoids a second coarse
    // rounding step undoing the source/standard thickness ratio.
    let axial = if metrics.width_metrics.is_extra_light {
        projected
    } else if (rounded as f64 - projected).abs() < 16.0 {
        rounded as f64
    } else {
        projected.max(64.0)
    };
    axial * dominant + (1.0 + fitted_slope.abs()).ceil()
}

pub(super) struct Plan {
    pairs: Vec<Pair>,
    curves: CurvedPairs,
    joined: Vec<[bool; 2]>,
}

fn round(value: f64) -> i32 {
    if value >= 0.0 {
        (value + 0.5) as i32
    } else {
        (value - 0.5) as i32
    }
}

impl Plan {
    pub fn new(outline: &Outline) -> Self {
        let mut borders = Vec::new();
        for (a, p) in outline.points.iter().enumerate() {
            let b = p.next();
            let q = &outline.points[b];
            if !p.is_on_curve() || !q.is_on_curve() {
                continue;
            }
            let dx = q.fx - p.fx;
            let dy = q.fy - p.fy;
            // Shamir §3.3 classifies slants by angle and overlapping extent.
            // Project hypothesis: use chord length rather than vertical span
            // for eligibility, so rotation does not discard short diagonals.
            if (dx as i64 * dx as i64 + dy as i64 * dy as i64)
                < (outline.units_per_em as i64 / 8).pow(2)
                || q.oy == p.oy
                || dx.abs() * 10 < dy.abs()
                || dx.abs() > dy.abs() * 2
            {
                continue;
            }
            let slope = (q.ox - p.ox) as f64 / (q.oy - p.oy) as f64;
            borders.push(Border {
                a,
                b,
                slope,
                intercept: p.ox as f64 - slope * p.oy as f64,
                low: p.oy.min(q.oy) as f64,
                high: p.oy.max(q.oy) as f64,
                direction: dy.signum(),
            });
        }
        let mut ink = Ink::default();
        let valid_path = outline.to_path(PathStyle::FreeType, &mut ink).is_ok();
        let mut best: Vec<Option<(usize, f64)>> = vec![None; borders.len()];
        if valid_path {
            for (i, a) in borders.iter().enumerate() {
                for (j, b) in borders.iter().enumerate().skip(i + 1) {
                    if a.direction == b.direction
                        || (a.slope - b.slope).abs() > 0.08 * (1.0 + (a.slope * b.slope).abs())
                        || [a.a, a.b].iter().any(|p| *p == b.a || *p == b.b)
                    {
                        continue;
                    }
                    let low = a.low.max(b.low);
                    let high = a.high.min(b.high);
                    if high - low < 0.5 * (a.high - a.low).min(b.high - b.low) {
                        continue;
                    }
                    let mut widths = [0.0; 3];
                    let mut inside = true;
                    for (k, fraction) in [0.25, 0.5, 0.75].iter().enumerate() {
                        let y = low + fraction * (high - low);
                        let ax = a.slope * y + a.intercept;
                        let bx = b.slope * y + b.intercept;
                        widths[k] = bx - ax;
                        for t in [0.25, 0.5, 0.75] {
                            inside &= ink.contains(ax + t * (bx - ax), y);
                        }
                    }
                    if !inside || widths.iter().any(|w| w.signum() != widths[1].signum()) {
                        continue;
                    }
                    let width = widths[1].abs();
                    let scale = (a.high - a.low)
                        / ((outline.points[a.b].fy - outline.points[a.a].fy).abs() as f64);
                    if width < outline.units_per_em as f64 * scale / 50.0
                        || width > outline.units_per_em as f64 * scale / 5.0
                    {
                        continue;
                    }
                    let score = width + (widths[2] - widths[0]).abs();
                    for (from, to) in [(i, j), (j, i)] {
                        if best[from].is_none_or(|(_, old)| score < old) {
                            best[from] = Some((to, score));
                        }
                    }
                }
            }
        }
        let mut pairs = Vec::new();
        for (i, link) in best.iter().enumerate() {
            let Some((j, _)) = *link else { continue };
            if j <= i || best[j].map(|(k, _)| k) != Some(i) {
                continue;
            }
            let a = borders[i];
            let b = borders[j];
            let y = (a.low.max(b.low) + a.high.min(b.high)) * 0.5;
            let width = (b.slope - a.slope) * y + b.intercept - a.intercept;
            let (left, right) = if width > 0.0 { (a, b) } else { (b, a) };
            pairs.push(Pair {
                left,
                right,
                width: width.abs(),
            });
        }
        let curves = if valid_path {
            CurvedPairs::new(outline, &ink)
        } else {
            CurvedPairs::default()
        };
        let mut joined = vec![[false; 2]; outline.points.len()];
        let affected: Vec<_> = outline
            .contours
            .iter()
            .map(|contour| {
                contour.range().any(|p| curves.affected(p))
                    || pairs.iter().any(|pair| {
                        [pair.left.a, pair.left.b, pair.right.a, pair.right.b]
                            .iter()
                            .any(|p| contour.range().contains(p))
                    })
            })
            .collect();
        let ranges: Vec<_> = ink
            .starts
            .iter()
            .enumerate()
            .map(|(i, start)| *start..ink.starts.get(i + 1).copied().unwrap_or(ink.lines.len()))
            .collect();
        for (a, range_a) in ranges.iter().enumerate() {
            for (b, range_b) in ranges.iter().enumerate().skip(a + 1) {
                if affected[a] && affected[b] {
                    continue;
                }
                if !ink.lines[range_a.clone()].iter().any(|line_a| {
                    ink.lines[range_b.clone()]
                        .iter()
                        .any(|line_b| intersects(*line_a, *line_b))
                }) {
                    continue;
                }
                for (own, other_id, other) in [(a, b, range_b), (b, a, range_a)] {
                    for p in outline.contours[own].range() {
                        let point = &outline.points[p];
                        if !Ink::contains_in(
                            &ink.lines[other.clone()],
                            point.ox as f64,
                            point.oy as f64,
                            true,
                        ) {
                            continue;
                        }
                        let support = outline.contours[other_id]
                            .range()
                            .filter_map(|i| {
                                let a = &outline.points[i];
                                let b = &outline.points[a.next()];
                                if !a.is_on_curve() || !b.is_on_curve() {
                                    return None;
                                }
                                let dx = b.fx - a.fx;
                                let dy = b.fy - a.fy;
                                let dim = if dy.abs() >= outline.units_per_em / 8
                                    && dx.abs() * 14 <= dy.abs()
                                {
                                    0
                                } else if dx.abs() >= outline.units_per_em / 8
                                    && dy.abs() * 14 <= dx.abs()
                                {
                                    1
                                } else {
                                    return None;
                                };
                                let vx = (b.ox - a.ox) as f64;
                                let vy = (b.oy - a.oy) as f64;
                                if vx == 0.0 && vy == 0.0 {
                                    return None;
                                }
                                let px = (point.ox - a.ox) as f64;
                                let py = (point.oy - a.oy) as f64;
                                let t = ((px * vx + py * vy) / (vx * vx + vy * vy)).clamp(0.0, 1.0);
                                Some((dim, (px - t * vx).powi(2) + (py - t * vy).powi(2)))
                            })
                            .min_by(|a, b| a.1.partial_cmp(&b.1).unwrap());
                        if let Some((dim, _)) = support {
                            joined[p][dim] = true;
                        } else {
                            joined[p] = [true; 2];
                        }
                    }
                }
            }
        }
        Self {
            pairs,
            curves,
            joined,
        }
    }

    pub fn len(&self) -> usize {
        self.pairs.len() + self.curves.len()
    }

    fn curve_join(
        &self,
        outline: &Outline,
        p: usize,
        diagonal_points: &[bool],
        hard_x: &[Option<i32>],
        reserved: &[bool],
    ) -> Option<CurveJoin> {
        let point = &outline.points[p];
        let forward = !outline.points[point.next()].is_on_curve();
        if forward && !outline.points[point.prev()].is_on_curve() {
            return None;
        }
        let mut q = if forward { point.next() } else { point.prev() };
        let mut controls = Vec::new();
        while !outline.points[q].is_on_curve() {
            if q == p || controls.len() >= outline.points.len() {
                return None;
            }
            if hard_x[q].is_some() || self.joined[q][0] || reserved[q] {
                return None;
            }
            controls.push(q);
            q = if forward {
                outline.points[q].next()
            } else {
                outline.points[q].prev()
            };
        }
        // One quadratic control belongs to both endpoint tangents. Moving it
        // cannot preserve those tangents with a stationary opposite endpoint.
        // Keep such joins, mixed curves, and diagonally owned opposite ends fixed.
        let quadratic = controls.len() >= 2
            && controls
                .iter()
                .all(|i| outline.points[*i].flags.is_off_curve_quad());
        let cubic = controls.len() == 2
            && controls
                .iter()
                .all(|i| outline.points[*i].flags.is_off_curve_cubic());
        let far_side = if forward {
            outline.points[q].next()
        } else {
            outline.points[q].prev()
        };
        // A curve-to-curve junction is not a terminal join: its other curve has
        // independent shape dependencies that this model cannot own.
        if (!quadratic && !cubic)
            || diagonal_points[q]
            || !outline.points[far_side].is_on_curve()
            || hard_x[q].is_some()
            || self.joined[q][0]
            || reserved[q]
        {
            return None;
        }
        Some(CurveJoin {
            controls,
            stationary: q,
        })
    }

    pub fn apply(
        &self,
        outline: &mut Outline,
        metrics: &[ScaledAxisMetrics; 2],
        axis: &super::super::topo::Axis,
        hard_y: &[bool],
        stem_relative: bool,
    ) -> ([u32; 3], Vec<bool>) {
        if stem_relative {
            // Shamir §§3.2–3.3: dependents preserve prepared parent offsets.
            // Skrifa's align_weak_points completes those prepared coordinates.
            // Project hypothesis: finish upstream IUP before fitting straight
            // components too, so terminal shifts do not freeze raw controls.
            super::outline::align_weak_points(outline, super::super::topo::Dimension::Horizontal);
            super::outline::align_weak_points(outline, super::super::topo::Dimension::Vertical);
        }
        let mut hard_x = vec![None; outline.points.len()];
        for segment in &axis.segments {
            let first = segment.first();
            let last = segment.last();
            if (outline.points[first].fy - outline.points[last].fy).abs() < outline.units_per_em / 8
            {
                continue;
            }
            let Some(edge) = segment.edge(axis.edges.as_slice()) else {
                continue;
            };
            let mut p = first;
            loop {
                hard_x[p] = Some(edge.pos);
                if p == last {
                    break;
                }
                p = outline.points[p].next();
            }
        }
        let endpoints: Vec<_> = self
            .pairs
            .iter()
            .map(|pair| [pair.left.a, pair.left.b, pair.right.a, pair.right.b])
            .collect();
        let mut diagonal_points = vec![false; outline.points.len()];
        for p in endpoints.iter().flatten() {
            diagonal_points[*p] = true;
        }
        let mut visited = vec![false; self.pairs.len()];
        let mut reserved = vec![false; outline.points.len()];
        let mut reserved_y = vec![false; outline.points.len()];
        let mut applied = 0;
        for root in 0..self.pairs.len() {
            if visited[root] {
                continue;
            }
            visited[root] = true;
            let mut members = vec![root];
            let mut next = 0;
            while next < members.len() {
                let i = members[next];
                next += 1;
                for j in 0..self.pairs.len() {
                    if !visited[j] && endpoints[i].iter().any(|p| endpoints[j].contains(p)) {
                        visited[j] = true;
                        members.push(j);
                    }
                }
            }
            let mut points: Vec<_> = members.iter().flat_map(|i| endpoints[*i]).collect();
            points.sort_unstable();
            points.dedup();
            let mut base = Vec::new();
            let mut free = Vec::new();
            for p in &points {
                let point = &outline.points[*p];
                base.push(hard_x[*p].unwrap_or(point.x) as f64);
                base.push(point.y as f64);
                let curve_join = !outline.points[point.prev()].is_on_curve()
                    || !outline.points[point.next()].is_on_curve();
                free.push(hard_x[*p].is_none() && !self.joined[*p][0] && !curve_join);
                free.push(!hard_y[*p] && !self.joined[*p][1] && !curve_join);
            }
            let mut rows = Vec::new();
            let mut full_rows = Vec::new();
            let mut rhs = Vec::new();
            let mut slopes = Vec::new();
            let mut valid = true;
            for i in &members {
                let pair = &self.pairs[*i];
                let grid_width = grid_width(pair, &metrics[0]);
                let mut slope = 0.0;
                for border in [pair.left, pair.right] {
                    let dy = outline.points[border.b].y - outline.points[border.a].y;
                    if dy == 0 {
                        valid = false;
                        continue;
                    }
                    slope += (outline.points[border.b].x - outline.points[border.a].x) as f64
                        / dy as f64
                        * 0.5;
                }
                slopes.push(slope);
                let mut target = if stem_relative {
                    stem_relative_width(pair, &metrics[0], slope)
                } else {
                    grid_width as f64 * slope.abs().max(1.0) + (1.0 + slope.abs()).ceil()
                };
                // Newly covered short slants receive a width floor: preserve
                // prepared thickness if it already exceeds the transferred target.
                // This conservative extension is a project hypothesis, not a
                // source prescription to thin every newly detected feature.
                if [pair.left, pair.right].iter().any(|border| {
                    (outline.points[border.b].fy - outline.points[border.a].fy).abs()
                        < outline.units_per_em / 8
                }) {
                    let y = (pair.left.low.max(pair.right.low)
                        + pair.left.high.min(pair.right.high))
                        * 0.5;
                    let at = |border: Border| {
                        let a = &outline.points[border.a];
                        let b = &outline.points[border.b];
                        a.x as f64 + (b.x - a.x) as f64 * (y - a.y as f64) / (b.y - a.y) as f64
                    };
                    target = target.max((at(pair.right) - at(pair.left)).abs());
                }
                for (a, b, distance) in [
                    (pair.left.a, pair.left.b, 0.0),
                    (pair.right.a, pair.right.b, 0.0),
                    (pair.left.a, pair.right.a, target),
                ] {
                    let ai = points.binary_search(&a).unwrap() * 2;
                    let bi = points.binary_search(&b).unwrap() * 2;
                    let mut row = vec![0.0; base.len()];
                    row[ai] -= 1.0;
                    row[ai + 1] += slope;
                    row[bi] += 1.0;
                    row[bi + 1] -= slope;
                    let residual =
                        distance - row.iter().zip(&base).map(|(a, b)| a * b).sum::<f64>();
                    full_rows.push(row.clone());
                    for (coefficient, is_free) in row.iter_mut().zip(&free) {
                        if !is_free {
                            *coefficient = 0.0;
                        }
                    }
                    rows.push(row);
                    rhs.push(residual);
                }
            }
            if !valid || slopes.iter().any(|slope| !slope.is_finite()) {
                continue;
            }
            let mut curve_joins = Vec::new();
            let delta = if let Some(delta) = minimum_norm(&rows, &rhs) {
                delta
            } else {
                // VTT XSHIFT supplies parent-relative control displacement;
                // Shamir §§3.2/3.3 supplies dependent point/segment roles. The
                // following is a project hypothesis, not their complete model:
                // retry an inconsistent system with supported terminal curves
                // dependent in X, while retaining their endpoint Y coordinates.
                // Successful existing fits use the original ownership unchanged.
                for (i, p) in points.iter().enumerate() {
                    if hard_x[*p].is_none() && !self.joined[*p][0] {
                        if let Some(join) =
                            self.curve_join(outline, *p, &diagonal_points, &hard_x, &reserved)
                        {
                            free[i * 2] = true;
                            curve_joins.push((i, join));
                        }
                    }
                }
                if curve_joins.is_empty() {
                    continue;
                }
                for (row, original) in rows.iter_mut().zip(&full_rows) {
                    for ((coefficient, original), is_free) in
                        row.iter_mut().zip(original).zip(&free)
                    {
                        *coefficient = if *is_free { *original } else { 0.0 };
                    }
                }
                let Some(delta) = minimum_norm(&rows, &rhs) else {
                    continue;
                };
                delta
            };
            let too_far = members.iter().zip(&slopes).any(|(i, slope)| {
                let norm = (1.0 + slope * slope).sqrt();
                [self.pairs[*i].left, self.pairs[*i].right]
                    .iter()
                    .any(|border| {
                        [border.a, border.b].iter().any(|p| {
                            let index = points.binary_search(p).unwrap() * 2;
                            let dx = delta[index];
                            let dy = delta[index + 1];
                            (dx - slope * dy).abs() > 32.0 * norm
                                || (slope * dx + dy).abs()
                                    > (border.high - border.low) * norm * norm / 8.0
                        })
                    })
            });
            if too_far {
                continue;
            }
            let fitted: Vec<_> = base.iter().zip(&delta).map(|(b, d)| round(b + d)).collect();
            if rows.iter().zip(&rhs).any(|(row, value)| {
                let residual = row
                    .iter()
                    .enumerate()
                    .map(|(i, a)| a * (fitted[i] as f64 - base[i]))
                    .sum::<f64>()
                    - value;
                residual.abs() > row.iter().map(|a| a.abs()).sum::<f64>() * 0.5 + 1e-7
            }) {
                continue;
            }
            // Preserve the X components of both terminal tangents: the
            // nearest control follows the moved endpoint; the far control and
            // opposite on-curve point keep their prepared X. Interpolating any
            // interior quadratic controls by spline order is an explicit Ratio
            // hypothesis; it preserves continuity at implied on-curve midpoints.
            // Reserve X only, allowing the upstream Y trajectory to finish.
            let mut updates = Vec::new();
            let mut compatible = true;
            for (i, join) in &curve_joins {
                let dx = fitted[i * 2] as f64 - base[i * 2];
                if dx == 0.0 {
                    continue;
                }
                // Apply the existing half-pixel movement budget to the dependent
                // control axis as well; do not amplify motion through the curve.
                compatible &= dx.abs() <= 32.0;
                updates.push((join.stationary, outline.points[join.stationary].x));
                for (j, p) in join.controls.iter().enumerate() {
                    compatible &= !reserved[*p];
                    let weight = 1.0 - j as f64 / (join.controls.len() - 1) as f64;
                    updates.push((*p, outline.points[*p].x + round(dx * weight)));
                }
            }
            updates.sort_unstable();
            compatible &= updates
                .windows(2)
                .all(|pair| pair[0].0 != pair[1].0 || pair[0].1 == pair[1].1);
            if !compatible {
                continue;
            }
            // Coordinates and ownership are committed only after every guard,
            // including dependent-control conflicts, has accepted the component.
            applied += members.len() as u32;
            for (i, p) in points.iter().enumerate() {
                outline.points[*p].x = fitted[i * 2];
                outline.points[*p].y = fitted[i * 2 + 1];
                outline.points[*p]
                    .flags
                    .set_marker(PointMarker::TOUCHED_X | PointMarker::TOUCHED_Y);
                reserved[*p] = true;
                reserved_y[*p] = true;
            }
            for (p, x) in updates {
                outline.points[p].x = x;
                outline.points[p].flags.set_marker(PointMarker::TOUCHED_X);
                reserved[p] = true;
            }
        }
        if stem_relative && self.curves.len() != 0 {
            // Curved-feature relations require a coherent prepared spline, not
            // a mixture of fitted extrema and un-interpolated source controls.
            // Complete upstream IUP before measuring widths/tangent dependencies.
            super::outline::align_weak_points(outline, super::super::topo::Dimension::Horizontal);
            super::outline::align_weak_points(outline, super::super::topo::Dimension::Vertical);
        }
        if stem_relative {
            applied += self.curves.apply(
                outline,
                metrics,
                &hard_x,
                hard_y,
                &self.joined,
                &mut reserved,
                &mut reserved_y,
            );
        }
        (
            [self.len() as u32, applied, self.len() as u32 - applied],
            reserved,
        )
    }
}

fn minimum_norm(rows: &[Vec<f64>], rhs: &[f64]) -> Option<Vec<f64>> {
    let n = rows.len();
    if n == 0 {
        return Some(Vec::new());
    }
    let mut matrix: Vec<Vec<f64>> = rows
        .iter()
        .enumerate()
        .map(|(i, a)| {
            let mut row: Vec<_> = rows
                .iter()
                .map(|b| a.iter().zip(b).map(|(x, y)| x * y).sum::<f64>())
                .collect();
            row.push(rhs[i]);
            row
        })
        .collect();
    let mut pivots = Vec::new();
    let mut rank = 0;
    for column in 0..n {
        let pivot = (rank..n).max_by(|a, b| {
            matrix[*a][column]
                .abs()
                .partial_cmp(&matrix[*b][column].abs())
                .unwrap()
        })?;
        if matrix[pivot][column].abs() <= 1e-9 {
            continue;
        }
        matrix.swap(rank, pivot);
        let divisor = matrix[rank][column];
        for value in &mut matrix[rank][column..=n] {
            *value /= divisor;
        }
        let pivot_row = matrix[rank][column..=n].to_vec();
        for (i, row) in matrix.iter_mut().enumerate() {
            if i == rank {
                continue;
            }
            let factor = row[column];
            for (value, pivot) in row[column..=n].iter_mut().zip(&pivot_row) {
                *value -= factor * pivot;
            }
        }
        pivots.push(column);
        rank += 1;
        if rank == n {
            break;
        }
    }
    if matrix.iter().skip(rank).any(|row| row[n].abs() > 1e-6) {
        return None;
    }
    let mut multipliers = vec![0.0; n];
    for (i, column) in pivots.iter().enumerate() {
        multipliers[*column] = matrix[i][n];
    }
    let mut delta = vec![0.0; rows[0].len()];
    for (row, multiplier) in rows.iter().zip(multipliers) {
        for (d, coefficient) in delta.iter_mut().zip(row) {
            *d += multiplier * coefficient;
        }
    }
    if rows.iter().zip(rhs).any(|(row, target)| {
        (row.iter().zip(&delta).map(|(a, b)| a * b).sum::<f64>() - target).abs() > 1e-5
    }) {
        return None;
    }
    Some(delta)
}

#[derive(Default)]
struct Ink {
    start: (f64, f64),
    current: (f64, f64),
    lines: Vec<Line>,
    starts: Vec<usize>,
}

impl Ink {
    fn contains(&self, x: f64, y: f64) -> bool {
        Self::contains_in(&self.lines, x, y, false)
    }

    fn contains_in(lines: &[Line], x: f64, y: f64, boundary: bool) -> bool {
        let mut winding = 0;
        for &((ax, ay), (bx, by)) in lines {
            let cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax);
            if boundary
                && cross.abs() < 1e-7
                && x >= ax.min(bx)
                && x <= ax.max(bx)
                && y >= ay.min(by)
                && y <= ay.max(by)
            {
                return true;
            }
            if ay <= y && by > y && cross > 0.0 {
                winding += 1;
            }
            if ay > y && by <= y && cross < 0.0 {
                winding -= 1;
            }
        }
        winding != 0
    }
}

impl OutlinePen for Ink {
    fn move_to(&mut self, x: f32, y: f32) {
        self.starts.push(self.lines.len());
        self.current = (x as f64 * 64.0, y as f64 * 64.0);
        self.start = self.current;
    }
    fn line_to(&mut self, x: f32, y: f32) {
        let next = (x as f64 * 64.0, y as f64 * 64.0);
        self.lines.push((self.current, next));
        self.current = next;
    }
    fn quad_to(&mut self, cx: f32, cy: f32, x: f32, y: f32) {
        let (ax, ay) = (self.current.0 / 64.0, self.current.1 / 64.0);
        for i in 1..=64 {
            let t = i as f64 / 64.0;
            let u = 1.0 - t;
            self.line_to(
                (u * u * ax + 2.0 * u * t * cx as f64 + t * t * x as f64) as f32,
                (u * u * ay + 2.0 * u * t * cy as f64 + t * t * y as f64) as f32,
            );
        }
    }
    fn curve_to(&mut self, cx: f32, cy: f32, dx: f32, dy: f32, x: f32, y: f32) {
        let (ax, ay) = (self.current.0 / 64.0, self.current.1 / 64.0);
        for i in 1..=64 {
            let t = i as f64 / 64.0;
            let u = 1.0 - t;
            self.line_to(
                (u * u * u * ax
                    + 3.0 * u * u * t * cx as f64
                    + 3.0 * u * t * t * dx as f64
                    + t * t * t * x as f64) as f32,
                (u * u * u * ay
                    + 3.0 * u * u * t * cy as f64
                    + 3.0 * u * t * t * dy as f64
                    + t * t * t * y as f64) as f32,
            );
        }
    }
    fn close(&mut self) {
        self.lines.push((self.current, self.start));
        self.current = self.start;
    }
}

fn intersects(a: Line, b: Line) -> bool {
    let side = |(ax, ay): (f64, f64), (bx, by): (f64, f64), (x, y): (f64, f64)| {
        (bx - ax) * (y - ay) - (by - ay) * (x - ax)
    };
    a.0 .0.min(a.1 .0) <= b.0 .0.max(b.1 .0)
        && b.0 .0.min(b.1 .0) <= a.0 .0.max(a.1 .0)
        && a.0 .1.min(a.1 .1) <= b.0 .1.max(b.1 .1)
        && b.0 .1.min(b.1 .1) <= a.0 .1.max(a.1 .1)
        && side(a.0, a.1, b.0) * side(a.0, a.1, b.1) <= 0.0
        && side(b.0, b.1, a.0) * side(b.0, b.1, a.1) <= 0.0
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::outline::{
        autohint::topo::Axis,
        unscaled::{UnscaledOutlineSink, UnscaledPoint},
    };
    use raw::tables::glyf::PointFlags;

    pub(super) fn outline(contours: &[&[(i16, i16)]]) -> Outline {
        let mut outline = Outline::default();
        outline.units_per_em = 1000;
        for contour in contours {
            let first = outline.points.len();
            for (i, &(x, y)) in contour.iter().enumerate() {
                outline
                    .push(UnscaledPoint {
                        x,
                        y,
                        flags: PointFlags::on_curve(),
                        is_contour_start: i == 0,
                    })
                    .unwrap();
                let p = outline.points.last_mut().unwrap();
                p.ox = round(x as f64 * 0.896);
                p.x = p.ox;
                p.oy = round(y as f64 * 0.896);
                p.y = p.oy;
            }
            for i in 0..contour.len() {
                let p = &mut outline.points[first + i];
                p.next_ix = (first + (i + 1) % contour.len()) as u16;
                p.prev_ix = (first + (i + contour.len() - 1) % contour.len()) as u16;
            }
        }
        outline
    }

    fn curve_join_outline(cubic: bool) -> Outline {
        let mut glyph = outline(&[&[
            (0, 0),
            (300, 600),
            (330, 640),
            (380, 640),
            (420, 630),
            (430, 600),
            (390, 600),
            (90, 0),
            (70, -40),
            (30, -40),
            (10, -30),
            (20, 0),
        ]]);
        for i in [2, 3, 8, 9] {
            glyph.points[i].flags = if cubic {
                PointFlags::off_curve_cubic()
            } else {
                PointFlags::off_curve_quad()
            };
        }
        glyph
    }

    #[test]
    fn terminal_dependencies_use_interpolated_parent_offsets() {
        // Shamir §§3.2–3.3 and VTT XSHIFT preserve dependent offsets. The
        // preparation-order hypothesis must retain upstream IUP's offsets,
        // rather than pinning the raw source controls after a parent shift.
        for reflected in [false, true] {
            let mut glyph = curve_join_outline(false);
            if reflected {
                for point in &mut glyph.points {
                    point.fx = -point.fx;
                    point.ox = -point.ox;
                    point.x = -point.x;
                }
            }
            let raw = glyph.points.to_vec();
            for p in [0, 4, 6, 10] {
                if p == 4 || p == 10 {
                    glyph.points[p].x += if reflected { -24 } else { 24 };
                }
                glyph.points[p].flags.set_marker(PointMarker::TOUCHED_X);
            }
            let plan = Plan::new(&glyph);
            super::super::outline::align_weak_points(
                &mut glyph,
                super::super::super::topo::Dimension::Horizontal,
            );
            let prepared = glyph.points.to_vec();
            assert_ne!(prepared[2].x - prepared[1].x, raw[2].x - raw[1].x);
            // Restore only weak coordinates so apply must perform preparation.
            for p in [1, 2, 3, 5, 7, 8, 9, 11] {
                glyph.points[p].x = raw[p].x;
            }
            let (counts, _) = plan.apply(
                &mut glyph,
                &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
                &Axis::default(),
                &[true; 12],
                true,
            );
            assert_eq!(counts, [1, 1, 0]);
            for (control, parent) in [(2, 1), (3, 4), (8, 7), (9, 10)] {
                assert_eq!(
                    glyph.points[control].x - glyph.points[parent].x,
                    prepared[control].x - prepared[parent].x
                );
            }
        }
    }

    #[test]
    fn dependent_curve_controls_preserve_terminal_x_tangents_after_interpolation() {
        // VTT XSHIFT preserves child-to-parent offsets. Two controls permit
        // distinct endpoint displacements; one quadratic control cannot do so.
        // Check actual tangent vectors and subsequent IUP ownership, independently
        // of the implementation's dependency weights.
        for cubic in [false, true] {
            let mut glyph = curve_join_outline(cubic);
            let old = glyph.points.to_vec();
            let plan = Plan::new(&glyph);
            assert_eq!(plan.len(), 1);
            let (counts, reserved) = plan.apply(
                &mut glyph,
                &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
                &Axis::default(),
                &[true; 12],
                false,
            );
            assert_eq!(counts, [1, 1, 0]);
            assert_ne!(glyph.points[1].x, old[1].x);
            for (control, parent) in [(2, 1), (3, 4), (8, 7), (9, 10)] {
                assert_eq!(
                    glyph.points[control].x - glyph.points[parent].x,
                    old[control].x - old[parent].x
                );
                assert_eq!(glyph.points[control].y, old[control].y);
                assert!(!glyph.points[control]
                    .flags
                    .has_marker(PointMarker::TOUCHED_Y));
                assert!(reserved[control]);
            }
            for p in [1, 4, 7, 10] {
                assert_eq!(glyph.points[p].y, old[p].y);
            }
            for p in [4, 10] {
                assert_eq!(glyph.points[p].x, old[p].x);
            }
            assert_eq!(glyph.points[7].x - glyph.points[0].x, 66);
            assert_eq!(glyph.points[6].x - glyph.points[1].x, 66);
            let xs = glyph.points.iter().map(|p| p.x).collect::<Vec<_>>();
            super::super::outline::align_weak_points(
                &mut glyph,
                super::super::super::topo::Dimension::Horizontal,
            );
            for p in [0, 1, 2, 3, 4, 6, 7, 8, 9, 10] {
                assert_eq!(glyph.points[p].x, xs[p]);
            }
        }
    }

    #[test]
    fn protected_curve_controls_and_excessive_retry_motion_reject_atomically() {
        let mut glyph = curve_join_outline(false);
        let old = glyph.points.to_vec();
        let mut plan = Plan::new(&glyph);
        // These child coordinates already belong to independent attachment
        // constraints. Their parents cannot acquire a new shift dependency.
        plan.joined[2][0] = true;
        plan.joined[8][0] = true;
        let (counts, reserved) = plan.apply(
            &mut glyph,
            &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
            &Axis::default(),
            &[true; 12],
            false,
        );
        assert_eq!(counts, [1, 0, 1]);
        assert!(reserved.iter().all(|p| !*p));
        assert_eq!(glyph.points.as_slice(), old.as_slice());

        let mut plan = Plan::new(&glyph);
        plan.pairs[0].width = 500.0;
        let (counts, reserved) = plan.apply(
            &mut glyph,
            &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
            &Axis::default(),
            &[true; 12],
            false,
        );
        assert_eq!(counts, [1, 0, 1]);
        assert!(reserved.iter().all(|p| !*p));
        assert_eq!(glyph.points.as_slice(), old.as_slice());
    }

    #[test]
    fn curve_to_curve_junctions_and_owned_opposite_ends_stay_protected() {
        for protected_by_shape in [true, false] {
            let mut glyph = curve_join_outline(false);
            if protected_by_shape {
                // Both far on-curve points also belong to a second curve. Moving
                // only one of those curves cannot preserve the junction shape.
                glyph.points[5].flags = PointFlags::off_curve_quad();
                glyph.points[11].flags = PointFlags::off_curve_quad();
            }
            let old = glyph.points.to_vec();
            let mut plan = Plan::new(&glyph);
            if !protected_by_shape {
                plan.joined[4][0] = true;
                plan.joined[10][0] = true;
            }
            let (counts, reserved) = plan.apply(
                &mut glyph,
                &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
                &Axis::default(),
                &[true; 12],
                false,
            );
            assert_eq!(counts, [1, 0, 1]);
            assert!(reserved.iter().all(|p| !*p));
            assert_eq!(glyph.points.as_slice(), old.as_slice());
        }
    }

    #[test]
    fn quadratic_spline_interior_control_has_symmetric_endpoint_displacement() {
        let mut glyph = curve_join_outline(false);
        // Extend the upper terminal to three quadratic controls. Its middle
        // control sits halfway along the spline's control sequence, so its
        // displacement must be the mean of the two terminal displacements.
        glyph.points[4].flags = PointFlags::off_curve_quad();
        let old = glyph.points.to_vec();
        let plan = Plan::new(&glyph);
        let (counts, _) = plan.apply(
            &mut glyph,
            &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
            &Axis::default(),
            &[true; 12],
            false,
        );
        assert_eq!(counts, [1, 1, 0]);
        let near = glyph.points[1].x - old[1].x;
        let far = glyph.points[5].x - old[5].x;
        assert_eq!(far, 0);
        assert_eq!(glyph.points[2].x - old[2].x, near);
        assert_eq!(glyph.points[4].x - old[4].x, far);
        assert!((2 * (glyph.points[3].x - old[3].x) - near - far).abs() <= 1);
    }

    #[test]
    fn extra_light_diagonals_preserve_normal_weight_and_contrast_under_projection() {
        // FreeType/Skrifa extra-light stems retain source width. The same
        // shared-width ratio must preserve both thin/thick roles through
        // reflection and steep/shallow fitted projections. Only the existing
        // 26.6 coordinate-rounding separation margin may increase that width.
        let mut metrics = ScaledAxisMetrics::default();
        metrics.width_metrics.is_extra_light = true;
        metrics
            .widths
            .push(super::super::super::metrics::ScaledWidth {
                scaled: 24,
                fitted: 24,
            });
        for source_slope in [-2.0_f64, -0.5, 0.5, 2.0] {
            for fitted_slope in [-1.5_f64, -0.4, 0.4, 1.5] {
                let mut fitted_normals = Vec::new();
                for normal in [18.0, 30.0] {
                    let border = Border {
                        a: 0,
                        b: 1,
                        slope: source_slope,
                        intercept: 0.0,
                        low: 0.0,
                        high: 640.0,
                        direction: 1,
                    };
                    let pair = Pair {
                        left: border,
                        right: Border {
                            direction: -1,
                            ..border
                        },
                        width: normal * (1.0 + source_slope * source_slope).sqrt(),
                    };
                    let fitted = stem_relative_width(&pair, &metrics, fitted_slope)
                        / (1.0 + fitted_slope * fitted_slope).sqrt();
                    assert!(fitted >= normal && fitted <= normal + 3.0);
                    assert!(fitted < 64.0, "extra-light stroke acquired a pixel floor");
                    fitted_normals.push(fitted);
                }
                assert!((fitted_normals[1] - fitted_normals[0] - 12.0).abs() < 1e-10);
            }
        }
    }

    #[test]
    fn stem_relative_fit_keeps_source_contrast_with_bounded_projection_error() {
        // Project hypothesis grounded in Shamir shared widths/relative dimensions
        // and VTT axial diagonal control: transfer the standard stem's fit ratio,
        // retaining distinct source stroke roles instead of snapping both to it.
        // FreeType's quarter-pixel distortion bound limits the final projection snap.
        let mut glyph = outline(&[
            &[(0, 0), (300, 600), (390, 600), (90, 0)],
            &[(600, 0), (900, 600), (1020, 600), (720, 0)],
        ]);
        let plan = Plan::new(&glyph);
        assert_eq!(plan.len(), 2);
        let mut metrics = ScaledAxisMetrics::default();
        metrics
            .widths
            .push(super::super::super::metrics::ScaledWidth {
                scaled: 96,
                fitted: 128,
            });
        let (counts, _) = plan.apply(
            &mut glyph,
            &[metrics.clone(), metrics.clone()],
            &Axis::default(),
            &[true; 8],
            true,
        );
        assert_eq!(counts, [2, 2, 0]);
        let mut normals = Vec::new();
        for offset in [0, 4] {
            let slope = (glyph.points[offset + 1].x - glyph.points[offset].x) as f64
                / (glyph.points[offset + 1].y - glyph.points[offset].y) as f64;
            let width = (glyph.points[offset + 3].x - glyph.points[offset].x) as f64;
            normals.push(width / (1.0 + slope * slope).sqrt());
        }
        // The two source normals are about 72 and 96 units; the standard changes
        // from 96 to 128 units. Thus desired normals are about 96 and 128 units.
        // Keep both within a quarter pixel plus the existing rounding margin.
        assert!((normals[0] - 96.0).abs() < 18.0);
        assert!((normals[1] - 128.0).abs() < 18.0);
        assert!(normals[1] > normals[0] + 8.0);
    }

    #[test]
    fn diagonal_pair_has_rounding_safe_separation_parallel_borders_and_fixed_y() {
        let mut glyph = outline(&[&[(0, 0), (300, 600), (390, 600), (90, 0)]]);
        let ys: Vec<_> = glyph.points.iter().map(|p| p.y).collect();
        let plan = Plan::new(&glyph);
        assert_eq!(plan.len(), 1);
        let (counts, reserved) = plan.apply(
            &mut glyph,
            &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
            &Axis::default(),
            &[true; 4],
            false,
        );
        assert_eq!(counts, [1, 1, 0]);
        assert!(reserved.iter().all(|p| *p));
        assert_eq!(glyph.points.iter().map(|p| p.y).collect::<Vec<_>>(), ys);
        assert_eq!(glyph.points[3].x - glyph.points[0].x, 66);
        assert_eq!(glyph.points[2].x - glyph.points[1].x, 66);
        assert_eq!(
            glyph.points[1].x - glyph.points[0].x,
            glyph.points[2].x - glyph.points[3].x
        );
    }

    #[test]
    fn shallow_diagonal_uses_the_horizontal_run_for_minimum_ink() {
        let mut glyph = outline(&[&[(0, 0), (600, 400), (690, 400), (90, 0)]]);
        let plan = Plan::new(&glyph);
        assert_eq!(plan.len(), 1);
        let (counts, _) = plan.apply(
            &mut glyph,
            &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
            &Axis::default(),
            &[true; 4],
            false,
        );
        assert_eq!(counts, [1, 1, 0]);
        let dx = (glyph.points[1].x - glyph.points[0].x) as f64;
        let dy = (glyph.points[1].y - glyph.points[0].y) as f64;
        let horizontal_width = (glyph.points[3].x - glyph.points[0].x) as f64;
        assert!(horizontal_width / (dx / dy) >= 64.0);
        assert!(horizontal_width < 128.0);
    }

    #[test]
    fn overlapping_axial_contour_preserves_transverse_join_ownership() {
        let glyph = outline(&[
            &[(0, 0), (300, 600), (390, 600), (90, 0)],
            &[(-50, -100), (-50, 300), (120, 300), (120, -100)],
        ]);
        let plan = Plan::new(&glyph);
        assert_eq!(plan.len(), 1);
        assert_eq!(plan.joined[0], [true, false]);
        assert_eq!(plan.joined[3], [true, false]);
        assert_eq!(plan.joined[1], [false, false]);
        let nested = outline(&[
            &[(-100, -100), (-100, 700), (500, 700), (500, -100)],
            &[(0, 0), (300, 600), (390, 600), (90, 0)],
        ]);
        assert!(Plan::new(&nested).joined.iter().all(|p| *p == [false; 2]));
    }

    #[test]
    fn unmodeled_curve_joins_retain_prepared_coordinates() {
        let mut glyph = outline(&[&[
            (0, 0),
            (300, 600),
            (340, 640),
            (390, 600),
            (90, 0),
            (40, -40),
        ]]);
        glyph.points[2].flags = PointFlags::off_curve_quad();
        glyph.points[5].flags = PointFlags::off_curve_quad();
        let old: Vec<_> = glyph.points.iter().copied().collect();
        let plan = Plan::new(&glyph);
        assert_eq!(plan.len(), 1);
        let (counts, reserved) = plan.apply(
            &mut glyph,
            &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
            &Axis::default(),
            &[true; 6],
            false,
        );
        assert_eq!(counts, [1, 0, 1]);
        assert!(reserved.iter().all(|p| !*p));
        assert_eq!(glyph.points.as_slice(), old.as_slice());
    }

    #[test]
    fn pair_detector_uses_ink_instead_of_gaps_and_excludes_curved_borders() {
        let glyph = outline(&[
            &[(0, 0), (300, 600), (390, 600), (90, 0)],
            &[(190, 0), (490, 600), (580, 600), (280, 0)],
        ]);
        assert_eq!(Plan::new(&glyph).len(), 2);
        let rectangle = outline(&[&[(0, 0), (0, 600), (90, 600), (90, 0)]]);
        assert_eq!(Plan::new(&rectangle).len(), 0);
        let mut curved = outline(&[&[(0, 0), (300, 600), (390, 600), (90, 0)]]);
        curved.points[1].flags = PointFlags::off_curve_quad();
        assert_eq!(Plan::new(&curved).len(), 0);
    }

    #[test]
    fn rejected_component_leaves_coordinates_and_ownership_unchanged() {
        let mut glyph = outline(&[&[(0, 0), (300, 600), (390, 600), (90, 0)]]);
        let old: Vec<_> = glyph.points.iter().copied().collect();
        let mut plan = Plan::new(&glyph);
        plan.pairs[0].width = 500.0;
        let (counts, reserved) = plan.apply(
            &mut glyph,
            &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
            &Axis::default(),
            &[true; 4],
            false,
        );
        assert_eq!(counts, [1, 0, 1]);
        assert!(reserved.iter().all(|p| !*p));
        assert_eq!(glyph.points.as_slice(), old.as_slice());
    }

    #[test]
    fn collapsed_fitted_y_leaves_the_component_unapplied() {
        let mut glyph = outline(&[&[(0, 0), (300, 600), (390, 600), (90, 0)]]);
        let plan = Plan::new(&glyph);
        for point in &mut glyph.points {
            point.y = 0;
        }
        let old: Vec<_> = glyph.points.iter().copied().collect();
        let (counts, reserved) = plan.apply(
            &mut glyph,
            &[ScaledAxisMetrics::default(), ScaledAxisMetrics::default()],
            &Axis::default(),
            &[true; 4],
            false,
        );
        assert_eq!(counts, [1, 0, 1]);
        assert!(reserved.iter().all(|p| !*p));
        assert_eq!(glyph.points.as_slice(), old.as_slice());
    }

    #[test]
    fn joint_solver_handles_shared_constraints_redundancy_and_conflicts() {
        let delta =
            minimum_norm(&[vec![1.0, -1.0, 0.0], vec![0.0, 1.0, -1.0]], &[1.0, 1.0]).unwrap();
        assert!((delta[0] - 1.0).abs() < 1e-9);
        assert!(delta[1].abs() < 1e-9);
        assert!((delta[2] + 1.0).abs() < 1e-9);
        assert_eq!(
            minimum_norm(&[vec![1.0], vec![1.0]], &[1.0, 1.0]).unwrap(),
            vec![1.0]
        );
        assert!(minimum_norm(&[vec![1.0], vec![1.0]], &[1.0, 2.0]).is_none());
    }

    #[test]
    fn stem_relative_transfer_uses_fitted_standard_without_integer_leap() {
        // Shamir §§3.2/3.4 shared widths: the diagonal transfer follows the
        // standard's actual fitted width. With {scaled 96, fitted 100} a
        // 96-unit source normal stays near 100 instead of leaping to the
        // reconstructed integer 128; distinct source roles stay distinct
        // through reflected/steep/shallow projections. PROJECT HYPOTHESIS:
        // fitted/scaled transfer under the smooth width policy.
        use super::super::super::metrics::ScaledWidth;
        let mut metrics = ScaledAxisMetrics::default();
        metrics.widths.push(ScaledWidth {
            scaled: 96,
            fitted: 100,
        });
        let pair_with_normal = |source_slope: f64, normal: f64| {
            let border = Border {
                a: 0,
                b: 1,
                slope: source_slope,
                intercept: 0.0,
                low: 0.0,
                high: 640.0,
                direction: 1,
            };
            Pair {
                left: border,
                right: Border {
                    direction: -1,
                    ..border
                },
                width: normal * (1.0 + source_slope * source_slope).sqrt(),
            }
        };
        let estimate = |result: f64, fitted_slope: f64| {
            (result - (1.0 + fitted_slope.abs()).ceil())
                / (1.0 + fitted_slope * fitted_slope).sqrt()
        };
        for source_slope in [-2.0_f64, -0.5, 0.5, 2.0] {
            for fitted_slope in [-1.5_f64, -0.5, 0.5, 1.5] {
                let thin = estimate(
                    stem_relative_width(
                        &pair_with_normal(source_slope, 80.0),
                        &metrics,
                        fitted_slope,
                    ),
                    fitted_slope,
                );
                let thick = estimate(
                    stem_relative_width(
                        &pair_with_normal(source_slope, 96.0),
                        &metrics,
                        fitted_slope,
                    ),
                    fitted_slope,
                );
                let normal_rounding_bound =
                    16.0 * fitted_slope.abs().max(1.0) / (1.0 + fitted_slope * fitted_slope).sqrt();
                assert!(
                    (thin - 80.0 * 100.0 / 96.0).abs() < normal_rounding_bound,
                    "thin role lost at slopes {source_slope}/{fitted_slope}: {thin}"
                );
                assert!(
                    (thick - 100.0).abs() < normal_rounding_bound,
                    "thick role leapt at slopes {source_slope}/{fitted_slope}: {thick}"
                );
                assert!(
                    thick > thin,
                    "roles merged at slopes {source_slope}/{fitted_slope}: {thin} vs {thick}"
                );
                // Reflection preserves the transfer exactly.
                assert_eq!(
                    stem_relative_width(
                        &pair_with_normal(source_slope, 96.0),
                        &metrics,
                        fitted_slope,
                    ),
                    stem_relative_width(
                        &pair_with_normal(-source_slope, 96.0),
                        &metrics,
                        -fitted_slope,
                    )
                );
            }
        }
        // A smooth 1.5px fitted standard transfers near itself, not 2px.
        metrics.widths[0] = ScaledWidth {
            scaled: 96,
            fitted: 96,
        };
        let result = stem_relative_width(&pair_with_normal(0.5, 96.0), &metrics, 0.5);
        assert!((estimate(result, 0.5) - 96.0).abs() < 16.0 / 1.25_f64.sqrt());
    }
}
