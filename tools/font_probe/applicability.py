"""Is Watson's visual perimetric complexity applicable at our sizes?
Watson's default visual blur is sigma = 2.33 arcmin of visual angle."""
import math
import freetype as ft
from PIL import Image, ImageFilter, ImageChops
from collections import deque
face=ft.Face('out/Plex400.ttf')
MM_IN=25.4; DIST=800.0; SIG=2.33
P={"Inkplate":(600,600,3.8),"Waveshare":(300,400,4.2)}
def geom(n):
    w,h,d=P[n]; pitch=MM_IN/(math.hypot(w,h)/d)
    return SIG/(math.degrees(math.atan2(pitch,DIST))*60.0), math.degrees(math.atan2(pitch,DIST))*60.0
print("Watson visual blur sigma = 2.33 arcmin. x-height = em/2 for IBM Plex Sans.\n")
print(f"{'panel':<11}{'em':>5}{'x-ht px':>9}{'sigma px':>10}{'sigma / x-height':>18}   applicable?")
for n in P:
    s,apx=geom(n)
    for em in (16,24,32,48,64,128):
        xh=em/2; r=s/xh
        verdict = "yes"          if r<=0.20 else \
                  "marginal"     if r<=0.35 else \
                  "NO - blur exceeds letter detail"
        print(f"{n:<11}{em:>5}{xh:>9.0f}{s:>10.2f}{r:>17.2f}   {verdict}")
    print()
print("For reference, book reading (x-height 0.24 deg = 14.4 arcmin) gives sigma/x-height = 0.16.\n")

def topo(im):
    W,H=im.size; d=list(im.getdata())
    g=[[1 if d[y*W+x] else 0 for x in range(W)] for y in range(H)]
    pad=[[0]*(W+2)]+[[0]+r+[0] for r in g]+[[0]*(W+2)]
    def cc(gr,val,c8):
        HH=len(gr); WW=len(gr[0]); seen=[[0]*WW for _ in range(HH)]; n=0
        nb=[(-1,0),(1,0),(0,-1),(0,1)]+([(-1,-1),(-1,1),(1,-1),(1,1)] if c8 else [])
        for y in range(HH):
            for x in range(WW):
                if gr[y][x]==val and not seen[y][x]:
                    n+=1; q=deque([(y,x)]); seen[y][x]=1
                    while q:
                        cy,cx=q.popleft()
                        for dy,dx in nb:
                            ny,nx=cy+dy,cx+dx
                            if 0<=ny<HH and 0<=nx<WW and not seen[ny][nx] and gr[ny][nx]==val:
                                seen[ny][nx]=1; q.append((ny,nx))
        return n
    comps=cc(pad,1,True)
    seen=[[0]*(W+2) for _ in range(H+2)]; q=deque([(0,0)]); seen[0][0]=1
    while q:
        cy,cx=q.popleft()
        for dy,dx in ((-1,0),(1,0),(0,-1),(0,1)):
            ny,nx=cy+dy,cx+dx
            if 0<=ny<H+2 and 0<=nx<W+2 and not seen[ny][nx] and pad[ny][nx]==0:
                seen[ny][nx]=1; q.append((ny,nx))
    inner=[[1 if (pad[y][x]==0 and not seen[y][x]) else 0 for x in range(W+2)] for y in range(H+2)]
    return comps, cc(inner,1,False)

print("What the modelled eye actually receives (blur then binarise), Inkplate @ 80 cm:")
s,_=geom("Inkplate")
for em in (16,24,64):
    face.set_pixel_sizes(0,em)
    out=[]
    for ch in "aegsbmnpRM8":
        face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_MONOCHROME)
        bm=face.glyph.bitmap
        im=Image.new('L',(bm.width,bm.rows))
        im.putdata([255 if (bm.buffer[y*bm.pitch+(x>>3)]>>(7-(x&7)))&1 else 0
                    for y in range(bm.rows) for x in range(bm.width)])
        M=4; im=im.resize((im.width*M,im.height*M),Image.NEAREST)
        pad=int(math.ceil(3*s*M))+2
        c=Image.new('L',(im.width+2*pad,im.height+2*pad),0); c.paste(im,(pad,pad))
        c=c.filter(ImageFilter.GaussianBlur(radius=s*M)).point(lambda v:255 if v>=128 else 0)
        comps,holes=topo(c)
        ink=c.histogram()[255]
        out.append(f"{ch}:{comps}c{holes}h" + ("(gone)" if ink==0 else ""))
    print(f"  em {em:>3}px  " + "  ".join(out))
print("\n  (each letter's true topology: a=1c1h e=1c1h g=1c2h s=1c0h b=1c1h m=1c0h")
print("   n=1c0h p=1c1h R=1c1h M=1c0h 8=1c2h -- counters that survive the blur are")
print("   the ones the eye can still use to tell letters apart.)")
