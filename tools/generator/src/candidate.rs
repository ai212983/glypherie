//! Working renderer; revision/iteration identities are metadata.
use skrifa_candidate as fitting_skrifa;
const FITTING_SHA256: &str = env!("SKRIFA_CANDIDATE_SHA256");
// FreeType afloader's fitted phantom-point advance, as returned by Skrifa.
// Project hypothesis: automatic Mono spacing must follow the fitted glyph's
// bearings/extent instead of accumulating its pre-fit linear design advance.
// Source pair kerning remains separate and is applied once by the layout stage.
const ADVANCE_POLICY: crate::reference::AdvancePolicy = crate::reference::AdvancePolicy::Hinted;
fn side_bearing_deltas(
    adjusted: &fitting_skrifa::outline::AdjustedMetrics,
    enabled: bool,
) -> Option<[i32; 2]> {
    enabled
        .then_some(adjusted.side_bearing_deltas_26_6)
        .flatten()
}
fn rasterize_enabled(
    commands: &[crate::probe::FittedCommand],
    config: &crate::Config,
    enabled: bool,
) -> Result<crate::probe::RasterOutput, crate::Error> {
    if enabled {
        crate::dropout::rasterize(commands, config)
    } else {
        crate::probe::rasterize(commands, config)
    }
}
fn raster_policy(enabled: bool) -> crate::reference::RasterPolicy {
    if enabled {
        crate::reference::RasterPolicy::CoverageDropout
    } else {
        crate::reference::RasterPolicy::Coverage
    }
}
include!("fitting.rs");
