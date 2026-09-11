"""Render saved Shamir and prepared-segment candidate using identical scan flags."""
import json
from pathlib import Path
import freetype as ft
from PIL import Image,ImageDraw
from compare_paper_prototypes import HERE,digest,render,pixels,draw_glyph,check_bounds
from compare_shamir_pipeline import CHARS,SIZES,text_positions
from shamir_segment_fit import build_font


def main():
    base=HERE/'out/shamir-controlled';out=base/'segments';out.mkdir(exist_ok=True)
    baseline=json.loads((base/'report.json').read_text());records=[];builds=[]
    inputs={p.name:digest(p) for p in base.glob('*.ttf')}
    sources={p:digest(HERE/p) for p in ('shamir_segment_fit.py','shamir_features.py','shamir_geometry.py','compare_shamir_segments.py')}
    for name in ('roboto','literata','source-sans-3'):
        for size in SIZES:
            src=base/f'{name}-{size}-source.ttf';dst=out/f'{name}-{size}.ttf'
            build=build_font(src,dst,CHARS);builds.append(dict(font=name,size=size,**build))
            a=ft.Face(str(base/f'{name}-{size}-shamir.ttf'));b=ft.Face(str(dst));source=ft.Face(str(src))
            subset=[]
            for char in CHARS:
                old=render(a,char,size,hinted=True);new=render(b,char,size,hinted=True)
                saved=next(r for r in baseline['records'] if (r['font'],r['size'],r['char'])==(name,size,char))
                if old!=saved['shamir']:raise ValueError('baseline reproduction mismatch')
                r=dict(font=name,size=size,char=char,a=old,b=new,reference=render(source,char,size*6),different_pixels=len(pixels(old)^pixels(new)),preparation_changed_pixels=len(pixels(render(source,char,size))^pixels(render(b,char,size))))
                subset.append(r);records.append(r)
            for group,chars in [('focus','eX.,:;!?'),('regression','6gbdhmnpqEKYv'),('alphabet',CHARS)]:
                selected=[r for c in chars for r in subset if r['char']==c]
                cols=8;rows=(len(selected)+cols-1)//cols
                im=Image.new('RGB',(cols*180,rows*510+35),'white');d=ImageDraw.Draw(im)
                d.text((10,10),f'{name} {size}px | source / A current Shamir / B segment candidate | 6x pixels',fill='black')
                for i,r in enumerate(selected):
                    x=i%cols*180;y=i//cols*510+35;d.text((x+10,y),repr(r['char']),fill='black')
                    for j,key in enumerate(('reference','a','b')):
                        scale=1 if key=='reference' else 6;baseline_y=y+150+j*165
                        d.text((x+2,baseline_y-30),('S','A','B')[j],fill='#555555')
                        glyph=r[key];xx=x+25-min(0,glyph['left']*scale)
                        check_bounds(glyph,xx,baseline_y,scale,(x,y+12,x+180,y+510))
                        draw_glyph(d,glyph,xx,baseline_y,scale)
                im.save(out/f'{name}-{size}-{group}.png')
            im=Image.new('RGB',(1000,220),'white');d=ImageDraw.Draw(im)
            for row,key in enumerate(('a','b')):
                y=10+row*105;d.text((10,y),f'{name} {size}px '+('A: current Shamir' if key=='a' else 'B: segment candidate'),fill='black')
                glyphs={r['char']:r[key] for r in subset}
                for line,text in enumerate(('Example X: minimum 6g bdh npq', '21.5°C - 48% + 6 = 27.5; Why?!')):
                    run=text_positions(src.read_bytes(),glyphs,text,size)
                    for p in run['placements']:draw_glyph(d,glyphs[p['char']],15+p['x'],y+36+line*32+p['y'],1)
            im.save(out/f'{name}-{size}-text.png')
            print(json.dumps(dict(font=name,size=size,changed=sum(bool(r['different_pixels']) for r in subset),diagonals=sum(r['diagonals_applied'] for r in build['records'].values()))),flush=True)
    if inputs!={p.name:digest(p) for p in base.glob('*.ttf')}:raise ValueError('baseline files changed')
    (out/'report.json').write_text(json.dumps(dict(records=records,builds=builds,inputs=inputs,source_hashes=sources),indent=2)+'\n')
    (out/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>Shamir rendered comparison</title>
<style>body{font:16px system-ui;background:#eee;margin:24px}header{position:sticky;top:0;background:#eee;padding:12px}select{font:inherit}img{display:block;max-width:none;image-rendering:pixelated;margin:20px 0}</style>
<header><b>A: current Shamir · B: corrected stroke anchors</b><p>Updated: paired curve edges preserve stroke width. <a href="../segments-before-width-fix/">Previous candidate</a>. Experimental candidate, not approved. Known regressions: Roboto 14px X has a thinner centre; Source Sans 3 14px punctuation is uneven. Source is a shape reference. Same MONO scan, dropout off.</p>
<select id="font"><option>roboto</option><option>literata</option><option>source-sans-3</option></select>
<select id="size"><option>14</option><option>16</option><option>18</option><option>20</option></select>
<select id="group"><option>focus</option><option>regression</option><option>alphabet</option></select>
<p>Native text first (100% browser zoom), then enlarged glyphs: S source, A current, B candidate.</p></header><img id="text"><img id="glyphs">
<script>const f=document.querySelector('#font'),s=document.querySelector('#size'),g=document.querySelector('#group');function show(){document.querySelector('#text').src=f.value+'-'+s.value+'-text.png?v=stroke-width';document.querySelector('#glyphs').src=f.value+'-'+s.value+'-'+g.value+'.png?v=stroke-width'}[f,s,g].forEach(e=>e.onchange=show);show()</script>''')

if __name__=='__main__':main()
