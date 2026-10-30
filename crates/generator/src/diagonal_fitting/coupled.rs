//! Adopted coupled whole-outline fit (Hobby 3.1, 3.2, 3.6, 6; Hersch 2).
//!
//! The reviewed native-Y slice uses exact common polynomials for feature
//! recognition, shared controls and scanning. Unsupported reconstruction or
//! lost native ownership returns the preceding fit unchanged.

use super::{abstain, curve_model, partition, FitResult, Reference};
use crate::{fitting_source::SourceOutline, probe::FittedCommand, Error};

pub fn fit(
    raw: &SourceOutline,
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    let fallback = |reason: &str| abstain(upstream, reason, serde_json::json!({}));
    if native_axes != [false, true] {
        return Ok(fallback("coupled-native-Y-required"));
    }
    let Some(normalized) = partition::normalize(raw, upstream) else {
        return Ok(fallback("coupled-partition-unsupported"));
    };
    let mut result = curve_model::fit_coupled(
        &normalized.source,
        &normalized.upstream,
        size_px,
        reference,
        native_axes,
    )?;
    if !result.applied {
        result.commands = upstream.to_vec();
        return Ok(result);
    }
    if !normalized.preserves_original_y(&result.commands) {
        return Ok(fallback("coupled-original-Y-or-expansion"));
    }
    result.diagnostics["model"] = serde_json::json!("coupled-outline-01");
    Ok(result)
}

/// Automatic-Y shape gate over the original source outline: exact
/// partition normalization first, then the coupled front-half report.
/// Always abstains; no renderer path calls this yet.
pub fn automatic_shape_gate(
    raw: &SourceOutline,
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    let fallback = |reason: &str| abstain(upstream, reason, serde_json::json!({}));
    if native_axes != [false, false] {
        return Ok(fallback("shape-gate:automatic-axes-required"));
    }
    let Some(normalized) = partition::normalize(raw, upstream) else {
        let mut result = fallback("shape-gate:coupled-partition-unsupported");
        result.diagnostics["model"] = serde_json::json!("coupled-shape-auto-01");
        result.diagnostics["gate_report"] = serde_json::json!(true);
        result.diagnostics["reached"] = serde_json::json!("normalize");
        return Ok(result);
    };
    let mut result = curve_model::automatic_shape_gate(
        &normalized.source,
        &normalized.upstream,
        size_px,
        reference,
        native_axes,
    )?;
    result.commands = upstream.to_vec();
    Ok(result)
}

/// Automatic-Y shape gate on the original raw source outline (f64
/// parsed geometry, exact segment topology correspondence with the
/// upstream). Always abstains; no renderer path calls this yet.
pub fn automatic_shape_gate_raw(
    raw: &SourceOutline,
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    if native_axes != [false, false] {
        return Ok(abstain(
            upstream,
            "shape-gate:automatic-axes-required",
            serde_json::json!({
                "model": "coupled-shape-auto-01", "gate_report": true, "reached": "axes",
            }),
        ));
    }
    let mut result =
        curve_model::automatic_shape_gate_parsed(raw, upstream, size_px, reference, native_axes)?;
    result.commands = upstream.to_vec();
    Ok(result)
}

/// Automatic-Y source-shape solve on the original raw source outline:
/// translated raw head profile with the certified standard in one
/// upstream budget (Hobby 3.1/3.6/6, Shamir 3.2-3.6). Routed from
/// `approved::fit`, which returns applied results directly; donors are
/// raw outlines with their fitted upstream commands.
pub fn automatic_shape(
    raw: &SourceOutline,
    source_captured: &[FittedCommand],
    upstream: &[FittedCommand],
    size_px: f64,
    reference: &Reference,
    native_axes: [bool; 2],
) -> Result<FitResult, Error> {
    curve_model::fit_automatic_shape(
        raw,
        source_captured,
        upstream,
        size_px,
        reference,
        native_axes,
    )
}
