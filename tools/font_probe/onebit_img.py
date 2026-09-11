import json, freetype as ft
from PIL import Image, ImageDraw, ImageFont
R="../.."
by={(r['ch'],r['px']):r for r in json.load(open('out/rasters1.json'))}
face=ft.Face('out/Plex400.ttf')
def ft_glyph(ch,px):
    face.set_pixel_sizes(0,int(px))
    face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_MONOCHROME)
    g=face.glyph; bm=g.bitmap; s=set()
    for y in range(bm.rows):
        for x in range(bm.width):
            if (bm.buffer[y*bm.pitch+(x>>3)]>>(7-(x&7)))&1: s.add((g.bitmap_left+x,g.bitmap_top-y))
    return s, g.advance.x>>6
def arm_glyph(ch,px,sec,ras):
    r=by.get((ch,px));
    if not r: return set()
    s=r[sec]; w=s['w']; o=set()
    for y in range(s['h']):
        for x in range(w):
            if s[ras][y*w+x]: o.add((s['l']+x,s['t']-y))
    return o
TEXT="Meditamer 12:34"
SIZES=[(12.0,8),(16.0,7),(18.0,6),(24.0,5)]
ARMS=[('u','zeno',"today:  unhinted AA + threshold 128"),
      ('h','zeno',"skrifa Target::Mono + zeno + threshold"),
      (None,None,"FreeType FT_RENDER_MODE_MONO  (reference)")]
def compose(px,sec,ras):
    pen=0; pts=set()
    for ch in TEXT:
        if ch==' ':
            _,adv=ft_glyph('n',px); pen+=adv; continue
        fs,adv=ft_glyph(ch,px)
        g = fs if sec is None else arm_glyph(ch,px,sec,ras)
        for (x,y) in g: pts.add((pen+x,y))
        pen+=adv
    return pts,pen
try:
    fnt=ImageFont.truetype(f"{R}/assets/fonts/IBMPlexSans-Variable.ttf",15)
    fsm=ImageFont.truetype(f"{R}/assets/fonts/IBMPlexSans-Variable.ttf",12)
except Exception: fnt=fsm=ImageFont.load_default()
blocks=[]
for px,S in SIZES:
    ref,_=compose(px,None,None)
    rows=[]
    for sec,ras,label in ARMS:
        pts,width=compose(px,sec,ras)
        rows.append((label,pts,ref,width,S))
    blocks.append((px,rows))
W=1360; H=70+sum(28+len(r)*(0) for _,r in blocks)
# measure
hh=70
for px,rows in blocks:
    hh+=34
    for label,pts,ref,width,S in rows:
        ys=[y for _,y in pts|ref]; hh+= (max(ys)-min(ys)+1)*S + 26
    hh+=16
img=Image.new('RGB',(W,hh),'white'); d=ImageDraw.Draw(img)
d.text((16,14),"1-bit rendering — IBM Plex Sans, black/white only (the Waveshare panel's native mode)",font=fnt,fill='black')
d.text((16,36),"red outline = pixel differs from FreeType's mono rasterizer. Same advances used in all three rows, so only glyph rendering varies.",font=fsm,fill=(90,90,90))
y=74
for px,rows in blocks:
    d.text((16,y),f"{int(px)} px",font=fnt,fill=(20,20,20)); y+=26
    for label,pts,ref,width,S in rows:
        ys=[yy for _,yy in pts|ref]; ymax,ymin=max(ys),min(ys)
        d.text((30,y),label,font=fsm,fill=(70,70,70)); y+=16
        x0=40
        for (px_,py_) in pts:
            X=x0+px_*S; Y=y+(ymax-py_)*S
            d.rectangle([X,Y,X+S-1,Y+S-1],fill=(20,20,20))
        if ref is not pts:
            for (px_,py_) in (pts^ref):
                X=x0+px_*S; Y=y+(ymax-py_)*S
                d.rectangle([X,Y,X+S-1,Y+S-1],outline=(225,45,45))
        y+=(ymax-ymin+1)*S+10
    y+=16
img=img.crop((0,0,W,min(hh,y+10)))
img.save('out/onebit_comparison.png'); print("wrote",img.size)
