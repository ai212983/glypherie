//! TypeFacet Autokern profiles and pair constraints in font units.
//!
//! Port of revision 8c6db26d0c599ece16f3704696811275120a4044, copyright
//! (c) 2012 Charles Matthew Chen, Apache-2.0. See typefacet/NOTICE.txt.
//! This module owns the original profile construction and intrusion predicates.
//! Geometry acquisition, placement search and final rendering are caller policy.

mod geometry;
#[cfg(test)]
mod tests;
pub(crate) use geometry::{Point, Segment};

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TypefacetSettings {
    pub normal_distance_em: f64,
    pub intrusion_tolerance_em: f64,
    #[serde(default)]
    pub minimum_distance_em: f64,
    #[serde(default = "default_max_x_extrema_overlap_em")]
    pub max_x_extrema_overlap_em: f64,
}

fn default_max_x_extrema_overlap_em() -> f64 {
    0.1
}

impl Default for TypefacetSettings {
    fn default() -> Self {
        // Author manual example, not an automatically calibrated font setting.
        Self {
            normal_distance_em: 0.1,
            intrusion_tolerance_em: 0.1,
            minimum_distance_em: 0.0,
            max_x_extrema_overlap_em: default_max_x_extrema_overlap_em(),
        }
    }
}

impl TypefacetSettings {
    pub fn validate(&self) -> Result<(), crate::Error> {
        if !self.normal_distance_em.is_finite()
            || !(0.01..=0.5).contains(&self.normal_distance_em)
            || !self.intrusion_tolerance_em.is_finite()
            || !(0.0..=0.5).contains(&self.intrusion_tolerance_em)
            || !self.minimum_distance_em.is_finite()
            || !(0.0..=self.normal_distance_em).contains(&self.minimum_distance_em)
            || !self.max_x_extrema_overlap_em.is_finite()
            || !(0.0..=0.5).contains(&self.max_x_extrema_overlap_em)
        {
            return Err(crate::fail("TypeFacet requires normal distance in 0.01..=0.5 em, intrusion tolerance and maximum x-extrema overlap in 0..=0.5 em, and minimum distance in 0..=normal distance"));
        }
        Ok(())
    }
}

const MAX_ROWS: usize = 4096;
const MAX_SEGMENTS: usize = 131072;
const MAX_PROFILE_VALUES: usize = 2_000_000;
const MAX_WORK: usize = 100_000_000;

#[derive(Default)]
pub(crate) struct WorkBudget {
    visits: usize,
}
impl WorkBudget {
    fn charge(&mut self, visits: usize) -> Result<(), crate::Error> {
        self.visits = self
            .visits
            .checked_add(visits)
            .ok_or_else(|| crate::fail("TypeFacet work limit"))?;
        if self.visits > MAX_WORK {
            return Err(crate::fail("TypeFacet work limit exceeded"));
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub(crate) struct GeometryGlyph {
    pub codepoint: u32,
    pub contours: Vec<Vec<Segment>>,
}

#[derive(Clone, Copy)]
struct Grid {
    min: i32,
    precision: f64,
}
struct Shape {
    codepoint: u32,
    raw: Profile,
    minimum: Profile,
    maximum: Profile,
    bounds: [f64; 2],
}

pub(crate) struct Prepared {
    shapes: Vec<Shape>,
    indices: std::collections::HashMap<u32, usize>,
    grid: Grid,
    normal: f64,
    tolerance: f64,
    ascender: f64,
    extrema_overlap: f64,
}
pub(crate) struct PairConstraint<'a> {
    pub minimum_units: f64,
    pub maximum_units: f64,
    pub extrema_bound_units: f64,
    left: &'a Shape,
    right: &'a Shape,
    prepared: &'a Prepared,
}
impl Prepared {
    pub(crate) fn codepoints(&self) -> impl Iterator<Item = u32> + '_ {
        self.shapes.iter().map(|s| s.codepoint)
    }
    pub(crate) fn pair(&self, left: u32, right: u32) -> Option<PairConstraint<'_>> {
        let a = &self.shapes[*self.indices.get(&left)?];
        let b = &self.shapes[*self.indices.get(&right)?];
        let minimum =
            contact(&a.minimum.right, &b.minimum.left).unwrap_or(a.bounds[1] - b.bounds[0]);
        let maximum = contact(&a.maximum.right, &b.maximum.left)
            .unwrap_or(a.bounds[1] + self.normal - b.bounds[0]);
        Some(PairConstraint {
            minimum_units: minimum,
            maximum_units: maximum,
            extrema_bound_units: a.bounds[1] - b.bounds[0] - self.extrema_overlap,
            left: a,
            right: b,
            prepared: self,
        })
    }
}
impl PairConstraint<'_> {
    pub(crate) fn admissible(
        &self,
        origin_units: f64,
        budget: &mut WorkBudget,
    ) -> Result<bool, crate::Error> {
        if !origin_units.is_finite() {
            return Err(crate::fail("TypeFacet requires a finite origin"));
        }
        if origin_units < self.minimum_units || origin_units < self.extrema_bound_units {
            return Ok(false);
        }
        let p = self.prepared;
        Ok(intrusion(
            self.left,
            self.right,
            origin_units,
            p.normal,
            p.tolerance,
            p.grid,
            p.ascender,
            false,
            budget,
        )? && intrusion(
            self.left,
            self.right,
            origin_units,
            p.normal,
            p.tolerance,
            p.grid,
            p.ascender,
            true,
            budget,
        )?)
    }
}

#[derive(Debug)]
struct Profile {
    left: Vec<Option<f64>>,
    right: Vec<Option<f64>>,
}
impl Profile {
    fn new(rows: usize) -> Self {
        Self {
            left: vec![None; rows],
            right: vec![None; rows],
        }
    }
    fn add(&mut self, row: i32, x: f64) -> Result<(), crate::Error> {
        let i = usize::try_from(row)
            .map_err(|_| crate::fail("TypeFacet profile row outside bounds"))?;
        if i >= self.left.len() {
            return Err(crate::fail("TypeFacet profile row outside bounds"));
        }
        self.left[i] = Some(self.left[i].map_or(x, |v| v.min(x)));
        self.right[i] = Some(self.right[i].map_or(x, |v| v.max(x)));
        Ok(())
    }
    fn line(
        &mut self,
        a: Point,
        b: Point,
        grid: Grid,
        budget: &mut WorkBudget,
    ) -> Result<(), crate::Error> {
        let ya = (a.y / grid.precision).round() as i32;
        let yb = (b.y / grid.precision).round() as i32;
        budget.charge(usize::try_from((i64::from(ya) - i64::from(yb)).abs() + 1).unwrap())?;
        if ya == yb {
            self.add(ya - grid.min, a.x)?;
            self.add(ya - grid.min, b.x)?;
            return Ok(());
        }
        let (lo, hi, xlo, xhi) = if ya < yb {
            (ya, yb, a.x, b.x)
        } else {
            (yb, ya, b.x, a.x)
        };
        for offset in 0..=hi - lo {
            self.add(
                lo + offset - grid.min,
                xlo + (xhi - xlo) * f64::from(offset) / f64::from(hi - lo),
            )?;
        }
        Ok(())
    }
    fn segment(
        &mut self,
        segment: Segment,
        grid: Grid,
        budget: &mut WorkBudget,
    ) -> Result<(), crate::Error> {
        if let Segment::Line([a, b]) = segment {
            return self.line(a, b, grid, budget);
        }
        let mut last = segment.start();
        for i in 1..=16 {
            let next = if i == 16 {
                segment.end()
            } else {
                segment.evaluate(f64::from(i) / 16.0)
            };
            self.line(last, next, grid, budget)?;
            last = next;
        }
        Ok(())
    }
}

// Python 2 round(x, 1) rounds the actual binary value to decimal tenths.
// Multiplication can itself round onto a half: use its exact FMA residual
// to distinguish that from a true tie before applying ties away from zero.
fn python_round_tenth(x: f64) -> f64 {
    let absolute = x.abs();
    let scaled = absolute * 10.0;
    let lower = scaled.floor();
    let rounded = if scaled - lower == 0.5 && absolute.mul_add(10.0, -scaled) < 0.0 {
        lower
    } else {
        scaled.round()
    };
    (rounded / 10.0).copysign(x)
}

fn contact(a: &[Option<f64>], b: &[Option<f64>]) -> Option<f64> {
    a.iter()
        .zip(b)
        .filter_map(|(a, b)| Some(a.as_ref()? - b.as_ref()?))
        .reduce(f64::max)
}

// Upstream splitSection recurses at the first large gap, retaining overlap
// between the two slices. An explicit stack preserves this without stack risk.
fn intrusion(
    a: &Shape,
    b: &Shape,
    advance: f64,
    normal: f64,
    tolerance: f64,
    grid: Grid,
    ascender: f64,
    within_ascender: bool,
    budget: &mut WorkBudget,
) -> Result<bool, crate::Error> {
    let rows = a.raw.left.len();
    budget.charge(rows)?;
    let max_protrusion = normal * 1.5;
    let max_gap = (normal * 0.5 / grid.precision).round() as usize;
    let padding = (normal / grid.precision).round() as usize;
    let baseline = -f64::from(grid.min);
    let asc = (ascender / grid.precision).round() - f64::from(grid.min);
    let mut offsets = Vec::with_capacity(rows);
    for i in 0..rows {
        let mut value = match (a.maximum.right[i], b.maximum.left[i]) {
            (Some(x), Some(y)) => Some(advance + y - x),
            _ => None,
        };
        if within_ascender && !((baseline..=asc).contains(&(i as f64))) {
            value = None;
        }
        if (a.raw.right[i].is_none() || b.raw.left[i].is_none()) && value.is_some_and(|x| x >= 0.0)
        {
            value = None;
        }
        offsets.push(value);
    }
    let valid = |x: Option<f64>| x.is_some_and(|v| v < max_protrusion);
    let mut stack = vec![(0, rows)];
    while let Some((start, end)) = stack.pop() {
        // Bound all visits, including repeated scans of overlapping split
        // sections. Six scans also cover removal of missing end rows.
        budget.charge(6 * (end - start))?;
        let mut last = None;
        let mut split = None;
        for (i, value) in offsets[start..end].iter().enumerate() {
            if valid(*value) {
                if let Some(last) = last {
                    if i - last >= max_gap {
                        split = Some((i, last));
                        break;
                    }
                }
                last = Some(i);
            }
        }
        if let Some((i, last)) = split {
            stack.push((start + last + 1, end));
            stack.push((start, start + i));
            continue;
        }
        // Preserve upstream's index-based counts (not a conventional count).
        let mut head = 0;
        let mut tail = 0;
        for (i, v) in offsets[start..end].iter().enumerate() {
            if valid(*v) {
                break;
            }
            head = i;
        }
        for (i, v) in offsets[start..end].iter().rev().enumerate() {
            if valid(*v) {
                break;
            }
            tail = i;
        }
        let head = head.saturating_sub(padding);
        let tail = tail.saturating_sub(padding);
        if head + tail >= end - start {
            continue;
        }
        let mut lo = start + head;
        let mut hi = end - tail;
        while lo < hi && offsets[lo].is_none() {
            lo += 1;
        }
        while lo < hi && offsets[hi - 1].is_none() {
            hi -= 1;
        }
        if lo == hi {
            continue;
        }
        let mut total = 0.0;
        let mut powered = 0.0;
        let mut protrusion = 0.0;
        for value in &offsets[lo..hi] {
            let x = value.unwrap_or(max_protrusion);
            let intr = (-x).max(0.0);
            total += intr;
            powered += intr.powf(1.15);
            protrusion += x.max(0.0).min(max_protrusion);
        }
        if powered > protrusion || total > tolerance * (hi - lo) as f64 {
            return Ok(false);
        }
    }
    Ok(true)
}

pub(crate) fn prepare(
    glyphs: &[GeometryGlyph],
    units_per_em: u16,
    ascender_units: f64,
    settings: &TypefacetSettings,
) -> Result<Prepared, crate::Error> {
    settings.validate()?;
    if glyphs.len() > 1024 {
        return Err(crate::fail("TypeFacet geometry repertoire limit exceeded"));
    }
    if units_per_em == 0 || !ascender_units.is_finite() {
        return Err(crate::fail(
            "TypeFacet requires positive UPM and finite ascender",
        ));
    }
    let normal = settings.normal_distance_em * f64::from(units_per_em);
    let tolerance = settings.intrusion_tolerance_em * f64::from(units_per_em);
    let minimum_distance = settings.minimum_distance_em * f64::from(units_per_em);
    let precision = (0.005 * f64::from(units_per_em)).round();
    if precision < 1.0 {
        return Err(crate::fail(
            "TypeFacet precision rounds below one font unit",
        ));
    }
    let mut count = 0usize;
    let mut active = Vec::new();
    let mut seen = std::collections::HashSet::new();
    let mut min_y = f64::INFINITY;
    let mut max_y = f64::NEG_INFINITY;
    for glyph in glyphs {
        if !seen.insert(glyph.codepoint) {
            return Err(crate::fail("TypeFacet duplicate glyph"));
        }
        let mut bounds = [f64::INFINITY, f64::NEG_INFINITY];
        let mut any = false;
        for contour in &glyph.contours {
            // Empty contours still consume input-validation work.
            count = count
                .checked_add(contour.len().max(1))
                .ok_or_else(|| crate::fail("TypeFacet segment work limit"))?;
            if count > MAX_SEGMENTS {
                return Err(crate::fail("TypeFacet segment work limit exceeded"));
            }
            if contour.is_empty() {
                continue;
            }
            for (i, segment) in contour.iter().enumerate() {
                if !segment.valid()
                    || segment
                        .points()
                        .iter()
                        .any(|p| p.x.abs() > 1e8 || p.y.abs() > 1e8)
                    || segment.end() != contour[(i + 1) % contour.len()].start()
                {
                    return Err(crate::fail(
                        "TypeFacet requires valid connected closed contours",
                    ));
                }
                // minmaxPathsEvaluated uses the same fixed subdivisions as profiles.
                let divisions = if matches!(segment, Segment::Line(_)) {
                    1
                } else {
                    16
                };
                for i in 0..=divisions {
                    let p = if i == 0 {
                        segment.start()
                    } else if i == divisions {
                        segment.end()
                    } else {
                        segment.evaluate(f64::from(i) / f64::from(divisions))
                    };
                    bounds[0] = bounds[0].min(p.x);
                    bounds[1] = bounds[1].max(p.x);
                    min_y = min_y.min(p.y);
                    max_y = max_y.max(p.y);
                }
                any = true;
            }
        }
        if any {
            active.push((glyph, bounds));
        }
    }
    let mut prepared = Prepared {
        shapes: Vec::new(),
        indices: std::collections::HashMap::new(),
        grid: Grid { min: 0, precision },
        normal,
        tolerance,
        ascender: ascender_units,
        extrema_overlap: settings.max_x_extrema_overlap_em * f64::from(units_per_em),
    };
    if active.is_empty() {
        return Ok(prepared);
    }
    let minimum = ((min_y - normal) / precision).floor();
    let maximum = ((max_y + normal) / precision).ceil();
    if minimum.abs() > f64::from(i32::MAX / 4) || maximum.abs() > f64::from(i32::MAX / 4) {
        return Err(crate::fail("TypeFacet profile coordinate limit exceeded"));
    }
    let rows = (maximum - minimum + 1.0) as usize;
    if rows > MAX_ROWS
        || active
            .len()
            .checked_mul(rows)
            .and_then(|n| n.checked_mul(6))
            .is_none_or(|n| n > MAX_PROFILE_VALUES)
    {
        return Err(crate::fail("TypeFacet profile memory limit exceeded"));
    }
    prepared.grid.min = minimum as i32;
    let grid = prepared.grid;
    let mut budget = WorkBudget::default();
    for (glyph, bounds) in active {
        let mut shape = Shape {
            codepoint: glyph.codepoint,
            raw: Profile::new(rows),
            minimum: Profile::new(rows),
            maximum: Profile::new(rows),
            bounds,
        };
        for contour in &glyph.contours {
            if contour.is_empty() {
                continue;
            }
            for segment in contour {
                shape.raw.segment(*segment, grid, &mut budget)?;
            }
            let oriented: Vec<_> = if geometry::clockwise(contour) {
                contour.clone()
            } else {
                contour.iter().rev().map(|s| s.reverse()).collect()
            };
            for segment in oriented {
                if let Some(minimum) = segment.inflated(minimum_distance * 0.5)? {
                    shape.minimum.segment(minimum, grid, &mut budget)?;
                }
                // Preserve both endpoint circles, including their original cubic approximation.
                for endpoint in [segment.start(), segment.end()] {
                    if minimum_distance > 0.0 {
                        for arc in geometry::circle(endpoint, minimum_distance * 0.5) {
                            shape.minimum.segment(arc, grid, &mut budget)?;
                        }
                    }
                    for arc in geometry::circle(endpoint, normal * 0.5) {
                        shape.maximum.segment(arc, grid, &mut budget)?;
                    }
                }
                if let Some(maximum) = segment.inflated(normal * 0.5)? {
                    shape.maximum.segment(maximum, grid, &mut budget)?;
                }
            }
        }
        prepared
            .indices
            .insert(shape.codepoint, prepared.shapes.len());
        prepared.shapes.push(shape);
    }
    Ok(prepared)
}
