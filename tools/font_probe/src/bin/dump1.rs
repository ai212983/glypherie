use skrifa::{prelude::*, outline::{DrawSettings, HintingInstance, HintingOptions, Target, Engine, OutlinePen}, MetadataProvider, FontRef};
use tiny_skia::{PathBuilder, Mask, FillRule, Transform};
#[derive(Clone,Copy)] enum C{M(f32,f32),L(f32,f32),Q(f32,f32,f32,f32),U(f32,f32,f32,f32,f32,f32),Z}
#[derive(Default)] struct R{c:Vec<C>}
impl OutlinePen for R{
    fn move_to(&mut self,x:f32,y:f32){self.c.push(C::M(x,-y))}
    fn line_to(&mut self,x:f32,y:f32){self.c.push(C::L(x,-y))}
    fn quad_to(&mut self,a:f32,b:f32,x:f32,y:f32){self.c.push(C::Q(a,-b,x,-y))}
    fn curve_to(&mut self,a:f32,b:f32,d:f32,e:f32,x:f32,y:f32){self.c.push(C::U(a,-b,d,-e,x,-y))}
    fn close(&mut self){self.c.push(C::Z)}
}
fn bounds(c:&[C])->Option<(f32,f32,u32,u32)>{
    let mut pb=PathBuilder::new();
    for k in c{match *k{C::M(x,y)=>pb.move_to(x,y),C::L(x,y)=>pb.line_to(x,y),C::Q(a,b,x,y)=>pb.quad_to(a,b,x,y),
        C::U(a,b,d,e,x,y)=>pb.cubic_to(a,b,d,e,x,y),C::Z=>pb.close()}}
    let p=pb.finish()?; let b=p.bounds();
    let (ox,oy)=(b.left().floor(),b.top().floor());
    Some((ox,oy,((b.right().ceil()-ox) as u32).max(1),((b.bottom().ceil()-oy) as u32).max(1)))
}
fn zeno(c:&[C],ox:f32,oy:f32,w:u32,h:u32)->Vec<u8>{
    use zeno::{Command,Mask as Z,Format,Point};
    let z:Vec<Command>=c.iter().map(|k|match *k{
        C::M(x,y)=>Command::MoveTo(Point::new(x-ox,y-oy)),C::L(x,y)=>Command::LineTo(Point::new(x-ox,y-oy)),
        C::Q(a,b,x,y)=>Command::QuadTo(Point::new(a-ox,b-oy),Point::new(x-ox,y-oy)),
        C::U(a,b,d,e,x,y)=>Command::CurveTo(Point::new(a-ox,b-oy),Point::new(d-ox,e-oy),Point::new(x-ox,y-oy)),
        C::Z=>Command::Close}).collect();
    let mut b=vec![0u8;(w*h) as usize];
    Z::new(z.as_slice()).format(Format::Alpha).size(w,h).render_into(&mut b,None); b
}
fn tsk(c:&[C],ox:f32,oy:f32,w:u32,h:u32)->Vec<u8>{
    let mut pb=PathBuilder::new();
    for k in c{match *k{C::M(x,y)=>pb.move_to(x-ox,y-oy),C::L(x,y)=>pb.line_to(x-ox,y-oy),
        C::Q(a,b,x,y)=>pb.quad_to(a-ox,b-oy,x-ox,y-oy),
        C::U(a,b,d,e,x,y)=>pb.cubic_to(a-ox,b-oy,d-ox,e-oy,x-ox,y-oy),C::Z=>pb.close()}}
    let Some(p)=pb.finish() else{return vec![0;(w*h) as usize]};
    let mut m=Mask::new(w,h).unwrap(); m.fill_path(&p,FillRule::Winding,true,Transform::identity()); m.data().to_vec()
}
fn abg(c:&[C],ox:f32,oy:f32,w:u32,h:u32)->Vec<u8>{
    use ab_glyph_rasterizer::{Rasterizer,point};
    let mut r=Rasterizer::new(w as usize,h as usize);
    let (mut cu,mut st)=((0.0,0.0),(0.0,0.0));
    for k in c{match *k{
        C::M(x,y)=>{cu=(x-ox,y-oy);st=cu}
        C::L(x,y)=>{let n=(x-ox,y-oy);r.draw_line(point(cu.0,cu.1),point(n.0,n.1));cu=n}
        C::Q(a,b,x,y)=>{let n=(x-ox,y-oy);r.draw_quad(point(cu.0,cu.1),point(a-ox,b-oy),point(n.0,n.1));cu=n}
        C::U(a,b,d,e,x,y)=>{let n=(x-ox,y-oy);r.draw_cubic(point(cu.0,cu.1),point(a-ox,b-oy),point(d-ox,e-oy),point(n.0,n.1));cu=n}
        C::Z=>{r.draw_line(point(cu.0,cu.1),point(st.0,st.1));cu=st}}}
    let mut b=vec![0u8;(w*h) as usize];
    r.for_each_pixel(|i,a| b[i]=(a*255.0).round().clamp(0.0,255.0) as u8); b
}
fn bits(v:&[u8])->Vec<u8>{v.iter().map(|&x| if x>=128 {1} else {0}).collect()}
fn main(){
    let data=std::fs::read("out/Plex400.ttf").unwrap();
    let f=FontRef::new(&data).unwrap(); let og=f.outline_glyphs();
    let chars:Vec<char>=(0x21u8..0x7f).map(|c|c as char).collect();
    let mut out=String::from("["); let mut first=true;
    for px in [12.0f32,16.0,18.0,24.0]{
        let mono=HintingInstance::new(&og,Size::new(px),LocationRef::default(),
            HintingOptions{engine:Engine::AutoFallback,target:Target::Mono}).unwrap();
        let gm=f.glyph_metrics(Size::new(px),LocationRef::default());
        for &ch in &chars{
            let Some(gid)=f.charmap().map(ch) else{continue}; let Some(g)=og.get(gid) else{continue};
            let mut hr=R::default(); if g.draw(DrawSettings::hinted(&mono,false),&mut hr).is_err(){continue}
            let mut ur=R::default(); if g.draw(DrawSettings::unhinted(Size::new(px),LocationRef::default()),&mut ur).is_err(){continue}
            if hr.c.is_empty(){continue}
            let Some((hox,hoy,hw,hh))=bounds(&hr.c) else{continue};
            let Some((uox,uoy,uw,uh))=bounds(&ur.c) else{continue};
            if !first{out.push(',')} first=false;
            out.push_str(&format!("{{\"ch\":{:?},\"px\":{px},\"adv\":{:.4},\
              \"h\":{{\"l\":{},\"t\":{},\"w\":{hw},\"h\":{hh},\"zeno\":{:?},\"tsk\":{:?},\"abg\":{:?}}},\
              \"u\":{{\"l\":{},\"t\":{},\"w\":{uw},\"h\":{uh},\"zeno\":{:?}}}}}",
              ch.to_string(), gm.advance_width(gid).unwrap_or(0.0),
              hox as i32, -(hoy as i32), bits(&zeno(&hr.c,hox,hoy,hw,hh)), bits(&tsk(&hr.c,hox,hoy,hw,hh)), bits(&abg(&hr.c,hox,hoy,hw,hh)),
              uox as i32, -(uoy as i32), bits(&zeno(&ur.c,uox,uoy,uw,uh))));
        }
    }
    out.push(']');
    std::fs::write("out/rasters1.json",out).unwrap();
    println!("wrote out/rasters1.json");
}
