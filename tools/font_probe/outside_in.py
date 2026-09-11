"""Recover metric-bound stroke relations before uniform correction construction.

Project policy: an outer metric anchor may control an ordinary stroke distance
inward, replacing one parallel non-metric Abs at the other side. Ambiguous
ownership is reported instead of choosing a correction by identity.
"""
from dataclasses import replace
import numpy as np


def recover(data, lost):
    cs=[dict(c) for c in data.constraints];changes=[];held=[];used=set()
    for width in lost:
        outer=width['point'];inner,=width['sources'];n=np.asarray(width['normal'])
        def parallel(c):return abs(abs(float(np.asarray(c['normal'])@n))-1)<1e-12
        metric=[c for c in cs if c['point']==outer and c.get('metric') and parallel(c)]
        if not metric:continue
        anchors=[c for c in cs if c['point']==inner and c['kind']=='Abs' and not c.get('metric') and parallel(c)]
        if len(anchors)!=1 or (inner,tuple(n)) in used:
            held.append(dict(width=width,reason='requires one unclaimed ordinary inner anchor'));continue
        anchor,=anchors
        if any(c.get('feature')==width.get('feature') for c in cs):continue
        reversed_width=dict(width,point=inner,sources=[outer],value=-width['value'],id=anchor['id'])
        cs[cs.index(anchor)]=reversed_width;used.add((inner,tuple(n)))
        changes.append(dict(restored=width,reversed=reversed_width,removed=anchor,metric=metric))
    return replace(data,constraints=tuple(cs)),changes,held
