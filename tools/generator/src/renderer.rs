//! Stable renderer roles. Revision/iteration numbers identify reviewed states.
use crate::{reference::ReferenceReport, reference::ReferenceRequest, Error};
use serde::{Deserialize, Serialize};

/// Explicit stages for current preview work. Layout is always the shared
/// bitmap metric policy, neutral by default with a uniform-tracking entry
/// point; historical roles stay separate.
/// FreeType's glyph metric model keeps fitted advances/bearings with fitting,
/// while scan conversion consumes the resulting outline without changing them:
/// https://freetype.org/freetype2/docs/glyphs/glyphs-3.html
#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct RenderPipeline {
    pub fitting: crate::stem_fitting::StemFittingStrategy,
    pub rasterization: Rasterization,
    // Independent opt-in for the reviewed stroke fitting sequence; default off
    // so omitted fields keep the established pipeline output bit-identical.
    #[serde(default, skip_serializing_if = "is_false")]
    pub diagonal_fitting: bool,
}

fn is_false(value: &bool) -> bool {
    !*value
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Rasterization {
    #[default]
    FreeTypeMono,
    FreeTypeMonoTerminals,
    Coverage,
}

impl RenderPipeline {
    pub fn validate(&self, config: &crate::Config) -> Result<(), Error> {
        // Width-only diagonal fitting is independent of native hints; it
        // needs 1-bit FreeType monochrome output on a supported strategy.
        if self.diagonal_fitting
            && (config.output_bits != 1
                || !matches!(
                    self.rasterization,
                    Rasterization::FreeTypeMono | Rasterization::FreeTypeMonoTerminals
                )
                || !matches!(
                    self.fitting,
                    crate::stem_fitting::StemFittingStrategy::FontHintsAuto
                        | crate::stem_fitting::StemFittingStrategy::UpstreamMono
                ))
        {
            return Err(crate::fail(
                "diagonal fitting requires 1-bit FreeTypeMono/Terminals with FontHintsAuto or UpstreamMono",
            ));
        }
        match config.output_bits {
            1 => {}
            2 | 3 | 4
                if self.rasterization == Rasterization::Coverage
                    && self.fitting == crate::stem_fitting::StemFittingStrategy::UpstreamMono => {}
            _ => {
                return Err(crate::fail(
                    "pipeline requires 1-bit output, or 2/3/4-bit coverage with automatic fitting",
                ))
            }
        }
        if matches!(
            self.fitting,
            crate::stem_fitting::StemFittingStrategy::SourceRelative
                | crate::stem_fitting::StemFittingStrategy::FontHintsAuto
        ) && self.rasterization == Rasterization::Coverage
        {
            return Err(crate::fail(
                "source-relative and selective fitting require monochrome scan conversion",
            ));
        }
        if self.rasterization == Rasterization::Coverage {
            crate::require_default_mono_raster(config)?;
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RendererRole {
    Reference,
    Baseline,
    Candidate,
}

pub fn render(
    data: &[u8],
    request: &ReferenceRequest,
    role: RendererRole,
) -> Result<ReferenceReport, Error> {
    match role {
        RendererRole::Reference => crate::reference::reference(data, request),
        RendererRole::Baseline => crate::baseline::render(data, request),
        RendererRole::Candidate if request.extensions == "none" => {
            crate::reference::reference(data, request)
        }
        RendererRole::Candidate => candidate(data, request),
    }
}

#[cfg(feature = "candidate")]
fn candidate(data: &[u8], request: &ReferenceRequest) -> Result<ReferenceReport, Error> {
    crate::candidate::render(data, request)
}

#[cfg(not(feature = "candidate"))]
fn candidate(_data: &[u8], _request: &ReferenceRequest) -> Result<ReferenceReport, Error> {
    Err(crate::fail(
        "candidate rendering requires the candidate Cargo feature",
    ))
}
