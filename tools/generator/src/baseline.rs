//! Approved production snapshot; revision/iteration identities are metadata.
use skrifa_baseline as fitting_skrifa;
const FITTING_SHA256: &str = env!("SKRIFA_BASELINE_SHA256");
fn rasterize_enabled(
    commands: &[crate::probe::FittedCommand],
    config: &crate::Config,
    _enabled: bool,
) -> Result<crate::probe::RasterOutput, crate::Error> {
    crate::probe::rasterize(commands, config)
}
fn raster_policy(_enabled: bool) -> crate::reference::RasterPolicy {
    crate::reference::RasterPolicy::Coverage
}
/// Latest explicitly approved model. Update only on an authorized promotion.
pub const VERSION: &str = "001.01";
include!("fitting.rs");
