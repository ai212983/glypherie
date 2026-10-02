use crate::probe::{rasterize, FittedCommand};
use crate::{fail, Config, Error};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const COORD_SCALE: f32 = 64.0;
pub const MAX_RAW_COORD: i32 = 2097152;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct BatchSettings {
    #[serde(default = "default_output_bits")]
    pub output_bits: u8,
    #[serde(default = "default_mono_threshold")]
    pub mono_threshold: u8,
    #[serde(default = "default_gray_gamma")]
    pub gray_gamma: f32,
}

fn default_output_bits() -> u8 {
    1
}

fn default_mono_threshold() -> u8 {
    128
}

fn default_gray_gamma() -> f32 {
    1.0
}

impl Default for BatchSettings {
    fn default() -> Self {
        Self {
            output_bits: 1,
            mono_threshold: 128,
            gray_gamma: 1.0,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RawCommand {
    pub op: String,
    pub coords: Vec<i32>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct BatchCaseInput {
    pub key: String,
    pub commands: Vec<RawCommand>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct BatchJob {
    #[serde(default)]
    pub settings: BatchSettings,
    pub cases: Vec<BatchCaseInput>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct BatchCaseOutput {
    pub key: String,
    pub fitted_commands: Vec<FittedCommand>,
    pub pixels: Vec<u8>,
    pub coverage: Vec<u8>,
    pub left: i32,
    pub top: i32,
    pub width: u32,
    pub height: u32,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct BatchOutput {
    pub output_bits: u8,
    pub mono_threshold: u8,
    pub gray_gamma: f32,
    pub cases: Vec<BatchCaseOutput>,
}

pub fn convert_coord(raw: i32) -> f32 {
    raw as f32 / COORD_SCALE
}

fn convert_checked(raw: i32) -> Result<f32, Error> {
    if raw > MAX_RAW_COORD || raw < -MAX_RAW_COORD {
        return Err(fail("coordinate outside safe bounds"));
    }
    Ok(convert_coord(raw))
}

pub fn to_fitted(commands: &[RawCommand]) -> Result<Vec<FittedCommand>, Error> {
    let mut out = Vec::with_capacity(commands.len());
    let mut open = false;
    for command in commands {
        match command.op.as_str() {
            "move" => {
                if command.coords.len() != 2 {
                    return Err(fail("move requires exactly 2 coordinates"));
                }
                if open {
                    return Err(fail(
                        "move opens a contour before the previous contour closed",
                    ));
                }
                let x = convert_checked(command.coords[0])?;
                let y = convert_checked(command.coords[1])?;
                out.push(FittedCommand::MoveTo(x, y));
                open = true;
            }
            "line" => {
                if command.coords.len() != 2 {
                    return Err(fail("line requires exactly 2 coordinates"));
                }
                if !open {
                    return Err(fail("line without an open contour"));
                }
                let x = convert_checked(command.coords[0])?;
                let y = convert_checked(command.coords[1])?;
                out.push(FittedCommand::LineTo(x, y));
            }
            "quadratic" => {
                if command.coords.len() != 4 {
                    return Err(fail("quadratic requires exactly 4 coordinates"));
                }
                if !open {
                    return Err(fail("quadratic without an open contour"));
                }
                let x1 = convert_checked(command.coords[0])?;
                let y1 = convert_checked(command.coords[1])?;
                let x = convert_checked(command.coords[2])?;
                let y = convert_checked(command.coords[3])?;
                out.push(FittedCommand::QuadTo(x1, y1, x, y));
            }
            "cubic" => {
                if command.coords.len() != 6 {
                    return Err(fail("cubic requires exactly 6 coordinates"));
                }
                if !open {
                    return Err(fail("cubic without an open contour"));
                }
                let x1 = convert_checked(command.coords[0])?;
                let y1 = convert_checked(command.coords[1])?;
                let x2 = convert_checked(command.coords[2])?;
                let y2 = convert_checked(command.coords[3])?;
                let x = convert_checked(command.coords[4])?;
                let y = convert_checked(command.coords[5])?;
                out.push(FittedCommand::CurveTo(x1, y1, x2, y2, x, y));
            }
            "close" => {
                if !command.coords.is_empty() {
                    return Err(fail("close requires exactly 0 coordinates"));
                }
                if !open {
                    return Err(fail("close without an open contour"));
                }
                out.push(FittedCommand::Close);
                open = false;
            }
            _ => {
                return Err(fail(format!("unknown op {}", command.op)));
            }
        }
    }
    if open {
        return Err(fail("unclosed contour at end of command sequence"));
    }
    Ok(out)
}

fn batch_config(settings: &BatchSettings) -> Result<Config, Error> {
    if !matches!(settings.output_bits, 1 | 3) {
        return Err(fail(
            "batch requires output_bits 1 or 3 for mono_1bit/gray_3bit profiles",
        ));
    }
    if settings.mono_threshold == 0 {
        return Err(fail("mono_threshold must be within 1..=255"));
    }
    if !settings.gray_gamma.is_finite() || settings.gray_gamma <= 0.0 {
        return Err(fail("gray_gamma must be finite and positive"));
    }
    Ok(Config {
        output_bits: settings.output_bits,
        mono_threshold: settings.mono_threshold,
        gray_gamma: settings.gray_gamma,
        ..Config::default()
    })
}

pub fn rasterize_batch(job: &BatchJob) -> Result<BatchOutput, Error> {
    let config = batch_config(&job.settings)?;
    let mut seen = BTreeSet::new();
    for case in &job.cases {
        if case.key.is_empty() {
            return Err(fail("case key must be nonempty"));
        }
        if !seen.insert(case.key.clone()) {
            return Err(fail(format!("duplicate case key {}", case.key)));
        }
    }
    let mut ordered: BTreeMap<&str, &BatchCaseInput> = BTreeMap::new();
    for case in &job.cases {
        ordered.insert(case.key.as_str(), case);
    }
    let mut cases = Vec::with_capacity(ordered.len());
    for (key, input) in ordered {
        let fitted = to_fitted(&input.commands)?;
        let output = rasterize(&fitted, &config)?;
        cases.push(BatchCaseOutput {
            key: key.to_string(),
            fitted_commands: fitted,
            pixels: output.pixels,
            coverage: output.coverage,
            left: output.left,
            top: output.top,
            width: output.width,
            height: output.height,
        });
    }
    Ok(BatchOutput {
        output_bits: job.settings.output_bits,
        mono_threshold: job.settings.mono_threshold,
        gray_gamma: job.settings.gray_gamma,
        cases,
    })
}
