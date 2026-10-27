//! FreeType's integer-positioning correction for fitted phantom-point deltas.
//! https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_glyphslotrec
//! The asymmetric limits implement the documented 26.6 rounding boundary;
//! they are source constants, not optical thresholds tuned to a pair.
//!
//! This module also owns the general source/ink geometry retained for the
//! explicit-tracking minimum-clearance guard; it is not a placement policy.

use crate::{
    fail, fixed, probe::FittedCommand, reference::ReferenceReport, Config, Error, GeneratedFont,
};
use sha2::{Digest, Sha256};
use skrifa::MetadataProvider as RegistryMetadataProvider;
use skrifa_baseline::{instance::Size, raw::TableProvider, MetadataProvider};
use std::collections::BTreeMap;

pub fn bearing_adjustment(previous_rsb: i32, current_lsb: i32) -> i32 {
    let difference = i64::from(previous_rsb) - i64::from(current_lsb);
    if difference > 32 {
        -64
    } else if difference < -31 {
        64
    } else {
        0
    }
}

/// Font-level spacing properties determined from the source font at the
/// exact axes, independently of the selected repertoire.
///
/// Fixed pitch comes from the source `post` table. Tabular digits use the
/// actually drawn (coordinate-selected) glyphs' variation-aware advances:
/// all ten digits must be present with equal advances. A cmap-absent digit
/// keeps the unknown-digits behavior (not tabular); resolution failures
/// for present digits stay explicit errors.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct FontSpacingProperties {
    pub monospace: bool,
    pub tabular_digits: bool,
}

pub fn font_spacing_properties(
    data: &[u8],
    config: &Config,
) -> Result<FontSpacingProperties, Error> {
    let font = crate::open_font(data)?;
    let location = font.axes().location(
        config
            .axes
            .iter()
            .map(|(tag, value)| (tag.as_str(), *value)),
    );
    let metrics = font.glyph_metrics(Size::new(config.size_px), &location);
    let charmap = font.charmap();
    let digits: Option<Vec<f32>> =
        if ('0'..='9').all(|digit| charmap.map(digit).is_some_and(|g| g.to_u32() != 0)) {
            let digit_chars: Vec<char> = ('0'..='9').collect();
            let resolved =
                crate::spacing::resolve_scalars(data, &config.axes, config.kerning, &digit_chars)?;
            resolved
                .iter()
                .map(|scalar| metrics.advance_width(skrifa::GlyphId::new(scalar.glyph_id)))
                .collect()
        } else {
            None
        };
    Ok(FontSpacingProperties {
        monospace: font.post().is_ok_and(|table| table.is_fixed_pitch() != 0),
        tabular_digits: digits.is_some_and(|advances| {
            advances[0].is_finite() && advances.iter().all(|value| *value == advances[0])
        }),
    })
}

/// General geometry retained for the explicit-tracking minimum-clearance
/// guard. This is not a placement policy: neutral layout never consults it.
///
/// Source foundation: the FreeType advance/bearing model plus pair kerning.
/// For glyphs `L` (left) and `R` (right) with source kerning `K`, all in 26.6
/// except the outline extents in pixels, the signed source white gap is
/// `G = src_adv(L)/64 + K/64 + src_min_x(R) - src_max_x(L)`. The guard only
/// asks whether that gap, rounded with `floor(G + 0.5)`, is at least one
/// blank column; negative values (intended source overhangs) are preserved
/// and never trigger a floor. Fixed-pitch fonts, tabular digit pairs,
/// spaces and empty glyphs return no target and bypass the floor.
pub struct TrackingGuard {
    source_min_x: BTreeMap<u32, f64>,
    source_max_x: BTreeMap<u32, f64>,
    source_advance: BTreeMap<u32, i32>,
    ink_min_col: BTreeMap<u32, i32>,
    ink_max_col: BTreeMap<u32, i32>,
    monospace: bool,
    tabular_digits: bool,
    usable: bool,
    source_sha256: String,
}

impl TrackingGuard {
    /// Build guard extents from an independent unhinted source report and
    /// the delivered report at the same size, axes and repertoire. Never
    /// fails: unusable or mismatched input yields a guard that answers
    /// `None` for every pair, leaving tracking without a floor.
    pub fn build(source: &ReferenceReport, candidate: &ReferenceReport) -> Self {
        let usable = source.source_sha256 == candidate.source_sha256
            && source.size_px == candidate.size_px
            && source.axes == candidate.axes;
        let mut guard = TrackingGuard {
            source_min_x: BTreeMap::new(),
            source_max_x: BTreeMap::new(),
            source_advance: BTreeMap::new(),
            ink_min_col: BTreeMap::new(),
            ink_max_col: BTreeMap::new(),
            monospace: false,
            tabular_digits: false,
            usable,
            source_sha256: source.source_sha256.clone(),
        };
        if !usable {
            return guard;
        }
        for record in &source.records {
            if let Some((min_x, max_x)) = tight_source_x(&record.fitted_commands) {
                guard.source_min_x.insert(record.codepoint, min_x);
                guard.source_max_x.insert(record.codepoint, max_x);
            }
            guard
                .source_advance
                .insert(record.codepoint, record.advance_26_6);
        }
        for record in &candidate.records {
            if let Some((min_col, max_col)) =
                ink_columns(&record.pixels, record.left, record.width, record.height)
            {
                guard.ink_min_col.insert(record.codepoint, min_col);
                guard.ink_max_col.insert(record.codepoint, max_col);
            }
        }
        guard
    }

    /// Add source font properties independently of the selected repertoire.
    pub fn from_font(
        data: &[u8],
        config: &Config,
        source: &ReferenceReport,
        candidate: &ReferenceReport,
    ) -> Result<Self, Error> {
        let properties = font_spacing_properties(data, config)?;
        let mut guard = Self::build(source, candidate);
        guard.monospace = properties.monospace;
        guard.tabular_digits = properties.tabular_digits;
        Ok(guard)
    }

    /// Guard from unhinted source geometry only, matching the former
    /// unhinted registry reference capture exactly: registry Skrifa
    /// outlines are drawn to commands and their tight x-extents taken,
    /// source advances are registry `GlyphMetrics::advance_width`
    /// rounded with the configured fixed rule, and no coverage,
    /// thresholding or raster is produced. Ink columns come from the
    /// actual delivered bitmaps in `output`.
    pub(crate) fn for_output_from_geometry(
        data: &[u8],
        output: &GeneratedFont,
    ) -> Result<Self, Error> {
        let properties = font_spacing_properties(data, &output.config)?;
        if !matches!(data.get(..4), Some(b"\0\x01\0\0" | b"OTTO")) {
            return Err(fail("supported input is a single sfnt TTF/OTF outline font; collections, WOFF and bitmap formats require conversion"));
        }
        let font = skrifa::FontRef::new(data).map_err(|e| fail(format!("invalid font: {e}")))?;
        for tag in [b"COLR", b"SVG ", b"CBDT", b"sbix"] {
            if font.table_data(skrifa::Tag::new(tag)).is_some() {
                return Err(fail("color fonts require a color output adapter"));
            }
        }
        if ![b"glyf", b"CFF ", b"CFF2"]
            .iter()
            .any(|t| font.table_data(skrifa::Tag::new(t)).is_some())
        {
            return Err(fail("font has no supported glyf/CFF/CFF2 outlines"));
        }
        for (tag, value) in &output.config.axes {
            if tag.len() != 4 || !tag.is_ascii() {
                return Err(fail(format!("axis tag {tag:?} must be four ASCII bytes")));
            }
            let axis = font
                .axes()
                .iter()
                .find(|a| a.tag().to_string() == *tag)
                .ok_or_else(|| fail(format!("unsupported axis {tag}")))?;
            if !value.is_finite() || *value < axis.min_value() || *value > axis.max_value() {
                return Err(fail(format!(
                    "axis {tag} must be within {}..={}",
                    axis.min_value(),
                    axis.max_value()
                )));
            }
        }
        let location = font.axes().location(
            output
                .config
                .axes
                .iter()
                .map(|(tag, value)| (tag.as_str(), *value)),
        );
        let size = skrifa::instance::Size::new(output.config.size_px);
        let outlines = font.outline_glyphs();
        let advances = font.glyph_metrics(size, &location);
        let mut guard = TrackingGuard {
            source_min_x: BTreeMap::new(),
            source_max_x: BTreeMap::new(),
            source_advance: BTreeMap::new(),
            ink_min_col: BTreeMap::new(),
            ink_max_col: BTreeMap::new(),
            monospace: properties.monospace,
            tabular_digits: properties.tabular_digits,
            usable: true,
            source_sha256: format!("{:x}", Sha256::digest(data)),
        };
        for glyph in &output.glyphs {
            let gid = skrifa::GlyphId::new(glyph.glyph_id);
            let outline = outlines
                .get(gid)
                .ok_or_else(|| fail(format!("missing outline U+{:04X}", glyph.codepoint)))?;
            let mut pen = crate::probe::FittedPen::default();
            #[cfg(test)]
            crate::source::raster_counter::record_source_geometry(1);
            outline
                .draw(
                    skrifa::outline::DrawSettings::unhinted(size, &location),
                    &mut pen,
                )
                .map_err(|e| fail(format!("outline U+{:04X}: {e}", glyph.codepoint)))?;
            if let Some((min_x, max_x)) = tight_source_x(&pen.into_commands()) {
                guard.source_min_x.insert(glyph.codepoint, min_x);
                guard.source_max_x.insert(glyph.codepoint, max_x);
            }
            let advance = advances
                .advance_width(gid)
                .ok_or_else(|| fail(format!("missing advance U+{:04X}", glyph.codepoint)))?;
            guard.source_advance.insert(
                glyph.codepoint,
                fixed(advance, output.config.metric_rounding),
            );
        }
        for glyph in &output.glyphs {
            if let Some((lo, hi)) =
                ink_columns(&glyph.pixels, glyph.left, glyph.width, glyph.height)
            {
                guard.ink_min_col.insert(glyph.codepoint, lo);
                guard.ink_max_col.insert(glyph.codepoint, hi);
            }
        }
        Ok(guard)
    }

    /// Explicit USER POLICY: live Mono spacing must leave at least one blank
    /// column for pairs whose rounded source target is positive. This floor
    /// implements the user's requested restriction, not an optical threshold
    /// inferred from a witness. Hersch's grid-placement model supplies the
    /// coordinate foundation; the minimum is a project/user constraint.
    ///
    /// Inspect the delivered origins, including their rounding phase, so
    /// fractional tracking cannot silently close a normally separated pair.
    /// The source target itself is unchanged. Signed source overlap, fixed
    /// pitch, tabular digits, empty glyphs and spaces keep their contracts.
    /// Returns a whole-pixel correction; common whole-pixel translation is
    /// invariant. Measurement and placement must call this same function.
    pub(crate) fn minimum_tracking_correction(
        &self,
        previous: u32,
        current: u32,
        kern_26_6: i32,
        previous_origin: i64,
        proposed_origin: i64,
    ) -> i64 {
        if !self
            .source_target_gap(previous, current, kern_26_6)
            .is_some_and(|gap| gap >= 1)
        {
            return 0;
        }
        let (Some(&left_max), Some(&right_min)) = (
            self.ink_max_col.get(&previous),
            self.ink_min_col.get(&current),
        ) else {
            return 0;
        };
        let gap = (proposed_origin + 32).div_euclid(64) - (previous_origin + 32).div_euclid(64)
            + i64::from(right_min)
            - i64::from(left_max)
            - 1;
        (1 - gap).max(0) * 64
    }

    /// Provenance of the source capture this guard was derived from.
    pub fn source_sha256(&self) -> &str {
        &self.source_sha256
    }

    /// Rounded source white-gap target in whole pixels, or `None` when the
    /// pair is not geometrically supported. Signed: negative source
    /// overhangs stay negative. Internal to the tracking guard.
    fn source_target_gap(&self, previous: u32, current: u32, kern_26_6: i32) -> Option<i64> {
        if !self.usable || self.monospace {
            return None;
        }
        if previous == ' ' as u32 || current == ' ' as u32 {
            return None;
        }
        if self.tabular_digits && is_ascii_digit(previous) && is_ascii_digit(current) {
            return None;
        }
        let (&min_right, &max_left, &advance_left) = (
            self.source_min_x.get(&current)?,
            self.source_max_x.get(&previous)?,
            self.source_advance.get(&previous)?,
        );
        let gap =
            f64::from(advance_left) / 64.0 + f64::from(kern_26_6) / 64.0 + f64::from(min_right)
                - f64::from(max_left);
        Some((gap + 0.5).floor() as i64)
    }
}

fn is_ascii_digit(codepoint: u32) -> bool {
    (u32::from(b'0')..=u32::from(b'9')).contains(&codepoint)
}

/// Delivered fitted ink columns relative to the glyph origin, from the
/// candidate bitmap box. Empty glyphs (no nonzero texels) return `None` so
/// pairing falls back instead of squeezing space from empty extents.
fn ink_columns(pixels: &[u8], left: i32, width: u32, height: u32) -> Option<(i32, i32)> {
    if width == 0
        || height == 0
        || u64::from(width) * u64::from(height) != pixels.len() as u64
        || i64::from(left) + i64::from(width) - 1 > i64::from(i32::MAX)
    {
        return None;
    }
    let mut min_col: Option<i32> = None;
    let mut max_col: Option<i32> = None;
    for y in 0..height {
        for x in 0..width {
            if pixels[(y as usize) * (width as usize) + (x as usize)] == 0 {
                continue;
            }
            let column = left + x as i32;
            min_col = Some(min_col.map_or(column, |best| best.min(column)));
            max_col = Some(max_col.map_or(column, |best| best.max(column)));
        }
    }
    min_col.zip(max_col)
}

/// True tight source x-extrema in pixels from fitted outline commands:
/// actual endpoints plus quadratic/cubic derivative extrema, never the
/// control box. Returns `None` for empty outlines. Common translations of
/// the whole command stream shift both extrema equally.
pub fn tight_source_x(commands: &[FittedCommand]) -> Option<(f64, f64)> {
    let mut extent: Option<(f64, f64)> = None;
    let mut observe = |x: f64| -> Option<()> {
        if !x.is_finite() {
            return None;
        }
        extent = Some(extent.map_or((x, x), |(min, max)| (min.min(x), max.max(x))));
        Some(())
    };
    let mut current = 0.0;
    let mut start = 0.0;
    for command in commands {
        match *command {
            FittedCommand::MoveTo(x, _) => {
                current = f64::from(x);
                start = current;
            }
            FittedCommand::LineTo(x, _) => {
                observe(current)?;
                current = f64::from(x);
                observe(current)?;
            }
            FittedCommand::QuadTo(x1, _, x, _) => {
                let (p0, p1, p2) = (current, f64::from(x1), f64::from(x));
                if !p1.is_finite() {
                    return None;
                }
                observe(p0)?;
                observe(p2)?;
                let denominator = p0 - 2.0 * p1 + p2;
                if denominator != 0.0 {
                    let t = (p0 - p1) / denominator;
                    if t > 0.0 && t < 1.0 {
                        observe((1.0 - t).powi(2) * p0 + 2.0 * (1.0 - t) * t * p1 + t * t * p2)?;
                    }
                }
                current = p2;
            }
            FittedCommand::CurveTo(x1, _, x2, _, x, _) => {
                let (p0, p1, p2, p3) = (current, f64::from(x1), f64::from(x2), f64::from(x));
                if !p1.is_finite() || !p2.is_finite() {
                    return None;
                }
                observe(p0)?;
                observe(p3)?;
                let a = 3.0 * (-p0 + 3.0 * p1 - 3.0 * p2 + p3);
                let b = 6.0 * (p0 - 2.0 * p1 + p2);
                let c = 3.0 * (p1 - p0);
                let mut roots = [f64::NAN; 2];
                // Algebraic degree reduction, with no coordinate-scale threshold.
                // Stable quadratic roots avoid cancellation near a linear derivative.
                if a == 0.0 {
                    if b != 0.0 {
                        roots[0] = -c / b;
                    }
                } else {
                    let discriminant = b * b - 4.0 * a * c;
                    if discriminant >= 0.0 {
                        let q = -0.5 * (b + discriminant.sqrt().copysign(b));
                        if q == 0.0 {
                            roots[0] = -b / (2.0 * a);
                        } else {
                            roots = [q / a, c / q];
                        }
                    }
                }
                for t in roots {
                    if t > 0.0 && t < 1.0 {
                        let u = 1.0 - t;
                        observe(
                            u.powi(3) * p0
                                + 3.0 * u * u * t * p1
                                + 3.0 * u * t * t * p2
                                + t.powi(3) * p3,
                        )?;
                    }
                }
                current = p3;
            }
            FittedCommand::Close => current = start,
        }
    }
    extent
}

#[cfg(test)]
mod tests {
    use super::{bearing_adjustment, ink_columns, tight_source_x, TrackingGuard};
    use crate::{
        probe::FittedCommand,
        reference::{AdvancePolicy, RasterPolicy, ReferenceRecord, ReferenceReport},
    };
    use std::collections::BTreeMap;

    #[test]
    fn documented_boundary_and_common_translation_are_preserved() {
        for (difference, expected) in [(-32, 64), (-31, 0), (0, 0), (32, 0), (33, -64)] {
            for translation in [-500, -1, 0, 7, 500] {
                assert_eq!(
                    bearing_adjustment(translation + difference, translation),
                    expected
                );
            }
        }
        assert_eq!(bearing_adjustment(i32::MAX, i32::MIN), -64);
        assert_eq!(bearing_adjustment(i32::MIN, i32::MAX), 64);
    }

    #[test]
    fn rectangle_extents_follow_endpoints() {
        let commands = vec![
            FittedCommand::MoveTo(1.0, 0.0),
            FittedCommand::LineTo(5.0, 0.0),
            FittedCommand::LineTo(5.0, 9.0),
            FittedCommand::LineTo(1.0, 9.0),
            FittedCommand::Close,
        ];
        assert_eq!(tight_source_x(&commands), Some((1.0, 5.0)));
    }

    #[test]
    fn empty_and_bare_moves_have_no_extents() {
        assert_eq!(tight_source_x(&[]), None);
        assert_eq!(
            tight_source_x(&[FittedCommand::MoveTo(2.0, 3.0), FittedCommand::Close]),
            None
        );
        assert_eq!(ink_columns(&[], 0, 0, 0), None);
        assert_eq!(ink_columns(&[0, 0, 0, 0], 3, 2, 2), None);
    }

    #[test]
    fn quad_interior_extremum_beats_endpoints_but_not_controls() {
        // Arch from x=0 to x=4 with the control at x=6: the interior extremum
        // is t = (0-6)/(0-12+4) = 0.75, x = 0.375*6 + 0.5625*4 = 4.5. The
        // control value 6 itself must not leak into the tight extent.
        let commands = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::QuadTo(6.0, 0.0, 4.0, 8.0),
        ];
        let (min_x, max_x) = tight_source_x(&commands).unwrap();
        assert_eq!(min_x, 0.0);
        assert!((max_x - 4.5).abs() < 1e-5, "unexpected {max_x}");
    }

    #[test]
    fn cubic_interior_extremum_is_observed() {
        // Bump from x=0 back to x=0 through controls at x=4: interior peaks
        // at t=0.5 with x = 12*0.5*0.5 = 3, past both endpoints.
        let commands = vec![
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::CurveTo(4.0, 0.0, 4.0, 8.0, 0.0, 8.0),
        ];
        let (min_x, max_x) = tight_source_x(&commands).unwrap();
        assert_eq!(min_x, 0.0);
        assert!((max_x - 3.0).abs() < 1e-5, "unexpected {max_x}");
    }

    #[test]
    fn extrema_follow_scaled_geometry_and_ignore_empty_contours() {
        for scale in [2.0_f32.powi(-20), 1.0, 2.0_f32.powi(20)] {
            for translation in [0.0, 11.5] {
                let x = |value: f32| (value + translation) * scale;
                let cubic = [
                    FittedCommand::MoveTo(x(1000.0), 0.0),
                    FittedCommand::Close,
                    FittedCommand::MoveTo(x(0.0), 0.0),
                    FittedCommand::CurveTo(x(4.0), 0.0, x(4.0), 8.0, x(0.0), 8.0),
                ];
                let (min, max) = tight_source_x(&cubic).unwrap();
                assert!((min / f64::from(scale) - f64::from(translation)).abs() < 1e-12);
                assert!((max / f64::from(scale) - f64::from(translation) - 3.0).abs() < 1e-12);
            }
        }
        assert_eq!(ink_columns(&[1], 0, 2, 2), None);
        assert_eq!(ink_columns(&[1, 1], i32::MAX, 2, 1), None);
    }

    #[test]
    fn closed_contours_restore_their_start_for_later_segments() {
        let shape = [
            FittedCommand::MoveTo(0.0, 0.0),
            FittedCommand::LineTo(2.0, 0.0),
            FittedCommand::Close,
            FittedCommand::QuadTo(4.0, 1.0, 0.0, 2.0),
        ];
        assert_eq!(tight_source_x(&shape), Some((0.0, 2.0)));
    }

    #[test]
    fn common_translation_shifts_both_extrema() {
        let base = vec![
            FittedCommand::MoveTo(1.0, 0.0),
            FittedCommand::QuadTo(6.0, 1.0, 4.0, 8.0),
            FittedCommand::CurveTo(7.0, 2.0, 0.0, 3.0, 3.0, 9.0),
        ];
        let shifted: Vec<FittedCommand> = base
            .iter()
            .map(|command| match *command {
                FittedCommand::MoveTo(x, y) => FittedCommand::MoveTo(x + 11.5, y),
                FittedCommand::LineTo(x, y) => FittedCommand::LineTo(x + 11.5, y),
                FittedCommand::QuadTo(x1, y1, x, y) => {
                    FittedCommand::QuadTo(x1 + 11.5, y1, x + 11.5, y)
                }
                FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                    FittedCommand::CurveTo(x1 + 11.5, y1, x2 + 11.5, y2, x + 11.5, y)
                }
                FittedCommand::Close => FittedCommand::Close,
            })
            .collect();
        let (min_base, max_base) = tight_source_x(&base).unwrap();
        let (min_moved, max_moved) = tight_source_x(&shifted).unwrap();
        assert!((min_moved - min_base - 11.5).abs() < 1e-4);
        assert!((max_moved - max_base - 11.5).abs() < 1e-4);
    }

    fn record(
        codepoint: u32,
        advance_26_6: i32,
        commands: Vec<FittedCommand>,
        left: i32,
        pixels: Vec<u8>,
        width: u32,
        height: u32,
    ) -> ReferenceRecord {
        ReferenceRecord {
            side_bearing_deltas_26_6: None,
            mono_rasterizer: None,
            mono_raster: None,
            font_scan: None,
            raster_policy: RasterPolicy::Coverage,
            diagonal_pairs: None,
            codepoint,
            glyph_id: codepoint,
            selected_engine: String::from("none"),
            target: String::from("mono"),
            smooth_mode: None,
            symmetric_rendering: None,
            preserve_linear_metrics: None,
            draw_pedantic: false,
            skrifa_version: String::new(),
            skrifa_registry_checksum: String::new(),
            zeno_version: String::new(),
            zeno_format: String::from("alpha"),
            output_bits: 1,
            mono_threshold: 128,
            gray_gamma: 1.0,
            source_commands: None,
            width_fitting: None,
            selective_fitting: None,
            top_alignment: None,
            diagonal_fitting: None,
            fitted_commands: commands,
            coverage: Vec::new(),
            coverage_sha256: String::new(),
            left,
            top: 0,
            width,
            height,
            pixels,
            advance_26_6,
            hinted_has_overlaps: false,
            hinted_lsb: None,
            hinted_advance_width: None,
        }
    }

    fn reports(
        pairs: Vec<(u32, i32, Vec<FittedCommand>, i32, Vec<u8>, u32, u32)>,
    ) -> ReferenceReport {
        ReferenceReport {
            advance_policy: AdvancePolicy::Linear,
            source_sha256: String::from("00"),
            size_px: 14.0,
            axes: BTreeMap::new(),
            profile: String::from("mono_1bit"),
            extensions: String::from("none"),
            hinting_requested: String::from("none"),
            target: String::from("mono"),
            smooth_mode: None,
            symmetric_rendering: None,
            preserve_linear_metrics: None,
            draw_pedantic: false,
            implementation: String::from("upstream"),
            fork: false,
            skrifa_version: String::new(),
            skrifa_registry_checksum: String::new(),
            zeno_version: String::new(),
            dependency_lock_sha256: String::new(),
            metrics: crate::FontMetrics {
                ascent_26_6: 0,
                descent_26_6: 0,
                line_gap_26_6: 0,
            },
            missing_codepoints: Vec::new(),
            records: pairs
                .into_iter()
                .map(|(cp, adv, commands, left, pixels, w, h)| {
                    record(cp, adv, commands, left, pixels, w, h)
                })
                .collect(),
        }
    }

    fn rect_commands(min_x: f32, max_x: f32) -> Vec<FittedCommand> {
        vec![
            FittedCommand::MoveTo(min_x, 0.0),
            FittedCommand::LineTo(max_x, 0.0),
            FittedCommand::LineTo(max_x, 8.0),
            FittedCommand::LineTo(min_x, 8.0),
            FittedCommand::Close,
        ]
    }

    #[test]
    fn explicit_minimum_preserves_phase_translation_and_signed_source_intent() {
        let source = reports(vec![
            (65, 4 * 64, rect_commands(0.0, 2.0), 0, vec![1, 1], 2, 1),
            (66, 4 * 64, rect_commands(1.0, 3.0), 1, vec![1, 1], 2, 1),
        ]);
        let mut spacing = TrackingGuard::build(&source, &source);
        for translation in [-17, 0, 23] {
            for phase in [-32, -1, 0, 31, 32, 63] {
                let left = translation * 64 + phase;
                // Ink columns [0,1] and [1,2] give gap = step - 1.
                for (step, expected) in [(0, 128), (64, 64), (128, 0), (192, 0)] {
                    assert_eq!(
                        spacing.minimum_tracking_correction(65, 66, 0, left, left + step),
                        expected
                    );
                }
                // Neutral source G=3. Kerning may intentionally make it
                // zero or negative: the user floor must not reinterpret it.
                for kern in [-3 * 64, -4 * 64] {
                    assert_eq!(
                        spacing.minimum_tracking_correction(65, 66, kern, left, left),
                        0
                    );
                }
            }
        }
        spacing.monospace = true;
        assert_eq!(spacing.minimum_tracking_correction(65, 66, 0, 0, 0), 0);
    }

    #[test]
    fn signed_gap_rounding_and_overhang_are_preserved() {
        // Left source stem [0,2] with advance 6px, right stem [1,3]:
        // G = 6 + 1 - 2 = 5? No: G = adv + min_right - max_left = 6+1-2 = 5.
        // Ink: left cols [0,1] (left=0, two texels), right cols [4,5]
        // (left=4): desired = 1 + 1 - 4 + 5 = 3; extra = 3*64 - (6*64 + 0).
        let source = reports(vec![
            (
                u32::from(b'A'),
                6 * 64,
                rect_commands(0.0, 2.0),
                0,
                vec![1, 1],
                2,
                1,
            ),
            (
                u32::from(b'B'),
                5 * 64,
                rect_commands(1.0, 3.0),
                0,
                vec![1, 1],
                2,
                1,
            ),
        ]);
        let candidate = reports(vec![
            (u32::from(b'A'), 6 * 64, vec![], 0, vec![1, 1], 2, 1),
            (u32::from(b'B'), 5 * 64, vec![], 4, vec![1, 1], 2, 1),
        ]);
        let spacing = TrackingGuard::build(&source, &candidate);
        assert_eq!(
            spacing.source_target_gap(u32::from(b'A'), u32::from(b'B'), 0),
            Some(5)
        );
        // Negative source gap (overlapping extents) stays negative: no clamping.
        let over = reports(vec![
            (
                u32::from(b'A'),
                2 * 64,
                rect_commands(0.0, 4.0),
                0,
                vec![1],
                1,
                1,
            ),
            (
                u32::from(b'B'),
                5 * 64,
                rect_commands(1.0, 3.0),
                0,
                vec![1],
                1,
                1,
            ),
        ]);
        let spacing = TrackingGuard::build(&over, &candidate);
        // G = 2 + 1 - 4 = -1.
        assert_eq!(
            spacing.source_target_gap(u32::from(b'A'), u32::from(b'B'), 0),
            Some(-1)
        );
    }

    #[test]
    fn empty_space_and_unknown_pairs_have_no_guard_target() {
        let source = reports(vec![
            (
                u32::from(b'A'),
                6 * 64,
                rect_commands(0.0, 2.0),
                0,
                vec![1, 1],
                2,
                1,
            ),
            (u32::from(b' '), 4 * 64, vec![], 0, vec![], 0, 0),
        ]);
        let candidate = reports(vec![
            (u32::from(b'A'), 6 * 64, vec![], 0, vec![1, 1], 2, 1),
            (u32::from(b' '), 4 * 64, vec![], 0, vec![], 0, 0),
        ]);
        let spacing = TrackingGuard::build(&source, &candidate);
        assert_eq!(
            spacing.source_target_gap(u32::from(b'A'), u32::from(b' '), 0),
            None
        );
        assert_eq!(
            spacing.source_target_gap(u32::from(b' '), u32::from(b'A'), 0),
            None
        );
        assert_eq!(
            spacing.source_target_gap(u32::from(b'A'), u32::from(b'Z'), 0),
            None
        );
    }

    #[test]
    fn monospace_and_tabular_digit_runs_have_no_guard_target() {
        let source = reports(vec![
            (
                u32::from(b'A'),
                8 * 64,
                rect_commands(0.0, 2.0),
                0,
                vec![1],
                1,
                1,
            ),
            (
                u32::from(b'B'),
                8 * 64,
                rect_commands(1.0, 3.0),
                0,
                vec![1],
                1,
                1,
            ),
        ]);
        let candidate = reports(vec![
            (u32::from(b'A'), 8 * 64, vec![], 0, vec![1], 1, 1),
            (u32::from(b'B'), 8 * 64, vec![], 5, vec![1], 1, 1),
        ]);
        let mut spacing = TrackingGuard::build(&source, &candidate);
        spacing.monospace = true;
        assert_eq!(
            spacing.source_target_gap(u32::from(b'A'), u32::from(b'B'), 0),
            None
        );
        let mut entries = Vec::new();
        for digit in b'0'..=b'9' {
            entries.push((
                u32::from(digit),
                7 * 64,
                rect_commands(1.0, 5.0),
                1,
                vec![1, 1],
                2,
                1,
            ));
        }
        entries.push((
            u32::from(b'A'),
            6 * 64,
            rect_commands(0.0, 2.0),
            0,
            vec![1],
            1,
            1,
        ));
        entries.push((
            u32::from(b'B'),
            9 * 64,
            rect_commands(1.0, 3.0),
            0,
            vec![1],
            1,
            1,
        ));
        let source = reports(entries.clone());
        let candidate = reports(entries);
        let mut spacing = TrackingGuard::build(&source, &candidate);
        spacing.tabular_digits = true;
        assert_eq!(
            spacing.source_target_gap(u32::from(b'3'), u32::from(b'4'), 0),
            None
        );
        assert!(spacing
            .source_target_gap(u32::from(b'A'), u32::from(b'B'), 0)
            .is_some());
    }

    #[test]
    fn geometry_guard_matches_unhinted_registry_reference_at_variation_and_pixel_rounding() {
        use crate::{
            generate,
            reference::{reference, ReferenceRequest},
            Config, Hinting, MetricRounding,
        };
        use std::path::Path;
        let data =
            std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/RobotoFlex.ttf"))
                .unwrap();
        let mut axes = BTreeMap::new();
        axes.insert("opsz".into(), 14.0);
        axes.insert("wght".into(), 700.0);
        axes.insert("wdth".into(), 100.0);
        axes.insert("slnt".into(), 0.0);
        // Pixel rounding pins the registry advance rounding; variation
        // axes (incl. the substituted `$`) pin the exact coordinates.
        let config = Config {
            size_px: 14.0,
            axes: axes.clone(),
            characters: "AV$09 ".into(),
            metric_rounding: MetricRounding::Pixel,
            ..Config::default()
        };
        let output = generate(&data, &config).unwrap();
        let mut source_settings = config.clone();
        source_settings.hinting = Hinting::None;
        let source_report = reference(
            &data,
            &ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: "none".into(),
                settings: source_settings,
            },
        )
        .unwrap();
        let registry = TrackingGuard::build(&source_report, &source_report);
        let geometry = TrackingGuard::for_output_from_geometry(&data, &output).unwrap();
        assert_eq!(geometry.source_min_x, registry.source_min_x);
        assert_eq!(geometry.source_max_x, registry.source_max_x);
        assert_eq!(geometry.source_advance, registry.source_advance);
        assert_eq!(geometry.source_sha256, registry.source_sha256);
        // Every delivered advance is a whole pixel under Pixel rounding.
        assert!(geometry
            .source_advance
            .values()
            .all(|advance| advance % 64 == 0));
        // Ink still comes from the delivered output, not the source capture.
        for glyph in &output.glyphs {
            assert_eq!(
                geometry.ink_min_col.get(&glyph.codepoint).copied(),
                ink_columns(&glyph.pixels, glyph.left, glyph.width, glyph.height).map(|(lo, _)| lo)
            );
        }
    }
}
