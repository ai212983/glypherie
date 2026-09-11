use harfrust::*;
fn main() {
    let data = std::fs::read("out/Plex400.ttf").unwrap();
    let fr = FontRef::from_index(&data, 0).unwrap();
    let sp = ShaperData::new(&fr);
    let shaper = sp.shaper(&fr).build();
    let upem = shaper.units_per_em() as f32;
    let px = 18.0f32;
    let ascii: Vec<char> = (0x20u8..0x7f).map(|c| c as char).collect();
    let adv = |s: &str| -> f32 {
        let mut b = UnicodeBuffer::new();
        b.push_str(s);
        b.guess_segment_properties();
        let g = shaper.shape(b, ShapeOptions::new());
        g.glyph_positions().iter().map(|p| p.x_advance as f32).sum::<f32>() * px / upem
    };
    let solo: Vec<f32> = ascii.iter().map(|c| adv(&c.to_string())).collect();
    let (mut n, mut half, mut one) = (0, 0, 0);
    for (i,a) in ascii.iter().enumerate() { for (j,b) in ascii.iter().enumerate() {
        let d = adv(&format!("{a}{b}")) - solo[i] - solo[j];
        if d.abs() > 1e-4 { n+=1; if d.abs()>=0.5 {half+=1} if d.abs()>=1.0 {one+=1} }
    }}
    println!("harfrust  : {n} non-zero pairs, {half} >= 0.5px, {one} >= 1.0px");
    println!("rustybuzz : 1232 / 309 / 92");
    println!("HarfBuzz C: 1232 / 309 / 92");
}
