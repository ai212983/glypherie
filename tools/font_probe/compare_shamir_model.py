"""Render saved Shamir and combined-model candidate using identical scan flags."""
import json
from pathlib import Path
import freetype as ft
from PIL import Image,ImageDraw
from compare_paper_prototypes import HERE,digest,render,pixels,draw_glyph,check_bounds
from compare_shamir_pipeline import CHARS,SIZES,text_positions
import shutil


def main():
    base=HERE/'out/shamir-controlled';out=base/'combined';out.mkdir(exist_ok=True)
    baseline=json.loads((base/'report.json').read_text());records=[];builds=[]
    conformance=json.loads((HERE/'out/shamir-model/conformance.json').read_text())
    for path,value in conformance['source_hashes'].items():
        if digest(HERE/path)!=value:raise ValueError('conformance source differs from current model')
    if any(r['violations'] or not all(r['coverage'].values()) for r in conformance['records']):raise ValueError('conformance checks incomplete')
    inputs={p.name:digest(p) for p in base.glob('*.ttf')}
    sources={p:digest(HERE/p) for p in ('shamir_model.py','shamir_constraints.py','shamir_templates.py','shamir_features.py','shamir_geometry.py','compare_shamir_model.py')}
    for name in ('roboto','literata','source-sans-3'):
        for size in SIZES:
            src=base/f'{name}-{size}-source.ttf';dst=out/f'{name}-{size}.ttf'
            checked=HERE/f'out/shamir-model/{name}-{size}.ttf'
            checked_record=next(b for b in conformance['builds'] if (b['font'],b['size'])==(name,size))
            if digest(checked)!=checked_record['font_sha256'] or digest(src)!=checked_record['source_sha256']:
                raise ValueError('font files differ from conformance run')
            shutil.copyfile(checked,dst)
            builds.append(dict(font=name,size=size,font_sha256=digest(dst)))
            a=ft.Face(str(base/f'{name}-{size}-shamir.ttf'));b=ft.Face(str(dst));source=ft.Face(str(src))
            subset=[]
            for char in CHARS:
                old=render(a,char,size,hinted=True);new=render(b,char,size,hinted=True)
                saved=next(r for r in baseline['records'] if (r['font'],r['size'],r['char'])==(name,size,char))
                if old!=saved['shamir']:raise ValueError('baseline reproduction mismatch')
                r=dict(font=name,size=size,char=char,a=old,b=new,reference=render(source,char,size*6),different_pixels=len(pixels(old)^pixels(new)),preparation_changed_pixels=len(pixels(render(source,char,size))^pixels(render(b,char,size))))
                subset.append(r);records.append(r)
            for group,chars in [('focus','FaeX.,:;!?'),('regression','6gbdhmnpqEKYv'),('audit','NRZKm4Pe'),('alphabet',CHARS)]:
                selected=[r for c in chars for r in subset if r['char']==c]
                cols=8;rows=(len(selected)+cols-1)//cols
                measures=[(r[key],1 if key=='reference' else 6) for r in selected for key in ('reference','a','b')]
                ascent=max(120,max(-g['top']*s for g,s in measures)+12)
                descent=max(28,max((g['top']+g['height'])*s for g,s in measures)+12)
                step=ascent+descent+20;cell_height=30+3*step
                pad=max(25,16-min(g['left']*s for g,s in measures))
                cell_width=max(180,pad+16+max((g['left']+g['width'])*s for g,s in measures))
                im=Image.new('RGB',(cols*cell_width,rows*cell_height+35),'white');d=ImageDraw.Draw(im)
                d.text((10,10),f'{name} {size}px | source / A current Shamir / B combined model | 6x pixels',fill='black')
                for i,r in enumerate(selected):
                    x=i%cols*cell_width;y=i//cols*cell_height+35;d.text((x+10,y),repr(r['char']),fill='black')
                    for j,key in enumerate(('reference','a','b')):
                        scale=1 if key=='reference' else 6;baseline_y=y+30+ascent+j*step
                        d.text((x+2,baseline_y-30),('S','A','B')[j],fill='#555555')
                        glyph=r[key];xx=x+pad

                        check_bounds(glyph,xx,baseline_y,scale,(x,y+12,x+cell_width,y+cell_height))
                        draw_glyph(d,glyph,xx,baseline_y,scale)
                im.save(out/f'{name}-{size}-{group}.png')
            im=Image.new('RGB',(1000,220),'white');d=ImageDraw.Draw(im)
            for row,key in enumerate(('a','b')):
                y=10+row*105;d.text((10,y),f'{name} {size}px '+('A: current Shamir' if key=='a' else 'B: combined model'),fill='black')
                glyphs={r['char']:r[key] for r in subset}
                for line,text in enumerate(('Example X: minimum 6g bdh npq', '21.5°C - 48% + 6 = 27.5; Why?!')):
                    run=text_positions(src.read_bytes(),glyphs,text,size)
                    for p in run['placements']:
                        glyph=glyphs[p['char']];xx=15+p['x'];yy=y+36+line*32+p['y']
                        check_bounds(glyph,xx,yy,1,(0,y+18,1000,y+105))
                        draw_glyph(d,glyph,xx,yy,1)
            im.save(out/f'{name}-{size}-text.png')
            print(json.dumps(dict(font=name,size=size,changed=sum(bool(r['different_pixels']) for r in subset),cases=len(subset))),flush=True)
    if inputs!={p.name:digest(p) for p in base.glob('*.ttf')}:raise ValueError('baseline files changed')
    (out/'report.json').write_text(json.dumps(dict(records=records,builds=builds,inputs=inputs,source_hashes=sources),indent=2)+'\n')
    (out/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>Shamir combined model comparison</title>
<style>body{font:16px system-ui;background:#eee;margin:24px}header{position:sticky;top:0;background:#eee;padding:12px}select{font:inherit}img{display:block;max-width:none;image-rendering:pixelated;margin:20px 0}</style>
<header><b>A: current Shamir · B: combined model</b><p>Same source outlines, MONO scan and dropout-off settings. B includes scalar dependency scheduling: Roboto 14px F is fixed. Full review of all 972 cases found new and retained defects, including Roboto 14px H, Literata 18px h/n and Source Sans 3 14px !. This candidate has not passed visual review. A remains the preferred baseline; user review is pending.</p>
<select id="font"><option>roboto</option><option>literata</option><option>source-sans-3</option></select>
<select id="size"><option>14</option><option>16</option><option>18</option><option>20</option></select>
<select id="group"><option>focus</option><option>regression</option><option>audit</option><option>alphabet</option></select>
<p>Native text first (100% browser zoom), then enlarged glyphs: S source, A current, B candidate.</p></header><img id="text"><img id="glyphs">
<script>const f=document.querySelector('#font'),s=document.querySelector('#size'),g=document.querySelector('#group');function show(){document.querySelector('#text').src=f.value+'-'+s.value+'-text.png?v=combined-scalar-1';document.querySelector('#glyphs').src=f.value+'-'+s.value+'-'+g.value+'.png?v=combined-scalar-1'}[f,s,g].forEach(e=>e.onchange=show);show()</script>''')

if __name__=='__main__':main()
