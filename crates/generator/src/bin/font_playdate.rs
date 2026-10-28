//! Native Playdate `.fnt` exporter.
//!
//! Reads a sfnt font plus a [`font_generator::playdate::ExportRequest`] (JSON)
//! and writes a standalone Playdate source font; see
//! <https://sdk.play.date/Inside%20Playdate.html#_fonts>.
use font_generator::playdate::{export, ExportRequest};
use std::{env, fs, path::Path, process::ExitCode};

fn run() -> Result<(), String> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() == 1 && (args[0] == "--help" || args[0] == "-h") {
        println!("Usage: font_playdate FONT REQUEST.json OUTPUT.fnt");
        return Ok(());
    }
    if args.len() != 3 {
        return Err("usage: font_playdate FONT REQUEST.json OUTPUT.fnt".into());
    }
    let font = fs::read(Path::new(&args[0])).map_err(|e| format!("cannot read font: {e}"))?;
    let request: ExportRequest = serde_json::from_slice(
        &fs::read(Path::new(&args[1])).map_err(|e| format!("cannot read request: {e}"))?,
    )
    .map_err(|e| format!("invalid request: {e}"))?;
    let bytes = export(&font, &request).map_err(|e| e.to_string())?;
    let destination = Path::new(&args[2]);
    for input in [Path::new(&args[0]), Path::new(&args[1])] {
        if destination.exists()
            && fs::canonicalize(destination).map_err(|e| e.to_string())?
                == fs::canonicalize(input).map_err(|e| e.to_string())?
        {
            return Err("output must differ from the font and request inputs".into());
        }
    }
    fs::write(destination, bytes).map_err(|e| format!("cannot write output: {e}"))?;
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("font_playdate: {error}");
            ExitCode::FAILURE
        }
    }
}
