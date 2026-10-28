//! Selectable upstream monochrome fitting policies over registry Skrifa.
//!
//! Each policy returns whole fitted outlines to the shared raster and source
//! layout pipeline. SourceRelative additionally preserves recognized source width relationships.
use crate::Hinting;
use serde::{Deserialize, Serialize};

pub const EXTENSIONS_FONT_HINTS_FIRST: &str = "font-hints-01";
pub const EXTENSIONS_MONO_WIDTH_01: &str = "mono-width-01";
pub const EXTENSIONS_SOURCE_WIDTH_01: &str = "source-width-01";
pub const EXTENSIONS_FONT_HINTS_AUTO: &str = "font-hints-auto-01";

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum StemFittingStrategy {
    /// Upstream Mono with the font's interpreter when available, otherwise
    /// the automatic hinter, except that TrueType fonts verified to carry no
    /// hint programs use the automatic hinter directly. See the generator API
    /// for the selection rules.
    #[default]
    FontHintsFirst,
    /// Force upstream automatic Mono fitting, ignoring embedded instructions.
    UpstreamMono,
    /// Font hints first with conservative source-relative straight-stroke coupling.
    SourceRelative,
    /// Native fitting on axes used by its instructions, automatic on the rest.
    FontHintsAuto,
}

impl StemFittingStrategy {
    pub fn extension(strategy: Option<Self>) -> &'static str {
        match strategy.unwrap_or_default() {
            Self::FontHintsFirst => EXTENSIONS_FONT_HINTS_FIRST,
            Self::UpstreamMono => EXTENSIONS_MONO_WIDTH_01,
            Self::SourceRelative => EXTENSIONS_SOURCE_WIDTH_01,
            Self::FontHintsAuto => EXTENSIONS_FONT_HINTS_AUTO,
        }
    }

    /// The selected policy owns engine choice. Record this effective mode
    /// before drawing, so provenance describes the actual library request.
    pub fn hinting(self) -> Hinting {
        match self {
            Self::FontHintsFirst | Self::SourceRelative | Self::FontHintsAuto => {
                Hinting::AutoFallback
            }
            Self::UpstreamMono => Hinting::Auto,
        }
    }
}
