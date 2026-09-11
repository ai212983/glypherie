"""Absolute quality metrics for low-resolution glyph rendering.

None of these compare against FreeType. They measure properties that make
small text readable, so any renderer -- FreeType included -- can score badly.
Topology ground truth comes from an 8x supersampled render of the same
outline, which is renderer-independent.
"""
import json, sys
from functools import lru_cache
from collections import deque, Counter
import freetype as ft

FONT='out/Plex400.ttf'
face=ft.Face(FONT)

def ft_mono(ch,px):
    face.set_pixel_sizes(0,int(px))
    face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_MONOCHROME)
    g=face.glyph; bm=g.bitmap
    grid=[[(bm.buffer[y*bm.pitch+(x>>3)]>>(7-(x&7)))&1 for x in range(bm.width)] for y in range(bm.rows)]
    return grid,g.bitmap_left,g.bitmap_top

@lru_cache(maxsize=None)
def ft_ref_topology(ch,px,scale=4):
    """Renderer-independent topology: the same outline at 8x, unhinted."""
    face.set_pixel_sizes(0,int(px*scale))
    face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_NO_HINTING)
    bm=face.glyph.bitmap
    grid=[[1 if bm.buffer[y*bm.pitch+x]>=128 else 0 for x in range(bm.width)] for y in range(bm.rows)]
    return topology(grid)

def load_ours(px, sec='h', ras='zeno'):
    out={}
    for r in json.load(open('out/rasters1.json')):
        if r['px']!=px: continue
        s=r[sec]; w=s['w']
        grid=[[s[ras][y*w+x] for x in range(w)] for y in range(s['h'])]
        out[r['ch']]=(grid,s['l'],s['t'])
    return out

def _cc(grid,val,conn8):
    if not grid or not grid[0]: return 0
    H,W=len(grid),len(grid[0]); seen=[[False]*W for _ in range(H)]; n=0
    nb=[(-1,0),(1,0),(0,-1),(0,1)]+([(-1,-1),(-1,1),(1,-1),(1,1)] if conn8 else [])
    for y in range(H):
        for x in range(W):
            if grid[y][x]==val and not seen[y][x]:
                n+=1; q=deque([(y,x)]); seen[y][x]=True
                while q:
                    cy,cx=q.popleft()
                    for dy,dx in nb:
                        ny,nx=cy+dy,cx+dx
                        if 0<=ny<H and 0<=nx<W and not seen[ny][nx] and grid[ny][nx]==val:
                            seen[ny][nx]=True; q.append((ny,nx))
    return n

def topology(grid):
    """(ink components, enclosed holes). Ink 8-connected, background 4-connected."""
    if not grid or not grid[0]: return (0,0)
    H,W=len(grid),len(grid[0])
    pad=[[0]*(W+2)]+[[0]+row+[0] for row in grid]+[[0]*(W+2)]
    comps=_cc(pad,1,True)
    # background regions reachable from the border are outside
    seen=[[False]*(W+2) for _ in range(H+2)]; q=deque([(0,0)]); seen[0][0]=True
    while q:
        cy,cx=q.popleft()
        for dy,dx in ((-1,0),(1,0),(0,-1),(0,1)):
            ny,nx=cy+dy,cx+dx
            if 0<=ny<H+2 and 0<=nx<W+2 and not seen[ny][nx] and pad[ny][nx]==0:
                seen[ny][nx]=True; q.append((ny,nx))
    inner=[[1 if (pad[y][x]==0 and not seen[y][x]) else 0 for x in range(W+2)] for y in range(H+2)]
    holes=_cc(inner,1,False)
    return comps,holes

XH="acemnorsuvwxz"; CAPS="EFHILT"; SYM="oxHITAMWvw08"
STEM="bdhiklmnpqruEFHILT"
CONFUSE=[("I","l"),("l","1"),("I","1"),("O","0"),("5","S"),("8","B"),("c","e"),("g","9")]

def ink(g): return sum(sum(r) for r in g)

def score(glyphs, px, label):
    # 1. topology errors vs 8x reference
    topo_err=0; topo_bad=[]
    for ch,(g,l,t) in glyphs.items():
        if ch.isspace(): continue
        ref=ft_ref_topology(ch,px)
        got=topology(g)
        e=abs(got[0]-ref[0])+abs(got[1]-ref[1])
        if e: topo_err+=e; topo_bad.append(f"{ch}({got[0]},{got[1]}!={ref[0]},{ref[1]})")
    # 2. x-height / cap-height row consistency
    def rows(sel):
        vals=[glyphs[c][2] for c in sel if c in glyphs]
        return Counter(vals)
    xh=rows(XH); cap=rows(CAPS)
    # 3. stem-width uniformity: horizontal run lengths at mid x-height
    runs=Counter()
    for ch in STEM:
        if ch not in glyphs: continue
        g,_,t=glyphs[ch]; H=len(g)
        if H<3: continue
        row=g[H//2]; n=0
        for v in row+[0]:
            if v: n+=1
            elif n: runs[n]+=1; n=0
    dom=runs.most_common(1)[0] if runs else (0,0)
    off=sum(v for k,v in runs.items() if k!=dom[0])
    # 4. symmetry
    sym_err=0; sym_tot=0
    for ch in SYM:
        if ch not in glyphs: continue
        g,_,_=glyphs[ch]
        mir=[list(reversed(r)) for r in g]
        sym_err+=sum(1 for y in range(len(g)) for x in range(len(g[0])) if g[y][x]!=mir[y][x])
        sym_tot+=ink(g)
    # 5. confusability: normalised symmetric difference, higher is better
    conf=[]
    for a,b in CONFUSE:
        if a not in glyphs or b not in glyphs: continue
        ga,la,ta=glyphs[a]; gb,lb,tb=glyphs[b]
        pa={(la+x,ta-y) for y,r in enumerate(ga) for x,v in enumerate(r) if v}
        pb={(lb+x,tb-y) for y,r in enumerate(gb) for x,v in enumerate(r) if v}
        u=len(pa|pb)
        conf.append((f"{a}/{b}", len(pa^pb)/u if u else 0))
    print(f"\n=== {label} @ {int(px)}px ===")
    print(f"  topology errors (lost/gained strokes or counters) : {topo_err}"
          + (f"   {' '.join(topo_bad[:8])}" if topo_bad else "   none"))
    print(f"  x-height top rows   : {len(xh)} distinct {dict(xh)}")
    print(f"  cap-height top rows : {len(cap)} distinct {dict(cap)}")
    print(f"  stem widths at mid-x: dominant {dom[0]}px x{dom[1]}, off-width runs {off}  {dict(runs)}")
    print(f"  symmetry error      : {sym_err} px ({100*sym_err/max(1,sym_tot):.1f}% of ink)")
    print(f"  confusability (higher=better): " + "  ".join(f"{k} {v:.2f}" for k,v in conf))
    return dict(topo=topo_err, xh=len(xh), cap=len(cap), off=off, sym=sym_err,
                conf=sum(v for _,v in conf)/max(1,len(conf)))

for px in (16.0, 24.0):
    ours=load_ours(px)
    ftg={ch:ft_mono(ch,px) for ch in ours}
    a=score(ftg, px, "FreeType FT_RENDER_MODE_MONO")
    b=score(ours, px, "ours: skrifa Target::Mono + zeno")
    print(f"\n  --- {int(px)}px head-to-head (lower better except conf) ---")
    for k in ('topo','xh','cap','off','sym'):
        w = "FreeType" if a[k]<b[k] else ("ours" if b[k]<a[k] else "tie")
        print(f"    {k:<6} FreeType {a[k]:>5}   ours {b[k]:>5}   -> {w}")
    print(f"    {'conf':<6} FreeType {a['conf']:>5.2f}   ours {b['conf']:>5.2f}   -> "
          + ("ours" if b['conf']>a['conf'] else "FreeType" if a['conf']>b['conf'] else "tie"))
