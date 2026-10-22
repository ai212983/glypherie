use font_generator::{fitting_source, Config};
use serde_json::{json, Value};
use std::io::{self, BufRead};

fn capture(input: Value) -> Result<Value, Box<dyn std::error::Error>> {
    let data = std::fs::read(input["font"].as_str().ok_or("font")?)?;
    let config = Config {
        size_px: input["size"].as_f64().ok_or("size")? as f32,
        axes: serde_json::from_value(input["axes"].clone())?,
        ..Config::default()
    };
    let mut glyphs = Vec::new();
    for id in input["glyphs"].as_array().ok_or("glyphs")? {
        let id = id.as_u64().ok_or("glyph id")? as u32;
        let source = fitting_source::draw(&data, &config, id)?;
        glyphs.push(json!({"glyph_id":id,"oncurve":source.oncurve,"offcurve":source.offcurve}));
    }
    Ok(json!({"glyphs":glyphs}))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    for line in io::stdin().lock().lines() {
        println!("{}", capture(serde_json::from_str(&line?)?)?);
    }
    Ok(())
}
