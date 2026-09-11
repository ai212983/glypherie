//! Diagnostic for the 16px stem/arch join failure: four fill rules applied to
//! the *same* skrifa Target::Mono hinted outline.
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
fn path(c:&[C],ox:f32,oy:f32,s:f32)->Option<tiny_skia::Path>{
    let mut pb=PathBuilder::new();
    for k in c{match *k{
        C::M(x,y)=>pb.move_to((x-ox)*s,(y-oy)*s), C::L(x,y)=>pb.line_to((x-ox)*s,(y-oy)*s),
        C::Q(a,b,x,y)=>pb.quad_to((a-ox)*s,(b-oy)*s,(x-ox)*s,(y-oy)*s),
        C::U(a,b,d,e,x,y)=>pb.cubic_to((a-ox)*s,(b-oy)*s,(d-ox)*s,(e-oy)*s,(x-ox)*s,(y-oy)*s),
        C::Z=>pb.close()}}
    pb.finish()
}
fn zeno_cov(c:&[C],ox:f32,oy:f32,w:u32,h:u32,s:f32)->Vec<u8>{
    use zeno::{Command,Mask as Z,Format,Point};
    let z:Vec<Command>=c.iter().map(|k|match *k{
        C::M(x,y)=>Command::MoveTo(Point::new((x-ox)*s,(y-oy)*s)),
        C::L(x,y)=>Command::LineTo(Point::new((x-ox)*s,(y-oy)*s)),
        C::Q(a,b,x,y)=>Command::QuadTo(Point::new((a-ox)*s,(b-oy)*s),Point::new((x-ox)*s,(y-oy)*s)),
        C::U(a,b,d,e,x,y)=>Command::CurveTo(Point::new((a-ox)*s,(b-oy)*s),Point::new((d-ox)*s,(e-oy)*s),Point::new((x-ox)*s,(y-oy)*s)),
        C::Z=>Command::Close}).collect();
    let mut b=vec![0u8;(w*h) as usize];
    Z::new(z.as_slice()).format(Format::Alpha).size(w,h).render_into(&mut b,None); b
}
fn main(){
    let data=std::fs::read("out/Plex400.ttf").unwrap();
    let f=FontRef::new(&data).unwrap(); let og=f.outline_glyphs();
    let mut out=String::from("["); let mut first=true;
    for px in [16.0f32,24.0,64.0]{
        let inst=HintingInstance::new(&og,Size::new(px),LocationRef::default(),
            HintingOptions{engine:Engine::AutoFallback,target:Target::Mono}).unwrap();
        for ch in (0x21u8..0x7f).map(|c|c as char){
            let Some(gid)=f.charmap().map(ch) else{continue}; let Some(g)=og.get(gid) else{continue};
            let mut r=R::default(); if g.draw(DrawSettings::hinted(&inst,false),&mut r).is_err(){continue}
            if r.c.is_empty(){continue}
            let Some(p1)=path(&r.c,0.0,0.0,1.0) else{continue};
            let b=p1.bounds();
            let (ox,oy)=(b.left().floor(),b.top().floor());
            let w=((b.right().ceil()-ox) as u32).max(1); let h=((b.bottom().ceil()-oy) as u32).max(1);
            let cov=zeno_cov(&r.c,ox,oy,w,h,1.0);
            let a:Vec<u8>=cov.iter().map(|&v| (v>=128) as u8).collect();      // current
            let c96:Vec<u8>=cov.iter().map(|&v| (v>=96) as u8).collect();     // lower threshold
            // tiny-skia aliased == pixel-centre-inside, FreeType's mono rule
            let mut m=Mask::new(w,h).unwrap();
            if let Some(p)=path(&r.c,ox,oy,1.0){ m.fill_path(&p,FillRule::Winding,false,Transform::identity()); }
            let tsk:Vec<u8>=m.data().iter().map(|&v| (v>=128) as u8).collect();
            // 3x supersample, take centre subpixel
            let cov3=zeno_cov(&r.c,ox,oy,w*3,h*3,3.0);
            let mut ss=vec![0u8;(w*h) as usize];
            for y in 0..h{ for x in 0..w{
                ss[(y*w+x) as usize]=(cov3[(((y*3+1)*w*3)+(x*3+1)) as usize]>=128) as u8; }}
            if !first{out.push(',')} first=false;
            out.push_str(&format!("{{\"ch\":{:?},\"px\":{px},\"l\":{},\"t\":{},\"w\":{w},\"h\":{h},\
              \"zeno128\":{:?},\"zeno96\":{:?},\"tsk_aliased\":{:?},\"ss3_centre\":{:?}}}",
              ch.to_string(), ox as i32, -(oy as i32), a, c96, tsk, ss));
        }
    }
    out.push(']');
    std::fs::write("out/joins.json",out).unwrap();
    println!("wrote out/joins.json");
}
