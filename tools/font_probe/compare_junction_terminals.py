"""Cumulative all-case comparison of bar placement and curved cap recovery."""
from pathlib import Path
from collections import Counter
import json,html
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from junction_terminal_fit import fit
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from compare_diagonal_widths import build,metrics
from cross_section_widths import export_graph
from cumulative_hinter import validate_geometry
from outline_relationships import reversed_edges


def run(fitter=fit, output='junction-terminals-v2', label='Paired curved-cap candidate'):
    root=Path(__file__).resolve().parent/'out';out=root/output;out.mkdir(exist_ok=True)
    rows=[];panels=[]
    for stale in out.glob('*.png'):stale.unlink()
    for stale in out.glob('*-after.ttf'):stale.unlink()
    for old in json.load(open(root/'cumulative-hinter-v6/report.json'))['cases']:
        key,ch=old['key'],old['char'];size=int(key.rsplit('-',1)[1]);stem=f'{key}-u{ord(ch):04x}'
        row=dict(key=key,char=ch);rows.append(row)
        if old['status']=='rejected':row['status']='upstream-rejected';continue
        paths=[root/d/(stem+'-after.ttf') for d in ['stem-relative-terminals-v1','source-junctions-v1','curved-width-links-v2','round-symmetry-v4','component-symmetry-v2','cumulative-hinter-v6']]
        paths += [root/'cumulative-hinter-v6'/(stem+'-current.ttf'),root/'geometric-candidate-v3'/(key+'-candidate.ttf')]
        path=next(p for p in paths if p.exists());face=ft.Face(str(path));q=coords(face,ch,size);before=render(face,ch,size,hinted=True)
        with TTFont(path) as f:
            name=f.getBestCmap()[ord(ch)];p,e,t=f['glyf'][name].getCoordinates(f['glyf']);scale=size/f['head'].unitsPerEm;advance=f['hmtx'][name]
        try:
            after,audit=fitter(p,e,t,q,scale,old['audit'].get('order_relations',[]),old['audit'].get('ownership',[]));row['audit']=audit
            if not audit:row['status']='unaffected';continue
            validate_geometry(np.asarray(p)*scale,after,'junction and terminal')
            if reversed_edges(np.asarray(p)*scale,after,e,t):raise ValueError('cardinal edge inversion')
            new,native=build(path,ch,size,p,export_graph(after,scale),out/(stem+'-after.ttf'))
            if np.max(abs(native-after))>1/128+1e-9:raise ValueError('native coordinate mismatch')
            for cap in audit:
                if cap['kind']=='curved-cap':
                    a,b=cap['endpoints'];axis=cap['thickness_axis']
                    if abs((native[b,axis]-native[a,axis])-(q[b,axis]-q[a,axis]))>1/64+1e-9:raise ValueError('native cap thickness changed')
            for stroke in audit:
                if stroke['kind']=='whole-curved-stroke':
                    ids=stroke['attachments'];axis=stroke['thickness_axis'];ext=stroke['extrema']
                    if np.max(abs(native[ids]-q[ids]))>1/64+1e-9:raise ValueError('native stem attachment changed')
                    if np.max(abs(native[ext,axis]-q[ext,axis]))>1/64+1e-9:raise ValueError('native curve height changed')
            if metrics(pixels(new),native,np.asarray(p)*scale)['white_counters']!=metrics(pixels(before),q,np.asarray(p)*scale)['white_counters']:raise ValueError('counter topology change')
            with TTFont(out/(stem+'-after.ttf')) as f:assert f['hmtx'][name]==advance
            delta=len(pixels(new)^pixels(before));row.update(status='changed' if delta else 'unchanged',changed_pixels=delta,input=str(path.relative_to(root)))
            if delta:
                panel=comparison([before,new],['Previous cumulative input',label],f'{key} {ch!r}')
                prepend_reference(face,ch,size,f'{key} {ch!r}',[before,new],panel).save(out/(stem+'.png'))
                panels.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(ch)}</h2><img src="{stem}.png"></section>')
        except (ValueError,AssertionError) as ex:row.update(status='held',reason=str(ex));(out/(stem+'-after.ttf')).unlink(missing_ok=True)
    counts=dict(Counter(r['status'] for r in rows));(out/'report.json').write_text(json.dumps(dict(summary=counts,cases=rows),indent=2)+'\n')
    (out/'index.html').write_text('<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}</style><h1>Bar and curved terminal correction</h1><p>Smooth source, previous cumulative input, experimental correction. All changed admitted cases; human review pending.</p>'+''.join(panels));print(counts)

if __name__=='__main__':run()
