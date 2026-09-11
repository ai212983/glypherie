use skrifa::{prelude::*, outline::{DrawSettings, HintingInstance, HintingOptions, Target, SmoothMode, Engine, OutlinePen}, MetadataProvider, FontRef};
use tiny_skia::{PathBuilder, Mask, FillRule, Transform};

#[derive(Clone, Copy, Debug)]
enum Cmd { M(f32,f32), L(f32,f32), Q(f32,f32,f32,f32), C(f32,f32,f32,f32,f32,f32), Z }

#[derive(Default)]
struct Rec { cmds: Vec<Cmd> }
impl OutlinePen for Rec {
    fn move_to(&mut self, x: f32, y: f32) { self.cmds.push(Cmd::M(x,-y)); }
    fn line_to(&mut self, x: f32, y: f32) { self.cmds.push(Cmd::L(x,-y)); }
    fn quad_to(&mut self, a: f32, b: f32, x: f32, y: f32) { self.cmds.push(Cmd::Q(a,-b,x,-y)); }
    fn curve_to(&mut self, a: f32, b: f32, c: f32, d: f32, x: f32, y: f32) { self.cmds.push(Cmd::C(a,-b,c,-d,x,-y)); }
    fn close(&mut self) { self.cmds.push(Cmd::Z); }
}

fn ts_render(cmds: &[Cmd], ox: f32, oy: f32, w: u32, h: u32) -> Vec<u8> {
    let mut pb = PathBuilder::new();
    for c in cmds { match *c {
        Cmd::M(x,y)=>pb.move_to(x-ox,y-oy), Cmd::L(x,y)=>pb.line_to(x-ox,y-oy),
        Cmd::Q(a,b,x,y)=>pb.quad_to(a-ox,b-oy,x-ox,y-oy),
        Cmd::C(a,b,c2,d,x,y)=>pb.cubic_to(a-ox,b-oy,c2-ox,d-oy,x-ox,y-oy), Cmd::Z=>pb.close() } }
    let Some(p) = pb.finish() else { return vec![0; (w*h) as usize] };
    let mut m = Mask::new(w,h).unwrap();
    m.fill_path(&p, FillRule::Winding, true, Transform::identity());
    m.data().to_vec()
}

fn zeno_render(cmds: &[Cmd], ox: f32, oy: f32, w: u32, h: u32) -> Vec<u8> {
    use zeno::{Command, Mask as ZMask, PathData, Format, Point};
    let z: Vec<Command> = cmds.iter().map(|c| match *c {
        Cmd::M(x,y)=>Command::MoveTo(Point::new(x-ox,y-oy)), Cmd::L(x,y)=>Command::LineTo(Point::new(x-ox,y-oy)),
        Cmd::Q(a,b,x,y)=>Command::QuadTo(Point::new(a-ox,b-oy),Point::new(x-ox,y-oy)),
        Cmd::C(a,b,c2,d,x,y)=>Command::CurveTo(Point::new(a-ox,b-oy),Point::new(c2-ox,d-oy),Point::new(x-ox,y-oy)),
        Cmd::Z=>Command::Close }).collect();
    let mut buf = vec![0u8; (w*h) as usize];
    ZMask::new(z.as_slice()).format(Format::Alpha).size(w,h).render_into(&mut buf, None);
    buf
}

fn ab_render(cmds: &[Cmd], ox: f32, oy: f32, w: u32, h: u32) -> Vec<u8> {
    use ab_glyph_rasterizer::{Rasterizer, point};
    let mut r = Rasterizer::new(w as usize, h as usize);
    let (mut cur, mut start) = ((0.0,0.0), (0.0,0.0));
    for c in cmds { match *c {
        Cmd::M(x,y)=>{ cur=(x-ox,y-oy); start=cur; }
        Cmd::L(x,y)=>{ let n=(x-ox,y-oy); r.draw_line(point(cur.0,cur.1), point(n.0,n.1)); cur=n; }
        Cmd::Q(a,b,x,y)=>{ let n=(x-ox,y-oy); r.draw_quad(point(cur.0,cur.1), point(a-ox,b-oy), point(n.0,n.1)); cur=n; }
        Cmd::C(a,b,c2,d,x,y)=>{ let n=(x-ox,y-oy); r.draw_cubic(point(cur.0,cur.1), point(a-ox,b-oy), point(c2-ox,d-oy), point(n.0,n.1)); cur=n; }
        Cmd::Z=>{ r.draw_line(point(cur.0,cur.1), point(start.0,start.1)); cur=start; } } }
    let mut buf = vec![0u8; (w*h) as usize];
    r.for_each_pixel(|i, a| buf[i] = (a*255.0).round().clamp(0.0,255.0) as u8);
    buf
}

fn main() {
    let data = std::fs::read("out/Plex400.ttf").unwrap();
    let font = FontRef::new(&data).unwrap();
    let outlines = font.outline_glyphs();
    let ascii: Vec<char> = (0x21u8..0x7f).map(|c| c as char).collect();

    for px in [12.0f32, 18.0, 32.0] {
        let inst = HintingInstance::new(&outlines, Size::new(px), LocationRef::default(),
            HintingOptions { engine: Engine::AutoFallback,
                             target: Target::Smooth { mode: SmoothMode::Normal, symmetric_rendering: true, preserve_linear_metrics: false } }).unwrap();
        let (mut n, mut sum_tz, mut sum_ta, mut max_tz, mut max_ta) = (0u64, 0u64, 0u64, 0u8, 0u8);
        let (mut q3_tz, mut q3_ta, mut q1_tz, mut q1_ta) = (0u64, 0u64, 0u64, 0u64);
        for &ch in &ascii {
            let Some(gid) = font.charmap().map(ch) else { continue };
            let Some(g) = outlines.get(gid) else { continue };
            let mut rec = Rec::default();
            if g.draw(DrawSettings::hinted(&inst, false), &mut rec).is_err() { continue }
            if rec.cmds.is_empty() { continue }
            // shared canvas from tiny-skia's bounds
            let mut pb = PathBuilder::new();
            for c in &rec.cmds { match *c {
                Cmd::M(x,y)=>pb.move_to(x,y), Cmd::L(x,y)=>pb.line_to(x,y),
                Cmd::Q(a,b,x,y)=>pb.quad_to(a,b,x,y), Cmd::C(a,b,c2,d,x,y)=>pb.cubic_to(a,b,c2,d,x,y), Cmd::Z=>pb.close() } }
            let Some(p) = pb.finish() else { continue };
            let b = p.bounds();
            let (ox, oy) = (b.left().floor(), b.top().floor());
            let w = ((b.right().ceil()-ox) as u32).max(1);
            let h = ((b.bottom().ceil()-oy) as u32).max(1);
            let (ts, zn, ab) = (ts_render(&rec.cmds,ox,oy,w,h), zeno_render(&rec.cmds,ox,oy,w,h), ab_render(&rec.cmds,ox,oy,w,h));
            for i in 0..ts.len() {
                n += 1;
                let dz = ts[i].abs_diff(zn[i]); let da = ts[i].abs_diff(ab[i]);
                sum_tz += dz as u64; sum_ta += da as u64;
                max_tz = max_tz.max(dz); max_ta = max_ta.max(da);
                if (ts[i]>>5) != (zn[i]>>5) { q3_tz += 1 }
                if (ts[i]>>5) != (ab[i]>>5) { q3_ta += 1 }
                if (ts[i]>=128) != (zn[i]>=128) { q1_tz += 1 }
                if (ts[i]>=128) != (ab[i]>=128) { q1_ta += 1 }
            }
        }
        println!("--- {px}px, hinted (Smooth/Normal), {n} pixels over printable ASCII ---");
        println!("  tiny-skia vs zeno  : mean |d| {:.3}/255, max {}, differ after 3-bit quant {:.3}%, after 1-bit {:.3}%",
                 sum_tz as f64/n as f64, max_tz, 100.0*q3_tz as f64/n as f64, 100.0*q1_tz as f64/n as f64);
        println!("  tiny-skia vs abgr  : mean |d| {:.3}/255, max {}, differ after 3-bit quant {:.3}%, after 1-bit {:.3}%",
                 sum_ta as f64/n as f64, max_ta, 100.0*q3_ta as f64/n as f64, 100.0*q1_ta as f64/n as f64);
    }
}
