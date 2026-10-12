//! Reusable line-layout spacing engine.
//!
//! Source foundation: FreeType's advance/bearing model plus pair kerning
//! (source metrics and source kerning), fitted advances returned by the
//! scaler and its documented bearing deltas, and the
//! projected source-gap pair target (current project
//! hypothesis — see [`crate::mono_spacing::PairSpacing`]).
//!
//! Geometric invariant: spacing only chooses whole-string pen positions. It
//! never refits, rescales or reinterprets glyph bitmaps; scalar glyph pixels
//! and source roles are owned by the input adapters.
//!
//! The engine is input-adapter agnostic: the surface renderer feeds it
//! `generate()` advances, the source kern table and role-report metadata,
//! while a native adapter may feed an attached-left shaping kern as the pair
//! kern input. The pair kern is applied exactly once per pair, shifting the
//! current glyph's origin; adapters that receive left-attached kern values
//! must relocate the attachment into this pair slot before calling
//! [`SpacingEngine::place`]. Drawing, wrapping and line parsing stay with
//! the caller; wrapping simulation and placement must both go through
//! [`SpacingEngine::place`] so measurement and placement never diverge.
//!
//! New pair algorithms plug in behind the same [`SpacingEngine::place`]
//! contract: add a correction source to [`EngineInputs`] and combine it in
//! `neutral_pair_adjustment`, keeping the single-application rule.

use crate::{mono_spacing::PairSpacing, reference::ReferenceRecord, MetricRounding};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Selectable spacing model for monochrome layout.
///
/// `Auto` (default) retains the current rendering paths exactly: the working
/// candidate uses fitted advances with the projected source-gap pair model,
/// while the approved baseline and the independent reference use source
/// linear advances plus source pair kerning. Gray (and any non-monochrome
/// depth) is always source layout; explicit non-`Auto` models are rejected
/// there. Explicit `Source` uses source linear advances plus the existing
/// source kern table with the same role's glyph bitmaps. Explicit `Fitted`
/// uses the actual returned hinted advance from the same role's report with
/// FreeType bearing correction where same-role metadata is available.
/// Explicit `Projected` uses same-role fitted metrics with the source-gap
/// pair model, falling back to fitted placement for
/// empty/fixed-pitch/tabular/unknown pairs.
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SpacingModel {
    #[default]
    Auto,
    Source,
    Fitted,
    Projected,
}

/// Immutable per-engine inputs assembled by the calling adapter.
///
/// Advances and the kern table are snapshots: source advances come from
/// `generate()` before any role swap, fitted advances from the same role's
/// report via [`fitted_advance_26_6`], and the kern table from the font's
/// source pair extraction (or a host shaping kern relocated to the pair
/// slot). A disabled source kern config must reach the engine as
/// `apply_kerning: false` (and/or an empty table) and then stays off under
/// every model.
pub struct EngineInputs<'a> {
    /// Selected model, with the renderer default resolved by the adapter.
    pub model: SpacingModel,
    /// Immutable source advances per codepoint in 26.6 pixels.
    pub source_advances_26_6: HashMap<u32, i32>,
    /// Same-renderer fitted advances, including documented metadata fallbacks.
    pub fitted_advances_26_6: HashMap<u32, i32>,
    /// Source pair kern adjustments in 26.6, applied exactly once per pair.
    pub kern_26_6: HashMap<(u32, u32), i32>,
    /// Fitted phantom-point side-bearing deltas per codepoint in 26.6.
    pub bearing_deltas_26_6: HashMap<u32, [i32; 2]>,
    /// Projected source-gap pair model, if the selected model uses one.
    pub pair: Option<&'a PairSpacing>,
    /// Minimum-separation model for explicit tracking; usually the same
    /// spacing as `pair`, or a capture over the selected output bitmaps.
    pub minimum: Option<&'a PairSpacing>,
    /// False keeps every kern lookup at zero under all models.
    pub apply_kerning: bool,
    /// True for 1-bit layout (whole-pixel tracking, space floor).
    pub mono: bool,
    /// User-selected tracking in pixels; the engine normalizes it
    /// (whole-pixel steps with ties away from zero at mono, 26.6 otherwise).
    pub letter_spacing_px: f32,
}

/// Line-layout spacing engine: advance choice, single kern application,
/// bearing correction, projected pair correction, tracking normalization
/// and the minimum-separation floor behind one placement operation.
#[derive(Clone)]
pub struct SpacingEngine<'a> {
    model: SpacingModel,
    advances: HashMap<u32, i32>,
    kern: HashMap<(u32, u32), i32>,
    deltas: HashMap<u32, [i32; 2]>,
    pair: Option<&'a PairSpacing>,
    minimum: Option<&'a PairSpacing>,
    apply_kerning: bool,
    mono: bool,
    tracking_26_6: i32,
}

impl<'a> SpacingEngine<'a> {
    /// Normalize a user tracking offset: whole-pixel steps at mono (ties
    /// away from zero, matching the UI convention) and 26.6 otherwise.
    /// This is a user-policy normalization, not an optical threshold.
    pub(crate) fn normalize_tracking_offset(mono: bool, letter_spacing_px: f32) -> i32 {
        if mono {
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
        if inputs.model == SpacingModel::Auto {
            return Err(crate::fail("spacing engine requires a resolved model"));
        }
        if inputs.model != SpacingModel::Source && !inputs.mono {
            return Err(crate::fail(
                "experimental spacing models require monochrome output",
            ));
        }
        if inputs.model == SpacingModel::Projected && inputs.pair.is_none() {
            return Err(crate::fail(
                "projected spacing requires source and output geometry",
            ));
        }
        let tracking_26_6 = Self::normalize_tracking_offset(inputs.mono, inputs.letter_spacing_px);
        let advances = match inputs.model {
            SpacingModel::Source => inputs.source_advances_26_6,
            SpacingModel::Fitted | SpacingModel::Projected => inputs.fitted_advances_26_6,
            SpacingModel::Auto => unreachable!(),
        };
        Ok(SpacingEngine {
            model: inputs.model,
            advances,
            kern: inputs.kern_26_6,
            deltas: inputs.bearing_deltas_26_6,
            pair: if inputs.model == SpacingModel::Projected {
                inputs.pair
            } else {
                None
            },
            minimum: if inputs.mono { inputs.minimum } else { None },
            apply_kerning: inputs.apply_kerning,
            mono: inputs.mono,
            tracking_26_6,
        })
    }

    /// Selected (already `Auto`-resolved) model this engine was built for.
    pub fn model(&self) -> SpacingModel {
        self.model
    }

    /// Normalized tracking offset in 26.6 pixels.
    pub fn tracking_26_6(&self) -> i32 {
        self.tracking_26_6
    }

    /// Whether `codepoint` has a spacing advance in this engine.
    pub fn has_glyph(&self, codepoint: u32) -> bool {
        self.advances.contains_key(&codepoint)
    }

    /// Pair kern for `previous`/`current` as applied by placement: zero when
    /// kerning is disabled or the pair has no entry. Single-application
    /// accessor for adapters carrying attached-left shaping kern.
    pub fn pair_kern(&self, previous: Option<u32>, current: u32) -> i32 {
        if !self.apply_kerning {
            return 0;
        }
        previous
            .and_then(|left| self.kern.get(&(left, current)))
            .copied()
            .unwrap_or(0)
    }

    /// Source pair kerning plus, for supported pairs, the projected
    /// source-gap extra correction. Unsupported pairs keep the prior
    /// integer-bearing correction. Feeds both placement and wrapping
    /// simulation, so measurement and placement never diverge.
    fn neutral_pair_adjustment(&self, previous: Option<u32>, current: u32) -> i64 {
        let kern = i64::from(self.pair_kern(previous, current));
        if self.model == SpacingModel::Source {
            return kern;
        }
        if let (Some(left), Some(spacing)) = (previous, self.pair) {
            if let Some(advance) = self.advances.get(&left) {
                if let Some(extra) = spacing.correction(left, current, kern as i32, *advance) {
                    return kern + i64::from(extra);
                }
            }
        }
        let previous_rsb = previous
            .and_then(|left| self.deltas.get(&left))
            .map_or(0, |deltas| deltas[1]);
        let current_lsb = self.deltas.get(&current).map_or(0, |deltas| deltas[0]);
        kern + i64::from(crate::mono_spacing::bearing_adjustment(
            previous_rsb,
            current_lsb,
        ))
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
        neutral.checked_add(spacing.minimum_tracking_correction(
            left,
            current,
            self.pair_kern(previous, current),
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

/// Fitted advance choice from a same-role report record.
///
/// Uses the returned hinted advance width converted to 26.6 with the
/// report's metric rounding when the capture provides one; otherwise falls
/// back to the reported advance and returns `false`.
///
/// Documented metadata limit: under a linear advance policy the reported
/// advance is the design advance, not a fitted metric, so a `false` return
/// carries no hinted-advance information and fitted placement degrades to
/// the reported value.
pub fn fitted_advance_26_6(record: &ReferenceRecord, rounding: MetricRounding) -> (i32, bool) {
    match record.hinted_advance_width {
        Some(width) if width.is_finite() => (crate::fixed(width, rounding), true),
        _ => (record.advance_26_6, false),
    }
}
