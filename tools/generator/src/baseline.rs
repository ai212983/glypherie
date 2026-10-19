//! Legacy comparison snapshot; revision/iteration identities are metadata.
use skrifa_baseline as fitting_skrifa;
const FITTING_SHA256: &str = env!("SKRIFA_BASELINE_SHA256");
const ADVANCE_POLICY: crate::reference::AdvancePolicy = crate::reference::AdvancePolicy::Linear;
/// Legacy comparison identity.
pub const VERSION: &str = "001.02";
// The legacy fork predates the current registry dependency. Its provenance
// must describe its own upstream base, not whichever registry crate is latest.
fn fitting_skrifa_version() -> String {
    let manifest = include_str!("../vendor/skrifa-baseline/Cargo.toml");
    manifest
        .lines()
        .find_map(|line| line.strip_prefix("version = "))
        .unwrap()
        .trim_matches('"')
        .to_string()
}
fn fitting_skrifa_checksum() -> String {
    // Source ancestry recorded in vendor/skrifa-baseline/PATCH.md.
    "d4febebda507fb889c545a37a135517769d1391941013561292897961d1887d6".into()
}
include!("fitting.rs");
