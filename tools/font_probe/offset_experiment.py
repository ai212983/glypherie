"""Average translated coverage masks before one bilevel threshold; fixed hinting."""
import ctypes
import hashlib
import itertools
import json
from pathlib import Path

import freetype as ft
from fontTools.ttLib import TTFont
from PIL import Image,ImageDraw
from shapely.affinity import scale as reflect

from analyze_features import ROOT,FlattenPen,visible_boundary
from track_features import solid,bitmap_shape
from diagonal_experiment import render as mono
from calibrate import topology

OUT=ROOT/'tools/font_probe/out/offset-experiment'
OFFSETS=list(itertools.product((-16,0,16),repeat=2))


def coverage(face,char,dx,dy):
    face.load_char(char,ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_NO_BITMAP)
    o=face.glyph.outline._FT_Outline
    error=ft.FT_Outline_EmboldenXY(ctypes.byref(o),24,0)
    if error:raise ft.FT_Exception(error)
    ft.FT_Outline_Translate(ctypes.byref(o),-4+dx,dy)
    face.glyph.render(ft.FT_RENDER_MODE_NORMAL)
    s=face.glyph;b=s.bitmap;buf=b.buffer
    return {(s.bitmap_left+x,-s.bitmap_top+y):buf[y*b.pitch+x]
            for y in range(b.rows) for x in range(b.width)}


def average(samples):
    points=set().union(*samples)
    left=min(x for x,y in points);top=min(y for x,y in points)
    width=max(x for x,y in points)-left+1;height=max(y for x,y in points)-top+1
    values=[sum(s.get((left+x,top+y),0) for s in samples)/len(samples)
            for y in range(height) for x in range(width)]
    return dict(left=left,top=top,width=width,height=height,pixels=[int(v>=128) for v in values],coverage=values)


def asymmetric(shape):
    x0,y0,x1,y1=shape.bounds;origin=((x0+x1)/2,(y0+y1)/2)
    return {name:shape.symmetric_difference(reflect(shape,xfact=x,yfact=y,origin=origin)).area/shape.area
            for name,x,y in [('left_right',-1,1),('top_bottom',1,-1),('rotation_180',-1,-1)]}


def sheet(records,size,char,path):
    arms=['mono','coverage','average9'];phases=(0,8,16,24,32)
    im=Image.new('RGB',(960,570),'white');d=ImageDraw.Draw(im)
    for row,arm in enumerate(arms):
        for col,phase in enumerate(phases):
            r=next(r for r in records if (r['size'],r['char'],r['phase'],r['arm'])==(size,char,phase,arm))
            g=r['glyph'];ox=12+col*190;oy=165+row*185
            d.text((ox,12+row*185),f'{arm} / x offset {phase}/64px',fill='black')
            for i,v in enumerate(g['pixels']):
                if v:
                    x=ox+(g['left']+i%g['width'])*9;y=oy+(g['top']+i//g['width'])*9
                    d.rectangle((x,y,x+8,y+8),fill='black')
    im.save(path)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    path=ROOT/'tools/font_probe/fonts/Roboto.ttf'
    face=ft.Face(str(path));face.set_var_design_coords([400,100])
    f=TTFont(path);gs=f.getGlyphSet(location={'wght':400,'wdth':100});cmap=f.getBestCmap()
    p=FlattenPen(gs,16/f['head'].unitsPerEm);gs[cmap[ord('X')]].draw(p)
    source=asymmetric(solid(visible_boundary(p.contours)))
    records=[]
    for size in (14,16,18,20):
        face.set_pixel_sizes(0,size)
        for char in 'XxKVWY':
            for phase in (0,8,16,24,32):
                variants={'mono':mono(face,char,ft.FT_LOAD_TARGET_MONO,24,8+phase),
                          'coverage':average([coverage(face,char,phase,0)]),
                          'average9':average([coverage(face,char,phase+x,y) for x,y in OFFSETS])}
                for arm,g in variants.items():
                    records.append(dict(size=size,char=char,phase=phase,arm=arm,glyph=g,topology=topology(g,1),
                                        symmetry=asymmetric(bitmap_shape(g)) if char=='X' else None))
    result=dict(font_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),freetype_version=ft.version(),
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependency_hashes={n:hashlib.sha256((ROOT/'tools/font_probe'/n).read_bytes()).hexdigest()
                                   for n in ('analyze_features.py','track_features.py','diagonal_experiment.py','calibrate.py')},
                parameters=dict(hinting='native mono target',growth_26_6=24,base_phase_26_6=8,
                                offsets_26_6=OFFSETS,threshold=128,phases_26_6=[0,8,16,24,32]),
                source_X_symmetry=source,records=records,
                limits='Equal-weight coverage averaging, no alignment back after translation; no symmetry constraint. Reflection metric is symmetric-difference area divided by original area about bounding-box center.')
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    sheet(records,16,'X',OUT/'X-16.png')
    print('Source X asymmetry:',source)
    print('Cases',len(records),'topology flags',[(r['size'],r['char'],r['arm'],r['phase'],r['topology']) for r in records if r['topology']!=(1,0)])


if __name__=='__main__':main()
