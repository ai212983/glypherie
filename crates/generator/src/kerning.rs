//! Interchangeable pair-table methods before tracking or line placement.
//!
//! Plans separate auxiliary calibration captures from the output repertoire.
//! Each method owns its measurement, calibration and completed placements;
//! the coordinator validates and commits the table atomically. Rendering and
//! shared line placement remain ignorant of each method's geometric model.
mod fontforge;
mod geometry;
mod hu_hersch;
mod outline;
mod placement;
mod typefacet;
pub use fontforge::FontforgeSettings;
pub use hu_hersch::HuHerschSettings;
pub use typefacet::TypefacetSettings;

use crate::{fail, layout_spacing::FinalizedBitmapMetrics, Config, Error, Glyph};
use serde::{Deserialize, Serialize};
use skrifa_baseline::{instance::Size, MetadataProvider};
use std::collections::HashMap;

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize)]
#[serde(tag = "method", rename_all = "snake_case", deny_unknown_fields)]
pub enum KerningMethod {
    #[default]
    Source,
    Typefacet(TypefacetSettings),
    HuHersch(HuHerschSettings),
    Fontforge(FontforgeSettings),
}

// A struct-shaped source variant makes unknown settings an error too; Serde's
// internally tagged unit variant otherwise discards them on native JSON input.
impl<'de> Deserialize<'de> for KerningMethod {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        #[derive(Deserialize)]
        #[serde(tag = "method", rename_all = "snake_case", deny_unknown_fields)]
        enum Wire {
            Source {},
            Typefacet(TypefacetSettings),
            HuHersch(HuHerschSettings),
            Fontforge(FontforgeSettings),
        }
        Ok(match Wire::deserialize(deserializer)? {
            Wire::Source {} => Self::Source,
            Wire::Typefacet(settings) => Self::Typefacet(settings),
            Wire::HuHersch(settings) => Self::HuHersch(settings),
            Wire::Fontforge(settings) => Self::Fontforge(settings),
        })
    }
}

impl KerningMethod {
    /// Validate independently of text, captures and cached results.
    pub fn validate(&self, explicit_pipeline: bool) -> Result<(), Error> {
        match self {
            Self::Source => Ok(()),
            Self::Typefacet(settings) => {
                settings.validate()?;
                require_pipeline(explicit_pipeline, "TypeFacet")
            }
            Self::HuHersch(settings) => {
                settings.validate()?;
                require_pipeline(explicit_pipeline, "Hu/Hersch")
            }
            Self::Fontforge(settings) => {
                settings.validate()?;
                require_pipeline(explicit_pipeline, "FontForge-derived")
            }
        }
    }
}

fn require_pipeline(explicit_pipeline: bool, label: &str) -> Result<(), Error> {
    if !explicit_pipeline {
        return Err(fail(format!(
            "{label} kerning requires an explicit bitmap-layout pipeline"
        )));
    }
    Ok(())
}

/// Every output pair carries an explicit replacement or Source-retention
/// reason. Replace(0) removes an existing adjustment. The complete table is
/// validated before any replacement is committed.
pub(super) type PairAdjustments = HashMap<(u32, u32), PairDecision>;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum PairDecision {
    Replace(i32),
    RetainSource(&'static str),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum CalibrationClass {
    Lowercase,
    Uppercase,
    Digits,
    Mixed,
}

/// Plans are computed before the output capture. Auxiliary repertoires never
/// enlarge the output scalar/pair domain or exported strike.
#[cfg(feature = "candidate")]
pub(crate) struct AnalysisPlan {
    classes: Vec<CalibrationClass>,
    source_geometry: bool,
}

#[cfg(feature = "candidate")]
impl AnalysisPlan {
    pub(crate) fn new(data: &[u8], method: KerningMethod, config: &Config) -> Result<Self, Error> {
        let mut plan = Self {
            classes: Vec::new(),
            source_geometry: false,
        };
        if matches!(method, KerningMethod::Source | KerningMethod::Typefacet(_))
            || matches!(method,KerningMethod::Fontforge(settings) if settings.strength == 0.0)
            || matches!(method,KerningMethod::HuHersch(settings) if settings.strength == 0.0)
        {
            return Ok(plan);
        }
        crate::validate_config(config)?;
        let properties = crate::mono_spacing::font_spacing_properties(data, config)?;
        if properties.monospace {
            return Ok(plan);
        }
        match method {
            KerningMethod::Source | KerningMethod::Typefacet(_) => {}
            KerningMethod::Fontforge(settings) => plan.source_geometry = settings.strength > 0.0,
            KerningMethod::HuHersch(_) => {
                // Class discovery is linear in supplied text, never its pair
                // cross product. Use the adapter's exact Unicode classifier.
                let mut lower = false;
                let mut upper = false;
                let mut digits = false;
                for cp in config.characters.chars().map(u32::from) {
                    match hu_hersch::calibration_class(cp, cp) {
                        Some(CalibrationClass::Lowercase) => lower = true,
                        Some(CalibrationClass::Uppercase) => upper = true,
                        Some(CalibrationClass::Digits) => digits = true,
                        _ => {}
                    }
                }
                if lower {
                    plan.classes.push(CalibrationClass::Lowercase);
                }
                if upper {
                    plan.classes.push(CalibrationClass::Uppercase);
                }
                if digits && !properties.tabular_digits {
                    plan.classes.push(CalibrationClass::Digits);
                }
                if lower && upper {
                    plan.classes.push(CalibrationClass::Mixed);
                }
            }
        }
        Ok(plan)
    }
}

pub(super) struct CalibrationCapture {
    pub class: CalibrationClass,
    pub unavailable_reason: Option<&'static str>,
    pub records: Vec<crate::reference::ReferenceRecord>,
    pub source_advances_26_6: HashMap<u32, i32>,
    pub source_pairs_26_6: HashMap<(u32, u32), i32>,
}

#[derive(Default)]
pub(crate) struct AnalysisCapture {
    calibration: Vec<CalibrationCapture>,
    source_commands: HashMap<u32, Vec<crate::probe::FittedCommand>>,
    source_advances_26_6: HashMap<u32, i32>,
    source_pairs_26_6: HashMap<(u32, u32), i32>,
}

/// Methods receive captured facts rather than a universal scoring interface.
/// Geometry, calibration, rounding and feasibility remain method policy.
pub(super) struct MethodContext<'a> {
    pub glyphs: &'a [Glyph],
    pub records: &'a [crate::reference::ReferenceRecord],
    /// Exact unscaled HarfBuzz-style source outline coordinates in design units.
    pub source_commands: &'a HashMap<u32, Vec<crate::probe::FittedCommand>>,
    pub source_advances_26_6: &'a HashMap<u32, i32>,
    pub source_pairs_26_6: &'a HashMap<(u32, u32), i32>,
    pub advances_26_6: &'a HashMap<u32, i32>,
    pub pair_adjustments_26_6: &'a HashMap<(u32, u32), i32>,
    pub output_bits: u8,
    pub units_per_em: u16,
    pub size_px: f64,
    pub ascender_26_6: i32,
    pub properties: crate::mono_spacing::FontSpacingProperties,
    pub source_kerning: bool,
}

#[cfg(feature = "candidate")]
pub(crate) fn capture_analysis(
    session: &crate::reference::CaptureSession<'_>,
    config: &Config,
    pipeline: crate::renderer::RenderPipeline,
    plan: &AnalysisPlan,
    output_records: &[crate::reference::ReferenceRecord],
) -> Result<AnalysisCapture, Error> {
    use crate::reference::{ReferenceRequest, PROFILE_GRAY_3BIT, PROFILE_MONO_1BIT};
    let mut result = AnalysisCapture::default();
    for &class in &plan.classes {
        let characters = match class {
            CalibrationClass::Lowercase => ('a'..='z').collect(),
            CalibrationClass::Uppercase => ('A'..='Z').collect(),
            CalibrationClass::Digits => ('0'..='9').collect(),
            CalibrationClass::Mixed => ('A'..='Z').chain('a'..='z').collect(),
        };
        // A missing reference makes its class unavailable; never fabricate a
        // reduced-domain target or introduce those references into the output.
        let mut settings = config.clone();
        settings.characters = characters;
        settings.missing_glyphs = crate::MissingGlyphs::Skip;
        let mut source_settings = settings.clone();
        source_settings.kerning = true;
        source_settings.metric_rounding = crate::MetricRounding::Subpixel;
        // Mixed calibration declares the two ordered cross products, not
        // the union alphabet's full Cartesian pair domain. Extra same-case
        // shaping requirements must not invalidate this independent class.
        let requested_pairs: Option<std::collections::BTreeSet<_>> =
            if class == CalibrationClass::Mixed {
                Some(
                    ('A'..='Z')
                        .flat_map(|upper| {
                            ('a'..='z').flat_map(move |lower| {
                                [
                                    (u32::from(upper), u32::from(lower)),
                                    (u32::from(lower), u32::from(upper)),
                                ]
                            })
                        })
                        .collect(),
                )
            } else {
                None
            };
        let (source, unavailable_reason) =
            match crate::source::prepare_calibration_source_in_session(
                session,
                &source_settings,
                requested_pairs.as_ref(),
            )? {
                crate::source::CalibrationSource::Available(source) => (Some(source), None),
                crate::source::CalibrationSource::Unavailable(reason) => (None, Some(reason)),
            };
        let records = if source.is_some() {
            let request = ReferenceRequest {
                profile: if config.output_bits == 1 {
                    PROFILE_MONO_1BIT
                } else {
                    PROFILE_GRAY_3BIT
                }
                .into(),
                extensions: crate::stem_fitting::StemFittingStrategy::extension(Some(
                    pipeline.fitting,
                ))
                .into(),
                settings,
            };
            crate::candidate::render_with_pipeline_in_session(session, &request, pipeline)?.records
        } else {
            Vec::new()
        };
        result.calibration.push(CalibrationCapture {
            class,
            unavailable_reason,
            records,
            source_advances_26_6: source
                .as_ref()
                .map(|source| {
                    source
                        .glyphs
                        .iter()
                        .map(|g| (g.codepoint, g.advance_26_6))
                        .collect()
                })
                .unwrap_or_default(),
            source_pairs_26_6: source
                .as_ref()
                .map(|source| {
                    source
                        .kerning
                        .iter()
                        .map(|pair| ((pair.left, pair.right), pair.adjustment_26_6))
                        .collect()
                })
                .unwrap_or_default(),
        });
    }
    if plan.source_geometry {
        let mut source_settings = config.clone();
        source_settings.kerning = true;
        source_settings.metric_rounding = crate::MetricRounding::Subpixel;
        let source = crate::source::prepare_source_in_session(session, &source_settings)?;
        result.source_advances_26_6 = source
            .glyphs
            .iter()
            .map(|g| (g.codepoint, g.advance_26_6))
            .collect();
        result.source_pairs_26_6 = source
            .kerning
            .iter()
            .map(|p| ((p.left, p.right), p.adjustment_26_6))
            .collect();
        use skrifa::{
            instance::Size,
            outline::{pen::PathStyle, DrawSettings},
            MetadataProvider,
        };
        let font = skrifa::FontRef::new(session.data).map_err(|error| fail(error.to_string()))?;
        let location = font.axes().location(
            config
                .axes
                .iter()
                .map(|(tag, value)| (tag.as_str(), *value)),
        );
        let outlines = font.outline_glyphs();
        let mut source_command_count = 0usize;
        for record in output_records {
            if !source
                .glyphs
                .iter()
                .any(|g| g.codepoint == record.codepoint && g.glyph_id == record.glyph_id)
            {
                return Err(fail("source and delivered kerning glyph identities differ"));
            }
            let outline = outlines
                .get(skrifa::GlyphId::new(record.glyph_id))
                .ok_or_else(|| fail("missing source kerning outline"))?;
            let mut pen = crate::probe::FittedPen::default();
            outline
                .draw(
                    DrawSettings::unhinted(Size::unscaled(), &location)
                        .with_path_style(PathStyle::HarfBuzz),
                    &mut pen,
                )
                .map_err(|error| fail(error.to_string()))?;
            source_command_count = source_command_count
                .checked_add(pen.commands().len())
                .ok_or_else(|| fail("source kerning command allocation overflow"))?;
            if source_command_count > 262_144 {
                return Err(fail("source kerning command allocation limit exceeded"));
            }
            result
                .source_commands
                .insert(record.codepoint, pen.into_commands());
        }
    }
    Ok(result)
}

/// Replace supported pairs in an already-finalized, untracked bitmap table.
/// Other pairs retain the source method; fixed-pitch cells always retain it.
/// Source kerning and bearing deltas must not be added again after this call.
pub(crate) fn resolve(
    data: &[u8],
    config: &Config,
    method: KerningMethod,
    glyphs: &[Glyph],
    records: &[crate::reference::ReferenceRecord],
    metrics: &mut FinalizedBitmapMetrics,
    properties: crate::mono_spacing::FontSpacingProperties,
    analysis: &AnalysisCapture,
) -> Result<(), Error> {
    if glyphs.len() > 1024 {
        return Err(fail("kerning pair domain exceeds 1048576 decisions"));
    }
    if properties.monospace {
        return Ok(());
    }
    match method {
        KerningMethod::Source => return Ok(()),
        KerningMethod::Typefacet(settings) => settings.validate()?,
        KerningMethod::HuHersch(settings) => settings.validate()?,
        KerningMethod::Fontforge(settings) => settings.validate()?,
    }
    if matches!(method,KerningMethod::Fontforge(settings) if settings.strength == 0.0)
        || matches!(method,KerningMethod::HuHersch(settings) if settings.strength == 0.0)
    {
        // The method's disabled endpoint is exact Source identity, without
        // source geometry, calibration, rounding or feasibility work.
        return Ok(());
    }
    let font = crate::open_font(data)?;
    let location = font.axes().location(
        config
            .axes
            .iter()
            .map(|(tag, value)| (tag.as_str(), *value)),
    );
    let units_per_em = font.metrics(Size::unscaled(), &location).units_per_em;
    let ascender = font.metrics(Size::new(config.size_px), &location).ascent;
    let ascender_26_6 = crate::fixed(ascender, crate::MetricRounding::Subpixel);
    let context = MethodContext {
        glyphs,
        records,
        source_commands: &analysis.source_commands,
        source_advances_26_6: &analysis.source_advances_26_6,
        source_pairs_26_6: &analysis.source_pairs_26_6,
        advances_26_6: &metrics.advances_26_6,
        pair_adjustments_26_6: &metrics.pair_adjustments_26_6,
        output_bits: config.output_bits,
        units_per_em,
        size_px: f64::from(config.size_px),
        ascender_26_6,
        properties,
        source_kerning: config.kerning,
    };
    let pairs = match method {
        KerningMethod::Source => unreachable!("source returned before preparation"),
        KerningMethod::Typefacet(settings) => resolve_typefacet(&context, &settings)?,
        KerningMethod::HuHersch(settings) => {
            hu_hersch::resolve(&context, &analysis.calibration, &settings)?
        }
        KerningMethod::Fontforge(settings) => fontforge::resolve(&context, &settings)?,
    };
    commit_pair_decisions(glyphs, metrics, pairs)
}

fn commit_pair_decisions(
    glyphs: &[Glyph],
    metrics: &mut FinalizedBitmapMetrics,
    pairs: PairAdjustments,
) -> Result<(), Error> {
    let expected = glyphs
        .len()
        .checked_mul(glyphs.len())
        .ok_or_else(|| fail("kerning pair domain overflow"))?;
    if pairs.len() != expected
        || glyphs.iter().any(|left| {
            glyphs
                .iter()
                .any(|right| !pairs.contains_key(&(left.codepoint, right.codepoint)))
        })
        || pairs.values().any(|decision| match decision {
            PairDecision::RetainSource(reason) => reason.is_empty(),
            PairDecision::Replace(adjustment) => adjustment % 64 != 0,
        })
    {
        return Err(fail(
            "kerning method returned an incomplete pair-decision table",
        ));
    }
    for (pair, decision) in pairs {
        match decision {
            PairDecision::RetainSource(_) => {}
            PairDecision::Replace(0) => {
                metrics.pair_adjustments_26_6.remove(&pair);
            }
            PairDecision::Replace(adjustment) => {
                metrics.pair_adjustments_26_6.insert(pair, adjustment);
            }
        }
    }
    Ok(())
}

fn resolve_typefacet(
    context: &MethodContext<'_>,
    settings: &TypefacetSettings,
) -> Result<PairAdjustments, Error> {
    let glyphs = context.glyphs;
    let records = context.records;
    let properties = context.properties;
    let scope = placement::participating_codepoints(
        glyphs.iter().map(|g| g.codepoint),
        properties.tabular_digits,
    );
    let mut decisions = HashMap::new();
    for left in glyphs {
        for right in glyphs {
            let reason = if char::from_u32(left.codepoint).is_some_and(char::is_whitespace)
                || char::from_u32(right.codepoint).is_some_and(char::is_whitespace)
            {
                "whitespace"
            } else if properties.tabular_digits
                && (0x30..=0x39).contains(&left.codepoint)
                && (0x30..=0x39).contains(&right.codepoint)
            {
                "source_tabular_digits"
            } else {
                "empty_geometry"
            };
            decisions.insert(
                (left.codepoint, right.codepoint),
                PairDecision::RetainSource(reason),
            );
        }
    }
    if scope.is_empty() {
        return Ok(decisions);
    }
    let unit = f64::from(context.units_per_em) / context.size_px;
    // These adapters retain TypeFacet's previous exact geometry and search.
    // They do not define another method's geometry or feasibility policy.
    let (geometry, feasibility) = if records.first().is_some_and(|r| r.output_bits == 1) {
        (
            geometry::delivered_cells(
                glyphs.iter().filter(|g| scope.contains(&g.codepoint)),
                unit,
            )?,
            placement::Feasibility::BinaryCells,
        )
    } else {
        (
            geometry::fitted_outlines(
                records.iter().filter(|r| scope.contains(&r.codepoint)),
                unit,
            )?,
            placement::Feasibility::ProfileBounds,
        )
    };
    let prepared = typefacet::prepare(
        &geometry,
        context.units_per_em,
        f64::from(context.ascender_26_6) / 64.0 * unit,
        settings,
    )?;
    let replacements = placement::resolve(
        &prepared,
        glyphs,
        context.advances_26_6,
        unit,
        placement::Policy {
            feasibility,
            preserve_tabular_digits: properties.tabular_digits,
        },
    )?;
    for (pair, adjustment) in replacements {
        decisions.insert(pair, PairDecision::Replace(adjustment));
    }
    Ok(decisions)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(feature = "candidate")]
    #[test]
    fn zero_hu_strength_requires_no_font_or_auxiliary_analysis() {
        let method = KerningMethod::HuHersch(HuHerschSettings { strength: 0.0 });
        let plan = AnalysisPlan::new(&[], method, &Config::default()).unwrap();
        assert!(plan.classes.is_empty());
        assert!(!plan.source_geometry);
        assert!(AnalysisPlan::new(
            &[],
            KerningMethod::HuHersch(Default::default()),
            &Config::default()
        )
        .is_err());
    }

    #[test]
    fn completed_tables_are_atomic_and_zero_is_an_explicit_replacement() {
        let glyph = Glyph {
            codepoint: 97,
            glyph_id: 1,
            advance_26_6: 128,
            left: 0,
            top: 0,
            width: 0,
            height: 0,
            pixels: Vec::new(),
        };
        let glyphs = [glyph];
        let mut metrics = FinalizedBitmapMetrics {
            advances_26_6: HashMap::from([(97, 128)]),
            pair_adjustments_26_6: HashMap::from([((97, 97), 64)]),
            source_kern_26_6: HashMap::new(),
        };
        for invalid in [
            HashMap::new(),
            HashMap::from([((97, 97), PairDecision::Replace(1))]),
            HashMap::from([((97, 97), PairDecision::RetainSource(""))]),
        ] {
            assert!(commit_pair_decisions(&glyphs, &mut metrics, invalid).is_err());
            assert_eq!(
                metrics.pair_adjustments_26_6,
                HashMap::from([((97, 97), 64)])
            );
        }
        commit_pair_decisions(
            &glyphs,
            &mut metrics,
            HashMap::from([((97, 97), PairDecision::RetainSource("empty_geometry"))]),
        )
        .unwrap();
        assert_eq!(metrics.pair_adjustments_26_6[&(97, 97)], 64);
        commit_pair_decisions(
            &glyphs,
            &mut metrics,
            HashMap::from([((97, 97), PairDecision::Replace(0))]),
        )
        .unwrap();
        assert!(metrics.pair_adjustments_26_6.is_empty());
        assert_eq!(metrics.advances_26_6[&97], 128);
    }
}
