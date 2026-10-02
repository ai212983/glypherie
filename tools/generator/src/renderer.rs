//! Stable renderer roles. Revision/iteration numbers identify reviewed states.
use crate::{reference::ReferenceReport, reference::ReferenceRequest, Error};
use serde::{Deserialize, Serialize};

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
