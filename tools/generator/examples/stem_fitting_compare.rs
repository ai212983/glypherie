//! Isolated fitting comparison: identical candidate raster, source metrics.
use font_generator::{
    candidate,
    reference::{reference, ReferenceRequest, PROFILE_MONO_1BIT},
    Config, Hinting,
};
use serde_json::json;
use std::{collections::BTreeMap, env, fs, path::Path};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let destination = env::args().nth(1).ok_or("expected output JSON path")?;
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut cases = Vec::new();
    for (family, size, slant) in [
        ("Roboto", 13.0, None),
        ("Roboto", 14.0, None),
        ("Roboto", 15.0, None),
        ("Roboto", 16.0, None),
        ("Roboto-Italic", 14.0, None),
        ("SourceSans3", 14.0, None),
        ("Literata", 14.0, None),
        ("RobotoFlex", 14.0, Some(-10.0)),
    ] {
        let data = fs::read(root.join(format!("fonts/{family}.ttf")))?;
        let mut axes = BTreeMap::from([(String::from("wght"), 400.0)]);
        if family.starts_with("Roboto") {
            axes.insert(String::from("wdth"), 100.0);
        }
        if family == "Literata" || family == "RobotoFlex" {
            axes.insert(String::from("opsz"), size);
        }
        if let Some(slant) = slant {
            axes.insert(String::from("slnt"), slant);
        }
        let mut request = ReferenceRequest {
            profile: PROFILE_MONO_1BIT.into(),
            extensions: "none".into(),
            settings: Config {
                characters: "mutAvo".into(),
                size_px: size,
                axes,
                hinting: Hinting::None,
                output_bits: 1,
                ..Config::default()
            },
        };
        let source = reference(&data, &request)?;
        request.settings.hinting = Hinting::Auto;
        let upstream = reference(&data, &request)?;
        request.extensions = "font-hints-01".into();
        let font_hints = candidate::render(&data, &request)?;
        request.extensions = "mono-width-01".into();
        let mono = candidate::render(&data, &request)?;
        cases.push(json!({
            "family": family, "size_px": size, "axes": request.settings.axes,
            "source": source, "upstream": upstream, "font_hints_first": font_hints,
            "upstream_mono": mono,
        }));
    }
    let destination = Path::new(&destination);
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(destination, serde_json::to_vec(&json!({"cases": cases}))?)?;
    Ok(())
}
