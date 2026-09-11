"""Apply one identity-free ring rule across all verified candidate outlines."""
import json,html,shutil
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from repeated_rings import fit
from component_placement import place
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from check_shamir_baseline import digest
HERE=Path(__file__).resolve().parent


def run():
    root=HERE/'out/geometric-candidate-v3'; recovery=HERE/'out/outside-in-v1'; out=HERE/'out/component-placement-v1'
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    inputs={}; rows=[]; sections=[]; matched=0
    for name in ('repeated_rings.py','component_placement.py','compare_component_placement.py'):
        shutil.copy2(HERE/name,out/name)
    for path in sorted(root.glob('*-candidate.ttf')):
        key=path.stem.removesuffix('-candidate'); size=int(key.rsplit('-',1)[1]); font=TTFont(path); em=font['head'].unitsPerEm
        inputs[str(path.relative_to(HERE))]=digest(path); old=ft.Face(str(path))
        for code,name in sorted(font.getBestCmap().items()):
            char=chr(code); base=coords(old,char,size); alternate=recovery/f'{key}-u{code:04x}.ttf'
            if alternate.exists():
                inputs[str(alternate.relative_to(HERE))]=digest(alternate); face=ft.Face(str(alternate)); before=coords(face,char,size)
            else:face=old;before=base
            source,ends,flags=font['glyf'][name].getCoordinates(font['glyf'])
            candidate,pairs=fit(source,before,[int(f)&1 for f in flags],list(ends),em,size)
            row=dict(key=key,char=char,pairs=pairs);rows.append(row)
            previous=candidate.copy()
            candidate,placement=place(source,previous,[int(f)&1 for f in flags],list(ends),em,size)
            row['placement']=placement
            if placement['status']!='placed':
                assert np.array_equal(candidate,previous)
                continue
            for group in placement['components']:
                delta=candidate[group]-previous[group]
                assert np.array_equal(delta,np.tile(delta[0],(len(group),1)))
            matched+=1
            stem=f'{key}-u{code:04x}'
            accepted=HERE/'out/joint-rings-v1'/f'{stem}-points.npy'
            reference=np.load(accepted) if accepted.exists() else previous
            if accepted.exists():inputs[str(accepted.relative_to(HERE))]=digest(accepted)
            glyphs=[render(face,char,size,points=previous,hinted=True),render(face,char,size,points=reference,hinted=True),render(face,char,size,points=candidate,hinted=True)]
            row.update(changed_pixels=len(pixels(glyphs[0])^pixels(glyphs[2])),coordinate_changed=bool(np.any(candidate!=previous)),preferred_pixel_difference=len(pixels(glyphs[1])^pixels(glyphs[2])),bounds_before=[previous.min(axis=0).tolist(),previous.max(axis=0).tolist()],bounds_after=[candidate.min(axis=0).tolist(),candidate.max(axis=0).tolist()])
            stem=f'{key}-u{code:04x}'; np.save(out/f'{stem}-points.npy',candidate)
            panel=comparison(glyphs,['Before placement','Previous joint result' if accepted.exists() else 'Before (no prior joint result)','General component placement'],f'{key} {char!r}')
            prepend_reference(old,char,size,f'{key} {char!r}',glyphs,panel).save(out/f'{stem}.png')
            bounds_note=(' Ink bounds changed: '+str(row['bounds_before'])+' → '+str(row['bounds_after'])+'.') if row['bounds_before']!=row['bounds_after'] else ''
            sections.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)}</h2><img src="{stem}.png"><p>{len(pairs)} pair(s), {row["changed_pixels"]} changed pixels.{bounds_note}</p></section>')
        font.close()
    assert all(digest(HERE/n)==h for n,h in inputs.items())
    (out/'report.json').write_text(json.dumps(dict(inputs=inputs,sources={n:digest(HERE/n) for n in ('repeated_rings.py','component_placement.py','compare_component_placement.py')},cases=rows),indent=2)+'\n')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>General component placement</title><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{border-top:1px solid #ddd}</style><h1>General component placement</h1><nav><a href="changes.html">Every pixel change</a> | <a href="percent.html">Percent comparisons</a></nav><p>Columns: smooth source, before placement, preferred narrow result (otherwise before placement), general component placement. The new placement rule receives geometry alone, recognizes disconnected components and translated repetition, and preserves all pairwise source center vectors. Component shapes remain fixed. Repeated components move by integer pixels; others by 1/64 pixel. Existing shared-ring sizing remains an upstream experimental control.</p>'+f'<p>{len(rows)} outlines checked; {matched} matched.</p>'+''.join(sections))
    placed=[r for r in rows if r['placement']['status']=='placed']
    header='<!doctype html><meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{border-top:1px solid #ddd}</style>'
    for page,title,predicate in [('changes.html','Every pixel change',lambda r:r['changed_pixels']>0),('percent.html','Percent comparison',lambda r:r['char']=='%')]:
        selected=[(r,section) for r,section in zip(placed,sections) if predicate(r)]
        navigation=' '.join(f'<a href="#{r["key"]}-u{ord(r["char"]):04x}">{html.escape(r["key"])} {html.escape(r["char"])}</a>' for r,_ in selected)
        (out/page).write_text(header+f'<h1>{title}</h1><p>{len(selected)} cases. Columns: smooth source, before placement, previous joint result where available, general placement.</p><p><a href="index.html">All applicable cases and method</a></p><nav>'+navigation+'</nav>'+''.join(section for _,section in selected))
    print(f'{len(rows)} checked; {matched} applicable; {sum(r["changed_pixels"]>0 for r in placed)} pixel changes')

if __name__=='__main__':run()
