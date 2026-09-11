"""Experimental missing-curve width links over the reviewed upstream fit.

Widths within the geometry distance tolerance share a mean and integer target.
Outer extrema retain placement. Inner extrema follow by a width link; source
coordinate IUP distributes the additional movement between anchored extrema.
"""
import numpy as np
from fontTools.varLib.iup import iup_contour
from shamir_features import recognize
from shamir_segment_fit import prepared_glyph


def detect(model):
    old = recognize(model)['features']
    old_pairs = {(f['axis'], tuple(sorted(f['points']))) for f in old
                 if f['kind'] in ('bow', 'arc')}
    found = [f for f in recognize(model, curved_support=True)['features']
             if f['kind'] in ('bow', 'arc')]
    for f in found:
        f['new'] = (f['axis'], tuple(sorted(f['points']))) not in old_pairs
    return found


def fit(model, current, ownership=(), *, reconstruct_curves=False):
    glyph, mapping, _ = prepared_glyph(model)
    source = np.asarray(glyph.coordinates, float)
    q = np.asarray(current, float); result = q.copy()
    if q.shape != source.shape: raise ValueError('prepared point mapping differs')
    features = detect(model)
    axes = {f['axis'] for f in features if f['new']}
    audit = []; reconstruction = []
    for axis in sorted(axes):
        fs = sorted((f for f in features if f['axis'] == axis), key=lambda f:f['width'])
        clusters = []
        for f in fs:
            if not clusters or f['width']-clusters[-1][0]['width'] > model['tolerances']['distance']+1e-9:
                clusters.append([])
            clusters[-1].append(f)
        claims = {}; links = []
        for cluster in clusters:
            width = float(np.mean([f['width'] for f in cluster]))
            target = max(1., float(np.floor(width*model['scale']+.5)))
            for f in cluster:
                a,b = f['points']; pa,pb = model['points'][a],model['points'][b]
                sign = 1 if pa['extrema'][str(axis)] == 'min' else -1
                if sign*(pa['position'][axis]-pb['position'][axis]) > 0:a,b=b,a
                outer,inner = mapping[a],mapping[b]
                value = q[outer,axis]+sign*target
                if inner in claims and abs(claims[inner]-value)>1e-9:
                    raise ValueError('competing curved width links')
                claims[inner] = value
                links.append(dict(axis=axis,outer=outer,inner=inner,new=f['new'],
                    source_width_px=f['width']*model['scale'],shared_width_px=width*model['scale'],
                    target_width_px=target,before_width_px=sign*(q[inner,axis]-q[outer,axis])))
        if all(abs(q[i,axis]-v)<=1/128 for i,v in claims.items()):continue
        if reconstruct_curves:
            from curve_reconstruction import reconstruct
            for o in ownership:
                if o['axis']==axis and o['point'] in claims and abs(claims[o['point']]-o['value'])>1/128:
                    raise ValueError('curved width conflicts with owned coordinate')
            paired=[]
            if model.get('source_junctions'):
                for f in features:
                    if f['axis']==axis:continue
                    a,b=f['points'];other=f['axis']
                    if any(model['points'][i]['kind']!='curve' for i in (a,b)):continue
                    sign=1 if model['points'][a]['extrema'][str(other)]=='min' else -1
                    if sign*(model['points'][a]['position'][other]-model['points'][b]['position'][other])>0:a,b=b,a
                    paired.append((mapping[a],mapping[b]))
            result,local=reconstruct(model,result,axis,claims,[l['outer'] for l in links],ownership,paired)

            reconstruction.append(local)
        else:
            anchors = {mapping[p['id']]:0. for p in model['points'] if str(axis) in p['extrema']}
            for o in ownership:
                if o['axis'] == axis:
                    if o['point'] in claims and abs(claims[o['point']]-o['value'])>1/128:
                        raise ValueError('curved width conflicts with owned coordinate')
                    anchors[o['point']] = 0.
            for i,v in claims.items():anchors[i]=v-q[i,axis]
            start=0
            for end in glyph.endPtsOfContours:
                delta=[(anchors[i],anchors[i]) if i in anchors else None for i in range(start,end+1)]
                # The two IUP coordinates are independent; retain only this axis.
                movement=np.asarray(iup_contour(delta,source[start:end+1].tolist()))[:,axis]
                result[start:end+1,axis]+=movement;start=end+1
        for link in links:
            link['after_width_px']=abs(result[link['inner'],axis]-result[link['outer'],axis])
            if abs(link['after_width_px']-link['target_width_px'])>1e-8:
                raise ValueError('overlapping parent/child curve constraints')
        audit.extend(links)
    return result,dict(new_pairs=sum(f['new'] for f in features),links=audit,reconstruction=reconstruction)
