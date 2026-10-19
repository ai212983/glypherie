//! Working Mono candidate: unmodified registry Skrifa fitting, project raster.
//!
//! The default uses Target::Mono + Engine::AutoFallback: font-provided hints
//! when available, otherwise the upstream autohinter. The explicit automatic
//! control forces Engine::Auto. This follows Skrifa's documented FreeType
//! engine selection, without X/Y recombination or custom width corrections.
//! See https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.Engine.html.
//! Fitting is upstream; coverage reduction and dropout remain project raster
//! policies. Gray retains its existing upstream Normal automatic fitting.
use crate::{
    fail,
    layout_spacing::finalize_bitmap_metrics,
    mono_spacing::font_spacing_properties,
    reference::{
        capture_with_policy, CapturePolicy, ReferenceReport, ReferenceRequest, PROFILE_GRAY_3BIT,
        PROFILE_MONO_1BIT,
    },
    stem_fitting::{StemFittingStrategy, EXTENSIONS_FONT_HINTS_FIRST, EXTENSIONS_MONO_WIDTH_01},
    Config, Error, GeneratedFont, Glyph, Hinting, KerningPair,
};
use skrifa::outline::Target;
use std::collections::HashMap;

pub fn render(data: &[u8], request: &ReferenceRequest) -> Result<ReferenceReport, Error> {
    let strategy = match request.extensions.as_str() {
        EXTENSIONS_FONT_HINTS_FIRST => StemFittingStrategy::FontHintsFirst,
        EXTENSIONS_MONO_WIDTH_01 => StemFittingStrategy::UpstreamMono,
        _ => {
            return Err(fail(
                "candidate rendering requires font-hints-01 or mono-width-01",
            ))
        }
    };
    if !matches!(
        request.settings.hinting,
        Hinting::Auto | Hinting::AutoFallback
    ) {
        return Err(fail(
            "candidate fitting requires automatic policy selection",
        ));
    }
    if request.profile == PROFILE_GRAY_3BIT && strategy == StemFittingStrategy::FontHintsFirst {
        let mut upstream = request.clone();
        upstream.extensions = String::from("none");
        upstream.settings.hinting = Hinting::Auto;
        let mut report = crate::reference::reference(data, &upstream)?;
        report.extensions = request.extensions.clone();
        return Ok(report);
    }
    if request.profile != PROFILE_MONO_1BIT {
        return Err(fail("Mono fitting requires profile 'mono_1bit'"));
    }
    if request.settings.output_bits != 1 {
        return Err(fail("profile mono_1bit requires settings.output_bits 1"));
    }
    // Strategy selection explicitly controls the effective automatic policy;
    // normalize before capture so both requested and selected engine metadata
    // describe the actual draw. None/Interpreter never silently enable it.
    let mut effective = request.clone();
    effective.settings.hinting = strategy.hinting();
    let policy = CapturePolicy {
        target: Target::Mono,
        target_name: String::from("mono"),
        smooth_mode: None,
        symmetric_rendering: None,
        preserve_linear_metrics: None,
        dropout: false,
        overlap_4x: true,
        implementation: format!(
            "skrifa-{}:registry:{}",
            request.extensions,
            crate::probe::skrifa_version()
        ),
        fork: false,
        extensions: request.extensions.clone(),
    };
    let selected = match strategy {
        StemFittingStrategy::FontHintsFirst => "auto_fallback",
        StemFittingStrategy::UpstreamMono => "auto",
    };
    capture_with_policy(data, &effective, selected, &policy)
}

/// Generate the working candidate as a bitmap strike.
///
/// This is the maintained candidate counterpart to legacy `generate()`:
/// glyph bitmaps and offsets come from the candidate capture, advances are
/// whole pixels (fitted when available, otherwise the rounded source
/// advance, with a common advance for source-tabular digits), and pair
/// adjustments are sparse whole-pixel values resolved once from source
/// kerning plus any available fitted bearing correction. Consumers add a
/// pair adjustment exactly once for that pair; pen positions accumulated
/// from these metrics are whole pixels at any starting pixel. Only 1-bit
/// Mono and 3-bit Gray strikes are defined; other depths fail explicitly.
/// `strategy` selects the Mono fitting policy and is ignored for Gray,
/// which retains upstream Normal automatic fitting.
pub fn generate_bitmap_font(
    data: &[u8],
    config: &Config,
    strategy: Option<StemFittingStrategy>,
) -> Result<GeneratedFont, Error> {
    let profile = match config.output_bits {
        1 => PROFILE_MONO_1BIT,
        3 => PROFILE_GRAY_3BIT,
        other => {
            return Err(fail(format!(
                "candidate bitmap generation requires output_bits 1 or 3, got {other}"
            )))
        }
    };
    let strategy = strategy.unwrap_or_default();
    let mut effective = config.clone();
    effective.hinting = if config.output_bits == 1 {
        strategy.hinting()
    } else {
        Hinting::Auto
    };
    // Source metrics and kerning are inputs to the bitmap policy, not an
    // alternative layout: prepare them without rasterizing, then take
    // every bitmap from the one candidate capture below.
    let source = crate::source::prepare_source(data, &effective)?;
    let report = render(
        data,
        &ReferenceRequest {
            profile: profile.to_string(),
            extensions: if config.output_bits == 1 {
                StemFittingStrategy::extension(Some(strategy)).to_string()
            } else {
                EXTENSIONS_FONT_HINTS_FIRST.to_string()
            },
            settings: effective.clone(),
        },
    )?;
    let source_advances: HashMap<u32, i32> = source
        .glyphs
        .iter()
        .map(|glyph| (glyph.codepoint, glyph.advance_26_6))
        .collect();
    let source_kern: HashMap<(u32, u32), i32> = source
        .kerning
        .iter()
        .map(|pair| ((pair.left, pair.right), pair.adjustment_26_6))
        .collect();
    let properties = font_spacing_properties(data, &effective)?;
    // The one finalized bitmap table for this strike; preview and
    // specimens resolve the same table from their own captures.
    let metrics = finalize_bitmap_metrics(
        &report.records,
        &source_advances,
        &source_kern,
        config.kerning,
        properties.monospace,
        properties.tabular_digits,
    );
    let mut glyphs = Vec::with_capacity(report.records.len());
    for record in &report.records {
        let advance = metrics
            .advances_26_6
            .get(&record.codepoint)
            .copied()
            .ok_or_else(|| fail(format!("missing bitmap advance U+{:04X}", record.codepoint)))?;
        glyphs.push(Glyph {
            codepoint: record.codepoint,
            glyph_id: record.glyph_id,
            advance_26_6: advance,
            left: record.left,
            top: record.top,
            width: record.width,
            height: record.height,
            pixels: record.pixels.clone(),
        });
    }
    glyphs.sort_by_key(|glyph| glyph.codepoint);
    let mut kerning: Vec<KerningPair> = metrics
        .pair_adjustments_26_6
        .iter()
        .map(|((left, right), adjustment)| KerningPair {
            left: *left,
            right: *right,
            adjustment_26_6: *adjustment,
        })
        .collect();
    kerning.sort_by_key(|pair| (pair.left, pair.right));
    Ok(GeneratedFont {
        source_sha256: report.source_sha256.clone(),
        config: effective,
        metrics: report.metrics.clone(),
        glyphs,
        missing_codepoints: report.missing_codepoints.clone(),
        kerning,
    })
}

#[cfg(test)]
mod tests {
    use super::generate_bitmap_font;
    use crate::{source::raster_counter, stem_fitting::StemFittingStrategy, Config};
    use std::{collections::BTreeMap, path::Path};

    fn roboto() -> Vec<u8> {
        std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf")).unwrap()
    }

    fn config(characters: &str, output_bits: u8) -> Config {
        let mut axes = BTreeMap::new();
        axes.insert("wght".into(), 400.0);
        axes.insert("wdth".into(), 100.0);
        Config {
            size_px: 14.0,
            axes,
            characters: characters.into(),
            output_bits,
            ..Config::default()
        }
    }

    #[test]
    fn candidate_rasterizes_once_per_unique_character_and_never_for_source() {
        let data = roboto();
        // Repeated letters collapse: "hello world" has 8 unique scalars,
        // "oooo" has one.
        for (bits, strategies) in [
            (
                1u8,
                vec![
                    Some(StemFittingStrategy::FontHintsFirst),
                    Some(StemFittingStrategy::UpstreamMono),
                ],
            ),
            (3u8, vec![None]),
        ] {
            for strategy in strategies {
                for (characters, unique) in [("hello world", 8usize), ("oooo", 1usize)] {
                    raster_counter::reset();
                    let font =
                        generate_bitmap_font(&data, &config(characters, bits), strategy).unwrap();
                    assert_eq!(
                        font.glyphs.len(),
                        unique,
                        "bits={bits} strategy={strategy:?} text={characters:?}"
                    );
                    assert_eq!(
                        raster_counter::logical_rasters(),
                        unique,
                        "final raster once per unique character, bits={bits} strategy={strategy:?} text={characters:?}"
                    );
                    assert_eq!(raster_counter::source_geometry_draws(), 0);
                }
            }
        }
    }
}

/// Disabled capture returns the explicit independent reference unchanged.
pub fn capture(
    data: &[u8],
    request: &ReferenceRequest,
    enabled: bool,
) -> Result<ReferenceReport, Error> {
    if !enabled {
        if request.extensions != "none" {
            return Err(fail("disabled candidate capture requires extensions none"));
        }
        return crate::reference::reference(data, request);
    }
    render(data, request)
}
