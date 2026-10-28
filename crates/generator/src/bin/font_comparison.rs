use font_generator::comparison::publish;
use std::{env, path::Path, process::ExitCode};

fn main() -> ExitCode {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() != 2 {
        eprintln!("Usage: font_comparison CONFIG.json SPECIMEN_DIRECTORY");
        return ExitCode::FAILURE;
    }
    match publish(Path::new(&args[0]), Path::new(&args[1])) {
        Ok(count) => {
            println!("Published {count} glyph comparisons.");
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}
