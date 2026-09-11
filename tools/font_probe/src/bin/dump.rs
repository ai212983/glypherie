use skrifa::{prelude::*, outline::{DrawSettings, HintingInstance, HintingOptions, Target, SmoothMode, Engine, OutlinePen}, MetadataProvider, FontRef};
use tiny_skia::{PathBuilder, Mask, FillRule, Transform};

#[derive(Clone, Copy)]
enum Cmd { M(f32,f32), L(f32,f32), Q(f32,f32,f32,f32), C(f32,f32,f32,f32,f32,f32), Z }
#[derive(Default)]
struct Rec { cmds: Vec<Cmd> }
impl OutlinePen for Rec {
    fn move_to(&mut self,x:f32,y:f32){self.cmds.push(Cmd::M(x,-y))}
    fn line_to(&mut self,x:f32,y:f32){self.cmds.push(Cmd::L(x,-y))}
    fn quad_to(&mut self,a:f32,b:f32,x:f32,y:f32){self.cmds.push(Cmd::Q(a,-b,x,-y))}
    fn curve_to(&mut self,a:f32,b:f32,c:f32,d:f32,x:f32,y:f32){self.cmds.push(Cmd::C(a,-b,c,-d,x,-y))}
    fn close(&mut self){self.cmds.push(Cmd::Z)}
}
fn ts(c:&[Cmd],ox:f32,oy:f32,w:u32,h:u32)->Vec<u8>{
    let mut pb=PathBuilder::new();
    for k in c { match *k { Cmd::M(x,y)=>pb.move_to(x-ox,y-oy),Cmd::L(x,y)=>pb.line_to(x-ox,y-oy),
        Cmd::Q(a,b,x,y)=>pb.quad_to(a-ox,b-oy,x-ox,y-oy),
        Cmd::C(a,b,d,e,x,y)=>pb.cubic_to(a-ox,b-oy,d-ox,e-oy,x-ox,y-oy),Cmd::Z=>pb.close() } }
    let Some(p)=pb.finish() else { return vec![0;(w*h) as usize] };
    let mut m=Mask::new(w,h).unwrap(); m.fill_path(&p,FillRule::Winding,true,Transform::identity()); m.data().to_vec()
}
fn zn(c:&[Cmd],ox:f32,oy:f32,w:u32,h:u32)->Vec<u8>{
    use zeno::{Command,Mask as ZM,Format,Point};
    let z:Vec<Command>=c.iter().map(|k| match *k {
        Cmd::M(x,y)=>Command::MoveTo(Point::new(x-ox,y-oy)),Cmd::L(x,y)=>Command::LineTo(Point::new(x-ox,y-oy)),
        Cmd::Q(a,b,x,y)=>Command::QuadTo(Point::new(a-ox,b-oy),Point::new(x-ox,y-oy)),
        Cmd::C(a,b,d,e,x,y)=>Command::CurveTo(Point::new(a-ox,b-oy),Point::new(d-ox,e-oy),Point::new(x-ox,y-oy)),
        Cmd::Z=>Command::Close}).collect();
    let mut buf=vec![0u8;(w*h) as usize];
    ZM::new(z.as_slice()).format(Format::Alpha).size(w,h).render_into(&mut buf,None); buf
}
fn ab(c:&[Cmd],ox:f32,oy:f32,w:u32,h:u32)->Vec<u8>{
    use ab_glyph_rasterizer::{Rasterizer,point};
    let mut r=Rasterizer::new(w as usize,h as usize);
    let (mut cur,mut st)=((0.0,0.0),(0.0,0.0));
    for k in c { match *k {
        Cmd::M(x,y)=>{cur=(x-ox,y-oy);st=cur}
        Cmd::L(x,y)=>{let n=(x-ox,y-oy);r.draw_line(point(cur.0,cur.1),point(n.0,n.1));cur=n}
        Cmd::Q(a,b,x,y)=>{let n=(x-ox,y-oy);r.draw_quad(point(cur.0,cur.1),point(a-ox,b-oy),point(n.0,n.1));cur=n}
        Cmd::C(a,b,d,e,x,y)=>{let n=(x-ox,y-oy);r.draw_cubic(point(cur.0,cur.1),point(a-ox,b-oy),point(d-ox,e-oy),point(n.0,n.1));cur=n}
        Cmd::Z=>{r.draw_line(point(cur.0,cur.1),point(st.0,st.1));cur=st} } }
    let mut buf=vec![0u8;(w*h) as usize];
    r.for_each_pixel(|i,a| buf[i]=(a*255.0).round().clamp(0.0,255.0) as u8); buf
}
fn main(){
    let data=std::fs::read("out/Plex400.ttf").unwrap();
    let font=FontRef::new(&data).unwrap();
    let outlines=font.outline_glyphs();
    let mut out=String::from("[");
    let mut first=true;
    for px in [12.0f32,18.0,32.0] {
        let inst=HintingInstance::new(&outlines,Size::new(px),LocationRef::default(),
            HintingOptions{engine:Engine::AutoFallback,
                target:Target::Smooth{mode:SmoothMode::Normal,symmetric_rendering:true,preserve_linear_metrics:false}}).unwrap();
        for ch in "aegsMR8".chars(){
            let gid=font.charmap().map(ch).unwrap();
            let g=outlines.get(gid).unwrap();
            let mut rec=Rec::default();
            g.draw(DrawSettings::hinted(&inst,false),&mut rec).unwrap();
            let mut pb=PathBuilder::new();
            for k in &rec.cmds { match *k { Cmd::M(x,y)=>pb.move_to(x,y),Cmd::L(x,y)=>pb.line_to(x,y),
                Cmd::Q(a,b,x,y)=>pb.quad_to(a,b,x,y),Cmd::C(a,b,d,e,x,y)=>pb.cubic_to(a,b,d,e,x,y),Cmd::Z=>pb.close() } }
            let p=pb.finish().unwrap(); let b=p.bounds();
            let (ox,oy)=(b.left().floor(),b.top().floor());
            let w=((b.right().ceil()-ox) as u32).max(1); let h=((b.bottom().ceil()-oy) as u32).max(1);
            if !first { out.push(','); } first=false;
            out.push_str(&format!("{{\"ch\":\"{ch}\",\"px\":{px},\"left\":{},\"top\":{},\"w\":{w},\"h\":{h},\"zeno\":{:?},\"abgr\":{:?},\"tinyskia\":{:?}}}",
                ox as i32, -(oy as i32), zn(&rec.cmds,ox,oy,w,h), ab(&rec.cmds,ox,oy,w,h), ts(&rec.cmds,ox,oy,w,h)));
        }
    }
    out.push(']');
    std::fs::write("out/rasters.json",out).unwrap();
    println!("wrote out/rasters.json");
}
