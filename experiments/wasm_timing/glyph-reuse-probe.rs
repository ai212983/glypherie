use font_generator::{
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    surface::{HAlign, PreparedFont, TextRenderRequest, WrapMode},
    Config,
};
use sha2::{Digest, Sha256};
use std::{env, fs, path::Path, time::Instant};

fn main() {
    let folder = env::args().nth(1).unwrap();
    for family in ["Roboto", "SourceSans3"] {
        let font =
            PreparedFont::new(fs::read(Path::new(&folder).join(format!("{family}.ttf"))).unwrap());
        for case in [
            "cold",
            "repeat",
            "narrow",
            "spacing",
            "append",
            "delete",
            "no-kerning",
            "return",
            "weight-410",
            "weight-420",
            "return",
            "size-18",
            "return",
            "color",
        ] {
            let mut request = TextRenderRequest {
                config: Config {
                    axes: [("wght".into(), 400.)].into(),
                    ..Config::default()
                },
                text: "Pack my box with five dozen liquor jugs.".into(),
                width: if case == "narrow" { 160 } else { 600 },
                height: 160,
                wrap: WrapMode::Word,
                align: HAlign::Left,
                foreground: [0, 0, 0, 255],
                background: [255; 4],
                palette: None,
            };
            if case == "append" {
                request.text.push_str(" é");
            }
            if case == "delete" {
                request.text = "Pack my box".into();
            }
            if case == "no-kerning" {
                request.config.kerning = false;
            }
            if case == "weight-410" {
                request.config.axes.insert("wght".into(), 410.);
            }
            if case == "weight-420" {
                request.config.axes.insert("wght".into(), 420.);
            }
            if case == "size-18" {
                request.config.size_px = 18.;
            }
            if case == "color" {
                request.foreground = [100, 50, 0, 255];
            }
            let pipeline = RenderPipeline {
                fitting: StemFittingStrategy::FontHintsAuto,
                rasterization: Rasterization::FreeTypeMonoTerminals,
                diagonal_fitting: true,
            };
            eprintln!(
                "REUSE_REQUEST {}",
                serde_json::json!({"family":family,"case":case})
            );
            let start = Instant::now();
            let result = font
                .render_text_with_pipeline_and_spacing(
                    &request,
                    pipeline,
                    if case == "spacing" { 1. } else { 0. },
                )
                .unwrap();
            println!(
                "{}",
                serde_json::json!({"family":family,"case":case,
                "ms": start.elapsed().as_secs_f64()*1000.,"sha":format!("{:x}",Sha256::digest(&result.pixels))})
            );
        }
    }
}
