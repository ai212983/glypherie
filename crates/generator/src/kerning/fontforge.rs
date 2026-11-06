//! FontForge's native-band estimator with a source-relative project endpoint.
//!
//! The estimator preserves `aw2_findedges` and `aw2_bbox_separation` from
//! FontForge c41bdb922285f35defd1e1385adfd13bde1ab32a, including its cached
//! parameter traversal, design-unit flooring and top-band exclusion:
//! <https://github.com/fontforge/fontforge/blob/c41bdb922285f35defd1e1385adfd13bde1ab32a/fontforge/autowidth2.c>.
//! Copyright (C) 2009-2012 George Williams; BSD-3-Clause, see fontforge/.
//!
//! Preserving each source pair's measured separation, applying the full
//! source-relative correction and enforcing delivered feasibility are project
//! adaptations. They are not FontForge's shared-target AutoKern2 operation.
//! Gray measures fitted outlines and never thresholds antialiased coverage.

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

/// Admission for outline decoding: the command stream and the design-unit
/// scale must fit the evaluation budget.
fn check_command_budget(commands: &[FittedCommand], scale: f64) -> Result<(), Error> {
    if commands.len() > MAX_COMMANDS || !scale.is_finite() || scale <= 0.0 {
        return Err(fail("FontForge command or scale work limit exceeded"));
    }
    Ok(())
}

/// One raw outline coordinate scaled to design units.
fn scaled_point(x: f32, y: f32, scale: f64) -> Result<Point, Error> {
    Ok(Point {
        x: finite(f64::from(x) * scale)?,
        y: finite(f64::from(y) * scale)?,
    })
}

/// Close the active contour, emitting its closing edge when the endpoints
/// differ.
fn close_contour(
    result: &mut Vec<Vec<Point>>,
    current: &mut Option<Point>,
    start: Option<Point>,
) -> Result<(), Error> {
    let (Some(a), Some(b)) = (*current, start) else {
        return Err(fail("FontForge close requires an active contour"));
    };
    if a != b {
        result.push(vec![a, b]);
    }
    *current = Some(b);
    Ok(())
}

/// One drawing command's scaled design points: the anchor followed by each
/// raw coordinate in command order. Scaling lives in exactly one place.
fn command_points(anchor: Point, raw: &[(f32, f32)], scale: f64) -> Result<Vec<Point>, Error> {
    let mut points = vec![anchor];
    for (x, y) in raw {
        points.push(scaled_point(*x, *y, scale)?);
    }
    Ok(points)
}

/// Decode one drawing command against the active contour.
fn push_segment(
    result: &mut Vec<Vec<Point>>,
    current: &mut Option<Point>,
    command: &FittedCommand,
    scale: f64,
) -> Result<(), Error> {
    let anchor = current.ok_or_else(|| fail("FontForge command requires move_to"))?;
    let points = match *command {
        FittedCommand::LineTo(x, y) => command_points(anchor, &[(x, y)], scale)?,
        FittedCommand::QuadTo(x1, y1, x, y) => command_points(anchor, &[(x1, y1), (x, y)], scale)?,
        FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
            command_points(anchor, &[(x1, y1), (x2, y2), (x, y)], scale)?
        }
        _ => unreachable!(),
    };
    *current = points.last().copied();
    result.push(points);
    Ok(())
}

fn segments(commands: &[FittedCommand], scale: f64) -> Result<Vec<Vec<Point>>, Error> {
    check_command_budget(commands, scale)?;
    let mut result = Vec::new();
    let mut current = None;
    let mut start = None;
    for command in commands {
        match *command {
            FittedCommand::MoveTo(x, y) => {
                current = Some(scaled_point(x, y, scale)?);
                start = current;
            }
            FittedCommand::Close => close_contour(&mut result, &mut current, start)?,
            _ => push_segment(&mut result, &mut current, command, scale)?,
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
        result.extend(cubic_roots(d[0] / scale, d[1] / scale, d[2] / scale));
    }
    result.retain(|t| t.is_finite() && *t > 0.0 && *t < 1.0);
    Ok(result)
}

/// Interior extrema of a cubic Bézier coordinate via its scaled derivative
/// coefficients, using the numerically stable q formulation.
fn cubic_roots(c: f64, mid: f64, end: f64) -> Vec<f64> {
    let b = 2.0 * (mid - c);
    let a = c - 2.0 * mid + end;
    if a == 0.0 {
        if b != 0.0 {
            return vec![-c / b];
        }
        return Vec::new();
    }
    let discriminant = b * b - 4.0 * a * c;
    if discriminant >= 0.0 {
        let q = -0.5 * (b + discriminant.sqrt().copysign(b));
        if q == 0.0 {
            vec![-b / (2.0 * a)]
        } else {
            vec![q / a, c / q]
        }
    } else {
        Vec::new()
    }
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

/// Degenerate linear solve on a constant-slope segment, pinned to `[lo, hi]`.
/// Returns `None` when the polynomial is not linear.
fn linear_root(c: &[f64; 4], lo: f64, hi: f64) -> Option<Option<f64>> {
    if c[0] == 0.0 && c[1] == 0.0 && c[2] != 0.0 {
        let t = -c[3] / c[2];
        Some((lo <= t && t <= hi).then_some(t))
    } else {
        None
    }
}

/// Whether the endpoint values bracket a root by sign change.
fn brackets_root(low: f64, high: f64) -> bool {
    (low < 0.0 && high > 0.0) || (high < 0.0 && low > 0.0)
}

/// Whether the midpoint value keeps `low`'s half-interval.
fn keeps_low_interval(low: f64, test: f64) -> bool {
    (low < 0.0 && test < 0.0) || (low > 0.0 && test > 0.0)
}

/// Bisection on a sign-bracketed interval, stopping on endpoint collapse or
/// an exact midpoint hit.
fn bisect_to_root(c: [f64; 4], mut lo: f64, mut hi: f64, low: f64) -> Result<Option<f64>, Error> {
    for _ in 0..1100 {
        let t = (hi + lo) / 2.0;
        if t == lo || t == hi {
            return Ok(Some(t));
        }
        let test = polynomial(c, t)?;
        if test == 0.0 {
            return Ok(Some(t));
        }
        if keeps_low_interval(low, test) {
            lo = t;
        } else {
            hi = t;
        }
    }
    Err(fail("FontForge root solver work limit exceeded"))
}

// Pinned IterateSplineSolve endpoint rule, in font design units.
fn near_endpoint(value: f64, endpoint: f64) -> Option<f64> {
    if -0.0001 < value && value < 0.0001 {
        Some(endpoint)
    } else {
        None
    }
}

fn solve(mut c: [f64; 4], lo: f64, hi: f64, target: f64) -> Result<Option<f64>, Error> {
    c[3] = finite(c[3] - target)?;
    if let Some(answer) = linear_root(&c, lo, hi) {
        return Ok(answer);
    }
    let low = polynomial(c, lo)?;
    let high = polynomial(c, hi)?;
    if low == 0.0 {
        return Ok(Some(lo));
    }
    if high == 0.0 {
        return Ok(Some(hi));
    }
    if brackets_root(low, high) {
        return bisect_to_root(c, lo, hi, low);
    }
    if let Some(t) = near_endpoint(low, lo).or_else(|| near_endpoint(high, hi)) {
        return Ok(Some(t));
    }
    Ok(None)
}

#[cfg(test)]
fn analyze(commands: &[FittedCommand], scale: f64, em: u16) -> Result<Option<Envelope>, Error> {
    analyze_with_budget(commands, scale, em, &mut 0)
}

/// One segment group's extremum-split parameters and vertices: split every
/// Bézier at its x and y derivative roots so each span is monotone.
fn split_vertices(points: &[Point]) -> Result<(Vec<f64>, Vec<Point>), Error> {
    let mut ts = vec![0.0, 1.0];
    ts.extend(roots(points, true)?);
    ts.extend(roots(points, false)?);
    ts.sort_by(f64::total_cmp);
    ts.dedup();
    let vertices: Vec<_> = ts
        .iter()
        .map(|t| evaluate(points, *t))
        .collect::<Result<_, _>>()?;
    Ok((ts, vertices))
}

/// Sweep portions strictly monotone in y; horizontal spans carry no band
/// transition.
fn push_monotone_portions(
    portions: &mut Vec<Portion>,
    points: &[Point],
    ts: &[f64],
    vertices: &[Point],
) {
    for i in 0..ts.len() - 1 {
        if vertices[i].y != vertices[i + 1].y {
            portions.push(Portion {
                points: points.to_vec(),
                ta: ts[i],
                tb: ts[i + 1],
                p: vertices[i],
                q: vertices[i + 1],
            });
        }
    }
}

/// Decoded monotone sweep portions with every evaluated vertex kept for the
/// outline bounds below.
fn collect_portions(
    commands: &[FittedCommand],
    scale: f64,
) -> Result<(Vec<Portion>, Vec<Point>), Error> {
    let mut coordinates = Vec::new();
    let mut portions = Vec::new();
    for points in segments(commands, scale)? {
        let (ts, vertices) = split_vertices(&points)?;
        coordinates.extend(vertices.iter().copied());
        push_monotone_portions(&mut portions, &points, &ts, &vertices);
    }
    Ok((portions, coordinates))
}

fn bounds_of(coordinates: &[Point]) -> Bounds {
    Bounds {
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
    }
}

/// Band index range covering the outline, with the allocation guard that
/// keeps the edge arrays bounded.
fn band_range(bounds: &Bounds, height: f64) -> Result<(i32, i32), Error> {
    let imin_float = finite(bounds.miny / height)?.floor();
    let imax_float = finite(bounds.maxy / height)?.ceil();
    if imin_float < f64::from(i32::MIN + 1)
        || imax_float > f64::from(i32::MAX - 1)
        || imax_float - imin_float + 1.0 > MAX_BANDS as f64
    {
        return Err(fail("FontForge band count work limit exceeded"));
    }
    Ok((imin_float as i32, imax_float as i32))
}

/// One monotone portion's solved coefficients with its y extent and sweep
/// direction.
struct BandCtx {
    xc: [f64; 4],
    yc: [f64; 4],
    ymin: f64,
    ymax: f64,
    ta: f64,
    tb: f64,
    increasing: bool,
    height: f64,
}

/// One band's solved edge xs with the previous-band solution threaded to the
/// next band.
struct BandSolution {
    first_x: Option<f64>,
    second_x: Option<f64>,
    previous: Option<f64>,
}

/// The band-edge sweep: accumulates per-band design-unit extents across all
/// monotone portions, then quantizes them to native short edges.
struct BandSweep {
    imin: i32,
    imax: i32,
    height: f64,
    left: Vec<f64>,
    right: Vec<f64>,
    visits: usize,
}

impl BandSweep {
    fn new(imin: i32, imax: i32, height: f64) -> Self {
        let left = vec![f64::INFINITY; (imax - imin + 1) as usize];
        let right = vec![f64::NEG_INFINITY; left.len()];
        Self {
            imin,
            imax,
            height,
            left,
            right,
            visits: 0,
        }
    }

    /// Charge one portion's band span against the per-envelope and global
    /// evaluation budgets.
    fn charge(&mut self, first: i32, last: i32, total_visits: &mut usize) -> Result<(), Error> {
        self.visits += (last - first + 1) as usize;
        *total_visits += (last - first + 1) as usize;
        if self.visits > MAX_BAND_VISITS {
            return Err(fail("FontForge band evaluation work limit exceeded"));
        }
        if *total_visits > MAX_TOTAL_VISITS {
            return Err(fail("FontForge total evaluation work limit exceeded"));
        }
        Ok(())
    }

    /// Invert y on the monotone portion, bracketing from the previous band's
    /// solution when the sweep direction keeps it valid.
    fn solve_y(&self, ctx: &BandCtx, target: f64, old: Option<f64>) -> Result<Option<f64>, Error> {
        let (mut lo, mut hi) = (ctx.ta, ctx.tb);
        if let Some(old) = old {
            if ctx.increasing {
                lo = old;
            } else {
                hi = old;
            }
        }
        solve(ctx.yc, lo, hi, target)
    }

    /// The portion's x at a solved y parameter.
    fn band_x(xc: [f64; 4], t: Option<f64>) -> Result<Option<f64>, Error> {
        t.map(|t| polynomial(xc, t)).transpose()
    }

    /// Invert y at the band's exit: the top edge while it stays inside the
    /// portion, else the portion end. Returns the exit solution with the
    /// previous-band value threaded forward.
    fn solve_band_exit(
        &self,
        ctx: &BandCtx,
        top: f64,
        entry: Option<f64>,
    ) -> Result<(Option<f64>, Option<f64>), Error> {
        if top < ctx.ymax {
            let solved = self.solve_y(ctx, top, entry)?;
            Ok((solved, solved))
        } else {
            Ok((self.solve_y(ctx, ctx.ymax, entry)?, None))
        }
    }

    /// Solve one band's entry and exit, threading the previous band's
    /// solution as the entry bracket. Returns `None` for bands the portion
    /// does not reach.
    fn solve_band(
        &self,
        ctx: &BandCtx,
        index: i32,
        previous: Option<f64>,
    ) -> Result<Option<BandSolution>, Error> {
        let bottom = f64::from(index) * ctx.height;
        let top = bottom + ctx.height;
        if ctx.ymax < bottom || ctx.ymin > top {
            return Ok(None);
        }
        let entry = previous.map_or_else(|| self.solve_y(ctx, ctx.ymin, None), |t| Ok(Some(t)))?;
        let first_x = Self::band_x(ctx.xc, entry)?;
        let (exit, next) = self.solve_band_exit(ctx, top, entry)?;
        let second_x = Self::band_x(ctx.xc, exit)?;
        Ok(Some(BandSolution {
            first_x,
            second_x,
            previous: next,
        }))
    }

    /// Fold one band's solved edge xs into the accumulated extents.
    fn sweep_band(&mut self, index: i32, first_x: Option<f64>, second_x: Option<f64>) {
        let slot = (index - self.imin) as usize;
        for x in [first_x, second_x].into_iter().flatten() {
            self.left[slot] = self.left[slot].min(x);
            self.right[slot] = self.right[slot].max(x);
        }
    }

    fn sweep_portion(&mut self, portion: Portion, total_visits: &mut usize) -> Result<(), Error> {
        let Portion {
            points,
            ta,
            tb,
            p,
            q,
        } = portion;
        let ctx = BandCtx {
            xc: coefficients(&points, true)?,
            yc: coefficients(&points, false)?,
            ymin: p.y.min(q.y),
            ymax: p.y.max(q.y),
            ta,
            tb,
            increasing: q.y > p.y,
            height: self.height,
        };
        let first = self.imin.max((ctx.ymin / self.height).ceil() as i32 - 1);
        let last = self.imax.min((ctx.ymax / self.height).floor() as i32);
        self.charge(first, last, total_visits)?;
        let mut previous = if ctx.ymin <= f64::from(self.imin) * self.height {
            self.solve_y(&ctx, f64::from(self.imin) * self.height, None)?
        } else {
            None
        };
        for index in first..=last {
            if let Some(solution) = self.solve_band(&ctx, index, previous)? {
                self.sweep_band(index, solution.first_x, solution.second_x);
                previous = solution.previous;
            }
        }
        Ok(())
    }

    /// Quantize accumulated extents to native short edges relative to the
    /// outline bounds. Unrepresentable geometry abstains the envelope.
    fn into_edges(self, bounds: &Bounds) -> Result<Option<Envelope>, Error> {
        let mut edges = Vec::with_capacity(self.left.len());
        for (a, b) in self.left.into_iter().zip(self.right) {
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
            bounds: *bounds,
            imin: self.imin,
            imax: self.imax,
            edges,
        }))
    }
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
    let (portions, coordinates) = collect_portions(commands, scale)?;
    if coordinates.is_empty() {
        return Ok(None);
    }
    let bounds = bounds_of(&coordinates);
    let (imin, imax) = band_range(&bounds, height)?;
    let mut sweep = BandSweep::new(imin, imax, height);
    for portion in portions {
        sweep.sweep_portion(portion, total_visits)?;
    }
    sweep.into_edges(&bounds)
}

/// One shared band's inverse-square separation weight, softened by the
/// em/50 divisor. The divisor must stay positive for the weighted mean to
/// exist.
fn band_weight(sep: f64, em: u16) -> Result<f64, Error> {
    let divisor = finite(sep + f64::from(em) / 50.0)?;
    if divisor <= 0.0 {
        return Err(fail("FontForge weight divisor must be positive"));
    }
    let weight = finite(1.0 / divisor)?;
    finite(weight * weight)
}

fn separation(left: &Envelope, right: &Envelope, em: u16) -> Result<Option<f64>, Error> {
    let (mut total, mut count) = (0.0, 0.0);
    for index in left.imin.max(right.imin)..left.imax.min(right.imax) {
        if let (Some((_, a)), Some((b, _))) = (
            left.edges[(index - left.imin) as usize],
            right.edges[(index - right.imin) as usize],
        ) {
            let sep = f64::from(b) - f64::from(a);
            let weight = band_weight(sep, em)?;
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

/// Every output pair starts as an explicit Source retention with the reason
/// it keeps when the method abstains: fixed pitch, whitespace, tabular
/// digits or unsupported geometry.
fn seed_retain_table(context: &super::MethodContext<'_>) -> super::PairAdjustments {
    use super::PairDecision;
    let mut result = super::PairAdjustments::new();
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
                PairDecision::RetainSource(reason),
            );
        }
    }
    result
}

/// Restrict Mono solving to glyphs with delivered ink: a vanished binary
/// glyph has no facing ink to compensate. Gray keeps its outline geometry
/// independently of quantized coverage values.
fn retain_occupied_glyphs(
    scope: &mut std::collections::HashSet<u32>,
    context: &super::MethodContext<'_>,
) {
    if context.output_bits != 1 {
        return;
    }
    let occupied: std::collections::HashSet<_> = context
        .glyphs
        .iter()
        .filter(|g| g.pixels.iter().any(|v| *v != 0))
        .map(|g| g.codepoint)
        .collect();
    scope.retain(|cp| occupied.contains(cp));
}

/// Analyzed envelopes plus the prepared output geometry shared by every
/// pair.
struct ScopeMaps {
    source: HashMap<u32, Option<Envelope>>,
    fitted: HashMap<u32, Option<Envelope>>,
    outlines: HashMap<u32, super::outline::OutlineGeometry>,
    cells: HashMap<u32, super::placement::Rows>,
}

/// One supported pair's full source-relative correction request: solved
/// contour offsets with the finalized metrics the correction applies to.
struct PairCorrection {
    key: (u32, u32),
    source_offset: f64,
    fitted_offset: f64,
    unit: f64,
    source_advance: i32,
    source_kern: i32,
    advance: i32,
    saved: i32,
}

impl PairCorrection {
    /// Apply the full source-relative correction before the existing
    /// feasibility bound: whole-pixel admission, optical step, Mono/Gray
    /// minimum and integer placement encoding.
    fn apply(
        &self,
        mono: bool,
        maps: &ScopeMaps,
        feasibility_visits: &mut usize,
    ) -> Result<super::PairDecision, Error> {
        use super::PairDecision;
        if self.advance % 64 != 0 {
            return Err(fail("FontForge requires whole-pixel finalized advances"));
        }
        if self.saved % 64 != 0 {
            return Err(fail(
                "FontForge requires whole-pixel finalized pair adjustments",
            ));
        }
        let source_step =
            f64::from(self.source_advance) / 64.0 + f64::from(self.source_kern) / 64.0;
        let optical_step =
            finite(source_step + (self.source_offset - self.fitted_offset) / self.unit)?;
        // Rounding the adjustment preserves the existing signed tie policy
        // when an integer left advance makes the origin negative. The full
        // source-relative correction always applies to supported pairs.
        let adjustment = finite(optical_step - f64::from(self.advance) / 64.0)?.round();
        let minimum = if mono {
            super::placement::minimum(&maps.cells[&self.key.0], &maps.cells[&self.key.1])
        } else {
            maps.outlines[&self.key.0]
                .minimum_with_budget(&maps.outlines[&self.key.1], feasibility_visits)?
        };
        let step = (f64::from(self.advance) / 64.0 + adjustment)
            .max(minimum.map_or(f64::NEG_INFINITY, f64::from));
        let value = encode_step_adjustment(step, self.advance)?;
        Ok(PairDecision::Replace(value))
    }
}

/// Encode one corrected step as a whole-pixel 26.6 adjustment with integer
/// placement-range and overflow guards.
fn encode_step_adjustment(step: f64, advance: i32) -> Result<i32, Error> {
    if !step.is_finite() || step < f64::from(i32::MIN / 64) || step > f64::from(i32::MAX / 64) {
        return Err(fail("FontForge integer placement range exceeded"));
    }
    (step as i32)
        .checked_mul(64)
        .and_then(|s| s.checked_sub(advance))
        .ok_or_else(|| fail("FontForge adjustment overflow"))
}

/// Analyze one glyph's source and fitted envelopes for the scope.
fn analyze_glyph_pair(
    source_commands: &[FittedCommand],
    fitted_commands: &[FittedCommand],
    unit: f64,
    em: u16,
    total_visits: &mut usize,
) -> Result<(Option<Envelope>, Option<Envelope>), Error> {
    let source = analyze_with_budget(source_commands, 1.0, em, total_visits)?;
    let fitted = analyze_with_budget(fitted_commands, unit, em, total_visits)?;
    Ok((source, fitted))
}

/// Analyze every scope glyph's envelopes and prepare the output geometry
/// shared by all pairs, with allocation accounting across the scope.
fn analyze_scope(
    context: &super::MethodContext<'_>,
    scope: &std::collections::HashSet<u32>,
    unit: f64,
    records: &HashMap<u32, &crate::reference::ReferenceRecord>,
    total_visits: &mut usize,
) -> Result<ScopeMaps, Error> {
    let mut maps = ScopeMaps {
        source: HashMap::new(),
        fitted: HashMap::new(),
        outlines: HashMap::new(),
        cells: HashMap::new(),
    };
    let mut total_commands = 0usize;
    let mut total_bands = 0usize;
    for &cp in scope {
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
        let (source, fitted) = analyze_glyph_pair(
            commands,
            &record.fitted_commands,
            unit,
            context.units_per_em,
            total_visits,
        )?;
        total_bands += source.as_ref().map_or(0, |envelope| envelope.edges.len())
            + fitted.as_ref().map_or(0, |envelope| envelope.edges.len());
        if total_bands > MAX_TOTAL_BANDS {
            return Err(fail("FontForge total profile allocation limit exceeded"));
        }
        maps.source.insert(cp, source);
        maps.fitted.insert(cp, fitted);
        if context.output_bits != 1 {
            maps.outlines.insert(
                cp,
                super::outline::OutlineGeometry::new(&record.fitted_commands)?,
            );
        }
    }
    Ok(maps)
}

/// Mono delivery cells for the no-overlap feasibility bound; Gray measures
/// fitted outlines instead and needs no cells.
fn scope_cells(
    context: &super::MethodContext<'_>,
) -> Result<HashMap<u32, super::placement::Rows>, Error> {
    if context.output_bits != 1 {
        return Ok(HashMap::new());
    }
    context
        .glyphs
        .iter()
        .map(|g| Ok((g.codepoint, super::placement::cell_rows(g)?)))
        .collect()
}

/// Admit one pair's four envelopes for solving, charging the shared-band
/// overlap against the global pair budget. Missing envelopes skip the pair.
fn pair_envelopes<'a>(
    maps: &'a ScopeMaps,
    total_visits: &mut usize,
    a: u32,
    b: u32,
) -> Result<Option<(&'a Envelope, &'a Envelope, &'a Envelope, &'a Envelope)>, Error> {
    let Some(sa) = maps.source.get(&a).and_then(|envelope| envelope.as_ref()) else {
        return Ok(None);
    };
    let Some(sb) = maps.source.get(&b).and_then(|envelope| envelope.as_ref()) else {
        return Ok(None);
    };
    let Some(fa) = maps.fitted.get(&a).and_then(|envelope| envelope.as_ref()) else {
        return Ok(None);
    };
    let Some(fb) = maps.fitted.get(&b).and_then(|envelope| envelope.as_ref()) else {
        return Ok(None);
    };
    *total_visits += (sa.imax.min(sb.imax) - sa.imin.max(sb.imin)).max(0) as usize
        + (fa.imax.min(fb.imax) - fa.imin.max(fb.imin)).max(0) as usize;
    if *total_visits > MAX_TOTAL_VISITS {
        return Err(fail("FontForge total pair work limit exceeded"));
    }
    Ok(Some((sa, sb, fa, fb)))
}

/// Solve one pair's source and fitted contour offsets. Pairs without shared
/// measurement bands retain Source.
fn pair_offsets(
    source_left: &Envelope,
    source_right: &Envelope,
    fitted_left: &Envelope,
    fitted_right: &Envelope,
    em: u16,
) -> Result<Option<(f64, f64)>, Error> {
    let (Some(source_offset), Some(fitted_offset)) = (
        offset(source_left, source_right, em)?,
        offset(fitted_left, fitted_right, em)?,
    ) else {
        return Ok(None);
    };
    Ok(Some((source_offset, fitted_offset)))
}

/// The source table's contribution to the source-relative target. The source
/// `kerning` switch gates the source table as well as the Source endpoint.
fn source_kern_contribution(context: &super::MethodContext<'_>, a: u32, b: u32) -> i32 {
    if context.source_kerning {
        context.source_pairs_26_6.get(&(a, b)).copied().unwrap_or(0)
    } else {
        0
    }
}

fn resolve_pair(
    context: &super::MethodContext<'_>,
    em: u16,
    unit: f64,
    maps: &ScopeMaps,
    total_visits: &mut usize,
    feasibility_visits: &mut usize,
    a: u32,
    b: u32,
    result: &mut super::PairAdjustments,
) -> Result<(), Error> {
    use super::PairDecision;
    let Some((sa, sb, fa, fb)) = pair_envelopes(maps, total_visits, a, b)? else {
        return Ok(());
    };
    let Some((source_offset, fitted_offset)) = pair_offsets(sa, sb, fa, fb, em)? else {
        result.insert((a, b), PairDecision::RetainSource("no_shared_bands"));
        return Ok(());
    };
    let source_advance = *context
        .source_advances_26_6
        .get(&a)
        .ok_or_else(|| fail("FontForge source advance is missing"))?;
    let source_kern = source_kern_contribution(context, a, b);
    let advance = *context
        .advances_26_6
        .get(&a)
        .ok_or_else(|| fail("FontForge finalized advance is missing"))?;
    let saved = context
        .pair_adjustments_26_6
        .get(&(a, b))
        .copied()
        .unwrap_or(0);
    let correction = PairCorrection {
        key: (a, b),
        source_offset,
        fitted_offset,
        unit,
        source_advance,
        source_kern,
        advance,
        saved,
    };
    let mono = context.output_bits == 1;
    result.insert((a, b), correction.apply(mono, maps, feasibility_visits)?);
    Ok(())
}

/// Solve every in-scope pair's correction, charging pair work against the
/// global budget. Source-tabular digit pairs keep their seeded retention.
fn resolve_pairs(
    context: &super::MethodContext<'_>,
    scope: &std::collections::HashSet<u32>,
    em: u16,
    unit: f64,
    maps: &ScopeMaps,
    total_visits: &mut usize,
    feasibility_visits: &mut usize,
    result: &mut super::PairAdjustments,
) -> Result<(), Error> {
    let mut pairs = 0usize;
    for &a in scope {
        for &b in scope {
            if context.properties.tabular_digits && (48..=57).contains(&a) && (48..=57).contains(&b)
            {
                continue;
            }
            pairs += 1;
            if pairs > 1_048_576 {
                return Err(fail("FontForge pair work limit exceeded"));
            }
            resolve_pair(
                context,
                em,
                unit,
                maps,
                total_visits,
                feasibility_visits,
                a,
                b,
                result,
            )?;
        }
    }
    Ok(())
}

pub(super) fn resolve(
    context: &super::MethodContext<'_>,
    settings: &FontforgeSettings,
) -> Result<super::PairAdjustments, Error> {
    settings.validate()?;
    let mut result = seed_retain_table(context);
    if context.properties.monospace {
        return Ok(result);
    }
    let mut scope = super::placement::participating_codepoints(
        context.glyphs.iter().map(|g| g.codepoint),
        context.properties.tabular_digits,
    );
    retain_occupied_glyphs(&mut scope, context);
    let unit = f64::from(context.units_per_em) / context.size_px;
    if !unit.is_finite() || unit <= 0.0 {
        return Err(fail(
            "FontForge requires a finite positive coordinate scale",
        ));
    }
    let records: HashMap<_, _> = context.records.iter().map(|r| (r.codepoint, r)).collect();
    let mut total_visits = 0usize;
    let mut maps = analyze_scope(context, &scope, unit, &records, &mut total_visits)?;
    maps.cells = scope_cells(context)?;
    let mut feasibility_visits = 0usize;
    resolve_pairs(
        context,
        &scope,
        context.units_per_em,
        unit,
        &maps,
        &mut total_visits,
        &mut feasibility_visits,
        &mut result,
    )?;
    Ok(result)
}

#[cfg(test)]
mod tests;
