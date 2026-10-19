//! Selectable upstream monochrome fitting policies over registry Skrifa.
//!
//! Each policy returns whole fitted outlines to the shared raster and source
//! layout pipeline. No project geometry adjustments or stroke recognizer run.
use crate::Hinting;
use serde::{Deserialize, Serialize};

pub const EXTENSIONS_FONT_HINTS_FIRST: &str = "font-hints-01";
pub const EXTENSIONS_MONO_WIDTH_01: &str = "mono-width-01";

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum StemFittingStrategy {
    /// Upstream Mono with the font's interpreter when available, otherwise
    /// the automatic hinter. See Skrifa Engine::AutoFallback.
    #[default]
    FontHintsFirst,
    /// Force upstream automatic Mono fitting, ignoring embedded instructions.
    UpstreamMono,
}

impl StemFittingStrategy {
    pub fn extension(strategy: Option<Self>) -> &'static str {
        match strategy.unwrap_or_default() {
            Self::FontHintsFirst => EXTENSIONS_FONT_HINTS_FIRST,
            Self::UpstreamMono => EXTENSIONS_MONO_WIDTH_01,
        }
    }

    /// The selected policy owns engine choice. Record this effective mode
    /// before drawing, so provenance describes the actual library request.
    pub fn hinting(self) -> Hinting {
        match self {
            Self::FontHintsFirst => Hinting::AutoFallback,
            Self::UpstreamMono => Hinting::Auto,
        }
    }
}
