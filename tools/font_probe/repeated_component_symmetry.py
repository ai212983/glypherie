"""Experimental translation correspondence for axis-aligned repeated contours."""
import numpy as np


def normalized_ink(ink, bounds):
    lo,hi=bounds
    cells={(x,y) for x,y in ink if lo[0]-1e-7<=x+.5<=hi[0]+1e-7 and lo[1]-1e-7<=-y-.5<=hi[1]+1e-7}
    if not cells:return frozenset(),None
    origin=(min(x for x,y in cells),min(y for x,y in cells))
    return frozenset((x-origin[0],y-origin[1]) for x,y in cells),origin


def fit(points, fitted, ends, flags, em, scale, ink, ownership=(), raster=None):
    p,q=np.asarray(points,float),np.asarray(fitted,float);out=q.copy();contours=[];start=0
    for end in ends:contours.append(list(range(start,end+1)));start=end+1
    pairs=[]
    for i,a in enumerate(contours):
        for j in range(i+1,len(contours)):
            b=contours[j]
            if len(a)!=len(b):continue
            ca=p[a].mean(axis=0);cb=p[b].mean(axis=0);delta=cb-ca
            axis=int(np.argmax(abs(delta)));fixed=1-axis
            if abs(delta[fixed])>em/512 or abs(delta[axis])<em/16:continue
            # Require disjoint component boxes, avoiding nested counters.
            if not (p[a,axis].max()<p[b,axis].min() or p[b,axis].max()<p[a,axis].min()):continue
            matches=[]
            for shift in range(len(b)):
                mapped=np.roll(b,shift).tolist()
                if any((flags[x]&1)!=(flags[y]&1) for x,y in zip(a,mapped)):continue
                error=float(np.max(np.linalg.norm((p[a]-ca)-(p[mapped]-cb),axis=1)))
                if error<=em/512:matches.append((error,mapped))
            if len(matches)==1:pairs.append((a,matches[0][1],axis,matches[0][0]))
    counts={i:sum(i in a+b for a,b,_,_ in pairs) for i in range(len(p))};audit=[]
    for a,b,axis,error in pairs:
        info=dict(contours=[a,b],axis=axis,source_error_units=error);audit.append(info)
        if any(counts[i]>1 for i in a+b):info['status']='held-ambiguous-group';continue
        if any(o['point'] in a+b for o in ownership):info['status']='held-owned';continue
        shape_a,oa=normalized_ink(ink,(q[a].min(axis=0),q[a].max(axis=0)))
        shape_b,ob=normalized_ink(ink,(q[b].min(axis=0),q[b].max(axis=0)))
        if raster is not None:
            def normalize(cells):
                if not cells:return frozenset(),None
                origin=(min(x for x,y in cells),min(y for x,y in cells))
                return frozenset((x-origin[0],y-origin[1]) for x,y in cells),origin
            shape_a,oa=normalize(raster(q,a,1));shape_b,ob=normalize(raster(q,b,1))
        if shape_a and shape_a==shape_b and oa[1-axis]==ob[1-axis]:
            info['status']='already-repeated';continue
        ca,cb=q[a].mean(axis=0),q[b].mean(axis=0)
        template=((p[a]-p[a].mean(axis=0))+(p[b]-p[b].mean(axis=0)))*scale/2
        delta=cb-ca;delta[1-axis]=0;delta[axis]=np.floor(delta[axis]+.5)
        midpoint=(ca+cb)/2;centers=[midpoint-delta/2,midpoint+delta/2]
        candidate=q.copy();candidate[a]=template+centers[0];candidate[b]=template+centers[1]
        if raster is not None:
            choices=[]
            for dx in (-.5,-.25,0,.25):
                for dy in (-.5,-.25,0,.25):
                    trial=candidate.copy();trial[a]+=np.array([dx,dy]);trial[b]+=np.array([dx,dy])
                    ia,ib=raster(trial,a,1),raster(trial,b,1)
                    if not ia or not ib:continue
                    va=[cell[axis] for cell in ia];vb=[cell[axis] for cell in ib]
                    gap=max(min(vb)-max(va)-1,min(va)-max(vb)-1)
                    if gap<1:continue
                    sa,_=normalize(ia);sb,_=normalize(ib)
                    if sa!=sb:continue
                    fine=raster(trial,a,8);coverage={}
                    for x,y in fine:coverage[x//8,y//8]=coverage.get((x//8,y//8),0)+1/64
                    fidelity=sum((coverage.get(cell,0)-(cell in ia))**2 for cell in set(coverage)|ia)/max(1,len(ia))
                    movement=float(np.mean((trial[a+b]-q[a+b])**2))
                    choices.append((fidelity+.02*movement,movement,dx,dy,trial))
            if not choices:info['status']='held-spacing';continue
            candidate=min(choices,key=lambda c:c[:4])[-1]
        out[a]=candidate[a];out[b]=candidate[b]
        info.update(status='coordinated',translation_px=delta.tolist())
    return out,audit
