"""Full specimen of the conservative cumulative Python integration candidate."""
import html
import json
from collections import Counter
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from cumulative_hinter import prepare, reflect
from build_geometric_candidate import geometry
from compare_diagonal_widths import build, metrics
from cross_section_widths import export_graph
from compare_paper_prototypes import render, pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from check_shamir_baseline import digest
from audit_terminal_coverage import coords

HERE = Path(__file__).resolve().parent


def run():
    out = HERE/'out/cumulative-hinter-v6'
    out.mkdir(exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('output must be empty')
    inputs = {str(p.relative_to(HERE)):digest(p) for p in HERE.glob('*.py')}
    rows, pages = [], []
    for uniform in sorted((HERE/'out/geometric-candidate-v3').glob('*-candidate.ttf')):
        key = uniform.stem.removesuffix('-candidate'); size = int(key.rsplit('-',1)[1])
        ref = HERE/'out/shamir-representative-comparison'/f'{key}-experiment.ttf'
        model = ref.with_name(f'{key}-model.json')
        for p in (uniform, ref, model):inputs[str(p.relative_to(HERE))] = digest(p)
        records = json.loads(model.read_text())['records']
        sections = []
        with TTFont(ref) as font, TTFont(uniform) as repertoire:
            old = ft.Face(str(uniform)); source_face = ft.Face(str(ref))
            for code in sorted(repertoire.getBestCmap()):
                char = chr(code); stem = f'{key}-u{code:04x}'
                row = dict(key=key, char=char); rows.append(row)
                try:
                    p, ends, flags = font['glyf'][font.getBestCmap()[code]].getCoordinates(font['glyf'])
                    data = geometry(records[char],p,ends,flags,size,font['head'].unitsPerEm)
                    base, current, audit = prepare(data,records[char])
                    baseline = render(old,char,size,hinted=True)
                    bn = coords(old,char,size)
                    assert np.max(abs(bn-base))<1/64+1e-7, 'geometric rebuild differs from frozen candidate'
                    if np.max(abs(current-bn))<1e-9:
                        middle,mn = baseline,bn
                    else:
                        middle,mn = build(ref,char,size,p,export_graph(current,size/data.em),out/f'{stem}-current.ttf')
                    final, reflection = reflect(data,records[char],current,audit,pixels(middle))
                    if np.array_equal(final,current):
                        after,an = middle,mn
                    else:
                        after,an = build(ref,char,size,p,export_graph(final,size/data.em),out/f'{stem}-after.ttf')
                    assert np.max(abs(an-final))<=1/128+1e-9
                    previous = HERE/'out/cumulative-hinter-v4'/f'{stem}-after.ttf'
                    if not previous.exists():previous=HERE/'out/cumulative-hinter-v4'/f'{stem}-current.ttf'
                    prior = render(ft.Face(str(previous)),char,size,hinted=True) if previous.exists() else baseline
                    if previous.exists():inputs[str(previous.relative_to(HERE))]=digest(previous)
                    delta = len(pixels(prior)^pixels(after))
                    row.update(status=audit['status'],audit=audit,reflection=reflection,
                        changed_from_geometric=len(pixels(baseline)^pixels(after)),changed_from_previous=delta,
                        previous_available=previous.exists(),
                        metrics=metrics(pixels(after),an,np.asarray(p)*size/data.em))
                    panel = comparison([baseline,prior,after],['Geometric baseline','Previous isolated fit' if previous.exists() else 'Geometric baseline (no prior fit)','Cumulative candidate'],f'{key} {char!r}')
                    prepend_reference(source_face,char,size,f'{key} {char!r}',[baseline,prior,after],panel).save(out/f'{stem}.png')
                    section=f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)}</h2><p>{html.escape(row["status"])}; {delta} pixels changed from previous. <a href="{stem}.json">Audit</a></p><img loading="lazy" src="{stem}.png"></section>'
                    sections.append(section); pages.append((delta,section))
                except (ValueError, AssertionError, np.linalg.LinAlgError, ft.FT_Exception) as exc:
                    row.update(status='rejected',reason=str(exc))
                    section=f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)}</h2><p>REJECTED: {html.escape(str(exc))}</p></section>'
                    sections.append(section); pages.append((1,section))
                (out/f'{stem}.json').write_text(json.dumps(row,indent=2)+'\n')
        header='<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{margin:30px 0}</style><h1>Cumulative Python candidate</h1><p>Stage-owned coordinates enter the joint solve as hard constraints. All stages report ownership conflicts and geometry admission failures. Reflection remains experimental; rejected cases are listed explicitly.</p>'
        (out/f'{key}.html').write_text(header+''.join(sections))
        print(key,dict(Counter(r['status'] for r in rows if r['key']==key)),flush=True)
    assert all(digest(HERE/n)==sha for n,sha in inputs.items())
    counts=dict(Counter(r['status'] for r in rows))
    (out/'report.json').write_text(json.dumps(dict(counts=counts,cases=rows,inputs=inputs),indent=2)+'\n')
    nav='<p><a href="changes.html">Changed from prior experiment</a> · <a href="index.html">Full specimen</a></p>'
    (out/'index.html').write_text(header+nav+html.escape(str(counts))+''.join(s for _,s in pages))
    (out/'changes.html').write_text(header+nav+''.join(s for d,s in pages if d))
    print(counts)

if __name__=='__main__':run()
