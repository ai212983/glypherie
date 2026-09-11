"""Support-first stem experiment using our own point-equation solver.

Accepts outline geometry and numeric feature/constraint provenance only.
No Microsoft compiler, hint bytecode, or fitted-reference coordinates are used.
"""
import copy
import numpy as np
from stem_widths import inherit_widths
from feature_coordination import shared_diagonal_widths,reflected_outline,diagnostics
from shamir_baseline_solver import evaluate_baseline


class Unsupported(ValueError):
    pass


def fit(points, record, ppem, em, *, coordinate=False, ends=None, flags=None):
    p=np.asarray(points,float);features=record['features']
    graph=copy.deepcopy(record['graph']);cs=graph['constraints']
    links=cs+[a['constraint'] for a in record['attachment_resolution']]
    sections=[dict(feature=i,cvts=[f['width']]*2) for i,f in enumerate(features) if f['kind']=='slant']
    audit=inherit_widths(sections,features,links)
    if not audit:return None,dict(status='unaffected')
    if any(r['status']!='inherited' or len(r['candidates'])!=1 for r in audit):
        raise Unsupported('ambiguous supporting stem')
    members={}
    for f in features:
        for g,i in zip(f['groups'],f['points']):members.setdefault(g,set()).add(i)
    for c in links:
        name=c.get('feature','')
        if name.startswith('align-'):members.setdefault(int(name[6:]),set()).update([c['point'],*c['sources']])
    width_classes=shared_diagonal_widths(features,cs) if coordinate else []
    if coordinate:
        used={r['candidates'][0]['feature'] for r in audit}
        for index,f in enumerate(features):
            if f['kind']=='stem' and index not in used:
                audit.append(dict(section=index,status='inherited',candidates=[dict(feature=index,shared_group=f['groups'][0],width=int(np.floor(f['width']+.5)))]))
    assignments={};owned=set();support_audit=[];cap_audit=[]
    for r in audit:
        match=r['candidates'][0];stem=features[match['feature']];section=features[r['section']]
        n=np.asarray(stem['normal'],float);axis=int(np.argmax(abs(n)))
        if abs(n[1-axis])>1e-8:raise Unsupported('support stem is not cardinal')
        common=match['shared_group'];other=next(g for g in stem['groups'] if g!=common)
        extension=next(g for g in section['groups'] if g!=common)
        outer=members[common].copy();inner=members[other]|members[extension]
        if outer & inner:raise Unsupported('overlapping stem sides')
        source_outer=float(np.mean(p[list(outer),axis]));source_inner=float(np.mean(p[list(members[other]),axis]))
        outer_fit=float(np.floor(source_outer*ppem/em+.5))
        width=float(np.floor(match['width']*ppem/em+.5))
        if width<=0:raise Unsupported('stem rounds to zero width')
        inner_fit=outer_fit+np.sign(source_inner-source_outer)*width
        if coordinate:
            # Include source end-cap corners only with an exact shared height
            # and modest source flare relative to the detected stem body.
            direction=np.sign(source_inner-source_outer)
            for endpoint in sorted(outer):
                candidates=[i for i in range(len(p)) if i not in outer and
                    (flags is None or flags[i]&1) and abs(p[i,1-axis]-p[endpoint,1-axis])<1e-7 and
                    .8*match['width']<=direction*(p[i,axis]-p[endpoint,axis])<=1.2*match['width']]
                if len(candidates)==1:
                    inner.add(candidates[0]);cap_audit.append(dict(stem=match['feature'],outer=endpoint,inner=candidates[0]))
        for ids,value in ((outer,outer_fit),(inner,inner_fit)):
            for i in ids:
                # Cardinal support coordinate, rounded source longitudinal anchor.
                target=np.floor(p[i]*ppem/em+.5);target[axis]=value
                if i in assignments and np.max(abs(assignments[i]-target))>1e-9:
                    raise Unsupported('competing support positions')
                assignments[i]=target;owned.add(i)
        support_audit.append(dict(section=r['section'],stem=match['feature'],axis=axis,
                                  source_width=match['width'],fitted_width=width,outer_points=sorted(outer),inner_points=sorted(inner)))
    released=[copy.deepcopy(c) for c in cs if c['point'] in owned]
    coordinate_counts={}
    for c in cs:
        if c['point'] in owned:
            axis=coordinate_counts.get(c['point'],0)
            coordinate_counts[c['point']]=axis+1
            if axis>1:raise Unsupported('requires two equations per point')
            c.update(kind='Abs',normal=np.eye(2)[axis].tolist(),sources=[],value=float(assignments[c['point']][axis])*em/ppem,round=False)
    # Reverse a now-released alignment when its former source has the same
    # absolute line constraint: the fitted support becomes that line's parent.
    reversals=[];claimed=set()
    for c in released:
        if c['kind']!='Dist' or c.get('round',True) or not c.get('feature','').startswith('align-') or len(c['sources'])!=1:continue
        child=c['sources'][0];parent=c['point']
        if child in owned:continue
        n=np.array(c['normal'],float)
        candidates=[a for a in cs if a['point']==child and a['kind'] in ('Abs','PAbs') and abs(abs(float(np.array(a['normal'])@n)/(np.linalg.norm(a['normal'])*np.linalg.norm(n)))-1)<1e-8]
        if len(candidates)!=1:continue
        a=candidates[0]
        if a['id'] in claimed:raise Unsupported('competing diagonal support parents')
        claimed.add(a['id']);reversals.append(dict(before=copy.deepcopy(a),support_point=parent))
        normal=np.array(a['normal']);a.update(kind='Dist',sources=[parent],value=float((p[child]-p[parent])@normal),round=False)
    by_point={i:[c for c in cs if c['point']==i] for i in range(len(p))}
    pending=set(by_point);order=[]
    while pending:
        ready=sorted(i for i in pending if not {s for c in by_point[i] for s in c['sources']} & pending)
        if not ready:raise Unsupported('support dependency cycle')
        order.extend(ready);pending.difference_update(ready)
    graph['order']=order
    for c in cs:c['depends_on']=[a['id'] for a in cs if a['point'] in c['sources']]
    # Reject unresolved ill-conditioning; do not hide excursions with clipping.
    for i,pair in by_point.items():
        if len(pair)!=2:raise Unsupported('incomplete point constraints')
        matrix=np.array([c['normal'] for c in pair],float);matrix/=np.linalg.norm(matrix,axis=1)[:,None]
        if abs(np.linalg.det(matrix))<1/16:raise Unsupported(f'unresolved near-parallel equations at point {i}')
    fitted,metadata=evaluate_baseline(graph,p,ppem,em)
    solved_graph=copy.deepcopy(graph)
    symmetry=dict(status='disabled')
    if coordinate:
        if ends is None or flags is None:raise Unsupported('coordination requires contours and point tags')
        fitted,symmetry=reflected_outline(p,fitted,ends,flags,em)
        # Export the coordinated geometry through the same requested-size adapter.
        counts={}
        for c in cs:
            axis=counts.get(c['point'],0);counts[c['point']]=axis+1
            c.update(kind='Abs',normal=np.eye(2)[axis].tolist(),sources=[],depends_on=[],round=False,value=float(fitted[c['point'],axis])*em/ppem)
    return fitted,dict(status='fitted',width_classes=width_classes,caps=cap_audit,symmetry=symmetry,diagnostics=diagnostics(fitted,support_audit,symmetry),solved_graph=solved_graph,inheritance=audit,supports=support_audit,released=released,
                       reversed_alignments=reversals,order=order,graph=graph,
                       max_movement_px=float(np.max(np.linalg.norm(fitted-p*ppem/em,axis=1))))
