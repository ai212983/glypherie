//! Diagnostic capture of source geometry, preview fitting and finalized spacing.
//! No alternative placement model; see docs/revisions/001/03-spacing-kerning.md.
use font_generator::{
    ascii_kerning_pairs, candidate,
    layout_spacing::finalize_bitmap_metrics,
    mono_spacing::font_spacing_properties,
    reference::{reference, ReferenceRequest},
    renderer::RenderPipeline,
    stem_fitting::StemFittingStrategy,
    Config, Hinting,
};
use serde::Deserialize;
use serde_json::json;
use std::{
    collections::HashMap,
    io::{self, BufRead},
};

#[derive(Deserialize)]
struct Input {
    font: String,
    settings: Config,
    pipeline: RenderPipeline,
}

fn capture(input: Input) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let data = std::fs::read(&input.font)?;
    let mut source_config = input.settings.clone();
    source_config.hinting = Hinting::None;
    source_config.mono_raster = Default::default();
    let source = reference(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "none".into(),
            settings: source_config,
        },
    )?;
    let fitted = candidate::render_with_pipeline(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: StemFittingStrategy::extension(Some(input.pipeline.fitting)).into(),
            settings: input.settings.clone(),
        },
        input.pipeline,
    )?;
    let source_advances = source
        .records
        .iter()
        .map(|r| (r.codepoint, r.advance_26_6))
        .collect();
    let kern = ascii_kerning_pairs(&data, input.settings.size_px, &input.settings.axes)?;
    let source_pairs: HashMap<_, _> = kern
        .pairs
        .iter()
        .map(|p| ((p.left, p.right), p.adjustment_26_6))
        .collect();
    let properties = font_spacing_properties(&data, &input.settings)?;
    let finalized = finalize_bitmap_metrics(
        &fitted.records,
        &source_advances,
        &source_pairs,
        input.settings.kerning,
        properties.monospace,
        properties.tabular_digits,
    );
    let mut advances = finalized
        .advances_26_6
        .iter()
        .map(|(cp, value)| json!({"codepoint":cp,"advance_26_6":value}))
        .collect::<Vec<_>>();
    advances.sort_by_key(|v| v["codepoint"].as_u64());
    let mut pairs = finalized
        .pair_adjustments_26_6
        .iter()
        .map(|((a, b), value)| json!({"left":a,"right":b,"adjustment_26_6":value}))
        .collect::<Vec<_>>();
    pairs.sort_by_key(|v| (v["left"].as_u64(), v["right"].as_u64()));
    Ok(
        json!({"font":input.font,"settings":input.settings,"pipeline":input.pipeline,
        "source":source,"fitted":fitted,"source_kerning":kern,
        "finalized_advances":advances,"finalized_pairs":pairs}),
    )
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    for line in io::stdin().lock().lines() {
        println!("{}", capture(serde_json::from_str(&line?)?)?);
    }
    Ok(())
}
