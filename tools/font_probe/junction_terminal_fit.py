"""Geometry-only experimental recovery of repaired bars and curved end caps.

Policies are local interpretations, not a paper baseline. Input is source geometry,
current coordinates and the generic contour-order repair provenance.
"""
import numpy as np


def fit(points, ends, flags, current, scale, order=(), ownership=()):
    p=np.asarray(points,float)*scale;q=np.asarray(current,float);out=q.copy();audit=[]
    # A repaired corner belongs to a source horizontal bar. Restore each complete
    # horizontal boundary to its nearest grid line, including split collinear sides.
    for c in order:
        if c['axis']!=1:continue
        a,b=c['a'],c['b'];groups=[]
        lo=0
        for hi in ends:
            if lo<=a<=hi:break
            lo=hi+1
        if not lo<=b<=hi:continue
        outer=p[lo:hi+1];inside=[];begin=0
        for stop in ends:
            ids=np.arange(begin,stop+1);begin=stop+1
            if np.all(p[ids].min(axis=0)>=outer.min(axis=0)-1e-8) and np.all(p[ids].max(axis=0)<=outer.max(axis=0)+1e-8):inside.extend(ids)
        contour=np.asarray(inside,dtype=int)
        for i in (a,b):
            ids=contour[abs(p[contour,1]-p[i,1])<1e-8]
            if len(ids)>=3:groups.append(ids)
        if len(groups)!=1:continue
        lower=groups[0];near=[]
        for y in np.unique(p[contour,1]):
            ids=contour[abs(p[contour,1]-y)<1e-8]
            if len(ids)>=3 and .5<=abs(y-p[a,1])<=2:near.append(ids)
        if len(near)!=1:continue
        for ids in [lower,near[0]]:
            target=np.floor(np.median(q[ids,1])+.5);out[ids,1]=target
        out[b,1]=out[a,1]+p[b,1]-p[a,1]
        audit.append(dict(kind='repaired-bar',corner=[a,b],groups=[v.tolist() for v in [lower,near[0]]]))
    # Short near-cardinal line caps between curves: keep their authored vector.
    # Blend endpoint corrections through neighboring curves up to their extrema.
    start=0
    for end in ends:
        loop=list(range(start,end+1));start=end+1;n=len(loop)
        for k,a in enumerate(loop):
            b=loop[(k+1)%n]
            if not(flags[a]&1 and flags[b]&1):continue
            if flags[loop[(k-1)%n]]&1 or flags[loop[(k+2)%n]]&1:continue
            d=p[b]-p[a];axis=int(np.argmin(abs(d)));other=1-axis
            if abs(d[other])<.25 or abs(d[other])>2 or abs(d[axis])>.15*abs(d[other]):continue
            # Require a source extremal cap, avoiding interior joins.
            edge=min(abs(p[a,axis]-p[:,axis].min()),abs(p[a,axis]-p[:,axis].max()))
            if edge>1/64:continue
            runs=[]
            for tip,direction,pos in [(a,-1,k),(b,1,k+1)]:
                ids=[tip]
                for step in range(1,n):
                    i=loop[(pos+direction*step)%n];ids.append(i)
                    j=loop[(pos+direction*(step+1))%n]
                    if flags[i]&1:
                        prev=loop[(pos+direction*(step-1))%n]
                        turn=(p[i,other]-p[prev,other])*(p[j,other]-p[i,other])
                        if flags[j]&1 or turn<=0:break
                else:break
                runs.append(ids)
            if len(runs)!=2:continue
            if abs(p[runs[0][-1],other]-p[runs[1][-1],other])>2*abs(d[other]):continue
            target=q[[a,b]].copy();target[1,axis]=target[0,axis]+d[axis]
            # Preserve the small source offset from the adjacent curve extremum.
            ids=runs[0];ext=max(ids,key=lambda i:p[i,other]) if d[other]<0 else min(ids,key=lambda i:p[i,other])
            target[0,other]=q[ext,other]+p[a,other]-p[ext,other]
            # Translate both cap edges together: preserve the fitted cap thickness.
            target[1,other]=q[b,other]+target[0,other]-q[a,other]
            if np.max(abs(target-q[[a,b]]))<=1/64:continue
            for ids,t in zip(runs,target):
                tip,anchor=ids[0],ids[-1]
                for ax in (0,1):
                    span=p[tip,ax]-p[anchor,ax]
                    if abs(span)<1e-9:
                        if abs((t-p[tip])[ax]-(q[anchor]-p[anchor])[ax])>1/64:raise ValueError('degenerate curve interpolation')
                        weights=np.zeros(len(ids))
                    else:weights=np.clip((p[ids,ax]-p[anchor,ax])/span,0,1)
                    out[ids,ax]=q[ids,ax]+weights*(t[ax]-q[tip,ax])
            audit.append(dict(kind='curved-cap',endpoints=[a,b],runs=runs,
                              thickness_axis=other,thickness_before_px=float(abs(q[b,other]-q[a,other])),
                              thickness_after_px=float(abs(out[b,other]-out[a,other]))))
    for o in ownership:
        if abs(out[o['point'],o['axis']]-q[o['point'],o['axis']])>1/64:raise ValueError('owned coordinate conflict')
    return out,audit
