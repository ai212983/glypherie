use font_generator::batch::{rasterize_batch, BatchJob};
use std::{env, fs, path::Path, process::ExitCode};

fn run() -> Result<(), String> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() == 1 && (args[0] == "--help" || args[0] == "-h") {
        println!("Usage: common_rasterizer INPUT.json OUTPUT.json");
        return Ok(());
    }
    if args.len() != 2 {
        return Err("usage: common_rasterizer INPUT.json OUTPUT.json".into());
    }
    let input_path = Path::new(&args[0]);
    let raw = fs::read(input_path).map_err(|e| format!("cannot read input: {e}"))?;
    let job: BatchJob = serde_json::from_slice(&raw).map_err(|e| format!("invalid input: {e}"))?;
    let output = rasterize_batch(&job).map_err(|e| e.to_string())?;
    let mut encoded = serde_json::to_vec_pretty(&output).map_err(|e| e.to_string())?;
    encoded.push(b'\n');
    let destination = Path::new(&args[1]);
    if destination.exists() {
        let want = fs::canonicalize(destination).map_err(|e| e.to_string())?;
        let input_canon = fs::canonicalize(input_path).map_err(|e| e.to_string())?;
        if want == input_canon {
            return Err("output must differ from the input".into());
        }
    }
    fs::write(destination, encoded).map_err(|e| format!("cannot write output: {e}"))?;
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("common_rasterizer: {error}");
            ExitCode::FAILURE
        }
    }
}
