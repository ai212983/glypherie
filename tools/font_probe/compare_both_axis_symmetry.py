"""Bounded both-axis symmetry experiment driver (diagnostic experiment, not promotion).

Runs the CURRENT approved source pipeline (``build_source_bitmap.Pipeline``)
from original source for each key -- never consuming historical
checkpoints -- then applies the isolated ``both_axis_symmetry`` final
geometry proposal to the newly generated approved final. Candidates compile
to actual native TTF programs via ``Pipeline.install`` and render through
the real export path; verification uses native coords, native raster, and
export metrics only.

Output: ``tools/font_probe/out/both-axis-symmetry-v2/`` (report.json,
gallery PNGs with smooth source / current approved / proposed, index.html).

Usage from the repository root::

    OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe \\
        tools/font_probe/.venv/bin/python tools/font_probe/compare_both_axis_symmetry.py [--focus]
"""
import argparse
import html
import json
from pathlib import Path

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont

import both_axis_symmetry as bax
from audit_terminal_coverage import coords
from build_source_bitmap import FACES, Pipeline
from check_shamir_baseline import digest
from compare_diagonal_widths import metrics
from compare_paper_prototypes import render, pixels
from compare_shamir_pipeline import SIZES
from compare_shamir_representatives import comparison
from cross_section_widths import system
from serif_reference_view import prepend_reference

HERE = Path(__file__).resolve().parent
FULL_NAME = 'both-axis-symmetry-v2'
FOCUS_NAME = 'both-axis-symmetry-focus-v2'
FOCUS_KEYS = (('literata', 14),)
EXACT_BOUNDS = frozenset({'glyph-x-bound', 'glyph-y-bound'})
FROZEN_REF = HERE / 'out' / 'source-bitmap-constraints-v2'


class ExperimentPipeline(Pipeline):
    """Approved pipeline subclass; original stage methods run unmodified."""

    def __init__(self, output):
        super().__init__(output)
        self.saved_records = {}
        self.saved_baseline_font = {}

    def baseline(self, key, size, static_path):
        font_path, records = super().baseline(key, size, static_path)
        self.saved_records[key] = records
        self.saved_baseline_font[key] = str(font_path)
        return font_path, records


def _protected_selection(record, count, scale):
    matrix, rhs = system(record['graph'], count, scale)
    constraints = record['graph']['constraints']
    protected, bound, unknown_metric = [], [], []
    for i, c in enumerate(constraints):
        if c['kind'].startswith('P'):
            protected.append(i)
        elif c.get('metric'):
            if c.get('metric_role') in EXACT_BOUNDS:
                bound.append(i)
            else:
                protected.append(i)
                if c.get('metric_role') is None:
                    unknown_metric.append(c.get('id'))
    return matrix, rhs, protected, bound, unknown_metric


def _trace_levels(face, char, size, source_px, ends, flags, native, ink, scale):
    import audit_axis_placement as audit
    fitted_contours = audit.sample_outline(np.asarray(native, float) / scale,
                                           list(ends), list(flags), scale)
    source_contours = audit.sample_outline(np.asarray(source_px, float) / scale,
                                           list(ends), list(flags), scale)
    out = {}
    for ax, name in ((0, 'x'), (1, 'y')):
        s_box = (source_px[:, ax].min(), source_px[:, ax].max())
        f_box = (np.asarray(native)[:, ax].min(), np.asarray(native)[:, ax].max())
        box = audit.ink_box_of(set(ink)) if len(ink) else None
        out[name] = dict(
            source_levels=sorted(set(np.round(source_px[:, ax], 3).tolist())),
            fitted_levels=sorted(set(np.round(np.asarray(native)[:, ax], 3).tolist())),
            source_center=round((s_box[0] + s_box[1]) / 2, 4),
            fitted_center=round((f_box[0] + f_box[1]) / 2, 4),
            source_outline_max=round(
                audit.symmetry_error(source_contours, name, (s_box[0] + s_box[1]) / 2)['max'], 4),
            fitted_outline_max=round(
                audit.symmetry_error(fitted_contours, name, (f_box[0] + f_box[1]) / 2)['max'], 4),
            raster_mismatch=(audit.ink_mismatch(
                set(ink), name, audit.ink_axis_center(box, name))['mismatch']
                if box else 0))
    return out


def _frozen_reference_ink(key):
    path = FROZEN_REF / f'{key}-bitmap.json'
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return None


def _source_numeric_groups_features(font, char, p):
    """Numeric source groups/features stripped of glyph identity.

    Extracted from the final font only via
    ``shamir_model.feature_model(shamir_geometry.from_font(font, char,
    baseline=True), baseline=True)``. Asserts the model points EXACTLY
    match the final font coords and every group member maps exactly
    (records carry no groups; nothing is invented).
    """
    import shamir_geometry
    import shamir_model
    model = shamir_geometry.from_font(font, char, baseline=True)
    assert np.array_equal(np.asarray(model['points'], float),
                          np.asarray(p, float)), (char, 'source-points-mismatch')
    fm = shamir_model.feature_model(model, baseline=True)
    n = len(np.asarray(p))
    groups = []
    for g in fm.get('groups', ()):
        members = sorted(set(int(m) for m in g['members']))
        assert members and max(members) < n, (char, 'group-members-unmapped')
        groups.append({'normal': [float(v) for v in np.asarray(g['normal'], float)],
                       'members': members})
    features = []
    for f in fm.get('features', ()):
        if f.get('kind') not in ('stem', 'bar'):
            continue
        gids = [int(g) for g in f['groups']]
        assert all(0 <= g < len(groups) for g in gids), (char, 'feature-group-unmapped')
        features.append({'kind': f['kind'], 'groups': gids,
                         'width': float(f.get('width', 0.0)),
                         'length': float(f.get('length', 0.0)),
                         'normal': [float(v) for v in np.asarray(f['normal'], float)]})
    return groups, features


def _bind_pdist_targets(features, groups, record, matrix, rhs):
    """Bind per-feature PDist width targets from the actual system RHS.

    A feature gets ``target`` only when a PDist constraint's normal is
    cardinal along the feature axis and its point/sources lie in the
    corresponding opposite group members; target is abs(system RHS).
    """
    axis_of = {'stem': 0, 'bar': 1}
    constraints = record['graph']['constraints']
    for f in features:
        ax = axis_of[f['kind']]
        if len(f['groups']) != 2:
            continue
        sides = [set(groups[g]['members']) for g in f['groups']]
        for i, c in enumerate(constraints):
            if c.get('kind') != 'PDist':
                continue
            nrm = np.asarray(c.get('normal', (0, 0)), float)
            if abs(float(nrm[ax])) <= 0.999:
                continue
            pts = {int(c['point'])} | {int(a) for a in c.get('sources', ())}
            if ((pts & sides[0]) and (pts & sides[1])):
                f['target'] = int(round(abs(float(rhs[i]))))
                break


def _required_axes(audit):
    req = (audit.get('constraints') or {}).get('sym_axes')
    if req:
        return [int(a) for a in req]
    return [int(r['axis']) for r in audit.get('relationships', ())
            if r.get('type') == 'symmetry']


def run_key_proposals(pipe, name, size, out, rows, panels, records_out,
                      engine=None):
    key = f'{name}-{size}'
    key_rows, key_failures, sections, key_changes = pipe.run_key(name, size)
    records = pipe.saved_records[key]
    final_path = pipe.output / f'{key}-candidate.ttf'
    face = ft.Face(str(final_path))
    with TTFont(str(final_path)) as font:
        em = font['head'].unitsPerEm
        cmap = font.getBestCmap()
        glyphs = [(chr(c), n) for c, n in sorted(cmap.items())]
        outlines, advances = {}, {}
        for char, gname in glyphs:
            p, e, t = font['glyf'][gname].getCoordinates(font['glyf'])
            outlines[char] = (np.asarray(p, float), list(e), list(t))
            advances[char] = tuple(font['hmtx'][gname])
    scale = size / em
    # Baseline-native trace before the work dir closes.
    base_face = ft.Face(str(pipe.saved_baseline_font[key]))
    rows_by_char = {r['char']: r for r in key_rows if 'char' in r}
    jobs, changed = [], {}
    verify = {}
    frozen = _frozen_reference_ink(key)
    assert frozen is not None, (key, 'frozen-reference-absent')
    assert isinstance(frozen.get('glyphs'), dict), (key, 'frozen-schema')
    admitted = {c for c, _ in glyphs if c in rows_by_char and c in records}
    frozen_keys = set(frozen['glyphs'])
    frozen_key_diff = sorted(admitted ^ frozen_keys)
    key_failures = list(key_failures) + [('frozen-key-mismatch', c)
                                         for c in frozen_key_diff]
    assert not frozen_key_diff, (key, 'frozen-key-mismatch', frozen_key_diff)
    for char, _ in glyphs:
        row = rows_by_char.get(char)
        if row is None or char not in records:
            continue
        p, e, t = outlines[char]
        q = coords(face, char, size)
        current = render(face, char, size, hinted=True)
        base_native = coords(base_face, char, size, hinted=True)
        base_ink = pixels(render(base_face, char, size, hinted=True))
        ownership = row.get('upstream_audit', {}).get('ownership', ())
        ref = frozen['glyphs'][char]
        assert set(map(tuple, ref['ink'])) == set(pixels(current)), \
            (key, 'frozen-ink', char)
        assert np.array_equal(np.asarray(ref['native_points_px'], float),
                              np.asarray(q, float)), (key, 'frozen-native', char)
        assert tuple(ref['advance_hmtx']) == tuple(advances[char]), \
            (key, 'frozen-hmtx', char)
        matrix, rhs, protected, bound, unknown = _protected_selection(
            records[char], len(p), scale)
        audit_row = dict(key=key, char=char, unknown_metric_ids=unknown)
        eligible = bax._applies(np.asarray(p, float), list(e), list(t), scale) is not None
        if not eligible:
            audit_row.update(status='no-eligible-geometry', trials=0,
                             x_mismatch=-1, y_mismatch=-1)
            if frozen is not None:
                ref = (frozen.get('glyphs', {}) or {}).get(char)
                audit_row['frozen_reference_present'] = ref is not None
            rows.append(audit_row)
            continue
        if bax.mismatch(set(pixels(current)), [0, 1]) == 0:
            audit_row.update(status='already-symmetric', trials=0,
                             x_mismatch=0, y_mismatch=0)
            if frozen is not None:
                ref = (frozen.get('glyphs', {}) or {}).get(char)
                audit_row['frozen_reference_present'] = ref is not None
            rows.append(audit_row)
            continue
        if protected:
            viol = [int(records[char]['graph']['constraints'][i].get('id', i))
                    for i in protected
                    if abs(float(matrix[i] @ q.ravel()) - float(rhs[i])) > 1e-7]
            if viol:
                audit_row.update(status='held-baseline-violates', violating_ids=viol,
                                 trials=0, x_mismatch=-1, y_mismatch=-1)
                audit_row['trace_current'] = _trace_levels(
                    face, char, size, p * scale, e, t, q, pixels(current), scale)
                rows.append(audit_row)
                continue
        bound_res = {}
        for i in bound:
            cid = records[char]['graph']['constraints'][i].get('id', i)
            bound_res[str(cid)] = dict(
                before_px=round(float(abs(float(matrix[i] @ q.ravel())
                                             - float(rhs[i]))), 4))
        audit_row['bound_residual_before_px'] = bound_res
        prot = ((matrix[protected], rhs[protected]) if protected else None)

        def raster(v, _f=face, _c=char, _s=size):
            return pixels(render(_f, _c, _s, hinted=True, points=np.asarray(v, float)))

        after, audit = bax.fit(p, e, t, q, scale, raster,
                               ownership=ownership, protected=prot)
        audit_row.update(audit)
        if audit.get('status') == 'candidate':
            if bound:
                after_arr = np.asarray(after).ravel()
                audit_row['bound_targets'] = {
                    str(records[char]['graph']['constraints'][i].get('id', i)): dict(
                        old_target_px=round(float(rhs[i]), 4),
                        new_signed_px=round(float(matrix[i] @ after_arr), 4))
                    for i in bound}
            if protected:
                resid = np.abs(matrix[protected] @ np.asarray(after).ravel()
                               - rhs[protected])
                bad = [int(records[char]['graph']['constraints'][i].get('id', i))
                       for i, v in zip(protected, resid) if float(v) > 1e-7]
                if bad:
                    audit_row.update(status='held-protected-residual',
                                     blocking_ids=bad)
                    rows.append(audit_row)
                    continue
            jobs.append((char, size, (outlines[char][0], e, t), np.asarray(after)))
            verify[char] = (matrix, rhs, protected, ownership, np.asarray(q))
            audit_row['trace_current'] = _trace_levels(
                face, char, size, p * scale, e, t, q, pixels(current), scale)
            audit_row['trace_baseline'] = _trace_levels(
                base_face, char, size, p * scale, e, t,
                base_native, base_ink, scale)
            audit_row['pending'] = True
        else:
            if audit.get('status') == 'held' and protected and audit.get('blocked'):
                resid = np.abs(matrix[protected] @ q.ravel() - rhs[protected])
                audit_row['blocking_ids'] = [
                    int(records[char]['graph']['constraints'][i].get('id', i))
                    for i, v in zip(protected, resid) if float(v) > 1e-7]
            audit_row['trace_current'] = _trace_levels(
                face, char, size, p * scale, e, t, q, pixels(current), scale)
        if frozen is not None:
            ref = (frozen.get('glyphs', {}) or {}).get(char) \
                or (frozen.get('records', {}) or {}).get(char)
            audit_row['frozen_reference_present'] = ref is not None
        rows.append(audit_row)
    if jobs:
        target = out / f'{key}-proposed.ttf'
        pipe.install(final_path, target, [(c, s, (np.asarray(o[0]), o[1], o[2]), f)
                                          for c, s, o, f in jobs])
        new_face = ft.Face(str(target))
        changed_set = {c for c, _, _, _ in jobs}
        with TTFont(str(final_path)) as _before, TTFont(str(target)) as _after:
            _bc, _ac = _before.getBestCmap(), _after.getBestCmap()
            for other, _ in glyphs:
                if other in changed_set or other not in outlines:
                    continue
                assert np.array_equal(coords(new_face, other, size),
                                      coords(face, other, size)), \
                    (key, 'unaffected-coords', other)
                assert pixels(render(new_face, other, size, hinted=True)) == \
                    pixels(render(face, other, size, hinted=True)), \
                    (key, 'unaffected-bitmap', other)
                assert tuple(_after['hmtx'][_ac[ord(other)]]) == \
                    tuple(_before['hmtx'][_bc[ord(other)]]), \
                    (key, 'unaffected-hmtx', other)
        with TTFont(str(target)) as font:
            new_cmap = font.getBestCmap()
        for char, size_, outline, fitted in jobs:
            row = next(r for r in rows if r.get('key') == key and r.get('char') == char
                       and r.get('pending'))
            native = coords(new_face, char, size)
            assert np.max(abs(native - np.asarray(fitted))) <= 1 / 128 + 1e-9, (key, char)
            new = render(new_face, char, size, hinted=True)
            assert bax.mismatch(pixels(new), [0, 1]) == 0, (key, char)
            vmatrix, vrhs, vprot, vown, vq = verify[char]
            if vprot:
                vresid = np.abs(vmatrix[vprot] @ np.asarray(native).ravel()
                                - vrhs[vprot])
                assert bool(np.all(vresid <= 1e-7)), (key, 'final-protected', char)
            for _o in vown or ():
                assert abs(float(native[_o['point'], _o['axis']])
                           - float(_o['value'])) <= 1 / 64 + 1e-9, \
                    (key, 'final-ownership', char)
            _cur = pixels(render(face, char, size, hinted=True))
            for _ax in (0, 1):
                _lo = min(v[_ax] for v in _cur) if _cur else 0
                _hi = max(v[_ax] for v in _cur) if _cur else 0
                if len(_cur) and len(_cur ^ {tuple(_lo + _hi - v[j] if j == _ax
                                                  else v[j] for j in (0, 1))
                                             for v in _cur}) == 0:
                    assert np.array_equal(np.asarray(native)[:, _ax],
                                          np.asarray(vq)[:, _ax]), \
                        (key, 'final-symmetric-axis', char, _ax)
            with TTFont(str(target)) as font:
                assert tuple(font['hmtx'][new_cmap[ord(char)]]) == tuple(advances[char]), \
                    (key, char)
            current = render(face, char, size, hinted=True)
            q = coords(face, char, size)
            p = outlines[char][0]
            assert metrics(pixels(new), native, p * scale)['white_counters'] == \
                metrics(pixels(current), q, p * scale)['white_counters'], (key, char)
            row['changed_pixels'] = len(pixels(new) ^ pixels(current))
            row['trace_proposed'] = _trace_levels(
                new_face, char, size, p * scale, outlines[char][1],
                outlines[char][2], native, pixels(new), scale)
            row.pop('pending', None)
            stem = f'{key}-u{ord(char):04x}'
            panel = comparison(
                [current, new],
                ['Current approved final', 'Both-axis proposal'],
                f'{key} {char!r} both-axis')
            prepend_reference(face, char, size, f'{key} {char!r}',
                              [current, new], panel).save(
                                  out / 'img' / f'{stem}.png')
            row['panel'] = f'img/{stem}.png'
            tc, tp = row['trace_current'], row['trace_proposed']
            panels.append(
                f'<section id="{stem}"><h2>{html.escape(key)} {html.escape(char)} '
                f'U+{ord(char):04X}</h2><p>left-right mismatch '
                f'{tc["x"]["raster_mismatch"]} -&gt; {tp["x"]["raster_mismatch"]}; '
                f'top-bottom mismatch {tc["y"]["raster_mismatch"]} -&gt; '
                f'{tp["y"]["raster_mismatch"]}.</p>'
                f'<img loading="lazy" src="img/{stem}.png"></section>')
            changed[char] = True
    for r in rows:
        r.pop('pending', None)
    for r in rows:
        if r.get('panel'):
            assert (out / r['panel']).is_file(), (key, 'missing-panel', r['panel'])
    print(key, 'changed', sorted(changed), flush=True)
    return key_rows, key_failures, sections, key_changes


def run(keys, out_name):
    out = HERE / 'out' / out_name
    if out.exists():
        raise ValueError('output must be empty (remove it first)')
    out.mkdir(parents=True)
    (out / 'img').mkdir()
    inputs = {str(p.relative_to(HERE)): digest(p) for p in HERE.glob('*.py')}
    rows, panels = [], []
    key_failures_all = []
    for name, size in keys:
        pipe = ExperimentPipeline(out)
        pipe.note_sources()
        _, kf, _, _ = run_key_proposals(pipe, name, size, out, rows, panels, None)
        key_failures_all.extend(list(kf or []))
        pipe.verify_sources()
        pipe.close()
    for p in HERE.glob('*.py'):
        assert digest(p) == inputs[str(p.relative_to(HERE))], p
    (out / 'report.json').write_text(json.dumps(
        dict(keys=[f'{n}-{s}' for n, s in keys], cases=rows, inputs=inputs,
             key_failures=key_failures_all,
             key_failure_count=len(key_failures_all)),
        indent=1) + '\n')
    header = ('<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}'
              'img{max-width:100%}</style><h1>Both-axis symmetry experiment</h1>'
              '<p>Changed glyphs only: smooth source, current approved, proposed. '
              'Left-right AND top-bottom metrics labeled. Review arm lengths, '
              'thickness, and fidelity before any approval; '
              'no visual approval claimed.</p>')
    (out / 'index.html').write_text(header + ''.join(panels))
    held = [r for r in rows if str(r.get('status', '')).startswith('held')
            or r.get('status') in ('no-eligible-geometry',)]
    (out / 'diagnostics.html').write_text(
        header + '<pre>' + html.escape(json.dumps(held, indent=1,
                                                  default=str)) + '</pre>')
    from collections import Counter
    counts = dict(Counter(str(r.get('status')) for r in rows))
    print(counts)
    return rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--focus', action='store_true')
    args = ap.parse_args()
    if args.focus:
        run(list(FOCUS_KEYS), FOCUS_NAME)
    else:
        run([(n, s) for n in FACES for s in SIZES], FULL_NAME)
