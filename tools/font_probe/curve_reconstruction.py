"""Source reconstruction of curve runs bounded by corners or line tangencies.

Experimental composition policy: protect junction coordinates, retain fitted
axis extrema, and rebuild the intervening coordinates from source IUP ratios.
"""
import numpy as np
from fontTools.varLib.iup import iup_contour
from shamir_segment_fit import prepared_glyph


def reconstruct(model,current,axis,claims,parents,ownership=(), paired_extrema=()):
    glyph,mapping,members=prepared_glyph(model)
    if model.get('source_junctions'):
        source=np.asarray([p for loop in model['contours'] for sid in loop
                           for p in model['segments'][sid]['control'][:-1]],float)*model['scale']
    else:
        source=np.asarray(glyph.coordinates,float)*model['scale']
    q=np.asarray(current,float);target=q.copy()
    reverse={i:pid for pid,i in mapping.items()}
    active=set();boundaries=set()
    def junction(p):
        if not model.get('source_junctions'):
            return p['kind'] in ('corner','tangent')
        # Curve/curve turns retain their shape through interpolation. A line
        # attachment is structural in both coordinates; extrema own one axis.
        return p['kind'] in ('corner','tangent') and any(
            len(s['control'])==2 and p['id'] in (s['start'],s['end'])
            for s in model['segments'])
    for anchor in set(claims)|set(parents):
        point=model['points'][reverse[anchor]]
        loop=model['contours'][point['contour']]
        ids=[model['segments'][s]['start'] for s in loop];start=ids.index(point['id'])
        for direction in (-1,1):
            for step in range(len(loop)):
                sid=loop[(start+step)%len(loop)] if direction==1 else loop[(start-step-1)%len(loop)]
                segment=model['segments'][sid];active.update(members[sid])
                end=segment['end'] if direction==1 else segment['start']
                p=model['points'][end]
                if junction(p):
                    boundaries.add(mapping[end]);break
                if end==point['id']:break
    anchors={i:q[i,axis] for i in range(len(q)) if i not in active}
    for p in model['points']:
        if str(axis) in p['extrema'] or junction(p):
            anchors[mapping[p['id']]]=q[mapping[p['id']],axis]
    anchors.update({i:q[i,axis] for i in boundaries})
    for o in ownership:
        if o['axis']==axis:anchors[o['point']]=o['value']
    for i,value in claims.items():
        if i in boundaries and abs(value-q[i,axis])>1e-9:
            raise ValueError('curve width moves a junction')
        anchors[i]=value
    def interpolate():
        start=0
        for end in glyph.endPtsOfContours:
            deltas=[(anchors[i]-source[i,axis],)*2 if i in anchors else None for i in range(start,end+1)]
            values=np.asarray(iup_contour(deltas,source[start:end+1].tolist()))[:,axis]
            target[start:end+1,axis]=source[start:end+1,axis]+values;start=end+1
    interpolate()
    paired_claims=[]
    if paired_extrema:
        for outer,inner in paired_extrema:
            if outer not in active or inner not in active:continue
            desired=target[outer,axis]+source[inner,axis]-source[outer,axis]
            if inner in anchors and abs(anchors[inner]-desired)>1/128:
                raise ValueError('paired curve position conflicts with an anchor')
            anchors[inner]=desired
            paired_claims.append((outer,inner))
        interpolate()
        if any(abs((target[b,axis]-target[a,axis])-(source[b,axis]-source[a,axis]))>1e-8 for a,b in paired_claims):
            raise ValueError('coupled curve positions require joint resolution')
    # An inward move must not turn a source maximum into a local minimum (or
    # the reverse). Check the full control polygon, including curve handles.
    for sid,ids in members.items():
        if not active.intersection(ids):continue
        for a,b in zip(ids,ids[1:]):
            d=source[b,axis]-source[a,axis]
            if abs(d)>1e-9 and (target[b,axis]-target[a,axis])*d < -1e-8:
                raise ValueError('curve width conflicts with source arc order')
    return target,dict(axis=axis,boundaries=sorted(boundaries),active_points=sorted(active),
                       paired_extrema=[list(p) for p in paired_claims],
                       max_junction_movement_px=max((abs(target[i,axis]-q[i,axis]) for i in boundaries),default=0.))
