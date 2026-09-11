"""Identity-free candidate correction boundary; fixed stages for every outline.

Experimental interpretations remain separate from the paper baseline. This API
accepts geometry, scale and equations only; selection identities stay in the I/O
adapter. Unsupported construction is explicit, never an inherited-program fallback.
"""
from dataclasses import dataclass
import re
import numpy as np
from shamir_reorientation import prototype, Unsupported
from shamir_parent_anchor import experiment
from vtt_serif_experiment import detect as serif_roles, fit as fit_serifs
from vtt_terminal_links import candidates, values, program
from shamir_constraints import relation
from shamir_baseline_solver import compile_baseline
from opposing_terminals import detect as opposing_roles, fit as fit_opposing

STAGES = ('reorientation', 'parent-anchor', 'serifs', 'coordinated-terminals', 'paired-terminal')
_FIELDS = {'kind','point','normal','sources','value','round','default','default_reason',
           'feature','segment_owner','metric','metric_role','id','depends_on'}


def equation(raw):
    result = {k: raw[k] for k in _FIELDS if k in raw}
    # Provenance used by the existing algorithms has a numeric role vocabulary.
    if 'feature' in result and not re.fullmatch(r'(?:align|segment)-\d+', result['feature']):
        result.pop('feature')
    if 'default_reason' in result and result['default_reason'] != 'dependency cycle':
        result.pop('default_reason')
    return result


@dataclass(frozen=True, slots=True)
class Geometry:
    points: tuple
    ends: tuple
    flags: tuple
    ppem: int
    em: int
    constraints: tuple
    members: tuple

    def __post_init__(self):
        object.__setattr__(self,'constraints',tuple(equation(c) for c in self.constraints))
        object.__setattr__(self,'members',tuple(equation(c) for c in self.members))


def correct(data, center_fit=None):
    if type(data) is not Geometry:
        raise TypeError('correction requires Geometry')
    points = np.asarray(data.points, float)
    record = dict(graph=dict(constraints=[equation(c) for c in data.constraints],
                  baseline_execution=dict(model_points_px=points.tolist(), ppem=data.ppem, em=data.em)),
                  attachment_resolution=[dict(constraint=equation(c)) for c in data.members])
    oriented = prototype(record)
    parent = experiment(oriented, points, data.ppem, data.em, False)
    before = np.asarray(parent['graph']['baseline_execution']['model_points_px'])
    early = None
    if center_fit is not None:
        before, early = center_fit(points, data.ends, data.flags, before, data.ppem / data.em)
        before = np.asarray(before, float)
    halves = serif_roles(points, data.ends, data.flags, data.em)
    fitted, serif_audit = fit_serifs(points, before, halves, data.ppem/data.em)
    hits = candidates(points, data.flags, data.ends)
    if len(hits)>1:
        raise Unsupported('multiple terminal pairs require a joint ownership policy')
    if hits:
        r=hits[0]; terminal={r['top'],r['bottom'],*r['upper'],*r['lower'],*r['tip']}
        if terminal & {i for h in halves for i in h['members']}:
            raise Unsupported('serif and terminal ownership overlap')
    cs=[dict(relation('Abs',i,np.eye(2)[axis],value=float(p[axis])*data.em/data.ppem,round=False),
             id=2*i+axis,depends_on=[]) for i,p in enumerate(fitted) for axis in (0,1)]
    graph=dict(order=list(range(len(points))),constraints=cs,scheduler='point')
    assembly, metadata=compile_baseline(graph,points,data.ppem,data.em)
    opposing=opposing_roles(points,data.ends,data.flags,data.em)
    if len(opposing)>1:
        raise Unsupported('multiple opposing terminal pairs require joint ownership')
    opposing_audit=[]
    if opposing:
        owned={r['outer'] for r in opposing[0]}|{i for r in opposing[0] for i in r['members']}
        occupied={i for h in halves for i in h['members']}
        for r in hits:
            occupied.update([r['top'],r['bottom'],r['upper_arm'],r['lower_arm'],*r['upper'],*r['lower'],*r['tip']])
        if owned & occupied:
            raise Unsupported('opposing terminals overlap another correction')
        fitted,opposing_audit=fit_opposing(points,metadata['native_points_px'],opposing[0],data.ppem/data.em)
        for c in cs:c['value']=float(fitted[c['point']]@np.array(c['normal']))*data.em/data.ppem
        assembly,metadata=compile_baseline(graph,points,data.ppem,data.em)
    result = dict(assembly=assembly, preterminal=metadata['native_points_px'], terminal=hits,
                opposing=opposing, opposing_audit=opposing_audit,
                stages=list(STAGES), parent_changes=parent['changes'], serif_audit=serif_audit,
                reorientation_removed=oriented['removed'])
    if center_fit is not None:
        result['central_upright'] = early
        result['central_upright_mapped'] = np.asarray(before, float).tolist()
    return result


def finish(result, data, cvt_index):
    assembly=list(result['assembly']); expected=np.round(np.asarray(result['preterminal'])*64)/64
    cvt=[]
    if result['terminal']:
        r,=result['terminal']; value=min(values(data.points,r,False)); cvt=[value]
        scaled=np.floor(value*data.ppem/data.em*64+.5)/64
        points=np.asarray(data.points)
        for parent, child in [(r['upper_arm'],r['top']),(r['lower_arm'],r['bottom'])]:
            distance=(points[child,1]-points[parent,1])*data.ppem/data.em
            if abs(abs(distance)-scaled)>=1:
                raise Unsupported('shared terminal distance exceeds CVT cut-in')
            expected[child,1]=expected[parent,1]+np.sign(distance)*np.floor(scaled)
        for a,b,children in [(r['upper_arm'],r['top'],r['upper']),
                              (r['bottom'],r['lower_arm'],r['lower']),
                              (r['top'],r['bottom'],r['tip'])]:
            for i in children:
                t=(points[i,1]-points[a,1])/(points[b,1]-points[a,1])
                expected[i,1]=expected[a,1]+t*(expected[b,1]-expected[a,1])
        assembly=assembly[:-1]+program(r,[cvt_index,cvt_index],round_down=True)+assembly[-1:]
    return assembly,cvt,expected
