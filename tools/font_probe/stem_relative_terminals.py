"""Experimental placement of short terminal excursions relative to a stem.

Geometry only. A long cardinal side ends in a short excursion that contains an
outline extremum and returns across the side's plane. Preserve the source
extension without rounding; blend the additional movement through that excursion.
"""
import numpy as np
from shamir_segment_fit import prepared_glyph


def detect(model):
    glyph,mapping,members=prepared_glyph(model)
    p=np.asarray([v for loop in model['contours'] for sid in loop
                  for v in model['segments'][sid]['control'][:-1]],float)
    eps=model['tolerances']['distance'];hits=[]
    for loop in model['contours']:
        for j,sid in enumerate(loop):
            segment=model['segments'][sid]
            if len(segment['control'])!=2:continue
            a,b=np.asarray(segment['control']);d=b-a
            # Current experiment: horizontal extensions from vertical sides.
            if abs(d[0])>1e-9 or abs(d[1])<=eps:continue
            for direction in (-1,1):
                start=segment['end'] if direction==1 else segment['start']
                parent=mapping[start];origin=p[parent,0];ids=[parent];oncurve=[];returned=False
                sign=None
                for step in range(1,len(loop)):
                    k=(j+step)%len(loop) if direction==1 else (j-step)%len(loop)
                    run=model['segments'][loop[k]]
                    runids=members[run['id']][1:] if direction==1 else members[run['id']][::-1][1:]
                    end=run['end'] if direction==1 else run['start'];point=mapping[end]
                    ids.extend(runids);oncurve.append(point)
                    x=p[point,0]-origin
                    if sign is None:
                        if abs(x)<=eps:break
                        sign=1 if x>0 else -1
                    elif sign*x<=0:
                        returned=True;break
                if not returned or not oncurve:continue
                tip=max(oncurve,key=lambda i:sign*(p[i,0]-origin))
                extension=sign*(p[tip,0]-origin)
                if extension<=eps or abs(d[1])<2*extension:continue
                if max(abs(p[i,1]-p[parent,1]) for i in ids)>abs(d[1])/2:continue
                global_edge=p[:,0].max() if sign>0 else p[:,0].min()
                if abs(p[tip,0]-global_edge)>1e-9:continue
                hits.append(dict(parent=parent,tip=tip,sign=sign,extension=extension,
                                 points=sorted(set(ids)),stem_length=abs(d[1])))
    # Alternative supports must not silently compete for the same terminal.
    unique=[]
    for h in hits:
        if sum(x['tip']==h['tip'] for x in hits)!=1:continue
        unique.append(h)
    return p,unique


def fit(model,current,ownership=()):
    p,hits=detect(model);q=np.asarray(current,float);result=q.copy();audits=[];used=set()
    for h in hits:
        parent,tip=h['parent'],h['tip'];sign=h['sign'];source=h['extension']*model['scale']
        before=sign*(q[tip,0]-q[parent,0]);target=q[parent,0]+sign*source
        # Leave extensions whose fit already preserves the authored distance.
        if abs(before-source)<=1/64:continue
        ids=np.array(h['points']);weights=np.clip(sign*(p[ids,0]-p[parent,0])/h['extension'],0,1)
        moving={int(i) for i,w in zip(ids,weights) if w>0}
        if moving&used:raise ValueError('overlapping terminal ownership')
        for o in ownership:
            if o['axis']==0 and o['point'] in moving:raise ValueError('terminal conflicts with owned coordinate')
        result[ids,0]+=weights*(target-q[tip,0]);used.update(moving)
        audits.append(dict(**h,source_extension_px=source,before_extension_px=before,
                           after_extension_px=sign*(result[tip,0]-result[parent,0])))
    return result,audits
