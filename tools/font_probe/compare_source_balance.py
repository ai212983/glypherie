"""Current, source-relative stroke balance, and strict bitmap reference."""
from pathlib import Path
import json,html
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from source_relative_balance import fit
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from compare_diagonal_widths import build,metrics
from cross_section_widths import export_graph
from cumulative_hinter import validate_geometry
from outline_relationships import reversed_edges
from round_component_fit import mismatch
from check_shamir_baseline import digest
HERE=Path(__file__).resolve().parent


def strict_reference(glyph):
    """Diagnostic majority projection; never exported as font coordinates."""
    result=dict(glyph);w,h=glyph['width'],glyph['height'];original=glyph['pixels'];out=list(original)
    for y in range(h):
        for x in range(w):
            orbit={(x,y),(w-1-x,y),(x,h-1-y),(w-1-x,h-1-y)}
            out[y*w+x]=int(sum(bool(original[b*w+a]) for a,b in orbit)*2>=len(orbit))
    result['pixels']=out;return result


def run():
    base=HERE/'out/cumulative-hinter-v6';out=HERE/'out/source-balance-v2';out.mkdir(exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.glob('*.py')};rows=[];panels=[];diagnostics=[]
    for old in json.load(open(base/'report.json'))['cases']:
        key,ch=old['key'],old['char'];stem=f'{key}-u{ord(ch):04x}';size=int(key.rsplit('-',1)[1]);row=dict(key=key,char=ch);rows.append(row)
        if old['status']=='rejected':row['status']='upstream-rejected';continue
        choices=[HERE/'out/round-symmetry-v4'/(stem+'-after.ttf'),HERE/'out/component-symmetry-v2'/(stem+'-after.ttf'),base/(stem+'-after.ttf'),base/(stem+'-current.ttf'),HERE/'out/geometric-candidate-v3'/(key+'-candidate.ttf')]
        path=next(p for p in choices if p.exists());hashes[str(path.relative_to(HERE))]=digest(path)
        face=ft.Face(str(path));current=render(face,ch,size,hinted=True);q=coords(face,ch,size)
        with TTFont(path) as f:p,e,t=f['glyf'][f.getBestCmap()[ord(ch)]].getCoordinates(f['glyf']);em=f['head'].unitsPerEm
        model=HERE/'out/shamir-representative-comparison'/(key+'-model.json');hashes[str(model.relative_to(HERE))]=digest(model);record=json.load(open(model))['records'][ch]
        if not mismatch(pixels(current),0) and not mismatch(pixels(current),1):row['status']='already-symmetric';continue
        try:
            after,audit=fit(p,q,e,t,size/em,em,record,old['audit']['ownership'])
            if audit['status']=='no-match':row['status']='no-match';continue
            validate_geometry(np.asarray(p)*size/em,after,'source-relative balance')
            if reversed_edges(np.asarray(p)*size/em,after,e,t):raise ValueError('cardinal edge inversion')
            balanced,native=build(path,ch,size,p,export_graph(after,size/em),out/(stem+'-after.ttf'))
            assert np.max(abs(native-after))<=1/128+1e-9
            before_metrics=metrics(pixels(current),q,np.asarray(p)*size/em);after_metrics=metrics(pixels(balanced),after,np.asarray(p)*size/em)
            if after_metrics['white_counters']!=before_metrics['white_counters']:raise ValueError('counter topology changes')
            row.update(status='changed' if pixels(current)!=pixels(balanced) else 'unchanged',audit=audit,changed_pixels=len(pixels(current)^pixels(balanced)))
            strict=strict_reference(current)
            row['reflection']={label:[mismatch(pixels(g),axis) for axis in (0,1)] for label,g in [('current',current),('balanced',balanced),('strict',strict)]}
            row['strict_changed_pixels']=len(pixels(strict)^pixels(current))
            panel=comparison([current,balanced,strict],['Current rendering','Source-relative stroke balance','Strict bitmap reflection (diagnostic)'],f'{key} {ch!r}')
            prepend_reference(face,ch,size,f'{key} {ch!r}',[current,balanced,strict],panel).save(out/(stem+'.png'))
            panels.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(ch)}</h2><p>Compare weight and counter spacing against source character. Balanced: {row["changed_pixels"]} changed pixels. Strict reflection is a bitmap diagnostic, not a font candidate.</p><img src="{stem}.png"></section>')
        except (ValueError,AssertionError) as exc:row.update(status='held',reason=str(exc));diagnostics.append(row)
        (out/(stem+'.json')).write_text(json.dumps(row,indent=2)+'\n')
    assert all(digest(HERE/n)==h for n,h in hashes.items())
    header='<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{margin:30px 0}</style><h1>Source asymmetry and stroke balance</h1><p>Single-counter experiment. Metric and owned coordinates retained; opposing stroke differences target the source difference, not zero. Strict reflection majority-projects current pixels across both axes (ties filled); it is diagnostic only.</p><p><a href="diagnostics.html">Automated diagnostics</a></p>'
    (out/'index.html').write_text(header+''.join(panels));(out/'diagnostics.html').write_text(header+'<pre>'+html.escape(json.dumps(diagnostics,indent=2))+'</pre>')
    (out/'report.json').write_text(json.dumps(dict(cases=rows,inputs=hashes),indent=2)+'\n')
    print([(r['key'],r['char'],r.get('changed_pixels')) for r in rows if r['status']=='changed'])

if __name__=='__main__':run()
