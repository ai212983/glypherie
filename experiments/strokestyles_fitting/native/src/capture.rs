//! Explicit single-case capture CLI over maintained generator APIs.
//!
//! `run` expects the argument slice after the `capture` mode word:
//! `--font PATH --chars STRING --out PATH [--size 16] [--axes JSON]`.
//! It writes a one-element JSON array with the exact case schema of the
//! native diagonal audit: `{family, size, axes, source, modes}` where
//! `source` is the independent `mono_1bit` reference and `modes` holds the
//! `auto_default` and `selective_default` candidate reports. Native input
//! validation (axes, repertoire, raster settings) stays in the generator;
//! this module only wires explicit arguments and refuses to overwrite the
//! input font file.

use font_generator::{
    candidate,
    reference::{reference, ReferenceRequest},
    renderer::Rasterization,
    Config, Hinting, MonoRasterSettings,
};
use std::collections::BTreeMap;

fn fail<T>(message: impl Into<String>) -> Result<T, Box<dyn std::error::Error>> {
    Err(std::io::Error::new(std::io::ErrorKind::InvalidInput, message.into()).into())
}

fn missing(name: &str) -> Box<dyn std::error::Error> {
    std::io::Error::new(std::io::ErrorKind::InvalidInput, format!("missing {name}")).into()
}

fn invalid(what: &str) -> Box<dyn std::error::Error> {
    std::io::Error::new(std::io::ErrorKind::InvalidInput, format!("invalid {what}")).into()
}

struct Parsed {
    font: String,
    chars: String,
    out: String,
    size: f32,
    axes: BTreeMap<String, f32>,
}

fn flag<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
    args.windows(2)
        .find(|w| w[0] == name)
        .map(|w| w[1].as_str())
}

fn parse(args: &[String]) -> Result<Parsed, Box<dyn std::error::Error>> {
    let font = flag(args, "--font").ok_or_else(|| missing("--font PATH"))?;
    let chars = flag(args, "--chars").ok_or_else(|| missing("--chars STRING"))?;
    let out = flag(args, "--out").ok_or_else(|| missing("--out PATH"))?;
    if chars.is_empty() {
        return fail("empty --chars STRING");
    }
    let size = match flag(args, "--size") {
        Some(text) => text.parse::<f32>().map_err(|_| invalid("--size PX"))?,
        None => 16.0,
    };
    if !size.is_finite() || size <= 0.0 {
        return fail("invalid --size PX");
    }
    let axes: BTreeMap<String, f32> = match flag(args, "--axes") {
        Some(text) => serde_json::from_str(text).map_err(|_| invalid("--axes JSON"))?,
        None => BTreeMap::new(),
    };
    if axes.values().any(|v| !v.is_finite()) {
        return fail("non-finite axis value");
    }
    Ok(Parsed {
        font: font.into(),
        chars: chars.into(),
        out: out.into(),
        size,
        axes,
    })
}

/// Capture one case; `args` is the slice after the `capture` mode word.
pub fn run(args: &[String]) -> Result<(), Box<dyn std::error::Error>> {
    let parsed = parse(args)?;
    let out_path = std::path::Path::new(&parsed.out);
    if let Some(parent) = out_path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)?;
        }
    }
    let data = std::fs::read(&parsed.font)?;
    // Refuse to overwrite the input font: compare the canonical input path
    // against the canonicalized output parent joined with the file name.
    let font_canon = std::fs::canonicalize(&parsed.font)?;
    let out_canon = if out_path.exists() {
        std::fs::canonicalize(out_path)?
    } else {
        match out_path.parent() {
            Some(parent) if !parent.as_os_str().is_empty() => {
                std::fs::canonicalize(parent)?.join(out_path.file_name().unwrap_or_default())
            }
            // A bare file name resolves against the canonical working directory.
            _ => std::fs::canonicalize(std::env::current_dir()?)?
                .join(out_path.file_name().unwrap_or_default()),
        }
    };
    if out_canon == font_canon {
        return fail("refusing to overwrite the input font file");
    }
    let family = std::path::Path::new(&parsed.font)
        .file_stem()
        .and_then(|s| s.to_str())
        .ok_or_else(|| invalid("--font PATH"))?;
    let cfg = Config {
        size_px: parsed.size,
        characters: parsed.chars.clone(),
        axes: parsed.axes.clone(),
        output_bits: 1,
        hinting: Hinting::None,
        ..Config::default()
    };
    let source = reference(
        &data,
        &ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: "none".into(),
            settings: cfg.clone(),
        },
    )?;
    let mut modes = serde_json::Map::new();
    for (policy, extension) in [
        ("auto_default", "mono-width-01"),
        ("selective_default", "font-hints-auto-01"),
    ] {
        let mut settings = cfg.clone();
        settings.hinting = Hinting::AutoFallback;
        settings.mono_raster = MonoRasterSettings {
            font_instructions: true,
            include_stubs: true,
            ..Default::default()
        };
        let report = candidate::render_with_rasterization(
            &data,
            &ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: extension.into(),
                settings,
            },
            Rasterization::FreeTypeMonoTerminals,
        )?;
        modes.insert(policy.into(), serde_json::to_value(report)?);
    }
    let case = serde_json::json!({
        "family": family, "size": parsed.size, "axes": parsed.axes,
        "source": source, "modes": modes,
    });
    std::fs::write(&parsed.out, serde_json::to_vec(&[case])?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(pairs: &[(&str, &str)]) -> Vec<String> {
        pairs
            .iter()
            .flat_map(|(k, v)| [k.to_string(), v.to_string()])
            .collect()
    }

    #[test]
    fn rejects_missing_flags() {
        assert!(parse(&[]).is_err());
        assert!(parse(&args(&[("--font", "a.ttf")])).is_err());
    }

    #[test]
    fn rejects_bad_size_axes_chars() {
        let base = [("--font", "a.ttf"), ("--chars", "kx"), ("--out", "o.json")];
        let mut with_size = base.to_vec();
        with_size.push(("--size", "nan"));
        assert!(parse(&args(&with_size)).is_err());
        let mut with_axes = base.to_vec();
        with_axes.push(("--axes", "[1]"));
        assert!(parse(&args(&with_axes)).is_err());
        let mut with_inf = base.to_vec();
        with_inf.push(("--axes", "{\"wght\": 1e999}"));
        // 1e999 parses to inf in f32 only via overflow to inf: rejected.
        assert!(parse(&args(&with_inf)).is_err());
    }

    #[test]
    fn parses_explicit_case() {
        let parsed = parse(&args(&[
            ("--font", "fonts/Roboto.ttf"),
            ("--chars", "kx"),
            ("--out", "o.json"),
            ("--size", "16"),
            ("--axes", "{\"wght\": 300.0, \"wdth\": 100.0}"),
        ]))
        .unwrap();
        assert_eq!(parsed.size, 16.0);
        assert_eq!(parsed.axes["wght"], 300.0);
    }
}
