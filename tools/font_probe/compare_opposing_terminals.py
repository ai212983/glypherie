"""Compare opposing terminal policies across every verified uniform candidate."""
import json,shutil,html
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.ttProgram import Program
from opposing_terminals import detect,fit
from shamir_constraints import relation
from shamir_baseline_solver import compile_baseline
from audit_terminal_coverage import coords
from check_shamir_baseline import digest
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference

HERE=Path(__file__).resolve().parent


def run():
    root=HERE/'out/geometric-candidate-v1';out=HERE/'out/opposing-terminals-v1'
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    (out/'sources').mkdir();hashes={p.name:digest(p) for p in HERE.glob('*.py')}
    for name in hashes:shutil.copy2(HERE/name,out/'sources'/name)
    rows=[];figures=[];inputs={};scanned=0
    for path in sorted(root.glob('*-candidate.ttf')):
        key=path.stem.removesuffix('-candidate');size=int(key.rsplit('-',1)[1]);inputs[path.name]=digest(path)
        shutil.copy2(path,out/path.name);font=TTFont(path);face=ft.Face(str(path));em=font['head'].unitsPerEm
        for code,name in sorted(font.getBestCmap().items()):
            scanned+=1;char=chr(code);p,e,t=font['glyf'][name].getCoordinates(font['glyf']);pairs=detect(p,e,t,em)
            row=dict(key=key,char=char,pairs=pairs,status='no-match');rows.append(row)
            if not pairs:continue
            if len(pairs)!=1:row['status']='ambiguous';continue
            row['status']='matched';before=coords(face,char,size);glyphs=[render(face,char,size,hinted=True)];checks=[]
            for shared in (False,True):
                fitted,audit=fit(p,before,pairs[0],size/em,shared)
                changed={r['outer'] for r in pairs[0]}|{i for r in pairs[0] for i in r['members']}
                assert all(np.array_equal(fitted[i],before[i]) for i in range(len(p)) if i not in changed)
                f=TTFont(path);g=f['glyf'][name]
                cs=[dict(relation('Abs',i,np.eye(2)[axis],value=float(q[axis])*em/size,round=False),id=2*i+axis,depends_on=[]) for i,q in enumerate(fitted) for axis in (0,1)]
                assembly,_=compile_baseline(dict(order=list(range(len(p))),constraints=cs,scheduler='point'),p,size,em)
                g.program=Program();g.program.fromAssembly(assembly)
                f['maxp'].maxSizeOfInstructions=max(f['maxp'].maxSizeOfInstructions,len(g.program.getBytecode()))
                dest=out/f'{key}-u{code:04x}-{"shared" if shared else "coordinated"}.ttf';f.save(dest);f.close()
                new=ft.Face(str(dest));actual=coords(new,char,size)
                error=float(np.max(abs(actual-fitted)));assert error<=1/128+1e-7
                assert all(np.array_equal(actual[i],before[i]) for i in range(len(p)) if i not in changed)
                for r in pairs[0]:
                    source=np.array(r['tip_vector']);tip=actual[r['inner']]-actual[r['outer']]
                    assert abs(float(source[0]*tip[1]-source[1]*tip[0]))<=np.linalg.norm(source)*2/64
                glyphs.append(render(new,char,size,hinted=True))
                checks.append(dict(shared=shared,dimensions=audit,native_error_px=error,changed_pixels=len(pixels(glyphs[0])^pixels(glyphs[-1]))))
            row['checks']=checks
            image=f'{key}-u{code:04x}.png'
            panel=comparison(glyphs,['Current uniform candidate','Coordinated terminals','Shared lengths / thicknesses'],f'{key} {char!r}')
            prepend_reference(face,char,size,f'{key} {char!r}',glyphs,panel).save(out/image)
            figures.append(f'<figure id="{key}-u{code:04x}"><img src="{image}" alt="{html.escape(char,quote=True)}"></figure>')
        font.close()
    assert hashes=={n:digest(HERE/n) for n in hashes}
    assert inputs=={n:digest(root/n) for n in inputs}
    (out/'report.json').write_text(json.dumps(dict(scanned=scanned,inputs=inputs,sources=hashes,cases=rows,policy='Geometry-selected opposing right-facing curved arm terminals. Coordinated: own length rounded nearest, original tip vector. Shared: mean source length rounded nearest, mean tip magnitude, each original tip direction. Curves interpolate to fixed arm anchors. Explicit coordinate export, not native VTT Link/IP parity.'),indent=2)+'\n')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>img{max-width:100%}figure{margin:20px 0}</style><h1>Opposing arm terminals</h1><p>Smooth source, current uniform candidate, coordinated terminals, shared dimensions. Experimental geometry-only policies; shared dimensions preserve each source tip direction. All available candidate mappings scanned. <a href="report.json">Coverage and checks</a>.</p>'+''.join(figures))
    print('scanned',scanned,'matches',sum(r['status']=='matched' for r in rows),'ambiguous',sum(r['status']=='ambiguous' for r in rows))


if __name__=='__main__':run()
