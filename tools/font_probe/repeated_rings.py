"""Geometry-only repeated-ring experiment; source-derived affine contour fitting.

This is a separate extension, not Shamir's constraint solver. Recognition uses
translation-normalized sampled curves (0.004 em Hausdorff tolerance). Only isolated
outer contours containing exactly one counter and unambiguous pairs are supported.
"""
import numpy as np
from shapely.geometry import Polygon
from shapely.affinity import translate
from hobby_prototype import segments, evaluate


def contours(points, tags, ends):
    result=[]; start=0
    for end in ends:
        ids=np.arange(start,end+1); p=points[ids]; start=end+1
        curves=segments(p,[tags[i] for i in ids],[len(ids)-1])
        samples=np.array([evaluate(c,t)@p for c in curves for t in np.linspace(0,1,33)[:-1]])
        poly=Polygon(samples)
        result.append(dict(ids=ids,poly=poly,lo=p.min(axis=0),hi=p.max(axis=0)))
    return result


def fit(source, fitted, tags, ends, em, ppem):
    source=np.asarray(source,float); fitted=np.asarray(fitted,float)
    cs=contours(source,tags,ends); tol=.004*em
    parents=[]
    for i,c in enumerate(cs):
        parents.append([j for j,d in enumerate(cs) if i!=j and d['poly'].contains(c['poly'])])
    rings=[]
    for i,c in enumerate(cs):
        children=[j for j,p in enumerate(parents) if p==[i]]
        if parents[i] or len(children)!=1:continue
        j=children[0]
        if any(parents[k] and j in parents[k] for k in range(len(cs))):continue
        if any(k not in (i,j) and c['poly'].intersects(d['poly']) for k,d in enumerate(cs)):continue
        if not c['poly'].is_valid or not cs[j]['poly'].is_valid:continue
        rings.append((i,j))
    matches=[]
    for a,r in enumerate(rings):
        for s in rings[a+1:]:
            errors=[]
            for u,v in zip(r,s):
                p=translate(cs[u]['poly'],xoff=-cs[r[0]]['lo'][0],yoff=-cs[r[0]]['lo'][1])
                q=translate(cs[v]['poly'],xoff=-cs[s[0]]['lo'][0],yoff=-cs[s[0]]['lo'][1])
                errors.append(p.hausdorff_distance(q))
            if max(errors)<=tol:matches.append((r,s,errors))
    result=fitted.copy(); records=[]
    for r,s,errors in matches:
        if any(sum(x in (a,b) for a,b,_ in matches)!=1 for x in (r,s)):continue
        pair=(r,s); dims=[]
        for k in range(2):
            dims.append(np.floor(np.mean([cs[t[k]]['hi']-cs[t[k]]['lo'] for t in pair],axis=0)*ppem/em+.5))
        outer,inner=dims
        if np.any(inner<1) or np.any(outer-inner<2):continue
        offset=np.floor(np.mean([cs[t[1]]['lo']-cs[t[0]]['lo'] for t in pair],axis=0)*ppem/em+.5)
        offset=np.clip(offset,1,outer-inner-1)
        placements=[]
        for t in pair:
            c=cs[t[0]]; old=fitted[c['ids']]
            origin=np.floor((old.min(axis=0)+old.max(axis=0)-outer)/2+.5)
            for k in range(2):
                d=cs[t[k]]; span=d['hi']-d['lo']
                if np.any(span<=0):raise ValueError('degenerate contour')
                result[d['ids']]=origin+(offset if k else 0)+(source[d['ids']]-d['lo'])/span*dims[k]
            placements.append(origin.tolist())
        records.append(dict(contours=[list(r),list(s)],source_error_fu=errors,outer_px=outer.tolist(),inner_px=inner.tolist(),inner_offset_px=offset.tolist(),origins_px=placements))
    return np.rint(result*64)/64,records
