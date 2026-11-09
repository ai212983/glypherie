//! Hu/Hersch full fitted-wall adapter.
//!
//! The wall transforms follow Hu (1998) §4.4 and Hersch/Betrisey
//! US5768490A, transformations A–D, including the published .21 aperture and
//! .25 body-height depth factors. Bounded sampled bays and a 64/px midpoint
//! integral are the retained experiment's explicit numerical adaptation, not
//! recovered author code. Density calibration preserves the complete ASCII
//! class's mean source origin step; that constraint is a project policy.
//! https://patents.google.com/patent/US5768490A/en
//!
//! Mono retains the experiment's delivered n/H/0 body windows. Gray uses the
//! corresponding fitted-outline bounds, avoiding a coverage threshold or gamma
//! dependency. Both measure fitted outlines, without changing rendered paths.

use super::outline::{Outline, OutlineGeometry};
use crate::{fail, reference::ReferenceRecord, Error};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Published construction constants from Hersch/Betrisey US5768490A:
/// aperture-relative cavity DepthFactor (transformation C) and body-height
/// GlobalDepthParameter (transformation D). The adjustable 0..=1 range is a
/// project bound; the patent supplies the defaults, not this range.
/// See docs/references/hu-hersch-construction-order.md.
pub const APERTURE_DEPTH_FACTOR_DEFAULT: f64 = 0.21;
pub const GLOBAL_DEPTH_FACTOR_DEFAULT: f64 = 0.25;

fn aperture_default() -> f64 {
    APERTURE_DEPTH_FACTOR_DEFAULT
}

fn global_default() -> f64 {
    GLOBAL_DEPTH_FACTOR_DEFAULT
}

#[derive(Clone, Copy, Debug, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HuHerschSettings {
    /// Cavity-depth fraction of the cavity aperture height (patent C).
    #[serde(default = "aperture_default")]
    pub aperture_depth_factor: f64,
    /// Maximum wall-depth fraction of the class body height (patent D).
    #[serde(default = "global_default")]
    pub global_depth_factor: f64,
}

impl Default for HuHerschSettings {
    fn default() -> Self {
        Self {
            aperture_depth_factor: APERTURE_DEPTH_FACTOR_DEFAULT,
            global_depth_factor: GLOBAL_DEPTH_FACTOR_DEFAULT,
        }
    }
}

impl HuHerschSettings {
    pub fn validate(&self) -> Result<(), Error> {
        for (label, value) in [
            ("aperture depth factor", self.aperture_depth_factor),
            ("global depth factor", self.global_depth_factor),
        ] {
            if !value.is_finite() || !(0.0..=1.0).contains(&value) {
                return Err(fail(format!(
                    "Hu/Hersch {label} must be finite and between 0 and 1"
                )));
            }
        }
        Ok(())
    }
}

const SAMPLES_PER_PIXEL: f64 = 64.;
const MAX_SAMPLES: usize = 8192;
const MAX_VISITS: usize = 2_000_000;
const MAX_TOTAL_VISITS: usize = 100_000_000;

#[derive(Default)]
struct Budget(usize, usize);
impl Budget {
    fn outline(
        &mut self,
        commands: &[crate::probe::FittedCommand],
    ) -> Result<OutlineGeometry, Error> {
        self.1 = self
            .1
            .checked_add(commands.len())
            .ok_or_else(|| fail("Hu/Hersch outline allocation limit"))?;
        if self.1 > 262_144 {
            return Err(fail(
                "Hu/Hersch aggregate outline allocation limit exceeded",
            ));
        }
        let outline = OutlineGeometry::new(commands)?;
        // Both commands and their monotonic decomposition are bounded across
        // calibration and output preparation, before retaining more geometry.
        self.1 = self
            .1
            .checked_add(outline.0.portions.len())
            .ok_or_else(|| fail("Hu/Hersch outline allocation limit"))?;
        if self.1 > 262_144 {
            return Err(fail(
                "Hu/Hersch aggregate outline allocation limit exceeded",
            ));
        }
        Ok(outline)
    }
    fn charge(&mut self, amount: usize) -> Result<(), Error> {
        self.0 = self
            .0
            .checked_add(amount)
            .ok_or_else(|| fail("Hu/Hersch work limit"))?;
        if self.0 > MAX_TOTAL_VISITS {
            return Err(fail("Hu/Hersch work limit exceeded"));
        }
        Ok(())
    }
}

fn finite(value: f64) -> Result<f64, Error> {
    if value.is_finite() && value.abs() < 1e12 {
        Ok(value)
    } else {
        Err(fail("Hu/Hersch requires bounded finite geometry"))
    }
}

// Partial summation avoids making an alphabet target depend on hash iteration
// order. This is the error-free two-sum expansion used by math.fsum's reference
// recipe; no font- or glyph-dependent tolerance enters the measurement.
fn sum(values: impl IntoIterator<Item = f64>) -> f64 {
    let mut partials = Vec::<f64>::new();
    for mut x in values {
        let mut i = 0;
        for j in 0..partials.len() {
            let mut y = partials[j];
            if x.abs() < y.abs() {
                std::mem::swap(&mut x, &mut y);
            }
            let hi = x + y;
            let lo = y - (hi - x);
            if lo != 0. {
                partials[i] = lo;
                i += 1;
            }
            x = hi;
        }
        partials.truncate(i);
        partials.push(x);
    }
    partials.into_iter().rev().sum()
}

#[derive(Clone)]
struct Profile {
    left: Vec<f64>,
    right: Vec<f64>,
    occupied: Vec<bool>,
    mean_left: f64,
    mean_right: f64,
}

#[derive(Clone, Copy)]
struct Bay {
    lo: f64,
    hi: f64,
    a: f64,
    b: f64,
}

fn bays(ys: &[f64], values: &[f64]) -> Vec<Bay> {
    let mut runs = vec![];
    let mut start = 0;
    for i in 1..=values.len() {
        if i == values.len() || values[i] != values[start] {
            runs.push((start, i - 1, values[start]));
            start = i;
        }
    }
    let peaks: Vec<_> = runs
        .iter()
        .enumerate()
        .filter(|(i, v)| {
            (*i == 0 || v.2 > runs[*i - 1].2) && (*i == runs.len() - 1 || v.2 > runs[*i + 1].2)
        })
        .map(|(_, v)| *v)
        .collect();
    peaks
        .windows(2)
        .filter_map(|v| {
            let (a, b) = (v[0], v[1]);
            if a.1 + 1 >= b.0
                || values[a.1 + 1..b.0]
                    .iter()
                    .copied()
                    .fold(f64::INFINITY, f64::min)
                    >= a.2.min(b.2)
            {
                return None;
            }
            let lo = (ys[a.1] + ys[a.1 + 1]) / 2.;
            let hi = (ys[b.0 - 1] + ys[b.0]) / 2.;
            (lo < hi).then_some(Bay {
                lo,
                hi,
                a: a.2,
                b: b.2,
            })
        })
        .collect()
}

fn slice_indices(ys: &[f64], bay: Bay) -> (usize, usize) {
    (
        ys.partition_point(|y| *y < bay.lo),
        ys.partition_point(|y| *y <= bay.hi),
    )
}

fn slope_filter(ys: &[f64], raw: &[f64]) -> Vec<f64> {
    let mut result = raw.to_vec();
    for bay in bays(ys, raw) {
        let (start, stop) = slice_indices(ys, bay);
        let mut coords = vec![bay.lo];
        coords.extend_from_slice(&ys[start..stop]);
        coords.push(bay.hi);
        let mut values = vec![bay.a];
        values.extend_from_slice(&raw[start..stop]);
        values.push(bay.b);
        for i in 1..values.len() {
            values[i] = values[i].max(values[i - 1] - (coords[i] - coords[i - 1]));
        }
        for i in (0..values.len() - 1).rev() {
            values[i] = values[i].max(values[i + 1] - (coords[i + 1] - coords[i]));
        }
        for i in start..stop {
            result[i] = result[i].max(values[i - start + 1]);
        }
    }
    result
}

fn aperture_filter(ys: &[f64], slope: &[f64], aperture_depth_factor: f64) -> Vec<f64> {
    // Full-outline construction redetects C's bays on the output of B.
    let mut result = slope.to_vec();
    for bay in bays(ys, slope) {
        let (start, stop) = slice_indices(ys, bay);
        let cutoff = bay.a.max(bay.b) - aperture_depth_factor * (bay.hi - bay.lo);
        let inner = bay.a.min(bay.b);
        if inner >= cutoff {
            for value in &mut result[start..stop] {
                *value = value.max(cutoff);
            }
            continue;
        }
        asymmetric_connector(ys, slope, bay, cutoff, inner, start, stop, &mut result);
    }
    result
}

/// Patent Fig. 2b's asymmetric cavity connector: from the cutoff's departure
/// on the higher lip, ramp down to the recessed lip. Shallow cavities that
/// never reach the cutoff are filled flat by the caller instead.
fn asymmetric_connector(
    ys: &[f64],
    slope: &[f64],
    bay: Bay,
    cutoff: f64,
    inner: f64,
    start: usize,
    stop: usize,
    result: &mut [f64],
) {
    let forward = bay.a >= bay.b;
    let mut coords = vec![bay.lo];
    coords.extend_from_slice(&ys[start..stop]);
    coords.push(bay.hi);
    let mut values = vec![bay.a];
    values.extend_from_slice(&slope[start..stop]);
    values.push(bay.b);
    if !forward {
        coords = coords.into_iter().rev().map(|v| -v).collect();
        values.reverse();
    }
    let departure = coords.windows(2).zip(values.windows(2)).find_map(|(y, x)| {
        (x[0] >= cutoff && x[1] < cutoff)
            .then(|| y[0] + (y[1] - y[0]) * (x[0] - cutoff) / (x[0] - x[1]))
    });
    if let Some(departure) = departure {
        let end = coords[coords.len() - 1];
        for i in start..stop {
            let y = if forward { ys[i] } else { -ys[i] };
            if departure <= y && y <= end {
                result[i] =
                    result[i].max(cutoff + (y - departure) * (inner - cutoff) / (end - departure));
            }
        }
    }
}

/// The construction sampling policy: midpoint samples over the class body
/// window with full-outline margins on both sides, so wall construction sees
/// the contour beyond the body integral.
struct SampleGrid {
    ys: Vec<f64>,
    before: usize,
    count: usize,
    height: f64,
}

/// The body sample-count allocation policy: the window must sample to a
/// representable row count.
fn check_sample_count(count: usize) -> Result<(), Error> {
    if count == 0 || count > MAX_SAMPLES {
        return Err(fail("Hu/Hersch sample limit exceeded"));
    }
    Ok(())
}

/// The full-outline allocation policy: body samples plus both construction
/// margins must stay bounded.
fn check_construction_total(before: usize, count: usize, after: usize) -> Result<usize, Error> {
    let total = before
        .checked_add(count)
        .and_then(|v| v.checked_add(after))
        .ok_or_else(|| fail("Hu/Hersch construction sample limit"))?;
    if total > MAX_SAMPLES {
        return Err(fail("Hu/Hersch full-outline sample limit exceeded"));
    }
    Ok(total)
}

/// Midpoint body samples with full-outline margins on both sides. The grid
/// must stay strictly increasing to remain representable.
fn grid_ys(lo: f64, dy: f64, count: usize, before: usize, after: usize) -> Result<Vec<f64>, Error> {
    let body: Vec<_> = (0..count).map(|i| lo + (i as f64 + 0.5) * dy).collect();
    let mut ys: Vec<_> = (1..=before)
        .rev()
        .map(|i| body[0] - i as f64 * dy)
        .collect();
    ys.extend_from_slice(&body);
    ys.extend((1..=after).map(|i| body[count - 1] + i as f64 * dy));
    if ys.windows(2).any(|v| v[0] >= v[1]) {
        return Err(fail("Hu/Hersch sample grid is unrepresentable"));
    }
    Ok(ys)
}

fn sample_grid(bounds: super::outline::Bounds, window: (f64, f64)) -> Result<SampleGrid, Error> {
    let (lo, hi) = window;
    let height = finite(hi - lo)?;
    if height <= 0. {
        return Err(fail("Hu/Hersch body window must have positive height"));
    }
    let count = finite(height * SAMPLES_PER_PIXEL)?.ceil() as usize;
    check_sample_count(count)?;
    let dy = height / count as f64;
    let before = finite((lo - bounds.miny).max(0.) / dy)?.ceil() as usize;
    let after = finite((bounds.maxy - hi).max(0.) / dy)?.ceil() as usize;
    check_construction_total(before, count, after)?;
    let ys = grid_ys(lo, dy, count, before, after)?;
    Ok(SampleGrid {
        ys,
        before,
        count,
        height,
    })
}

/// Scanline wall accumulation over the construction grid: each outline
/// portion contributes its x extents to the rows it crosses. Empty rows keep
/// sentinel walls for the finishing substitution.
fn scan_walls(
    outline: &Outline,
    ys: &[f64],
    budget: &mut Budget,
) -> Result<(Vec<f64>, Vec<f64>, Vec<bool>), Error> {
    let mut left = vec![f64::INFINITY; ys.len()];
    let mut right = vec![f64::NEG_INFINITY; ys.len()];
    let mut occupied = vec![false; ys.len()];
    let mut visits = 0;
    for portion in &outline.portions {
        let (miny, maxy) = portion.y_range();
        let start = ys.partition_point(|y| *y < miny);
        let end = ys.partition_point(|y| *y <= maxy);
        visits += end - start;
        if visits > MAX_VISITS {
            return Err(fail("Hu/Hersch scanline evaluation limit exceeded"));
        }
        budget.charge(end - start)?;
        for i in start..end {
            let (a, b) = if miny == maxy {
                (portion.a[0], portion.b[0])
            } else {
                let x = portion.at_y(ys[i])?;
                (x, x)
            };
            left[i] = left[i].min(a).min(b);
            right[i] = right[i].max(a).max(b);
            occupied[i] = true;
        }
    }
    Ok((left, right, occupied))
}

/// Wall finishing: empty scanlines take the opposite edge (Hu 1998 §4.4),
/// then the B slope filter, C aperture filter and D body-height clamp run in
/// construction order before the fsum wall means.
fn finish_profile(
    grid: &SampleGrid,
    left: Vec<f64>,
    right: Vec<f64>,
    occupied: Vec<bool>,
    bounds: super::outline::Bounds,
    settings: &HuHerschSettings,
) -> Profile {
    let mut left = left;
    let mut right = right;
    for i in 0..occupied.len() {
        if !occupied[i] {
            left[i] = bounds.maxx;
            right[i] = bounds.minx;
        }
    }
    let outward_left: Vec<_> = left.iter().map(|x| -x).collect();
    let slope_left = slope_filter(&grid.ys, &outward_left);
    let slope_right = slope_filter(&grid.ys, &right);
    let aperture_left = aperture_filter(&grid.ys, &slope_left, settings.aperture_depth_factor);
    let aperture_right = aperture_filter(&grid.ys, &slope_right, settings.aperture_depth_factor);
    let filtered_left: Vec<_> = aperture_left[grid.before..grid.before + grid.count]
        .iter()
        .map(|x| (-x).min(bounds.minx + settings.global_depth_factor * grid.height))
        .collect();
    let filtered_right: Vec<_> = aperture_right[grid.before..grid.before + grid.count]
        .iter()
        .map(|x| x.max(bounds.maxx - settings.global_depth_factor * grid.height))
        .collect();
    let mean_left = sum(filtered_left.iter().copied()) / grid.count as f64;
    let mean_right = sum(filtered_right.iter().copied()) / grid.count as f64;
    Profile {
        left: filtered_left,
        right: filtered_right,
        occupied: occupied[grid.before..grid.before + grid.count].to_vec(),
        mean_left,
        mean_right,
    }
}

fn profile(
    outline: &Outline,
    window: (f64, f64),
    budget: &mut Budget,
    settings: &HuHerschSettings,
) -> Result<Option<Profile>, Error> {
    let Some(bounds) = outline.bounds else {
        return Ok(None);
    };
    let grid = sample_grid(bounds, window)?;
    let (left, right, occupied) = scan_walls(outline, &grid.ys, budget)?;
    Ok(Some(finish_profile(
        &grid, left, right, occupied, bounds, settings,
    )))
}

/// The Latin case-combination rule: which cased-letter pairs share a density
/// class. Script admission and the digit fast path live in
/// `calibration_class`.
fn latin_case_pair(a: char, b: char) -> Option<super::CalibrationClass> {
    use super::CalibrationClass::*;
    use unicode_general_category::{get_general_category, GeneralCategory};
    match (get_general_category(a), get_general_category(b)) {
        (GeneralCategory::LowercaseLetter, GeneralCategory::LowercaseLetter) => Some(Lowercase),
        (GeneralCategory::UppercaseLetter, GeneralCategory::UppercaseLetter) => Some(Uppercase),
        (GeneralCategory::LowercaseLetter, GeneralCategory::UppercaseLetter)
        | (GeneralCategory::UppercaseLetter, GeneralCategory::LowercaseLetter) => Some(Mixed),
        _ => None,
    }
}

/// Only cased Latin letters use the Latin reference alphabets. Other Unicode
/// letters must not silently inherit Latin density. Numerals are experimental
/// and limited to the ASCII set on which the tabular safeguard is measured.
pub(super) fn calibration_class(left: u32, right: u32) -> Option<super::CalibrationClass> {
    use super::CalibrationClass::*;
    use unicode_script::{Script, UnicodeScript};
    if (48..=57).contains(&left) && (48..=57).contains(&right) {
        return Some(Digits);
    }
    let a = char::from_u32(left)?;
    let b = char::from_u32(right)?;
    if a.script() != Script::Latin || b.script() != Script::Latin {
        return None;
    }
    latin_case_pair(a, b)
}

fn products(class: super::CalibrationClass) -> Vec<(Vec<u32>, Vec<u32>)> {
    use super::CalibrationClass::*;
    let lower: Vec<_> = (97..=122).collect();
    let upper: Vec<_> = (65..=90).collect();
    let digits: Vec<_> = (48..=57).collect();
    match class {
        Lowercase => vec![(lower.clone(), lower)],
        Uppercase => vec![(upper.clone(), upper)],
        Digits => vec![(digits.clone(), digits)],
        Mixed => vec![(lower.clone(), upper.clone()), (upper, lower)],
    }
}

fn reference_window(record: &ReferenceRecord, mono: bool) -> Result<Option<(f64, f64)>, Error> {
    if !mono {
        return Ok(Outline::new(&record.fitted_commands)?
            .bounds
            .map(|b| (b.miny, b.maxy))
            .filter(|(a, b)| a < b));
    }
    let width = record.width as usize;
    let height = record.height as usize;
    if width.checked_mul(height) != Some(record.pixels.len())
        || record.pixels.len() > 2_000_000
        || record.pixels.iter().any(|v| *v > 1)
    {
        return Err(fail(
            "Hu/Hersch reference requires bounded unpacked binary pixels",
        ));
    }
    if width == 0 {
        return Ok(None);
    }
    let rows: Vec<_> = (0..height)
        .filter(|row| {
            record.pixels[row * width..(row + 1) * width]
                .iter()
                .any(|v| *v != 0)
        })
        .collect();
    Ok(rows.first().zip(rows.last()).map(|(first, last)| {
        (
            -(record.top as f64 + *last as f64) - 1.,
            -(record.top as f64 + *first as f64),
        )
    }))
}

fn class_window(
    class: super::CalibrationClass,
    records: &HashMap<u32, &ReferenceRecord>,
    mono: bool,
) -> Result<Option<(f64, f64)>, Error> {
    use super::CalibrationClass::*;
    if class == Mixed {
        let lower = class_window(Lowercase, records, mono)?;
        let upper = class_window(Uppercase, records, mono)?;
        return Ok(lower
            .zip(upper)
            .map(|(a, b)| ((a.0 + b.0) / 2., (a.1 + b.1) / 2.)));
    }
    let reference = match class {
        Lowercase => 110,
        Uppercase => 72,
        Digits => 48,
        Mixed => unreachable!(),
    };
    records
        .get(&reference)
        .map_or(Ok(None), |record| reference_window(record, mono))
}

/// Admit one class's calibration repertoire: the capture must be available
/// and every alphabet glyph must carry a source advance. Returns the alphabet
/// products with their record index and sorted repertoire.
fn admitted_repertoire(
    capture: &super::CalibrationCapture,
) -> Option<(
    Vec<(Vec<u32>, Vec<u32>)>,
    HashMap<u32, &ReferenceRecord>,
    Vec<u32>,
)> {
    if capture.unavailable_reason.is_some() {
        return None;
    }
    let products = products(capture.class);
    let records: HashMap<_, _> = capture.records.iter().map(|r| (r.codepoint, r)).collect();
    let mut repertoire: Vec<_> = products
        .iter()
        .flat_map(|(a, b)| a.iter().chain(b))
        .copied()
        .collect();
    repertoire.sort_unstable();
    repertoire.dedup();
    if repertoire
        .iter()
        .any(|cp| !records.contains_key(cp) || !capture.source_advances_26_6.contains_key(cp))
    {
        return None;
    }
    Some((products, records, repertoire))
}

/// Profile every repertoire glyph on the class window; a missing wall
/// abstains the whole calibration.
fn profile_repertoire(
    records: &HashMap<u32, &ReferenceRecord>,
    repertoire: &[u32],
    window: (f64, f64),
    budget: &mut Budget,
    settings: &HuHerschSettings,
) -> Result<Option<HashMap<u32, Profile>>, Error> {
    let mut profiles = HashMap::new();
    for &cp in repertoire {
        let outline = budget.outline(&records[&cp].fitted_commands)?;
        let Some(value) = profile(&outline.0, window, budget, settings)? else {
            return Ok(None);
        };
        profiles.insert(cp, value);
    }
    Ok(Some(profiles))
}

/// The shared density target over the class alphabet: mean source origin
/// step plus mean fitted-wall offset, in exact fsum order. A pair without
/// shared ink rows abstains the whole calibration.
fn calibration_target(
    products: &[(Vec<u32>, Vec<u32>)],
    profiles: &HashMap<u32, Profile>,
    capture: &super::CalibrationCapture,
    count: usize,
) -> Result<Option<f64>, Error> {
    let mut steps = vec![];
    let mut offsets = vec![];
    for (left, right) in products {
        for &a in left {
            for &b in right {
                let pa = &profiles[&a];
                let pb = &profiles[&b];
                if !pa.occupied.iter().zip(&pb.occupied).any(|(a, b)| *a && *b) {
                    return Ok(None);
                }
            }
        }
        let advances = sum(left
            .iter()
            .map(|cp| f64::from(capture.source_advances_26_6[cp]) / 64.));
        let kern = sum(left.iter().flat_map(|a| {
            right.iter().map(move |b| {
                f64::from(*capture.source_pairs_26_6.get(&(*a, *b)).unwrap_or(&0)) / 64.
            })
        }));
        steps.push(advances * right.len() as f64 + kern);
        let offset = sum(right.iter().map(|cp| profiles[cp].mean_left)) / right.len() as f64
            - sum(left.iter().map(|cp| profiles[cp].mean_right)) / left.len() as f64;
        offsets.push((left.len() * right.len()) as f64 * offset);
    }
    let target = finite(sum(steps) / count as f64 + sum(offsets) / count as f64)?;
    Ok((target > 0.).then_some(target))
}

fn calibrate(
    capture: &super::CalibrationCapture,
    mono: bool,
    budget: &mut Budget,
    settings: &HuHerschSettings,
) -> Result<Option<((f64, f64), f64)>, Error> {
    let Some((products, records, repertoire)) = admitted_repertoire(capture) else {
        return Ok(None);
    };
    let Some(window) = class_window(capture.class, &records, mono)? else {
        return Ok(None);
    };
    let Some(profiles) = profile_repertoire(&records, &repertoire, window, budget, settings)?
    else {
        return Ok(None);
    };
    let count: usize = products.iter().map(|(a, b)| a.len() * b.len()).sum();
    let target = calibration_target(&products, &profiles, capture, count)?;
    Ok(target.map(|target| (window, target)))
}

/// Every output pair starts as an explicit Source retention; supported
/// classes replace their entries below, abstentions keep their reason.
fn seed_retain_table(context: &super::MethodContext<'_>) -> super::PairAdjustments {
    use super::PairDecision;
    let mut result = super::PairAdjustments::new();
    for left in context.glyphs {
        for right in context.glyphs {
            let reason = if context.properties.tabular_digits
                && (48..=57).contains(&left.codepoint)
                && (48..=57).contains(&right.codepoint)
            {
                "source_tabular_digits"
            } else {
                "unsupported_calibration_class"
            };
            result.insert(
                (left.codepoint, right.codepoint),
                PairDecision::RetainSource(reason),
            );
        }
    }
    result
}

/// Whether a glyph admitted under its own case class also profiles under
/// Mixed: only the two cased Latin classes cross over.
fn mixed_case_admit(class: super::CalibrationClass, own: Option<super::CalibrationClass>) -> bool {
    use super::CalibrationClass::*;
    class == Mixed && (own == Some(Lowercase) || own == Some(Uppercase))
}

/// One pair's continuous optical ideal: mean fitted-wall gap against the
/// class target. Pairs without shared ink rows abstain before rounding.
/// Pair integration follows the retained math.fsum order rather than
/// subtracting independently rounded single-wall means.
fn pair_ideal(a: &Profile, b: &Profile, target: f64) -> Result<Option<f64>, Error> {
    if !a.occupied.iter().zip(&b.occupied).any(|(a, b)| *a && *b) {
        return Ok(None);
    }
    // Pair integration follows the retained math.fsum order rather
    // than subtracting independently rounded single-wall means.
    let offset = sum(a.right.iter().zip(&b.left).map(|(a, b)| b - a)) / a.left.len() as f64;
    Ok(Some(finite(target - offset)?))
}

/// Retain the experiment's signed adjustment rounding, including ties away
/// from zero; there is no common post-method rounder. The full optical
/// correction always applies to supported pairs.
fn quantized_step(advance_26_6: i32, optical_adjustment: f64) -> Result<i32, Error> {
    let adjustment = optical_adjustment.round();
    if adjustment.abs() > f64::from(i32::MAX / 64) {
        return Err(fail("Hu/Hersch origin exceeds layout range"));
    }
    Ok(advance_26_6 / 64 + adjustment as i32)
}

/// The per-resolve Hu/Hersch candidate state: prepared output geometry shared
/// across classes plus the render-mode switch. Calibration targets stay with
/// their class; this owns only output-side preparation and placement.
struct Resolver<'a> {
    context: &'a super::MethodContext<'a>,
    calibration: &'a [super::CalibrationCapture],
    settings: &'a HuHerschSettings,
    records: HashMap<u32, &'a ReferenceRecord>,
    outlines: HashMap<u32, OutlineGeometry>,
    cells: HashMap<u32, super::placement::Rows>,
    budget: Budget,
    mono: bool,
}

impl<'a> Resolver<'a> {
    fn new(
        context: &'a super::MethodContext<'a>,
        calibration: &'a [super::CalibrationCapture],
        settings: &'a HuHerschSettings,
    ) -> Self {
        let records: HashMap<_, _> = context.records.iter().map(|r| (r.codepoint, r)).collect();
        Self {
            context,
            calibration,
            settings,
            records,
            outlines: HashMap::new(),
            cells: HashMap::new(),
            budget: Budget::default(),
            mono: context.output_bits == 1,
        }
    }

    fn run(&mut self) -> Result<super::PairAdjustments, Error> {
        use super::CalibrationClass::*;
        let mut result = seed_retain_table(self.context);
        for class in [Lowercase, Uppercase, Digits, Mixed] {
            self.resolve_class(class, &mut result)?;
        }
        Ok(result)
    }

    fn resolve_class(
        &mut self,
        class: super::CalibrationClass,
        result: &mut super::PairAdjustments,
    ) -> Result<(), Error> {
        if class == super::CalibrationClass::Digits && self.context.properties.tabular_digits {
            return Ok(());
        }
        let (calibrated, retention) = self.calibrate_class(class)?;
        let profiles = if let Some((window, _)) = calibrated {
            self.build_class_profiles(class, window)?
        } else {
            HashMap::new()
        };
        for left in self.context.glyphs {
            for right in self.context.glyphs {
                self.place_class_pair(
                    (left.codepoint, right.codepoint),
                    class,
                    calibrated,
                    retention,
                    &profiles,
                    result,
                )?;
            }
        }
        Ok(())
    }

    /// Run one class's density calibration, reporting both the shared target
    /// and the retention reason its pairs keep when calibration is unavailable.
    fn calibrate_class(
        &mut self,
        class: super::CalibrationClass,
    ) -> Result<(Option<((f64, f64), f64)>, &'static str), Error> {
        let captured = self.calibration.iter().find(|c| c.class == class);
        let retention = captured
            .and_then(|c| c.unavailable_reason)
            .unwrap_or("calibration_unavailable");
        let calibrated = captured
            .map(|c| calibrate(c, self.mono, &mut self.budget, self.settings))
            .transpose()?
            .flatten();
        Ok((calibrated, retention))
    }

    /// Profile one class's admitted glyphs on its calibrated window. Glyphs
    /// whose own class differs keep their seeded retention; glyphs without
    /// records keep an empty profile entry that abstains their pairs below.
    fn build_class_profiles(
        &mut self,
        class: super::CalibrationClass,
        window: (f64, f64),
    ) -> Result<HashMap<u32, Option<Profile>>, Error> {
        let mut profiles = HashMap::new();
        for glyph in self.context.glyphs {
            let own_class = calibration_class(glyph.codepoint, glyph.codepoint);
            if own_class != Some(class) && !mixed_case_admit(class, own_class) {
                continue;
            }
            if let Some(record) = self.records.get(&glyph.codepoint) {
                self.ensure_outline(glyph, record)?;
                profiles.insert(
                    glyph.codepoint,
                    profile(
                        &self.outlines[&glyph.codepoint].0,
                        window,
                        &mut self.budget,
                        self.settings,
                    )?,
                );
            }
        }
        Ok(profiles)
    }

    /// Prepare one glyph's fitted outline (and its Mono delivery cells) once
    /// per resolve, shared by every class that admits the glyph.
    fn ensure_outline(
        &mut self,
        glyph: &crate::Glyph,
        record: &ReferenceRecord,
    ) -> Result<(), Error> {
        if !self.outlines.contains_key(&glyph.codepoint) {
            self.outlines.insert(
                glyph.codepoint,
                self.budget.outline(&record.fitted_commands)?,
            );
            if self.mono {
                self.cells
                    .insert(glyph.codepoint, super::placement::cell_rows(glyph)?);
            }
        }
        Ok(())
    }

    /// One pair's class-scoped placement: pairs outside the class keep their
    /// seed; pairs in the class resolve against its target or keep the
    /// class's retention reason.
    fn place_class_pair(
        &mut self,
        key: (u32, u32),
        class: super::CalibrationClass,
        calibrated: Option<((f64, f64), f64)>,
        retention: &'static str,
        profiles: &HashMap<u32, Option<Profile>>,
        result: &mut super::PairAdjustments,
    ) -> Result<(), Error> {
        use super::PairDecision;
        if calibration_class(key.0, key.1) != Some(class) {
            return Ok(());
        }
        let Some((_, target)) = calibrated else {
            result.insert(key, PairDecision::RetainSource(retention));
            return Ok(());
        };
        let Some(a) = profiles.get(&key.0).and_then(Option::as_ref) else {
            result.insert(key, PairDecision::RetainSource("empty_geometry"));
            return Ok(());
        };
        let Some(b) = profiles.get(&key.1).and_then(Option::as_ref) else {
            result.insert(key, PairDecision::RetainSource("empty_geometry"));
            return Ok(());
        };
        result.insert(key, self.place_pair(key, a, b, target)?);
        Ok(())
    }

    /// One supported pair's full optical correction before signed pixel
    /// rounding and the existing feasibility bound.
    fn place_pair(
        &mut self,
        key: (u32, u32),
        a: &Profile,
        b: &Profile,
        target: f64,
    ) -> Result<super::PairDecision, Error> {
        use super::PairDecision;
        let Some(ideal) = pair_ideal(a, b, target)? else {
            return Ok(PairDecision::RetainSource("no_shared_ink_rows"));
        };
        let advance = self.admitted_advance(key)?;
        let optical_adjustment = finite(ideal - f64::from(advance) / 64.)?;
        self.admitted_saved_adjustment(key)?;
        let step = quantized_step(advance, optical_adjustment)?;
        let step = self.clamp_to_minimum(key, step)?;
        let adjustment = step
            .checked_mul(64)
            .and_then(|s| s.checked_sub(advance))
            .ok_or_else(|| fail("Hu/Hersch adjustment overflow"))?;
        Ok(PairDecision::Replace(adjustment))
    }

    /// Finalized advances must be whole pixels; the source layout contract
    /// accumulates integer pen steps.
    fn admitted_advance(&self, key: (u32, u32)) -> Result<i32, Error> {
        let advance = *self
            .context
            .advances_26_6
            .get(&key.0)
            .ok_or_else(|| fail("missing Hu/Hersch finalized advance"))?;
        if advance % 64 != 0 {
            return Err(fail("Hu/Hersch requires whole-pixel finalized advances"));
        }
        Ok(advance)
    }

    /// Finalized pair adjustments must be whole pixels as well.
    fn admitted_saved_adjustment(&self, key: (u32, u32)) -> Result<(), Error> {
        if self
            .context
            .pair_adjustments_26_6
            .get(&key)
            .copied()
            .unwrap_or(0)
            % 64
            != 0
        {
            return Err(fail(
                "Hu/Hersch requires whole-pixel finalized pair adjustments",
            ));
        }
        Ok(())
    }

    /// The Mono/Gray feasibility clamp: Mono forbids occupied-cell overlap,
    /// Gray uses the certified conservative bound on continuous fitted walls.
    fn clamp_to_minimum(&mut self, key: (u32, u32), step: i32) -> Result<i32, Error> {
        let minimum = if self.mono {
            super::placement::minimum(&self.cells[&key.0], &self.cells[&key.1])
        } else {
            self.outlines[&key.0]
                .minimum_with_budget(&self.outlines[&key.1], &mut self.budget.0)
                .map_err(|error| {
                    fail(format!(
                        "Hu/Hersch pair U+{:04X} U+{:04X}: {}",
                        key.0, key.1, error.0
                    ))
                })?
        };
        Ok(minimum.map_or(step, |bound| step.max(bound)))
    }
}

pub(super) fn resolve(
    context: &super::MethodContext<'_>,
    calibration: &[super::CalibrationCapture],
    settings: &HuHerschSettings,
) -> Result<super::PairAdjustments, Error> {
    settings.validate()?;
    if context.glyphs.len() > 1024 {
        return Err(fail("Hu/Hersch repertoire limit exceeded"));
    }
    Resolver::new(context, calibration, settings).run()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        mono_spacing::FontSpacingProperties, probe::FittedCommand as C, reference::RasterPolicy,
        Glyph,
    };
    use serde_json::Value;

    fn commands(value: &Value) -> Vec<C> {
        value
            .as_array()
            .unwrap()
            .iter()
            .map(|v| {
                let n = |key: &str| v[key].as_f64().unwrap() as f32;
                match v["op"].as_str().unwrap() {
                    "move_to" => C::MoveTo(n("x"), n("y")),
                    "line_to" => C::LineTo(n("x"), n("y")),
                    "quad_to" => C::QuadTo(n("x1"), n("y1"), n("x"), n("y")),
                    "curve_to" => C::CurveTo(n("x1"), n("y1"), n("x2"), n("y2"), n("x"), n("y")),
                    "close" => C::Close,
                    _ => panic!("unknown fixture command"),
                }
            })
            .collect()
    }

    fn record(value: &Value) -> ReferenceRecord {
        let bitmap = &value["bitmap"];
        ReferenceRecord {
            side_bearing_deltas_26_6: None,
            raster_policy: RasterPolicy::Coverage,
            mono_rasterizer: None,
            mono_raster: None,
            font_scan: None,
            diagonal_pairs: None,
            codepoint: value["codepoint"].as_u64().unwrap() as u32,
            glyph_id: value["codepoint"].as_u64().unwrap() as u32,
            selected_engine: String::new(),
            target: String::new(),
            smooth_mode: None,
            symmetric_rendering: None,
            preserve_linear_metrics: None,
            draw_pedantic: false,
            skrifa_version: String::new(),
            skrifa_registry_checksum: String::new(),
            zeno_version: String::new(),
            zeno_format: String::new(),
            output_bits: 1,
            mono_threshold: 128,
            gray_gamma: 1.,
            fitted_commands: commands(&value["produced_commands"]),
            source_commands: None,
            width_fitting: None,
            selective_fitting: None,
            diagonal_fitting: None,
            top_alignment: None,
            baseline_alignment: None,
            extremity_phase: None,
            coverage: vec![],
            coverage_sha256: String::new(),
            left: bitmap["left"].as_i64().unwrap() as i32,
            top: bitmap["top"].as_i64().unwrap() as i32,
            width: bitmap["width"].as_u64().unwrap() as u32,
            height: bitmap["height"].as_u64().unwrap() as u32,
            pixels: bitmap["pixels"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_u64().unwrap() as u8)
                .collect(),
            advance_26_6: (value["finalized_advance_px"].as_f64().unwrap() * 64.) as i32,
            hinted_has_overlaps: false,
            hinted_lsb: None,
            hinted_advance_width: None,
        }
    }

    #[test]
    fn independent_python_full_fitted_four_font_tables() {
        let fixture: Value =
            serde_json::from_str(include_str!("../../tests/hu_hersch/full-fitted.json")).unwrap();
        let empty = HashMap::new();
        let empty_pairs = HashMap::new();
        for case in fixture["cases"].as_array().unwrap() {
            let values = case["glyphs"].as_array().unwrap();
            let records: Vec<_> = values.iter().map(record).collect();
            let source_advances: HashMap<_, _> = values
                .iter()
                .map(|v| {
                    (
                        v["codepoint"].as_u64().unwrap() as u32,
                        (v["source_advance_px"].as_f64().unwrap() * 64.) as i32,
                    )
                })
                .collect();
            let source_pairs: HashMap<_, _> = case["source_pairs"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| {
                    (
                        (
                            v["left"].as_u64().unwrap() as u32,
                            v["right"].as_u64().unwrap() as u32,
                        ),
                        (v["adjustment_px"].as_f64().unwrap() * 64.) as i32,
                    )
                })
                .collect();
            let glyphs: Vec<_> = records
                .iter()
                .map(|r| Glyph {
                    codepoint: r.codepoint,
                    glyph_id: r.glyph_id,
                    advance_26_6: r.advance_26_6,
                    left: r.left,
                    top: r.top,
                    width: r.width,
                    height: r.height,
                    pixels: r.pixels.clone(),
                })
                .collect();
            let advances: HashMap<_, _> = glyphs
                .iter()
                .map(|g| (g.codepoint, g.advance_26_6))
                .collect();
            let classes = [
                (super::super::CalibrationClass::Lowercase, "lowercase"),
                (super::super::CalibrationClass::Uppercase, "uppercase"),
                (super::super::CalibrationClass::Digits, "digits"),
                (super::super::CalibrationClass::Mixed, "mixed"),
            ];
            let calibrations: Vec<_> = classes
                .iter()
                .map(|(class, _)| super::super::CalibrationCapture {
                    class: *class,
                    unavailable_reason: None,
                    records: records.clone(),
                    source_advances_26_6: source_advances.clone(),
                    source_pairs_26_6: source_pairs.clone(),
                })
                .collect();
            let mut targets = vec![];
            for ((class, name), capture) in classes.iter().zip(&calibrations) {
                let actual = calibrate(
                    capture,
                    true,
                    &mut Budget::default(),
                    &HuHerschSettings::default(),
                )
                .unwrap()
                .unwrap();
                let expected = case["classes"][*name]["target_px"].as_f64().unwrap();
                assert!(
                    (actual.1 - expected).abs() < 1e-10,
                    "{} {name} target {} vs {expected}",
                    case["family"],
                    actual.1
                );
                targets.push((*class, actual));
            }
            let mut context = super::super::MethodContext {
                glyphs: &glyphs,
                records: &records,
                source_commands: &empty,
                source_advances_26_6: &source_advances,
                source_pairs_26_6: &source_pairs,
                advances_26_6: &advances,
                pair_adjustments_26_6: &empty_pairs,
                output_bits: 1,
                units_per_em: case["units_per_em"].as_u64().unwrap() as u16,
                size_px: case["size_px"].as_f64().unwrap(),
                ascender_26_6: 0,
                properties: FontSpacingProperties {
                    monospace: false,
                    tabular_digits: false,
                },
                source_kerning: true,
            };
            let actual = resolve(&context, &calibrations, &HuHerschSettings::default()).unwrap();
            for pair in case["pairs"].as_array().unwrap() {
                let a = pair[0].as_u64().unwrap() as u32;
                let b = pair[1].as_u64().unwrap() as u32;
                let super::super::PairDecision::Replace(adjustment) = actual[&(a, b)] else {
                    panic!("reference pair unexpectedly retainedSource")
                };
                let step = (advances[&a] + adjustment) / 64;
                assert_eq!(
                    step,
                    pair[3].as_f64().unwrap() as i32,
                    "{} {a} {b}",
                    case["family"]
                );
            }
            // Non-default depth factors must propagate into both the shared
            // calibration target and candidate walls. Assert a general change
            // (target moves and at least one emitted step moves) rather than
            // preferred pixels for any reported pair.
            let deep = HuHerschSettings {
                aperture_depth_factor: 0.35,
                global_depth_factor: 0.4,
            };
            let mut target_moved = false;
            for (capture, (_, before)) in calibrations.iter().zip(&targets) {
                let after = calibrate(capture, true, &mut Budget::default(), &deep)
                    .unwrap()
                    .unwrap();
                target_moved |= (after.1 - before.1).abs() > 1e-9;
            }
            assert!(
                target_moved,
                "{} calibration target ignores depth factors",
                case["family"]
            );
            let moved = resolve(&context, &calibrations, &deep).unwrap();
            let full = resolve(&context, &calibrations, &HuHerschSettings::default()).unwrap();
            assert!(
                case["pairs"].as_array().unwrap().iter().any(|pair| {
                    let key = (
                        pair[0].as_u64().unwrap() as u32,
                        pair[1].as_u64().unwrap() as u32,
                    );
                    moved.get(&key) != full.get(&key)
                }),
                "{} placements ignore depth factors",
                case["family"]
            );
            // The retired `strength` blend is rejected at the schema boundary:
            // no saved value may silently load as new defaults.
            for rejected in [
                serde_json::json!({"method":"hu_hersch","strength":0.0}),
                serde_json::json!({"method":"hu_hersch","strength":0.35}),
                serde_json::json!({"method":"hu_hersch","strength":1.0}),
                serde_json::json!({"method":"hu_hersch","strength":null}),
                serde_json::json!({"method":"hu_hersch","strength":"0.35"}),
            ] {
                assert!(
                    serde_json::from_value::<super::super::KerningMethod>(rejected).is_err(),
                    "{} retired strength must not parse",
                    case["family"]
                );
            }
        }
    }

    #[test]
    fn sampled_bays_use_post_b_supports_and_do_not_expand_monotone_exteriors() {
        let ys: Vec<_> = (0..7).map(|i| i as f64 + 0.5).collect();
        let raw = vec![0., 0., 2., 0., 1., 0., 2.];
        let slope = slope_filter(&ys, &raw);
        assert_eq!(slope, vec![0., 0., 2., 1.5, 1., 1.5, 2.]);
        let filtered = aperture_filter(&ys, &slope, APERTURE_DEPTH_FACTOR_DEFAULT);
        assert!((filtered[4] - (2. - 0.21 * 3.)).abs() < 1e-14);
        assert_eq!(
            slope_filter(&ys, &[0., 1., 2., 3., 4., 5., 6.]),
            vec![0., 1., 2., 3., 4., 5., 6.]
        );
    }

    #[test]
    fn full_construction_keeps_lips_outside_body_and_has_bounded_work() {
        let outline = Outline::new(&[
            C::MoveTo(-1., 0.),
            C::LineTo(3., 0.),
            C::QuadTo(-1., 2., 3., 4.),
            C::LineTo(-1., 4.),
            C::Close,
        ])
        .unwrap();
        let settings = HuHerschSettings::default();
        let p = profile(&outline, (0., 3.), &mut Budget::default(), &settings)
            .unwrap()
            .unwrap();
        // The missing upper lip is retained before construction, not replaced
        // by a spurious body-window endpoint. Published global D still uses H=3.
        assert!(p.right[p.right.len() - 1] > 2.0);
        assert!(profile(&outline, (0., 200.), &mut Budget::default(), &settings).is_err());
        let moved = Outline::new(&[
            C::MoveTo(4., 0.),
            C::LineTo(8., 0.),
            C::QuadTo(4., 2., 8., 4.),
            C::LineTo(4., 4.),
            C::Close,
        ])
        .unwrap();
        let q = profile(&moved, (0., 3.), &mut Budget::default(), &settings)
            .unwrap()
            .unwrap();
        assert!((q.mean_left - p.mean_left - 5.).abs() < 1e-12);
        assert!((q.mean_right - p.mean_right - 5.).abs() < 1e-12);
    }

    #[test]
    fn unicode_classes_are_independent_of_ascii_calibration_repertoire() {
        use super::super::CalibrationClass::*;
        assert_eq!(calibration_class('é' as u32, 'a' as u32), Some(Lowercase));
        assert_eq!(calibration_class('É' as u32, 'a' as u32), Some(Mixed));
        assert_eq!(calibration_class('Ω' as u32, 'a' as u32), None);
        assert_eq!(calibration_class('١' as u32, '٢' as u32), None);
        assert_eq!(calibration_class('1' as u32, '2' as u32), Some(Digits));
    }

    #[test]
    fn degenerate_windows_and_empty_outlines_cannot_profile() {
        let outline = Outline::new(&[
            C::MoveTo(0., 0.),
            C::LineTo(4., 0.),
            C::LineTo(4., 4.),
            C::LineTo(0., 4.),
            C::Close,
        ])
        .unwrap();
        let settings = HuHerschSettings::default();
        assert!(
            profile(&outline, (5., 5.), &mut Budget::default(), &settings).is_err(),
            "a zero-height window has no body samples"
        );
        assert!(
            profile(&outline, (5., 0.), &mut Budget::default(), &settings).is_err(),
            "an inverted window has no body samples"
        );
        let empty = Outline::new(&[]).unwrap();
        assert!(
            profile(&empty, (0., 3.), &mut Budget::default(), &settings)
                .unwrap()
                .is_none(),
            "empty geometry abstains the profile"
        );
    }

    #[test]
    fn pairs_without_shared_ink_rows_abstain_before_rounding() {
        let walls = |occupied: Vec<bool>| Profile {
            left: vec![0., 0.],
            right: vec![0., 0.],
            occupied,
            mean_left: 0.,
            mean_right: 0.,
        };
        let left = walls(vec![true, false]);
        let disjoint = walls(vec![false, true]);
        assert_eq!(pair_ideal(&left, &disjoint, 3.0).unwrap(), None);
        let shared = walls(vec![true, false]);
        assert_eq!(pair_ideal(&left, &shared, 3.0).unwrap(), Some(3.0));
    }

    #[test]
    fn optical_steps_hold_the_layout_range_inclusively() {
        let bound = f64::from(i32::MAX / 64);
        assert_eq!(quantized_step(0, bound).unwrap(), i32::MAX / 64);
        assert_eq!(quantized_step(0, -bound).unwrap(), -(i32::MAX / 64));
        assert!(quantized_step(0, bound - 1.).is_ok());
        assert!(quantized_step(0, bound + 1.).is_err());
        assert!(quantized_step(0, -bound - 1.).is_err());
    }

    #[test]
    fn unavailable_calibration_abstains_the_target() {
        let capture = super::super::CalibrationCapture {
            class: super::super::CalibrationClass::Lowercase,
            unavailable_reason: Some("test fixture is unavailable"),
            records: Vec::new(),
            source_advances_26_6: HashMap::new(),
            source_pairs_26_6: HashMap::new(),
        };
        assert!(calibrate(
            &capture,
            true,
            &mut Budget::default(),
            &HuHerschSettings::default()
        )
        .unwrap()
        .is_none());
    }
}
