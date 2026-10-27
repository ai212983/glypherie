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
