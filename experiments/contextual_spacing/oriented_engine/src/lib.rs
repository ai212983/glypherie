//! Experimental Rust/WASM runtime for the frozen YinYang oriented fields
//! plus the corrected SCORE-v2 interpreter.
//!
//! Own leaf: `experiments/contextual_spacing/oriented_engine/`. No
//! maintained crate depends on this; the reviewed page is untouched.

pub mod bessel;
pub mod engine;
pub mod fft;
pub mod fields;
pub mod local_energy;
pub mod params;
pub mod score;

#[cfg(feature = "wasm")]
pub mod bindings;

pub mod capture;

pub use engine::{
    CacheStats, Engine, LocalPairResult, LocalStepRecord, NoDomain, PairResult, SearchDomain,
    StepRecord,
};
pub use local_energy::{LocalAbstain, LocalConfidence, LocalStepScore};
pub use params::{EngineParams, ScoreParams};
pub use score::Strength;

/// Placement-search identity, versioned separately from the model and the
/// page settings: exhaustive whole-pixel enumeration over the
/// geometry-derived ordered-letter domain (ink-ordered lower bound
/// intersected with strictly forward pen order, padded field-overlap
/// upper bound), TIE-v2 over supported steps only.
pub const SEARCH_POLICY: &str = "yinyangfit-search-v2";

/// Engine errors surface as-is (thrown strings at the WASM seam).
#[derive(Debug, Clone)]
pub enum EngineError {
    Invalid(String),
    Cancelled,
}

impl std::fmt::Display for EngineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            EngineError::Invalid(msg) => write!(f, "invalid: {msg}"),
            EngineError::Cancelled => write!(f, "cancelled"),
        }
    }
}

impl std::error::Error for EngineError {}
