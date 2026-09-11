"""Contour-local Ratio defaults for the baseline's unspecified reference choice.

Shamir 2003 §3.2 specifies Ratio defaults between key points but leaves their
selection unspecified. TrueType IUP supplies a primary-source topology precedent:
use preceding and following touched points along the same contour. We use that
neighbor selection with Shamir Ratio equations, including extrapolation; this is
not IUP's outside-interval shift rule. A single reference or a zero projected
span preserves the original signed offset through an unrounded Dist relation.
"""
import numpy as np
from shamir_constraints import relation


def complete_defaults(points, chosen, references, first_id, contours=None):
    """Fill free projections in place; contours are ordered native point IDs.

    Without contour information no topological relation is assumed, so completion
    retains the original coordinate. This is also used for the reduced graph.
    A contour with no references keeps its original coordinates independently of
    unrelated contours. Degenerate pairs choose the preceding contour reference.
    """
    points = np.asarray(points, float).reshape(-1, 2)
    references = set(map(int, references))
    if any(r < 0 or r >= len(points) for r in references):
        raise ValueError('baseline reference point outside outline')
    membership = {}
    for contour in (() if contours is None else contours):
        ids = list(map(int, contour))
        for i, p in enumerate(ids):
            if p < 0 or p >= len(points) or p in membership:
                raise ValueError('invalid or duplicate native contour point')
            membership[p] = (ids, i)
    if contours is not None and set(membership) != set(range(len(points))):
        raise ValueError('native contours must cover outline points exactly')
    for p in range(len(points)):
        group = chosen.setdefault(p, [])
        normals = ([np.array([-group[0]['normal'][1], group[0]['normal'][0]])]
                   if len(group) == 1 else list(np.eye(2)) if not group else [])
        for slot, n in enumerate(normals):
            c = relation('Abs', p, n, value=float(points[p] @ n), round=False,
                         default=True, id=first_id + 2*p + slot,
                         baseline_assumption='B08-contour-neighbor-ratio')
            pair = None
            if p in membership:
                ids, index = membership[p]
                before = next((ids[(index-k) % len(ids)] for k in range(1, len(ids))
                               if ids[(index-k) % len(ids)] in references), None)
                after = next((ids[(index+k) % len(ids)] for k in range(1, len(ids))
                              if ids[(index+k) % len(ids)] in references), None)
                if before is not None:
                    pair = before, after
            if pair is None:
                c['default_reason'] = 'no contour reference points'
            else:
                a, b = pair
                span = float((points[b]-points[a]) @ n)
                offset = float((points[p]-points[a]) @ n)
                c['default_reference_policy'] = 'preceding-following-contour-points'
                if a != b and span != 0:
                    c.update(kind='Ratio', sources=[a, b], value=offset/span)
                else:
                    c.update(kind='Dist', sources=[a], value=offset,
                             default_reason=('single contour reference' if a == b
                                             else 'zero projected contour-reference span'))
            group.append(c)
