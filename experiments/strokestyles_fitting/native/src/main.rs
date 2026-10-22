//! Minimal CLI over the parity/raster adapter (diagnostic use only).

use strokestyles_fit_adapter as adapter;
mod capture;
mod text_layout;

fn read_json(path: &str) -> serde_json::Value {
    let text = std::fs::read_to_string(path).expect("read input file");
    serde_json::from_str(&text).expect("parse input JSON")
}

fn usage() -> ! {
    eprintln!("usage: adapter parity --record FILE");
    eprintln!(
        "       adapter capture --font PATH --chars STRING --out PATH [--size 16] [--axes JSON]"
    );
    eprintln!(
        "       adapter text-layout --font PATH --chars STRING --text-file PATH --out PATH [--size 16] [--axes JSON]"
    );
    eprintln!("       adapter rasterize --commands FILE [--mono-raster JSON] [--scan FILE]");
    eprintln!("       adapter candidate --record FILE --commands FILE");
    std::process::exit(2);
}

fn print_output(output: &font_generator::probe::RasterOutput) {
    println!(
        "{}",
        serde_json::json!({
            "left": output.left,
            "top": output.top,
            "width": output.width,
            "height": output.height,
            "pixels": output.pixels,
            "coverage": output.coverage,
        })
    );
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        usage();
    }
    match args[1].as_str() {
        "capture" => {
            if let Err(error) = capture::run(&args[2..]) {
                eprintln!("capture error: {error}");
                std::process::exit(1);
            }
        }
        "text-layout" => {
            if let Err(error) = text_layout::run(&args[2..]) {
                eprintln!("text-layout error: {error}");
                std::process::exit(1);
            }
        }
        "parity" => {
            let path = args
                .windows(2)
                .find(|w| w[0] == "--record")
                .map(|w| w[1].as_str())
                .unwrap_or_else(|| usage());
            let record = read_json(path);
            match adapter::parity_record(&record) {
                Ok(report) => {
                    println!("{}", serde_json::to_string_pretty(&report).unwrap());
                    if !report
                        .get("match")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false)
                    {
                        std::process::exit(1);
                    }
                }
                Err(error) => {
                    eprintln!("parity error: {error}");
                    std::process::exit(1);
                }
            }
        }
        "rasterize" => {
            let path = args
                .windows(2)
                .find(|w| w[0] == "--commands")
                .map(|w| w[1].as_str())
                .unwrap_or_else(|| usage());
            let mono_json = args
                .windows(2)
                .find(|w| w[0] == "--mono-raster")
                .map(|w| w[1].as_str());
            let scan_path = args
                .windows(2)
                .find(|w| w[0] == "--scan")
                .map(|w| w[1].as_str());
            let commands = read_json(path);
            let parsed = adapter::parse_commands(&commands).unwrap_or_else(|e| {
                eprintln!("parse error: {e}");
                std::process::exit(1);
            });
            let mono_raster: font_generator::MonoRasterSettings = match mono_json {
                Some(text) => serde_json::from_str(text).unwrap_or_else(|e| {
                    eprintln!("mono-raster error: {e}");
                    std::process::exit(1);
                }),
                None => Default::default(),
            };
            let scan_value = scan_path.map(read_json);
            let scan = scan_value.as_ref().map(|v| {
                adapter::parse_scan_state(v).unwrap_or_else(|e| {
                    eprintln!("scan error: {e}");
                    std::process::exit(1);
                })
            });
            match adapter::rasterize(&parsed, &mono_raster, scan.as_ref()) {
                Ok(output) => print_output(&output),
                Err(error) => {
                    eprintln!("raster error: {error}");
                    std::process::exit(1);
                }
            }
        }
        "candidate" => {
            let record_path = args
                .windows(2)
                .find(|w| w[0] == "--record")
                .map(|w| w[1].as_str())
                .unwrap_or_else(|| usage());
            let commands_path = args
                .windows(2)
                .find(|w| w[0] == "--commands")
                .map(|w| w[1].as_str())
                .unwrap_or_else(|| usage());
            let record = read_json(record_path);
            let commands = read_json(commands_path);
            match adapter::rasterize_record(&record, Some(&commands)) {
                Ok(output) => print_output(&output),
                Err(error) => {
                    eprintln!("candidate error: {error}");
                    std::process::exit(1);
                }
            }
        }
        _ => usage(),
    }
}
