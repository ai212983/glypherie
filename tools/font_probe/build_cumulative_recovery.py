"""Integrate the approved final pass, export complete fonts, and verify the specimen."""
from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
import html,json
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from cumulative_hinter import finalize
from cumulative_inputs import resolve,CHECKPOINTS
from audit_terminal_coverage import coords
from cross_section_widths import export_graph
from shamir_baseline_solver import compile_baseline
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from compare_diagonal_widths import metrics
from check_shamir_baseline import digest

HERE=Path(__file__).resolve().parent


def run():
    root=HERE/'out';out=root/'cumulative-hinter-v7';out.mkdir(exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    inputs={str(p.relative_to(HERE)):digest(p) for p in HERE.glob('*.py')}
    def track(p):inputs[str(p.relative_to(HERE))]=digest(p);return p
    previous=json.loads(track(root/'cumulative-hinter-v6/report.json').read_text())['cases']
    approved_dir=root/'curved-stroke-recovery-v1'
    approved=json.loads(track(approved_dir/'report.json').read_text())['cases']
    accepted={(r['key'],r['char']):r for r in approved}
    for checkpoint in CHECKPOINTS:track(root/checkpoint/'report.json')
    groups=defaultdict(list)
    for r in previous:groups[r['key']].append(r)
    rows=[];pages=[];changes=[];failures=[]
    for key,group in sorted(groups.items()):
        size=int(key.rsplit('-',1)[1]);base=track(root/'geometric-candidate-v3'/(key+'-candidate.ttf'))
        expected={};sections=[]
        with TTFont(base) as combined:
            cmap=combined.getBestCmap();included=set()
            for old in group:
                ch=old['char'];stem=f'{key}-u{ord(ch):04x}';row=dict(key=key,char=ch);rows.append(row)
                if old['status']=='rejected':
                    row.update(status='upstream-rejected',reason=old.get('reason','upstream rejected'));failures.append(row);continue
                path=track(resolve(root,key,ch));face=ft.Face(str(path));q=coords(face,ch,size);before=render(face,ch,size,hinted=True)
                with TTFont(path) as source:
                    name=source.getBestCmap()[ord(ch)];glyph=source['glyf'][name]
                    p,e,t=glyph.getCoordinates(source['glyf']);em=source['head'].unitsPerEm
                    assert em==combined['head'].unitsPerEm
                    fitted,audit=finalize(p,e,t,q,size/em,old['audit'])
                    reference=accepted[key,ch]
                    approved_path=approved_dir/(stem+'-after.ttf')
                    if reference['status'] in ('changed','unchanged'):
                        if not approved_path.exists():raise ValueError(f'missing approved output: {stem}')
                        reference_face=ft.Face(str(track(approved_path)))
                    elif reference['status']=='unaffected':reference_face=face
                    else:raise ValueError(f'unexpected approved status: {reference["status"]}')
                    reference_q=coords(reference_face,ch,size);reference_ink=pixels(render(reference_face,ch,size,hinted=True))
                    if np.max(abs(fitted-reference_q))>1/128+1e-9:raise ValueError(f'approved geometry drift: {stem}')
                    assembly,_=compile_baseline(export_graph(fitted,size/em),p,size,em)
                    if glyph.isComposite():raise ValueError(f'composite export requires explicit component mapping: {stem}')
                    compiled=deepcopy(glyph);compiled.program=Program();compiled.program.fromAssembly(assembly)
                    combined['glyf'][cmap[ord(ch)]]=compiled
                    combined['hmtx'][cmap[ord(ch)]]=source['hmtx'][name]
                    included.add(ord(ch))
                    expected[ch]=(fitted,reference_ink,before,np.asarray(p)*size/em,source['hmtx'][name],audit,path)
            # Unsupported cases are absent from the exported character map.
            for table in combined['cmap'].tables:
                if table.isUnicode():table.cmap={c:n for c,n in table.cmap.items() if c in included}
            combined['maxp'].maxStackElements=max(combined['maxp'].maxStackElements,16)
            target=out/(key+'-candidate.ttf');combined.save(target)
        face=ft.Face(str(target))
        with TTFont(target) as exported:
            assert set(exported.getBestCmap())==included
            for row in [r for r in rows if r['key']==key and r.get('status')!='upstream-rejected']:
                ch=row['char'];stem=f'{key}-u{ord(ch):04x}'
                fitted,reference_ink,before,source,advance,audit,path=expected[ch]
                actual=coords(face,ch,size);after=render(face,ch,size,hinted=True);ink=pixels(after)
                assert np.max(abs(actual-fitted))<=1/128+1e-9, stem
                assert ink==reference_ink, f'approved bitmap drift: {stem}'
                assert exported['hmtx'][exported.getBestCmap()[ord(ch)]]==advance
                assert metrics(ink,actual,source)['white_counters']==metrics(pixels(before),actual,source)['white_counters']
                delta=len(ink^pixels(before));row.update(status='changed' if delta else 'retained',changed_pixels=delta,
                    approved_bitmap_match=True,input=str(path.relative_to(root)),audit=audit)
                panel=comparison([before,after],['Previous cumulative input','Integrated approved pipeline'],f'{key} {ch!r}')
                prepend_reference(face,ch,size,f'{key} {ch!r}',[before,after],panel).save(out/(stem+'.png'))
                section=f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(ch)}</h2><img loading="lazy" src="{stem}.png"></section>'
                sections.append(section)
                if delta:changes.append(section)
        (out/(key+'.html')).write_text(header()+''.join(sections));pages.append(f'<li><a href="{key}.html">{key}</a></li>')
        print(key,len(expected),'verified',flush=True)
    assert all(digest(HERE/n)==sha for n,sha in inputs.items()),'inputs changed during generation'
    counts=dict(Counter(r['status'] for r in rows))
    (out/'report.json').write_text(json.dumps(dict(summary=counts,cases=rows,inputs=inputs),indent=2)+'\n')
    (out/'index.html').write_text(header()+'<p>832 admitted glyphs match the approved cumulative reference. Unresolved cases are excluded from font character maps.</p><ul>'+''.join(pages)+'</ul>')
    (out/'changes.html').write_text(header()+''.join(changes))
    (out/'diagnostics.html').write_text(header()+'<pre>'+html.escape(json.dumps(failures,indent=2))+'</pre>')
    print(counts)


def header():
    return '<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}</style><h1>Integrated Python hinter</h1><p><a href="index.html">Full specimen</a> · <a href="changes.html">Seven approved changes</a> · <a href="diagnostics.html">Unresolved cases</a></p>'

if __name__=='__main__':run()
