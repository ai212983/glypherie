import json, freetype as ft
from PIL import Image, ImageDraw, ImageFont
R="../.."
recs={ (r['ch'],r['px']):r for r in json.load(open('out/rasters.json')) }
face=ft.Face('out/Plex400.ttf')
def ftr(ch,px):
    face.set_pixel_sizes(0,int(px)); face.load_char(ch, ft.FT_LOAD_RENDER)
    g=face.glyph; bm=g.bitmap
    return [[bm.buffer[y*bm.pitch+x] for x in range(bm.width)] for y in range(bm.rows)]
GL="aegsMR8"; PX=18.0; S=13
def grid(r,k,w,h): return [[r[k][y*w+x] for x in range(w)] for y in range(h)]
data={}
for c in GL:
    r=recs[(c,PX)]; w,h=r['w'],r['h']
    fb=ftr(c,PX)
    data[c]={'w':w,'h':h,'ref':[[fb[y][x] if y<len(fb) and x<len(fb[0]) else 0 for x in range(w)] for y in range(h)],
             'zeno':grid(r,'zeno',w,h),'abgr':grid(r,'abgr',w,h),'tinyskia':grid(r,'tinyskia',w,h)}
cols=[('FreeType (ref)','ref'),('zeno','zeno'),('ab_glyph','abgr'),('tiny-skia','tinyskia'),
      ('Δ zeno','dzeno'),('Δ ab_glyph','dabgr'),('Δ tiny-skia','dtinyskia')]
cw=max(d['w'] for d in data.values())*S+18
try:
    fnt=ImageFont.truetype(f"{R}/assets/fonts/IBMPlexSans-Variable.ttf",15)
    fsm=ImageFont.truetype(f"{R}/assets/fonts/IBMPlexSans-Variable.ttf",12)
except Exception: fnt=fsm=ImageFont.load_default()
rowh=[data[c]['h']*S+14 for c in GL]
top=92; q_h=data['a']['h']*S+90
H=top+sum(rowh)+q_h+420; W=64+len(cols)*cw
img=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(img)
d.text((16,14),"IBM Plex Sans 18px — skrifa-hinted outlines, three rasterizers vs FreeType",font=fnt,fill='black')
d.text((16,36),"cols 1-4: 8-bit coverage.   cols 5-7: |difference| from FreeType, deeper red = larger.   Hinted bboxes matched FreeType exactly on every glyph.",font=fsm,fill=(90,90,90))
for i,(l,_) in enumerate(cols): d.text((64+i*cw+6,66),l,font=fsm,fill='black')
y0=top
for gi,c in enumerate(GL):
    cell=data[c]; w,h=cell['w'],cell['h']
    d.text((26,y0+h*S//2-9),c,font=fnt,fill='black')
    for i,(l,k) in enumerate(cols):
        x0=64+i*cw+6
        for y in range(h):
            for x in range(w):
                if k.startswith('d'):
                    v=abs(cell[k[1:]][y][x]-cell['ref'][y][x])
                    col=(255,255-min(255,v*4),255-min(255,v*4)) if v else (248,248,248)
                else:
                    g=255-cell[k][y][x]; col=(g,g,g)
                d.rectangle([x0+x*S,y0+y*S,x0+x*S+S-1,y0+y*S+S-1],fill=col)
        d.rectangle([x0-1,y0-1,x0+w*S,y0+h*S],outline=(214,214,214))
    y0+=rowh[gi]
# 3-bit panel strip -- stacked rows
y0+=20
d.text((16,y0),"What the 3-bit panel actually shows -- coverage quantized to 8 gray levels",font=fnt,fill='black')
y0+=24
d.text((16,y0),"red outline = pixel landed on a different gray level than FreeType",font=fsm,fill=(90,90,90))
y0+=24
Q=9
for lbl,k in [('FreeType (ref)','ref'),('zeno','zeno'),('ab_glyph','abgr'),('tiny-skia','tinyskia')]:
    d.text((16,y0+6),lbl,font=fsm,fill='black')
    px_=150
    rowmax=0
    for c in GL:
        cell=data[c]; w,h=cell['w'],cell['h']; rowmax=max(rowmax,h)
        for y in range(h):
            for x in range(w):
                q=cell[k][y][x]>>5; g=255-int(q*255/7)
                d.rectangle([px_+x*Q,y0+y*Q,px_+x*Q+Q-1,y0+y*Q+Q-1],fill=(g,g,g))
                if k!='ref' and q!=(cell['ref'][y][x]>>5):
                    d.rectangle([px_+x*Q,y0+y*Q,px_+x*Q+Q-1,y0+y*Q+Q-1],outline=(225,45,45))
        px_+=w*Q+7
    y0+=rowmax*Q+16
img=img.crop((0,0,W,y0+34))
img.save('out/rasterizer_comparison.png')
print("wrote", img.size)
