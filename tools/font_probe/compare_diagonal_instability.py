"""Conditioning audit across verified glyphs; isolated source-model comparison."""
import json,html,shutil
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from diagonal_instability import cardinal_override
from shamir_baseline_solver import evaluate_baseline
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from check_shamir_baseline import digest
HERE=Path(__file__).resolve().parent


def run():
    out=HERE/'out/diagonal-instability-v1';out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    sources=['diagonal_instability.py','compare_diagonal_instability.py','shamir_baseline_solver.py']
    for name in sources:shutil.copy2(HERE/name,out/name)
    rows=[];sections=[];inputs={}
    for path in sorted((HERE/'out/geometric-candidate-v3').glob('*-candidate.ttf')):
        key=path.stem.removesuffix('-candidate');size=int(key.rsplit('-',1)[1]);ref=HERE/'out/shamir-representative-comparison'/f'{key}-experiment.ttf'
        mp=ref.with_name(f'{key}-model.json');model=json.loads(mp.read_text());font=TTFont(ref);em=font['head'].unitsPerEm
        uniform=TTFont(path);old=ft.Face(str(ref));current=ft.Face(str(path))
        for p in (path,ref,mp):inputs[str(p.relative_to(HERE))]=digest(p)
        for code in sorted(uniform.getBestCmap()):
            char=chr(code);record=model['records'][char];source,ends,flags=font['glyf'][font.getBestCmap()[code]].getCoordinates(font['glyf'])
            graph=record['graph'];changed,audit=cardinal_override(graph,source)
            row=dict(key=key,char=char,audit=audit,status='unchanged');rows.append(row)
            if not audit:continue
            if any(a['status']=='held' for a in audit):
                row.update(status='held',reason='one or more unsafe pairs outside override scope');continue
            baseline,_=evaluate_baseline(graph,source,size,em)
            expected=np.array(graph['baseline_execution']['model_points_px'])
            assert np.max(abs(baseline-expected))<1e-6
            fitted,_=evaluate_baseline(changed,source,size,em)
            # All replacements depend only on the already-scheduled width parent.
            assert np.isfinite(fitted).all()
            row.update(status='experimental',max_movement_before_px=float(np.max(np.linalg.norm(baseline-np.array(source)*size/em,axis=1))),
                       max_movement_after_px=float(np.max(np.linalg.norm(fitted-np.array(source)*size/em,axis=1))))
            glyphs=[render(current,char,size,hinted=True),render(old,char,size,points=baseline,hinted=True),render(old,char,size,points=fitted,hinted=True)]
            row['changed_pixels']=len(pixels(glyphs[1])^pixels(glyphs[2]))
            stem=f'{key}-u{code:04x}';np.save(out/f'{stem}-points.npy',fitted)
            panel=comparison(glyphs,['Current uniform candidate','Frozen model (unsafe)','Explicit cardinal experiment'],f'{key} {char!r}')
            prepend_reference(old,char,size,f'{key} {char!r}',glyphs,panel).save(out/f'{stem}.png')
            sections.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)}</h2><img src="{stem}.png"><p>{len(audit)} unsafe pair(s); {row["changed_pixels"]} pixels changed from frozen model.</p></section>')
        uniform.close();font.close()
    assert all(digest(HERE/n)==h for n,h in inputs.items())
    (out/'report.json').write_text(json.dumps(dict(inputs=inputs,sources={n:digest(HERE/n) for n in sources},cases=rows),indent=2)+'\n')
    held=''.join(f'<li>{r["key"]} {html.escape(r["char"])}: {r["reason"]}</li>' for r in rows if r['status']=='held')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}</style><h1>Unstable diagonal constraints</h1><p>Source, current uniform candidate, frozen model, explicit cardinal movement. The VTT-derived guard flags the frozen model; it has no automatic repair. The last column releases the conflicting alignment and preserves the source offset from the width parent on the other axis. This is a documented experimental override, not a full VTT port. Later uniform corrections are omitted to isolate the model change.</p><h2>Held cases</h2><ul>'+held+'</ul>'+''.join(sections))
    from collections import Counter
    print(Counter(r['status'] for r in rows))

if __name__=='__main__':run()
