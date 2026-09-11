"""Apply one identity-free ring rule across all verified candidate outlines."""
import json,html,shutil
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from repeated_rings import fit
from joint_ring_placement import place
from audit_terminal_coverage import coords
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from check_shamir_baseline import digest
HERE=Path(__file__).resolve().parent


def run():
    root=HERE/'out/geometric-candidate-v3'; recovery=HERE/'out/outside-in-v1'; out=HERE/'out/joint-rings-v1'
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('output must be empty')
    inputs={}; rows=[]; sections=[]; matched=0
    for name in ('repeated_rings.py','joint_ring_placement.py','compare_joint_rings.py'):
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
            if not pairs:
                assert np.array_equal(candidate,before)
                continue
            matched+=1
            previous=candidate.copy()
            candidate,placement=place(source,previous,[int(f)&1 for f in flags],list(ends),em,size,pairs)
            row['placement']=placement
            involved={i for pair in pairs for ring in pair['contours'] for c in ring for i in range(0 if c==0 else ends[c-1]+1,ends[c]+1)}
            involved.update(i for record in placement if record['status']=='placed' for i in range(0 if record['separator_contour']==0 else ends[record['separator_contour']-1]+1,ends[record['separator_contour']]+1))
            untouched=[i for i in range(len(before)) if i not in involved]
            assert np.array_equal(candidate[untouched],before[untouched])
            for pair in pairs:
                for outer,inner in pair['contours']:
                    for c,wanted in ((outer,pair['outer_px']),(inner,pair['inner_px'])):
                        ids=list(range(0 if c==0 else ends[c-1]+1,ends[c]+1))
                        assert np.array_equal(np.ptp(candidate[ids],axis=0),wanted)
            glyphs=[render(face,char,size,points=previous,hinted=True),render(face,char,size,points=candidate,hinted=True)]
            row.update(changed_pixels=len(pixels(glyphs[0])^pixels(glyphs[1])),bounds_before=[before.min(axis=0).tolist(),before.max(axis=0).tolist()],bounds_after=[candidate.min(axis=0).tolist(),candidate.max(axis=0).tolist()])
            stem=f'{key}-u{code:04x}'; np.save(out/f'{stem}-points.npy',candidate)
            panel=comparison(glyphs,['Shared sizes, independent placement','Joint placement around separator'],f'{key} {char!r}')
            prepend_reference(old,char,size,f'{key} {char!r}',glyphs,panel).save(out/f'{stem}.png')
            bounds_note=(' Ink bounds changed: '+str(row['bounds_before'])+' → '+str(row['bounds_after'])+'.') if row['bounds_before']!=row['bounds_after'] else ''
            sections.append(f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)}</h2><img src="{stem}.png"><p>{len(pairs)} pair(s), {row["changed_pixels"]} changed pixels.{bounds_note}</p></section>')
        font.close()
    assert all(digest(HERE/n)==h for n,h in inputs.items())
    (out/'report.json').write_text(json.dumps(dict(inputs=inputs,sources={n:digest(HERE/n) for n in ('repeated_rings.py','joint_ring_placement.py','compare_joint_rings.py')},cases=rows),indent=2)+'\n')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Joint ring placement</title><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{border-top:1px solid #ddd}</style><h1>Joint ring placement</h1><p>Columns: smooth source, previous shared-size experiment, joint placement. Ring shapes and dimensions stay fixed. The separator moves rigidly. Joint placement minimizes changes to source center vectors with a small movement penalty. This is an experimental policy, pending visual review.</p>'+f'<p>{len(rows)} outlines checked; {matched} matched.</p>'+''.join(sections))
    print(f'{len(rows)} checked; {matched} matched')

if __name__=='__main__':run()
