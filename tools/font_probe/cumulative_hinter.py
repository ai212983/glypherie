"""Stage-owned coordinate constraints for the Python integration experiment."""
import numpy as np
from geometric_candidate import correct, finish
from joint_stroke_fit import fit
from shared_stem_hinter import fit as shared_fit, Unsupported
from vtt_serif_experiment import detect as serif_roles
from outline_relationships import recover_order, reversed_edges


def validate_geometry(source, fitted, stage):
    source, fitted = np.asarray(source,float), np.asarray(fitted,float)
    if fitted.shape != source.shape or not np.isfinite(fitted).all():
        raise ValueError(f'{stage}: invalid coordinate array')
    movement = float(np.max(abs(fitted-source)))
    # Diagnostic admission bound in device pixels; never used to clip geometry.
    if movement > 2:
        raise ValueError(f'{stage}: source displacement {movement:.3f}px exceeds 2px admission bound')
    return dict(max_coordinate_movement_px=movement)


def claim(owners, points, axes, fitted, stage):
    for point in sorted(set(points)):
        for axis in axes:
            value = float(fitted[point,axis])
            previous = [o for o in owners if o['point']==point and o['axis']==axis]
            if any(abs(o['value']-value)>1e-7 for o in previous):
                raise ValueError(f'ownership conflict at point {point} axis {axis}: {stage}')
            owners.append(dict(point=int(point),axis=axis,value=value,stage=stage))


def prepare(data, record, center_fit=None):
    source = np.asarray(data.points)*data.ppem/data.em
    result = correct(data, center_fit=center_fit) if center_fit is not None else correct(data)
    _, _, baseline = finish(result, data, 0)
    baseline = np.round(np.asarray(baseline)*64)/64
    recovered, order = recover_order(data.points,baseline,data.ends,data.flags,record,data.ppem/data.em)
    sanity = validate_geometry(source,recovered,'geometric baseline')
    owners = []
    for change in result['parent_changes']:
        c=change['replacement'];axes=np.flatnonzero(c['normal']).tolist()
        claim(owners,[c['point']],axes,baseline,'parent-anchor')
    for role in serif_roles(data.points,data.ends,data.flags,data.em):
        claim(owners,role['members'],[0,1],baseline,'serif')
    for pair in result['opposing']:
        claim(owners,[i for r in pair for i in [r['outer'],*r['members']]],[0,1],baseline,'opposing-terminal')
    for r in result['terminal']:
        claim(owners,[r['top'],r['bottom'],r['upper_arm'],r['lower_arm'],*r['upper'],*r['lower'],*r['tip']],[1],baseline,'paired-terminal')
    audit=dict(geometric_stages=result['stages'],ownership=owners,sanity=sanity,order_relations=order)
    current=recovered.copy()
    if any(abs(current[o['point'],o['axis']]-o['value'])>1e-7 for o in owners):
        raise ValueError('contour-order recovery conflicts with geometric ownership')
    try:
        shared,support=shared_fit(data.points,record,data.ppem,data.em,
            coordinate=True,ends=data.ends,flags=data.flags)
        audit['coordinated_support']=support
        if shared is not None:
            validate_geometry(source,shared,'coordinated support')
            additions=[]
            for stem in support['supports']:
                claim(additions,stem['outer_points']+stem['inner_points'],[0,1],shared,'coordinated-support')
            combined=list(owners)
            for o in additions:claim(combined,[o['point']],[o['axis']],shared,o['stage'])
            owners[:]=combined
            current=shared
    except (Unsupported,ValueError) as exc:
        audit['coordinated_support']=dict(status='held',reason=str(exc))
    audit['upstream_points']=current.tolist()
    shape_diag = dict(status='disabled')
    if center_fit is not None and (result.get('central_upright') or {}).get('status') == 'candidate':
        try:
            from central_upright_shape import shape_targets, apply_to_record, ownership_for
            targets = shape_targets(None, result['central_upright'])
            if not targets:
                raise ValueError('central-upright shape experiment: empty targets; holding')
            new_record, changed = apply_to_record(record, targets, data.ppem / data.em)
            # Claim on a temporary copy: any clash with an existing owner
            # HOLDS, never supersedes. No record/owner mutation on failure.
            trial = list(owners)
            top = max([o['point'] for o in ownership_for(targets)] + [0])
            staged = np.zeros((top + 1, 2))
            for o in ownership_for(targets):
                staged[o['point'], o['axis']] = o['value']
            for o in ownership_for(targets):
                claim(trial, [o['point']], [o['axis']], staged, o['stage'])
            record = new_record
            owners[:] = trial
            shape_diag = dict(status='applied', targets={int(k): float(v) for k, v in targets.items()},
                              replaced_ids=changed,
                              shape_owners=ownership_for(targets))
        except ValueError as exc:
            shape_diag = dict(status='held', reason=str(exc))
    audit['central_upright_shape'] = shape_diag
    try:
        candidate,joint=fit(data.points,data.ends,data.flags,record,data.ppem/data.em,
            complete_stems=True,continuations=True,upstream=current,ownership=owners,order_relations=order)
        audit['joint']=joint
        audit['sanity']=validate_geometry(source,candidate,'joint fit')
        if reversed_edges(source,candidate,data.ends,data.flags):raise ValueError('joint fit reverses a source cardinal edge')
        audit['status']='joint-fit'
        return baseline,candidate,audit
    except ValueError as exc:
        audit.update(status='held-constraint-conflict',reason=str(exc))
        return baseline,current,audit


def reflect(data, record, current, audit, ink):
    if audit['status']!='joint-fit':return current,dict(status='retained-upstream')
    ownership = list(audit.get('ownership', ()))
    shape = audit.get('central_upright_shape') or {}
    if shape.get('status') == 'applied' and shape.get('targets'):
        try:
            from central_upright_shape import apply_to_record, ownership_for
            targets = {int(k): float(v) for k, v in shape['targets'].items()}
            new_record, changed = apply_to_record(record, targets, data.ppem / data.em)
            assert sorted(changed) == sorted(shape.get('replaced_ids', changed)), \
                'central-upright shape reflection targets differ from prepare'
            # Same claim-on-temp policy as prepare: conflict HOLDS, no superseding.
            trial = list(ownership)
            top = max(list(targets) + [0])
            staged = np.zeros((top + 1, 2))
            for o in ownership_for(targets):
                staged[o['point'], o['axis']] = o['value']
            for o in ownership_for(targets):
                claim(trial, [o['point']], [o['axis']], staged, o['stage'])
            record, ownership = new_record, trial
            result_shape = dict(status='applied', replaced_ids=changed,
                                targets={int(k): float(v) for k, v in targets.items()},
                                shape_owners=ownership_for(targets))
        except (ValueError, AssertionError) as exc:
            return current, dict(status='held-shape-conflict', reason=str(exc))
    else:
        result_shape = dict(status=shape.get('status', 'disabled'))
    candidate,result=fit(data.points,data.ends,data.flags,record,data.ppem/data.em,
        complete_stems=True,continuations=True,upstream=audit['upstream_points'],
        ownership=ownership,reflection_em=data.em,reflection_ink=ink,order_relations=audit['order_relations'],curve_reflection=True)
    try:
        validate_geometry(np.asarray(data.points)*data.ppem/data.em,candidate,'reflection')
        if reversed_edges(np.asarray(data.points)*data.ppem/data.em,candidate,data.ends,data.flags):raise ValueError('reflection reverses a source cardinal edge')
    except ValueError as exc:return current,dict(status='held-invalid-geometry',reason=str(exc))
    reflection = dict(result['reflection'])
    reflection['central_upright_shape'] = result_shape
    return candidate,reflection


def finalize(points, ends, flags, current, scale, upstream_audit):
    """Approved final geometry pass, after cumulative curves and terminal placement.

Call once on the pre-recovery cumulative coordinates. Selection of saved input
artifacts belongs to the adapter; this boundary receives no font/glyph identity.
"""
    from curved_stroke_recovery import fit as recover_stroke
    fitted, stages = recover_stroke(points, ends, flags, current, scale,
        order=upstream_audit.get('order_relations', ()),
        ownership=upstream_audit.get('ownership', ()))
    if stages:
        validate_geometry(np.asarray(points)*scale, fitted, 'approved curved-stroke recovery')
        if reversed_edges(np.asarray(points)*scale, fitted, ends, flags):
            raise ValueError('approved recovery reverses a source cardinal edge')
    return fitted, dict(stage='approved-whole-curved-stroke', operations=stages)
