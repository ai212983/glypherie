"""Add repeated-component symmetry to the accepted v6 review specimen."""
from pathlib import Path
import json,html
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from repeated_component_symmetry import fit
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from compare_diagonal_widths import build
from cross_section_widths import export_graph
from cumulative_hinter import validate_geometry
from outline_relationships import reversed_edges
from check_shamir_baseline import digest
HERE=Path(__file__).resolve().parent


def run():
    previous=HERE/'out/cumulative-hinter-v6';out=HERE/'out/component-symmetry-v2';out.mkdir(exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.glob('*.py')}
    rows=[];panels=[];diagnostics=[]
    for old in json.load(open(previous/'report.json'))['cases']:
        key,ch=old['key'],old['char'];stem=f'{key}-u{ord(ch):04x}';size=int(key.rsplit('-',1)[1]);row=dict(key=key,char=ch);rows.append(row)
        if old['status']=='rejected':row['status']='upstream-rejected';diagnostics.append(row);continue
        path=previous/(stem+'-after.ttf')
        if not path.exists():path=previous/(stem+'-current.ttf')
        if not path.exists():path=HERE/'out/geometric-candidate-v3'/(key+'-candidate.ttf')
        hashes[str(path.relative_to(HERE))]=digest(path)
        face=ft.Face(str(path));q=coords(face,ch,size);before=render(face,ch,size,hinted=True)
        with TTFont(path) as f:
            p,e,t=f['glyf'][f.getBestCmap()[ord(ch)]].getCoordinates(f['glyf']);em=f['head'].unitsPerEm
        def raster(candidate,ids,factor):
            isolated=np.zeros_like(candidate);isolated[ids]=candidate[ids]*factor
            return pixels(render(face,ch,size*factor,points=isolated,hinted=False))
        after,audit=fit(p,q,e,t,em,size/em,pixels(before),old['audit']['ownership'],raster=raster)
        row['components']=audit
        if not audit:row['status']='no-match';continue
        try:
            validate_geometry(np.asarray(p)*size/em,after,'component coordination')
            if reversed_edges(np.asarray(p)*size/em,after,e,t):raise ValueError('cardinal edge inversion')
            if np.array_equal(q,after):glyph=before
            else:
                glyph,native=build(path,ch,size,p,export_graph(after,size/em),out/(stem+'-after.ttf'))
                assert np.max(abs(native-after))<=1/128+1e-9
            delta=len(pixels(glyph)^pixels(before));row.update(status='changed' if delta else 'unchanged',changed_pixels=delta)
            panel=comparison([before,glyph],['Reviewed v6 specimen','Shared component shape and phase'],f'{key} {ch!r}')
            prepend_reference(face,ch,size,f'{key} {ch!r}',[before,glyph],panel).save(out/(stem+'.png'))
            if delta:panels.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(ch)}</h2><p>Compare repeated shapes, width, and alignment; {delta} changed pixels.</p><img src="{stem}.png"></section>')
        except (ValueError,AssertionError) as exc:row.update(status='held',reason=str(exc));diagnostics.append(row)
        (out/(stem+'.json')).write_text(json.dumps(row,indent=2)+'\n')
    assert all(digest(HERE/n)==h for n,h in hashes.items())
    header='<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}</style><h1>Repeated-component symmetry experiment</h1><p>Only horizontally or vertically repeated source contours. Existing identical bitmaps and owned coordinates are retained. This is a review candidate.</p><p><a href="diagnostics.html">Automated diagnostics</a></p>'
    (out/'index.html').write_text(header+''.join(panels))
    (out/'diagnostics.html').write_text(header+'<pre>'+html.escape(json.dumps(diagnostics,indent=2))+'</pre>')
    (out/'report.json').write_text(json.dumps(dict(cases=rows,inputs=hashes),indent=2)+'\n')
    print([(r['key'],r['char'],r.get('changed_pixels')) for r in rows if r['status']=='changed'])

if __name__=='__main__':run()
