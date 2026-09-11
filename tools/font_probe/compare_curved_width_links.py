"""Coverage review of geometry-supported curved width links."""
from pathlib import Path
from collections import Counter
import json,html
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from curved_width_links import fit,detect
from shamir_geometry import from_font
from shamir_segment_fit import prepared_glyph
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


def run(*, reconstruct_curves=False, source_junctions=False):
    base=HERE/'out/cumulative-hinter-v6';out=HERE/('out/source-junctions-v1' if source_junctions else 'out/curved-width-links-v2' if reconstruct_curves else 'out/curved-width-links-v1');out.mkdir(exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.glob('*.py')};rows=[];panels=[];diagnostics=[]
    for old in json.load(open(base/'report.json'))['cases']:
        key,ch=old['key'],old['char'];stem=f'{key}-u{ord(ch):04x}';size=int(key.rsplit('-',1)[1]);row=dict(key=key,char=ch);rows.append(row)
        if old['status']=='rejected':row['status']='upstream-rejected';continue
        choices=[HERE/'out/round-symmetry-v4'/(stem+'-after.ttf'),HERE/'out/component-symmetry-v2'/(stem+'-after.ttf'),base/(stem+'-after.ttf'),base/(stem+'-current.ttf'),HERE/'out/geometric-candidate-v3'/(key+'-candidate.ttf')]
        path=next(p for p in choices if p.exists());hashes[str(path.relative_to(HERE))]=digest(path)
        face=ft.Face(str(path));before=render(face,ch,size,hinted=True);q=coords(face,ch,size)
        with TTFont(path) as f:
            p,e,t=f['glyf'][f.getBestCmap()[ord(ch)]].getCoordinates(f['glyf']);em=f['head'].unitsPerEm
            model=from_font(f,ch,baseline=True);model['scale']=size/em
        if source_junctions:
            original=HERE/'out/shamir-representative-comparison'/(key+'-source.ttf')
            hashes[str(original.relative_to(HERE))]=digest(original)
            with TTFont(original) as f:
                from shamir_boundary import normalize_boundaries
                normalize_boundaries(f,[ch])
                model=from_font(f,ch,baseline=True)
            model.update(scale=size/em,source_junctions=True)
        # Defer disconnected counter-bearing components (including percentages).
        # Recognition remains general; this integration pass handles one outline component.
        from repeated_rings import contours
        cs=contours(np.asarray(p),t,e)
        outer_count=sum(not any(j!=i and b['poly'].contains(a['poly']) for j,b in enumerate(cs)) for i,a in enumerate(cs))
        if outer_count!=1:row['status']='deferred-disconnected';continue
        record_path=HERE/'out/shamir-representative-comparison'/(key+'-model.json');hashes[str(record_path.relative_to(HERE))]=digest(record_path)
        record=json.load(open(record_path))['records'][ch]
        try:
            if source_junctions and not any(f['new'] for f in detect(model)):
                row['status']='no-match';continue
            prepared,_,_=prepared_glyph(model)
            if not np.array_equal(prepared.coordinates,p) or list(prepared.endPtsOfContours)!=list(e):
                raise ValueError('prepared point mapping differs')
            after,audit=fit(model,q,old['audit']['ownership'],reconstruct_curves=reconstruct_curves);row['audit']=audit
            if not audit['new_pairs']:row['status']='no-match';continue
            if not audit['links']:row['status']='already-consistent';continue
            validate_geometry(np.asarray(p)*size/em,after,'curved width links')
            if reversed_edges(np.asarray(p)*size/em,after,e,t):raise ValueError('cardinal edge inversion')
            matrix,_=system(record['graph'],len(p),size/em)
            ids=[i for i,c in enumerate(record['graph']['constraints']) if c.get('metric') or c['kind'].startswith('P')]
            residual=float(np.max(abs(matrix[ids]@(after-q).ravel()))) if ids else 0.
            if residual>1/64+1e-9:raise ValueError('protected metric/parameter changes')
            candidate,native=build(path,ch,size,p,export_graph(after,size/em),out/(stem+'-after.ttf'))
            oracle=float(np.max(abs(native-after)))
            if oracle>1/128+1e-9:raise ValueError('native coordinate mismatch')
            a=metrics(pixels(before),q,np.asarray(p)*size/em);b=metrics(pixels(candidate),native,np.asarray(p)*size/em)
            if a['white_counters']!=b['white_counters']:raise ValueError('counter topology changes')
            if source_junctions:
                approved=HERE/'out/curved-width-links-v2'/(stem+'-after.ttf')
                if approved.exists():
                    hashes[str(approved.relative_to(HERE))]=digest(approved)
                    before=render(ft.Face(str(approved)),ch,size,hinted=True)
            delta=len(pixels(before)^pixels(candidate));row.update(status='changed' if delta else 'unchanged',changed_pixels=delta,native_error_px=oracle,protected_change_px=residual)
            if delta:
                gs=[before,candidate];labels=['Approved/current rendering','Original geometry + junctions' if source_junctions else 'Bounded source curves' if reconstruct_curves else 'Linked curved widths']
                prior=HERE/'out/curved-width-links-v1'/(stem+'-after.ttf')
                if reconstruct_curves and not source_junctions and prior.exists():
                    hashes[str(prior.relative_to(HERE))]=digest(prior)
                    gs.insert(1,render(ft.Face(str(prior)),ch,size,hinted=True));labels.insert(1,'Previous width candidate')
                panel=comparison(gs,labels,f'{key} {ch!r}')
                prepend_reference(face,ch,size,f'{key} {ch!r}',gs,panel).save(out/(stem+'.png'))
                panels.append((stem,f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(ch)}</h2><p>{delta} changed pixels. Compare side weight, curvature and counter shape.</p><img loading="lazy" src="{stem}.png"></section>'))
        except (ValueError,AssertionError) as exc:
            row.update(status='held',reason=str(exc));diagnostics.append(row)
            (out/(stem+'-after.ttf')).unlink(missing_ok=True)
            prior=HERE/'out/curved-width-links-v1'/(stem+'-after.ttf')
            if reconstruct_curves and not source_junctions and prior.exists():
                # Show the retained result, not an inadmissible proposed outline.
                panel=comparison([before,before],['Current rendering','Retained: curve conflict'],f'{key} {ch!r}')
                prepend_reference(face,ch,size,f'{key} {ch!r}',[before,before],panel).save(out/(stem+'.png'))
                panels.append((stem,f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(ch)}</h2><p>Current retained: {html.escape(str(exc))}. The previous width change is withheld.</p><img loading="lazy" src="{stem}.png"></section>'))
        (out/(stem+'.json')).write_text(json.dumps(row,indent=2)+'\n')
        if len(rows)%40==0:print(len(rows),dict(Counter(r['status'] for r in rows)),flush=True)
    assert all(digest(HERE/n)==h for n,h in hashes.items())
    panels.sort(key=lambda x:(x[0] not in ('literata-14-u0061','literata-14-u0030','literata-16-u0070'),x[0]))
    header='<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{margin:30px 0}</style><h1>Curved stroke width links</h1><p>Source reference, current rendering, and width-link candidate. All changed, admitted cases are below; inspect side weight, curve shape, counters and transitions. This experiment uses geometry only. Disconnected components are deferred.</p><p><a href="diagnostics.html">Automated diagnostics</a></p>'
    (out/'index.html').write_text(header+''.join(p for _,p in panels))
    (out/'diagnostics.html').write_text(header+'<pre>'+html.escape(json.dumps(diagnostics,indent=2))+'</pre>')
    summary=dict(Counter(r['status'] for r in rows));(out/'report.json').write_text(json.dumps(dict(summary=summary,cases=rows,inputs=hashes),indent=2)+'\n')
    print(summary,flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--reconstruct-curves',action='store_true')
    parser.add_argument('--source-junctions',action='store_true');args=parser.parse_args()
    run(reconstruct_curves=args.reconstruct_curves or args.source_junctions,source_junctions=args.source_junctions)
