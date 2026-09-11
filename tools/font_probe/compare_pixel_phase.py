"""Whole-outline translation diagnostic; never changes font programs or shape."""
import json,shutil
from pathlib import Path
import numpy as np
import freetype as ft
from PIL import Image,ImageDraw
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels,draw_glyph
from check_shamir_baseline import digest
from serif_reference_view import prepend_reference
from compare_shamir_representatives import comparison

HERE=Path(__file__).resolve().parent
OFFSETS=(-8,-2,0,2,8)  # exact 26.6 units: -1/8, -1/32, 0, +1/32, +1/8 pixel


def run():
    root=HERE/'out/outside-in-v1';out=HERE/'out/pixel-phase-v1'
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    shutil.copy2(Path(__file__),out/Path(__file__).name)
    cases=[];sections=[];inputs={}
    # Repertoire selection belongs to the diagnostic, not any correction rule.
    for size in (14,16,18,20):
        key=f'literata-{size}';path=root/f'{key}-u0025.ttf';inputs[path.name]=digest(path)
        face=ft.Face(str(path));points=coords(face,'%',size);base=render(face,'%',size,hinted=True);ink=pixels(base)
        variants=[]
        for dy in reversed(OFFSETS):
            for dx in OFFSETS:
                shifted=points+np.array([dx,dy])/64
                assert np.array_equal(np.rint(shifted*64)-np.rint(points*64),np.tile([dx,dy],(len(points),1)))
                glyph=render(face,'%',size,points=shifted,hinted=True);current=pixels(glyph)
                if dx==dy==0:assert current==ink
                variants.append((glyph,dict(dx=dx/64,dy=dy/64,added=sorted(current-ink),removed=sorted(ink-current))))
        all_pixels=set().union(ink,*(pixels(g) for g,_ in variants))
        x0=min(x for x,y in all_pixels);y0=min(y for x,y in all_pixels)
        scale=8;w=max(210,(max(x for x,y in all_pixels)-x0+1)*scale+32)
        h=(max(y for x,y in all_pixels)-y0+1)*scale+100
        sheet=Image.new('RGB',(w*5,h*5),'white');draw=ImageDraw.Draw(sheet)
        for index,(glyph,row) in enumerate(variants):
            x=(index%5)*w;y=(index//5)*h
            draw.rectangle((x,y,x+w-1,y+h-1),outline='#dddddd')
            if row['dx']==row['dy']==0:draw.rectangle((x+1,y+1,x+w-2,y+h-2),outline='#087f23',width=3)
            draw.text((x+12,y+10),f"x {row['dx']:+.5f} / y {row['dy']:+.5f}",fill='black')
            draw_glyph(draw,glyph,x+16-x0*scale,y+40-y0*scale,scale)
            draw.text((x+12,y+h-35),f"+{len(row['added'])} / -{len(row['removed'])} pixels",fill='black')
        sheet.save(out/f'{key}-grid.png')
        panel=comparison([base],['Unshifted fitted glyph'],key+' %')
        prepend_reference(face,'%',size,key+' %',[base],panel).save(out/f'{key}-reference.png')
        cases.append(dict(key=key,variants=[r for _,r in variants]))
        sections.append(f'<section><h2>{key}</h2><img src="{key}-reference.png"><div class="scroll"><img src="{key}-grid.png"></div></section>')
    assert inputs=={n:digest(root/n) for n in inputs}
    (out/'report.json').write_text(json.dumps(dict(inputs=inputs,cases=cases,script_sha256=digest(Path(__file__)),
        scope='Translate the entire hinted outline, including both loops and diagonal. Positive y moves upward. Shape, program and advance remain unchanged; ink placement relative to metrics intentionally varies. No phase selected for production.'),indent=2)+'\n')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:16px sans-serif}.scroll{overflow-x:auto}.scroll img{max-width:none}img{image-rendering:pixelated}</style><h1>Whole-glyph pixel phase</h1><p>Columns: increasing x shift. Rows: +1/8, +1/32, 0, -1/32, -1/8 pixel in y. Green centre is unchanged. Labels count added/removed pixels across the whole glyph. Scroll horizontally if needed. The fitted outline is translated without reshaping.</p>'+''.join(sections))
    print('100 translations verified; four zero-offset controls identical')


if __name__=='__main__':run()
