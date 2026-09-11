"""Whole-side experiment: geometry first, then compatible existing anchors.

Small source taper is flattened to the source feature normal. Conflicting old
equations are reported, never softened. This is an experimental priority policy.
"""
import numpy as np
from cross_section_widths import section, system
from shamir_baseline_solver import _round_pixel


def select(rows, values, dimension):
    """Incremental orthogonal equations; return explicit incompatible rows."""
    basis, targets, accepted, rejected = [], [], [], []
    for i, (row, value) in enumerate(zip(rows, values)):
        v = np.array(row, float); rhs = float(value)
        for _ in range(2):
            for q, b in zip(basis, targets):
                projection = float(v @ q); v -= projection*q; rhs -= projection*b
        norm = float(np.linalg.norm(v))
        if norm < 1e-10:
            if abs(rhs) > 1e-8:
                rejected.append(i)
            continue
        basis.append(v/norm); targets.append(rhs/norm); accepted.append(i)
    fitted = np.asarray(basis).T @ np.asarray(targets) if basis else np.zeros(dimension)
    return fitted, accepted, rejected, len(basis)


def fit(points, ends, flags, record, scale, protected=False):
    p = np.asarray(points, float); dimension = p.size
    original, targets = system(record['graph'], len(p), scale)
    rows, values, relations = [], [], []
    for c in record['graph']['constraints']:
        name = c.get('feature', '')
        if not name.startswith('width-') or c['kind'] not in ('Dist', 'PDist'):
            continue
        f = record['features'][int(name.split('-')[1])]
        if f['kind'] != 'slant':
            continue
        if c['kind'] == 'PDist':
            relations.append(dict(id=c['id'], status='held', reason='font-wide parameter policy unresolved'))
            continue
        try:
            weights = section(p, ends, flags, f)
        except ValueError as exc:
            relations.append(dict(id=c['id'], status='held', reason=str(exc)))
            continue
        sides = [[i for i, w in weights.items() if w < 0],
                 [i for i, w in weights.items() if w > 0]]
        n = np.asarray(f['normal']); width = _round_pixel(f['width']*scale)
        if width <= 0:
            raise ValueError('whole stroke width collapses')
        def relation(a, b):
            r = np.zeros(dimension); r[2*b:2*b+2] += n; r[2*a:2*a+2] -= n
            return r
        new = [relation(*side) for side in sides] + [relation(sides[0][0], sides[1][0])]
        _, _, conflicts, _ = select(rows+new, values+[0., 0., width], dimension)
        if conflicts:
            relations.append(dict(id=c['id'], status='held', reason='incompatible whole-side geometry'))
            continue
        rows.extend(new); values.extend([0., 0., width])
        relations.append(dict(id=c['id'], status='replaced', sides=sides, normal=n.tolist(), target_px=width))
    geometry_count = len(rows)
    if protected:
        # Replace only the admitted local width relations. Everything else,
        # including metrics, global parameters and junction links, stays hard.
        cs = record['graph']['constraints']
        replaced = {r['id'] for r in relations if r['status'] == 'replaced'}
        retained = [i for i, c in enumerate(cs) if c['id'] not in replaced]
        all_rows = [original[i] for i in retained]+rows
        all_values = [targets[i] for i in retained]+values
        q, accepted, rejected, rank = select(all_rows, all_values, dimension)
        if rejected or rank != dimension:
            from shamir_baseline_solver import evaluate_baseline
            baseline, _ = evaluate_baseline(record['graph'], p, scale, 1.)
            conflict = [dict(row=i-len(retained),
                            residual_at_original_px=float(all_rows[i] @ baseline.ravel()-all_values[i]))
                        for i in rejected]
            for r in relations:
                if r['status'] == 'replaced':
                    r.update(status='held', reason='candidate conflicts with protected equations')
            return baseline, dict(relations=relations, candidate_status='held',
                                  conflicts=conflict, released_equations=[],
                                  protected_ids=[cs[i]['id'] for i in retained])
        residual = float(np.max(abs(np.asarray(all_rows) @ q-all_values)))
        if residual > 1e-7 or not np.isfinite(q).all():
            raise ValueError('protected equation residual failed')
        return q.reshape(-1, 2), dict(relations=relations,
            candidate_status='fitted' if replaced else 'no-match',
            equation_residual_px=residual, released_equations=[],
            protected_ids=[cs[i]['id'] for i in retained])
    # Retain global and metric anchors first; preserve recorded order for ties.
    cs = record['graph']['constraints']
    order = sorted(range(len(cs)), key=lambda i:(not cs[i]['kind'].startswith('P'),
                    not bool(cs[i].get('metric')), bool(cs[i].get('default')), i))
    rows.extend(original[i] for i in order); values.extend(targets[i] for i in order)
    q, accepted, rejected, rank = select(rows, values, dimension)
    if rank != dimension:
        raise ValueError('whole-side system underdetermined')
    residual = float(np.max(abs(np.asarray(rows)[accepted] @ q-np.asarray(values)[accepted])))
    if residual > 1e-7 or not np.isfinite(q).all():
        raise ValueError('whole-side equation residual failed')
    q = q.reshape(-1, 2)
    for r in relations:
        if r['status'] != 'replaced':
            continue
        a, b = r['sides']; n = np.asarray(r['normal'])
        r['end_widths_px'] = [float((q[j]-q[i]) @ n) for i, j in zip(a, b)]
        assert max(abs(w-r['target_px']) for w in r['end_widths_px']) < 1e-7
    return q, dict(relations=relations, equation_residual_px=residual,
                   geometry_equations=geometry_count,
                   released_equations=[dict(cs[order[i-geometry_count]],
                       residual_px=float(original[order[i-geometry_count]] @ q.ravel()-targets[order[i-geometry_count]]))
                       for i in rejected if i >= geometry_count])
