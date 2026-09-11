"""Compare our support-first solver across the exported corpus; references read-only."""
import json,html,shutil
from collections import Counter
from pathlib import Path
import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from shamir_baseline_solver import compile_baseline
from audit_terminal_coverage import coords
from shared_stem_hinter import fit,Unsupported
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from check_shamir_baseline import digest
HERE=Path(__file__).resolve().parent


def run(*, coordinate=False):
    out=HERE/('out/shared-stem-hinter-v2' if coordinate else 'out/shared-stem-hinter-v1');out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    sources=['shared_stem_hinter.py','stem_widths.py','feature_coordination.py','compare_shared_stem_hinter.py','shamir_baseline_solver.py']
    for name in sources:shutil.copy2(HERE/name,out/name)
    inputs={};rows=[];panels=[]
    for path in sorted((HERE/'out/geometric-candidate-v3').glob('*-candidate.ttf')):
        key=path.stem.removesuffix('-candidate');size=int(key.rsplit('-',1)[1]);ref=HERE/'out/shamir-representative-comparison'/f'{key}-experiment.ttf';mp=ref.with_name(f'{key}-model.json')
        for q in (path,ref,mp):inputs[str(q.relative_to(HERE))]=digest(q)
        model=json.loads(mp.read_text());face=ft.Face(str(ref));current=ft.Face(str(path))
        with TTFont(path) as repertoire,TTFont(ref) as font:
            for code in sorted(repertoire.getBestCmap()):
                char=chr(code);stem=f'{key}-u{code:04x}';record=model['records'][char]
                p,e,t=font['glyf'][font.getBestCmap()[code]].getCoordinates(font['glyf']);row=dict(key=key,char=char);rows.append(row)
                try:fitted,audit=fit(p,record,size,font['head'].unitsPerEm,coordinate=coordinate,ends=e,flags=t)
                except Unsupported as exc:row.update(status='held',reason=str(exc));continue
                if fitted is None:row.update(status='unaffected');continue
                assert np.isfinite(fitted).all()
                (out/f'{stem}.json').write_text(json.dumps(audit,indent=2)+'\n');np.save(out/f'{stem}-points.npy',fitted)
                assembly,metadata=compile_baseline(audit['graph'],p,size,font['head'].unitsPerEm)
                with TTFont(ref) as export:
                    glyph=export['glyf'][export.getBestCmap()[code]]
                    glyph.program=Program();glyph.program.fromAssembly(assembly)
                    export['maxp'].maxStackElements=max(export['maxp'].maxStackElements,16)
                    target=out/f'{stem}.ttf';export.save(target)
                native=ft.Face(str(target));actual=coords(native,char,size)
                assert np.max(abs(actual-np.asarray(metadata['native_points_px'])))<1e-8
                with TTFont(target) as exported:
                    original=font['glyf'][font.getBestCmap()[code]].getCoordinates(font['glyf'])
                    recovered=exported['glyf'][exported.getBestCmap()[code]].getCoordinates(exported['glyf'])
                    assert all(list(a)==list(b) for a,b in zip(original,recovered))
                before_path=HERE/'out/shared-stem-hinter-v1'/f'{stem}.ttf'
                if coordinate and before_path.exists():
                    inputs[str(before_path.relative_to(HERE))]=digest(before_path)
                    current_case=ft.Face(str(before_path))
                else:current_case=current
                old=render(current_case,char,size,hinted=True);new=render(native,char,size,hinted=True)
                glyphs=[old,new];labels=['Previous own-hinter experiment' if coordinate else 'Current uniform candidate','Coordinated features' if coordinate else 'Our support-first experiment']
                approved=HERE/'out/vtt-stem-widths-v1'/f'{stem}-after.ttf'
                if approved.exists():
                    inputs[str(approved.relative_to(HERE))]=digest(approved)
                    glyphs.append(render(ft.Face(str(approved)),char,size,hinted=True));labels.append('Approved VTT reference')
                else:glyphs.append(None);labels.append('VTT reference unavailable')
                diagnostics=audit['diagnostics']
                for measured in diagnostics['stems']:
                    assert abs(measured['measured_width']-measured['target_width'])<1e-8
                    assert measured['side_spread']<1e-8
                if diagnostics['reflection_residual_px'] is not None:
                    assert diagnostics['reflection_residual_px']<1e-8
                    axis=audit['symmetry']['axis_px'];ink=pixels(new)
                    reflected={(int(round(2*axis-1-x)),y) for x,y in ink}
                    diagnostics['asymmetric_bitmap_pixels']=len(ink^reflected)
                    assert diagnostics['asymmetric_bitmap_pixels']==0
                row['diagnostics']=diagnostics
                delta=len(pixels(old)^pixels(new));row.update(status='changed' if delta else 'same-bitmap',changed_pixels=delta,max_movement_px=audit['max_movement_px'])
                panel=comparison(glyphs,labels,f'{key} {char!r}')
                prepend_reference(face,char,size,f'{key} {char!r}',glyphs,panel).save(out/f'{stem}.png')
                panels.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)}</h2><img src="{stem}.png"><p>{delta} pixels differ from before. <a href="{stem}.json">Equations and decisions</a></p></section>')
    assert all(digest(HERE/n)==h for n,h in inputs.items())
    counts=dict(Counter(r['status'] for r in rows))
    (out/'report.json').write_text(json.dumps(dict(counts=counts,cases=rows,inputs=inputs,sources={n:digest(HERE/n) for n in sources}),indent=2)+'\n')
    held=''.join(f'<li>{r["key"]} {html.escape(r["char"])}: {html.escape(r["reason"])}</li>' for r in rows if r['status']=='held')
    (out/'index.html').write_text('<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{margin-bottom:30px}</style><h1>Our shared-stem hinter experiment</h1><p>Source, before, own-hinter candidate, approved reference where available. No VTT compiler or VTT movement is used in the candidate. Later uniform serif/terminal corrections are omitted to isolate support fitting. Images use the common monochrome scan converter.</p><p>'+html.escape(str(counts))+'</p>'+''.join(panels)+'<h2>Held proposals</h2><ul>'+held+'</ul>')
    print(counts)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--coordinate',action='store_true')
    run(coordinate=parser.parse_args().coordinate)
