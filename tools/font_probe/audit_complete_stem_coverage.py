"""Corpus comparison of the approved complete-stem rule within the joint fit."""
import argparse
import html
import json
from collections import Counter
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
from joint_stroke_fit import fit, stem_relations
from cross_section_widths import export_graph
from compare_diagonal_widths import build, metrics
from compare_paper_prototypes import pixels, render
from audit_terminal_coverage import coords
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from check_shamir_baseline import digest

HERE = Path(__file__).resolve().parent


def run(terminal_filter=False, continuations=False, reflection=False):
    continuations = continuations or reflection
    terminal_filter = terminal_filter or continuations
    out = HERE/('out/stem-terminal-filter-v1' if terminal_filter else 'out/complete-stem-coverage-v1')
    if continuations:
        out = HERE/"out/stem-continuations-v1"
    if reflection:
        out = HERE/"out/reflection-coverage-v2"
    out.mkdir(exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('output must be empty')
    rows, hashes, panels, thumbs = [], {}, [], []
    for path in HERE.glob('*.py'):
        hashes[str(path.relative_to(HERE))] = digest(path)
    for uniform in sorted((HERE/'out/geometric-candidate-v3').glob('*-candidate.ttf')):
        key = uniform.stem.removesuffix('-candidate'); size = int(key.rsplit('-',1)[1])
        ref = HERE/'out/shamir-representative-comparison'/f'{key}-experiment.ttf'
        mp = ref.with_name(f'{key}-model.json')
        for path in (uniform,ref,mp):
            hashes[str(path.relative_to(HERE))] = digest(path)
        records = json.loads(mp.read_text())['records']
        with TTFont(uniform) as repertoire, TTFont(ref) as font:
            scale = size/font['head'].unitsPerEm
            for code in sorted(repertoire.getBestCmap()):
                char = chr(code); stem = f'{key}-u{code:04x}'
                row = dict(key=key,char=char); rows.append(row)
                p,ends,flags = font['glyf'][font.getBestCmap()[code]].getCoordinates(font['glyf'])
                record = records[char]
                try:
                    _,ids,supports = stem_relations(p,ends,record)
                    row['supports'] = supports
                    previous = HERE/('out/stem-continuations-v1' if reflection else 'out/stem-terminal-filter-v1' if continuations else 'out/complete-stem-coverage-v1')/f'{stem}-after.ttf'
                    if not reflection and not ids and not (terminal_filter and previous.exists()):
                        row['status'] = 'no-complete-stem'; continue
                    before,ba = fit(p,ends,flags,record,scale,complete_stems=reflection,continuations=reflection)
                    if ba['candidate_status']=='no-match':
                        row['status'] = 'outside-joint-fit'; continue
                    if terminal_filter and previous.exists():
                        hashes[str(previous.relative_to(HERE))] = digest(previous)
                        face=ft.Face(str(previous)); bg=render(face,char,size,hinted=True); bn=coords(face,char,size); before=bn
                    else:
                        bg,bn = build(ref,char,size,p,export_graph(before,scale),out/f'{stem}-before.ttf')
                    after,aa = fit(p,ends,flags,record,scale,complete_stems=True,continuations=continuations,reflection_em=font["head"].unitsPerEm if reflection else None,reflection_ink=pixels(bg) if reflection else None)
                    row['candidate_status'] = aa['candidate_status']
                    row['before_audit'] = ba; row['after_audit'] = aa
                    ag,an = build(ref,char,size,p,export_graph(after,scale),out/f'{stem}-after.ttf')
                    assert np.max(abs(bn-before))<=1/128+1e-9
                    assert np.max(abs(an-after))<=1/128+1e-9
                    delta = len(pixels(bg)^pixels(ag))
                    if aa['candidate_status'].startswith('held-'):
                        assert delta==0
                        row['status']='held-conflict'
                    else:
                        row['status']='changed' if delta else 'same-bitmap'
                    row['changed_pixels']=delta
                    row['stems']=[]
                    for s in aa.get('stem_relations',[]):
                        if s['status']!='protected' or aa['candidate_status'].startswith('held-'):continue
                        n=np.asarray(s['normal']); left,right=s['sides']
                        spread=max(float(np.ptp(after[side] @ n)) for side in (left,right))
                        native_spread=max(float(np.ptp(an[side] @ n)) for side in (left,right))
                        assert spread<1e-7 and native_spread<1e-7
                        row['stems'].append(dict(id=s['id'],spread_px=spread,native_spread_px=native_spread,
                            width_px=abs(float(np.mean(after[right] @ n)-np.mean(after[left] @ n)))))
                    for label,g,q in [('before',bg,before),('after',ag,after)]:
                        ink=pixels(g); m=metrics(ink,q,np.asarray(p)*scale)
                        if ink:
                            xs=[x for x,y in ink]; m['reflection_difference']=len(ink^{(min(xs)+max(xs)-x,y) for x,y in ink})
                        row[label]=m
                    panel=comparison([bg,ag],['Current joint fit' if reflection else 'Terminal-filtered baseline' if continuations else 'Prior complete stems' if terminal_filter else 'Joint fit before','Coordinated reflection' if reflection else 'Protected continuations' if continuations else 'Terminal-filtered stems' if terminal_filter else 'Complete stems after'],f'{key} {char!r}')
                    prepend_reference(ft.Face(str(ref)),char,size,f'{key} {char!r}',[bg,ag],panel).save(out/f'{stem}.png')
                    if delta:
                        thumb=Image.new('RGB',(230,panel.height+20),'white')
                        thumb.paste(panel.crop((panel.width//2,0,panel.width,panel.height)),(0,20))
                        ImageDraw.Draw(thumb).text((4,0),stem,fill='black'); thumbs.append(thumb)
                    panels.append((delta,f'<section id="{stem}"><h2>{key} {html.escape(char)}</h2><p>{row["status"]}; {delta} changed pixels. <a href="{stem}.json">Audit</a></p><img src="{stem}.png"></section>'))
                except (ValueError,np.linalg.LinAlgError,ft.FT_Exception) as exc:
                    row.update(status='failed',reason=str(exc))
                (out/f'{stem}.json').write_text(json.dumps(row,indent=2)+'\n')
        print(key,dict(Counter(r['status'] for r in rows if r['key']==key)),flush=True)
    assert all(digest(HERE/name)==sha for name,sha in hashes.items())
    counts=dict(Counter(r['status'] for r in rows))
    (out/'report.json').write_text(json.dumps(dict(counts=counts,cases=rows,inputs=hashes),indent=2)+'\n')
    intro='<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{margin:35px 0}</style><h1>Complete-stem coverage</h1><p>Same joint solver before/after; only complete cardinal stem/bar protection changes. All calibration cases screened. Outside-joint-fit cases do not enter the current diagonal experiment; they are not claimed as validated by this rule.</p><p>'+html.escape(str(counts))+'</p><p><a href="changes.html">Changed glyphs</a> · <a href="index.html">All rendered pairs</a> · <a href="report.json">Full coverage and failures</a></p>'
    if terminal_filter:
        intro=intro.replace('Complete-stem coverage','Terminal-length exclusion').replace('Same joint solver before/after; only complete cardinal stem/bar protection changes.', 'Frozen prior complete-stem output versus terminal-length exclusion. Only broad short pairs overlapping a perpendicular elongated stroke are excluded from complete-stem protection.')
    if continuations:
        intro=intro.replace('Terminal-length exclusion','Stem continuation protection').replace('Frozen prior complete-stem output versus terminal-length exclusion. Only broad short pairs overlapping a perpendicular elongated stroke are excluded from complete-stem protection.', 'Frozen terminal-filtered output versus protection of all selected stem continuations together. Existing unrounded alignments on one adjacent on-curve segment within 5 degrees are retained in their source direction. No recursive propagation. Conflicts retain the previous result.')
    if reflection:
        intro=intro[:intro.index('<h1>')]+'<h1>Coordinated reflection coverage</h1><p>Current joint fit versus integrated reflection constraints. Unique source-contour/tag correspondence within em/512; half-pixel symmetry centers compared near source center with the unchanged fit objective. Hard metrics, stems and continuation relations retained. Already symmetric bitmaps retain their fit before reflection is attempted. Unmatched or incompatible cases retain their fit. This is an experimental completion, not a paper/VTT port.</p><p>'+html.escape(str(counts))+'</p><p><a href="changes.html">Changes</a> · <a href="index.html">All pairs</a> · <a href="report.json">Full audit</a></p>'
    errors=''.join(f'<p>{r["key"]} {html.escape(r["char"])}: {html.escape(r["reason"])}</p>' for r in rows if r['status']=='failed')
    (out/'index.html').write_text(intro+errors+''.join(p for _,p in panels))
    (out/'changes.html').write_text(intro+errors+''.join(p for d,p in panels if d))
    if thumbs:
        height=max(t.height for t in thumbs)
        for chunk in range(0,len(thumbs),24):
            ts=thumbs[chunk:chunk+24];sheet=Image.new('RGB',(920,height*((len(ts)+3)//4)),'white')
            for i,t in enumerate(ts):sheet.paste(t,((i%4)*230,(i//4)*height))
            sheet.save(out/f'contact-{chunk//24}.png')
    print(counts)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--terminal-filter',action='store_true')
    parser.add_argument('--continuations',action='store_true'); parser.add_argument('--reflection',action='store_true'); args=parser.parse_args()
    run(args.terminal_filter,args.continuations,args.reflection)
