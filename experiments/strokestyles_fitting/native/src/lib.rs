//! Reproducible capture rasterization for StrokeStyles fitting evidence.
//!
//! The maintained scanner (`mono::rasterize_with_scan_state`) and the
//! terminal-cap kernel (`terminal_caps::suppress_certified`) are the only
//! raster paths; there is no coverage substitute. `FittedCommand` and
//! `FontScanState` carry `Serialize` only, so captures are parsed through
//! local DTOs with float-bit verification instead of changing maintained
//! code. A disabled/reference control (byte-identical re-rasterization of
//! captured outlines) must pass before any candidate pixel claim.

use font_generator::{
    mono, probe::FittedCommand, reference::FontScanState, terminal_caps, Config, Error,
    MonoRasterSettings,
};
use serde::Deserialize;

fn err(message: impl Into<String>) -> Error {
    Error(message.into())
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CommandDto {
    op: String,
    #[serde(default)]
    x: Option<f32>,
    #[serde(default)]
    y: Option<f32>,
    #[serde(default)]
    x1: Option<f32>,
    #[serde(default)]
    y1: Option<f32>,
    #[serde(default)]
    x2: Option<f32>,
    #[serde(default)]
    y2: Option<f32>,
    #[serde(default)]
    x_bits: Option<u32>,
    #[serde(default)]
    y_bits: Option<u32>,
    #[serde(default)]
    x1_bits: Option<u32>,
    #[serde(default)]
    y1_bits: Option<u32>,
    #[serde(default)]
    x2_bits: Option<u32>,
    #[serde(default)]
    y2_bits: Option<u32>,
}

fn checked(value: Option<f32>, bits: Option<u32>, name: &str) -> Result<f32, Error> {
    let v = value.ok_or_else(|| err(format!("command misses {name}")))?;
    if !v.is_finite() || v.abs() > 32768.0 {
        return Err(err("command coordinate out of scanner bounds"));
    }
    if let Some(want) = bits {
        if v.to_bits() != want {
            return Err(err("command float bits mismatch capture"));
        }
    }
    Ok(v)
}

/// Parse capture JSON commands into maintained outline commands.
pub fn parse_commands(value: &serde_json::Value) -> Result<Vec<FittedCommand>, Error> {
    let items: Vec<CommandDto> =
        serde_json::from_value(value.clone()).map_err(|e| err(e.to_string()))?;
    let mut out = Vec::with_capacity(items.len());
    for item in &items {
        match item.op.as_str() {
            "move_to" => out.push(FittedCommand::MoveTo(
                checked(item.x, item.x_bits, "x")?,
                checked(item.y, item.y_bits, "y")?,
            )),
            "line_to" => out.push(FittedCommand::LineTo(
                checked(item.x, item.x_bits, "x")?,
                checked(item.y, item.y_bits, "y")?,
            )),
            "quad_to" => out.push(FittedCommand::QuadTo(
                checked(item.x1, item.x1_bits, "x1")?,
                checked(item.y1, item.y1_bits, "y1")?,
                checked(item.x, item.x_bits, "x")?,
                checked(item.y, item.y_bits, "y")?,
            )),
            "curve_to" => out.push(FittedCommand::CurveTo(
                checked(item.x1, item.x1_bits, "x1")?,
                checked(item.y1, item.y1_bits, "y1")?,
                checked(item.x2, item.x2_bits, "x2")?,
                checked(item.y2, item.y2_bits, "y2")?,
                checked(item.x, item.x_bits, "x")?,
                checked(item.y, item.y_bits, "y")?,
            )),
            "close" => out.push(FittedCommand::Close),
            other => return Err(err(format!("unknown command op {other}"))),
        }
    }
    Ok(out)
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ScanDto {
    source_sha256: String,
    enabled: bool,
    scan_type: u16,
    contour_modes: Vec<Option<u8>>,
    hinting_axes: [bool; 2],
}

/// Parse capture JSON scan state without touching maintained types.
pub fn parse_scan_state(value: &serde_json::Value) -> Result<FontScanState, Error> {
    let dto: ScanDto = serde_json::from_value(value.clone()).map_err(|e| err(e.to_string()))?;
    Ok(FontScanState {
        source_sha256: dto.source_sha256,
        enabled: dto.enabled,
        scan_type: dto.scan_type,
        contour_modes: dto.contour_modes,
        hinting_axes: dto.hinting_axes,
    })
}

/// Rasterize on the exact maintained Mono path used by the pipeline.
pub fn rasterize(
    commands: &[FittedCommand],
    mono_raster: &MonoRasterSettings,
    font_scan: Option<&FontScanState>,
) -> Result<font_generator::probe::RasterOutput, Error> {
    let config = Config {
        output_bits: 1,
        mono_raster: *mono_raster,
        ..Config::default()
    };
    mono::rasterize_with_scan_state(commands, &config, font_scan)
}

/// Terminal-cap reproduction mirroring `candidate::rasterize_terminals`.
pub fn reproduce_terminals(
    source: &[FittedCommand],
    fitted: &[FittedCommand],
    mono_raster: &MonoRasterSettings,
) -> Result<font_generator::probe::RasterOutput, Error> {
    let mut output = rasterize(fitted, mono_raster, None)?;
    let mut plain = *mono_raster;
    plain.include_stubs = false;
    plain.font_instructions = false;
    let without = rasterize(fitted, &plain, None)?;
    output.pixels = terminal_caps::suppress_certified(source, fitted, &output, &without)?.pixels;
    Ok(output)
}

fn mono_raster_of(record: &serde_json::Value) -> Result<MonoRasterSettings, Error> {
    match record.get("mono_raster") {
        Some(value) => serde_json::from_value(value.clone()).map_err(|e| err(e.to_string())),
        None => Ok(MonoRasterSettings::default()),
    }
}

fn scan_of(record: &serde_json::Value) -> Result<Option<FontScanState>, Error> {
    match record.get("font_scan") {
        Some(value) if !value.is_null() => parse_scan_state(value).map(Some),
        _ => Ok(None),
    }
}

/// Rasterize a capture record on its own recorded policy.
///
/// `None` uses the record's `fitted_commands`; `Some` substitutes candidate
/// commands. Either way the captured `mono_raster`, `font_scan` and
/// `raster_policy` apply unchanged: the terminal policy reproduces
/// `reproduce_terminals(&original_source, &candidate)` while raw policy
/// reuses the captured scan. Unknown policies fail without fallback.
pub fn rasterize_record(
    record: &serde_json::Value,
    fitted_override: Option<&serde_json::Value>,
) -> Result<font_generator::probe::RasterOutput, Error> {
    let fitted = match fitted_override {
        Some(value) => parse_commands(value)?,
        None => parse_commands(
            record
                .get("fitted_commands")
                .ok_or_else(|| err("record misses fitted_commands"))?,
        )?,
    };
    let mono_raster = mono_raster_of(record)?;
    let scan = scan_of(record)?;
    let policy = record
        .get("raster_policy")
        .and_then(|v| v.as_str())
        .unwrap_or("free_type_mono");
    match policy {
        "free_type_mono_terminals" => {
            let source = parse_commands(
                record
                    .get("source_commands")
                    .ok_or_else(|| err("terminal record misses source_commands"))?,
            )?;
            reproduce_terminals(&source, &fitted, &mono_raster)
        }
        "free_type_mono" => rasterize(&fitted, &mono_raster, scan.as_ref()),
        other => Err(err(format!("unsupported raster_policy {other}"))),
    }
}

/// Disabled/reference control: re-rasterize a captured record verbatim.
///
/// Branches on the record's own `raster_policy`, exactly as captured.
/// Returns a JSON report; `match` must hold before candidate evidence.
pub fn parity_record(record: &serde_json::Value) -> Result<serde_json::Value, Error> {
    let output = rasterize_record(record, None)?;
    let policy = record
        .get("raster_policy")
        .and_then(|v| v.as_str())
        .unwrap_or("free_type_mono");
    let get_u64 = |key: &str| record.get(key).and_then(|v| v.as_u64());
    let get_i64 = |key: &str| record.get(key).and_then(|v| v.as_i64());
    let pixels: Vec<u8> = match record.get("pixels") {
        Some(value) => serde_json::from_value(value.clone()).map_err(|e| err(e.to_string()))?,
        None => return Err(err("record misses pixels")),
    };
    let frame_ok = get_i64("left") == Some(output.left as i64)
        && get_i64("top") == Some(output.top as i64)
        && get_u64("width") == Some(u64::from(output.width))
        && get_u64("height") == Some(u64::from(output.height));
    let pixels_ok = pixels == output.pixels;
    let coverage_ok = match record.get("coverage") {
        Some(value) => {
            let coverage: Vec<u8> =
                serde_json::from_value(value.clone()).map_err(|e| err(e.to_string()))?;
            coverage == output.coverage
        }
        None => true,
    };
    Ok(serde_json::json!({
        "policy": policy,
        "frame_match": frame_ok,
        "pixels_match": pixels_ok,
        "coverage_match": coverage_ok,
        "match": frame_ok && pixels_ok && coverage_ok,
        "left": output.left,
        "top": output.top,
        "width": output.width,
        "height": output.height,
    }))
}
