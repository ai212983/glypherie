"""Stage-boundary trace of Literata +/T horizontal asymmetry (diagnostic only).

Runs the real source-to-bitmap generator (``build_source_bitmap.Pipeline``)
for literata-14 and literata-18 only, intercepting stage boundaries with a
``Pipeline`` subclass (``stage_font`` choke point + short ``geometric``
wrapper) and pass-through wrappers around the stage fitting functions.
No generator code is copied and no algorithm is changed: every wrapper
records its inputs/outputs then delegates.

Sampling reuses the corrected ``audit_axis_placement`` helpers and the
identical hinted render flags (``hinted=True``). A zero-shift/native
equality gate runs before any diagnosis. The only comparison reference is
the latest ``source-bitmap-constraints-v2`` report (source-to-source final
parity check for the focused keys); no old generated checkpoint is read
as an input.

Output: ``tools/font_probe/out/literata-axis-trace-v1/`` (JSON trace plus
before/after/source PNGs).

Usage from the repository root::

    OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe \\
        tools/font_probe/.venv/bin/python tools/font_probe/trace_literata_axes.py
"""

import hashlib
import json
import shutil
from pathlib import Path

import freetype as ft
import numpy as np

import audit_axis_placement as audit
import build_source_bitmap as gen
import cumulative_hinter as cumulative_mod
import geometric_candidate as geometric_mod
import joint_stroke_fit as joint_mod
import shared_stem_hinter as shared_mod
import repeated_component_symmetry as component_mod
import round_component_fit as round_mod
import curved_width_links as width_mod
import stem_relative_terminals as terminal_mod
from compare_paper_prototypes import render, pixels
from audit_terminal_coverage import coords

HERE = Path(__file__).resolve().parent
OUT_NAME = 'literata-axis-trace-v1'
REF_CONSTRAINTS = HERE / 'out' / 'source-bitmap-constraints-v2'
FOCUS = (('literata', 14, '+'), ('literata', 14, 'T'),
         ('literata', 18, '+'), ('literata', 18, 'T'))
MATERIAL_PX = 0.1

CALL_LOG = []


def _as_2d(value):
    try:
        arr = np.asarray(value, float)
    except (ValueError, TypeError):
        return None
    if arr.ndim == 2 and arr.shape[1] == 2 and arr.shape[0] > 2:
        return arr
    return None


def _sig(points):
    return hashlib.sha256(np.asarray(points, float).tobytes()).hexdigest()[:16]


def _wrap_callable(namespace, name, label):
    original = getattr(namespace, name)

    def wrapper(*args, **kwargs):
        before = []
        for value in list(args) + list(kwargs.values()):
            if hasattr(value, 'points'):
                value = value.points
            arr = _as_2d(value)
            if arr is not None:
                before.append(arr.copy())
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            CALL_LOG.append(dict(stage=label, status='raised', reason=str(exc)[:160],
                                 input_sig=_sig(before[0]) if before else None,
                                 n_points=int(before[0].shape[0]) if before else 0))
            raise
        after = []
        stack = [result]
        while stack:
            item = stack.pop()
            if hasattr(item, 'points'):
                stack.append(item.points)
            elif isinstance(item, np.ndarray) and item.ndim == 2 and item.shape[1] == 2:
                after.append(np.asarray(item, float))
            elif isinstance(item, (tuple, list)):
                stack.extend(item)
            elif isinstance(item, dict):
                stack.extend(item.values())
        motion = 0.0
        for b in before:
            for a in after:
                if a.shape == b.shape:
                    motion = max(motion, float(np.max(abs(a - b))))
        CALL_LOG.append(dict(stage=label, status='ok', input_sig=_sig(before[0]) if before else None,
                             n_points=int(before[0].shape[0]) if before else 0,
                             max_motion_px=round(motion, 4)))
        return result

    wrapper.__name__ = getattr(original, '__name__', name)
    wrapper.__wrapped__ = original
    setattr(namespace, name, wrapper)


def _orig(namespace, name):
    func = getattr(namespace, name)
    return getattr(func, '__wrapped__', func)


def _install_wrappers():
    # Patch call-site namespaces (each module binds its imports at load,
    # so the wrapper must live where the call is made, not where defined).
    _wrap_callable(gen, 'correct', 'geometric-correct')
    _wrap_callable(gen, 'finish', 'geometric-finish')
    _wrap_callable(gen, 'prepare', 'cumulative-prepare')
    _wrap_callable(gen, 'reflect', 'cumulative-reflect')
    _wrap_callable(gen, 'finalize', 'export-finalize')
    _wrap_callable(gen, 'component_fit', 'component-symmetry')
    _wrap_callable(gen, 'round_fit', 'round-symmetry')
    _wrap_callable(gen, 'curved_width_fit', 'branch-width-links')
    _wrap_callable(gen, 'terminal_fit', 'stem-relative-terminals')
    _wrap_callable(cumulative_mod, 'correct', 'prepare-geometric-correct')
    _wrap_callable(cumulative_mod, 'shared_fit', 'shared-stem')
    _wrap_callable(cumulative_mod, 'fit', 'joint-fit')


class TracingPipeline(gen.Pipeline):
    """Pipeline subclass snapshotting focused chars at each compile boundary."""

    def __init__(self, output, focus_chars):
        super().__init__(output)
        self.focus_chars = set(focus_chars)
        self.snapshots = {}

    def _snapshot(self, key, stage, font_path, size):
        face = ft.Face(str(font_path))
        for char in sorted(self.focus_chars):
            native = coords(face, char, size)
            plain = render(face, char, size, hinted=True)
            requant = render(face, char, size, points=native, hinted=True)
            if pixels(requant) != pixels(plain):
                raise ValueError(f'zero-shift/native equality failed: {key} {char!r} {stage}')
            self.snapshots.setdefault((key, char), []).append(dict(
                stage=stage, native=native.tolist(), ink=sorted(pixels(plain)),
                advance=plain['advance_26_6']))

    def geometric(self, key, size, experiment_path, records):
        target, outcomes = super().geometric(key, size, experiment_path, records)
        self._snapshot(key, 'geometric-candidate', target, size)
        return target, outcomes

    def stage_font(self, key, stage, base_path, jobs):
        target, natives = super().stage_font(key, stage, base_path, jobs)
        size = int(key.rsplit('-', 1)[1])
        self._snapshot(key, stage, target, size)
        return target, natives


def _measure(native, ink, source_px, ends, flags, scale):
    fitted_contours = audit.sample_outline(np.asarray(native, float) / scale,
                                           list(ends), list(flags), scale)
    source_contours = audit.sample_outline(np.asarray(source_px, float) / scale,
                                           list(ends), list(flags), scale)
    source_box = audit.extent_of(np.asarray(source_px, float))
    fitted_box = audit.extent_of(np.asarray(native, float))
    source_center = (source_box[0] + source_box[2]) / 2.0
    fitted_center = (fitted_box[0] + fitted_box[2]) / 2.0
    box = audit.ink_box_of(set(ink))
    raster_center = audit.ink_axis_center(box, 'x') if box else 0.0
    return dict(
        source_outline_max=round(audit.symmetry_error(source_contours, 'x', source_center)['max'], 4),
        fitted_outline_max=round(audit.symmetry_error(fitted_contours, 'x', fitted_center)['max'], 4),
        raster_mismatch=audit.ink_mismatch(set(ink), 'x', raster_center)['mismatch'] if box else None,
        source_center=round(source_center, 4), fitted_center=round(fitted_center, 4),
        raster_center=round(raster_center, 4),
        source_width=round(source_box[2] - source_box[0], 4),
        fitted_width=round(fitted_box[2] - fitted_box[0], 4),
        ink=len(ink))


def _mirror_groups(source_px, before, after, top=8):
    """Mirrored point groups and same-source-x splits, worst motion first."""
    source = np.asarray(source_px, float)
    before_a = np.asarray(before, float)
    after_a = np.asarray(after, float)
    center = (source[:, 0].min() + source[:, 0].max()) / 2.0
    by_x = {}
    for i, x in enumerate(source[:, 0]):
        by_x.setdefault(round(float(x), 3), []).append(i)
    rows = []
    for x, ids in by_x.items():
        moves = [round(float(abs(after_a[i, 0] - before_a[i, 0])), 4) for i in ids]
        afters = [round(float(after_a[i, 0]), 4) for i in ids]
        befores = [round(float(before_a[i, 0]), 4) for i in ids]
        partners = sorted({round(float(2.0 * center - source[i, 0]), 3) for i in ids})
        rows.append(dict(source_x=x, n=len(ids), before_x=befores, after_x=afters,
                         motion_x=moves, mirror_source_x=partners,
                         max_motion=round(max(moves), 4)))
    rows.sort(key=lambda r: (-r['max_motion'], r['source_x']))
    return [r for r in rows if r['max_motion'] > 0][:top]


def main():
    out = HERE / 'out' / OUT_NAME
    if out.exists():
        raise ValueError('output must be empty (remove it first)')
    out.mkdir(parents=True)
    (out / 'img').mkdir()
    _install_wrappers()

    ref_report = json.loads((REF_CONSTRAINTS / 'report.json').read_text())
    ref_native = {}
    for name, size, char in FOCUS:
        key = f'{name}-{size}'
        data = json.loads((REF_CONSTRAINTS / f'{key}-bitmap.json').read_text())
        glyphs = data['glyphs'].values() if isinstance(data['glyphs'], dict) else data['glyphs']
        ref_native[(key, char)] = {g['char']: g for g in glyphs}[char]

    trace, parity, first_offense, all_calls = {}, {}, {}, {}
    for name, size in sorted({(n, s) for n, s, _ in FOCUS}):
        key = f'{name}-{size}'
        chars = sorted({c for n, s, c in FOCUS if n == name and s == size})
        pipe = TracingPipeline(out / f'_work-{key}', chars)
        pipe.output.mkdir(parents=True, exist_ok=True)
        (pipe.output / 'img').mkdir(exist_ok=True)
        CALL_LOG.clear()
        static_path = pipe.instantiate(key, name, size)
        experiment_path, records = pipe.baseline(key, size, static_path)
        candidate_path, outcomes = pipe.geometric(key, size, experiment_path, records)
        exp_face = ft.Face(str(experiment_path))
        outlines = {}
        with __import__('fontTools.ttLib', fromlist=['TTFont']).TTFont(str(experiment_path)) as font:
            em = font['head'].unitsPerEm
            cmap = font.getBestCmap()
            for char in chars:
                points, ends, flags = font['glyf'][cmap[ord(char)]].getCoordinates(font['glyf'])
                outlines[char] = (np.asarray(points, float), list(ends), list(flags))
        scale = size / em
        source_snaps = {}
        for char in chars:
            points, ends, flags = outlines[char]
            source_px = points * scale
            base_native = coords(exp_face, char, size)
            base_ink = pixels(render(exp_face, char, size, hinted=True))
            source_snaps[char] = dict(source_px=source_px.tolist(), ends=ends, flags=flags,
                                      baseline_native=base_native.tolist(),
                                      source_measure=_measure(base_native, base_ink,
                                                              source_px, ends, flags, scale))
        live, case_rows = {}, {}
        for char, outcome in outcomes.items():
            if outcome['status'] != 'verified':
                continue
            points, ends, flags = outcome['outline']
            live[char] = dict(outline=(np.asarray(points, float), list(ends), list(flags)))
        prev_font, cum_cases, _, _ = pipe.cumulative(
            key, size, candidate_path, experiment_path, records, outcomes)
        for char, cum_row in cum_cases.items():
            row = case_rows.setdefault(char, dict(key=key, char=char, stages={}))
            row.update(status=cum_row.get('status'))
            if cum_row.get('status') == 'rejected':
                live.pop(char, None)
                continue
            live[char]['audit'] = cum_row['audit']
        round_font = pipe.symmetry_stages(key, size, prev_font, records, static_path, live, case_rows)
        curved_font, curved_produced = pipe.branch_stage(
            key, size, round_font, records, static_path, live, case_rows, 'curved-width-links', False)
        junction_font, junction_produced = pipe.branch_stage(
            key, size, round_font, records, static_path, live, case_rows, 'source-junctions', True)
        stem_input = pipe.overlay(key, size, 'stem-input', round_font,
                                  [(curved_font, curved_produced), (junction_font, junction_produced)])
        stem_font, stem_produced = pipe.terminal_stage(
            key, size, stem_input, records, static_path, live, case_rows)
        recovery_input = pipe.overlay(key, size, 'recovery-input', stem_input, [(stem_font, stem_produced)])
        rows, _, _, _ = pipe.export(key, size, candidate_path, recovery_input, live, case_rows)
        final_face = ft.Face(str(out / f'_work-{key}' / f'{key}-candidate.ttf'))
        for char in chars:
            final_native = coords(final_face, char, size)
            ref = np.asarray(ref_native[(key, char)]['native_points_px'], float)
            parity[f'{key} {char!r}'] = dict(
                max_drift_px=round(float(np.max(abs(final_native - ref))), 4),
                parity=bool(np.max(abs(final_native - ref)) <= 1 / 128 + 1e-9))
            points, ends, flags = outlines[char]
            source_px = points * scale
            from build_geometric_candidate import geometry as geometric_data
            stages = [dict(stage='source', native=source_px.tolist(), ink=None,
                           measure=_measure(source_px, set(), source_px, ends, flags, scale))]
            stages[0]['measure']['raster_mismatch'] = 0
            stages[0]['measure']['ink'] = 0
            stages.append(dict(stage='source-baseline', native=source_snaps[char]['baseline_native'],
                               measure=source_snaps[char]['source_measure']))
            for snap in pipe.snapshots.get((key, char), []):
                stages.append(dict(stage=snap['stage'],
                                   measure=_measure(np.asarray(snap['native']), set(snap['ink']),
                                                    source_px, ends, flags, scale),
                                   native=snap['native'], ink=snap['ink']))
            fsnap = dict(stage='export-final',
                         native=final_native.tolist(),
                         ink=sorted(pixels(render(final_face, char, size, hinted=True))),
                         measure=_measure(final_native,
                                          pixels(render(final_face, char, size, hinted=True)),
                                          source_px, ends, flags, scale))
            stages.append(fsnap)
            src_max = stages[0]['measure']['source_outline_max']
            graph = records[char]['graph']['constraints']
            offend, changes = None, []
            for idx in range(1, len(stages)):
                prev_s, snap = stages[idx - 1], stages[idx]
                m = snap['measure']
                amp = round(m['fitted_outline_max'] - src_max, 4)
                snap['amplification_vs_source_px'] = amp
                before_a = np.asarray(prev_s['native'], float)
                after_a = np.asarray(snap['native'], float)
                motion = round(float(np.max(abs(after_a - before_a))), 4)
                snap['motion_vs_prev_px'] = motion
                r_prev = prev_s['measure']['raster_mismatch']
                r_now = m['raster_mismatch']
                snap['raster_delta_vs_prev'] = (r_now - r_prev
                                               if r_prev is not None and r_now is not None else None)
                if offend is None and amp >= MATERIAL_PX:
                    offend = snap['stage']
                if motion > 0 or (snap['raster_delta_vs_prev'] or 0) != 0:
                    moved = [i for i, (b, a) in enumerate(zip(prev_s['native'], snap['native']))
                             if abs(a[0] - b[0]) > 1e-9 or abs(a[1] - b[1]) > 1e-9]
                    rel = [c for c in graph if c.get('point') in set(moved)
                           and (c.get('metric') or (c.get('normal') or [0, 0])[0] == 1)]
                    changes.append(dict(stage=snap['stage'], motion_px=motion,
                                        raster_delta=snap['raster_delta_vs_prev'],
                                        amplification_px=amp, moved_points=moved,
                                        mirror_groups=_mirror_groups(source_px, prev_s['native'],
                                                                     snap['native']),
                                        relevant_constraints=rel[:12],
                                        n_relevant_constraints=len(rel)))
            first_offense[f'{key} {char!r}'] = offend
            # Sub-stage decomposition of the first-offending transition by
            # direct re-invocation of the same pure fitting entry points.
            sub = {}
            if offend in ('source-baseline', 'geometric-candidate'):
                data = geometric_data(records[char], tuple(map(tuple, points)),
                                      tuple(ends), tuple(flags), size, em)
                result = _orig(gen, 'correct')(data)
                _, _, geo_expected = _orig(gen, 'finish')(result, data, 0)
                sub['geometric_finish_expected'] = np.asarray(geo_expected).tolist()
                sub['geometric_preterminal'] = np.asarray(result['preterminal']).tolist()
                base, current, audit_rec = _orig(gen, 'prepare')(data, records[char])
                sub['prepare_baseline'] = np.asarray(base).tolist()
                sub['prepare_current'] = np.asarray(current).tolist()
                sub['prepare_status'] = audit_rec.get('status')
                sub['prepare_support'] = audit_rec.get('coordinated_support', {})
                try:
                    shared, _ = _orig(cumulative_mod, 'shared_fit')(
                        tuple(map(tuple, points)), records[char], size, em,
                        coordinate=True, ends=tuple(ends), flags=tuple(flags))
                    sub['shared_direct'] = None if shared is None else np.asarray(shared).tolist()
                except Exception as exc:
                    sub['shared_direct'] = f'held: {str(exc)[:160]}'
                sub['ownership'] = audit_rec.get('ownership', [])
                sub['order_relations'] = audit_rec.get('order_relations', [])
            trace[f'{key} {char!r}'] = dict(
                stages=[{k: v for k, v in s.items() if k != 'native'} for s in stages],
                first_offense_stage=offend, changes=changes, sub_stages=sub)
            from compare_shamir_representatives import comparison
            from serif_reference_view import prepend_reference
            cur = render(final_face, char, size, hinted=True)
            cand_face = ft.Face(str(candidate_path))
            geo = render(cand_face, char, size, hinted=True)
            title = f'{key} {char!r} diagnostic'
            panel = comparison([geo, cur], ['Geometric/current', 'Final hinted'], title)
            prepend_reference(exp_face, char, size, title, [geo, cur], panel).save(
                out / 'img' / f'{key}-u{ord(char):04x}.png')
        all_calls[key] = list(CALL_LOG)
        shutil.rmtree(out / f'_work-{key}', ignore_errors=True)

    payload = dict(focus=[dict(key=f'{n}-{s}', char=c) for n, s, c in FOCUS],
                   material_threshold_px=MATERIAL_PX,
                   first_offense_stage=first_offense,
                   final_parity_vs_constraints_v2=parity,
                   sub_stage_calls=all_calls,
                   cases=trace)
    (out / 'trace.json').write_text(json.dumps(payload, indent=1) + '\n')
    lines = ['# Literata axis trace: first material horizontal-asymmetry amplification',
             f'# material threshold: >= {MATERIAL_PX}px fitted-outline max growth vs source',
             '']
    for case in sorted(trace):
        stages = trace[case]['stages']
        symbols = ' -> '.join(f"{s['stage']}:{s['measure']['fitted_outline_max']:.3f}"
                              f"(r{s['measure']['raster_mismatch']})"
                              for s in stages)
        lines.append(f"== {case} first={first_offense[case]} parity={parity[case]['parity']} "
                     f"drift={parity[case]['max_drift_px']}px")
        lines.append(f"   {symbols}")
        for ch in trace[case]['changes']:
            lines.append(f"   [{ch['stage']}] motion={ch['motion_px']}px "
                         f"raster_delta={ch['raster_delta']} amp={ch['amplification_px']}px "
                         f"moved={ch['moved_points']} rel_constraints={ch['n_relevant_constraints']}")
            for g in ch['mirror_groups'][:4]:
                lines.append(f"      src_x={g['source_x']} before={g['before_x']} after={g['after_x']}")
    (out / 'summary.txt').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
