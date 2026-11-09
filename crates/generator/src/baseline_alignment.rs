//! Recover missed source-baseline associations before optional stroke fitting.
//!
//! Foundation: FreeType blue-zone association (freetype.org/autohinting/blues.html),
//! Shamir 2003 section 3.2 (relative point constraints), Hobby 1993 section 6
//! (Bezier control relations), and Shewchuk's filtered orientation predicates.
//! Project adaptation: solve the tangent-preserving Y-translation equalities
//! as a connected component. Only a source-baseline supporting terminal may
//! move; nonvertical tangent/control relations require equal displacement.
//! Vertical attachments retain direction, upper geometry and X remain fixed.
//! Uncertain ownership, curvature or hull separation keeps the preceding fit.

use crate::{
    diagonal_fitting::geometry::{self, Parsed, Pt, Segment},
    fail,
    orientation::filtered_sign,
    probe::FittedCommand,
    Error,
};

pub const MODEL: &str = "baseline-align-01";
// Computational bound, shared with the existing outline fitting stages.
const MAX_COMMANDS: usize = crate::diagonal_fitting::MAX_COMMANDS;
// The existing top-zone adaptation uses FreeType's one-pixel edge minimum.
const MIN_RUN_PX: f64 = 1.0;
// Independent nearest-grid placements differ by at most one pixel. This is
// a conservative movement budget, not a detector based on raster output.
const MAX_SHIFT_PX: f64 = 1.0;

pub struct Fit {
    pub commands: Vec<FittedCommand>,
    pub applied: bool,
    pub shift_px: f64,
}

fn points(parsed: &Parsed) -> Vec<Pt> {
    parsed
        .oncurve
        .iter()
        .chain(&parsed.offcurve)
        .copied()
        .collect()
}

fn indices(segment: Segment, oncurve: usize) -> Vec<usize> {
    match segment {
        Segment::Line { a, b } => vec![a, b],
        Segment::Quad { a, c, b } => vec![a, oncurve + c, b],
        Segment::Cubic { a, c1, c2, b } => vec![a, oncurve + c1, oncurve + c2, b],
    }
}

fn supports_above(points: &[Pt], a: usize, b: usize) -> bool {
    let (a, b) = (points[a], points[b]);
    let side = (b[0] - a[0]).signum() as i8;
    side != 0 && points.iter().all(|p| {
        matches!(filtered_sign(a[0], a[1], b[0], b[1], p[0], p[1]), Some(s) if s == 0 || s == side)
    })
}

fn component(source: &[Pt], upstream: &[Pt], segments: &[Vec<usize>], seed: usize) -> Vec<bool> {
    let mut edges = vec![Vec::new(); upstream.len()];
    for segment in segments {
        // Quadratic endpoint tangents are its two control-polygon edges.
        // Straight edges preserve their direction by the same equality.
        for pair in segment.windows(2) {
            let (a, b) = (pair[0], pair[1]);
            if source[a][0] != source[b][0]
                || upstream[a][0] != upstream[b][0]
                || upstream[a] == upstream[b]
            {
                edges[a].push(b);
                edges[b].push(a);
            }
        }
    }
    let mut moving = vec![false; upstream.len()];
    let mut stack = vec![seed];
    while let Some(i) = stack.pop() {
        if !moving[i] {
            moving[i] = true;
            stack.extend(&edges[i]);
        }
    }
    moving
}

fn orientation(points: &[Pt], ids: &[usize]) -> Option<i8> {
    let (a, b, c) = (points[ids[0]], points[ids[1]], points[ids[2]]);
    filtered_sign(a[0], a[1], b[0], b[1], c[0], c[1])
}

fn bounds(points: &[Pt], ids: &[usize], axis: usize) -> (f64, f64) {
    ids.iter()
        .fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), &i| {
            (lo.min(points[i][axis]), hi.max(points[i][axis]))
        })
}

// Bezier convex hulls bound the whole curves. Nonadjacent changed segments
// must have strictly separate boxes. Adjacent hulls may meet only at their
// shared endpoint, certified by an axis separating their control polygons.
fn hulls_separate(points: &[Pt], a: &[usize], b: &[usize]) -> bool {
    for axis in 0..2 {
        let (al, ah) = bounds(points, a, axis);
        let (bl, bh) = bounds(points, b, axis);
        if ah < bl || bh < al {
            return true;
        }
    }
    let shared: Vec<_> = [a[0], a[a.len() - 1]]
        .into_iter()
        .filter(|i| *i == b[0] || *i == b[b.len() - 1])
        .collect();
    if shared.len() != 1 {
        return false;
    }
    let p = points[shared[0]];
    (0..2).any(|axis| {
        let (al, ah) = bounds(points, a, axis);
        let (bl, bh) = bounds(points, b, axis);
        if !((ah == p[axis] && bl == p[axis]) || (bh == p[axis] && al == p[axis])) {
            return false;
        }
        let face = |ids: &[usize]| -> (f64, f64) {
            ids.iter()
                .filter(|&&i| points[i][axis] == p[axis])
                .fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), &i| {
                    (lo.min(points[i][1 - axis]), hi.max(points[i][1 - axis]))
                })
        };
        let (al, ah) = face(a);
        let (bl, bh) = face(b);
        al.max(bl) == p[1 - axis] && ah.min(bh) == p[1 - axis]
    })
}

fn geometry_retained(
    before: &[Pt],
    after: &[Pt],
    segments: &[Vec<usize>],
    moving: &[bool],
) -> bool {
    for (i, segment) in segments.iter().enumerate() {
        if !segment.iter().any(|&p| moving[p]) {
            continue;
        }
        for pair in segment.windows(2) {
            let (a, b) = (pair[0], pair[1]);
            let old = [before[b][0] - before[a][0], before[b][1] - before[a][1]];
            let new = [after[b][0] - after[a][0], after[b][1] - after[a][1]];
            if old == [0.0; 2] {
                if new != old {
                    return false;
                }
            } else if old[0] * new[1] != old[1] * new[0] || old[0] * new[0] + old[1] * new[1] <= 0.0
            {
                return false;
            }
        }
        if segment.len() == 3 {
            let old = orientation(before, segment);
            if old.is_none() || old != orientation(after, segment) {
                return false;
            }
        }
        for (j, other) in segments.iter().enumerate() {
            if i != j && !hulls_separate(after, segment, other) {
                return false;
            }
        }
    }
    true
}

fn commands_with_y(
    upstream: &[FittedCommand],
    points: &[Pt],
    oncurve: usize,
) -> Vec<FittedCommand> {
    let mut result = upstream.to_vec();
    let (mut on, mut off) = (0, oncurve);
    for command in &mut result {
        match command {
            FittedCommand::MoveTo(_, y) | FittedCommand::LineTo(_, y) => {
                *y = points[on][1] as f32;
                on += 1;
            }
            FittedCommand::QuadTo(_, y1, _, y) => {
                *y1 = points[off][1] as f32;
                *y = points[on][1] as f32;
                on += 1;
                off += 1;
            }
            FittedCommand::CurveTo(..) => unreachable!("unsupported cubic filtered before fitting"),
            FittedCommand::Close => {}
        }
    }
    result
}

/// Translate a certified baseline terminal, retaining the preceding fit on
/// unsupported geometry. Single-contour line/quadratic outlines only; native
/// axis ownership is enforced by the caller, independently of this geometry.
pub fn fit(
    source: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f32,
) -> Result<Fit, Error> {
    let unchanged = || Fit {
        commands: upstream.to_vec(),
        applied: false,
        shift_px: 0.0,
    };
    if !size_px.is_finite() || size_px <= 0.0 {
        return Err(fail("baseline alignment requires finite positive size"));
    }
    if source.len() > MAX_COMMANDS
        || source.len() != upstream.len()
        || !source
            .iter()
            .zip(upstream)
            .all(|(a, b)| std::mem::discriminant(a) == std::mem::discriminant(b))
        || !matches!(source.first(), Some(FittedCommand::MoveTo(..)))
        || !matches!(source.last(), Some(FittedCommand::Close))
        || source
            .iter()
            .filter(|c| matches!(c, FittedCommand::MoveTo(..) | FittedCommand::Close))
            .count()
            != 2
        || source
            .iter()
            .any(|c| matches!(c, FittedCommand::CurveTo(..)))
    {
        return Ok(unchanged());
    }
    let (Ok(raw), Ok(fitted)) = (
        geometry::parse_commands(source),
        geometry::parse_commands(upstream),
    ) else {
        return Err(fail(
            "baseline alignment requires finite outline coordinates",
        ));
    };
    if raw.contours.len() != 1 || raw.contours != fitted.contours {
        return Ok(unchanged());
    }
    let (source_points, before) = (points(&raw), points(&fitted));
    if source_points
        .iter()
        .chain(&before)
        .flatten()
        .any(|v| v.abs() > 32768.0)
    {
        return Err(fail("baseline alignment coordinate out of range"));
    }
    let band = (f64::from(size_px) / 40.0).min(0.5);
    let source_bottom = source_points
        .iter()
        .map(|p| p[1])
        .fold(f64::INFINITY, f64::min);
    let caps: Vec<_> = raw.contours[0]
        .iter()
        .filter_map(|segment| {
            let Segment::Line { a, b } = *segment else {
                return None;
            };
            let (p, q) = (source_points[a], source_points[b]);
            ((p[0] - q[0]).abs() >= MIN_RUN_PX
                && p[1].abs() <= band
                && q[1].abs() <= band
                && p[1].min(q[1]) == source_bottom
                && supports_above(&source_points, a, b)
                && supports_above(&before, a, b))
            .then_some((a, b))
        })
        .collect();
    let [(a, b)] = caps.as_slice() else {
        return Ok(unchanged());
    };
    let reference = if source_points[*a][1].abs() <= source_points[*b][1].abs() {
        *a
    } else {
        *b
    };
    // Retain the source offset relative to baseline zero, including the
    // terminal's slant/overshoot, instead of flattening it to a grid row.
    let shift = source_points[reference][1] - before[reference][1];
    if !(-MAX_SHIFT_PX..=-0.5).contains(&shift) {
        return Ok(unchanged());
    }
    let segments: Vec<_> = fitted.contours[0]
        .iter()
        .map(|s| indices(*s, fitted.oncurve.len()))
        .collect();
    let moving = component(&source_points, &before, &segments, *a);
    if !moving[*b]
        || moving
            .iter()
            .enumerate()
            .any(|(i, &m)| m && source_points[i][1].abs() > band)
    {
        return Ok(unchanged());
    }
    let moving_top = before
        .iter()
        .zip(&moving)
        .filter(|(_, m)| **m)
        .map(|(p, _)| p[1])
        .fold(f64::NEG_INFINITY, f64::max);
    if before.iter().zip(&moving).all(|(_, m)| *m)
        || before
            .iter()
            .zip(&moving)
            .any(|(p, &m)| !m && p[1] <= moving_top)
    {
        return Ok(unchanged());
    }
    let mut after = before.clone();
    for (point, &m) in after.iter_mut().zip(&moving) {
        if m {
            point[1] = f64::from((point[1] + shift) as f32);
        }
    }
    if !supports_above(&after, *a, *b) || !geometry_retained(&before, &after, &segments, &moving) {
        return Ok(unchanged());
    }
    Ok(Fit {
        commands: commands_with_y(upstream, &after, fitted.oncurve.len()),
        applied: true,
        shift_px: shift,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn synthetic_terminal() -> Vec<FittedCommand> {
        use FittedCommand::*;
        vec![
            MoveTo(0.0, -0.125),
            LineTo(-0.25, 0.0),
            QuadTo(-0.25, 1.0, -0.125, 2.0),
            LineTo(3.0, 2.0),
            QuadTo(3.0, 1.0, 3.0, 0.0),
            Close,
        ]
    }

    fn raised_terminal(source: &[FittedCommand]) -> Vec<FittedCommand> {
        use FittedCommand::*;
        source
            .iter()
            .cloned()
            .map(|mut c| {
                match &mut c {
                    MoveTo(_, y) | LineTo(_, y) | QuadTo(_, _, _, y) if *y <= 0.0 => *y += 0.625,
                    _ => {}
                }
                c
            })
            .collect()
    }

    #[test]
    fn terminal_translation_preserves_tangents_under_horizontal_reflection() {
        use FittedCommand::*;
        for reflect in [false, true] {
            let mut source = synthetic_terminal();
            let mut upstream = raised_terminal(&source);
            if reflect {
                for c in source.iter_mut().chain(&mut upstream) {
                    let mirror = |x: &mut f32| *x = 10.0 - *x;
                    match c {
                        MoveTo(x, _) | LineTo(x, _) => mirror(x),
                        QuadTo(x1, _, x, _) => {
                            mirror(x1);
                            mirror(x);
                        }
                        _ => {}
                    }
                }
            }
            let result = fit(&source, &upstream, 16.0).unwrap();
            assert!(result.applied);
            assert_eq!(result.shift_px, -0.625);
            assert_eq!(
                result.commands, source,
                "upper anchors/controls and terminal shape retained"
            );
            assert!(
                !fit(&source, &result.commands, 16.0).unwrap().applied,
                "idempotent association"
            );
        }
    }

    #[test]
    fn oblique_attachment_cannot_drag_upper_geometry_with_a_terminal() {
        let mut source = synthetic_terminal();
        let FittedCommand::QuadTo(x, _, _, _) = &mut source[2] else {
            unreachable!()
        };
        *x = -0.125;
        let upstream = raised_terminal(&source);
        let result = fit(&source, &upstream, 16.0).unwrap();
        assert!(
            !result.applied,
            "retaining the oblique tangent would move a control outside the baseline zone"
        );
        assert_eq!(result.commands, upstream);
    }

    #[test]
    fn descenders_and_multiple_contours_do_not_acquire_a_baseline_terminal() {
        let source = synthetic_terminal();
        let upstream = raised_terminal(&source);
        let mut multiple = source.clone();
        multiple.extend(source.clone());
        let mut fitted_multiple = upstream.clone();
        fitted_multiple.extend(upstream.clone());
        assert!(!fit(&multiple, &fitted_multiple, 16.0).unwrap().applied);
        let shift = |commands: &[FittedCommand]| -> Vec<FittedCommand> {
            commands
                .iter()
                .cloned()
                .map(|mut c| {
                    match &mut c {
                        FittedCommand::MoveTo(_, y) | FittedCommand::LineTo(_, y) => *y -= 2.0,
                        FittedCommand::QuadTo(_, y1, _, y) => {
                            *y1 -= 2.0;
                            *y -= 2.0;
                        }
                        _ => {}
                    }
                    c
                })
                .collect()
        };
        let descender = shift(&upstream);
        assert_eq!(
            fit(&shift(&source), &descender, 16.0).unwrap().commands,
            descender
        );
    }
}
