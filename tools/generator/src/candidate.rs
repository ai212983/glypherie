//! Working renderer; revision/iteration identities are metadata.
use skrifa_candidate as fitting_skrifa;
const FITTING_SHA256: &str = env!("SKRIFA_CANDIDATE_SHA256");
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
