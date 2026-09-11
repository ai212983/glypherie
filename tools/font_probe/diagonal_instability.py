"""VTT-derived conditioning diagnostic and explicit cardinal override experiment.

The 1/16 check follows VTT AlmostPerpendicular. Replacing an alignment is our
policy, not CalcDiagonalFVMT's previousAlign branch. The latter retains the
unstable movement direction. No character/family identity crosses this API.
"""
import copy
import numpy as np


def inspect_graph(graph):
    rows=[]
    for point in graph['order']:
        pair=[c for c in graph['constraints'] if c['point']==point]
        if len(pair)!=2:raise ValueError('requires whole-point graph')
        normals=np.array([c['normal'] for c in pair],float)
        normals/=np.linalg.norm(normals,axis=1)[:,None]
        dot=abs(float(np.linalg.det(normals)))
        if dot<1/16:
            rows.append(dict(point=point,equivalent_projection_freedom_dot=dot,
                             constraints=copy.deepcopy(pair),status='unsafe'))
    return rows


def cardinal_override(graph, points):
    result=copy.deepcopy(graph);points=np.asarray(points,float);audit=inspect_graph(graph)
    for row in audit:
        pair=row['constraints']
        widths=[c for c in pair if c['kind'] in ('Dist','PDist') and c.get('feature','').startswith('width-')]
        aligns=[c for c in pair if c['kind']=='Dist' and c.get('feature','').startswith('align-') and not c.get('round',True)]
        if len(widths)!=1 or len(aligns)!=1:
            row.update(status='held',reason='requires one width and one unrounded segment alignment');continue
        width=widths[0];align=aligns[0];axis=int(np.argmax(abs(np.array(width['normal']))));other=1-axis
        parent,=width['sources'];p=width['point'];n=np.eye(2)[other]
        replacement=dict(align,normal=n.tolist(),sources=[parent],value=float((points[p]-points[parent])@n),
                         feature='experimental-cardinal-companion',round=False)
        result['constraints']=[replacement if c['id']==align['id'] else c for c in result['constraints']]
        row.update(status='overridden',movement_axis='x' if axis==0 else 'y',released=align,replacement=replacement,
                   retained_width=width)
    for c in result['constraints'] if any(r['status']=='overridden' for r in audit) else []:
        c['depends_on']=[a['id'] for a in result['constraints'] if a['point'] in c['sources']]
    return result,audit
