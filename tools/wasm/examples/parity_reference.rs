//! Native oracle for smoke/parity.mjs. Recomputes the approved renderer's
//! output on each run; no historical pixel snapshots constrain model changes.
use font_generator::surface::{
    render_text, render_text_with_fitting_strategy, HAlign, TextRenderRequest, WrapMode,
};
use font_generator::{metadata, Config};
use font_generator::{renderer::RendererRole, stem_fitting::StemFittingStrategy};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::io::{self, Read};

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let cases: Vec<Value> = serde_json::from_str(&input).unwrap();
    let outputs: Vec<Value> = cases.iter().map(reference).collect();
    println!("{}", serde_json::to_string(&outputs).unwrap());
}

fn reference(case: &Value) -> Value {
    let data = std::fs::read(case["font_file"].as_str().unwrap()).unwrap();
    let spec = &case["spec"];
    let mut config = spec.as_object().unwrap().clone();
    for key in [
        "text",
        "width",
        "height",
        "wrap",
        "align",
        "foreground",
        "background",
        "palette",
        "renderer",
        "stem_fitting",
        "letter_spacing_px",
    ] {
        config.remove(key);
    }
    let config: Config = serde_json::from_value(Value::Object(config)).unwrap();
    let request = TextRenderRequest {
        config,
        text: spec["text"].as_str().unwrap().into(),
        width: spec["width"].as_u64().unwrap().try_into().unwrap(),
        height: spec["height"].as_u64().unwrap().try_into().unwrap(),
        wrap: match spec["wrap"].as_str() {
            Some("clip") => WrapMode::Clip,
            Some("char") => WrapMode::Char,
            _ => WrapMode::Word,
        },
        align: match spec["align"].as_str() {
            Some("right") => HAlign::Right,
            Some("center") => HAlign::Center,
            _ => HAlign::Left,
        },
        foreground: serde_json::from_value(
            spec.get("foreground")
                .cloned()
                .unwrap_or(json!([0, 0, 0, 255])),
        )
        .unwrap(),
        background: serde_json::from_value(
            spec.get("background")
                .cloned()
                .unwrap_or(json!([255, 255, 255, 255])),
        )
        .unwrap(),
        palette: spec
            .get("palette")
            .map(|p| serde_json::from_value(p.clone()).unwrap()),
    };
    let rendered = if let Some(role) = spec.get("renderer") {
        let role: RendererRole = serde_json::from_value(role.clone()).unwrap();
        let strategy: Option<StemFittingStrategy> = spec
            .get("stem_fitting")
            .map(|v| serde_json::from_value(v.clone()).unwrap());
        render_text_with_fitting_strategy(
            &data,
            &request,
            role,
            spec["letter_spacing_px"].as_f64().unwrap_or(0.0) as f32,
            strategy,
        )
    } else {
        render_text(&data, &request)
    };
    match rendered {
        Ok(result) => json!({
            "id": case["id"], "width": result.width, "height": result.height,
            "pixel_sha256": format!("{:x}", Sha256::digest(&result.pixels)),
            "layout": {
                "lines": result.lines.iter().map(|line| json!({
                    "byte_start": line.byte_start, "byte_end": line.byte_end,
                    "width_26_6": line.width_26_6, "height_px": line.height_px,
                })).collect::<Vec<_>>(),
                "missing_codepoints": result.missing_codepoints,
            },
            "metadata": metadata::extract(&data).unwrap(),
        }),
        Err(error) => json!({"id": case["id"], "error": error.to_string()}),
    }
}
