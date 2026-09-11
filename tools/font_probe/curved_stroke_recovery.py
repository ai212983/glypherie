"""Experimental source reconstruction of both sides of a curved terminal stroke.

The input cap recognizer is geometry-only. Rebuild complete quadratic runs up to
line joins, preserving fitted stem attachments and curve extrema heights. This
replaces the local endpoint warp rather than composing another warp after it.
"""
import numpy as np
from junction_terminal_fit import fit as local_fit


def fit(points, ends, flags, current, scale, order=(), ownership=()):
    source=np.asarray(points,float)*scale;q=np.asarray(current,float)
    candidate,local=local_fit(points,ends,flags,q,scale,order)
    out=q.copy();audit=[]
    # Retain the independent bar placement, exactly as previously reviewed.
    for event in local:
        if event['kind']=='repaired-bar':
            ids=sorted(set(event['corner']+sum(event['groups'],[])))
            out[ids,1]=candidate[ids,1];audit.append(event)
    used=set()
    for cap in local:
        if cap['kind']!='curved-cap':continue
        a,b=cap['endpoints'];axis=1-cap['thickness_axis'];other=1-axis
        lo=0
        for hi in ends:
            if lo<=a<=hi:break
            lo=hi+1
        loop=list(range(lo,hi+1));n=len(loop);runs=[]
        for tip,direction in [(a,-1),(b,1)]:
            pos=loop.index(tip);ids=[tip]
            for step in range(1,n):
                i=loop[(pos+direction*step)%n];j=loop[(pos+direction*(step+1))%n];ids.append(i)
                if flags[i]&1 and flags[j]&1:break
            else:raise ValueError('curve has no line attachment')
            # Both runs must join sides aligned with the cap's main direction.
            d=source[j]-source[i]
            if abs(d[axis])>1e-8 or abs(d[other])<1e-8:break
            runs.append(ids)
        if len(runs)!=2:continue
        if set(runs[0])&set(runs[1]):raise ValueError('overlapping stroke sides')
        # The stem attachments must face the same direction along the outline.
        anchors=[ids[-1] for ids in runs]
        if abs(source[anchors[0],other]-source[anchors[1],other])>1/64:continue
        region=set(sum(runs,[]))
        if region&used:raise ValueError('overlapping reconstructed strokes')
        targets=q[[a,b]].copy()
        # Resolve competing cap positions symmetrically around their fitted centre.
        centre=float(np.mean(q[[a,b],axis]));offset=source[b,axis]-source[a,axis]
        targets[:,axis]=[centre-offset/2,centre+offset/2]
        extrema=[]
        for ids in runs:
            sign=np.sign(source[ids[0],other]-source[ids[-1],other])
            ext=max(ids,key=lambda i:sign*source[i,other]);extrema.append(ext)
        # Reuse both fitted curve-height anchors; retain the source width profile
        # via separate affine maps on the two boundaries, not fixed cap thickness.
        for ids,target,ext in zip(runs,targets,extrema):
            tip,anchor=ids[0],ids[-1]
            for ax,endpoint in [(axis,tip),(other,ext)]:
                span=source[endpoint,ax]-source[anchor,ax]
                if abs(span)<1e-8:raise ValueError('degenerate curved stroke span')
                value=target[ax] if ax==axis else q[ext,ax]
                ratio=(value-q[anchor,ax])/span
                if ratio<=0:raise ValueError('reversed curved stroke span')
                out[ids,ax]=q[anchor,ax]+(source[ids,ax]-source[anchor,ax])*ratio
        gap=out[b,other]-out[a,other]
        if gap*(source[b,other]-source[a,other])<=0:raise ValueError('collapsed cap')
        used.update(region)
        audit.append(dict(kind='whole-curved-stroke',endpoints=[a,b],runs=runs,
                          attachments=anchors,extrema=extrema,
                          thickness_axis=other,cap_thickness_px=float(abs(gap)),
                          extrema_thickness_px=float(abs(out[extrema[0],other]-out[extrema[1],other]))))
    for o in ownership:
        if abs(out[o['point'],o['axis']]-q[o['point'],o['axis']])>1/64:raise ValueError('owned coordinate conflict')
    return out,audit
