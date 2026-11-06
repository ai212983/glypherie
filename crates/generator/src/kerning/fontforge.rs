//! FontForge's native-band estimator with a source-relative project endpoint.
//!
//! The estimator preserves `aw2_findedges` and `aw2_bbox_separation` from
//! FontForge c41bdb922285f35defd1e1385adfd13bde1ab32a, including its cached
//! parameter traversal, design-unit flooring and top-band exclusion:
//! <https://github.com/fontforge/fontforge/blob/c41bdb922285f35defd1e1385adfd13bde1ab32a/fontforge/autowidth2.c>.
//! Copyright (C) 2009-2012 George Williams; BSD-3-Clause, see fontforge/.
//!
//! Preserving each source pair's measured separation, blending with finalized
//! metrics and enforcing delivered feasibility are project adaptations. They
//! are not FontForge's shared-target AutoKern2 operation. Gray measures fitted
//! outlines and never thresholds antialiased coverage.

use crate::{fail, probe::FittedCommand, Error};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

const SUBDIVISIONS: u16 = 200;
const MAX_COMMANDS: usize = 100_000;
const MAX_BANDS: usize = 20_000;
const MAX_BAND_VISITS: usize = 2_000_000;
const MAX_TOTAL_BANDS: usize = 2_000_000;
const MAX_TOTAL_VISITS: usize = 100_000_000;

/// The source-relative endpoint has no parameters: the full correction
/// always applies to supported pairs. Each source pair keeps its own
/// measured separation; there is no shared target or blend control.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FontforgeSettings {}

impl FontforgeSettings {
    pub fn validate(&self) -> Result<(), Error> {
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Point {
    x: f64,
    y: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Bounds {
    minx: f64,
    miny: f64,
    maxx: f64,
    maxy: f64,
}

#[derive(Clone, Debug)]
struct Envelope {
    bounds: Bounds,
    imin: i32,
    imax: i32,
    edges: Vec<Option<(i16, i16)>>,
}

struct Portion {
    points: Vec<Point>,
    ta: f64,
    tb: f64,
    p: Point,
    q: Point,
}

fn finite(value: f64) -> Result<f64, Error> {
    if value.is_finite() {
        Ok(value)
    } else {
        Err(fail("nonfinite FontForge geometry"))
    }
}

fn segments(commands: &[FittedCommand], scale: f64) -> Result<Vec<Vec<Point>>, Error> {
    if commands.len() > MAX_COMMANDS || !scale.is_finite() || scale <= 0.0 {
        return Err(fail("FontForge command or scale work limit exceeded"));
    }
    let point = |x: f32, y: f32| -> Result<Point, Error> {
        Ok(Point {
            x: finite(f64::from(x) * scale)?,
            y: finite(f64::from(y) * scale)?,
        })
    };
    let mut result = Vec::new();
    let mut current = None;
    let mut start = None;
    for command in commands {
        match *command {
            FittedCommand::MoveTo(x, y) => {
                current = Some(point(x, y)?);
                start = current;
            }
            FittedCommand::Close => {
                let (Some(a), Some(b)) = (current, start) else {
                    return Err(fail("FontForge close requires an active contour"));
                };
                if a != b {
                    result.push(vec![a, b]);
                }
                current = Some(b);
            }
            _ => {
                let a = current.ok_or_else(|| fail("FontForge command requires move_to"))?;
                let points = match *command {
                    FittedCommand::LineTo(x, y) => vec![a, point(x, y)?],
                    FittedCommand::QuadTo(x1, y1, x, y) => {
                        vec![a, point(x1, y1)?, point(x, y)?]
                    }
                    FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                        vec![a, point(x1, y1)?, point(x2, y2)?, point(x, y)?]
                    }
                    _ => unreachable!(),
                };
                current = points.last().copied();
                result.push(points);
            }
        }
    }
    Ok(result)
}

fn evaluate(points: &[Point], t: f64) -> Result<Point, Error> {
    if t == 0.0 {
        return Ok(points[0]);
    }
    if t == 1.0 {
        return Ok(points[points.len() - 1]);
    }
    let mut p = points.to_vec();
    for length in (1..points.len()).rev() {
        for i in 0..length {
            p[i] = Point {
                x: finite((1.0 - t) * p[i].x + t * p[i + 1].x)?,
                y: finite((1.0 - t) * p[i].y + t * p[i + 1].y)?,
            };
        }
    }
    Ok(p[0])
}

fn roots(points: &[Point], x: bool) -> Result<Vec<f64>, Error> {
    let coordinate = |p: Point| if x { p.x } else { p.y };
    let d: Vec<_> = points
        .windows(2)
        .map(|p| finite(coordinate(p[1]) - coordinate(p[0])))
        .collect::<Result<_, _>>()?;
    if d.len() == 1 {
        return Ok(Vec::new());
    }
    let scale = d.iter().fold(0.0f64, |a, b| a.max(b.abs()));
    if scale == 0.0 {
        return Ok(Vec::new());
    }
    let mut result = Vec::new();
    if d.len() == 2 {
        let (c, end) = (d[0] / scale, d[1] / scale);
        let a = end - c;
        if a != 0.0 {
            result.push(-c / a);
        }
    } else {
        let (c, mid, end) = (d[0] / scale, d[1] / scale, d[2] / scale);
        let b = 2.0 * (mid - c);
        let a = c - 2.0 * mid + end;
        if a == 0.0 {
            if b != 0.0 {
                result.push(-c / b);
            }
        } else {
            let discriminant = b * b - 4.0 * a * c;
            if discriminant >= 0.0 {
                let q = -0.5 * (b + discriminant.sqrt().copysign(b));
                if q == 0.0 {
                    result.push(-b / (2.0 * a));
                } else {
                    result.extend([q / a, c / q]);
                }
            }
        }
    }
    result.retain(|t| t.is_finite() && *t > 0.0 && *t < 1.0);
    Ok(result)
}

fn coefficients(points: &[Point], x: bool) -> Result<[f64; 4], Error> {
    let p: Vec<_> = points.iter().map(|p| if x { p.x } else { p.y }).collect();
    let d = p[0];
    let (a, b, c) = match p.len() {
        2 => (0.0, 0.0, p[1] - d),
        3 => {
            let c = 2.0 * (p[1] - d);
            (0.0, p[2] - d - c, c)
        }
        4 => {
            let c = 3.0 * (p[1] - d);
            let b = 3.0 * (p[2] - p[1]) - c;
            (p[3] - d - c - b, b, c)
        }
        _ => unreachable!(),
    };
    Ok([finite(a)?, finite(b)?, finite(c)?, d])
}

fn polynomial([a, b, c, d]: [f64; 4], t: f64) -> Result<f64, Error> {
    // Keep native separate binary64 operations; no mul_add contraction.
    finite(((a * t + b) * t + c) * t + d)
}

fn solve(mut c: [f64; 4], mut lo: f64, mut hi: f64, target: f64) -> Result<Option<f64>, Error> {
    c[3] = finite(c[3] - target)?;
    if c[0] == 0.0 && c[1] == 0.0 && c[2] != 0.0 {
        let t = -c[3] / c[2];
        return Ok((lo <= t && t <= hi).then_some(t));
    }
    let low = polynomial(c, lo)?;
    let high = polynomial(c, hi)?;
    if low == 0.0 {
        return Ok(Some(lo));
    }
    if high == 0.0 {
        return Ok(Some(hi));
    }
    if (low < 0.0 && high > 0.0) || (high < 0.0 && low > 0.0) {
        for _ in 0..1100 {
            let t = (hi + lo) / 2.0;
            if t == lo || t == hi {
                return Ok(Some(t));
            }
            let test = polynomial(c, t)?;
            if test == 0.0 {
                return Ok(Some(t));
            }
            if (low < 0.0 && test < 0.0) || (low > 0.0 && test > 0.0) {
                lo = t;
            } else {
                hi = t;
            }
        }
        return Err(fail("FontForge root solver work limit exceeded"));
    }
    // Pinned IterateSplineSolve endpoint rule, in font design units.
    if -0.0001 < low && low < 0.0001 {
        return Ok(Some(lo));
    }
    if -0.0001 < high && high < 0.0001 {
        return Ok(Some(hi));
    }
    Ok(None)
}

#[cfg(test)]
fn analyze(commands: &[FittedCommand], scale: f64, em: u16) -> Result<Option<Envelope>, Error> {
    analyze_with_budget(commands, scale, em, &mut 0)
}

fn analyze_with_budget(
    commands: &[FittedCommand],
    scale: f64,
    em: u16,
    total_visits: &mut usize,
) -> Result<Option<Envelope>, Error> {
    let height = f64::from(em / SUBDIVISIONS);
    if height == 0.0 {
        // Native AutoKern's integer chunk height cannot represent this font.
        return Ok(None);
    }
    let mut coordinates = Vec::new();
    let mut portions = Vec::new();
    for points in segments(commands, scale)? {
        let mut ts = vec![0.0, 1.0];
        ts.extend(roots(&points, true)?);
        ts.extend(roots(&points, false)?);
        ts.sort_by(f64::total_cmp);
        ts.dedup();
        let vertices: Vec<_> = ts
            .iter()
            .map(|t| evaluate(&points, *t))
            .collect::<Result<_, _>>()?;
        coordinates.extend(vertices.iter().copied());
        for i in 0..ts.len() - 1 {
            if vertices[i].y != vertices[i + 1].y {
                portions.push(Portion {
                    points: points.clone(),
                    ta: ts[i],
                    tb: ts[i + 1],
                    p: vertices[i],
                    q: vertices[i + 1],
                });
            }
        }
    }
    if coordinates.is_empty() {
        return Ok(None);
    }
    let bounds = Bounds {
        minx: coordinates
            .iter()
            .map(|p| p.x)
            .fold(f64::INFINITY, f64::min),
        miny: coordinates
            .iter()
            .map(|p| p.y)
            .fold(f64::INFINITY, f64::min),
        maxx: coordinates
            .iter()
            .map(|p| p.x)
            .fold(f64::NEG_INFINITY, f64::max),
        maxy: coordinates
            .iter()
            .map(|p| p.y)
            .fold(f64::NEG_INFINITY, f64::max),
    };
    let imin_float = finite(bounds.miny / height)?.floor();
    let imax_float = finite(bounds.maxy / height)?.ceil();
    if imin_float < f64::from(i32::MIN + 1)
        || imax_float > f64::from(i32::MAX - 1)
        || imax_float - imin_float + 1.0 > MAX_BANDS as f64
    {
        return Err(fail("FontForge band count work limit exceeded"));
    }
    let (imin, imax) = (imin_float as i32, imax_float as i32);
    let mut left = vec![f64::INFINITY; (imax - imin + 1) as usize];
    let mut right = vec![f64::NEG_INFINITY; left.len()];
    let mut visits = 0usize;
    for portion in portions {
        let Portion {
            points,
            ta,
            tb,
            p,
            q,
        } = portion;
        let xc = coefficients(&points, true)?;
        let yc = coefficients(&points, false)?;
        let (ymin, ymax) = (p.y.min(q.y), p.y.max(q.y));
        let first = imin.max((ymin / height).ceil() as i32 - 1);
        let last = imax.min((ymax / height).floor() as i32);
        visits += (last - first + 1) as usize;
        *total_visits += (last - first + 1) as usize;
        if visits > MAX_BAND_VISITS {
            return Err(fail("FontForge band evaluation work limit exceeded"));
        }
        if *total_visits > MAX_TOTAL_VISITS {
            return Err(fail("FontForge total evaluation work limit exceeded"));
        }
        let mut previous = if ymin <= f64::from(imin) * height {
            solve(yc, ta, tb, f64::from(imin) * height)?
        } else {
            None
        };
        let increasing = q.y > p.y;
        let find_y = |target: f64, old: Option<f64>| {
            let (mut lo, mut hi) = (ta, tb);
            if let Some(old) = old {
                if increasing {
                    lo = old;
                } else {
                    hi = old;
                }
            }
            solve(yc, lo, hi, target)
        };
        for index in first..=last {
            let bottom = f64::from(index) * height;
            let top = bottom + height;
            if ymax < bottom || ymin > top {
                continue;
            }
            let t = match previous {
                Some(t) => Some(t),
                None => find_y(ymin, None)?,
            };
            let first_x = t.map(|t| polynomial(xc, t)).transpose()?;
            let t = if top < ymax {
                previous = find_y(top, t)?;
                previous
            } else {
                previous = None;
                find_y(ymax, t)?
            };
            let second_x = t.map(|t| polynomial(xc, t)).transpose()?;
            let slot = (index - imin) as usize;
            for x in [first_x, second_x].into_iter().flatten() {
                left[slot] = left[slot].min(x);
                right[slot] = right[slot].max(x);
            }
        }
    }
    let mut edges = Vec::with_capacity(left.len());
    for (a, b) in left.into_iter().zip(right) {
        if a.is_infinite() {
            edges.push(None);
        } else {
            let (l, r) = (
                finite(a - bounds.minx)?.floor(),
                finite(b - bounds.maxx)?.floor(),
            );
            if !(-32766.0..=32766.0).contains(&l) || !(-32766.0..=32766.0).contains(&r) {
                // Native short/sentinel representation is unavailable; abstain.
                return Ok(None);
            }
            edges.push(Some((l as i16, r as i16)));
        }
    }
    Ok(Some(Envelope {
        bounds,
        imin,
        imax,
        edges,
    }))
}

fn separation(left: &Envelope, right: &Envelope, em: u16) -> Result<Option<f64>, Error> {
    let (mut total, mut count) = (0.0, 0.0);
    for index in left.imin.max(right.imin)..left.imax.min(right.imax) {
        if let (Some((_, a)), Some((b, _))) = (
            left.edges[(index - left.imin) as usize],
            right.edges[(index - right.imin) as usize],
        ) {
            let sep = f64::from(b) - f64::from(a);
            let divisor = finite(sep + f64::from(em) / 50.0)?;
            if divisor <= 0.0 {
                return Err(fail("FontForge weight divisor must be positive"));
            }
            let weight = finite(1.0 / divisor)?;
            let weight = finite(weight * weight)?;
            total = finite(total + weight * sep)?;
            count = finite(count + weight)?;
        }
    }
    if count == 0.0 {
        return Ok(None);
    }
    Ok(Some(finite(total / count)?.round_ties_even()))
}

fn offset(left: &Envelope, right: &Envelope, em: u16) -> Result<Option<f64>, Error> {
    separation(left, right, em)?
        .map(|s| finite(right.bounds.minx - left.bounds.maxx + s))
        .transpose()
}

pub(super) fn resolve(
    context: &super::MethodContext<'_>,
    settings: &FontforgeSettings,
) -> Result<super::PairAdjustments, Error> {
    settings.validate()?;
    let mut result = HashMap::new();
    for a in context.glyphs {
        for b in context.glyphs {
            let reason = if context.properties.monospace {
                "fixed_pitch"
            } else if char::from_u32(a.codepoint).is_some_and(char::is_whitespace)
                || char::from_u32(b.codepoint).is_some_and(char::is_whitespace)
            {
                "whitespace"
            } else if context.properties.tabular_digits
                && (48..=57).contains(&a.codepoint)
                && (48..=57).contains(&b.codepoint)
            {
                "source_tabular_digits"
            } else {
                "empty_or_unsupported_geometry"
            };
            result.insert(
                (a.codepoint, b.codepoint),
                super::PairDecision::RetainSource(reason),
            );
        }
    }
    if context.properties.monospace {
        return Ok(result);
    }
    let mut scope = super::placement::participating_codepoints(
        context.glyphs.iter().map(|g| g.codepoint),
        context.properties.tabular_digits,
    );
    if context.output_bits == 1 {
        // A vanished binary glyph has no facing ink to compensate. Gray keeps
        // its outline geometry independently of quantized coverage values.
        let occupied: std::collections::HashSet<_> = context
            .glyphs
            .iter()
            .filter(|g| g.pixels.iter().any(|v| *v != 0))
            .map(|g| g.codepoint)
            .collect();
        scope.retain(|cp| occupied.contains(cp));
    }
    let unit = f64::from(context.units_per_em) / context.size_px;
    if !unit.is_finite() || unit <= 0.0 {
        return Err(fail(
            "FontForge requires a finite positive coordinate scale",
        ));
    }
    let mut source = HashMap::new();
    let mut fitted = HashMap::new();
    let mut total_bands = 0usize;
    let records: HashMap<_, _> = context.records.iter().map(|r| (r.codepoint, r)).collect();
    let mut total_visits = 0usize;
    let mut total_commands = 0usize;
    let mut outlines = HashMap::new();
    for &cp in &scope {
        let commands = context
            .source_commands
            .get(&cp)
            .ok_or_else(|| fail("FontForge source outline is missing"))?;
        let record = records
            .get(&cp)
            .ok_or_else(|| fail("FontForge fitted outline is missing"))?;
        total_commands += commands.len() + record.fitted_commands.len();
        if total_commands > 262_144 {
            return Err(fail("FontForge total command allocation limit exceeded"));
        }
        let a = analyze_with_budget(commands, 1.0, context.units_per_em, &mut total_visits)?;
        let b = analyze_with_budget(
            &record.fitted_commands,
            unit,
            context.units_per_em,
            &mut total_visits,
        )?;
        total_bands +=
            a.as_ref().map_or(0, |v| v.edges.len()) + b.as_ref().map_or(0, |v| v.edges.len());
        if total_bands > MAX_TOTAL_BANDS {
            return Err(fail("FontForge total profile allocation limit exceeded"));
        }
        source.insert(cp, a);
        fitted.insert(cp, b);
        if context.output_bits != 1 {
            outlines.insert(
                cp,
                super::outline::OutlineGeometry::new(&record.fitted_commands)?,
            );
        }
    }
    let cells = if context.output_bits == 1 {
        context
            .glyphs
            .iter()
            .map(|g| Ok((g.codepoint, super::placement::cell_rows(g)?)))
            .collect::<Result<HashMap<_, _>, Error>>()?
    } else {
        HashMap::new()
    };
    let mut feasibility_visits = 0usize;
    let mut pairs = 0usize;
    for &a in &scope {
        for &b in &scope {
            if context.properties.tabular_digits && (48..=57).contains(&a) && (48..=57).contains(&b)
            {
                continue;
            }
            pairs += 1;
            if pairs > 1_048_576 {
                return Err(fail("FontForge pair work limit exceeded"));
            }
            let (Some(sa), Some(sb), Some(fa), Some(fb)) =
                (&source[&a], &source[&b], &fitted[&a], &fitted[&b])
            else {
                continue;
            };
            total_visits += (sa.imax.min(sb.imax) - sa.imin.max(sb.imin)).max(0) as usize
                + (fa.imax.min(fb.imax) - fa.imin.max(fb.imin)).max(0) as usize;
            if total_visits > MAX_TOTAL_VISITS {
                return Err(fail("FontForge total pair work limit exceeded"));
            }
            let (Some(source_offset), Some(fitted_offset)) = (
                offset(sa, sb, context.units_per_em)?,
                offset(fa, fb, context.units_per_em)?,
            ) else {
                result.insert((a, b), super::PairDecision::RetainSource("no_shared_bands"));
                continue;
            };
            let source_advance = *context
                .source_advances_26_6
                .get(&a)
                .ok_or_else(|| fail("FontForge source advance is missing"))?;
            let source_kern = if context.source_kerning {
                context.source_pairs_26_6.get(&(a, b)).copied().unwrap_or(0)
            } else {
                0
            };
            let advance = *context
                .advances_26_6
                .get(&a)
                .ok_or_else(|| fail("FontForge finalized advance is missing"))?;
            if advance % 64 != 0 {
                return Err(fail("FontForge requires whole-pixel finalized advances"));
            }
            if context
                .pair_adjustments_26_6
                .get(&(a, b))
                .copied()
                .unwrap_or(0)
                % 64
                != 0
            {
                return Err(fail(
                    "FontForge requires whole-pixel finalized pair adjustments",
                ));
            }
            let source_step = f64::from(source_advance) / 64.0 + f64::from(source_kern) / 64.0;
            let optical_step = finite(source_step + (source_offset - fitted_offset) / unit)?;
            // Rounding the adjustment preserves the existing signed tie policy
            // when an integer left advance makes the origin negative. The full
            // source-relative correction always applies to supported pairs.
            let adjustment = finite(optical_step - f64::from(advance) / 64.0)?.round();
            let minimum = if context.output_bits == 1 {
                super::placement::minimum(&cells[&a], &cells[&b])
            } else {
                outlines[&a].minimum_with_budget(&outlines[&b], &mut feasibility_visits)?
            };
            let step = (f64::from(advance) / 64.0 + adjustment)
                .max(minimum.map_or(f64::NEG_INFINITY, f64::from));
            if !step.is_finite()
                || step < f64::from(i32::MIN / 64)
                || step > f64::from(i32::MAX / 64)
            {
                return Err(fail("FontForge integer placement range exceeded"));
            }
            let value = (step as i32)
                .checked_mul(64)
                .and_then(|s| s.checked_sub(advance))
                .ok_or_else(|| fail("FontForge adjustment overflow"))?;
            result.insert((a, b), super::PairDecision::Replace(value));
        }
    }
    Ok(result)
}

#[cfg(test)]
mod tests;
