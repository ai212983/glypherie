"""All admitted cumulative glyphs: generic axis and width-consistency experiment."""
from pathlib import Path
from collections import Counter
import json,html
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from axis_consistency import fit,mismatch
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from compare_diagonal_widths import build,metrics
from cross_section_widths import export_graph
from check_shamir_baseline import digest

HERE=Path(__file__).resolve().parent


def run():
    root=HERE/'out';out=root/'axis-consistency-v1';out.mkdir(exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    hashes={str(p.relative_to(HERE)):digest(p) for p in HERE.glob('*.py')}
    old=json.load(open(root/'cumulative-hinter-v6/report.json'))['cases'];owners={(r['key'],r['char']):r.get('audit',{}).get('ownership',[]) for r in old}
    rows=[];panels=[]
    for path in sorted((root/'cumulative-hinter-v7').glob('*-candidate.ttf')):
        hashes[str(path.relative_to(HERE))]=digest(path);key=path.stem.removesuffix('-candidate');size=int(key.rsplit('-',1)[1]);face=ft.Face(str(path))
        with TTFont(path) as f:
            for code,name in sorted(f.getBestCmap().items()):
                ch=chr(code);stem=f'{key}-u{code:04x}';q=coords(face,ch,size);before=render(face,ch,size,hinted=True);p,e,t=f['glyf'][name].getCoordinates(f['glyf']);scale=size/f['head'].unitsPerEm
                after,audit=fit(p,e,t,q,scale,lambda v:pixels(render(face,ch,size,hinted=True,points=v)),owners[key,ch]);row=dict(key=key,char=ch,**audit);rows.append(row)
                if audit['status']!='candidate':continue
                new,native=build(path,ch,size,p,export_graph(after,scale),out/(stem+'-after.ttf'))
                if metrics(pixels(new),native,np.asarray(p)*scale)['white_counters']!=metrics(pixels(before),q,np.asarray(p)*scale)['white_counters']:
                    row.update(status='held-topology');(out/(stem+'-after.ttf')).unlink();continue
                assert np.max(abs(native-after))<=1/128+1e-9
                assert mismatch(pixels(new),audit['axes'])==0
                with TTFont(out/(stem+'-after.ttf')) as saved:assert saved['hmtx'][name]==f['hmtx'][name]
                delta=len(pixels(new)^pixels(before));row['changed_pixels']=delta
                panel=comparison([before,new],['Integrated approved input','Geometry / raster symmetry'],f'{key} {ch!r}')
                prepend_reference(face,ch,size,f'{key} {ch!r}',[before,new],panel).save(out/(stem+'.png'))
                panels.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(ch)}</h2><p>{audit["kind"]}, {delta} changed pixels.</p><img loading="lazy" src="{stem}.png"></section>')
        print(key,flush=True)
    assert all(digest(HERE/n)==sha for n,sha in hashes.items())
    counts=dict(Counter(r['status'] for r in rows));(out/'report.json').write_text(json.dumps(dict(summary=counts,cases=rows,inputs=hashes),indent=2)+'\n')
    header='<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}</style><h1>Axis and stroke consistency</h1><p>All changed admitted cases. Source, approved input, experimental candidate. Human review pending.</p>'
    (out/'index.html').write_text(header+''.join(panels));(out/'diagnostics.html').write_text(header+'<pre>'+html.escape(json.dumps([r for r in rows if r['status'].startswith('held')],indent=2))+'</pre>');print(counts)

if __name__=='__main__':run()
