//! Capture exact source outlines and maintained bitmap-placement inputs.
//! The optical solver lives outside this adapter and never changes production.

use font_generator::{
    candidate,
    layout_spacing::finalize_bitmap_metrics,
    mono_spacing::font_spacing_properties,
    probe::{FittedCommand, FittedPen},
    reference::ReferenceRequest,
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting, MetricRounding, MonoRasterSettings,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use skrifa::{
    instance::Size,
    outline::{pen::PathStyle, DrawSettings},
    FontRef, MetadataProvider,
};
use std::{
    collections::{BTreeMap, HashMap},
    error::Error,
    path::Path,
};

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn invalid(message: impl Into<String>) -> Box<dyn Error> {
    std::io::Error::new(std::io::ErrorKind::InvalidInput, message.into()).into()
}

fn default_pipeline() -> RenderPipeline {
    RenderPipeline {
        fitting: StemFittingStrategy::FontHintsAuto,
        rasterization: Rasterization::FreeTypeMonoTerminals,
        diagonal_fitting: true,
    }
}

fn default_mono_raster() -> MonoRasterSettings {
    // Match the working explicit-pipeline preview, whose terminal scan stage
    // requires stub rescue to be enabled. Config's general default differs.
    MonoRasterSettings {
        include_stubs: true,
        font_instructions: true,
        ..Default::default()
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    font_path: String,
    size_px: f32,
    #[serde(default)]
    axes: BTreeMap<String, f32>,
    characters: String,
    #[serde(default = "default_pipeline")]
    pipeline: RenderPipeline,
    #[serde(default = "default_mono_raster")]
    mono_raster: MonoRasterSettings,
}

#[derive(Serialize)]
struct Pair {
    left: u32,
    right: u32,
    adjustment_px: f64,
}

fn pairs(values: &HashMap<(u32, u32), i32>) -> Vec<Pair> {
    let mut pairs: Vec<_> = values
        .iter()
        .map(|(&(left, right), &adjustment)| Pair {
            left,
            right,
            adjustment_px: f64::from(adjustment) / 64.0,
        })
        .collect();
    pairs.sort_by_key(|pair| (pair.left, pair.right));
    pairs
}

fn finite_commands(commands: &[FittedCommand]) -> bool {
    commands.iter().all(|command| match *command {
        FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) => {
            [x, y].iter().all(|value| value.is_finite())
        }
        FittedCommand::QuadTo(x1, y1, x, y) => [x1, y1, x, y].iter().all(|value| value.is_finite()),
        FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
            [x1, y1, x2, y2, x, y].iter().all(|value| value.is_finite())
        }
        FittedCommand::Close => true,
    })
}

const CALIBRATION_CODEPOINTS: [u32; 3] = [110, 72, 48];

fn source_reference(
    data: &[u8],
    source_settings: &Config,
    source: &font_generator::GeneratedFont,
    glyphs: &[serde_json::Value],
    codepoint: u32,
) -> serde_json::Value {
    let unavailable = |status: &str, diagnostic: String| serde_json::json!({"codepoint": codepoint, "status": status, "diagnostic": diagnostic});
    if let Some(glyph) = glyphs.iter().find(|glyph| glyph["codepoint"] == codepoint) {
        // Main generation validates every ordered pair, including repeats; its
        // sparse kerning output omits exactly-zero adjustments.
        let adjustment = source
            .kerning
            .iter()
            .find(|pair| pair.left == codepoint && pair.right == codepoint)
            .map_or(0, |pair| pair.adjustment_26_6);
        return serde_json::json!({
            "codepoint": codepoint,
            "status": "available",
            "glyph_id": glyph["glyph_id"],
            "source_commands": glyph["source_commands"],
            "source_advance_px": glyph["source_advance_px"],
            "source_pair_adjustment_px": f64::from(adjustment) / 64.0,
        });
    }
    let font = match FontRef::new(data) {
        Ok(font) => font,
        Err(error) => return unavailable("source_font_error", error.to_string()),
    };
    let character = char::from_u32(codepoint).expect("fixed calibration scalar");
    if font
        .charmap()
        .map(character)
        .is_none_or(|gid| gid.to_u32() == 0)
    {
        return unavailable(
            "missing_glyph",
            format!("missing source glyph U+{codepoint:04X}"),
        );
    }
    let mut settings = source_settings.clone();
    settings.characters = character.to_string();
    // A singleton repertoire validates only its self pair, avoiding interactions
    // with the requested repertoire. generate also rasterizes a diagnostic
    // source strike internally; none of those bitmap fields enter this block.
    let reference = match font_generator::generate(data, &settings) {
        Ok(reference) => reference,
        Err(error) => return unavailable("source_capture_error", error.to_string()),
    };
    if reference.source_sha256 != source.source_sha256 {
        return unavailable(
            "source_identity_mismatch",
            "reference font identity differs".into(),
        );
    }
    let Some(glyph) = reference
        .glyphs
        .iter()
        .find(|glyph| glyph.codepoint == codepoint)
    else {
        return unavailable(
            "missing_glyph",
            "source capture contains no reference glyph".into(),
        );
    };
    let outlines = font.outline_glyphs();
    let Some(outline) = outlines.get(skrifa::GlyphId::new(glyph.glyph_id)) else {
        return unavailable("missing_outline", "source reference has no outline".into());
    };
    let location = font.axes().location(
        settings
            .axes
            .iter()
            .map(|(tag, value)| (tag.as_str(), *value)),
    );
    let mut pen = FittedPen::default();
    if let Err(error) = outline.draw(
        DrawSettings::unhinted(Size::unscaled(), &location).with_path_style(PathStyle::HarfBuzz),
        &mut pen,
    ) {
        return unavailable("outline_draw_error", error.to_string());
    }
    if !finite_commands(pen.commands()) {
        return unavailable(
            "nonfinite_outline",
            "source reference contains non-finite coordinates".into(),
        );
    }
    let adjustment = reference
        .kerning
        .iter()
        .find(|pair| pair.left == codepoint && pair.right == codepoint)
        .map_or(0, |pair| pair.adjustment_26_6);
    serde_json::json!({
        "codepoint": codepoint,
        "status": "available",
        "glyph_id": glyph.glyph_id,
        "source_commands": pen.commands(),
        "source_advance_px": f64::from(glyph.advance_26_6) / 64.0,
        "source_pair_adjustment_px": f64::from(adjustment) / 64.0,
    })
}

fn capture(data: &[u8], request: &Request) -> Result<serde_json::Value> {
    // Source advances/pairs intentionally use the existing scalar-layout policy,
    // not a second shaper with subtly different substitutions or quantization.
    let source_settings = Config {
        size_px: request.size_px,
        axes: request.axes.clone(),
        characters: request.characters.clone(),
        hinting: Hinting::None,
        metric_rounding: MetricRounding::Subpixel,
        kerning: true,
        ..Default::default()
    };
    let source = font_generator::generate(data, &source_settings)?;
    let mut produced_settings = source_settings.clone();
    produced_settings.hinting = request.pipeline.fitting.hinting();
    produced_settings.mono_raster = request.mono_raster;
    let produced = candidate::render_with_pipeline(
        data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: StemFittingStrategy::extension(Some(request.pipeline.fitting)).into(),
            settings: produced_settings.clone(),
        },
        request.pipeline,
    )?;
    if source.source_sha256 != produced.source_sha256
        || !source.missing_codepoints.is_empty()
        || !produced.missing_codepoints.is_empty()
        || source.glyphs.len() != produced.records.len()
    {
        return Err(invalid("source and produced capture identities disagree"));
    }
    let source_advances: HashMap<_, _> = source
        .glyphs
        .iter()
        .map(|glyph| (glyph.codepoint, glyph.advance_26_6))
        .collect();
    let source_pairs: HashMap<_, _> = source
        .kerning
        .iter()
        .map(|pair| ((pair.left, pair.right), pair.adjustment_26_6))
        .collect();
    let properties = font_spacing_properties(data, &source_settings)?;
    let metrics_on = finalize_bitmap_metrics(
        &produced.records,
        &source_advances,
        &source_pairs,
        true,
        properties.monospace,
        properties.tabular_digits,
    );
    let metrics_off = finalize_bitmap_metrics(
        &produced.records,
        &source_advances,
        &source_pairs,
        false,
        properties.monospace,
        properties.tabular_digits,
    );
    let font = FontRef::new(data)?;
    let location = font.axes().location(
        request
            .axes
            .iter()
            .map(|(tag, value)| (tag.as_str(), *value)),
    );
    let units_per_em = font.metrics(Size::unscaled(), &location).units_per_em;
    if units_per_em == 0 {
        return Err(invalid("source font has zero units per em"));
    }
    let outlines = font.outline_glyphs();
    let mut glyphs = Vec::with_capacity(produced.records.len());
    for record in &produced.records {
        let source_glyph = source
            .glyphs
            .iter()
            .find(|glyph| glyph.codepoint == record.codepoint && glyph.glyph_id == record.glyph_id)
            .ok_or_else(|| {
                invalid(format!(
                    "source glyph identity mismatch U+{:04X}",
                    record.codepoint
                ))
            })?;
        let outline = outlines
            .get(skrifa::GlyphId::new(record.glyph_id))
            .ok_or_else(|| invalid(format!("missing source outline U+{:04X}", record.codepoint)))?;
        let mut pen = FittedPen::default();
        // Match fitting_source's continuous design-unit path: no scaled 26.6
        // draw or inverse scaling before the FontForge envelope flooring.
        outline.draw(
            DrawSettings::unhinted(Size::unscaled(), &location)
                .with_path_style(PathStyle::HarfBuzz),
            &mut pen,
        )?;
        if !finite_commands(pen.commands()) || !finite_commands(&record.fitted_commands) {
            return Err(invalid(format!(
                "non-finite outline U+{:04X}",
                record.codepoint
            )));
        }
        if record
            .hinted_advance_width
            .is_some_and(|value| !value.is_finite())
            || record.hinted_lsb.is_some_and(|value| !value.is_finite())
        {
            return Err(invalid(format!(
                "non-finite fitted metrics U+{:04X}",
                record.codepoint
            )));
        }
        glyphs.push(serde_json::json!({
            "codepoint": record.codepoint,
            "glyph_id": record.glyph_id,
            "source_commands": pen.commands(),
            "produced_commands": record.fitted_commands,
            "source_advance_px": f64::from(source_glyph.advance_26_6) / 64.0,
            "finalized_advance_px": f64::from(metrics_on.advances_26_6[&record.codepoint]) / 64.0,
            "side_bearing_deltas_26_6": record.side_bearing_deltas_26_6,
            "hinted_lsb_px": record.hinted_lsb,
            "hinted_advance_width_px": record.hinted_advance_width,
            "bitmap": {
                "left": record.left, "top": record.top,
                "width": record.width, "height": record.height,
                "pixels": record.pixels,
            },
        }));
    }
    let references: Vec<_> = CALIBRATION_CODEPOINTS
        .iter()
        .map(|&codepoint| source_reference(data, &source_settings, &source, &glyphs, codepoint))
        .collect();
    Ok(serde_json::json!({
        "schema_version": "contextual-spacing-capture-v1",
        "source_sha256": source.source_sha256,
        "font_path": request.font_path,
        "size_px": request.size_px,
        "axes": request.axes,
        "units_per_em": units_per_em,
        "pipeline": request.pipeline,
        "source_settings": source_settings,
        "produced_settings": produced_settings,
        "coordinates": {
            "source_commands": "font design units, baseline-relative, y-up; continuous variation deltas; no pixel scaling",
            "produced_commands": "pixels, baseline-relative, y-up",
            "bitmap": "pixels, baseline-relative left/top, y-down; row-major unpacked ink levels",
        },
        "source_metric_quantization": {
            "policy": "maintained generate: Hinting::None, MetricRounding::Subpixel, kerning=true",
            "unit_px": 1.0 / 64.0,
            "rounding": "nearest 1/64 pixel, half ties away from zero; source advances use variation-aware Skrifa metrics, pairs use HarfRust scalar pair shaping",
            "outline_quantization": "none before estimator; source geometry is independent of metric quantization",
        },
        "adapter_identity": {
            "name": env!("CARGO_PKG_NAME"),
            "version": env!("CARGO_PKG_VERSION"),
            "skrifa_version": "0.48.0",
            "dependency_lock_sha256": format!("{:x}", Sha256::digest(include_bytes!("../Cargo.lock"))),
        },
        "monospace": properties.monospace,
        "tabular_digits": properties.tabular_digits,
        "metrics": produced.metrics,
        "glyphs": glyphs,
        "source_calibration": {
            "schema_version": "contextual-spacing-source-calibration-v1",
            "references": references,
            "provenance": {
                "reference_policy": "fixed source self-pairs: nn lowercase, HH uppercase, 00 experimental numeral anchor; independent of requested repertoire and runtime kerning strength",
                "reference_codepoints": CALIBRATION_CODEPOINTS,
                "source_sha256": source.source_sha256,
                "size_px": request.size_px,
                "axes": request.axes,
                "outline_policy": "Skrifa 0.48.0 unhinted unscaled HarfBuzz path; continuous design units, baseline-relative y-up",
                "metric_policy": "maintained generate: Hinting::None, MetricRounding::Subpixel, kerning=true; full self-pair source kerning",
                "metric_unit_px": 1.0 / 64.0,
                "metric_rounding": "nearest 1/64 pixel, half ties away from zero",
                "adapter_dependency_lock_sha256": format!("{:x}", Sha256::digest(include_bytes!("../Cargo.lock"))),
                "capture_policy": "reuse main source records when present; otherwise generate each available reference as a separate singleton source repertoire; no produced reference glyphs or pair-domain expansion",
                "timing_caveat": "source-only generate calls also rasterize diagnostic source strikes internally; capture timing includes that work, but reference bitmaps are not emitted",
            },
        },
        "source_pairs": pairs(&source_pairs),
        "metric_pairs_on": pairs(&metrics_on.pair_adjustments_26_6),
        "metric_pairs_off": pairs(&metrics_off.pair_adjustments_26_6),
        "capture": produced,
    }))
}

fn run(args: &[String]) -> Result<()> {
    let (grayscale, request_path, output_path) = match args {
        [request, output] => (false, request, output),
        [mode, request, output] if mode == "--grayscale" => (true, request, output),
        _ => {
            return Err(invalid(
                "usage: contextual-spacing-capture [--grayscale] REQUEST.json OUTPUT.json",
            ))
        }
    };
    let request: Request = serde_json::from_slice(&std::fs::read(request_path)?)?;
    let input = std::fs::canonicalize(&request.font_path)?;
    let output = Path::new(output_path);
    let output_name = output
        .file_name()
        .ok_or_else(|| invalid("output must name a file"))?;
    let parent = output
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    std::fs::create_dir_all(parent)?;
    let output_identity = if output.exists() {
        std::fs::canonicalize(output)?
    } else {
        std::fs::canonicalize(parent)?.join(output_name)
    };
    if output_identity == input || output_identity == std::fs::canonicalize(request_path)? {
        return Err(invalid(
            "output must not overwrite the source font or request",
        ));
    }
    let data = std::fs::read(input)?;
    let result = if grayscale {
        capture_grayscale(&data, &request)?
    } else {
        capture(&data, &request)?
    };
    std::fs::write(output, serde_json::to_vec(&result)?)?;
    Ok(())
}

fn capture_grayscale(data: &[u8], request: &Request) -> Result<serde_json::Value> {
    // Vanilla generate preserves source-linear advances and kerning in 26.6.
    // Do not pass through the candidate bitmap-metric finalization policy.
    let settings = Config {
        size_px: request.size_px,
        axes: request.axes.clone(),
        characters: request.characters.clone(),
        output_bits: 3,
        ..Default::default()
    };
    let mut generated = font_generator::generate(data, &settings)?;
    if !generated.missing_codepoints.is_empty() {
        return Err(invalid("grayscale capture has missing codepoints"));
    }
    // Keep the existing default Gray coverage path. Only its layout changes:
    // take vanilla source metrics above, without finalizing bitmap advances.
    let rendered = candidate::render_with_rasterization(
        data,
        &ReferenceRequest {
            profile: "gray_3bit".into(),
            extensions: StemFittingStrategy::extension(Some(StemFittingStrategy::FontHintsFirst))
                .into(),
            settings: settings.clone(),
        },
        Rasterization::FreeTypeMono,
    )?;
    if rendered.source_sha256 != generated.source_sha256
        || rendered.records.len() != generated.glyphs.len()
    {
        return Err(invalid("grayscale rendering and source metrics disagree"));
    }
    for glyph in &mut generated.glyphs {
        let record = rendered
            .records
            .iter()
            .find(|record| record.codepoint == glyph.codepoint && record.glyph_id == glyph.glyph_id)
            .ok_or_else(|| invalid("grayscale glyph identity mismatch"))?;
        glyph.left = record.left;
        glyph.top = record.top;
        glyph.width = record.width;
        glyph.height = record.height;
        glyph.pixels = record.pixels.clone();
    }
    Ok(serde_json::json!({
        "schema_version": "contextual-spacing-grayscale-v2",
        "font_path": request.font_path,
        "policy": "unchanged default Gray coverage from candidate::render_with_rasterization; vanilla generate source-linear advances and full kerning in 26.6, accumulated without per-glyph rounding; native surface draw origins round with floor(x + 0.5); no bitmap spacing, optical correction or tracking",
        "spacing_policy": "source_linear_26_6",
        "font": generated,
    }))
}

fn main() -> Result<()> {
    run(&std::env::args().skip(1).collect::<Vec<_>>())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn grayscale_retains_vanilla_fractional_metrics_and_ignores_mono_overrides() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../fonts/Literata.ttf");
        let mut request: Request = serde_json::from_value(serde_json::json!({
            "font_path": path, "size_px": 16, "axes": {"wght": 400, "opsz": 16},
            "characters": " AVnoé",
        }))
        .unwrap();
        let data = std::fs::read(path).unwrap();
        let captured = capture_grayscale(&data, &request).unwrap();
        let expected = font_generator::generate(
            &data,
            &Config {
                size_px: request.size_px,
                axes: request.axes.clone(),
                characters: request.characters.clone(),
                output_bits: 3,
                ..Default::default()
            },
        )
        .unwrap();
        assert_eq!(
            captured["font"]["kerning"],
            serde_json::to_value(&expected.kerning).unwrap()
        );
        let bitmap_control =
            candidate::generate_bitmap_font(&data, &expected.config, None).unwrap();
        for (glyph, source) in captured["font"]["glyphs"]
            .as_array()
            .unwrap()
            .iter()
            .zip(&expected.glyphs)
        {
            assert_eq!(glyph["advance_26_6"], source.advance_26_6);
            let control = bitmap_control
                .glyphs
                .iter()
                .find(|g| g.codepoint == source.codepoint)
                .unwrap();
            assert_eq!(
                glyph["pixels"],
                serde_json::to_value(&control.pixels).unwrap()
            );
            assert_eq!(glyph["left"], control.left);
            assert_eq!(glyph["top"], control.top);
            assert_eq!(glyph["width"], control.width);
            assert_eq!(glyph["height"], control.height);
        }
        assert!(expected
            .glyphs
            .iter()
            .any(|glyph| glyph.advance_26_6 % 64 != 0));
        assert!(expected
            .kerning
            .iter()
            .any(|pair| pair.adjustment_26_6 % 64 != 0));
        assert!(expected
            .glyphs
            .iter()
            .flat_map(|glyph| &glyph.pixels)
            .any(|&ink| ink > 0 && ink < 7));
        request.mono_raster = MonoRasterSettings::default();
        request.pipeline = RenderPipeline {
            fitting: StemFittingStrategy::UpstreamMono,
            rasterization: Rasterization::FreeTypeMono,
            diagonal_fitting: false,
        };
        assert_eq!(captured, capture_grayscale(&data, &request).unwrap());
    }

    #[test]
    fn rejects_unknown_fields_and_invalid_cli() {
        assert!(run(&[]).is_err());
        assert!(serde_json::from_value::<Request>(serde_json::json!({
            "font_path": "font.ttf", "size_px": 16,
            "characters": "AV", "unrecognized": true,
        }))
        .is_err());
        for mono_raster in [
            serde_json::json!({"dropout": "unknown"}),
            serde_json::json!({"unknown": true}),
        ] {
            assert!(serde_json::from_value::<Request>(serde_json::json!({
                "font_path": "font.ttf", "size_px": 16,
                "characters": "AV", "mono_raster": mono_raster,
            }))
            .is_err());
        }
    }

    #[test]
    fn default_scan_matches_working_preview_and_explicit_overrides_are_retained() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../fonts/RobotoFlex.ttf");
        let request_json = serde_json::json!({
            "font_path": path, "size_px": 16, "characters": "tf",
            "pipeline": {
                "fitting": "font_hints_auto", "rasterization": "free_type_mono_terminals",
                "diagonal_fitting": false,
            },
        });
        let request: Request = serde_json::from_value(request_json.clone()).unwrap();
        let working_scan = serde_json::json!({
            "dropout": "smart", "include_stubs": true, "font_instructions": true,
        });
        assert_eq!(
            serde_json::to_value(request.mono_raster).unwrap(),
            working_scan
        );
        let data = std::fs::read(path).unwrap();
        let result = capture(&data, &request).unwrap();
        assert_eq!(result["produced_settings"]["mono_raster"], working_scan);
        assert_eq!(
            result["source_settings"]["mono_raster"],
            serde_json::to_value(MonoRasterSettings::default()).unwrap()
        );
        for record in result["capture"]["records"].as_array().unwrap() {
            assert_eq!(record["mono_raster"], working_scan);
            assert_eq!(record["raster_policy"], "free_type_mono_terminals");
        }
        let mut explicit_json = request_json.clone();
        explicit_json["mono_raster"] = working_scan;
        let explicit: Request = serde_json::from_value(explicit_json).unwrap();
        assert_eq!(result, capture(&data, &explicit).unwrap());

        // Explicit manual settings reproduce the old adapter policy; preserve
        // the renderer's actual fallback label rather than relabelling it.
        let mut old_json = request_json;
        let old_scan = serde_json::to_value(MonoRasterSettings::default()).unwrap();
        old_json["mono_raster"] = old_scan.clone();
        let old_request: Request = serde_json::from_value(old_json).unwrap();
        let old = capture(&data, &old_request).unwrap();
        assert_eq!(old["produced_settings"]["mono_raster"], old_scan);
        assert_eq!(old["source_calibration"], result["source_calibration"]);
        assert_eq!(old["source_settings"], result["source_settings"]);
        assert_eq!(old["source_pairs"], result["source_pairs"]);
        for (before, after) in old["capture"]["records"]
            .as_array()
            .unwrap()
            .iter()
            .zip(result["capture"]["records"].as_array().unwrap())
        {
            assert_eq!(before["mono_raster"], old_scan);
            assert_eq!(before["raster_policy"], "free_type_mono");
            assert_eq!(before["fitted_commands"], after["fitted_commands"]);
        }
    }

    #[test]
    fn capture_preserves_bitmap_identity_and_source_units() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../fonts/Roboto.ttf");
        let request = Request {
            font_path: path.to_string_lossy().into_owned(),
            size_px: 16.0,
            axes: BTreeMap::new(),
            characters: " AV01".into(),
            pipeline: RenderPipeline {
                diagonal_fitting: false,
                ..default_pipeline()
            },
            mono_raster: default_mono_raster(),
        };
        let data = std::fs::read(&request.font_path).unwrap();
        let result = capture(&data, &request).unwrap();
        assert_eq!(result["schema_version"], "contextual-spacing-capture-v1");
        let glyphs = result["glyphs"].as_array().unwrap();
        let records = result["capture"]["records"].as_array().unwrap();
        assert_eq!(glyphs.len(), 5);
        assert_eq!(glyphs[0]["codepoint"], 32);
        assert_eq!(glyphs[0]["bitmap"]["width"], 0);
        for (glyph, record) in glyphs.iter().zip(records) {
            for key in ["left", "top", "width", "height", "pixels"] {
                assert_eq!(glyph["bitmap"][key], record[key]);
            }
            assert_eq!(glyph["produced_commands"], record["fitted_commands"]);
        }
        let a = glyphs
            .iter()
            .find(|glyph| glyph["codepoint"] == 65)
            .unwrap();
        let max_source_y = a["source_commands"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|command| command["y"].as_f64())
            .fold(0.0_f64, f64::max);
        assert!(
            max_source_y > 100.0,
            "source outline must retain design units"
        );
        let repeat = capture(&data, &request).unwrap();
        assert_eq!(result, repeat, "capture output must be deterministic");
        let invalid_request = Request {
            characters: "\u{0301}".into(),
            ..request
        };
        assert!(capture(&data, &invalid_request).is_err());
    }

    #[test]
    fn auxiliary_references_preserve_requested_domain_and_source_identity() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../fonts/Roboto.ttf");
        let request = Request {
            font_path: path.to_string_lossy().into_owned(),
            size_px: 16.0,
            axes: BTreeMap::from([("wght".into(), 700.0)]),
            characters: "AV".into(),
            pipeline: RenderPipeline {
                diagonal_fitting: false,
                ..default_pipeline()
            },
            mono_raster: default_mono_raster(),
        };
        let data = std::fs::read(&request.font_path).unwrap();
        let result = capture(&data, &request).unwrap();
        let main_glyphs = result["glyphs"].as_array().unwrap();
        assert_eq!(main_glyphs.len(), 2);
        assert_eq!(result["capture"]["records"].as_array().unwrap().len(), 2);
        assert_eq!(result["source_settings"]["characters"], "AV");
        for key in ["source_pairs", "metric_pairs_on", "metric_pairs_off"] {
            for pair in result[key].as_array().unwrap() {
                assert!([65, 86].contains(&pair["left"].as_u64().unwrap()));
                assert!([65, 86].contains(&pair["right"].as_u64().unwrap()));
            }
        }
        let calibration = &result["source_calibration"];
        assert_eq!(
            calibration["schema_version"],
            "contextual-spacing-source-calibration-v1"
        );
        assert_eq!(
            calibration["provenance"]["source_sha256"],
            result["source_sha256"]
        );
        assert_eq!(calibration["provenance"]["axes"], result["axes"]);
        assert_eq!(calibration["provenance"]["metric_unit_px"], 1.0 / 64.0);
        let references = calibration["references"].as_array().unwrap();
        assert_eq!(references.len(), CALIBRATION_CODEPOINTS.len());
        let font = FontRef::new(&data).unwrap();
        let location = font.axes().location(
            request
                .axes
                .iter()
                .map(|(tag, value)| (tag.as_str(), *value)),
        );
        let outlines = font.outline_glyphs();
        for (&codepoint, reference) in CALIBRATION_CODEPOINTS.iter().zip(references) {
            assert_eq!(reference["codepoint"], codepoint);
            assert_eq!(reference["status"], "available");
            assert!(reference.get("bitmap").is_none());
            assert!(reference.get("produced_commands").is_none());
            let settings = Config {
                size_px: request.size_px,
                axes: request.axes.clone(),
                characters: char::from_u32(codepoint).unwrap().to_string(),
                hinting: Hinting::None,
                metric_rounding: MetricRounding::Subpixel,
                kerning: true,
                ..Default::default()
            };
            let expected = font_generator::generate(&data, &settings).unwrap();
            let glyph = &expected.glyphs[0];
            assert_eq!(reference["glyph_id"], glyph.glyph_id);
            assert_eq!(
                reference["source_advance_px"],
                f64::from(glyph.advance_26_6) / 64.0
            );
            let adjustment = expected
                .kerning
                .iter()
                .find(|pair| pair.left == codepoint && pair.right == codepoint)
                .map_or(0, |pair| pair.adjustment_26_6);
            assert_eq!(
                reference["source_pair_adjustment_px"],
                f64::from(adjustment) / 64.0
            );
            let mut pen = FittedPen::default();
            outlines
                .get(skrifa::GlyphId::new(glyph.glyph_id))
                .unwrap()
                .draw(
                    DrawSettings::unhinted(Size::unscaled(), &location)
                        .with_path_style(PathStyle::HarfBuzz),
                    &mut pen,
                )
                .unwrap();
            assert_eq!(
                reference["source_commands"],
                serde_json::to_value(pen.commands()).unwrap()
            );
            assert!(
                pen.commands().iter().any(|command| match command {
                    FittedCommand::MoveTo(x, y) | FittedCommand::LineTo(x, y) =>
                        x.abs().max(y.abs()) > 100.0,
                    _ => false,
                }),
                "reference commands must retain design units"
            );
        }
        // An unavailable auxiliary reference is data, rather than a failure of
        // the requested capture. No placeholder available geometry is emitted.
        let source_settings: Config =
            serde_json::from_value(result["source_settings"].clone()).unwrap();
        let source = font_generator::generate(&data, &source_settings).unwrap();
        let missing = source_reference(&data, &source_settings, &source, main_glyphs, 0x10ffff);
        assert_eq!(missing["status"], "missing_glyph");
        assert!(missing.get("source_commands").is_none());

        // A reference already in the main repertoire is reused byte-for-byte.
        let with_references = capture(
            &data,
            &Request {
                characters: "nH0".into(),
                ..request
            },
        )
        .unwrap();
        for reference in with_references["source_calibration"]["references"]
            .as_array()
            .unwrap()
        {
            let glyph = with_references["glyphs"]
                .as_array()
                .unwrap()
                .iter()
                .find(|glyph| glyph["codepoint"] == reference["codepoint"])
                .unwrap();
            for key in ["glyph_id", "source_commands", "source_advance_px"] {
                assert_eq!(reference[key], glyph[key]);
            }
        }
    }
}
