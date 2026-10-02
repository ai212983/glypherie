//! Evaluate the configured corpus without publishing or changing preview scope.
use font_generator::{
    evaluation::{evaluate, Evaluation},
    reference::{reference, ReferenceRequest},
    specimen_config::load,
    Config, Hinting,
};
use serde::Serialize;
use std::{collections::BTreeMap, env, fs, path::Path, process::ExitCode};

#[derive(Serialize)]
struct Case {
    family: String,
    size_px: f32,
    axes: BTreeMap<String, f32>,
    profile: String,
    variant: String,
    evaluation: Evaluation,
}

#[derive(Serialize)]
struct Corpus {
    schema_version: u32,
    hard_invariants_pass: bool,
    cases: Vec<Case>,
}

fn run() -> Result<bool, String> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() == 1 && (args[0] == "--help" || args[0] == "-h") {
        println!("Usage: font_evaluate SPECIMENS.json OUTPUT.json\nRuns source/upstream/latest-candidate diagnostics; writes JSON even when hard invariants fail. No optical score or preview publication.");
        return Ok(true);
    }
    if args.len() != 2 {
        return Err("usage: font_evaluate SPECIMENS.json OUTPUT.json".into());
    }
    let config_path = Path::new(&args[0]);
    let output_path = Path::new(&args[1]);
    let loaded = load(config_path).map_err(|e| e.to_string())?;
    let latest = loaded.config.latest_variant().map_err(|e| e.to_string())?;
    if output_path.exists() {
        let output = fs::canonicalize(output_path).map_err(|e| e.to_string())?;
        for input in
            std::iter::once(config_path).chain(loaded.cases.iter().map(|case| case.font.as_path()))
        {
            if output == fs::canonicalize(input).map_err(|e| e.to_string())? {
                return Err("output must differ from config and font inputs".into());
            }
        }
    }
    let mut fonts = BTreeMap::new();
    let mut cases = Vec::new();
    for case in loaded.cases.iter().filter(|case| case.variant == latest) {
        let data = if let Some(data) = fonts.get(&case.font) {
            data
        } else {
            let data = fs::read(&case.font).map_err(|e| format!("cannot read font: {e}"))?;
            fonts.entry(case.font.clone()).or_insert(data)
        };
        let variant = loaded
            .config
            .variants
            .iter()
            .find(|v| v.id == case.variant)
            .unwrap();
        let profile = loaded
            .config
            .profiles
            .iter()
            .find(|p| p.id == case.profile)
            .unwrap();
        let request = ReferenceRequest {
            profile: profile.id.clone(),
            extensions: "none".into(),
            settings: Config {
                size_px: case.size_px,
                axes: case.axes.clone(),
                characters: loaded.config.characters.clone(),
                hinting: variant.hinting,
                output_bits: profile.output_bits,
                mono_threshold: profile.mono_threshold,
                gray_gamma: profile.gray_gamma,
                ..Config::default()
            },
        };
        let upstream = reference(data, &request).map_err(|e| e.to_string())?;
        let mut source_request = request.clone();
        source_request.settings.hinting = Hinting::None;
        let source = reference(data, &source_request).map_err(|e| e.to_string())?;
        let mut candidate_request = request;
        candidate_request.extensions = variant.extensions.clone();
        let candidate =
            font_generator::renderer::render(data, &candidate_request, variant.renderer())
                .map_err(|e| e.to_string())?;
        cases.push(Case {
            family: case.family_id.clone(),
            size_px: case.size_px,
            axes: case.axes.clone(),
            profile: case.profile.clone(),
            variant: case.variant.clone(),
            evaluation: evaluate(&source, &upstream, &candidate),
        });
    }
    if cases.is_empty() {
        return Err("latest variant has no configured cases".into());
    }
    let pass = cases
        .iter()
        .all(|case| case.evaluation.hard_invariants_pass);
    let corpus = Corpus {
        schema_version: 1,
        hard_invariants_pass: pass,
        cases,
    };
    let mut output = serde_json::to_vec_pretty(&corpus).map_err(|e| e.to_string())?;
    output.push(b'\n');
    fs::write(output_path, output).map_err(|e| format!("cannot write evaluation: {e}"))?;
    println!(
        "Evaluated {} cases; hard invariants {}. Optical acceptance remains separate.",
        corpus.cases.len(),
        if pass { "passed" } else { "failed" }
    );
    Ok(pass)
}

fn main() -> ExitCode {
    match run() {
        Ok(true) => ExitCode::SUCCESS,
        Ok(false) => ExitCode::FAILURE,
        Err(error) => {
            eprintln!("font_evaluate: {error}");
            ExitCode::FAILURE
        }
    }
}
