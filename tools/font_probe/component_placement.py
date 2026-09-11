"""Experimental component graph placement, with no semantic shape recognition.

Every disconnected filled component includes its nested contours. All component
center vectors receive equal weight. Near-translated repeated components keep
integer translation phase; other components may translate in 26.6 units.
"""
from itertools import product
import numpy as np
from shapely.affinity import translate
from repeated_rings import contours


def place(source, fitted, tags, ends, em, ppem):
    source=np.asarray(source,float); fitted=np.asarray(fitted,float)
    cs=contours(source,tags,ends)
    if any(not c['poly'].is_valid for c in cs):return fitted.copy(),dict(status='held',reason='invalid contour')
    roots=[i for i,c in enumerate(cs) if not any(j!=i and d['poly'].contains(c['poly']) for j,d in enumerate(cs))]
    if len(roots)<2:return fitted.copy(),dict(status='unchanged',reason='single component')
    if len(roots)>8:return fitted.copy(),dict(status='held',reason='more than eight components')
    if any(cs[a]['poly'].intersects(cs[b]['poly']) for i,a in enumerate(roots) for b in roots[i+1:]):
        return fitted.copy(),dict(status='held',reason='overlapping components')
    groups=[];boundaries=[]
    for root in roots:
        members=[i for i,c in enumerate(cs) if i==root or cs[root]['poly'].contains(c['poly'])]
        groups.append(np.concatenate([cs[i]['ids'] for i in members]))
        boundary=cs[root]['poly'].boundary
        for i in members:
            if i!=root:boundary=boundary.union(cs[i]['poly'].boundary)
        boundaries.append((translate(boundary,xoff=-cs[root]['lo'][0],yoff=-cs[root]['lo'][1]),len(members)))
    locked=set(); matches=[]
    for i,(a,na) in enumerate(boundaries):
        for j in range(i+1,len(boundaries)):
            b,nb=boundaries[j]
            if na==nb and a.hausdorff_distance(b)<=.004*em:
                locked.update((i,j));matches.append([i,j])
    fixed=sorted(locked);free=[i for i in range(len(groups)) if i not in locked]
    if len(fixed)>4:return fitted.copy(),dict(status='held',reason='more than four repeated components')
    def centers(points):return np.array([(points[g].min(0)+points[g].max(0))/2 for g in groups])
    sc=centers(source)*ppem/em; fc=centers(fitted);n=len(groups)
    lap=n*np.eye(n)-np.ones((n,n));matrix=lap+.05*np.eye(n);rhs=-lap@(fc-sc)
    delta=np.zeros((n,2))
    for axis in range(2):
        best=None
        for shifts in product((-1,0,1),repeat=len(fixed)):
            d=np.zeros(n);d[fixed]=shifts
            if free:
                d[free]=np.linalg.solve(matrix[np.ix_(free,free)],rhs[free,axis]-matrix[np.ix_(free,fixed)]@d[fixed])
                d[free]=np.rint(d[free]*64)/64
            residual=fc[:,axis]+d-sc[:,axis]
            score=float(residual@lap@residual+.05*(d@d))
            key=(score,float(d@d),tuple(d))
            if best is None or key<best[0]:best=(key,d)
        delta[:,axis]=best[1]
    out=fitted.copy()
    for ids,d in zip(groups,delta):out[ids]+=d
    def error(c):
        d=c-sc
        return float(np.sqrt(sum(np.sum((d[i]-d[j])**2) for i in range(n) for j in range(i+1,n))))
    return out,dict(status='placed',components=[g.tolist() for g in groups],repeated_pairs=matches,
        translations_px=delta.tolist(),relative_error_before_px=error(fc),relative_error_after_px=error(fc+delta))
