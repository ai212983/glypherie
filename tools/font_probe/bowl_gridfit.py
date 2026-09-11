"""Pair vertical tangent supports on quadratic bowl sides.

Supports are aligned on/off-curve point runs, not straight segments. Only the
side extremum separation is constrained; adjoining curvature is interpolated.
"""
from stem_gridfit import geometry,contains


def bowl_pairs(points,tags,ends,size):
    if any(t==2 for t in tags):return []
    _,segments=geometry(points,tags,ends,size)
    supports=[];start=0
    for end in ends:
        ids=list(range(start,end+1));start=end+1
        # Start where x changes, so a tangent run crossing the contour seam is whole.
        cut=next((k for k,i in enumerate(ids) if abs(points[i,0]-points[ids[k-1],0])>1e-5),None)
        if cut is None:continue
        ids=ids[cut:]+ids[:cut];runs=[]
        for i in ids:
            if runs and abs(points[runs[-1][0],0]-points[i,0])<1e-5:runs[-1].append(i)
            else:runs.append([i])
        for run in runs:
            if not any(tags[i]==0 for i in run) or not any(tags[i]==1 for i in run):continue
            dy=points[run[-1],1]-points[run[0],1]
            if abs(dy)<size*.08:continue
            supports.append(tuple(run))
    found=[]
    for k,e in enumerate(supports):
        a,b=points[e[0]],points[e[-1]]
        for f in supports[k+1:]:
            c,d=points[f[0]],points[f[-1]]
            if (b[1]-a[1])*(d[1]-c[1])>=0:continue
            lo=max(min(a[1],b[1]),min(c[1],d[1]));hi=min(max(a[1],b[1]),max(c[1],d[1]))
            width=abs(a[0]-c[0])
            if hi-lo<size*.04 or not .4<=width<=size*.16:continue
            # The control support itself can lie outside ink; inspect near the
            # midpoint of the strip, where the opposing curved sides enclose ink.
            if not all(contains(segments,a[0]+(c[0]-a[0])*t,(lo+hi)/2) for t in (.3,.5,.7)):continue
            left,right=(e,f) if a[0]<c[0] else (f,e)
            found.append(dict(left=left,right=right,width=width))
    selected=[];used=set()
    for pair in sorted(found,key=lambda p:p['width']):
        if pair['left'] in used or pair['right'] in used:continue
        selected.append(pair);used.update((pair['left'],pair['right']))
    return selected
