//! Shared line-placement logic for source and bitmap layout.
//!
//! Source foundation: FreeType's advance/bearing model plus pair kerning
//! (https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) and its
//! integer bearing correction for fitted phantom-point deltas
//! (https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_glyphslotrec).
//! Bitmap strikes store integer advances, bitmap offsets and sparse integer
//! pair adjustments separately, as in OpenType EBDT and BMFont; see
//! `docs/revisions/001/03-spacing-kerning.md`.
//!
//! Geometric invariant: placement only chooses pen positions. It never
//! refits, rescales or reinterprets glyph bitmaps. Callers finalize the
//! advances and pair adjustments for their renderer role before calling
//! [`SpacingEngine::place`]; measurement, wrapping and drawing all share
//! that one operation, so they cannot diverge.
//!
//! Two finalized policies feed this engine, and neither is user-selectable
//! as a spacing model:
//! - Legacy baseline and independent reference roles keep source layout:
//!   fractional source advances and fractional source pair kerning.
//! - The working candidate uses one bitmap policy for Mono and Gray:
//!   fitted advances when the fitter returns one, otherwise the rounded
//!   source advance; source kerning and any available fitted bearing
//!   correction are resolved once into integer pair adjustments. Pen
//!   positions therefore accumulate in whole pixels and the same pair has
//!   the same relative placement regardless of preceding text.

use crate::{mono_spacing::TrackingGuard, reference::ReferenceRecord};
use std::collections::HashMap;

/// Uniform explicit tracking step in 26.6 for the separated bitmap pipeline.
///
/// Whole-pixel addition to every finalized advance, validated to the native
/// -16..=16 px range. Bitmap advances, offsets and pair adjustments are
/// independent storage in bitmap strikes (OpenType EBDT; BMFont), so the
/// step touches only advances.
/// https://freetype.org/freetype2/docs/glyphs/glyphs-3.html
/// https://www.angelcode.com/products/bmfont/doc/file_format.html
pub fn uniform_tracking_26_6(letter_spacing_px: f32) -> Result<i32, crate::Error> {
    if !letter_spacing_px.is_finite() || !(-16.0..=16.0).contains(&letter_spacing_px) {
        return Err(crate::fail(
            "letter_spacing_px must be finite and within -16..=16",
        ));
    }
    let pixels = letter_spacing_px.round() as i32;
    pixels
        .checked_mul(64)
        .ok_or_else(|| crate::fail("uniform tracking advance overflow"))
}

/// Baked uniform tracking over finalized whole-pixel advances.
///
/// Adds the [`uniform_tracking_26_6`] step to every advance, including
/// spaces and the final glyph advance; pair adjustments pass through
/// unchanged, so kerning and any fitted bearing correction still apply
/// exactly once. Zero is identity. Negative results are kept as-is:
/// tightening may overlap and is never clamped per glyph. Only `i32`
/// overflow fails.
pub fn apply_uniform_tracking(
    advances_26_6: &HashMap<u32, i32>,
    letter_spacing_px: f32,
) -> Result<HashMap<u32, i32>, crate::Error> {
    let step = uniform_tracking_26_6(letter_spacing_px)?;
    let mut tracked = HashMap::with_capacity(advances_26_6.len());
    for (codepoint, advance) in advances_26_6 {
        tracked.insert(
            *codepoint,
            advance
                .checked_add(step)
                .ok_or_else(|| crate::fail("uniform tracking advance overflow"))?,
        );
    }
    Ok(tracked)
}

/// Quantize a signed 26.6 value to a whole pixel, returned in 26.6.
///
/// Nearest pixel with ties away from zero, so negating an adjustment
/// negates its quantization: signed kerning and overhang keep their sign
/// symmetry. This is a documented project rounding choice for bitmap
/// strikes; it is not a claim of full FreeType layout parity.
pub fn quantize_26_6(value_26_6: i32) -> i32 {
    let value = i64::from(value_26_6);
    let pixels = if value >= 0 {
        (value + 32) / 64
    } else {
        -((-value + 32) / 64)
    };
    i32::try_from(pixels * 64).unwrap_or(if value >= 0 {
        i32::MAX / 64 * 64
    } else {
        i32::MIN / 64 * 64
    })
}

/// Bitmap advance for one fitted record in 26.6.
///
/// Uses the fitter's returned advance width when it is finite, quantized
/// with [`quantize_26_6`]'s whole-pixel rule; otherwise falls back to the
/// rounded source (linear) advance carried by the record. No glyph-specific
/// handling: the fallback is the same general rule for every glyph whose
/// fitter returns no advance.
pub fn bitmap_advance_26_6(record: &ReferenceRecord) -> i32 {
    match record.hinted_advance_width {
        Some(width) if width.is_finite() => {
            let pixels = width.round();
            if pixels >= i32::MAX as f32 / 64.0 {
                i32::MAX / 64 * 64
            } else if pixels <= i32::MIN as f32 / 64.0 {
                i32::MIN / 64 * 64
            } else {
                pixels as i32 * 64
            }
        }
        _ => quantize_26_6(record.advance_26_6),
    }
}

/// Finalized bitmap metrics for one strike: the single metric table the
/// exported strike, the interactive preview and native specimens consume.
///
/// `advances_26_6` are whole-pixel advances. `pair_adjustments_26_6` are
/// sparse whole-pixel pair adjustments with source kerning and any
/// available fitted bearing correction already baked in exactly once, so
/// placement never reapplies a correction. `source_kern_26_6` retains the
/// fractional source pair values for tracking classification and kerning
/// inspection only; it is not a placement input.
pub struct FinalizedBitmapMetrics {
    pub advances_26_6: HashMap<u32, i32>,
    pub pair_adjustments_26_6: HashMap<(u32, u32), i32>,
    pub source_kern_26_6: HashMap<(u32, u32), i32>,
}

/// Resolve the finalized bitmap metric table from fitted records.
///
/// Advances: the fitter's returned advance when available, otherwise the
/// rounded source advance (see [`bitmap_advance_26_6`]). Two font-level
/// rules override per-glyph fitted advances, following FreeType's autofit
/// loader, which preserves a common rounded advance for equal-width
/// glyphs and zeroes their bearing deltas
/// (https://github.com/freetype/freetype/blob/master/src/autofit/afloader.c):
/// source fixed-pitch glyphs (including space) use the rounded source
/// advance so differing hinted advances cannot break the source cells,
/// and source-tabular digits retain the quantized common source advance.
/// Fixed pitch and tabular digits likewise carry no bearing deltas.
/// Every record is part of the table as supplied, so an adapter that
/// captures its fitted space as a record gets the fitted space advance
/// from this same rule, with no adapter-specific space override.
pub fn finalize_bitmap_metrics(
    records: &[ReferenceRecord],
    source_advances_26_6: &HashMap<u32, i32>,
    source_kern_26_6: &HashMap<(u32, u32), i32>,
    kerning_enabled: bool,
    monospace: bool,
    tabular_digits: bool,
) -> FinalizedBitmapMetrics {
    let common_digit_advance = if tabular_digits {
        ('0'..='9')
            .filter_map(|digit| source_advances_26_6.get(&(digit as u32)))
            .next()
            .map(|advance| quantize_26_6(*advance))
    } else {
        None
    };
    let mut advances = HashMap::new();
    for record in records {
        // Fixed pitch: rounded source advance for every glyph, so equal
        // source cells stay equal regardless of fitted advances.
        let mut advance = if monospace {
            quantize_26_6(
                source_advances_26_6
                    .get(&record.codepoint)
                    .copied()
                    .unwrap_or(record.advance_26_6),
            )
        } else {
            bitmap_advance_26_6(record)
        };
        if let Some(common) = common_digit_advance {
            if (u32::from(b'0')..=u32::from(b'9')).contains(&record.codepoint) {
                advance = common;
            }
        }
        advances.insert(record.codepoint, advance);
    }
    let bearing_deltas: HashMap<u32, [i32; 2]> = if monospace {
        HashMap::new()
    } else {
        records
            .iter()
            .filter_map(|record| {
                record
                    .side_bearing_deltas_26_6
                    .map(|deltas| (record.codepoint, deltas))
            })
            .filter(|(codepoint, _)| {
                !(tabular_digits && (u32::from(b'0')..=u32::from(b'9')).contains(codepoint))
            })
            .collect()
    };
    // Sparse integer pair table: quantized source kerning (when enabled)
    // plus the available fitted bearing correction, applied once here.
    // A fitting correction therefore survives kerning being disabled.
    let mut pair_adjustments = HashMap::new();
    for left in advances.keys() {
        for right in advances.keys() {
            let previous_rsb = bearing_deltas.get(left).map_or(0, |deltas| deltas[1]);
            let current_lsb = bearing_deltas.get(right).map_or(0, |deltas| deltas[0]);
            let adjustment = bitmap_pair_adjustment_26_6(
                source_kern_26_6.get(&(*left, *right)).copied().unwrap_or(0),
                kerning_enabled,
                previous_rsb,
                current_lsb,
            );
            if adjustment != 0 {
                pair_adjustments.insert((*left, *right), adjustment);
            }
        }
    }
    FinalizedBitmapMetrics {
        advances_26_6: advances,
        pair_adjustments_26_6: pair_adjustments,
        source_kern_26_6: source_kern_26_6.clone(),
    }
}

/// Integer pair adjustment for one pair: quantized source kerning (when
/// kerning is enabled) plus the available fitted bearing correction.
/// Each source contributes exactly once.
pub fn bitmap_pair_adjustment_26_6(
    kern_26_6: i32,
    apply_kerning: bool,
    previous_rsb_26_6: i32,
    current_lsb_26_6: i32,
) -> i32 {
    let kern = if apply_kerning {
        quantize_26_6(kern_26_6)
    } else {
        0
    };
    kern.saturating_add(crate::mono_spacing::bearing_adjustment(
        previous_rsb_26_6,
        current_lsb_26_6,
    ))
}

/// Immutable per-engine inputs assembled by the calling adapter.
///
/// Advances and pair adjustments are already finalized for the caller's
/// role: source layout passes fractional advances with fractional source
/// pair values as the pair adjustments, while bitmap layout passes the
/// whole-pixel table from [`finalize_bitmap_metrics`], whose pair
/// adjustments already contain kerning and any fitting correction exactly
/// once. Placement therefore never looks up bearings or kerning again.
/// `guard_kern_26_6` keeps fractional source pair values, resolved by the
/// caller for its kerning switch, solely for the tracking guard's
/// source-gap classification.
pub struct EngineInputs<'a> {
    /// Finalized advances per codepoint in 26.6 pixels.
    pub advances_26_6: HashMap<u32, i32>,
    /// Finalized pair adjustments in 26.6, applied exactly once per pair.
    pub pair_adjustments_26_6: HashMap<(u32, u32), i32>,
    /// Fractional source kern for the tracking guard's source-gap target.
    pub guard_kern_26_6: HashMap<(u32, u32), i32>,
    /// Minimum-separation guard for explicit Mono tracking, if available.
    pub minimum: Option<&'a TrackingGuard>,
    /// True for 1-bit layout (whole-pixel tracking, space floor, guard).
    pub mono: bool,
    /// True when pen positions are whole pixels (candidate Mono and Gray):
    /// tracking is then quantized to whole pixels at any output depth.
    pub integer_positions: bool,
    /// User-selected tracking in pixels; the engine normalizes it
    /// (whole-pixel steps with ties away from zero for integer or Mono
    /// layout, 26.6 otherwise).
    pub letter_spacing_px: f32,
}

/// Line-layout placement engine: finalized advance choice, single kern
/// application, available bearing correction, tracking normalization and
/// the minimum-separation floor behind one placement operation.
#[derive(Clone)]
pub struct SpacingEngine<'a> {
    advances: HashMap<u32, i32>,
    pair_adjustments: HashMap<(u32, u32), i32>,
    guard_kern: HashMap<(u32, u32), i32>,
    minimum: Option<&'a TrackingGuard>,
    mono: bool,
    tracking_26_6: i32,
}

impl<'a> SpacingEngine<'a> {
    /// Normalize a user tracking offset: whole-pixel steps (ties away
    /// from zero) for Mono or integer-position layout, 26.6 otherwise.
    /// This is a user-policy normalization, not an optical threshold.
    pub(crate) fn normalize_tracking_offset(integer: bool, letter_spacing_px: f32) -> i32 {
        if integer {
            letter_spacing_px.round() as i32 * 64
        } else {
            (letter_spacing_px * 64.0).round() as i32
        }
    }

    pub fn new(inputs: EngineInputs<'a>) -> Result<Self, crate::Error> {
        if !inputs.letter_spacing_px.is_finite()
            || !(-16.0..=16.0).contains(&inputs.letter_spacing_px)
        {
            return Err(crate::fail(
                "letter_spacing_px must be finite and within -16..=16",
            ));
        }
        let integer = inputs.mono || inputs.integer_positions;
        let tracking_26_6 = Self::normalize_tracking_offset(integer, inputs.letter_spacing_px);
        Ok(SpacingEngine {
            advances: inputs.advances_26_6,
            pair_adjustments: inputs.pair_adjustments_26_6,
            guard_kern: inputs.guard_kern_26_6,
            minimum: if inputs.mono { inputs.minimum } else { None },
            mono: inputs.mono,
            tracking_26_6,
        })
    }

    /// Normalized tracking offset in 26.6 pixels.
    pub fn tracking_26_6(&self) -> i32 {
        self.tracking_26_6
    }

    /// Whether `codepoint` has a spacing advance in this engine.
    pub fn has_glyph(&self, codepoint: u32) -> bool {
        self.advances.contains_key(&codepoint)
    }

    /// Finalized pair adjustment for `previous`/`current` as applied by
    /// placement: zero when the pair has no entry. Kerning enablement and
    /// any fitting correction were already resolved into this table by
    /// the adapter, so placement applies the value exactly once.
    pub fn pair_kern(&self, previous: Option<u32>, current: u32) -> i32 {
        previous
            .and_then(|left| self.pair_adjustments.get(&(left, current)))
            .copied()
            .unwrap_or(0)
    }

    fn neutral_pair_adjustment(&self, previous: Option<u32>, current: u32) -> i64 {
        i64::from(self.pair_kern(previous, current))
    }

    /// Glyph advance with tracking. Explicit user policy: negative tracking
    /// keeps word gaps at neutral width, so an ASCII space uses its selected
    /// advance unchanged; other glyphs tighten as requested. Positive mono
    /// tracking keeps the existing one-pixel space floor. Outlines never change.
    fn tracked_advance(&self, current: u32) -> i64 {
        const SPACE: u32 = ' ' as u32;
        let selected = i64::from(self.advances.get(&current).copied().unwrap_or(0));
        if self.tracking_26_6 < 0 && current == SPACE {
            return selected;
        }
        let advance = selected + i64::from(self.tracking_26_6);
        if self.mono && self.tracking_26_6 != 0 && current == SPACE {
            // A space remains a positive blank advance under positive tracking.
            advance.max(64)
        } else {
            advance
        }
    }

    /// Neutral adjustment plus the user-selected minimum-separation floor
    /// under explicit nonzero tracking only; neutral layout is untouched.
    /// Explicit user policy for negative tracking: entering the first space
    /// after a nonspace predecessor refunds that predecessor's trailing step
    /// once, retaining the neutral kern/bearing correction, so the space run
    /// and the following glyph keep neutral origins relative to that glyph.
    /// Leading and repeated spaces take no refund.
    fn pair_adjustment(&self, pen_26_6: i64, previous: Option<u32>, current: u32) -> Option<i64> {
        const SPACE: u32 = ' ' as u32;
        let neutral = self.neutral_pair_adjustment(previous, current);
        if self.tracking_26_6 == 0 {
            return Some(neutral);
        }
        if self.tracking_26_6 < 0 {
            if current == SPACE {
                match previous {
                    Some(left) if left != SPACE && self.advances.contains_key(&left) => {
                        return neutral.checked_sub(i64::from(self.tracking_26_6));
                    }
                    _ => return Some(neutral),
                }
            }
            if previous == Some(SPACE) {
                return Some(neutral);
            }
        }
        let (Some(left), Some(spacing)) = (previous, self.minimum) else {
            return Some(neutral);
        };
        if !self.advances.contains_key(&left) {
            return Some(neutral);
        }
        let previous_origin = pen_26_6.checked_sub(self.tracked_advance(left))?;
        let proposed_origin = pen_26_6.checked_add(neutral)?;
        previous_origin.checked_add(32)?;
        proposed_origin.checked_add(32)?;
        let guard_kern = previous
            .and_then(|left_code| self.guard_kern.get(&(left_code, current)))
            .copied()
            .unwrap_or_else(|| self.pair_kern(previous, current));
        neutral.checked_add(spacing.minimum_tracking_correction(
            left,
            current,
            guard_kern,
            previous_origin,
            proposed_origin,
        ))
    }

    /// Place `current` after `previous` at pen `pen_26_6` (26.6 pixels).
    ///
    /// Returns the glyph origin and the next pen. Returns `None` when the
    /// codepoint has no advance in this engine or on integer overflow;
    /// callers with a skip-missing policy must check [`Self::has_glyph`]
    /// first to keep missing glyphs distinct from overflow.
    pub fn place(&self, pen_26_6: i64, previous: Option<u32>, current: u32) -> Option<(i64, i64)> {
        if !self.has_glyph(current) {
            return None;
        }
        let adjustment = self.pair_adjustment(pen_26_6, previous, current)?;
        let origin = pen_26_6.checked_add(adjustment)?;
        let next = origin.checked_add(self.tracked_advance(current))?;
        Some((origin, next))
    }
}

#[cfg(test)]
mod tests {
    use super::{finalize_bitmap_metrics, quantize_26_6};
    use crate::reference::{RasterPolicy, ReferenceRecord};
    use std::collections::HashMap;

    fn record(
        codepoint: u32,
        advance_26_6: i32,
        hinted: Option<f32>,
        deltas: Option<[i32; 2]>,
    ) -> ReferenceRecord {
        ReferenceRecord {
            side_bearing_deltas_26_6: deltas,
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
            diagonal_fitting: None,
            fitted_commands: Vec::new(),
            coverage: Vec::new(),
            coverage_sha256: String::new(),
            left: 0,
            top: 0,
            width: 0,
            height: 0,
            pixels: Vec::new(),
            advance_26_6,
            hinted_has_overlaps: false,
            hinted_lsb: None,
            hinted_advance_width: hinted,
        }
    }

    fn finalize(
        records: &[ReferenceRecord],
        source: &HashMap<u32, i32>,
        kern: &HashMap<(u32, u32), i32>,
        kerning: bool,
        monospace: bool,
        tabular: bool,
    ) -> super::FinalizedBitmapMetrics {
        finalize_bitmap_metrics(records, source, kern, kerning, monospace, tabular)
    }

    #[test]
    fn fitted_advance_wins_and_missing_fitted_falls_back_to_rounded_source() {
        let records = vec![
            record(65, 6 * 64 + 20, Some(7.6), None),
            record(66, 6 * 64 + 20, None, None),
            record(67, 6 * 64 + 20, Some(f32::NAN), None),
        ];
        let source = HashMap::from([(65, 6 * 64 + 20), (66, 6 * 64 + 20), (67, 6 * 64 + 20)]);
        let metrics = finalize(&records, &source, &HashMap::new(), true, false, false);
        assert_eq!(metrics.advances_26_6[&65], 8 * 64);
        assert_eq!(metrics.advances_26_6[&66], 6 * 64);
        assert_eq!(metrics.advances_26_6[&67], 6 * 64);
        assert_eq!(quantize_26_6(506), 512);
    }

    #[test]
    fn tabular_digits_share_the_common_rounded_source_advance() {
        let mut records = Vec::new();
        let mut source = HashMap::new();
        for digit in b'0'..=b'9' {
            // Fitted advances deliberately disagree; the common source
            // value (7.90625 px) must still win for every digit.
            records.push(record(
                u32::from(digit),
                506,
                Some(7.0 + f32::from(digit - b'0') * 0.4),
                Some([10, 10]),
            ));
            source.insert(u32::from(digit), 506);
        }
        records.push(record(65, 6 * 64, Some(6.2), Some([10, 10])));
        source.insert(65, 6 * 64);
        let kern = HashMap::from([((u32::from(b'3'), u32::from(b'4')), -70)]);
        let metrics = finalize(&records, &source, &kern, true, false, true);
        for digit in b'0'..=b'9' {
            assert_eq!(metrics.advances_26_6[&u32::from(digit)], 8 * 64);
        }
        assert_eq!(metrics.advances_26_6[&65], 6 * 64);
        // Tabular pairs carry no bearing delta: only quantized kern remains.
        assert_eq!(
            metrics.pair_adjustments_26_6[&(u32::from(b'3'), u32::from(b'4'))],
            -64
        );
    }

    #[test]
    fn fixed_pitch_uses_rounded_source_cells_and_no_bearing_deltas() {
        // Equal source cells (8 px) with deliberately differing fitted
        // advances (7 px, 9 px) and a fitted space: the source cells win
        // for every glyph, including space, so the grid cannot break.
        let records = vec![
            record(65, 8 * 64, Some(7.0), Some([40, 40])),
            record(66, 8 * 64, Some(9.0), Some([40, 40])),
            record(32, 8 * 64, Some(3.0), Some([40, 40])),
        ];
        let source = HashMap::from([(65, 8 * 64), (66, 8 * 64), (32, 8 * 64)]);
        let metrics = finalize(&records, &source, &HashMap::new(), true, true, false);
        assert_eq!(metrics.advances_26_6[&65], 8 * 64);
        assert_eq!(metrics.advances_26_6[&66], 8 * 64);
        assert_eq!(metrics.advances_26_6[&32], 8 * 64);
        assert!(
            metrics.pair_adjustments_26_6.is_empty(),
            "fixed pitch must carry no bearing correction: {:?}",
            metrics.pair_adjustments_26_6
        );
    }

    #[test]
    fn fitted_space_advance_is_carried_through_finalization() {
        // Space source advance 228 (3.5625 px) rounds to 256, but the
        // fitted space advance (5 px) is what every adapter must consume.
        let records = vec![
            record(65, 6 * 64, Some(6.0), None),
            record(32, 228, Some(5.0), None),
        ];
        let source = HashMap::from([(65, 6 * 64), (32, 228)]);
        let metrics = finalize(&records, &source, &HashMap::new(), true, false, false);
        assert_eq!(metrics.advances_26_6[&32], 5 * 64);
    }

    #[test]
    fn fitting_correction_survives_kerning_off_and_applies_once() {
        // AV source kern -100 quantizes to -128; bearing rsb 48 vs lsb 0
        // crosses the +32 limit and adds -64 exactly once when baked.
        let records = vec![
            record(65, 6 * 64, Some(6.0), Some([0, 48])),
            record(86, 7 * 64, Some(7.0), Some([0, 0])),
        ];
        let source = HashMap::from([(65, 6 * 64), (86, 7 * 64)]);
        let kern = HashMap::from([((65, 86), -100)]);
        let on = finalize(&records, &source, &kern, true, false, false);
        assert_eq!(on.pair_adjustments_26_6[&(65, 86)], -128 - 64);
        let off = finalize(&records, &source, &kern, false, false, false);
        assert_eq!(
            off.pair_adjustments_26_6[&(65, 86)],
            -64,
            "only the fitting correction remains with kerning off"
        );
        assert_eq!(off.source_kern_26_6[&(65, 86)], -100);
    }
}
