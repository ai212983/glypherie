"""Corpus-wide before/after audit of shared-point scheduling in the VTT experiment."""
import html,json,shutil
from collections import Counter
import numpy as np
import freetype as ft
import vttcompilepy as vtt
from fontTools.ttLib import TTFont
from compare_vtt_compiler import HERE,prepare,REV
from vtt_mapping import commands
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from audit_terminal_coverage import coords
from check_shamir_baseline import digest


def holes(ink):
    if not ink:return []
    xs,ys=zip(*ink)
    empty={(x,y) for x in range(min(xs)-1,max(xs)+2) for y in range(min(ys)-1,max(ys)+2)}-ink
    todo=[(min(xs)-1,min(ys)-1)];seen=set(todo)
    while todo:
        x,y=todo.pop()
        for n in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if n in empty and n not in seen:seen.add(n);todo.append(n)
    return sorted(empty-seen)


def compile_case(path,char,talk,cvts,target,size):
    f=prepare(path);name=f.getBestCmap()[ord(char)]
    original=f['glyf'][name].getCoordinates(f['glyf'])
    f['TSI3'].glyphPrograms[name]=talk
    f['TSI1'].extraPrograms['cvt']+='\n'+'\n'.join(f'{1000+i}: {v}' for i,v in enumerate(cvts))
    c=vtt.Compiler(f);c.compile_all();c.save_font(target)
    with TTFont(target) as result:
        actual=result['glyf'][name].getCoordinates(result['glyf'])
        assert all(list(a)==list(b) for a,b in zip(original,actual))
        target.with_suffix('.asm').write_text(result['TSI1'].glyphPrograms[name])
    face=ft.Face(str(target));points=coords(face,char,size)
    assert np.isfinite(points).all()
    target.with_suffix('.vtt').write_text(talk)
    return render(face,char,size,hinted=True),points


def run(*, stem_widths=False):
    out=HERE/('out/vtt-stem-widths-v1' if stem_widths else 'out/vtt-dependencies-v1');out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('Output must be empty')
    rows=[];panels=[];inputs={}
    for name in ('vtt_mapping.py','vtt_dependencies.py','vtt_stem_widths.py','compare_vtt_dependencies.py'):
        shutil.copy2(HERE/name,out/name)
    for uniform in sorted((HERE/'out/geometric-candidate-v3').glob('*-candidate.ttf')):
        key=uniform.stem.removesuffix('-candidate');size=int(key.rsplit('-',1)[1])
        path=HERE/'out/shamir-representative-comparison'/f'{key}-experiment.ttf'
        model_path=path.with_name(f'{key}-model.json');model=json.loads(model_path.read_text())
        for p in (path,model_path,uniform):inputs[str(p.relative_to(HERE))]=digest(p)
        with TTFont(path) as font,TTFont(uniform) as repertoire:
            for code in sorted(repertoire.getBestCmap()):
                char=chr(code);stem=f'{key}-u{code:04x}';name=font.getBestCmap()[code]
                p,e,t=font['glyf'][name].getCoordinates(font['glyf']);record=model['records'][char]
                before,bc,bm=commands(p,t,record,shared_dependencies=stem_widths)
                after,ac,am=commands(p,t,record,shared_dependencies=True,stem_widths=stem_widths)
                row=dict(key=key,char=char,dependencies=am['dependencies'],width_inheritance=am['width_inheritance']);rows.append(row)
                if not bm['strokes']:row['status']='unmapped';continue
                if am['status']=='held':row['status']='held';continue
                if before==after and bc==ac:row['status']='unchanged-program';continue
                try:
                    bg,bp=compile_case(path,char,before,bc,out/f'{stem}-before.ttf',size)
                    ag,ap=compile_case(path,char,after,ac,out/f'{stem}-after.ttf',size)
                except (vtt.CompileError,ft.FT_Exception) as exc:
                    row.update(status='execution-failed',reason=str(exc));continue
                changed=len(pixels(bg)^pixels(ag))
                row.update(status='changed' if changed else 'same-bitmap',changed_pixels=changed,
                           before_holes=holes(pixels(bg)),after_holes=holes(pixels(ag)),
                           max_coordinate_change_px=float(np.max(abs(bp-ap))))
                panel=comparison([bg,ag],(['Before: independent widths','After: inherited stem width'] if stem_widths else ['Before: length order','After: shared-point dependencies']),f'{key} {char!r}')
                prepend_reference(ft.Face(str(path)),char,size,f'{key} {char!r}',[bg,ag],panel).save(out/f'{stem}.png')
                panels.append((row['status'],f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)}</h2><img src="{stem}.png"><p>{changed} pixels changed; enclosed white pixels: {len(row["before_holes"])} → {len(row["after_holes"])}. <a href="{stem}-before.vtt">Before commands</a> / <a href="{stem}-after.vtt">After commands</a></p></section>'))
        print(key,Counter(r['status'] for r in rows),flush=True)
    assert all(digest(HERE/n)==h for n,h in inputs.items())
    counts=dict(Counter(r['status'] for r in rows))
    (out/'report.json').write_text(json.dumps(dict(counts=counts,compiler_revision=REV,templates={p.name:digest(p) for p in (HERE/"vtt_reference").glob("*.txt")},inputs=inputs,cases=rows,sources={n:digest(HERE/n) for n in ('vtt_mapping.py','vtt_dependencies.py','vtt_stem_widths.py','compare_vtt_dependencies.py')}),indent=2)+'\n')
    held=''.join(f'<li>{r["key"]} {html.escape(r["char"])}: {html.escape(str(r.get("reason",r["dependencies"]["conflicts"])))}</li>' for r in rows if r['status'] in ('held','execution-failed'))
    intro='<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{margin-bottom:35px}</style><h1>Shared-point dependency comparison</h1><p><strong>Roboto M holes persist at 16px and 18px; dependency ordering alone is insufficient.</strong> All 881 exported cases screened. Source reference, previous VTT mapping, dependency-ordered mapping. Enclosed white pixels are diagnostics; intentional counters also count. Held conflicts retain the prior result and are listed below.</p><p>'+html.escape(str(counts))+'</p>'
    if stem_widths:
        intro='<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{margin-bottom:35px}</style><h1>Stem width inheritance</h1><p>Source reference, dependency-ordered VTT with independent widths, inherited stem width. All 881 exported cases screened. Matching requires a shared side, connected opposite sides, direction within 5 degrees and source width within 20%. These are experimental limits. Enclosed white pixels include intentional counters.</p><p>'+html.escape(str(counts))+'</p>'
    (out/'index.html').write_text(intro+'<h2>Changed images</h2>'+''.join(s for status,s in panels if status=='changed')+'<h2>Changed programs, identical images</h2>'+''.join(s for status,s in panels if status=='same-bitmap')+'<h2>Held cases</h2><ul>'+held+'</ul>')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--stem-widths',action='store_true')
    run(stem_widths=parser.parse_args().stem_widths)
