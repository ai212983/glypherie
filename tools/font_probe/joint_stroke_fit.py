"""Experimental constrained least squares: hard metrics, soft stroke goals.

Source point and contour-edge displacement penalties each have weight 1;
each whole-side width/alignment residual has weight 4. These are explicit
experimental choices, not recovered Shamir or Microsoft policies.
"""
import re as _re

import numpy as np
from cross_section_widths import section, system
from shamir_baseline_solver import _round_pixel, evaluate_baseline


def constrained_fit(hard, values, goals, targets):
    hard = np.asarray(hard, float); values = np.asarray(values, float)
    goals = np.asarray(goals, float); targets = np.asarray(targets, float)
    count = goals.shape[1]
    if len(hard):
        _, s, vt = np.linalg.svd(hard, full_matrices=True)
        rank = int(np.sum(s > max(hard.shape)*np.finfo(float).eps*s[0]))
        origin = np.linalg.lstsq(hard, values, rcond=None)[0]
        if np.max(abs(hard @ origin-values)) > 1e-8:
            raise ValueError('incompatible metric/global constraints')
        null = vt[rank:].T
    else:
        origin = np.zeros(count); null = np.eye(count)
    q = origin + null @ np.linalg.lstsq(goals @ null, targets-goals @ origin, rcond=None)[0]
    if not np.isfinite(q).all() or (len(hard) and np.max(abs(hard @ q-values)) > 1e-7):
        raise ValueError('joint metric residual failed')
    return q


def terminal_competitor(points, feature, features):
    """A broad, short pair can be the ends of an intersecting longer bar."""
    if feature.get('length', float('inf')) >= feature['width']:
        return None
    p = np.asarray(points, float)
    def bounds(f):
        n = np.asarray(f['normal']); d = np.asarray(f['support_direction'])
        normal = p[f['points']] @ n
        corners = [n*a+d*b for a in (min(normal),max(normal))
                   for interval in f['support_intervals'] for b in interval]
        return np.min(corners,axis=0), np.max(corners,axis=0)
    lo,hi = bounds(feature)
    for i, other in enumerate(features):
        if other['kind'] not in ('stem','bar') or abs(np.dot(feature['normal'],other['normal'])) > 1e-8:
            continue
        if other.get('length',0) <= other['width'] or other['width'] >= feature['width'] or other['length'] <= feature['length']:
            continue
        a,b = bounds(other)
        if np.all(np.minimum(hi,b)-np.maximum(lo,a) > 1e-8):
            return i
    return None


def stem_relations(points, ends, record):
    """Exact cardinal contour runs belonging to detected stem/bar sides."""
    p = np.asarray(points, float); cs = record['graph']['constraints']
    rows, audit, width_ids = [], [], []
    for c in cs:
        name = c.get('feature', '')
        if not name.startswith('width-') or c['kind'] not in ('Dist', 'PDist'):
            continue
        f = record['features'][int(name.split('-')[1])]
        n = np.asarray(f['normal'])
        if f['kind'] not in ('stem', 'bar') or not np.any(abs(n) == 1):
            continue
        competing = terminal_competitor(p, f, record['features'])
        if competing is not None:
            audit.append(dict(id=c['id'], status='excluded-terminal-length', competing_feature=competing))
            continue
        sides = []
        for rep in f['points']:
            start = 0
            for end in ends:
                if start <= rep <= end:
                    break
                start = end+1
            members = {rep}
            for direction in (-1, 1):
                j = rep
                while True:
                    j = start+(j-start+direction) % (end-start+1)
                    if j in members or abs(float((p[j]-p[rep]) @ n)) > 1e-8:
                        break
                    members.add(j)
            sides.append(sorted(members))
        if any(len(side) < 2 for side in sides):
            audit.append(dict(id=c['id'], status='held', reason='incomplete straight-side support'))
            continue
        width_ids.append(c['id'])
        for side, rep in zip(sides, f['points']):
            for j in side:
                if j == rep:
                    continue
                row = np.zeros(p.size); row[2*j:2*j+2] += n; row[2*rep:2*rep+2] -= n
                rows.append(row)
        audit.append(dict(id=c['id'], status='protected', sides=sides, normal=n.tolist()))
    return rows, width_ids, audit


def continuation_relations(points, ends, flags, constraints, stems):
    """One adjoining straight segment within 5 degrees of a protected side.

    Preserve an existing unrounded alignment in its own direction. No recursive
    propagation, new point links, or glyph identities participate in selection.
    """
    p = np.asarray(points, float); adjacent = set(); start = 0
    for end in ends:
        for a in range(start, end+1):
            b = a+1 if a < end else start
            adjacent.add(frozenset((a,b)))
        start = end+1
    selected = {}
    for stem in stems:
        if stem['status'] != 'protected':
            continue
        normal = np.asarray(stem['normal'])
        for side in stem['sides']:
            members = set(side)
            for c in constraints:
                if c['kind'] != 'Dist' or c.get('round', True) or not c.get('feature','').startswith('align-'):
                    continue
                if len(c['sources']) != 1 or abs(c['value']) > 1e-8:
                    continue
                a, b = c['point'], c['sources'][0]
                if (a in members) == (b in members) or frozenset((a,b)) not in adjacent:
                    continue
                if not (flags[a] & 1 and flags[b] & 1):
                    continue
                n = np.asarray(c['normal']); cosine = abs(float(n @ normal))
                if not np.cos(np.deg2rad(5.)) <= cosine < 1-1e-12:
                    continue
                if abs(float((p[a]-p[b]) @ n)-c['value']) > 1e-6:
                    continue
                selected[c['id']] = dict(id=c['id'], points=[a,b], normal=n.tolist(),
                    angle_degrees=float(np.rad2deg(np.arccos(min(1.,cosine)))), stem_id=stem['id'])
    return list(selected.values())


_ALIGN_FEATURE = _re.compile(r'align-\d+\Z')
_CARDINAL_NORMALS = ((1., 0.), (-1., 0.), (0., 1.), (0., -1.))


def select_member_alignments(points, flags, constraints):
    """Select existing declared source-exact cardinal zero-alignment rows.

    Returns (selected_ids, skipped) where selected_ids lists constraint ids
    and skipped lists dicts {id, reason}. Geometry/constraints only: no
    glyph, family, or size identities participate. No new pairs are invented,
    no coordinate merging, no weight/metric changes, no new thresholds.
    """
    p = np.asarray(points, float)
    selected, skipped = [], []
    for c in constraints:
        cid = c.get('id')
        if c.get('kind') != 'Dist':
            skipped.append(dict(id=cid, reason='non-Dist-kind'))
            continue
        if not isinstance(c.get('feature', ''), str) or not _ALIGN_FEATURE.match(c.get('feature', '')):
            skipped.append(dict(id=cid, reason='non-align-feature'))
            continue
        if c.get('round', True) is not False:
            skipped.append(dict(id=cid, reason='rounded-or-missing-round-flag'))
            continue
        if c.get('value') != 0:
            skipped.append(dict(id=cid, reason='nonzero-value'))
            continue
        sources = c.get('sources', [])
        if not isinstance(sources, list) or len(sources) != 1:
            skipped.append(dict(id=cid, reason='not-exactly-one-source'))
            continue
        a, b = c.get('point'), sources[0]
        if not isinstance(a, int) or not isinstance(b, int) or isinstance(a, bool) or isinstance(b, bool):
            skipped.append(dict(id=cid, reason='non-integer-index'))
            continue
        if not (0 <= a < len(p) and 0 <= b < len(p)):
            skipped.append(dict(id=cid, reason='index-out-of-range'))
            continue
        try:
            n = (float(c['normal'][0]), float(c['normal'][1]))
        except (KeyError, TypeError, IndexError, ValueError):
            skipped.append(dict(id=cid, reason='invalid-normal'))
            continue
        if not np.isfinite(n[0]) or not np.isfinite(n[1]):
            skipped.append(dict(id=cid, reason='non-finite-normal'))
            continue
        if n not in _CARDINAL_NORMALS:
            skipped.append(dict(id=cid, reason='non-cardinal-normal'))
            continue
        try:
            fa, fb = flags[a], flags[b]
        except (IndexError, TypeError):
            skipped.append(dict(id=cid, reason='missing-flags'))
            continue
        if not (fa & 1 and fb & 1):
            skipped.append(dict(id=cid, reason='off-curve-endpoint'))
            continue
        if float((p[a]-p[b]) @ np.asarray(n)) != 0.:
            skipped.append(dict(id=cid, reason='source-projected-distance-nonzero'))
            continue
        selected.append(cid)
    return selected, skipped


def fit(points, ends, flags, record, scale, complete_stems=False, continuations=False, reflection_em=None, reflection_ink=None, upstream=None, ownership=(), order_relations=(), curve_reflection=False, preserve_member_alignments=False):  # noqa: PLR0913
    """Experimental constrained least squares with optional Shamir-style link preservation.

    Preserves existing declared source-exact cardinal member links throughout
    the solve when enabled. Default behavior is unchanged. This is a diagnostic
    constraint-preservation pass inside an experimental solver, not a claim of
    whole-model conformance with Shamir or Microsoft.
    """
    p = np.asarray(points, float); source = p.ravel()*scale; count = p.size
    original, values = system(record['graph'], len(p), scale)
    cs = record['graph']['constraints']
    protected = [i for i, c in enumerate(cs) if c.get('metric') or c['kind'].startswith('P')]
    extra, stem_audit = [], []
    if complete_stems:
        extra, ids, stem_audit = stem_relations(p, ends, record)
        protected = sorted(set(protected) | {i for i,c in enumerate(cs) if c['id'] in ids})
    continuation_audit = continuation_relations(p, ends, flags, cs, stem_audit) if continuations else []
    continuation_ids = {c['id'] for c in continuation_audit}
    protected = sorted(set(protected) | {i for i,c in enumerate(cs) if c['id'] in continuation_ids})
    member_audit, member_skipped, member_ids = [], [], []
    member_rows = []
    if preserve_member_alignments:
        member_ids, member_skipped = select_member_alignments(p, flags, cs)
        member_audit = [dict(id=i, status='protected', reason='existing-zero-alignment-preserved') for i in member_ids]
        member_rows = sorted(i for i, c in enumerate(cs) if c['id'] in member_ids)
    if preserve_member_alignments:
        protected = sorted(set(protected) | set(member_rows))
    reference = source if upstream is None else np.asarray(upstream, float).ravel()
    goals = list(np.eye(count)); targets = list(reference)
    start = 0
    for end in ends:
        for a in range(start, end+1):
            b = a+1 if a < end else start
            for axis in (0, 1):
                row = np.zeros(count); row[2*b+axis] = 1; row[2*a+axis] -= 1
                goals.append(row); targets.append(float(row @ reference))
        start = end+1
    audit = []
    for c in cs:
        name = c.get('feature', '')
        if not name.startswith('width-') or c['kind'] not in ('Dist', 'PDist'):
            continue
        f = record['features'][int(name.split('-')[1])]
        if f['kind'] != 'slant':
            continue
        if c['kind'] == 'PDist':
            audit.append(dict(id=c['id'], status='held', reason='font-wide target retained'))
            continue
        try:
            weights = section(p, ends, flags, f)
        except ValueError as exc:
            audit.append(dict(id=c['id'], status='held', reason=str(exc)))
            continue
        sides = [[i for i,w in weights.items() if w < 0], [i for i,w in weights.items() if w > 0]]
        n = np.asarray(f['normal']); width = _round_pixel(f['width']*scale)
        if width <= 0:
            raise ValueError('joint width target collapses')
        pairs = [(*side, 0.) for side in sides] + [(a, b, width) for a,b in zip(*sides)]
        indices = []
        for a,b,target in pairs:
            row = np.zeros(count); row[2*b:2*b+2] += n; row[2*a:2*a+2] -= n
            indices.append(len(goals)); goals.append(2*row); targets.append(2*target)
        audit.append(dict(id=c['id'], status='soft-goal', sides=sides, target_px=width, goal_indices=indices))
    if upstream is None and not any(a['status']=='soft-goal' for a in audit):
        q,_ = evaluate_baseline(record['graph'], p, scale, 1.)
        return q, dict(relations=audit, candidate_status='no-match', released_equations=[])
    hard = list(original[protected])+extra
    hard_values = list(values[protected])+[0.]*len(extra)
    for c in order_relations:
        row=np.zeros(count);row[2*c['b']+c['axis']]=1;row[2*c['a']+c['axis']]=-1
        hard.append(row);hard_values.append(c['value'])
    for owner in ownership:
        row = np.zeros(count); row[2*owner['point']+owner['axis']] = 1
        hard.append(row); hard_values.append(owner['value'])
    try:
        q = constrained_fit(hard, hard_values, goals, targets)
    except ValueError:
        if upstream is not None or not complete_stems:
            raise
        # Preserve the previous joint candidate on an incompatible proposal.
        q, audit = fit(points, ends, flags, record, scale, complete_stems=complete_stems if continuations else False, preserve_member_alignments=preserve_member_alignments)
        audit.update(candidate_status='held-continuation-conflict' if continuations else 'held-stem-conflict',
                     stem_relations=stem_audit, continuation_relations=continuation_audit)
        return q, audit
    reflection = dict(status='disabled')
    if reflection_em is not None:
        if reflection_ink is None:
            raise ValueError('reflection requires the current rendered bitmap')
        ink = set(reflection_ink)
        if not ink or ink == {(min(x for x,y in ink)+max(x for x,y in ink)-x,y) for x,y in ink}:
            reflection = dict(status='already-symmetric')
            reflection_em = None
    if reflection_em is not None:
        from feature_coordination import reflected_outline
        _, match = reflected_outline(p, q.reshape(-1,2), ends, flags, reflection_em)
        weighted_reflection = False
        if curve_reflection and match['status'] not in ('coordinated','ambiguous'):
            from outline_relationships import curve_correspondence
            match=curve_correspondence(p,ends,flags,reflection_em)
            weighted_reflection = True
        reflection = dict(status=match['status'], method='curve' if weighted_reflection else 'point', source_error_units=match.get('source_error_units'))
        if match['status']=='coordinated':
            pairs = match['pairs'] if weighted_reflection else sorted({tuple(sorted(pair)) for pair in match['pairs']})
            center = (p[:,0].min()+p[:,0].max())*scale/2
            nearest = _round_pixel(2*center)/2
            candidates = []
            for axis in [nearest+d/2 for d in (-2,-1,0,1,2)]:
                mirror_rows, mirror_values = [], []
                for a,b in pairs:
                    row = np.zeros(count)
                    if weighted_reflection:
                        row[::2]=a+b
                        mirror_rows.append(row);mirror_values.append(2*axis)
                        row=np.zeros(count);row[1::2]=a-b
                        mirror_rows.append(row);mirror_values.append(0.)
                    else:
                        row[2*a] += 1; row[2*b] += 1
                        mirror_rows.append(row); mirror_values.append(2*axis)
                        if a != b:
                            row = np.zeros(count); row[2*a+1] += 1; row[2*b+1] -= 1
                            mirror_rows.append(row); mirror_values.append(0.)
                try:
                    candidate = constrained_fit(hard+mirror_rows, hard_values+mirror_values, goals, targets)
                except ValueError:
                    continue
                score = float(np.sum((np.asarray(goals) @ candidate-targets)**2))
                candidates.append((score,abs(axis-center),axis,candidate))
            if candidates:
                score,_,axis,q = min(candidates,key=lambda c:c[:3])
                reflection = dict(status='fitted',method='curve' if weighted_reflection else 'point',axis_px=axis,source_residual_units=match['source_residual_units'],
                                  candidate_scores=[dict(axis_px=c[2],score=c[0]) for c in candidates])
            else:
                reflection = dict(status='held-conflict')
    for a in audit:
        if a['status']=='soft-goal':
            a['alignment_and_width_errors_px'] = [float((goals[i] @ q-targets[i])/2) for i in a['goal_indices']]
    changes = [dict(c, residual_px=float(original[i] @ q-values[i])) for i,c in enumerate(cs)
               if i not in protected and abs(original[i] @ q-values[i]) > 1e-7]
    result = dict(relations=audit, candidate_status='joint-fit',
        protected_ids=[cs[i]['id'] for i in protected], released_equations=changes,
        stem_relations=stem_audit,
        continuation_relations=continuation_audit,
        reflection=reflection,
        max_hard_residual_px=float(np.max(abs(np.asarray(hard) @ q-hard_values))) if hard else 0.)
    if preserve_member_alignments:
        result.update(member_alignment_relations=member_audit,
                      member_alignment_skipped=member_skipped,
                      experimental_status='member-alignment-preservation')
    return q.reshape(-1,2), result
