"""Opt-in central-upright shape constraints (experimental, never default).

For an accepted ``central_upright_fit`` proposal, derive explicit x targets
for the source-collinear knot-boundary member points (outer sides + upright
sides) and reflect them into the joint solver by replacing ONLY recognized
x glyph-bound hard equations. Never globally drops metric protections; y
bounds, global P*, and baseline links are never touched. Unknown or
conflicting semantics hold (raise ValueError -> held-constraint-conflict).
"""
import numpy as np


def shape_targets(fitted_current_px, audit):
    """Map point index -> target x (px) for knot-boundary members.

    Membership is determined by SOURCE x inside ``central_upright_fit``
    and carried as explicit ``evidence['member_targets']`` point-target
    pairs. This function only forwards those pairs; it never infers
    membership from mapped coordinates. ``fitted_current_px`` is accepted
    for API compatibility and ignored.
    """
    if (audit or {}).get('status') != 'candidate':
        return {}
    members = (audit.get('evidence') or {}).get('member_targets')
    if not members:
        return {}
    return {int(k): float(v) for k, v in members.items()}


def apply_to_record(record, targets_px, scale):
    """Replace recognized x glyph-bound hard equation values in a record copy.

    Returns (new_record, changed_ids). Only Abs/Dist constraints with
    metric_role == 'glyph-x-bound' and x-axis normal are eligible; Abs
    targets the point's own target, Dist targets source+width (target of
    point minus target of source, both in targets). Anything else holding
    a metric flag keeps its value. Raises ValueError on unknown/conflicting
    semantics (caller maps to held). All-or-nothing: if any eligible
    x-bound equation lacks a target endpoint, nothing is replaced.
    Replaced equations get round=False so targets are used exactly, and
    each replaced value is verified against its target in px.
    """
    import copy
    if not targets_px:
        raise ValueError('central-upright shape experiment: empty targets')
    rec = copy.deepcopy(record)
    eligible = []
    for c in rec['graph']['constraints']:
        if not c.get('metric'):
            continue
        role = c.get('metric_role')
        if role is None:
            raise ValueError(
                'central-upright shape experiment: metric constraint id '
                f"{c.get('id')} lacks metric_role; refusing to reinterpret")
        if role not in ('glyph-x-bound', 'glyph-y-bound', 'baseline'):
            raise ValueError(
                'central-upright shape experiment: metric constraint id '
                f"{c.get('id')} has unknown metric_role {role!r}; holding")
        if role != 'glyph-x-bound':
            continue
        n = np.asarray(c.get('normal', [0, 0]), float)
        if not (abs(n[0] - 1.0) < 1e-9 and abs(n[1]) < 1e-9):
            raise ValueError(
                'central-upright shape experiment: glyph-x-bound id '
                f"{c.get('id')} has non-x normal; holding")
        if c['kind'] not in ('Abs', 'Dist'):
            raise ValueError(
                'central-upright shape experiment: glyph-x-bound id '
                f"{c.get('id')} has ineligible kind {c['kind']}; holding")
        eligible.append(c)
    if not eligible:
        raise ValueError('central-upright shape experiment: no eligible x-bound equation matched')
    pending = []
    for c in eligible:
        pt = int(c['point'])
        if c['kind'] == 'Abs':
            if pt not in targets_px:
                raise ValueError(
                    'central-upright shape experiment: glyph-x-bound Abs id '
                    f"{c.get('id')} point {pt} lacks target; holding all")
            pending.append((c, float(targets_px[pt]) / scale, float(targets_px[pt])))
        else:
            srcs = [int(s) for s in c.get('sources', [])]
            if len(srcs) != 1 or pt not in targets_px or srcs[0] not in targets_px:
                raise ValueError(
                    'central-upright shape experiment: glyph-x-bound Dist id '
                    f"{c.get('id')} endpoints lack targets; holding all")
            pending.append((c, float(targets_px[pt] - targets_px[srcs[0]]) / scale,
                            float(targets_px[pt] - targets_px[srcs[0]])))
    changed = []
    for c, value_units, expect_px in pending:
        c['value'] = value_units
        c['round'] = False
        if abs(float(c['value']) * scale - expect_px) > 1e-9:
            raise ValueError(
                'central-upright shape experiment: replaced id '
                f"{c.get('id')} failed px verification; holding all")
        changed.append(c.get('id'))
    rec.setdefault('central_upright_shape', {})['replaced_ids'] = list(changed)
    return rec, changed


def ownership_for(targets_px, stage='central-upright-shape'):
    """Explicit x ownership rows for knot-boundary member points."""
    return [dict(point=int(p), axis=0, value=float(v), stage=stage)
            for p, v in sorted(targets_px.items())]
