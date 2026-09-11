"""Frozen graph-only representative-search experiment against baseline v6."""
import argparse, html, json, shutil
from pathlib import Path
import freetype as ft
from PIL import Image,ImageDraw
from shamir_model import build_font
from shamir_representative_search import representative_override
from check_shamir_baseline import digest,coordinate_check,graph_issues,construction_issues
from compare_shamir_pipeline import CHARS
from compare_paper_prototypes import render,pixels,draw_glyph
from render_shamir_baseline import extent,native_text

HERE=Path(__file__).resolve().parent


def comparison(glyphs,labels,title):
    x0,y0,x1,y1=extent(glyphs);scale=8;w=max(210,(x1-x0)*scale+32)
    im=Image.new('RGB',(w*len(glyphs),(y1-y0)*scale+80),'white');d=ImageDraw.Draw(im)
    d.text((16,5),title,fill='black')
    for i,(g,label) in enumerate(zip(glyphs,labels)):
        d.text((i*w+16,26),label,fill='black');draw_glyph(d,g,i*w+16-x0*scale,55-y0*scale,scale)
    return im


def contour_order_audit():
    from shamir_geometry import prepare
    from shamir_model import feature_model,constraints_for
    from shamir_representative_search import coordinate_representatives
    ps=[(65,55),(65,44),(25,44),(25,0),(12,0),(12,100),(73,100),(73,89),(25,89),(25,55)]
    rows=[]
    for reverse in (False,True):
        for start in range(len(ps)):
            q=ps[::-1] if reverse else ps;q=q[start:]+q[:start]
            m=feature_model(prepare([[[a,b] for a,b in zip(q,q[1:]+q[:1])]],100,baseline=True),baseline=True)
            result=coordinate_representatives(m,{'height-flat-min':[0.],'height-flat-max':[100.]},100,constraints_for)
            rows.append(dict(reverse=reverse,start=start,score=result['selected_score'],cycles=result['selected_cycles']))
    return dict(cases=rows,distinct_scores=len({tuple(r['score']) for r in rows}),
                interpretation='score variation demonstrates remaining contour-order sensitivity; zero cycles alone is insufficient')


def run(reference,output,budget):
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('output must be empty')
    paths=sorted(HERE.glob('*.py'));hashes={p.name:digest(p) for p in paths}
    (output/'sources').mkdir()
    for p in paths:shutil.copy2(p,output/'sources'/p.name)
    baseline=json.loads((reference/'baseline-verification.json').read_text())
    builds=[];sections=[]
    for b in baseline['builds']:
        key=f"{b['font']}-{b['size']}";source=output/f'{key}-source.ttf';old=output/f'{key}-reference.ttf'
        shutil.copy2(reference/b['input'],source);shutil.copy2(reference/b['output'],old)
        target=output/f'{key}-experiment.ttf'
        with representative_override(budget) as audits:
            model=build_font(source,target,CHARS,profile='baseline',ppem=b['size'])
        model['experiment_override']=dict(type='coordinated representatives',budget=budget,
                                         classification='unpromoted interpretation; fixed pre-search measurements')
        model['representative_search']=dict(zip(model['records'],audits))
        faces=[ft.Face(str(source)),ft.Face(str(old)),ft.Face(str(target))];checks=[];figures=[]
        for c,rec in model['records'].items():
            checks.append(dict(char=c,native=coordinate_check(faces[2],c,b['size'],rec['graph']),
                               issues=graph_issues(rec['graph'])+graph_issues(rec['reduced_graph'])+construction_issues(rec)))
            glyphs=[render(face,c,b['size'],hinted=i>0) for i,face in enumerate(faces)]
            changed=len(pixels(glyphs[1])^pixels(glyphs[2]));checks[-1]['changed_pixels']=changed
            name=f'{key}-u{ord(c):04x}.png'
            comparison(glyphs,['Unhinted input','Reference v6','Representative experiment'],f'{key} {c!r}').save(output/name)
            figures.append(f'<figure id="{key}-u{ord(c):04x}"><img loading="lazy" src="{name}" alt="{html.escape(c,quote=True)}"></figure>')
        native=[]
        for j,line in enumerate(('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz','0123456789 .,;:!?%°+-/()[]"\'=')):
            for i,label in enumerate(('Unhinted','Reference v6','Experiment')):
                name=f'{key}-text-{j}-{i}.png';native_text(faces[i],line,b['size'],i>0).save(output/name)
                native.append(f'<p>{label}</p><img src="{name}">')
        (output/f'{key}.html').write_text('<!doctype html><meta charset="utf-8"><title>'+key+'</title><style>img{max-width:100%}figure{margin:12px 0}</style><a href="index.html">Index</a><h1>'+key+'</h1><p>Experimental representative selection. Same equations and point scheduler; graph-only search, fixed measurements. Neither candidate is approved.</p>'+''.join(native+figures))
        (output/f'{key}-model.json').write_text(json.dumps(model,indent=2)+'\n')
        summary=dict(font=b['font'],size=b['size'],input_hash=digest(source),reference_hash=digest(old),output_hash=digest(target),
                     cycles_before=sum(a['initial_cycles'] for a in audits),cycles_after=sum(a['selected_cycles'] for a in audits),
                     exhausted=sum(a['budget_exhausted'] for a in audits),evaluations=sum(a['evaluations'] for a in audits),
                     changed_glyphs=sum(c['changed_pixels']>0 for c in checks),checks=checks)
        builds.append(summary);print(key,summary['cycles_before'],summary['cycles_after'],'changed',summary['changed_glyphs'],flush=True)
        sections.append(f'<li><a href="{key}.html">{key}</a> — cycles {summary["cycles_before"]} → {summary["cycles_after"]}; changed glyphs {summary["changed_glyphs"]}</li>')
    if hashes!={p.name:digest(p) for p in paths}:raise RuntimeError('sources changed during experiment')
    passed=all(c['native']['passed'] and not c['issues'] for b in builds for c in b['checks'])
    report=dict(experiment='coordinated representative selection',budget=budget,sources=hashes,passed=passed,builds=builds,contour_order_audit=contour_order_audit())
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Representative experiment</title><h1>Coordinated representative experiment</h1><p>Unpromoted graph-only search. No glyph names or rendered pixels guide selection. Existing point solver, fixed font measurements, 256-evaluation bound per glyph by default. Fewer cycles do not establish better glyphs or exact author equivalence. A synthetic contour-start/winding audit still finds different constraint scores; contour-order independence is not established.</p><ul>'+''.join(sections)+'</ul>')
    if not passed:raise ValueError('experiment failed verification; inspect report')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reference',type=Path,default=HERE/'out/shamir-baseline-v6');p.add_argument('--output',type=Path,default=HERE/'out/shamir-representative-comparison');p.add_argument('--budget',type=int,default=256);a=p.parse_args();run(a.reference,a.output,a.budget)
