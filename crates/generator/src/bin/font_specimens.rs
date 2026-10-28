use font_generator::specimens::publish;
use std::{env, path::Path, process::ExitCode};

fn run() -> Result<(), String> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() == 1 && (args[0] == "--help" || args[0] == "-h") {
        println!("Usage: font_specimens CONFIG.json OUTPUT_DIRECTORY");
        return Ok(());
    }
    if args.len() != 2 {
        return Err("usage: font_specimens CONFIG.json OUTPUT_DIRECTORY".into());
    }
    let result = publish(Path::new(&args[0]), Path::new(&args[1])).map_err(|e| e.to_string())?;
    println!(
        "Published {} packages, {} profile cases, {} images, {} failed/unsupported samples.",
        result.packages.len(),
        result.case_count,
        result.image_count,
        result.failure_count
    );
    println!(
        "Active specimens: {}",
        Path::new(&args[1]).join("active.json").display()
    );
    for package in result.packages {
        println!("Package: {package}");
    }
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("font_specimens: {error}");
            ExitCode::FAILURE
        }
    }
}
