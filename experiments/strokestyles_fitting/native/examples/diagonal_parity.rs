//! Bit-checked diagnostic adapter over the maintained diagonal fitter.
use font_generator::diagonal_fitting;
use serde_json::{json, Value};
use std::io::{self, BufRead};
use strokestyles_fit_adapter::{parse_commands, rasterize_record};

fn cell(input: &Value) -> Result<Value, Box<dyn std::error::Error>> {
    let mut donors = input["donors"]
        .as_array()
        .ok_or("missing donors")?
        .iter()
        .collect::<Vec<_>>();
    donors.sort_by_key(|r| r["codepoint"].as_u64());
    let donor_commands = donors
        .iter()
        .map(|r| {
            Ok((
                parse_commands(&r["source_commands"])?,
                parse_commands(&r["fitted_commands"])?,
            ))
        })
        .collect::<Result<Vec<_>, font_generator::Error>>()?;
    let refs = donor_commands
        .iter()
        .map(|(s, u)| (s.as_slice(), u.as_slice()))
        .collect::<Vec<_>>();
    let size = input["size"].as_f64().ok_or("missing size")?;
    let reference = diagonal_fitting::build_reference(&refs, size);
    let mut results = Vec::new();
    for r in input["records"].as_array().ok_or("missing records")? {
        let source = parse_commands(&r["source_commands"])?;
        let upstream = parse_commands(&r["fitted_commands"])?;
        let native_axes = r
            .get("selective_fitting")
            .and_then(|s| s.get("native_axes"))
            .and_then(|a| serde_json::from_value::<[bool; 2]>(a.clone()).ok())
            .unwrap_or_else(|| {
                if r["selected_engine"] == "auto" {
                    [false, false]
                } else {
                    [true, true]
                }
            });
        let fit = diagonal_fitting::fit(&source, &upstream, size, &reference, native_axes)?;
        let commands = serde_json::to_value(&fit.commands)?;
        let raster = rasterize_record(r, Some(&commands))?;
        results.push(json!({"codepoint":r["codepoint"], "applied":fit.applied,
            "reason":fit.reason,"diagnostics":fit.diagnostics,"commands":commands,
            "raster": {"left":raster.left,"top":raster.top,"width":raster.width,
                "height":raster.height,"pixels":raster.pixels,"coverage":raster.coverage}}));
    }
    Ok(json!({"reference":reference,"results":results}))
}

fn main() {
    for line in io::stdin().lock().lines() {
        let output = line
            .map_err(|e| e.to_string())
            .and_then(|s| serde_json::from_str::<Value>(&s).map_err(|e| e.to_string()))
            .and_then(|v| cell(&v).map_err(|e| e.to_string()));
        match output {
            Ok(v) => println!("{v}"),
            Err(e) => {
                eprintln!("{e}");
                std::process::exit(1);
            }
        }
    }
}
