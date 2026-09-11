"""Scan every verified candidate for discarded metric-bound stroke relations."""
import json,html,shutil
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from build_geometric_candidate import geometry
from geometric_candidate import correct,finish
from outside_in import recover
from shamir_reorientation import Unsupported
from audit_terminal_coverage import coords
from check_shamir_baseline import digest
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference

HERE=Path(__file__).resolve().parent


def lost_widths(record):
    reps=record['representative_points'];result=[]
    for rejected in record['reduced_graph']['rejected']:
        c=rejected['constraint'];feature=c.get('feature','')
        if c['kind'] not in ('Dist','PDist') or not feature.startswith('width-'):continue
        f=record['features'][int(feature.split('-')[1])]
        if f['kind'] not in ('stem','bar','curve_stem','curve_bar','bow','arc'):continue
        result.append(dict(c,point=reps[c['point']],sources=[reps[i] for i in c['sources']]))
    return result


def run():
    root=HERE/'out/geometric-candidate-v3';models=HERE/'out/shamir-representative-comparison';out=HERE/'out/outside-in-v1'
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    (out/'sources').mkdir();hashes={p.name:digest(p) for p in HERE.glob('*.py')}
    for n in hashes:shutil.copy2(HERE/n,out/'sources'/n)
    inventory=[];figures=[];inputs={}
    for path in sorted(root.glob('*-candidate.ttf')):
        key=path.stem.removesuffix('-candidate');size=int(key.rsplit('-',1)[1]);mp=models/f'{key}-model.json'
        for p in (path,mp):inputs[p.name]=digest(p);shutil.copy2(p,out/p.name)
        model=json.loads(mp.read_text());font=TTFont(path);em=font['head'].unitsPerEm;old=ft.Face(str(path))
        for code,name in sorted(font.getBestCmap().items()):
            char=chr(code);raw=model['records'][char];points,ends,flags=font['glyf'][name].getCoordinates(font['glyf'])
            data=geometry(raw,points,ends,flags,size,em);changed,changes,held=recover(data,lost_widths(raw))
            row=dict(key=key,char=char,changes=changes,held=held,status='unchanged');inventory.append(row)
            if not changes:continue
            try:
                result=correct(changed);f=TTFont(path)
                assembly,cvts,expected=finish(result,changed,len(f['cvt '].values))
            except (Unsupported,ValueError) as exc:
                row.update(status='unsupported',reason=str(exc));continue
            f['cvt '].values.extend(cvts);g=f['glyf'][name];g.program=Program();g.program.fromAssembly(assembly)
            f['maxp'].maxSizeOfInstructions=max(f['maxp'].maxSizeOfInstructions,len(g.program.getBytecode()))
            target=out/f'{key}-u{code:04x}.ttf';f.save(target);f.close();face=ft.Face(str(target));actual=coords(face,char,size)
            err=float(np.max(abs(actual-expected)));assert err<=1/64+1e-7
            before=coords(old,char,size)
            violations=[]
            for change in changes:
                c=change['restored'];outer=c['point'];inner,=c['sources'];n=np.array(c['normal'])
                if abs(float((actual[outer]-before[outer])@n))>1/64:violations.append("outer metric moved")
                requested=np.copysign(np.floor(abs(c['value']*size/em)+.5),c['value']*size/em) if c.get('round',True) else c['value']*size/em
                if abs(float((actual[outer]-actual[inner])@n)-requested)>2/64:violations.append("recovered width not preserved by subsequent pipeline stages")
            if violations:
                row.update(status="unsupported",reason="; ".join(sorted(set(violations))))
                target.unlink()
                continue
            glyphs=[render(f,char,size,hinted=True) for f in (old,face)]
            row.update(status='verified',native_error_px=err,changed_pixels=len(pixels(glyphs[0])^pixels(glyphs[1])))
            image=f'{key}-u{code:04x}.png';panel=comparison(glyphs,['Current uniform candidate','Outside-in experiment'],f'{key} {char!r}')
            prepend_reference(old,char,size,f'{key} {char!r}',glyphs,panel).save(out/image)
            figures.append(f'<figure id="{key}-u{code:04x}"><img src="{image}" alt="{html.escape(char,quote=True)}"></figure>')
        font.close()
    assert hashes=={n:digest(HERE/n) for n in hashes}
    for name,value in inputs.items():assert digest((models if name.endswith('.json') else root)/name)==value
    (out/'report.json').write_text(json.dumps(dict(sources=hashes,inputs=inputs,cases=inventory),indent=2)+'\n')
    excluded=''.join(f'<li>{r["key"]} {html.escape(r["char"])}: {html.escape(r.get("reason","ambiguous anchor"))}</li>' for r in inventory if r['status']=='unsupported' or r['held'])
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>img{max-width:100%}</style><h1>Outside-in stroke placement</h1><p>Smooth source, current candidate, experiment. Metric-bound outer edges stay fixed while recovered stroke links control inner edges. Geometry-only experimental direction policy; no promotion.</p><ul>'+excluded+'</ul>'+''.join(figures))
    from collections import Counter
    print(Counter(r['status'] for r in inventory))


if __name__=='__main__':run()
