"""Isolate material cross-section widths on the frozen 32-case comparison."""
import json
import argparse
import html
from pathlib import Path
from collections import Counter
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
from cross_section_widths import fit, system, section, export_graph
from compare_diagonal_widths import build, metrics
from compare_paper_prototypes import render, pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from shamir_baseline_solver import evaluate_baseline
from check_shamir_baseline import digest

HERE = Path(__file__).resolve().parent


def run(whole=False, protected=False, joint=False, stems=False, reflection=False):
    stems = stems or reflection
    joint = joint or stems
    whole = whole or protected or joint
    fitter = fit
    if whole:
        from whole_stroke_widths import fit as fitter
    if protected:
        from functools import partial
        fitter = partial(fitter, protected=True)
    if joint:
        from joint_stroke_fit import fit as fitter
    out = HERE/('out/protected-stroke-widths-v1' if protected else ('out/whole-stroke-widths-v1' if whole else 'out/cross-section-widths-v1'))
    if joint:
        out = HERE/"out/joint-stroke-widths-v1"
    if stems:
        from functools import partial
        fitter = partial(fitter, complete_stems=True)
        out = HERE/"out/joint-complete-stems-v1"
    if reflection:
        out = HERE/"out/joint-reflection-v1"
    out.mkdir(exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('output must be empty')
    old = HERE/'out/diagonal-widths-v1'
    input_paths = [old/'report.json']
    cases = json.loads(input_paths[0].read_text())['cases']
    rows, coverage, panels, thumbnails = [], [], [], []
    hashes = {}
    # Inventory support reconstruction across the complete detected repertoire.
    for uniform in sorted((HERE/'out/geometric-candidate-v3').glob('*-candidate.ttf')):
        key = uniform.stem.removesuffix('-candidate'); size = int(key.rsplit('-', 1)[1])
        ref = HERE/'out/shamir-representative-comparison'/f'{key}-experiment.ttf'
        model_path = ref.with_name(f'{key}-model.json')
        for path in (uniform, ref, model_path):
            hashes[str(path.relative_to(HERE))] = digest(path)
        records = json.loads(model_path.read_text())['records']
        with TTFont(uniform) as repertoire, TTFont(ref) as font:
            scale = size/font['head'].unitsPerEm
            for code in sorted(repertoire.getBestCmap()):
                char = chr(code); record = records[char]
                p, ends, flags = font['glyf'][font.getBestCmap()[code]].getCoordinates(font['glyf'])
                for i, f in enumerate(record['features']):
                    if f['kind'] != 'slant':
                        continue
                    row = dict(key=key, char=char, feature=i)
                    try:
                        weights = section(p, ends, flags, f)
                        measured = sum(w*np.asarray(p[j]) for j, w in weights.items()) @ f['normal']
                        assert abs(measured-f['width']) < 1e-6
                        row.update(status='reconstructed', error_units=abs(float(measured)-f['width']))
                    except ValueError as exc:
                        row.update(status='held', reason=str(exc))
                    coverage.append(row)
                prior = next((c for c in cases if c['key'] == key and c['char'] == char), None)
                if not prior or prior['status'] not in ('changed', 'same-bitmap'):
                    continue
                stem = f'{key}-u{code:04x}'; row = dict(key=key, char=char); rows.append(row)
                try:
                    base, _ = evaluate_baseline(record['graph'], p, size, font['head'].unitsPerEm)
                    matrix, rhs = system(record['graph'], len(p), scale)
                    assert np.max(abs(np.linalg.solve(matrix, rhs).reshape(-1, 2)-base)) < 1e-7
                    if reflection:
                        from joint_stroke_fit import fit as joint_fit
                        prior,_=joint_fit(p,ends,flags,record,scale,complete_stems=True,continuations=True)
                        current,_=build(ref,char,size,p,export_graph(prior,scale),out/f'{stem}-current.ttf')
                        q,audit=joint_fit(p,ends,flags,record,scale,complete_stems=True,continuations=True,reflection_em=font['head'].unitsPerEm,reflection_ink=pixels(current))
                    else:
                        q, audit = fitter(p, ends, flags, record, scale)
                    glyph, native = build(ref, char, size, p, export_graph(q, scale), out/f'{stem}.ttf')
                    assert np.max(abs(native-q)) <= 1/128+1e-9
                    before_path = old/f'{stem}-before.ttf'; direct_path = (HERE/'out/joint-stroke-widths-v1'/f'{stem}.ttf') if stems else ((HERE/'out/cross-section-widths-v1'/f'{stem}.ttf') if whole else old/f'{stem}-after.ttf')
                    for path in (before_path, direct_path):
                        hashes[str(path.relative_to(HERE))] = digest(path)
                    before = render(ft.Face(str(before_path)), char, size, hinted=True)
                    direct = render(ft.Face(str(direct_path)), char, size, hinted=True)
                    if reflection:
                        prior,_=joint_fit(p,ends,flags,record,scale,complete_stems=True,continuations=True)
                        direct,_=build(ref,char,size,p,export_graph(prior,scale),out/f'{stem}-before.ttf')
                    delta = len(pixels(before)^pixels(glyph))
                    previous_delta = len(pixels(direct)^pixels(glyph))
                    row.update(status='changed' if delta else 'same-bitmap', changed_pixels=delta, previous_column_changed_pixels=previous_delta, audit=audit,
                               before=metrics(pixels(before), base, np.asarray(p)*scale),
                               after=metrics(pixels(glyph), q, np.asarray(p)*scale))
                    for label, g in [('before', before), ('after', glyph)]:
                        ink = pixels(g); xs = [x for x, _ in ink]
                        row[label]['reflection_difference'] = len(ink^{(min(xs)+max(xs)-x, y) for x, y in ink})
                    glyphs = [before, direct, glyph]
                    panel = comparison(glyphs, ['Original equations', 'Current joint fit' if reflection else 'Previous joint fit' if stems else 'Midpoint experiment' if whole else 'Direct width substitution', 'Coordinated reflection' if reflection else 'Complete straight stems' if stems else 'Joint shape/width fit' if joint else ('Protected whole-side' if protected else ('Whole-side experiment' if whole else 'Cross-section relation'))], f'{key} {char!r}')
                    prepend_reference(ft.Face(str(ref)), char, size, f'{key} {char!r}', glyphs, panel).save(out/f'{stem}.png')
                    thumb = Image.new('RGB', (230, panel.height+20), 'white')
                    thumb.paste(panel.crop((2*panel.width//3, 0, panel.width, panel.height)), (0, 20))
                    ImageDraw.Draw(thumb).text((5, 0), stem, fill='black'); thumbnails.append(thumb)
                    panels.append((delta, f'<section id="{stem}"><h2>{key} {html.escape(char)}</h2><img src="{stem}.png"><p>{html.escape(audit.get('candidate_status', 'experimental'))}. {delta} pixels differ from original; {previous_delta} from middle column. Reflection: {row["before"]["reflection_difference"]} → {row["after"]["reflection_difference"]}. <a href="{stem}.json">Equations audit</a></p></section>'))
                except (ValueError, np.linalg.LinAlgError, ft.FT_Exception) as exc:
                    row.update(status='failed', reason=str(exc))
                (out/f'{stem}.json').write_text(json.dumps(row, indent=2)+'\n')
    for path in input_paths:
        hashes[str(path.relative_to(HERE))] = digest(path)
    assert all(digest(HERE/name) == sha for name, sha in hashes.items())
    counts = dict(Counter(r['status'] for r in rows))
    result = dict(counts=counts, support_coverage=dict(Counter(r['status'] for r in coverage)),
                  cases=rows, coverage=coverage, inputs=hashes,
                  sources={p.name:digest(p) for p in HERE.glob('*.py')})
    (out/'report.json').write_text(json.dumps(result, indent=2)+'\n')
    if thumbnails:
        height = max(t.height for t in thumbnails)
        sheet = Image.new('RGB', (920, height*((len(thumbnails)+3)//4)), 'white')
        for i, thumb in enumerate(thumbnails):
            sheet.paste(thumb, ((i%4)*230, (i//4)*height))
        sheet.save(out/'contact.png')
    failures = ''.join(f'<p>{r["key"]} {html.escape(r["char"])}: {html.escape(r["reason"])}</p>' for r in rows if r['status']=='failed')
    (out/'index.html').write_text('<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}section{margin:35px 0}</style><h1>Material cross-section width experiment</h1><p>Frozen 32-case scope; all 426 detected slants checked for source support reconstruction. Samples keep source edge interpolation weights. Nearest-pixel physical widths replace eligible local distances; font-wide PDist targets and ambiguous matches are held. Simultaneous solve, then requested-size export. No symmetry correction. Experimental; no production promotion.</p><p>'+html.escape(str(counts))+'</p><p><a href="report.json">Full audit and support holds</a></p>'+failures+''.join(p for _, p in sorted(panels, key=lambda v:-v[0])))
    if whole:
        page = out/'index.html'
        text = page.read_text().replace('Material cross-section width experiment', 'Whole-side width experiment')
        start = text.index('<p>Frozen'); end = text.index('</p>', start)+4
        text = text[:start]+'<p>Same 32 cases. Straight sides are parallelized to source feature direction and constrained at both ends. Whole-side geometry has priority; compatible global and metric anchors follow, then other original equations. Every released equation is recorded. PDist and unmatched supports are held. Midpoint experiment is the middle column. No symmetry correction. Experimental.</p>'+text[end:]
        text = text.replace('<h1>Whole-side width experiment</h1>', '<h1>Whole-side width experiment — rejected after visual audit</h1><p><strong>The geometry-first priority policy deforms w and X/x and can release metrics. Passing equation checks is insufficient. No promotion.</strong></p>')
        if protected:
            start = text.index('<h1>'); end = text.index('<p>{', start)
            text = text[:start]+'<h1>Protected whole-side experiment</h1><p>Original equations, midpoint experiment, protected whole-side result. All existing equations except admitted local width relations are preserved. Incompatible candidates return the original fit; held does not mean visually approved. No symmetry correction or promotion. Case audits identify conflicts.</p>'+text[end:]
        if joint:
            start = text.index('<h1>'); end = text.index('<p>{', start)
            text = text[:start]+'<h1>Joint stroke and source-shape experiment</h1><p>Original equations, midpoint experiment, joint fit. Metric and global constraints stay hard. Source coordinates and edge vectors have penalty weight 1; paired side alignment and width goals have weight 4. Soft goal residuals are reported. No symmetry correction. Experimental.</p>'+text[end:]
        if stems:
            text = text.replace('Joint stroke and source-shape experiment', 'Joint fit with complete straight stems').replace('Original equations, midpoint experiment, joint fit.', 'Original equations, previous joint fit, complete-stem candidate. Detected cardinal stem/bar widths and exact source-side alignment stay hard together. Incompatible proposals retain the previous joint fit.')
        if reflection:
            start=text.index('<h1>'); end=text.index('<p>{',start)
            text=text[:start]+'<h1>Coordinated reflection experiment</h1><p>Original equations, current joint fit, reflection-constrained joint fit. Source matching uses unique contour/tag correspondence within em/512. Mirrored coordinates are solved together; compatible half-pixel centers near the source center are compared using the unchanged objective. Hard metrics, stem and continuation relationships stay fixed. Unmatched/conflicting cases retain their current fit. Experimental.</p>'+text[end:]
        page.write_text(text)
    print(counts, result['support_coverage'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--whole", action="store_true")
    parser.add_argument("--protected", action="store_true")
    parser.add_argument("--joint", action="store_true")
    parser.add_argument("--stems", action="store_true")
    parser.add_argument("--reflection", action="store_true")
    args = parser.parse_args()
    run(args.whole, args.protected, args.joint, args.stems, args.reflection)
