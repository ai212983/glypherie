//! Browser WASM wrapper over the approved Rust font renderer.
//!
//! Thin ownership + conversion layer only: no fitting, no model code, no
//! preview-matrix or attention logic lives here.
//!
//! ## JS API
//!
//! ```js
//! import init, { Font } from "./pkg-web/font_wasm.js";
//! await init();
//! const font = new Font(bytes); // `bytes`: Uint8Array; throws on invalid font
//! try {
//!   const meta = font.metadata(); // plain JS object (see below)
//!   const result = font.render({
//!     text: "Hello", width: 200, height: 60,
//!     size_px: 16, axes: {}, hinting: "auto", output_bits: 1,
//!     mono_threshold: 128, gray_gamma: 1.0, kerning: true,
//!     metric_rounding: "subpixel", missing_glyphs: "error",
//!     wrap: "word", align: "left",
//!     foreground: [0, 0, 0, 255], background: [255, 255, 255, 255],
//!     // palette: [[r,g,b,a], ...] // optional, exactly 1 << output_bits entries
//!     // renderer: "baseline" // optional stable role: "baseline" (default,
//!     //   approved output), "reference", or "candidate" (preview builds only;
//!     //   a default build rejects it visibly instead of substituting)
//!   });
//!   try {
//!     // `result.pixels()` returns a *fresh Uint8Array copy* on every call.
//!     // For canvas: `new ImageData(new Uint8ClampedArray(u8.buffer), w, h)`
//!     // (zero-copy view; the copy is already JS-owned so the result can be
//!     // freed independently at any time).
//!     const layout = result.layout(); // plain object: { lines, missing_codepoints }
//!     void layout;
//!   } finally {
//!     result.free();
//!   }
//! } finally {
//!   font.free();
//! }
//! ```
//!
//! ### Ownership
//!
//! `Font` and `RenderResult` are wasm-bindgen structs holding Rust-side memory
//! and **must be freed** (`try/finally` or `.free()`). `pixels()` copies the
//! RGBA canvas into a new JS-owned buffer on each call, so freeing the result
//! never invalidates a previously returned array.
//!
//! ### `characters` is rejected
//!
//! The render spec has **no** `characters` field: the glyph repertoire is
//! always derived from `text` by `render_text`, so passing `characters` would
//! be contradictory. Unknown spec fields (including `characters`) are rejected
//! with an error. `text` is the only character source.
//!
//! ### `renderer` selects the preview role
//!
//! `"baseline"` (the default) renders the approved production output.
//! `"reference"` and `"candidate"` keep that output's validation, layout,
//! advances, kerning and metrics and replace only monochrome glyph bitmaps
//! with the role capture. Gray keeps the production target for every role.
//! Preview roles support 1-bit and 3-bit output; candidate uses automatic
//! hinting. Unsupported combinations fail explicitly. The `candidate` role needs the crate's opt-in
//! `preview` feature (the explicit preview artifact); a default production
//! build rejects it with an error instead of rendering another role.
//!
//! ### Errors
//!
//! Failures surface as thrown JS strings carrying the generator message only
//! (`JsValue::from_str`); no stacks or Rust internals cross the boundary.
//!
//! ### `generate_raw`
//!
//! Deliberately absent: glyph-JSON debugging already exists natively
//! (`cargo run -p font_generator`), and a second raw export would widen this
//! API for no browser use case. Reconsider if the host needs it.

use font_generator::surface::{self, HAlign, RenderedText, TextRenderRequest, WrapMode};
use font_generator::{renderer::RendererRole, Config, Hinting, MetricRounding, MissingGlyphs};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use wasm_bindgen::prelude::*;

fn js_error(message: impl Into<String>) -> JsValue {
    JsValue::from_str(&message.into())
}

/// Pure-Rust core of [`Font::new`]: copy `bytes` and validate once via
/// `metadata::extract` so construction fails fast on bad input.
/// Returns the message as `String` so native tests can assert on it without
/// touching `JsValue` (unconstructible off wasm32).
fn load_font(bytes: &[u8]) -> Result<Vec<u8>, String> {
    let data = bytes.to_vec();
    font_generator::metadata::extract(&data).map_err(|e| e.to_string())?;
    Ok(data)
}

/// Pure-Rust core of [`Font::metadata`].
fn metadata_value(data: &[u8]) -> Result<font_generator::metadata::FontMetadata, String> {
    font_generator::metadata::extract(data).map_err(|e| e.to_string())
}

/// Serialize a `Serialize` value to a *plain* JS object: `BTreeMap` fields
/// (e.g. metadata `names`, spec `axes`) become ordinary objects with string
/// keys, never `Map`s, and `None` optionals become explicit `null`s matching
/// the native nullable schema (rather than absent keys).
fn to_plain_object<T: Serialize>(value: &T) -> Result<JsValue, JsValue> {
    let serializer = serde_wasm_bindgen::Serializer::new()
        .serialize_maps_as_objects(true)
        .serialize_missing_as_null(true);
    value
        .serialize(&serializer)
        .map_err(|e| js_error(format!("serialization failed: {e}")))
}

/// Owned font bytes. Construction copies `bytes` and validates them once via
/// `metadata::extract`, so invalid input fails fast here instead of at first
/// render.
#[wasm_bindgen]
pub struct Font {
    data: Vec<u8>,
}

#[wasm_bindgen]
impl Font {
    /// Copy `bytes` (a `Uint8Array` view on the JS side) and validate.
    #[wasm_bindgen(constructor)]
    pub fn new(bytes: &[u8]) -> Result<Font, JsValue> {
        load_font(bytes).map_err(js_error).map(|data| Font { data })
    }

    /// Descriptive source-font metadata as a plain JS object (same shape as
    /// the native `FontMetadata` struct: `names`, `axes`, `kerning`, `style`,
    /// `classification`, `coverage`, `declared_unicode_ranges`).
    pub fn metadata(&self) -> Result<JsValue, JsValue> {
        let meta = metadata_value(&self.data).map_err(js_error)?;
        to_plain_object(&meta)
    }

    /// Render bounded multi-line text; see the module docs for the spec shape.
    pub fn render(&self, spec: JsValue) -> Result<RenderResult, JsValue> {
        validate_spec_keys(&spec)?;
        let parsed: RenderSpec = serde_wasm_bindgen::from_value(spec)
            .map_err(|e| js_error(format!("invalid render spec: {e}")))?;
        let rendered = render_parsed(&self.data, &parsed).map_err(js_error)?;
        Ok(RenderResult { inner: rendered })
    }
}

fn validate_spec_keys(spec: &JsValue) -> Result<(), JsValue> {
    if !spec.is_object() || spec.is_null() || js_sys::Array::is_array(spec) {
        return Err(js_error("invalid render spec: expected an object"));
    }
    // serde-wasm-bindgen reads only declared struct fields, so Serde's
    // deny_unknown_fields cannot see additional JS properties.
    for key in js_sys::Reflect::own_keys(spec)? {
        let key = key
            .as_string()
            .ok_or_else(|| js_error("invalid render spec: field names must be strings"))?;
        if !matches!(
            key.as_str(),
            "text"
                | "width"
                | "height"
                | "size_px"
                | "axes"
                | "hinting"
                | "output_bits"
                | "mono_threshold"
                | "gray_gamma"
                | "missing_glyphs"
                | "kerning"
                | "metric_rounding"
                | "wrap"
                | "align"
                | "foreground"
                | "background"
                | "palette"
                | "renderer"
        ) {
            return Err(js_error(format!(
                "invalid render spec: unknown field {key:?}"
            )));
        }
    }
    Ok(())
}

fn default_size_px() -> f32 {
    16.0
}
fn default_output_bits() -> u8 {
    1
}
fn default_mono_threshold() -> u8 {
    128
}
fn default_gray_gamma() -> f32 {
    1.0
}
fn default_kerning() -> bool {
    true
}
fn default_foreground() -> [u8; 4] {
    [0, 0, 0, 255]
}
fn default_background() -> [u8; 4] {
    [255, 255, 255, 255]
}

/// Render parameters deserialized from the JS spec object.
///
/// There is intentionally **no** `characters` field: `validate_spec_keys`
/// rejects unknown JS keys, because the repertoire always comes from `text`.
/// `deny_unknown_fields` also enforces this for native JSON deserialization.
/// `axes` accepts plain JS objects; `metadata()` emits ordinary objects.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RenderSpec {
    text: String,
    width: u32,
    height: u32,
    #[serde(default = "default_size_px")]
    size_px: f32,
    #[serde(default)]
    axes: BTreeMap<String, f32>,
    #[serde(default)]
    hinting: Hinting,
    #[serde(default = "default_output_bits")]
    output_bits: u8,
    #[serde(default = "default_mono_threshold")]
    mono_threshold: u8,
    #[serde(default = "default_gray_gamma")]
    gray_gamma: f32,
    #[serde(default)]
    missing_glyphs: MissingGlyphs,
    #[serde(default = "default_kerning")]
    kerning: bool,
    #[serde(default)]
    metric_rounding: MetricRounding,
    #[serde(default)]
    wrap: WrapModeDefault,
    #[serde(default)]
    align: AlignDefault,
    #[serde(default = "default_foreground")]
    foreground: [u8; 4],
    #[serde(default = "default_background")]
    background: [u8; 4],
    #[serde(default)]
    palette: Option<Vec<[u8; 4]>>,
    /// Stable preview role; the default keeps the approved baseline path.
    #[serde(default)]
    renderer: RendererArg,
}

// `surface::WrapMode`/`HAlign` implement `Default` (Word/Left) but not
// `Deserialize`, so the spec layer owns these thin defaults + conversions.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq, Default)]
#[serde(rename_all = "lowercase")]
enum WrapModeDefault {
    Clip,
    #[default]
    Word,
    Char,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq, Default)]
#[serde(rename_all = "lowercase")]
enum AlignDefault {
    #[default]
    Left,
    Center,
    Right,
}

// Stable renderer roles only; never revision/iteration-specific values.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq, Default)]
#[serde(rename_all = "lowercase")]
enum RendererArg {
    #[default]
    Baseline,
    Reference,
    Candidate,
}

impl RendererArg {
    fn role(self) -> RendererRole {
        match self {
            RendererArg::Baseline => RendererRole::Baseline,
            RendererArg::Reference => RendererRole::Reference,
            RendererArg::Candidate => RendererRole::Candidate,
        }
    }
}

/// Pure-Rust render path shared by the wasm export and native tests.
fn render_parsed(font_data: &[u8], spec: &RenderSpec) -> Result<RenderedText, String> {
    let request = TextRenderRequest {
        config: Config {
            size_px: spec.size_px,
            axes: spec.axes.clone(),
            hinting: spec.hinting,
            output_bits: spec.output_bits,
            mono_threshold: spec.mono_threshold,
            gray_gamma: spec.gray_gamma,
            characters: String::new(), // ignored: derived from `text`
            missing_glyphs: spec.missing_glyphs,
            kerning: spec.kerning,
            metric_rounding: spec.metric_rounding,
        },
        text: spec.text.clone(),
        width: spec.width,
        height: spec.height,
        wrap: match spec.wrap {
            WrapModeDefault::Clip => WrapMode::Clip,
            WrapModeDefault::Word => WrapMode::Word,
            WrapModeDefault::Char => WrapMode::Char,
        },
        align: match spec.align {
            AlignDefault::Left => HAlign::Left,
            AlignDefault::Center => HAlign::Center,
            AlignDefault::Right => HAlign::Right,
        },
        foreground: spec.foreground,
        background: spec.background,
        palette: spec.palette.clone(),
    };
    // Baseline is the approved production path; other roles reuse its
    // validation/layout and swap only glyph bitmaps.
    match spec.renderer {
        RendererArg::Baseline => surface::render_text(font_data, &request),
        role => surface::render_text_with_renderer(font_data, &request, role.role()),
    }
    .map_err(|e| e.to_string())
}

/// Owned result of [`Font::render`]. Free with `.free()` (see module docs).
#[wasm_bindgen]
pub struct RenderResult {
    inner: RenderedText,
}

#[derive(Clone, Debug, Serialize)]
struct LineView {
    byte_start: usize,
    byte_end: usize,
    width_26_6: i32,
    height_px: u32,
}

#[derive(Clone, Debug, Serialize)]
struct LayoutView {
    lines: Vec<LineView>,
    missing_codepoints: Vec<u32>,
}

#[wasm_bindgen]
impl RenderResult {
    /// Canvas width in pixels.
    pub fn width(&self) -> u32 {
        self.inner.width
    }

    /// Canvas height in pixels.
    pub fn height(&self) -> u32 {
        self.inner.height
    }

    /// RGBA row-major canvas (`width * height * 4` bytes). Returns a **fresh
    /// `Uint8Array` copy** on every call: `Uint8Array` (not
    /// `Uint8ClampedArray`) because it is the universal typed-array currency
    /// and converts to an `ImageData`-ready view for free with
    /// `new Uint8ClampedArray(u8.buffer)`. Copying keeps JS ownership
    /// independent of this result's lifetime.
    pub fn pixels(&self) -> js_sys::Uint8Array {
        js_sys::Uint8Array::from(self.inner.pixels.as_slice())
    }

    /// Number of laid-out visual lines.
    pub fn line_count(&self) -> usize {
        self.inner.lines.len()
    }

    /// Per-line layout plus skipped codepoints as a plain JS object:
    /// `{ lines: [{byte_start, byte_end, width_26_6, height_px}], missing_codepoints }`.
    pub fn layout(&self) -> Result<JsValue, JsValue> {
        let view = LayoutView {
            lines: self
                .inner
                .lines
                .iter()
                .map(|line| LineView {
                    byte_start: line.byte_start,
                    byte_end: line.byte_end,
                    width_26_6: line.width_26_6,
                    height_px: line.height_px,
                })
                .collect(),
            missing_codepoints: self.inner.missing_codepoints.clone(),
        };
        to_plain_object(&view)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};

    const FIXTURE: &[u8] = include_bytes!("../../generator/tests/fixtures/static-cff.otf");

    fn spec_from(value: Value) -> Result<RenderSpec, String> {
        serde_json::from_value(value).map_err(|e| e.to_string())
    }

    fn minimal_spec(text: &str, width: u32, height: u32) -> RenderSpec {
        spec_from(json!({ "text": text, "width": width, "height": height })).unwrap()
    }

    #[test]
    fn font_new_accepts_valid_font_and_rejects_garbage() {
        // `JsValue` cannot be constructed off wasm32 (it aborts), so the
        // error-message assertions go through the pure `load_font` core that
        // `Font::new` wraps with a one-line `JsValue::from_str` mapping.
        // The Ok path of the real constructor touches no `JsValue`.
        assert!(Font::new(FIXTURE).is_ok());
        let err = load_font(b"not a font").unwrap_err();
        assert!(!err.is_empty());
        assert!(load_font(&[]).is_err());
    }

    #[test]
    fn metadata_serializes_to_object_with_string_keys() {
        // `metadata()` itself returns a JsValue (only inspectable under a wasm
        // runtime), but it serializes this same `FontMetadata` value through
        // `to_plain_object` with maps-as-objects, so the JSON round-trip here
        // pins the observable shape: objects, not maps/arrays.
        let meta = metadata_value(FIXTURE).unwrap();
        let value = serde_json::to_value(&meta).unwrap();
        assert!(value.is_object());
        for key in [
            "names",
            "axes",
            "kerning",
            "style",
            "classification",
            "coverage",
            "declared_unicode_ranges",
        ] {
            assert!(value.get(key).is_some(), "missing metadata key {key}");
        }
        assert!(value["names"].is_object());
        assert!(value["axes"].is_array());
    }

    #[test]
    fn spec_accepts_plain_object_axes_and_defaults() {
        let spec = spec_from(json!({
            "text": "A", "width": 64, "height": 32,
            "axes": { "wght": 400.0 },
        }))
        .unwrap();
        assert_eq!(spec.axes.get("wght"), Some(&400.0));
        assert_eq!(spec.size_px, 16.0);
        assert_eq!(spec.wrap, WrapModeDefault::Word);
        assert_eq!(spec.align, AlignDefault::Left);
        assert_eq!(spec.foreground, [0, 0, 0, 255]);
        assert_eq!(spec.background, [255, 255, 255, 255]);
        assert!(spec.palette.is_none());
    }

    #[test]
    fn spec_rejects_characters_and_unknown_fields() {
        // `characters` would contradict `text` as the repertoire source.
        let with_characters = spec_from(json!({
            "text": "A", "width": 64, "height": 32, "characters": "A",
        }));
        assert!(with_characters.is_err(), "`characters` must be rejected");
        let unknown = spec_from(json!({
            "text": "A", "width": 64, "height": 32, "fontSize": 16,
        }));
        assert!(unknown.is_err(), "unknown fields must be rejected");
    }

    #[test]
    fn render_returns_correct_dimensions_and_rgba_length() {
        let spec = minimal_spec("A A", 96, 48);
        let rendered = render_parsed(FIXTURE, &spec).unwrap();
        assert_eq!(rendered.width, 96);
        assert_eq!(rendered.height, 48);
        assert_eq!(rendered.pixels.len(), 96 * 48 * 4);
        assert!(!rendered.lines.is_empty());
        // Background fill is opaque white by default; rendering ink changes bytes.
        assert!(rendered
            .pixels
            .chunks_exact(4)
            .any(|px| px != [255, 255, 255, 255]));
    }

    #[test]
    fn renderer_defaults_to_baseline_and_rejects_unknown_roles() {
        let spec = minimal_spec("A", 96, 48);
        assert_eq!(spec.renderer, RendererArg::Baseline);
        let unknown = spec_from(json!({
            "text": "A", "width": 96, "height": 48, "renderer": "iteration-02",
        }));
        assert!(
            unknown.is_err(),
            "iteration-specific roles must be rejected"
        );
    }

    #[test]
    fn baseline_render_matches_approved_surface_path() {
        // Routing identity for the unchanged production path: the default
        // spec must equal `surface::render_text` byte-for-byte.
        let spec = minimal_spec("A A", 96, 48);
        let routed = render_parsed(FIXTURE, &spec).unwrap();
        let request = TextRenderRequest {
            config: Config {
                characters: " A".into(),
                ..Default::default()
            },
            text: "A A".into(),
            width: 96,
            height: 48,
            wrap: WrapMode::Word,
            align: HAlign::Left,
            foreground: [0, 0, 0, 255],
            background: [255, 255, 255, 255],
            palette: None,
        };
        let direct = surface::render_text(FIXTURE, &request).unwrap();
        assert_eq!(routed.pixels, direct.pixels);
        assert_eq!(routed.lines, direct.lines);
    }

    #[test]
    fn reference_role_routes_with_shared_layout() {
        let mut value = serde_json::to_value(minimal_spec("A A", 96, 48)).unwrap();
        value["renderer"] = serde_json::Value::String("reference".into());
        let spec: RenderSpec = serde_json::from_value(value).unwrap();
        let reference = render_parsed(FIXTURE, &spec).unwrap();
        let baseline = render_parsed(FIXTURE, &minimal_spec("A A", 96, 48)).unwrap();
        // Same production layout; only bitmaps may differ.
        assert_eq!(reference.lines, baseline.lines);
        assert_eq!(reference.width, baseline.width);
        assert_eq!(reference.height, baseline.height);
    }

    #[test]
    fn preview_bits_and_hinting_reject_explicitly() {
        for patch in [
            json!({ "output_bits": 8 }),
            json!({ "hinting": "none" }),
            json!({ "hinting": "auto_fallback" }),
        ] {
            let mut value = serde_json::to_value(minimal_spec("A", 96, 48)).unwrap();
            value["renderer"] = serde_json::Value::String("candidate".into());
            for (key, val) in patch.as_object().unwrap() {
                value[key] = val.clone();
            }
            let spec: RenderSpec = serde_json::from_value(value).unwrap();
            assert!(
                render_parsed(FIXTURE, &spec).is_err(),
                "candidate must reject {patch}"
            );
        }
    }

    #[cfg(not(feature = "preview"))]
    #[test]
    fn candidate_without_preview_feature_fails_visibly() {
        let mut value = serde_json::to_value(minimal_spec("A", 96, 48)).unwrap();
        value["renderer"] = serde_json::Value::String("candidate".into());
        let spec: RenderSpec = serde_json::from_value(value).unwrap();
        let err = render_parsed(FIXTURE, &spec).unwrap_err();
        assert!(err.contains("candidate"), "unexpected error: {err}");
    }

    #[cfg(feature = "preview")]
    #[test]
    fn candidate_role_reaches_candidate_capture() {
        // Routing proof without pixel snapshots: the candidate role must go
        // through `candidate::render` (CoverageDropout policy), not silently
        // reuse the upstream coverage path.
        use font_generator::reference::{RasterPolicy, ReferenceRequest};
        let mut config = Config::default();
        config.characters = "A".into();
        let candidate = font_generator::renderer::render(
            FIXTURE,
            &ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: "diagonal-01".into(),
                settings: config.clone(),
            },
            font_generator::renderer::RendererRole::Candidate,
        )
        .unwrap();
        assert!(!candidate.records.is_empty());
        assert!(candidate
            .records
            .iter()
            .all(|record| record.raster_policy == RasterPolicy::CoverageDropout));
        let upstream = font_generator::renderer::render(
            FIXTURE,
            &ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: "none".into(),
                settings: config,
            },
            font_generator::renderer::RendererRole::Reference,
        )
        .unwrap();
        assert!(upstream
            .records
            .iter()
            .all(|record| record.raster_policy == RasterPolicy::Coverage));
    }

    #[cfg(feature = "preview")]
    #[test]
    fn candidate_with_preview_feature_renders_shared_layout() {
        let mut value = serde_json::to_value(minimal_spec("A A", 96, 48)).unwrap();
        value["renderer"] = serde_json::Value::String("candidate".into());
        let spec: RenderSpec = serde_json::from_value(value).unwrap();
        let candidate = render_parsed(FIXTURE, &spec).unwrap();
        let baseline = render_parsed(FIXTURE, &minimal_spec("A A", 96, 48)).unwrap();
        assert_eq!(candidate.lines, baseline.lines);
    }

    #[test]
    fn layout_view_round_trips_through_json() {
        let spec = minimal_spec("A", 96, 48);
        let rendered = render_parsed(FIXTURE, &spec).unwrap();
        let view = LayoutView {
            lines: rendered
                .lines
                .iter()
                .map(|line| LineView {
                    byte_start: line.byte_start,
                    byte_end: line.byte_end,
                    width_26_6: line.width_26_6,
                    height_px: line.height_px,
                })
                .collect(),
            missing_codepoints: rendered.missing_codepoints.clone(),
        };
        let value = serde_json::to_value(&view).unwrap();
        assert!(value["lines"].is_array());
        assert_eq!(
            value["lines"].as_array().unwrap().len(),
            rendered.lines.len()
        );
        assert!(value["missing_codepoints"].is_array());
    }
}
