"""Fixed-arm hinting/growth comparison for diagonal glyphs; analysis only."""
import ctypes
import hashlib
import json
from pathlib import Path

import freetype as ft
from PIL import Image, ImageDraw

from analyze_features import ROOT
from calibrate import topology

OUT=ROOT/'tools/font_probe/out/diagonal-experiment'
ARMS=[('Current',ft.FT_LOAD_TARGET_MONO,24,8),
      ('No growth, same shift',ft.FT_LOAD_TARGET_MONO,0,8),
      ('No growth, grid origin',ft.FT_LOAD_TARGET_MONO,0,0),
      ('Auto hint, no growth',ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_FORCE_AUTOHINT,0,0),
      ('Unhinted, no growth',ft.FT_LOAD_NO_HINTING,0,0)]
CHARS='XxKVWY'


def render(face,char,flags,growth,phase):
    face.load_char(char,flags|ft.FT_LOAD_NO_BITMAP)
    outline=face.glyph.outline._FT_Outline
    error=ft.FT_Outline_EmboldenXY(ctypes.byref(outline),growth,0)
    if error:raise ft.FT_Exception(error)
    ft.FT_Outline_Translate(ctypes.byref(outline),phase-growth//2,0)
    face.glyph.render(ft.FT_RENDER_MODE_MONO)
    s=face.glyph;b=s.bitmap;buffer=b.buffer
    if b.pitch<0 or b.pixel_mode!=ft.FT_PIXEL_MODE_MONO:raise ValueError('unexpected bitmap format')
    return dict(codepoint=ord(char),left=s.bitmap_left,top=-s.bitmap_top,
                width=b.width,height=b.rows,advance_26_6=s.advance.x,
                pixels=[(buffer[y*b.pitch+x//8]>>(7-x%8))&1 for y in range(b.rows) for x in range(b.width)])


def draw(records,selected_rows,path):
    scale=8;cell=175;height=195
    im=Image.new('RGB',(len(ARMS)*cell+20,len(selected_rows)*height+55),'white');d=ImageDraw.Draw(im)
    for col,(name,*_) in enumerate(ARMS):d.text((12+col*cell,12),name,fill='black')
    lookup={(r['size'],r['character'],r['arm']):r['glyph'] for r in records}
    for row,(size,char) in enumerate(selected_rows):
        y=50+row*height
        for col,(name,*_) in enumerate(ARMS):
            g=lookup[size,char,name];ox=12+col*cell;oy=y+140
            d.text((ox,y),f'{char} / {size}px',fill='black')
            for i,v in enumerate(g['pixels']):
                if v:
                    x=g['left']+i%g['width'];yy=g['top']+i//g['width']
                    d.rectangle((ox+x*scale,oy+yy*scale,ox+x*scale+scale-1,oy+yy*scale+scale-1),fill='black')
                    d.point((ox+145+x,y+20+yy),fill='black')
    im.save(path)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    font=ROOT/'tools/font_probe/fonts/Roboto.ttf'
    expected=json.loads((ROOT/'tools/font_generator/examples/roboto.json').read_text())['provenance']['expected_sha256']
    if hashlib.sha256(font.read_bytes()).hexdigest()!=expected:raise ValueError('font checksum mismatch')
    face=ft.Face(str(font));face.set_var_design_coords([400,100]);records=[]
    for size in (14,16,18,20):
        face.set_pixel_sizes(0,size)
        for char in CHARS:
            for name,flags,growth,phase in ARMS:
                g=render(face,char,flags,growth,phase)
                records.append(dict(size=size,character=char,arm=name,glyph=g,
                                    topology=topology(g,1),ink_pixels=sum(g['pixels'])))
    result=dict(font_sha256=expected,freetype_version=ft.version(),
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                axes={'wght':400,'wdth':100},arms=[dict(name=a,flags=b,growth_26_6=c,phase_26_6=d) for a,b,c,d in ARMS],
                limits='Fixed comparison arms; no automatic arm selection or geometry repair. Hinting modes may change advance metrics.',records=records)
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    draw(records,[(s,'X') for s in (14,16,18,20)],OUT/'X-sizes.png')
    draw(records,[(16,c) for c in CHARS],OUT/'diagonals-16.png')
    print('Rendered',len(records),'cases')
    print('Unexpected topology:',[(r['size'],r['character'],r['arm'],r['topology']) for r in records if r['topology']!=(1,0)])


if __name__=='__main__':main()
