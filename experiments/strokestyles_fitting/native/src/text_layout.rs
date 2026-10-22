//! Thin `text-layout` command: paired-text diagnostics on the exact capture pipeline.
//! Args after the mode word: `--font PATH --chars STRING --text-file PATH --out PATH
//! [--size PX] [--axes JSON]`; `--chars` is printable ASCII and covers every text char.
//! Per mode the strike comes from `candidate::generate_monochrome_font_with_pipeline`
//! with `FreeTypeMonoTerminals` (capture's rasterization) and pen positions from
//! `layout_spacing::SpacingEngine::place`. Contract: `modes.{auto_default,
//! selective_default}` hold `metrics`, whole-pixel `advances`, sparse
//! `pair_adjustments`, `glyphs` (verbatim `left`/`top`, keeping overhangs) and
//! `lines` (`[{text, baseline, placements: [{codepoint, x, advance, pair}]}]`).
//! Coordinates are y-down pixels from the native 26.6 engine; `baseline` starts at
//! `ascent_px` with the surface line pitch and explicit lines only (no wrapping).
//! The compositor chooses the shared origin later.

use font_generator::{
    candidate::generate_monochrome_font_with_pipeline,
    layout_spacing::{EngineInputs, SpacingEngine},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, GeneratedFont, Hinting, MonoRasterSettings,
};
use std::collections::{BTreeMap, HashMap};

fn fail<T>(message: impl Into<String>) -> Result<T, Box<dyn std::error::Error>> {
    Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, message.into()).into())
}

fn missing(name: &str) -> Box<dyn std::error::Error> {
    std::io::Error::new(std::io::ErrorKind::InvalidInput, format!("missing {name}")).into()
}

fn invalid(what: impl Into<String>) -> Box<dyn std::error::Error> {
    std::io::Error::new(
        std::io::ErrorKind::InvalidInput,
        format!("invalid {}", what.into()),
    )
    .into()
}

struct Parsed {
    font: String,
    chars: String,
    text_file: String,
    out: String,
    size: f32,
    axes: BTreeMap<String, f32>,
}

fn flag<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
    args.windows(2)
        .find(|w| w[0] == name)
        .map(|w| w[1].as_str())
}

fn is_printable_ascii(value: &str) -> bool {
    value.bytes().all(|b| (0x20..=0x7E).contains(&b))
}

fn parse(args: &[String]) -> Result<Parsed, Box<dyn std::error::Error>> {
    let font = flag(args, "--font").ok_or_else(|| missing("--font PATH"))?;
    let chars = flag(args, "--chars").ok_or_else(|| missing("--chars STRING"))?;
    let text_file = flag(args, "--text-file").ok_or_else(|| missing("--text-file PATH"))?;
    let out = flag(args, "--out").ok_or_else(|| missing("--out PATH"))?;
    if chars.is_empty() {
        return fail("empty --chars STRING");
    }
    if !is_printable_ascii(chars) {
        return fail("chars must be printable ASCII");
    }
    let size = match flag(args, "--size") {
        Some(text) => text.parse::<f32>().map_err(|_| invalid("--size PX"))?,
        None => 16.0,
    };
    if !size.is_finite() || size <= 0.0 {
        return fail("invalid --size PX");
    }
    let axes: BTreeMap<String, f32> = match flag(args, "--axes") {
        Some(text) => serde_json::from_str(text).map_err(|_| invalid("--axes JSON"))?,
        None => BTreeMap::new(),
    };
    if axes.values().any(|v| !v.is_finite()) {
        return fail("non-finite axis value");
    }
    Ok(Parsed {
        font: font.into(),
        chars: chars.into(),
        text_file: text_file.into(),
        out: out.into(),
        size,
        axes,
    })
}

/// Split text into explicit lines on `\r\n` (one break), `\r` or `\n`.
fn split_lines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let bytes = text.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'\r' {
            lines.push(&text[start..index]);
            index += 1;
            if bytes.get(index) == Some(&b'\n') {
                index += 1;
            }
            start = index;
        } else if bytes[index] == b'\n' {
            lines.push(&text[start..index]);
            index += 1;
            start = index;
        } else {
            index += 1;
        }
    }
    lines.push(&text[start..]);
    lines
}

const MODES: [(&str, StemFittingStrategy, &str); 2] = [
    (
        "auto_default",
        StemFittingStrategy::UpstreamMono,
        "mono-width-01",
    ),
    (
        "selective_default",
        StemFittingStrategy::FontHintsAuto,
        "font-hints-auto-01",
    ),
];

fn config_for(parsed: &Parsed) -> Config {
    Config {
        size_px: parsed.size,
        characters: parsed.chars.clone(),
        axes: parsed.axes.clone(),
        output_bits: 1,
        hinting: Hinting::AutoFallback,
        kerning: true,
        mono_raster: MonoRasterSettings {
            font_instructions: true,
            include_stubs: true,
            ..Default::default()
        },
        ..Config::default()
    }
}

/// Lay out `lines` with the finalized strike's engine; advances stay whole pixels.
fn layout_mode(
    strike: &GeneratedFont,
    lines: &[&str],
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let advances: HashMap<u32, i32> = strike
        .glyphs
        .iter()
        .map(|glyph| (glyph.codepoint, glyph.advance_26_6))
        .collect();
    let pairs: HashMap<(u32, u32), i32> = strike
        .kerning
        .iter()
        .map(|pair| ((pair.left, pair.right), pair.adjustment_26_6))
        .collect();
    // Neutral tracking with no minimum-separation floor: whole-pixel pen
    // positions accumulate the finalized advances plus one pair value each.
    let engine = SpacingEngine::new(EngineInputs {
        advances_26_6: advances.clone(),
        pair_adjustments_26_6: pairs.clone(),
        guard_kern_26_6: HashMap::new(),
        minimum: None,
        mono: true,
        integer_positions: true,
        letter_spacing_px: 0.0,
    })
    .map_err(|error| invalid(error.to_string()))?;
    // Surface line convention: first baseline at ceiled ascent, fixed pitch.
    let ascent_px = (i64::from(strike.metrics.ascent_26_6) + 63).div_euclid(64);
    let line_height_px = ((i64::from(strike.metrics.ascent_26_6)
        - i64::from(strike.metrics.descent_26_6)
        + i64::from(strike.metrics.line_gap_26_6)
        + 63)
        / 64)
        .max(1);
    let mut encoded_lines = Vec::with_capacity(lines.len());
    for (index, text) in lines.iter().enumerate() {
        let baseline = ascent_px + index as i64 * line_height_px;
        let mut pen = 0i64;
        let mut previous = None;
        let mut placements = Vec::new();
        for ch in text.chars() {
            let codepoint = ch as u32;
            let pair = engine.pair_kern(previous, codepoint);
            let (origin, next) = engine
                .place(pen, previous, codepoint)
                .ok_or_else(|| invalid(format!("layout failed for U+{codepoint:04X}")))?;
            let advance = advances
                .get(&codepoint)
                .copied()
                .ok_or_else(|| invalid(format!("missing advance U+{codepoint:04X}")))?;
            placements.push(serde_json::json!({
                "codepoint": codepoint,
                "x": origin.div_euclid(64),
                "x_26_6": origin,
                "advance": advance / 64,
                "pair": pair / 64,
            }));
            pen = next;
            previous = Some(codepoint);
        }
        encoded_lines.push(serde_json::json!({
            "text": text,
            "baseline": baseline,
            "placements": placements,
        }));
    }
    let mut advances_out: Vec<(u32, i32)> = advances
        .iter()
        .map(|(codepoint, advance)| (*codepoint, *advance))
        .collect();
    advances_out.sort_by_key(|(codepoint, _)| *codepoint);
    let mut pairs_out: Vec<((u32, u32), i32)> = pairs
        .iter()
        .map(|((left, right), adjustment)| ((*left, *right), *adjustment))
        .collect();
    pairs_out.sort_by_key(|((left, right), _)| (*left, *right));
    let mut glyphs_out = Vec::with_capacity(strike.glyphs.len());
    for glyph in &strike.glyphs {
        glyphs_out.push(serde_json::json!({
            "codepoint": glyph.codepoint,
            "glyph_id": glyph.glyph_id,
            "advance": glyph.advance_26_6 / 64,
            "left": glyph.left,
            "top": glyph.top,
            "width": glyph.width,
            "height": glyph.height,
        }));
    }
    Ok(serde_json::json!({
        "metrics": {
            "ascent_26_6": strike.metrics.ascent_26_6,
            "descent_26_6": strike.metrics.descent_26_6,
            "line_gap_26_6": strike.metrics.line_gap_26_6,
            "ascent_px": ascent_px,
            "line_height_px": line_height_px,
        },
        "advances": advances_out.iter().map(|(codepoint, advance)| {
            serde_json::json!({"codepoint": codepoint, "advance": advance / 64})
        }).collect::<Vec<_>>(),
        "pair_adjustments": pairs_out.iter().map(|((left, right), adjustment)| {
            serde_json::json!({"left": left, "right": right, "adjustment": adjustment / 64})
        }).collect::<Vec<_>>(),
        "glyphs": glyphs_out,
        "lines": encoded_lines,
    }))
}

/// Build the paired-text layout document for both hint modes.
fn document(
    data: &[u8],
    parsed: &Parsed,
    text: &str,
) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let repertoire: std::collections::BTreeSet<char> = parsed.chars.chars().collect();
    for ch in text.chars().filter(|c| *c != '\r' && *c != '\n') {
        if !repertoire.contains(&ch) {
            return fail(format!("text holds U+{:04X} outside --chars", ch as u32));
        }
    }
    let lines = split_lines(text);
    let config = config_for(parsed);
    let mut modes = serde_json::Map::new();
    for (name, strategy, extensions) in MODES {
        // Exact capture pipeline per mode; zero tracking keeps finalized pixels.
        let pipeline = RenderPipeline {
            fitting: strategy,
            rasterization: Rasterization::FreeTypeMonoTerminals,
            diagonal_fitting: false,
        };
        let strike = generate_monochrome_font_with_pipeline(data, &config, pipeline, 0.0)
            .map_err(|error| invalid(error.to_string()))?;
        let mut mode = layout_mode(&strike, &lines)?;
        mode["strategy"] = serde_json::Value::String(format!("{strategy:?}"));
        mode["extensions"] = serde_json::Value::String(extensions.into());
        modes.insert(name.into(), mode);
    }
    let family = std::path::Path::new(&parsed.font)
        .file_stem()
        .and_then(|s| s.to_str())
        .ok_or_else(|| invalid("--font PATH"))?;
    Ok(serde_json::json!({
        "font": family,
        "size": parsed.size,
        "axes": parsed.axes,
        "chars": parsed.chars,
        "modes": modes,
    }))
}

/// Run the `text-layout` command; `args` is the slice after the mode word.
pub fn run(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let parsed = parse(args)?;
    let out_path = std::path::Path::new(&parsed.out);
    if let Some(parent) = out_path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)?;
        }
    }
    let data = std::fs::read(&parsed.font)?;
    let font_canon = std::fs::canonicalize(&parsed.font)?;
    let out_canon = if out_path.exists() {
        std::fs::canonicalize(out_path)?
    } else {
        match out_path.parent() {
            Some(parent) if !parent.as_os_str().is_empty() => {
                std::fs::canonicalize(parent)?.join(out_path.file_name().unwrap_or_default())
            }
            _ => std::fs::canonicalize(std::env::current_dir()?)?
                .join(out_path.file_name().unwrap_or_default()),
        }
    };
    if out_canon == font_canon {
        return fail("refusing to overwrite the input font file");
    }
    let text = std::fs::read_to_string(&parsed.text_file)?;
    let output = document(&data, &parsed, &text)?;
    std::fs::write(&parsed.out, serde_json::to_string_pretty(&output)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(pairs: &[(&str, &str)]) -> Vec<String> {
        pairs
            .iter()
            .flat_map(|(k, v)| [k.to_string(), v.to_string()])
            .collect()
    }

    fn roboto() -> Vec<u8> {
        std::fs::read(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../fonts/Roboto.ttf"),
        )
        .unwrap()
    }

    fn parsed_for(text: &str) -> (Parsed, String) {
        let mut axes = BTreeMap::new();
        axes.insert("wght".into(), 400.0);
        axes.insert("wdth".into(), 100.0);
        (
            Parsed {
                font: "Roboto".into(),
                chars: "AV".into(),
                text_file: "text".into(),
                out: "out".into(),
                size: 16.0,
                axes,
            },
            text.into(),
        )
    }

    #[test]
    fn rejects_bad_flags() {
        assert!(parse(&[]).is_err());
        assert!(parse(&args(&[("--font", "a.ttf")])).is_err());
        let base = [
            ("--font", "a.ttf"),
            ("--chars", "AV"),
            ("--text-file", "t.txt"),
            ("--out", "o.json"),
        ];
        let non_ascii = [
            ("--font", "a.ttf"),
            ("--chars", "Aé"),
            ("--text-file", "t.txt"),
            ("--out", "o.json"),
        ];
        assert!(parse(&args(&non_ascii)).is_err());
        let mut bad_size = base.to_vec();
        bad_size.push(("--size", "nan"));
        assert!(parse(&args(&bad_size)).is_err());
        let mut bad_axes = base.to_vec();
        bad_axes.push(("--axes", "[1]"));
        assert!(parse(&args(&bad_axes)).is_err());
    }

    #[test]
    fn rejects_text_outside_chars() {
        let data = roboto();
        let (parsed, text) = parsed_for("AX");
        assert!(document(&data, &parsed, &text).is_err());
    }

    #[test]
    fn splits_explicit_lines() {
        assert_eq!(split_lines("a\nb\rc\r\nd"), vec!["a", "b", "c", "d"]);
        assert_eq!(split_lines(""), vec![""]);
    }

    #[test]
    fn places_both_modes_on_whole_pixels() {
        let data = roboto();
        let (parsed, text) = parsed_for("AV\nVA");
        let output = document(&data, &parsed, &text).unwrap();
        for mode in ["auto_default", "selective_default"] {
            let mode_value = &output["modes"][mode];
            assert_eq!(mode_value["lines"].as_array().unwrap().len(), 2);
            let metrics = &mode_value["metrics"];
            let ascent = metrics["ascent_px"].as_i64().unwrap();
            let pitch = metrics["line_height_px"].as_i64().unwrap();
            assert!(pitch >= 1);
            let advances: HashMap<u32, i64> = mode_value["advances"]
                .as_array()
                .unwrap()
                .iter()
                .map(|entry| {
                    (
                        entry["codepoint"].as_u64().unwrap() as u32,
                        entry["advance"].as_i64().unwrap(),
                    )
                })
                .collect();
            let pairs: HashMap<(u32, u32), i64> = mode_value["pair_adjustments"]
                .as_array()
                .unwrap()
                .iter()
                .map(|entry| {
                    (
                        (
                            entry["left"].as_u64().unwrap() as u32,
                            entry["right"].as_u64().unwrap() as u32,
                        ),
                        entry["adjustment"].as_i64().unwrap(),
                    )
                })
                .collect();
            for (index, line) in mode_value["lines"].as_array().unwrap().iter().enumerate() {
                assert_eq!(
                    line["baseline"].as_i64().unwrap(),
                    ascent + index as i64 * pitch
                );
                let placements = line["placements"].as_array().unwrap();
                for placement in placements {
                    // Native 26.6 origins stay on whole pixels; pairs apply once.
                    assert_eq!(placement["x_26_6"].as_i64().unwrap() % 64, 0);
                }
                for pair in placements.windows(2) {
                    let left = pair[0]["codepoint"].as_u64().unwrap() as u32;
                    let right = pair[1]["codepoint"].as_u64().unwrap() as u32;
                    let expected = pair[0]["x"].as_i64().unwrap()
                        + advances[&left]
                        + pairs.get(&(left, right)).copied().unwrap_or(0);
                    assert_eq!(pair[1]["x"].as_i64().unwrap(), expected);
                    assert_eq!(
                        pair[1]["pair"].as_i64().unwrap(),
                        pairs.get(&(left, right)).copied().unwrap_or(0)
                    );
                }
                assert_eq!(
                    placements[0]["pair"].as_i64().unwrap(),
                    0,
                    "line-initial pair must be zero"
                );
            }
            assert!(advances[&('A' as u32)] > 0);
        }
    }

    #[test]
    fn strike_matches_capture_render() {
        use font_generator::{
            candidate::render_with_rasterization,
            layout_spacing::bitmap_advance_26_6,
            reference::{ReferenceRequest, PROFILE_MONO_1BIT},
        };
        let data = roboto();
        let (parsed, _) = parsed_for("");
        let config = config_for(&parsed);
        for (strategy, extensions) in [
            (StemFittingStrategy::UpstreamMono, "mono-width-01"),
            (StemFittingStrategy::FontHintsAuto, "font-hints-auto-01"),
        ] {
            let strike = generate_monochrome_font_with_pipeline(
                &data,
                &config,
                RenderPipeline {
                    fitting: strategy,
                    rasterization: Rasterization::FreeTypeMonoTerminals,
                    diagonal_fitting: false,
                },
                0.0,
            )
            .unwrap();
            // Capture's own render call on identical settings and rasterization.
            let report = render_with_rasterization(
                &data,
                &ReferenceRequest {
                    profile: PROFILE_MONO_1BIT.into(),
                    extensions: extensions.into(),
                    settings: config.clone(),
                },
                Rasterization::FreeTypeMonoTerminals,
            )
            .unwrap();
            let records: HashMap<u32, _> = report
                .records
                .iter()
                .map(|record| (record.codepoint, record))
                .collect();
            assert_eq!(strike.glyphs.len(), records.len());
            for glyph in &strike.glyphs {
                let record = records[&glyph.codepoint];
                assert_eq!(glyph.glyph_id, record.glyph_id, "U+{:04X}", glyph.codepoint);
                assert_eq!(glyph.advance_26_6, bitmap_advance_26_6(record));
                assert_eq!(
                    (glyph.left, glyph.top, glyph.width, glyph.height),
                    (record.left, record.top, record.width, record.height),
                    "U+{:04X}",
                    glyph.codepoint
                );
                assert_eq!(glyph.pixels, record.pixels, "U+{:04X}", glyph.codepoint);
            }
        }
    }
}
