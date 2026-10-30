use font_generator::{diagonal_fitting as fitting, fitting_source, Config};
use serde_json::{json, Value};
use std::io::{self, BufRead};
use strokestyles_fit_adapter::{parse_commands, rasterize_record};

fn cell(input: Value) -> Result<Value, Box<dyn std::error::Error>> {
    let size = input["size"].as_f64().ok_or("size")?;
    let mut donors: Vec<_> = input["donors"].as_array().ok_or("donors")?.iter().collect();
    donors.sort_by_key(|d| d["codepoint"].as_u64());
    let donor_commands = donors
        .iter()
        .map(|r| {
            Ok((
                parse_commands(&r["source_commands"])?,
                parse_commands(&r["fitted_commands"])?,
            ))
        })
        .collect::<Result<Vec<_>, font_generator::Error>>()?;
    let reference = fitting::build_reference(
        &donor_commands
            .iter()
            .map(|(s, u)| (s.as_slice(), u.as_slice()))
            .collect::<Vec<_>>(),
        size,
    );
    let data = std::fs::read(input["font"].as_str().ok_or("font")?)?;
    let config = Config {
        size_px: size as f32,
        axes: serde_json::from_value(input["axes"].clone())?,
        ..Config::default()
    };
    let mut results = Vec::new();
    for r in input["records"].as_array().ok_or("records")? {
        let source = parse_commands(&r["source_commands"])?;
        let upstream = parse_commands(&r["fitted_commands"])?;
        let native_axes: [bool; 2] = serde_json::from_value(r["native_axes"].clone())?;
        let raw = if input["source_mode"] == "runtime" {
            fitting_source::draw(
                &data,
                &config,
                r["glyph_id"].as_u64().ok_or("glyph_id")? as u32,
            )?
        } else {
            serde_json::from_value::<fitting_source::SourceOutline>(r["raw_outline"].clone())?
        };
        let result = match input["mode"].as_str().unwrap_or("sequence") {
            "source-shape" => fitting::curve_model::diagnose_automatic_shape(
                &raw,
                &source,
                &upstream,
                size,
                &reference,
                native_axes,
            )?,
            "terminal" => fitting::terminal::fit_terminal(
                &raw,
                &source,
                &upstream,
                size,
                &reference,
                native_axes,
            ),
            "joint" => fitting::joint::fit(&source, &upstream, size, &reference, native_axes)?,
            "attached" => {
                fitting::attached::fit(&source, &upstream, size, &reference, native_axes)?
            }
            "crossing" => {
                fitting::crossing::fit(&raw, &source, &upstream, size, &reference, native_axes)?
            }
            "curve" => {
                let preferred = parse_commands(&r["preferred_commands"])?;
                fitting::curve_model::fit_horizontal(
                    &source,
                    &preferred,
                    size,
                    &reference,
                    native_axes,
                )?
            }
            _ => fitting::approved::fit(
                Some(&raw),
                &source,
                &upstream,
                size,
                &reference,
                native_axes,
            )?,
        };
        let commands = serde_json::to_value(&result.commands)?;
        let raster = rasterize_record(r, Some(&commands))?;
        results.push(json!({"codepoint":r["codepoint"],"applied":result.applied,"reason":result.reason,
            "commands":commands,"diagnostics":if input["diagnostics"]==true { result.diagnostics } else {Value::Null},
            "raster":{"left":raster.left,"top":raster.top,"width":raster.width,"height":raster.height,"pixels":raster.pixels}}));
    }
    Ok(json!({"reference":reference,"results":results}))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    for line in io::stdin().lock().lines() {
        println!("{}", cell(serde_json::from_str(&line?)?)?);
    }
    Ok(())
}
