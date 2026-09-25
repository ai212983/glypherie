"""Experimental missing-curve width links over the reviewed upstream fit.

Widths within the geometry distance tolerance share a mean and integer target.
The target prefers the shared stem class when the mean falls in its band
(literata O/Q sides take the 1px stem target instead of rounding their
straddling local mean up to 2px); widths outside every class keep local
rounding. A cluster whose target thins its design mean is
shared (Shamir 2003 section 3.5 removes ink where the scaler
adds it). Horizontal bands additionally hold or widen but never
narrow the fitted width: the moved outlines feed the bytecode,
so holding a fitted 2px side is load-bearing while narrowing an
honest 3px bowl starves it. Other clusters keep the solver fit.
Outer extrema retain placement. Inner extrema follow by a width
link; source coordinate IUP distributes the additional movement
between anchored extrema.
"""
import numpy as np
from fontTools.varLib.iup import iup_contour
from shamir_features import recognize
from shamir_segment_fit import prepared_glyph


def shared_target(width_units, scale, width_table):
    """Shared stem-class target for a curved width, else local rounding.

    A curved side whose design width falls in a stem cluster band takes
    the cluster target (Shamir 2003 section 3.4 links near values to
    the characteristic global under tolerance; section 5 requires
    width uniformity of stems and arcs). Widths outside every cluster
    keep the legacy local rounding bit-for-bit: half-up agrees with
    the previous floor(x + .5) on these magnitudes, so only in-band
    widths change behavior.
    """
    if width_table is not None:
        from stem_width_table import lookup as _table_lookup
        return max(1., float(_table_lookup(width_table, width_units)))
    return max(1., float(np.floor(width_units*scale+.5)))


def detect(model):
    old = recognize(model)['features']
    old_pairs = {(f['axis'], tuple(sorted(f['points']))) for f in old
                 if f['kind'] in ('bow', 'arc')}
    found = [f for f in recognize(model, curved_support=True)['features']
             if f['kind'] in ('bow', 'arc')]
    for f in found:
        f['new'] = (f['axis'], tuple(sorted(f['points']))) not in old_pairs
    return found


def fit(model, current, ownership=(), *, reconstruct_curves=False,
        width_table=None):
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
            target = shared_target(width, model['scale'], width_table)
            # A shared target applies when it thins the design
            # (Shamir 2003 §3.5), and bands hold or widen but never
            # narrow a fitted width the solver already widened past
            # design. The fitted comparison covers what the design
            # test misses: literata-16 m/n arch sides (1.12px
            # design, solver-fit 2.0px, unanimous 1px target)
            # settled against the narrowing (bow probe 2026-09-15:
            # m W=5 C=35, n W=3 C=20). Solver-untouched widths keep
            # thin-only (the straddling pin: fitted == design still
            # thins), and wider targets keep widening (literata-16
            # O/Q 1.0-to-2.0px links apply unchanged). WHY
            # (precedence clause): the joint solver's fitted widths
            # stand — links move untouched widths toward the shared
            # target and widen fitted ones up to it, but never
            # narrow a width the solver widened, matching the
            # solver layer's own widen-only rule
            # (``standardize_hard_widths``). Uniform at every size:
            # the old above-14px outright-claim exception (v1
            # hardens those sides) goes with it — v1 is a tripwire,
            # never a judge, and the exception's cited scaler cases
            # (roboto-16 8, literata-16 O/Q) all probe UNSETTLED.
            # The ``arc_sharing`` table key survives for the joint
            # solver, which still consults it; this layer no longer
            # reads it.
            design_px = width*model['scale']
            design_thins = target < design_px - 1e-9
            if width_table is not None:
                # Hold-or-widen, decided per cluster so a cluster
                # never applies halfway (a half-held pair would
                # split symmetric sides by grid phase).
                holds = True
                for f in cluster:
                    a,b = f['points']
                    pa,pb = model['points'][a],model['points'][b]
                    sign = 1 if pa['extrema'][str(axis)] == 'min' else -1
                    if sign*(pa['position'][axis]-pb['position'][axis]) > 0:
                        a,b = b,a
                    outer,inner = mapping[a],mapping[b]
                    fitted = sign*(q[inner,axis]-q[outer,axis])
                    design_f = f['width']*model['scale']
                    if (target < fitted - 1e-9
                            and fitted > design_f + 1e-9):
                        holds = False
                        break
                if not holds:
                    continue
            elif not design_thins:
                continue
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
