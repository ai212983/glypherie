//! Working renderer; revision/iteration identities are metadata.
use skrifa_candidate as fitting_skrifa;
const FITTING_SHA256: &str = env!("SKRIFA_CANDIDATE_SHA256");
include!("fitting.rs");
