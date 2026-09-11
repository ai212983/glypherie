import json
from collections import deque
import freetype as ft
from PIL import Image, ImageDraw, ImageFont
face=ft.Face('out/Plex400.ttf')
def ft_mono(ch,px):
    face.set_pixel_sizes(0,int(px))
    face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_MONOCHROME)
    g=face.glyph; bm=g.bitmap
    return [[(bm.buffer[y*bm.pitch+(x>>3)]>>(7-(x&7)))&1 for x in range(bm.width)] for y in range(bm.rows)]
def ours(px):
    o={}
    for r in json.load(open('out/rasters1.json')):
        if r['px']!=px: continue
        s=r['h']; w=s['w']
        o[r['ch']]=[[s['zeno'][y*w+x] for x in range(w)] for y in range(s['h'])]
    return o
def _cc(grid,val,conn8):
    H,W=len(grid),len(grid[0]); seen=[[0]*W for _ in range(H)]; comps=[]
    nb=[(-1,0),(1,0),(0,-1),(0,1)]+([(-1,-1),(-1,1),(1,-1),(1,1)] if conn8 else [])
    for y in range(H):
        for x in range(W):
            if grid[y][x]==val and not seen[y][x]:
                cur=[]; q=deque([(y,x)]); seen[y][x]=1
                while q:
                    cy,cx=q.popleft(); cur.append((cy,cx))
                    for dy,dx in nb:
                        ny,nx=cy+dy,cx+dx
                        if 0<=ny<H and 0<=nx<W and not seen[ny][nx] and grid[ny][nx]==val:
                            seen[ny][nx]=1; q.append((ny,nx))
                comps.append(cur)
    return comps
def topo(g):
    H,W=len(g),len(g[0])
    pad=[[0]*(W+2)]+[[0]+r+[0] for r in g]+[[0]*(W+2)]
    comps=_cc(pad,1,True)
    seen=[[0]*(W+2) for _ in range(H+2)]; q=deque([(0,0)]); seen[0][0]=1
    while q:
        cy,cx=q.popleft()
        for dy,dx in ((-1,0),(1,0),(0,-1),(0,1)):
            ny,nx=cy+dy,cx+dx
            if 0<=ny<H+2 and 0<=nx<W+2 and not seen[ny][nx] and pad[ny][nx]==0:
                seen[ny][nx]=1; q.append((ny,nx))
    inner=[[1 if (pad[y][x]==0 and not seen[y][x]) else 0 for x in range(W+2)] for y in range(H+2)]
    return len(comps), len(_cc(inner,1,False)), comps
SETS=[(16.0,"bhmnp9es"),(24.0,"9besab")]
S=18
try:
    fnt=ImageFont.truetype("../../assets/fonts/IBMPlexSans-Variable.ttf",15)
    fsm=ImageFont.truetype("../../assets/fonts/IBMPlexSans-Variable.ttf",12)
except Exception: fnt=fsm=ImageFont.load_default()
W=1300; img=Image.new('RGB',(W,2400),'white'); d=ImageDraw.Draw(img)
d.text((16,14),"FreeType vs ours (skrifa Target::Mono + zeno) — glyphs where stroke/counter topology differs",font=fnt,fill='black')
d.text((16,36),"blue = separate ink components (should be 1 for these). orange = enclosed counter. A glyph splitting into 2 pieces, or losing its counter, is the defect.",font=fsm,fill=(90,90,90))
y=66
COLS=[(255,60,60),(40,90,220),(20,160,90),(200,120,0)]
for px,glyphs in SETS:
    d.text((16,y),f"{int(px)} px",font=fnt,fill=(20,20,20)); y+=24
    o=ours(px)
    for label,src in [("FreeType",lambda c: ft_mono(c,px)),("ours",lambda c: o[c])]:
        d.text((20,y+6),label,font=fsm,fill=(70,70,70))
        x0=110
        for c in glyphs:
            g=src(c)
            if not g or not g[0]: continue
            nc,nh,comps=topo(g)
            H,Wd=len(g),len(g[0])
            for i,comp in enumerate(comps):
                col=COLS[i%len(COLS)] if nc>1 else (25,25,25)
                for (cy,cx) in comp:
                    if 1<=cy<=H and 1<=cx<=Wd:
                        d.rectangle([x0+(cx-1)*S,y+(cy-1)*S,x0+(cx-1)*S+S-1,y+(cy-1)*S+S-1],fill=col)
            bad = nc>1 or (c in "bpeas9" and nh<1)
            d.text((x0,y+H*S+2),f"{c}: {nc}c {nh}h"+("  BAD" if bad else ""),font=fsm,
                   fill=(200,30,30) if bad else (110,110,110))
            x0+=Wd*S+26
        y+=max(len(src(c)) for c in glyphs)*S+34
    y+=18
img=img.crop((0,0,W,y+10)); img.save('out/topology_comparison.png'); print("wrote",img.size)
