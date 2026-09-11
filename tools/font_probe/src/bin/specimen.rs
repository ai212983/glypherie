//! Panel-sized specimen sheets through the real pipeline:
//! skrifa (hinting, variable axes) + harfrust (GPOS kerning) + zeno (raster).
//!
//! One sheet per (panel, face, bit depth), showing every role size for that
//! face. Writes binary PGM; the Python side upscales and labels for review.

use harfrust::{FontRef as HrFont, ShapeOptions, ShaperData, ShaperInstance, UnicodeBuffer};
use skrifa::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, OutlinePen, SmoothMode, Target},
    FontRef, GlyphId, MetadataProvider,
};
use zeno::{Command, Format, Mask as ZMask, Point};

#[derive(Clone, Copy)]
enum C { M(f32,f32), L(f32,f32), Q(f32,f32,f32,f32), U(f32,f32,f32,f32,f32,f32), Z }
#[derive(Default)]
struct Rec { c: Vec<C> }
impl OutlinePen for Rec {
    fn move_to(&mut self, x: f32, y: f32) { self.c.push(C::M(x, -y)) }
    fn line_to(&mut self, x: f32, y: f32) { self.c.push(C::L(x, -y)) }
    fn quad_to(&mut self, a: f32, b: f32, x: f32, y: f32) { self.c.push(C::Q(a, -b, x, -y)) }
    fn curve_to(&mut self, a: f32, b: f32, d: f32, e: f32, x: f32, y: f32) { self.c.push(C::U(a,-b,d,-e,x,-y)) }
    fn close(&mut self) { self.c.push(C::Z) }
}

fn raster(cmds: &[C]) -> (Vec<u8>, i32, i32, u32, u32) {
    let (mut x0, mut y0, mut x1, mut y1) = (f32::MAX, f32::MAX, f32::MIN, f32::MIN);
    let mut acc = |x: f32, y: f32| { x0 = x0.min(x); y0 = y0.min(y); x1 = x1.max(x); y1 = y1.max(y); };
    for c in cmds { match *c {
        C::M(x,y) | C::L(x,y) => acc(x,y),
        C::Q(a,b,x,y) => { acc(a,b); acc(x,y) }
        C::U(a,b,d,e,x,y) => { acc(a,b); acc(d,e); acc(x,y) }
        C::Z => {} } }
    if x0 > x1 { return (vec![], 0, 0, 0, 0); }
    let (ox, oy) = (x0.floor(), y0.floor());
    let w = ((x1.ceil() - ox) as u32).max(1);
    let h = ((y1.ceil() - oy) as u32).max(1);
    let z: Vec<Command> = cmds.iter().map(|k| match *k {
        C::M(x,y) => Command::MoveTo(Point::new(x-ox, y-oy)),
        C::L(x,y) => Command::LineTo(Point::new(x-ox, y-oy)),
        C::Q(a,b,x,y) => Command::QuadTo(Point::new(a-ox,b-oy), Point::new(x-ox,y-oy)),
        C::U(a,b,d,e,x,y) => Command::CurveTo(Point::new(a-ox,b-oy), Point::new(d-ox,e-oy), Point::new(x-ox,y-oy)),
        C::Z => Command::Close,
    }).collect();
    let mut buf = vec![0u8; (w*h) as usize];
    ZMask::new(z.as_slice()).format(Format::Alpha).size(w, h).render_into(&mut buf, None);
    (buf, ox as i32, oy as i32, w, h)
}

struct Canvas { w: u32, h: u32, px: Vec<u8> }
impl Canvas {
    fn new(w: u32, h: u32) -> Self { Canvas { w, h, px: vec![0; (w*h) as usize] } }
    fn put(&mut self, x: i32, y: i32, v: u8) {
        if x >= 0 && y >= 0 && (x as u32) < self.w && (y as u32) < self.h {
            let i = (y as u32 * self.w + x as u32) as usize;
            if v > self.px[i] { self.px[i] = v; }
        }
    }
    fn fill_rect(&mut self, x0: u32, y0: u32, x1: u32, y1: u32, ink: u8) {
        for y in y0..y1.min(self.h) {
            for x in x0..x1.min(self.w) {
                self.px[(y * self.w + x) as usize] = ink;
            }
        }
    }

    /// 16-byte header: magic, version, format, width, height, reserved.
    fn header(&self, format: u8) -> Vec<u8> {
        let mut h = Vec::with_capacity(16);
        h.extend_from_slice(b"MDFR");
        h.push(1);            // version
        h.push(format);       // 0 = bw1 (LSB-first), 1 = gray4
        h.extend_from_slice(&(self.w as u16).to_le_bytes());
        h.extend_from_slice(&(self.h as u16).to_le_bytes());
        h.extend_from_slice(&[0u8; 6]);
        h
    }

    /// Inkplate binary framebuffer. Bit order is **LSB-first** within the
    /// byte -- `value |= 1 << (x % 8)` -- matching
    /// `targets/meditamer-inkplate/src/panel_waveform_fixture.rs`'s
    /// `fill_binary_reference_pattern`. This is the opposite of the
    /// MSB-first packing the Waveshare frames use; do not share the code.
    fn write_inkplate_bw(&self, path: &str) {
        let stride = self.w as usize / 8;
        let mut out = self.header(0);
        let mut fb = vec![0u8; stride * self.h as usize];
        for y in 0..self.h as usize {
            for x in 0..self.w as usize {
                if self.px[y * self.w as usize + x] >= 128 {
                    fb[y * stride + (x >> 3)] |= 1 << (x % 8);
                }
            }
        }
        out.extend(fb);
        std::fs::write(path, out).unwrap();
    }

    /// Inkplate Gray4: two pixels per byte, **high nibble is the even (left)
    /// x**, row-major, 300 bytes per row. The panel's eight physical levels
    /// occupy the *even* values of the 4-bit field (`level * 2`), per the
    /// fixture's `gray4_at`, so a 3-bit value q is stored as `q * 2`.
    /// Polarity is confirmed on hardware: a **higher** Gray4 value is
    /// **lighter**, so the white ground stores as level 7 (nibble 14) and
    /// full black text as 0. Undocumented in the datasheet; established by
    /// showing both variants on the panel.
    fn write_inkplate_gray4(&self, path: &str) {
        let stride = self.w as usize / 2;
        let mut out = self.header(1);
        let mut fb = vec![0u8; stride * self.h as usize];
        let level = |v: u8| -> u8 {
            let ink = ((v as u16 * 7) + 127) / 255;    // ink 0..255 -> 0..7
            (7 - ink as u8) * 2                         // lighter = higher; evens
        };
        for y in 0..self.h as usize {
            for x in (0..self.w as usize).step_by(2) {
                let hi = level(self.px[y * self.w as usize + x]);
                let lo = level(self.px[y * self.w as usize + x + 1]);
                fb[y * stride + x / 2] = (hi << 4) | lo;
            }
        }
        out.extend(fb);
        std::fs::write(path, out).unwrap();
    }

    /// Packed 1bpp, row-major, MSB first -- what the Waveshare probe embeds.
    fn write_bin(&self, path: &str) {
        let stride = (self.w as usize + 7) / 8;
        let mut out = vec![0u8; stride * self.h as usize];
        for y in 0..self.h as usize {
            for x in 0..self.w as usize {
                if self.px[y * self.w as usize + x] >= 128 {
                    out[y * stride + (x >> 3)] |= 0x80 >> (x & 7);
                }
            }
        }
        std::fs::write(path, out).unwrap();
    }

    fn write_pgm(&self, path: &str) {
        let mut out = format!("P5\n{} {}\n255\n", self.w, self.h).into_bytes();
        out.extend(self.px.iter().map(|&v| 255 - v));
        std::fs::write(path, out).unwrap();
    }
}

fn draw_line(canvas: &mut Canvas, data: &[u8], axes: &[(&str, f32)],
             text: &str, px: f32, baseline_y: i32, bits: u32) {
    draw_line_at(canvas, data, axes, text, px, baseline_y, 8, bits)
}

fn alloc_num(n: u32) -> String { n.to_string() }

fn draw_line_at(canvas: &mut Canvas, data: &[u8], axes: &[(&str, f32)],
                text: &str, px: f32, baseline_y: i32, x_start: i32, bits: u32) {
    let skr = FontRef::new(data).unwrap();
    let hr = HrFont::from_index(data, 0).unwrap();
    let loc = skr.axes().location(axes.iter().map(|(t, v)| (*t, *v)));
    let outlines = skr.outline_glyphs();
    let target = if bits == 1 { Target::Mono } else {
        Target::Smooth { mode: SmoothMode::Normal, symmetric_rendering: true, preserve_linear_metrics: false }
    };
    let inst = HintingInstance::new(&outlines, Size::new(px), &loc,
        HintingOptions { engine: Engine::AutoFallback, target }).unwrap();
    let metrics = skr.glyph_metrics(Size::new(px), &loc);

    let hinst = ShaperInstance::from_variations(&hr, axes.iter().map(|(t, v)| (*t, *v)));
    let sdata = ShaperData::new(&hr);
    let shaper = sdata.shaper(&hr).instance(Some(&hinst)).build();
    let upem = shaper.units_per_em() as f32;
    let adv = |s: &str| -> f32 {
        let mut b = UnicodeBuffer::new();
        b.push_str(s); b.guess_segment_properties();
        shaper.shape(b, ShapeOptions::new()).glyph_positions().iter()
            .map(|p| p.x_advance as f32).sum()
    };

    // Small sizes need a lower coverage threshold or stem/arch joins break:
    // measured 8 topology errors at >=128 and 0 at >=96, at 16px em.
    let thresh: u8 = if px <= 20.0 { 96 } else { 128 };

    let chars: Vec<char> = text.chars().collect();
    let mut pen = x_start as f32;
    for (i, &ch) in chars.iter().enumerate() {
        let Some(gid) = skr.charmap().map(ch) else { continue };
        if let Some(g) = outlines.get(gid) {
            let mut rec = Rec::default();
            if g.draw(DrawSettings::hinted(&inst, false), &mut rec).is_ok() && !rec.c.is_empty() {
                let (cov, ox, oy, w, h) = raster(&rec.c);
                let px0 = pen.round() as i32;
                for y in 0..h { for x in 0..w {
                    let v = cov[(y*w + x) as usize];
                    // 3-bit: quantise coverage to the panel's 8 levels. The
                    // widening cast matters -- (v >> 5) * 255 overflows u8.
                    let out = if bits == 1 { if v >= thresh { 255 } else { 0 } }
                              else { ((v >> 5) as u16 * 255 / 7) as u8 };
                    if out > 0 { canvas.put(px0 + ox + x as i32, baseline_y + oy + y as i32, out); }
                }}
            }
        }
        let mut a = metrics.advance_width(GlyphId::new(gid.to_u32())).unwrap_or(0.0);
        if i + 1 < chars.len() {
            let pair: String = [ch, chars[i+1]].iter().collect();
            a += (adv(&pair) - adv(&ch.to_string()) - adv(&chars[i+1].to_string())) * px / upem;
        }
        pen += a;
    }
}

fn main() {
    let roboto = std::fs::read("fonts/Roboto.ttf").unwrap();
    let literata = std::fs::read("fonts/Literata.ttf").unwrap();
    let source = std::fs::read("fonts/SourceSans3.ttf").unwrap();

    // name, bytes, base axes, whether the face has an opsz axis to track size
    let faces: Vec<(&str, &str, &Vec<u8>, Vec<(&str, f32)>, bool)> = vec![
        ("Roboto",       "1  Roboto",        &roboto,   vec![("wght", 400.0), ("wdth", 100.0)], false),
        ("Literata",     "2  Literata",      &literata, vec![("wght", 400.0)],                  true),
        ("SourceSans3",  "3  Source Sans 3", &source,   vec![("wght", 400.0)],                  false),
    ];

    // per panel: (label, w, h, top margin, per-face role sizes, texts)
    // sizes are ambient-primary, ambient-secondary, heading, body, caption
    let inkplate_sizes = [
        ("Roboto",      [122.0, 70.0, 44.0, 34.0, 28.0]),
        ("Literata",    [126.0, 72.0, 46.0, 36.0, 30.0]),
        ("SourceSans3", [132.0, 76.0, 48.0, 38.0, 32.0]),
    ];
    let waveshare_sizes = [
        ("Roboto",      [64.0, 36.0, 24.0, 18.0, 16.0]),
        ("Literata",    [68.0, 38.0, 24.0, 20.0, 16.0]),
        ("SourceSans3", [70.0, 40.0, 26.0, 20.0, 16.0]),
    ];
    let ink_texts  = ["12:34", "23°C 45%", "Meditamer", "Ready to begin", "Il1 O0 5S 8B 69 rn"];
    let wav_texts  = ["12:34", "23°C 45%", "Medinote", "Sleep / Awake", "Il1 O0 5S 8B 69 rn"];

    std::fs::create_dir_all("out/specimen").unwrap();
    std::fs::create_dir_all("out/specimen/sd").unwrap();
    // Each Inkplate variant is its own numbered, self-labelling file: the
    // playlist index and the depth are drawn into the frame, so a slide is
    // identifiable on the glass without the viewer knowing the play order.
    // (An earlier attempt used drawn marker bars; they were the same ink as
    // the text, so an inverted frame rendered them white-on-white.)
    let panels: [(&str, u32, u32, &[(&str, [f32; 5])], &[&str; 5], &[u32]); 2] = [
        ("inkplate",  600, 600, &inkplate_sizes,  &ink_texts, &[1, 3]),
        ("waveshare", 400, 300, &waveshare_sizes, &wav_texts, &[1]),
    ];

    let mut slide = 0usize;
    for (panel, w, h, sizes, texts, variants) in panels {
        for (fname, pretty, data, base_axes, has_opsz) in &faces {
            let row = sizes.iter().find(|(n, _)| n == fname).unwrap();
            for &bits in variants {
                if panel == "inkplate" { slide += 1; }
                let mut c = Canvas::new(w, h);
                let label_px: f32 = if w >= 600 { 26.0 } else { 18.0 };
                let gap: i32 = if w >= 600 { 14 } else { 12 };
                let mut label_axes = base_axes.clone();
                if *has_opsz { label_axes.push(("opsz", label_px.clamp(7.0, 72.0))); }
                draw_line(&mut c, data, &label_axes, pretty, label_px, 4 + label_px as i32, bits);
                let mut y = 4 + label_px as i32 + 10 + row.1[0] as i32;
                for (i, &px) in row.1.iter().enumerate() {
                    let mut axes = base_axes.clone();
                    if *has_opsz { axes.push(("opsz", px.clamp(7.0, 72.0))); }
                    draw_line(&mut c, data, &axes, texts[i], px, y, bits);
                    let next = row.1.get(i + 1).copied().unwrap_or(px);
                    y += (next * 1.30) as i32 + gap;
                }

                if panel == "inkplate" {
                    // Footer in the empty strip below the specimen: which
                    // slide this is and how it is encoded.
                    let depth = if bits == 1 { "1-bit" } else { "3-bit" };
                    let footer = format!("{slide:02}   {depth}");
                    let f_px = 30.0f32;
                    let mut f_axes = base_axes.clone();
                    if *has_opsz { f_axes.push(("opsz", f_px)); }
                    draw_line(&mut c, data, &f_axes, &footer, f_px, h as i32 - 22, bits);

                    let out = format!("out/specimen/sd/{slide:02}.bin");
                    if bits == 1 { c.write_inkplate_bw(&out); }
                    else { c.write_inkplate_gray4(&out); }
                    println!("{out}  {pretty}  {depth}");
                }

                let path = format!("out/specimen/{panel}_{fname}_{bits}bit.pgm");
                c.write_pgm(&path);
                if panel == "waveshare" {
                    c.write_bin(&format!("out/specimen/dev_{panel}_{fname}.bin"));
                }
            }
        }
    }
    // A dedicated 3-bit verification frame: the panel's eight physical levels
    // as labelled vertical bands. Viewed through the gallery rather than the
    // product, because the product repaints over anything drawn behind its UI.
    {
        let (roboto_name, roboto_pretty, roboto_data, roboto_axes, _) = &faces[0];
        let _ = (roboto_name, roboto_pretty);
        let mut c = Canvas::new(600, 600);
        let band_w = 600 / 8;
        for level in 0..8u32 {
            // write_inkplate_gray4 maps ink -> level as (7 - ink_q) * 2, so
            // invert here to land exactly on the intended physical level.
            let ink = ((7 - level) * 255 / 7) as u8;
            c.fill_rect(level * band_w, 90, (level + 1) * band_w, 470, ink);
        }
        let mut axes = roboto_axes.clone();
        let _ = &mut axes;
        draw_line(&mut c, roboto_data, &axes, "3-bit levels 0-7", 40.0, 60, 3);
        // Label each band beneath its swatch, always in full black so it stays
        // readable over every level.
        for level in 0..8u32 {
            let label = alloc_num(level);
            draw_line_at(
                &mut c,
                roboto_data,
                &axes,
                &label,
                34.0,
                520,
                (level * band_w + band_w / 2 - 8) as i32,
                3,
            );
        }
        c.write_inkplate_gray4("out/specimen/sd/07.bin");
        c.write_pgm("out/specimen/inkplate_ramp_3bit.pgm");
        println!("out/specimen/sd/07.bin  3-bit level ramp 0-7");
    }
    println!("done");
}
