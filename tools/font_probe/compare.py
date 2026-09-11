import json, freetype as ft
from PIL import Image, ImageDraw, ImageFont

R="../.."
recs=json.load(open('out/rasters.json'))
face=ft.Face('out/Plex400.ttf')

def ft_render(ch, px):
    face.set_pixel_sizes(0, int(px))
    face.load_char(ch, ft.FT_LOAD_RENDER)   # NORMAL target, default hinting
    g=face.glyph; bm=g.bitmap
    buf=[[bm.buffer[y*bm.pitch+x] for x in range(bm.width)] for y in range(bm.rows)]
    return buf, g.bitmap_left, g.bitmap_top, bm.width, bm.rows

RAS=['zeno','abgr','tinyskia']
stats={}
cells={}
for r in recs:
    ch,px,w,h=r['ch'],r['px'],r['w'],r['h']
    fb,fl,ftp,fw,fh=ft_render(ch,px)
    aligned = (fl==r['left'] and ftp==r['top'] and fw==w and fh==h)
    ref=[[fb[y][x] if y<fh and x<fw else 0 for x in range(w)] for y in range(h)]
    cells[(ch,px)]={'ref':ref,'w':w,'h':h,'aligned':aligned}
    for name in RAS:
        buf=r[name]; grid=[[buf[y*w+x] for x in range(w)] for y in range(h)]
        cells[(ch,px)][name]=grid
        s=stats.setdefault((px,name),[0,0,0,0,0])
        for y in range(h):
            for x in range(w):
                d=abs(grid[y][x]-ref[y][x]); s[0]+=1; s[1]+=d; s[2]=max(s[2],d)
                if (grid[y][x]>>5)!=(ref[y][x]>>5): s[3]+=1
                if (grid[y][x]>=128)!=(ref[y][x]>=128): s[4]+=1

print("FreeType (FT_LOAD_RENDER, hinted, NORMAL) as ground truth\n")
print(f"{'size':>6} {'rasterizer':<11} {'mean|d|':>8} {'max':>5} {'3-bit differ':>13} {'1-bit differ':>13}")
for px in (12.0,18.0,32.0):
    for name in RAS:
        n,sd,mx,q3,q1=stats[(px,name)]
        print(f"{int(px):>5}px {name:<11} {sd/n:>8.2f} {mx:>5} {100*q3/n:>12.2f}% {100*q1/n:>12.2f}%")
    print()
mis=[(c,p) for (c,p),v in cells.items() if not v['aligned']]
print("glyphs where skrifa's hinted bbox != FreeType's:", mis if mis else "none — all aligned")

# ---- image ----
GL="aegsMR8"; PX=18.0; S=13
cols=[('FreeType','ref'),('zeno','zeno'),('ab_glyph','abgr'),('tiny-skia','tinyskia'),
      ('Δ zeno','dzeno'),('Δ ab_glyph','dabgr'),('Δ tiny-skia','dtinyskia')]
cw=max(cells[(c,PX)]['w'] for c in GL)*S+16
ch_=max(cells[(c,PX)]['h'] for c in GL)*S+10
try: fnt=ImageFont.truetype(f"{R}/assets/fonts/IBMPlexSans-Variable.ttf", 15)
except: fnt=ImageFont.load_default()
try: fsm=ImageFont.truetype(f"{R}/assets/fonts/IBMPlexSans-Variable.ttf", 12)
except: fsm=fnt
W=60+len(cols)*cw; H=90+len(GL)*ch_+ch_+60
img=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(img)
d.text((16,14),"IBM Plex Sans 18px, skrifa-hinted outlines (Smooth/Normal) — FreeType vs three rasterizers",font=fnt,fill='black')
d.text((16,34),"columns 1-4: 8-bit coverage   columns 5-7: |difference| vs FreeType, red = larger",font=fsm,fill=(90,90,90))
for i,(lbl,_) in enumerate(cols):
    d.text((60+i*cw+6,62),lbl,font=fsm,fill='black')
for gi,c in enumerate(GL):
    cell=cells[(c,PX)]; w,h=cell['w'],cell['h']
    y0=84+gi*ch_
    d.text((22,y0+h*S//2-8),c,font=fnt,fill='black')
    for i,(lbl,key) in enumerate(cols):
        x0=60+i*cw+6
        for y in range(h):
            for x in range(w):
                if key.startswith('d'):
                    v=abs(cell[key[1:]][y][x]-cell['ref'][y][x])
                    col=(255,255-min(255,v*3),255-min(255,v*3)) if v else (247,247,247)
                else:
                    g=255-cell[key][y][x]; col=(g,g,g)
                d.rectangle([x0+x*S,y0+y*S,x0+x*S+S-1,y0+y*S+S-1],fill=col)
        d.rectangle([x0-1,y0-1,x0+w*S,y0+h*S],outline=(215,215,215))
img.save('out/rasterizer_comparison.png')
print("\nwrote out/rasterizer_comparison.png", img.size)
