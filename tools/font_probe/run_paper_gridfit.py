"""Paper-guided calibration entry point; no post-render corrections or growth."""
import argparse
import hashlib
import json
import string
from pathlib import Path

from PIL import Image,ImageDraw
import numpy as np

from paper_gridfit import ft,load,pairs,width_table,generate,bitmap
from analyze_features import ROOT
from calibrate import topology

OUT=ROOT/'tools/font_probe/out/paper-gridfit'
CHARS=string.ascii_uppercase+string.ascii_lowercase+string.digits


def sheet(records,name):
    chars='XHbhmnpdq';s=6;cell=105
    im=Image.new('RGB',(len(chars)*cell+24,4*170+40),'white');d=ImageDraw.Draw(im)
    for row,size in enumerate((14,16,18,20)):
        d.text((12,8+row*170),f'{name} {size}px / outline grid constraints',fill='black')
        for col,char in enumerate(chars):
            r=next(r for r in records if r['size']==size and r['char']==char)
            if 'error' in r:continue
            g=r['glyph'];ox=12+col*cell;oy=145+row*170
            d.text((ox,28+row*170),char,fill='black')
            for i,v in enumerate(g['pixels']):
                if v:
                    x=ox+(g['left']+i%g['width'])*s;y=oy+(g['top']+i//g['width'])*s
                    d.rectangle((x,y,x+s-1,y+s-1),fill='black')
    im.save(OUT/f'{name}.png')


def comparison(records,name):
    scale=8
    im=Image.new('RGB',(660,360),'white');draw=ImageDraw.Draw(im)
    draw.text((12,12),f'{name} X: native hints / paper-guided outline constraints',fill='black')
    for column,size in enumerate((14,16,18,20)):
        record=next(r for r in records if r['size']==size and r['char']=='X')
        for row,key in enumerate(('baseline_glyph','glyph')):
            glyph=record[key];left=column*160+20;top=row*165+40
            draw.text((left,top),f'{size}px '+('native' if row==0 else 'constrained'),fill='black')
            for i,value in enumerate(glyph['pixels']):
                if value:
                    x=left+(i%glyph['width'])*scale;y=top+22+(i//glyph['width'])*scale
                    draw.rectangle((x,y,x+scale-1,y+scale-1),fill='black')
    im.save(OUT/f'{name}-x-comparison.png')


def stem_comparison(records,name,bowls=False):
    chars='bhmnpdqX';scale=7;cell=125
    label_after='Bowl + stem constraints' if bowls else 'Stem + curve constraints'
    im=Image.new('RGB',(1020,640),'white');draw=ImageDraw.Draw(im)
    for row,(size,key,label) in enumerate(((16,'baseline_glyph','Before'),(16,'glyph',label_after),(18,'baseline_glyph','Before'),(18,'glyph',label_after))):
        draw.text((12,row*160+8),f'{name} {size}px / {label}',fill='black')
        for col,char in enumerate(chars):
            record=next(r for r in records if r['size']==size and r['char']==char)
            glyph=record[key];left=col*cell+12;baseline=row*160+128
            draw.text((left,row*160+28),char,fill='black')
            for i,value in enumerate(glyph['pixels']):
                if value:
                    x=left+(i%glyph['width'])*scale;y=baseline+(glyph['top']+i//glyph['width'])*scale
                    draw.rectangle((x,y,x+scale-1,y+scale-1),fill='black')
    im.save(OUT/f'{name}-stems-comparison.png')


def prior_topology_review():
    rows=[]
    for name in ('roboto','literata','source-sans-3'):
        prior_path=OUT.parent/'paper-stems'/f'{name}.json'
        if not prior_path.exists():continue
        prior=json.loads(prior_path.read_text())
        current=json.loads((OUT/f'{name}.json').read_text())
        for old in prior['records']:
            if 'error' in old or old['topology']==old['baseline_topology']:continue
            new=next(r for r in current['records'] if r['char']==old['char'] and r['size']==old['size'])
            rows.append(dict(font=name,size=old['size'],char=old['char'],
                             glyphs=[old['baseline_glyph'],old['glyph'],new['glyph']]))
    if not rows:return
    im=Image.new('RGB',(750,len(rows)*180+35),'white');draw=ImageDraw.Draw(im)
    for col,label in enumerate(('Before stems','Stem extension','Bowl extension')):
        draw.text((col*250+12,8),label,fill='black')
    for row,record in enumerate(rows):
        for col,glyph in enumerate(record['glyphs']):
            left=col*250+12;top=row*180+36
            draw.text((left,top),f"{record['font']} {record['size']}px {record['char']}",fill='black')
            for i,value in enumerate(glyph['pixels']):
                if value:
                    x=left+(i%glyph['width'])*7;y=top+22+(i//glyph['width'])*7
                    draw.rectangle((x,y,x+6,y+6),fill='black')
    im.save(OUT/'prior-topology-review.png')


def main():
    global OUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--stems',action='store_true')
    parser.add_argument('--bowls',action='store_true')
    parser.add_argument('--source-aware',action='store_true')
    parser.add_argument('--curves',action='store_true')
    args=parser.parse_args()
    if args.curves:args.source_aware=True
    if args.source_aware:args.bowls=True
    if args.bowls:args.stems=True
    if args.stems:OUT=OUT.parent/('paper-curves' if args.curves else 'paper-source-aware' if args.source_aware else ('paper-bowls' if args.bowls else 'paper-stems'))
    OUT.mkdir(parents=True,exist_ok=True)
    summaries=[]
    for filename in ('roboto','literata','source-sans-3'):
        jobpath=ROOT/f'tools/font_generator/examples/{filename}.json'
        job=json.loads(jobpath.read_text());font=(jobpath.parent/job['font']).resolve()
        digest=hashlib.sha256(font.read_bytes()).hexdigest()
        if digest!=job['provenance']['expected_sha256']:raise ValueError('font checksum mismatch')
        face=ft.Face(str(font));axes=face.get_variation_info().axes;records=[];tables={}
        for size in (14,16,18,20):
            values=dict(job['settings']['axes']);values['wght']=400
            if any(a.tag=='opsz' for a in axes):values['opsz']=size
            face.set_var_design_coords([values.get(a.tag,a.default) for a in axes]);face.set_pixel_sizes(0,size)
            widths=[]
            for char in CHARS:
                source,_,tags,ends=load(face,char,size)
                widths.extend(p['width'] for p in pairs(source,tags,ends,size))
            table=width_table(widths);tables[size]=dict(diagonal=table)
            stem_table=None
            if args.stems:
                from stem_gridfit import stems
                vertical=[]
                for char in CHARS:
                    source,_,tags,ends=load(face,char,size)
                    vertical.extend(p['width'] for p in stems(source,tags,ends,size))
                stem_table=width_table(vertical);tables[size]['vertical']=stem_table
            for char in CHARS:
                try:
                    face.load_char(char,ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_NO_BITMAP)
                    baseline=bitmap(face,char)
                    if args.stems:baseline,_=generate(face,char,size,table,stem_table if args.bowls else None)
                    glyph,diagnostics=generate(face,char,size,table,stem_table,args.bowls,args.source_aware,args.curves)
                    records.append(dict(size=size,char=char,axes=values,glyph=glyph,baseline_glyph=baseline,diagnostics=diagnostics,
                                        topology=list(topology(glyph,1)),baseline_topology=list(topology(baseline,1))))
                except Exception as error:records.append(dict(size=size,char=char,error=str(error)))
        errors=[r for r in records if 'error' in r]
        flags=[(r['size'],r['char'],r['baseline_topology'],r['topology']) for r in records
               if 'error' not in r and r['baseline_topology']!=r['topology']]
        summary=dict(source_adjusted=[(r['size'],r['char'],r['diagnostics']['source_constraints']['selected_shift_26_6']) for r in records if r.get('diagnostics',{}).get('source_constraints',{}).get('selected_shift_26_6')],
                     source_unresolved=[(r['size'],r['char'],r['diagnostics']['source_constraints']['selected']['defect_count']) for r in records if r.get('diagnostics',{}).get('source_constraints',{}).get('selected',{}).get('defect_count')],
                     bowl_topology_rejections=[(r['size'],r['char']) for r in records if 'bowl_topology_rejection' in r.get('diagnostics',{})],
                     bowl_anchor_rejections=[(r['size'],r['char']) for r in records if 'bowl_rejection' in r.get('diagnostics',{}).get('vertical_stems',{})],
                     curved_cases=sum(bool(r.get('diagnostics',{}).get('vertical_stems',{}).get('curved_sides')) for r in records),font=filename,cases=len(records),errors=len(errors),topology_changes=flags,
                     constrained=sum(r.get('diagnostics',{}).get('status')=='outline constrained' for r in records),
                     fallback=sum('fallback' in r.get('diagnostics',{}).get('status','') for r in records),
                     stems_constrained=sum(r.get('diagnostics',{}).get('vertical_stems',{}).get('status')=='stem outlines constrained' for r in records),
                     stem_fallbacks=[(r['size'],r['char'],r['diagnostics']['vertical_stems']['status']) for r in records if 'fallback' in r.get('diagnostics',{}).get('vertical_stems',{}).get('status','')])
        summaries.append(summary)
        evidence=dict(font_sha256=digest,versions={'freetype':ft.version(),'numpy':np.__version__},
                      source_hashes={p:hashlib.sha256((ROOT/'tools/font_probe'/p).read_bytes()).hexdigest()
                                     for p in ('paper_gridfit.py','run_paper_gridfit.py','stem_gridfit.py','bowl_gridfit.py','source_constraints.py','curve_gridfit.py')},
                      paper='https://lspwww.epfl.ch/publications/typography/frsa.pdf',
                      scope='Sections 5–6 outline constraints subset; automatic detection, clustering and solver are project choices; no local bitmap edits.',
                      baseline='stem constraints' if args.bowls else ('diagonal and symmetry constraints' if args.stems else 'native hints'),
                      bowl_constraints=args.bowls,source_aware=args.source_aware,curves=args.curves,
                      vertical_stem_constraints=args.stems,
                      width_tables=tables,summary=summary,records=records)
        (OUT/f'{filename}.json').write_text(json.dumps(evidence,indent=2)+'\n');sheet(records,filename)
        if args.stems:stem_comparison(records,filename,args.bowls)
        else:comparison(records,filename)
        print(json.dumps(summary),flush=True)
    (OUT/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    if args.bowls:prior_topology_review()
    if any(s['errors'] for s in summaries):raise SystemExit('calibration errors recorded')


if __name__=='__main__':main()
