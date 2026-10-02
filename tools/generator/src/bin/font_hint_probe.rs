use font_generator::{probe::probe, Config};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{env, fs, path::Path, process::ExitCode};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Job {
    font: String,
    provenance: Provenance,
    settings: Config,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Provenance {
    source: String,
    license: String,
    expected_sha256: String,
}

#[derive(Serialize)]
struct Artifact<T: Serialize> {
    schema_version: u32,
    generator_version: &'static str,
    dependency_lock_sha256: String,
    provenance: Provenance,
    generated: T,
}

fn run() -> Result<(), String> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() == 1 && (args[0] == "--help" || args[0] == "-h") {
        println!("Usage: font_hint_probe JOB.json OUTPUT.json");
        return Ok(());
    }
    if args.len() != 2 {
        return Err("usage: font_hint_probe JOB.json OUTPUT.json".into());
    }
    let job_path = Path::new(&args[0]);
    let job: Job =
        serde_json::from_slice(&fs::read(job_path).map_err(|e| format!("cannot read job: {e}"))?)
            .map_err(|e| format!("invalid job: {e}"))?;
    if job.provenance.source.trim().is_empty() || job.provenance.license.trim().is_empty() {
        return Err(
            "provenance source and license must be nonempty (use 'unknown' when unverified)".into(),
        );
    }
    let font_path = job_path.parent().unwrap_or(Path::new(".")).join(&job.font);
    let font = fs::read(&font_path).map_err(|e| format!("cannot read font: {e}"))?;
    let checksum = format!("{:x}", Sha256::digest(&font));
    if job.provenance.expected_sha256 != checksum {
        return Err(format!(
            "font checksum mismatch: actual SHA-256 is {checksum}"
        ));
    }
    let generated = probe(&font, &job.settings).map_err(|e| e.to_string())?;
    let artifact = Artifact {
        schema_version: 1,
        generator_version: env!("CARGO_PKG_VERSION"),
        dependency_lock_sha256: font_generator::probe::lock_sha256(),
        provenance: job.provenance,
        generated,
    };
    let mut output = serde_json::to_vec_pretty(&artifact).map_err(|e| e.to_string())?;
    output.push(b'\n');
    let destination = Path::new(&args[1]);
    for input in [job_path, font_path.as_path()] {
        if destination.exists()
            && fs::canonicalize(destination).map_err(|e| e.to_string())?
                == fs::canonicalize(input).map_err(|e| e.to_string())?
        {
            return Err("output must differ from the job and font inputs".into());
        }
    }
    fs::write(destination, output).map_err(|e| format!("cannot write output: {e}"))?;
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("font_hint_probe: {error}");
            ExitCode::FAILURE
        }
    }
}
