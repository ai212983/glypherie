//! Approved production snapshot; revision/iteration identities are metadata.
use skrifa_baseline as fitting_skrifa;
const FITTING_SHA256: &str = env!("SKRIFA_BASELINE_SHA256");
/// Latest explicitly approved model. Update only on an authorized promotion.
pub const VERSION: &str = "001.01";
include!("fitting.rs");
