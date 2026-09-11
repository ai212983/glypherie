"""Broaden only diagonal width classes; audit every generated specimen."""
import copy,json,html,shutil
from collections import Counter
from pathlib import Path
import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from feature_coordination import shared_diagonal_widths
from shamir_baseline_solver import evaluate_baseline,compile_baseline
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from audit_terminal_coverage import coords
from check_shamir_baseline import digest
HERE=Path(__file__).resolve().parent


def regions(cells):
    remaining=set(cells);count=0
    while remaining:
        count+=1;todo=[remaining.pop()]
        while todo:
            x,y=todo.pop()
            for q in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if q in remaining:remaining.remove(q);todo.append(q)
    return count


def metrics(ink,points,source):
    xs,ys=zip(*ink) if ink else ([0],[0])
    box={(x,y) for x in range(min(xs)-1,max(xs)+2) for y in range(min(ys)-1,max(ys)+2)}
    return dict(black_components=regions(ink),white_counters=max(0,regions(box-ink)-1),
                max_source_movement_px=float(np.max(np.linalg.norm(points-source,axis=1))),
                bbox=[min(xs),min(ys),max(xs)+1,max(ys)+1])


def build(ref,char,size,p,graph,target):
    fitted,meta=evaluate_baseline(graph,p,size,TTFont(ref)['head'].unitsPerEm)
    assembly,_=compile_baseline(graph,p,size,TTFont(ref)['head'].unitsPerEm)
    with TTFont(ref) as f:
        name=f.getBestCmap()[ord(char)];original=f['glyf'][name].getCoordinates(f['glyf'])
        f['glyf'][name].program=Program();f['glyf'][name].program.fromAssembly(assembly)
        f['maxp'].maxStackElements=max(f['maxp'].maxStackElements,16);f.save(target)
    face=ft.Face(str(target));actual=coords(face,char,size)
    assert np.max(abs(actual-np.array(meta['native_points_px'])))<1e-8
    with TTFont(target) as f:
        recovered=f['glyf'][f.getBestCmap()[ord(char)]].getCoordinates(f['glyf'])
        assert all(list(a)==list(b) for a,b in zip(original,recovered))
    return render(face,char,size,hinted=True),actual


def run():
    out=HERE/'out/diagonal-widths-v1';out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    inputs={};rows=[];panels=[]
    sources=['compare_diagonal_widths.py','feature_coordination.py','shamir_baseline_solver.py']
    for n in sources:shutil.copy2(HERE/n,out/n)
    for uniform in sorted((HERE/'out/geometric-candidate-v3').glob('*-candidate.ttf')):
        key=uniform.stem.removesuffix('-candidate');size=int(key.rsplit('-',1)[1]);ref=HERE/'out/shamir-representative-comparison'/f'{key}-experiment.ttf';mp=ref.with_name(f'{key}-model.json')
        for path in (uniform,ref,mp):inputs[str(path.relative_to(HERE))]=digest(path)
        model=json.loads(mp.read_text())
        with TTFont(uniform) as repertoire,TTFont(ref) as font:
            for code in sorted(repertoire.getBestCmap()):
                char=chr(code);stem=f'{key}-u{code:04x}';row=dict(key=key,char=char);rows.append(row)
                frozen=HERE/'out/shared-stem-hinter-v2'/f'{stem}.ttf'
                if frozen.exists():
                    inputs[str(frozen.relative_to(HERE))]=digest(frozen);row['status']='frozen-coordinated-case';continue
                record=model['records'][char];graph=copy.deepcopy(record['graph'])
                groups=shared_diagonal_widths(record['features'],graph['constraints']);row['groups']=groups
                if not any(g['changes'] for g in groups):row['status']='unaffected';continue
                p,e,t=font['glyf'][font.getBestCmap()[code]].getCoordinates(font['glyf'])
                # Prove that only the selected distance values changed.
                for a,b in zip(record['graph']['constraints'],graph['constraints']):
                    assert {k:v for k,v in a.items() if k!='value'}=={k:v for k,v in b.items() if k!='value'}
                try:
                    bg,bp=build(ref,char,size,p,record['graph'],out/f'{stem}-before.ttf')
                    ag,ap=build(ref,char,size,p,graph,out/f'{stem}-after.ttf')
                except (ValueError,np.linalg.LinAlgError,ft.FT_Exception) as exc:
                    row.update(status='failed',reason=str(exc));continue
                before=metrics(pixels(bg),bp,np.array(p)*size/font['head'].unitsPerEm)
                after=metrics(pixels(ag),ap,np.array(p)*size/font['head'].unitsPerEm)
                delta=len(pixels(bg)^pixels(ag));issues=[]
                for k in ('black_components','white_counters'):
                    if before[k]!=after[k]:issues.append(f'{k}: {before[k]} to {after[k]}')
                if after['max_source_movement_px']>4:issues.append('movement exceeds diagnostic 4px screen')
                row.update(status='changed' if delta else 'same-bitmap',before=before,after=after,changed_pixels=delta,diagnostics=issues)
                (out/f'{stem}.json').write_text(json.dumps(dict(groups=groups,graph=graph,audit=row),indent=2)+'\n')
                glyphs=[render(ft.Face(str(uniform)),char,size,hinted=True),bg,ag]
                panel=comparison(glyphs,['Current uniform context','Frozen equations: before','Shared diagonal widths: after'],f'{key} {char!r}')
                prepend_reference(ft.Face(str(ref)),char,size,f'{key} {char!r}',glyphs,panel).save(out/f'{stem}.png')
                panels.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)}</h2><img src="{stem}.png"><p>{delta} pixels changed. {html.escape(str(issues))} <a href="{stem}.json">Full audit</a></p></section>')
    assert all(digest(HERE/n)==h for n,h in inputs.items())
    counts=dict(Counter(r['status'] for r in rows))
    (out/'report.json').write_text(json.dumps(dict(counts=counts,inputs=inputs,sources={n:digest(HERE/n) for n in sources},cases=rows),indent=2)+'\n')
    failures=''.join(f'<li>{r["key"]} {html.escape(r["char"])}: {html.escape(r["reason"])}</li>' for r in rows if r['status']=='failed')
    (out/'index.html').write_text('<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{margin:35px 0}</style><h1>Broader diagonal-width experiment</h1><p>Python only. The eight coordinated cases remain frozen. Elsewhere this changes only distance values in the frozen source-model equations; current uniform output is context, not the before baseline. Cap and symmetry rules are unchanged. Component/counter changes and large movements are diagnostics, not automatic rejection or acceptance.</p><p>'+html.escape(str(counts))+'</p>'+''.join(panels)+'<h2>Failed specimens</h2><ul>'+failures+'</ul>')
    print(counts)

if __name__=='__main__':run()
