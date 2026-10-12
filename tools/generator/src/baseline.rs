//! Approved production snapshot; revision/iteration identities are metadata.
use skrifa_baseline as fitting_skrifa;
const FITTING_SHA256: &str = env!("SKRIFA_BASELINE_SHA256");
const ADVANCE_POLICY: crate::reference::AdvancePolicy = crate::reference::AdvancePolicy::Linear;
fn side_bearing_deltas(_: &fitting_skrifa::outline::AdjustedMetrics, _: bool) -> Option<[i32; 2]> {
    None
}
fn rasterize_enabled(
    commands: &[crate::probe::FittedCommand],
    config: &crate::Config,
    enabled: bool,
) -> Result<crate::probe::RasterOutput, crate::Error> {
    // Approved outline-driven monochrome dropout (Hersch §7 / SCANTYPE,
    // project hypothesis): rescue applies only to actually enabled Mono
    // automatic instances; raw coverage is never modified.
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
/// Latest explicitly approved model. Update only on an authorized promotion.
pub const VERSION: &str = "001.02";
include!("fitting.rs");
