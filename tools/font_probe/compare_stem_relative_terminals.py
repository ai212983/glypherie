"""All affected horizontal terminal extensions, with explicit metric replacement."""
from pathlib import Path
from collections import Counter
import json,html
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from shamir_geometry import from_font
from shamir_boundary import normalize_boundaries
from shamir_segment_fit import prepared_glyph
from stem_relative_terminals import fit
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from compare_diagonal_widths import build,metrics
from cross_section_widths import export_graph,system
from cumulative_hinter import validate_geometry
from outline_relationships import reversed_edges
from check_shamir_baseline import digest
HERE=Path(__file__).resolve().parent


def run():
    root=HERE/'out';out=root/'stem-relative-terminals-v1';out.mkdir(exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.glob('*.py')};rows=[];panels=[]
    for old in json.load(open(root/'cumulative-hinter-v6/report.json'))['cases']:
        key,ch=old['key'],old['char'];stem=f'{key}-u{ord(ch):04x}';size=int(key.rsplit('-',1)[1]);r=dict(key=key,char=ch);rows.append(r)
        if old['status']=='rejected':r['status']='upstream-rejected';continue
        paths=[root/d/(stem+'-after.ttf') for d in ['source-junctions-v1','curved-width-links-v2','round-symmetry-v4','component-symmetry-v2','cumulative-hinter-v6']]
        paths += [root/'cumulative-hinter-v6'/(stem+'-current.ttf'),root/'geometric-candidate-v3'/(key+'-candidate.ttf')]
        path=next(p for p in paths if p.exists());original=root/'shamir-representative-comparison'/(key+'-source.ttf');record_path=original.with_name(key+'-model.json')
        for p in (path,original,record_path):hashes[str(p.relative_to(HERE))]=digest(p)
        with TTFont(original) as f:normalize_boundaries(f,[ch]);m=from_font(f,ch,baseline=True)
        m['scale']=size/m['em'];face=ft.Face(str(path));q=coords(face,ch,size);before=render(face,ch,size,hinted=True)
        with TTFont(path) as f:
            p,e,t=f['glyf'][f.getBestCmap()[ord(ch)]].getCoordinates(f['glyf']);advance=f['hmtx'][f.getBestCmap()[ord(ch)]]
        try:
            g,_,_=prepared_glyph(m)
            if not np.array_equal(g.coordinates,p) or list(g.endPtsOfContours)!=list(e):raise ValueError('point mapping differs')
            after,audit=fit(m,q,old['audit']['ownership']);r['terminals']=audit
            if not audit:r['status']='no-change';continue
            validate_geometry(np.asarray(p)*m['scale'],after,'stem-relative terminal')
            if reversed_edges(np.asarray(p)*m['scale'],after,e,t):raise ValueError('cardinal edge inversion')
            record=json.load(open(record_path))['records'][ch];cs=record['graph']['constraints'];matrix,_=system(record['graph'],len(p),m['scale']);tips={a['tip'] for a in audit}
            released=[i for i,c in enumerate(cs) if c.get('metric') and abs(c['normal'][0])==1 and
                      tips.intersection([c['point'],*c.get('sources',[])])]
            if not released:raise ValueError('no outline dimension constraint identified')
            protected=[i for i,c in enumerate(cs) if (c.get('metric') or c['kind'].startswith('P')) and i not in released]
            residual=float(np.max(abs(matrix[protected]@(after-q).ravel()))) if protected else 0.
            if residual>1/64+1e-9:raise ValueError('other protected relationship changes')
            new,native=build(path,ch,size,p,export_graph(after,m['scale']),out/(stem+'-after.ttf'))
            if np.max(abs(native-after))>1/128+1e-9:raise ValueError('native coordinate mismatch')
            if metrics(pixels(new),native,np.asarray(p)*m['scale'])['white_counters']!=metrics(pixels(before),q,np.asarray(p)*m['scale'])['white_counters']:raise ValueError('counter topology changes')
            with TTFont(out/(stem+'-after.ttf')) as f:assert f['hmtx'][f.getBestCmap()[ord(ch)]]==advance
            delta=len(pixels(new)^pixels(before));r.update(status='changed' if delta else 'unchanged',changed_pixels=delta,released_constraints=[cs[i] for i in released],protected_change_px=residual)
            if delta:
                panel=comparison([before,new],['Current rendering','Stem-relative extension'],f'{key} {ch!r}')
                prepend_reference(face,ch,size,f'{key} {ch!r}',[before,new],panel).save(out/(stem+'.png'))
                panels.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(ch)}</h2><p>{delta} changed pixels. Compare terminal length and curve shape.</p><img src="{stem}.png"></section>')
        except (ValueError,AssertionError) as ex:r.update(status='held',reason=str(ex));(out/(stem+'-after.ttf')).unlink(missing_ok=True)
        (out/(stem+'.json')).write_text(json.dumps(r,indent=2)+'\n')
    assert all(digest(HERE/n)==h for n,h in hashes.items())
    counts=dict(Counter(r['status'] for r in rows));header='<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}</style><h1>Stem-relative terminal placement</h1><p>Right: experimental source extension from the supporting stem. Advance widths are preserved. All changed admitted glyphs are shown.</p><a href="diagnostics.html">Diagnostics</a>'
    (out/'index.html').write_text(header+''.join(panels));(out/'diagnostics.html').write_text(header+'<pre>'+html.escape(json.dumps([r for r in rows if r['status']=='held'],indent=2))+'</pre>')
    (out/'report.json').write_text(json.dumps(dict(summary=counts,cases=rows,inputs=hashes),indent=2)+'\n');print(counts)

if __name__=='__main__':run()
