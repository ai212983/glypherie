"""Visual perimetric complexity, per Watson (2012).

C = (P_in + P_out)^2 / (4*pi*A), normalised so a unit disk = 1.
Visual variant: blur by a Gaussian of sigma = 2.33 arcmin of visual angle,
binarise at 0.5, then compute C on the resulting binary image.

Perimeter uses Watson's PerimeterLength (count of exposed pixel faces). He
notes it overestimates -- 62% for a circle vs 9% for his PolygonalLength --
but the bias is common to every arm, so relative comparison holds.
Blur is Pillow's GaussianBlur (3-pass box approximation, radius = sigma).
"""
import json, math
from functools import lru_cache
import freetype as ft
from PIL import Image, ImageFilter, ImageChops

face=ft.Face('out/Plex400.ttf')
MM_IN=25.4; DIST_MM=800.0; SIGMA_ARCMIN=2.33
PANELS={"Inkplate":(600,600,3.8), "Waveshare":(300,400,4.2)}
def panel_sigma(name):
    w,h,d=PANELS[name]
    pitch=MM_IN/(math.hypot(w,h)/d)
    apx=math.degrees(math.atan2(pitch,DIST_MM))*60.0
    return SIGMA_ARCMIN/apx, apx

def to_img(g):
    H=len(g); W=len(g[0])
    im=Image.new('L',(W,H)); im.putdata([255 if v else 0 for r in g for v in r]); return im

def blur_binarise(im, sigma_px, M=4):
    if M!=1: im=im.resize((im.width*M, im.height*M), Image.NEAREST)
    s=sigma_px*M; pad=int(math.ceil(3*s))+2
    c=Image.new('L',(im.width+2*pad, im.height+2*pad),0); c.paste(im,(pad,pad))
    c=c.filter(ImageFilter.GaussianBlur(radius=s))
    return c.point(lambda v: 255 if v>=128 else 0)

def complexity(im):
    """im: binary L image, ink=255. Exposed-face perimeter, ink-pixel area."""
    A=im.histogram()[255]
    if A==0: return None
    P=0
    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
        sh=ImageChops.offset(im,dx,dy)
        # border wraps; blank the wrapped edge so outside counts as background
        if dx: sh.paste(0,(0,0,1,sh.height) if dx>0 else (sh.width-1,0,sh.width,sh.height))
        if dy: sh.paste(0,(0,0,sh.width,1) if dy>0 else (0,sh.height-1,sh.width,sh.height))
        P+=ImageChops.darker(im, ImageChops.invert(sh)).histogram()[255]
    return (P*P)/(4*math.pi*A)

def visual_C(g,sigma): return complexity(blur_binarise(to_img(g),sigma))

@lru_cache(maxsize=None)
def ideal(ch,px,sigma,S=8):
    face.set_pixel_sizes(0,int(px*S))
    face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_NO_HINTING)
    bm=face.glyph.bitmap
    g=[[1 if bm.buffer[y*bm.pitch+x]>=128 else 0 for x in range(bm.width)] for y in range(bm.rows)]
    return complexity(blur_binarise(to_img(g), sigma*S, M=1))

def ft_mono(ch,px):
    face.set_pixel_sizes(0,int(px))
    face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_MONOCHROME)
    g=face.glyph; bm=g.bitmap
    return [[(bm.buffer[y*bm.pitch+(x>>3)]>>(7-(x&7)))&1 for x in range(bm.width)] for y in range(bm.rows)]

recs=json.load(open('out/joins.json'))
GL="aegsbmnpRM8"; ARMS=['zeno128','zeno96','tsk_aliased']
for panel in ("Inkplate","Waveshare"):
    sig,apx=panel_sigma(panel)
    print(f"\n===== {panel}: {apx:.3f} arcmin/px at 80 cm  ->  visual blur sigma = {sig:.2f} px =====")
    for px in (16.0,24.0,64.0):
        rs={r['ch']:r for r in recs if r['px']==px and r['ch'] in GL}
        if not rs: continue
        print(f"\n  {int(px)}px em      ideal" + "".join(f"{a:>16}" for a in ARMS) + f"{'FreeType':>14}")
        tot={a:0.0 for a in ARMS}; tot['ft']=0.0; n=0
        for ch in GL:
            if ch not in rs: continue
            ic=ideal(ch,px,round(sig,4))
            if ic is None: continue
            n+=1; row=f"    {ch!r:<8}{ic:>8.2f}"
            for a in ARMS:
                r=rs[ch]; w=r['w']
                g=[[r[a][y*w+x] for x in range(w)] for y in range(r['h'])]
                c=visual_C(g,sig)
                if c is None: row+=f"{'--':>16}"; continue
                tot[a]+=abs(c-ic); row+=f"{c:>9.2f}({c-ic:+.2f})"
            c=visual_C(ft_mono(ch,px),sig)
            if c is None: row+=f"{'--':>14}"
            else: tot['ft']+=abs(c-ic); row+=f"{c:>7.2f}({c-ic:+.2f})"
            print(row)
        if n: print(f"    {'MEAN |dev|':<8}{'':>8}" + "".join(f"{tot[a]/n:>16.3f}" for a in ARMS) + f"{tot['ft']/n:>14.3f}")
