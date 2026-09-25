"""Opt-in complete-member preservation through the original-source pipeline.

Frozen outputs are comparison references only. The default fitter is unchanged.
"""
import argparse
from collections import Counter
from copy import deepcopy
import html
import json
from pathlib import Path

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont

import build_source_bitmap as bsb
import cumulative_hinter as cumulative
import source_bitmap_output as output
from audit_terminal_coverage import coords
from check_shamir_baseline import digest
from compare_paper_prototypes import pixels, render
from compare_shamir_pipeline import SIZES
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / 'out' / 'source-bitmap-constraints-v2'


def header():
    return ('<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}'
            'img{max-width:100%}section{border-bottom:1px solid #ddd;padding:16px 0}</style>'
            '<h1>Member alignment preservation — candidate</h1><p>'
            '<a href="index.html">Review</a> · <a href="all-affected.html">All affected</a> · '
            '<a href="diagnostics.html">Diagnostics</a></p>'
            '<p>Columns: smooth source / current approved / candidate. Review straight edges, '
            'stroke thickness and shape fidelity. Image approval is pending.</p>')


class CandidatePipeline(bsb.Pipeline):
    def __init__(self, path):
        super().__init__(path)
        self.fit_audit = []

    def cumulative(self, key, size, candidate_path, experiment_path, records, outcomes):
        original = cumulative.fit
        identities = {id(r): char for char, r in records.items()}

        def wrapped(*args, **kwargs):
            record = args[3]
            entry = dict(key=key, char=identities[id(record)],
                         phase='reflection' if kwargs.get('reflection_ink') is not None else 'initial',
                         ownership=deepcopy(kwargs.get('ownership', [])))
            try:
                result = original(*args, **dict(kwargs, preserve_member_alignments=True))
            except ValueError as exc:
                entry.update(status='held', reason=str(exc))
                self.fit_audit.append(entry)
                raise
            audit = result[1]
            selected = {r['id'] for r in audit.get('member_alignment_relations', [])}
            held = audit.get('reflection', {}).get('status', '').startswith('held')
            entry.update(status='held' if held else 'fitted', reason=audit.get('reflection', {}).get('status'), joint=deepcopy(audit), selected_equations=[
                deepcopy(c) for c in record['graph']['constraints'] if c['id'] in selected])
            self.fit_audit.append(entry)
            return result

        cumulative.fit = wrapped
        try:
            return super().cumulative(key, size, candidate_path, experiment_path, records, outcomes)
        finally:
            cumulative.fit = original


def symmetry(ink):
    if not ink:
        return dict(x=0, y=0)
    xs, ys = zip(*ink)
    return dict(x=len(ink ^ {(min(xs)+max(xs)-x, y) for x, y in ink}),
                y=len(ink ^ {(x, min(ys)+max(ys)-y) for x, y in ink}))


def verify_export(face, char, size, record):
    bitmap = render(face, char, size, hinted=True)
    native = coords(face, char, size)
    for field in ('codepoint', 'width', 'height', 'left', 'top', 'advance_26_6', 'pixels'):
        assert bitmap[field] == record[field], (char, field)
    assert np.array_equal(native, np.asarray(record['native_points_px'])), (char, 'native-export')
    return bitmap, native


def compare_key(pipe, key, size, generation_rows):
    old_path, new_path = REFERENCE / f'{key}-candidate.ttf', pipe.output / f'{key}-candidate.ttf'
    old_json = json.loads((REFERENCE / f'{key}-bitmap.json').read_text())['glyphs']
    new_json = json.loads((pipe.output / f'{key}-bitmap.json').read_text())['glyphs']
    old_face, new_face = ft.Face(str(old_path)), ft.Face(str(new_path))
    admissions = dict(new_admissions=sorted(new_json.keys()-old_json.keys()),
                      new_rejections=sorted(old_json.keys()-new_json.keys()))
    rows = []
    generation = {r['char']: r for r in generation_rows}
    with TTFont(old_path) as old, TTFont(new_path) as new:
        oc, nc = old.getBestCmap(), new.getBestCmap()
        assert set(nc) == {ord(c) for c in new_json}
        for char in sorted(old_json.keys() & new_json.keys()):
            before, bq = verify_export(old_face, char, size, old_json[char])
            after, aq = verify_export(new_face, char, size, new_json[char])
            old_outline = old['glyf'][oc[ord(char)]].getCoordinates(old['glyf'])
            new_outline = new['glyf'][nc[ord(char)]].getCoordinates(new['glyf'])
            assert all(np.array_equal(a, b) for a, b in zip(old_outline, new_outline)), (key, char, 'source')
            assert old['hmtx'][oc[ord(char)]] == new['hmtx'][nc[ord(char)]], (key, char, 'metrics')
            audits = [a for a in pipe.fit_audit if a['key'] == key and a['char'] == char]
            violations, max_residual, held = [], 0., []
            for a in audits:
                if a['status'] == 'held':
                    held.append(a['phase'] + ': ' + a['reason'])
                for c in a.get('selected_equations', []):
                    error = abs(float((aq[c['point']]-aq[c['sources'][0]]) @ c['normal']))
                    max_residual = max(max_residual, error)
                    if error > 1e-9:
                        violations.append(c['id'])
                for owner in a['ownership']:
                    if abs(aq[owner['point'], owner['axis']]-owner['value']) > 1/64+1e-9:
                        held.append('final ownership changed')
            if violations:
                held.append('later stage violates member alignment')
            if generation[char].get('status') == 'rejected':
                held.append('upstream rejection')
            old_ink, new_ink = pixels(before), pixels(after)
            delta = len(old_ink ^ new_ink)
            movement = float(np.max(abs(aq-bq))) if aq.size else 0.
            status = 'held' if held else 'candidate' if delta else 'native-only' if movement else 'unchanged'
            row = dict(key=key, char=char, status=status, bitmap_delta=delta,
                       native_delta=movement, max_member_residual=max_residual,
                       violating_ids=sorted(set(violations)), holds=sorted(set(held)),
                       symmetry_before=symmetry(old_ink), symmetry_after=symmetry(new_ink),
                       selected_count=len({c['id'] for a in audits for c in a.get('selected_equations', [])}))
            if delta or movement:
                stem = f'{key}-u{ord(char):04x}'
                panel = comparison([before, after], ['Current approved', 'Candidate'], f'{key} {char!r}')
                prepend_reference(old_face, char, size, f'{key} {char!r}', [before, after], panel).save(
                    pipe.output / 'img' / f'{stem}.png')
                row['image'] = f'img/{stem}.png'
            rows.append(row)
    return rows, admissions


def panel(row):
    if 'image' not in row:
        return ''
    stem = f"{row['key']}-u{ord(row['char']):04x}"
    label = 'Held diagnostic' if row['status'] == 'held' else 'Review candidate' if row['bitmap_delta'] else 'Native-only diagnostic'
    return (f'<section id="{stem}"><h2>{html.escape(row["key"])} '
            f'{html.escape(row["char"])} — {label}</h2><p>Changed pixels: {row["bitmap_delta"]}. '
            f'Left/right mismatch: {row["symmetry_before"]["x"]} → {row["symmetry_after"]["x"]}; '
            f'top/bottom: {row["symmetry_before"]["y"]} → {row["symmetry_after"]["y"]}.</p>'
            f'<p>{html.escape("; ".join(row["holds"]))}</p><img loading="lazy" src="{row["image"]}"></section>')


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--focus', action='store_true'); mode.add_argument('--full', action='store_true')
    ap.add_argument('--output')
    args = ap.parse_args()
    jobs = [(n, s) for n in bsb.FACES for s in SIZES] if args.full else [('source-sans-3', s) for s in (16, 20)]
    name = args.output or ('member-alignments-v2' if args.full else 'member-alignments-focus-v2')
    out = HERE / 'out' / name
    if out.exists() and any(out.iterdir()):
        raise ValueError('output must be empty')
    out.mkdir(parents=True, exist_ok=True); (out/'img').mkdir(exist_ok=True)
    pipe = CandidatePipeline(out)
    pipe.note_sources()
    refs, rows, admissions, failures, generation = {}, [], {}, [], []
    try:
        for face, size in jobs:
            key = f'{face}-{size}'
            for suffix in ('candidate.ttf', 'bitmap.json'):
                path = REFERENCE / f'{key}-{suffix}'
                refs[output.repo_relative(path)] = digest(path)
            generated, rejected, _, _, _, _ = pipe.run_key(face, size)
            generation.extend(generated); failures.extend(rejected)
            cases, admission = compare_key(pipe, key, size, generated)
            rows.extend(cases); admissions[key] = admission
            (out/f'{key}.html').write_text(header()+''.join(panel(r) for r in cases))
            print(key, dict(Counter(r['status'] for r in cases)), admission, flush=True)
        review = ''.join(panel(r) for r in rows if r['status'] == 'candidate')
        counts = dict(Counter(r['status'] for r in rows))
        intro = '<p>'+html.escape(str(counts))+'</p>'
        for filename in ('index.html', 'changes.html'):
            (out/filename).write_text(header()+intro+review)
        (out/'all-affected.html').write_text(header()+intro+''.join(panel(r) for r in rows))
        held = [r for r in rows if r['status'] in ('held', 'native-only')]
        (out/'diagnostics.html').write_text(header()+''.join(panel(r) for r in held)+'<pre>'+html.escape(
            json.dumps(dict(admissions=admissions, failures=failures, holds=held), default=bsb._json_default, indent=1))+'</pre>')
        report = dict(counts=counts, cases=rows, admissions=admissions, failures=failures,
                      generation=generation, fit_audit=pipe.fit_audit, inputs=pipe.inputs,
                      provenance=pipe.provenance, environment=output.environment(), reference_hashes=refs)
        (out/'report.json').write_text(json.dumps(report, default=bsb._json_default, indent=1)+'\n')
        pipe.verify_inputs_unchanged(); pipe.verify_sources()
        for path, sha in refs.items():
            assert digest(output.REPO_ROOT/path) == sha, path
    finally:
        pipe.close()


if __name__ == '__main__':
    main()
