"""Which fill rule preserves stroke/counter topology? Reference topology comes
from a 4x supersampled render of the same outline, not from FreeType."""
import json
from functools import lru_cache
from collections import deque
import freetype as ft
face=ft.Face('out/Plex400.ttf')

def _cc(g,val,conn8):
    H,W=len(g),len(g[0]); seen=[[0]*W for _ in range(H)]; n=0
    nb=[(-1,0),(1,0),(0,-1),(0,1)]+([(-1,-1),(-1,1),(1,-1),(1,1)] if conn8 else [])
    for y in range(H):
        for x in range(W):
            if g[y][x]==val and not seen[y][x]:
                n+=1; q=deque([(y,x)]); seen[y][x]=1
                while q:
                    cy,cx=q.popleft()
                    for dy,dx in nb:
                        ny,nx=cy+dy,cx+dx
                        if 0<=ny<H and 0<=nx<W and not seen[ny][nx] and g[ny][nx]==val:
                            seen[ny][nx]=1; q.append((ny,nx))
    return n
def topo(g):
    if not g or not g[0]: return (0,0)
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
    return comps,_cc(inner,1,False)
@lru_cache(maxsize=None)
def ref_topo(ch,px,scale=4):
    face.set_pixel_sizes(0,int(px*scale))
    face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_NO_HINTING)
    bm=face.glyph.bitmap
    return topo([[1 if bm.buffer[y*bm.pitch+x]>=128 else 0 for x in range(bm.width)] for y in range(bm.rows)])
def ft_mono(ch,px):
    face.set_pixel_sizes(0,int(px))
    face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_MONOCHROME)
    g=face.glyph; bm=g.bitmap
    return [[(bm.buffer[y*bm.pitch+(x>>3)]>>(7-(x&7)))&1 for x in range(bm.width)] for y in range(bm.rows)]

recs=json.load(open('out/joins.json'))
ARMS=['zeno128','zeno96','tsk_aliased','ss3_centre']
LABEL={'zeno128':'zeno AA >=128 (current)','zeno96':'zeno AA >=96',
       'tsk_aliased':'tiny-skia aliased = pixel-centre rule','ss3_centre':'3x supersample, centre subpixel'}
for px in (16.0,24.0):
    rs=[r for r in recs if r['px']==px]
    print(f"\n=== {int(px)}px -- topology errors vs 4x reference ({len(rs)} glyphs) ===")
    for arm in ARMS:
        err=0; bad=[]
        for r in rs:
            w=r['w']; g=[[r[arm][y*w+x] for x in range(w)] for y in range(r['h'])]
            ref=ref_topo(r['ch'],px); got=topo(g)
            e=abs(got[0]-ref[0])+abs(got[1]-ref[1])
            if e: err+=e; bad.append(r['ch'])
        print(f"  {LABEL[arm]:<42} {err:>3}   {' '.join(bad[:14])}")
    fe=0; fbad=[]
    for r in rs:
        ref=ref_topo(r['ch'],px); got=topo(ft_mono(r['ch'],px))
        e=abs(got[0]-ref[0])+abs(got[1]-ref[1])
        if e: fe+=e; fbad.append(r['ch'])
    print(f"  {'FreeType FT_RENDER_MODE_MONO':<42} {fe:>3}   {' '.join(fbad[:14])}")
