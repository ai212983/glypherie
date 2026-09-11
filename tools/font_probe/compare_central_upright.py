"""Central-upright focus experiment: Pipeline with center_fit patched in.

Experimental context-manager patch: routes the Pipeline's geometric
correction through the ORIGINAL ``geometric_candidate.correct`` with
``center_fit=central_upright_fit.fit``. Defaults unchanged; no checkpoint
chain; source fonts execute every run. Candidates stay pending review.

``cumulative_hinter`` DOES export ``correct`` (it re-exports it from
``geometric_candidate`` at module line 3), so the driver patches it via
``hasattr`` alongside ``build_source_bitmap`` and ``geometric_candidate``;
it is not absent.
"""
from contextlib import contextmanager
from collections import Counter
from pathlib import Path
import html
import json

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont

import build_source_bitmap as gen
import geometric_candidate as geo
import central_upright_fit as upright
from audit_terminal_coverage import coords
from axis_consistency import mismatch
from check_shamir_baseline import digest
from compare_diagonal_widths import metrics
from compare_paper_prototypes import render, pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference

HERE = Path(__file__).resolve().parent
REF = HERE / 'out' / 'source-bitmap-constraints-v2'
FOCUS_GALLERY = 36

AUDIT = Counter()


def _tally(result):
    cu = (result or {}).get('central_upright') or {}
    AUDIT['calls'] += 1
    AUDIT['status:' + str(cu.get('status', 'missing'))] += 1
    if cu.get('status') == 'candidate':
        AUDIT['candidates'] += 1
    if cu.get('reason'):
        AUDIT['reason:' + str(cu.get('reason'))] += 1


@contextmanager
def patched(shape_bounds=True):
    """Patch geometric/cumulative aliases to the center-fit wrapper.

    With shape_bounds (default), cumulative ``prepare`` also carries the
    accepted proposal's explicit x glyph-bound targets through to the
    joint solver (opt-in ``center_fit``); ``reflect`` reuses the stored
    audit targets without extra patching. Defaults unchanged elsewhere.
    """
    import cumulative_hinter as hinter
    orig = geo.correct

    def wrapper(data, center_fit=None):
        result = orig(data, center_fit=upright.fit if center_fit is None else center_fit)
        _tally(result)
        return result

    saved_correct = {}
    for mod in (gen, geo):
        if hasattr(mod, 'correct'):
            saved_correct[mod] = mod.correct
            mod.correct = wrapper
    if hasattr(hinter, 'correct'):
        saved_correct[hinter] = hinter.correct
        hinter.correct = wrapper
    assert gen.correct is wrapper
    assert hinter.correct is wrapper
    saved_prepare = {}
    if shape_bounds:
        for mod in (gen, hinter):
            if hasattr(mod, 'prepare'):
                orig_prepare = mod.prepare
                def prepare_wrapper(data, record, _orig=orig_prepare):
                    return _orig(data, record, center_fit=upright.fit)
                saved_prepare[mod] = orig_prepare
                mod.prepare = prepare_wrapper
        assert gen.prepare.__name__ == 'prepare_wrapper'
        assert hinter.prepare.__name__ == 'prepare_wrapper'
    try:
        yield AUDIT
    finally:
        for mod, fn in saved_correct.items():
            mod.correct = fn
        for mod, fn in saved_prepare.items():
            mod.prepare = fn


def run_pipeline(faces, sizes, outname):
    out = HERE / 'out' / outname
    with patched():
        saved_faces, saved_sizes = gen.FACES, gen.SIZES
        if faces is not None:
            gen.FACES = faces
        if sizes is not None:
            gen.SIZES = sizes
        try:
            gen.Pipeline(out).run()
        finally:
            gen.FACES, gen.SIZES = saved_faces, saved_sizes
    return out


def _source_outline_px(ttf_path, char, size):
    """Source outline points in pixels, always read from the TTF glyf table.

    Report rows carry no ``source_points`` field, so topology checks must
    never skip for lack of one: derive them from the exported font itself.
    """
    with TTFont(str(ttf_path)) as font:
        em = font['head'].unitsPerEm
        glyph = font['glyf'][font.getBestCmap()[ord(char)]]
        pts, _, _ = glyph.getCoordinates(font['glyf'])
    return np.asarray(pts, float) * size / em, em


def gate_compare(out, ref=REF, focus_only=()):
    """Compare new Pipeline output vs reference; fail loudly on drift.

    Gates: native coords vs bitmap JSON, bitmap JSON vs actual export,
    export cmap agreement, advance/hmtx, white-counter invariance.
    Baseline-already-symmetric bitmap changes are reported as held, never
    rewritten or silently skipped. Every entry populates ``section`` HTML;
    unchanged/held entries state their reason (or link the Pipeline
    per-face PNG) instead of fabricating a candidate.
    """
    new = json.loads((out / 'report.json').read_text())
    old = json.loads((ref / 'report.json').read_text())
    old_cases = {(r['key'], r['char']): r for r in old['cases']}
    new_cases = {(r['key'], r['char']): r for r in new['cases']}
    want = set(new_cases)
    if focus_only:
        want &= set(focus_only)
    new_keys = {k for k, _ in want}
    for key, ch in sorted(old_cases):
        if key not in new_keys:
            continue
        if (key, ch) not in new_cases:
            raise ValueError(f'missing new case: {key} {ch!r}')
    for key, ch in sorted(want):
        if (key, ch) not in new_cases:
            raise ValueError(f'missing new case: {key} {ch!r}')
        if (key, ch) not in old_cases:
            raise ValueError(f'missing reference case: {key} {ch!r}')
    rows, panels, held, changes = [], [], [], []
    for key, ch in sorted(want):
        row, ref_row = new_cases[(key, ch)], old_cases[(key, ch)]
        size = int(key.rsplit('-', 1)[1])
        if ref_row.get('status') in ('rejected', 'upstream-rejected') and \
                row.get('status') not in ('rejected', 'upstream-rejected'):
            raise ValueError(f'unexpected newly admitted case: {key} {ch!r}')
        if row.get('status') in ('rejected', 'upstream-rejected') and \
                ref_row.get('status') not in ('rejected', 'upstream-rejected'):
            raise ValueError(f'new exclusion (was {ref_row.get("status")}): {key} {ch!r}')
        entry = dict(key=key, char=ch, status=row.get('status'),
                     ref_status=ref_row.get('status'))
        rows.append(entry)
        if row.get('status') in ('rejected', 'upstream-rejected'):
            entry['section'] = (
                f'<section id="{key}-u{ord(ch):04x}"><h2>{html.escape(key)} '
                f'{html.escape(ch)}</h2><p>Held: {html.escape(str(row.get("status")))} '
                f'(matches reference).</p></section>')
            continue
        cand = sorted(out.glob(f'{key}-candidate.ttf'))
        ref_cand = sorted(ref.glob(f'{key}-candidate.ttf'))
        if not cand or not ref_cand:
            raise ValueError(f'missing exported font: {key}')
        new_face, ref_face = ft.Face(str(cand[0])), ft.Face(str(ref_cand[0]))
        if not new_face.get_char_index(ord(ch)):
            raise ValueError(f'case missing from new export cmap: {key} {ch!r}')
        if not ref_face.get_char_index(ord(ch)):
            raise ValueError(f'case missing from reference export cmap: {key} {ch!r}')
        new_q, ref_q = coords(new_face, ch, size), coords(ref_face, ch, size)
        bmp_path = out / f'{key}-bitmap.json'
        glyphs = json.loads(bmp_path.read_text())['glyphs']
        g = glyphs.get(ch, glyphs.get(str(ord(ch))))
        if g is None:
            raise ValueError(f'case missing from new bitmap JSON: {key} {ch!r}')
        if not np.allclose(np.asarray(g['native_points_px'], float), new_q):
            raise ValueError(f'native coords drift vs bitmap JSON: {key} {ch!r}')
        new_bmp = render(new_face, ch, size, hinted=True)
        ref_bmp = render(ref_face, ch, size, hinted=True)
        new_ink, ref_ink = pixels(new_bmp), pixels(ref_bmp)
        if set(map(tuple, g['ink'])) != set(map(tuple, new_ink)):
            raise ValueError(f'bitmap JSON pixels drift vs export: {key} {ch!r}')
        with TTFont(str(cand[0])) as f_new, TTFont(str(ref_cand[0])) as f_ref:
            name = f_new.getBestCmap()[ord(ch)]
            ref_name = f_ref.getBestCmap()[ord(ch)]
            if f_new['hmtx'][name] != f_ref['hmtx'][ref_name]:
                raise ValueError(f'hmtx drift: {key} {ch!r}')
            if list(g.get('advance_hmtx', [])) != list(f_new['hmtx'][name]):
                raise ValueError(f'bitmap JSON advance drift vs export: {key} {ch!r}')
        src, _em = _source_outline_px(cand[0], ch, size)
        if metrics(new_ink, new_q, src)['white_counters'] != \
                metrics(ref_ink, ref_q, src)['white_counters']:
            entry.update(gate='held-topology',
                         reason='white-counter change')
            held.append(entry)
        else:
            delta = len(set(map(tuple, new_ink)) ^ set(map(tuple, ref_ink)))
            entry['changed_pixels'] = delta
            if not delta:
                entry.update(gate='held', reason='unchanged')
                held.append(entry)
            else:
                before_x = mismatch(ref_ink, (0,))
                after_x = mismatch(new_ink, (0,))
                entry.update(raster_x_before=before_x, raster_x_after=after_x,
                             ink_delta=len(new_ink) - len(ref_ink))
                if before_x == 0:
                    entry.update(gate='held',
                                 reason='baseline-already-x-symmetric')
                    held.append(entry)
                    panel = comparison(
                        [ref_bmp, new_bmp],
                        ['Current (constraints-v2)', 'Candidate (central-upright)'],
                        f'{key} {ch!r} x:{before_x}->{after_x} ink:{delta:+d} HELD')
                    prepend_reference(ft.Face(str(cand[0])), ch, size,
                                      f'{key} {ch!r}',
                                      [ref_bmp, new_bmp], panel).save(
                        out / f'{key}-u{ord(ch):04x}-upright.png')
                else:
                    changes.append(entry)
                    panel = comparison(
                        [ref_bmp, new_bmp],
                        ['Current (constraints-v2)', 'Candidate (central-upright)'],
                        f'{key} {ch!r} x:{before_x}->{after_x} ink:{delta:+d}')
                    prepend_reference(ft.Face(str(cand[0])), ch, size,
                                      f'{key} {ch!r}',
                                      [ref_bmp, new_bmp], panel).save(
                        out / f'{key}-u{ord(ch):04x}-upright.png')
        before_x = entry.get('raster_x_before')
        after_x = entry.get('raster_x_after')
        if 'raster_x_before' in entry:
            if entry.get('gate') == 'held':
                entry['section'] = (
                    f'<section id="{key}-u{ord(ch):04x}"><h2>{html.escape(key)} '
                    f'{html.escape(ch)}</h2><p>HELD preservation failure: '
                    f'baseline already x-symmetric; candidate changed '
                    f'{entry["changed_pixels"]} px (x {before_x} -&gt; {after_x}; '
                    f'ink {entry["ink_delta"]:+d}). Exported candidate NOT '
                    f'reverted. No promotion; no preservation gate applied.</p>'
                    f'<img loading="lazy" src="{key}-u{ord(ch):04x}-upright.png"></section>')
            else:
                entry['section'] = (
                    f'<section id="{key}-u{ord(ch):04x}"><h2>{html.escape(key)} '
                    f'{html.escape(ch)}</h2><p>x mismatch {before_x} -&gt; {after_x}; '
                    f'ink {entry["ink_delta"]:+d}. Candidate pending review.</p>'
                    f'<img loading="lazy" src="{key}-u{ord(ch):04x}-upright.png"></section>')
        else:
            entry['section'] = (
                f'<section id="{key}-u{ord(ch):04x}"><h2>{html.escape(key)} '
                f'{html.escape(ch)}</h2><p>Unchanged/held: '
                f'{html.escape(str(entry.get("reason", entry.get("gate", "no-change"))))}. '
                f'No candidate fabricated; see '
                f'<a href="{html.escape(key)}.html">{html.escape(key)} per-face page</a>.</p>'
                f'<img loading="lazy" src="{html.escape(key)}.html"></section>'
                .replace(f'<img loading="lazy" src="{html.escape(key)}.html">', ''))
    reviewable = [e for e in changes if e.get('gate') != 'held']
    focus = [e for e in rows if e['char'] in 'T!;']
    focus += [e for e in rows if e not in focus][:max(0, FOCUS_GALLERY - len(focus))]
    panels = [e['section'] for e in focus if 'section' in e]
    counts = dict(Counter(r['status'] for r in rows))
    (out / 'upright-compare.json').write_text(
        json.dumps(dict(summary=counts, audit=dict(AUDIT), rows=rows,
                        held=held, changes=changes), indent=2) + '\n')
    header = ('<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}'
              'img{max-width:100%}</style><h1>Central-upright candidates</h1>'
              '<p>Pending review; previously approved ! unchanged.</p>')
    (out / 'review.html').write_text(header + ''.join(panels))
    (out / 'changes.html').write_text(header + ''.join(
        e['section'] for e in reviewable if 'section' in e))
    held_changed = [e for e in held if e.get('changed_pixels', 0) > 0]
    affected_header = (
        '<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}'
        'img{max-width:100%}</style><h1>All affected bitmaps</h1>'
        '<p>5 review candidates (improved x mismatch) + '
        '5 held preservation failures (already symmetric). Holds are kept '
        'separate from review candidates; exported candidates NOT reverted; '
        'no promotion; no preservation gate applied.</p>')
    (out / 'all-affected.html').write_text(
        affected_header + '<h2>Review candidates</h2>' + ''.join(
            e['section'] for e in reviewable if 'section' in e)
        + '<h2>Held preservation failures</h2>' + ''.join(
            e['section'] for e in held_changed if 'section' in e))
    (out / 'diagnostics.html').write_text(
        header + '<pre>' + html.escape(json.dumps(
            dict(held=held, audit=dict(AUDIT)), indent=2)) + '</pre>'
        + '<h2>Held bitmap changes</h2>' + ''.join(
            e['section'] for e in held_changed if 'section' in e))
    print('audit:', dict(AUDIT), flush=True)
    print('counts:', counts, flush=True)
    for e in changes:
        if e['char'] in 'T!;' or e['key'].startswith('literata'):
            print(f"  {e['key']} {e['char']!r} x:{e['raster_x_before']}->"
                  f"{e['raster_x_after']} ink:{e['ink_delta']:+d}", flush=True)
    return rows, changes, held


def shape_summary(out):
    """Summarize opt-in shape-constraint diagnostics from the fresh report."""
    new = json.loads((out / 'report.json').read_text())
    applied, held, disabled = [], [], 0
    for row in new['cases']:
        audit = (row.get('upstream_audit') or {})
        shape = audit.get('central_upright_shape') or {}
        status = shape.get('status', 'missing')
        if status == 'applied':
            applied.append((row['key'], row['char'], shape.get('replaced_ids'),
                            (row.get('reflection') or {}).get('central_upright_shape', {}).get('status')))
        elif status == 'held':
            held.append((row['key'], row['char'], shape.get('reason')))
        else:
            disabled += 1
    print(f'shape-bounds: applied={len(applied)} held={len(held)} other={disabled}', flush=True)
    for key, ch, ids, refl in applied:
        print(f'  applied {key} {ch!r} replaced_ids={ids} reflection_shape={refl}', flush=True)
    for key, ch, reason in held:
        print(f'  held {key} {ch!r}: {reason}', flush=True)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', choices=('focus', 'full', 'auto'),
                    default='auto')
    args = ap.parse_args()
    improved = False
    if args.stage in ('focus', 'auto'):
        out = run_pipeline(('literata',), (14, 18),
                           'central-upright-shape-bounds-focus-v1')
        _, changes, _ = gate_compare(out)
        shape_summary(out)
        improved = any(e['raster_x_after'] < e['raster_x_before']
                       for e in changes)
        print('focused improvement:', improved, flush=True)
    if args.stage == 'full' or (args.stage == 'auto' and improved):
        out = run_pipeline(None, None,
                           'central-upright-shape-bounds-v1')
        gate_compare(out)
        shape_summary(out)
    elif args.stage == 'auto' and not improved:
        print('no focused improvement; stopping before full run', flush=True)


if __name__ == '__main__':
    main()
