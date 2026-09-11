"""Shamir 2003 §§3.2/3.6: projected relations, priorities and a scalar dependency DAG.

Two independent scalar relations define each point. Relations are selected by
published priority order; deterministic ties and cycle removals are reported.
The conditioning cutoff and default reference selection are project policies.
The two-direction system has condition number at most four. This project
policy also stays clear of FreeType 2.13.2 freedom-vector fallback.
"""
import numpy as np
from shamir_geometry import unit
from shamir_prototype import push


def priority(c):
    return (int(c['kind'].startswith('P')),int(c.get('metric',False)),
            int(c['kind'].removeprefix('P') in ('Dist','Ratio')))


def relation(kind,point,normal,sources=(),value=None,**extra):
    n=unit(np.asarray(normal,float))
    if not np.any(n):raise ValueError('zero projection')
    return dict(kind=kind,point=int(point),normal=n.tolist(),sources=list(map(int,sources)),value=value,**extra)


MAX_DIRECTION_CONDITION = 4.0


def independent(selected,c):
    if not selected:return True
    if len(selected)>=2:return False
    a,b=selected[0]['normal'],c['normal']
    # For unit rows, kappa_2(A)^2 = (1 + |dot|)/(1 - |dot|).
    # Limit error amplification, rather than merely testing nonzero determinant.
    return abs(float(np.dot(a,b))) <= (MAX_DIRECTION_CONDITION**2-1)/(MAX_DIRECTION_CONDITION**2+1)


def freeze_ratio(points,c):
    """Ordinary Ratio preserves original geometry; PRatio carries a parameter."""
    if c['kind']!='Ratio':return
    a,b=c['sources'];n=np.asarray(c['normal'])
    distance=float((points[c['point']]-points[a])@n)
    span=float((points[b]-points[a])@n)
    if abs(span)<1e-9:
        # A degenerate interval has no ratio. Translate from its first anchor
        # while retaining the original projected offset.
        c.update(kind='Dist',sources=[a],value=distance,round=False,degenerate_ratio=True)
    else:c['value']=distance/span


def ratio_coefficient(c):
    t=float(c['value'])
    if not np.isfinite(t):raise ValueError('non-finite Ratio coefficient')
    if c['kind']=='PRatio' and not 0<=t<=1:raise ValueError('shared Ratio parameter must be in [0,1]')
    coefficient=round(t*16384)
    if not -(2**31-1)<=coefficient<=2**31-1:raise ValueError('Ratio coefficient exceeds signed 32-bit arithmetic')
    return coefficient


def push_integer(value):
    """Materialize a signed stack integer without overflowing PUSHW operands."""
    if -32768<=value<=32767:return push(value)
    bits=bin(abs(value))[2:];assembly=push(1)
    for bit in bits[1:]:
        assembly+=['DUP[ ]','ADD[ ]']
        if bit=='1':assembly+=push(1)+['ADD[ ]']
    return assembly+(['NEG[ ]'] if value<0 else [])


def resolve(points,candidates,reference_points=(),scheduler="scalar"):
    """Resolve scalar degrees of freedom and all multi-source dependencies."""
    if scheduler not in ("scalar","point"):raise ValueError(f"unknown scheduler: {scheduler}")
    points=np.asarray(points,float);rejected=[];warnings=[];chosen={}
    candidates=[dict(c,id=i) for i,c in enumerate(candidates)]
    for c in candidates:freeze_ratio(points,c)
    for c in sorted(candidates,key=lambda c:(tuple(-p for p in priority(c)),c['id'])):
        group=chosen.setdefault(c['point'],[])
        if independent(group,c):group.append(c)
        else:
            reason='two degrees already constrained' if len(group)>=2 else 'dependent or ill-conditioned direction'
            rejected.append(dict(constraint=c,reason=reason))
            if any(priority(c)==priority(a) for a in group):warnings.append(dict(kind='priority tie',discarded=c['id']))
    # Complete each representative before dependent points use it. Defaults are
    # original distances/ratios; they do not add a second rounding operation.
    refs=sorted(set(reference_points))
    for p in range(len(points)):
        group=chosen.setdefault(p,[])
        normals=([np.array([-group[0]['normal'][1],group[0]['normal'][0]])]
                 if len(group)==1 else list(np.eye(2)) if not group else [])
        for slot,n in enumerate(normals):
            projection=points@n
            c=relation('Abs',p,n,value=float(projection[p]),round=False,default=True,id=len(candidates)+p*2+slot)
            eligible=[r for r in refs if r!=p]
            lower=[r for r in eligible if projection[r]<=projection[p]]
            upper=[r for r in eligible if projection[r]>=projection[p]]
            pair=None
            if lower and upper:
                a=max(lower,key=lambda r:projection[r]);b=min(upper,key=lambda r:projection[r])
                if abs(projection[b]-projection[a])>1e-9:pair=(a,b)
            if pair is None and eligible:
                # An exact reference match or an unbracketed point still has a
                # Ratio when a second distinct projected reference exists.
                a=min(eligible,key=lambda r:abs(projection[r]-projection[p]))
                distinct=[r for r in eligible if abs(projection[r]-projection[a])>1e-9]
                if distinct:
                    b=min(distinct,key=lambda r:abs(projection[r]-projection[p]))
                    pair=(a,b)
            if pair is not None:
                a,b=pair
                c.update(kind='Ratio',sources=[a,b],value=float((projection[p]-projection[a])/(projection[b]-projection[a])))
            elif eligible:
                a=min(eligible,key=lambda r:abs(projection[p]-projection[r]))
                c.update(kind='Dist',sources=[a],value=float(projection[p]-projection[a]),
                         default_reason='no distinct projected reference pair')
            else:c['default_reason']='no reference points'
            group.append(c)
    # Each relation owns one scalar coordinate. Its dual freedom vector leaves
    # the other selected projection unchanged, even if that projection has not
    # executed yet. Thus opposite x/y dependencies need not form a cycle.
    constraints=[c for p in sorted(chosen) for c in chosen[p]]
    for p,group in chosen.items():
        for slot,c in enumerate(group):
            other=np.asarray(group[1-slot]['normal'])
            freedom=unit(np.array([-other[1],other[0]]))
            if float(freedom@c['normal'])<0:freedom=-freedom
            c['freedom']=freedom.tolist()
    for c in constraints:freeze_ratio(points,c)
    if scheduler=='point':
        from shamir_point_schedule import schedule
        return schedule(points,chosen,rejected,warnings)
    by_id={c['id']:c for c in constraints}
    def dependencies(c):
        n=np.rint(np.asarray(c['normal'])*16384).astype(int)
        # Use the actual F2Dot14 vectors emitted below. A movement that only
        # appears orthogonal before native quantization is still a dependency.
        sources=c['sources']
        if c['kind'] in ('Ratio','PRatio'):
            coefficient=ratio_coefficient(c)
            if coefficient in (0,16384):sources=[sources[0 if coefficient==0 else 1]]
        return sorted({a['id'] for source in sources for a in chosen[source]
                       if int(n@np.rint(np.asarray(a['freedom'])*16384).astype(int))!=0})
    while True:
        deps={c['id']:dependencies(c) for c in constraints}
        pending=set(by_id);scalar_order=[]
        while pending:
            ready=sorted(i for i in pending if not pending.intersection(deps[i]))
            if not ready:break
            scalar_order.extend(ready);pending.difference_update(ready)
        if not pending:break
        # Remove only a relation whose scalar dependency really participates in
        # a cycle. Downstream relations and independent coordinates survive.
        def reaches(start,target,seen):
            if start==target:return True
            if start in seen:return False
            seen.add(start)
            return any(reaches(s,target,seen) for s in deps[start])
        cyclic=[by_id[i] for i in pending if any(reaches(s,i,set()) for s in deps[i])]
        c=min(cyclic,key=lambda c:(priority(c),-c['id']))
        rejected.append(dict(constraint=dict(c),reason='dependency cycle'))
        c.update(kind='Abs',sources=[],value=float(points[c['point']]@c['normal']),round=False,default=True,default_reason='dependency cycle')
        warnings.append(dict(kind='cycle removed',constraint=c['id']))
    for c in constraints:c['depends_on']=deps[c['id']]
    # Retain point completion order for reports; scheduling is explicitly scalar.
    rank={i:k for k,i in enumerate(scalar_order)}
    order=sorted(chosen,key=lambda p:max(rank[c['id']] for c in chosen[p]))
    return dict(order=order,scalar_order=scalar_order,constraints=[by_id[i] for i in scalar_order],rejected=rejected,warnings=warnings)


def compile_graph(graph,cvt_id):
    assembly=['RTG[ ]']+push(6400)+['SCVTCI[ ]']
    for c in graph['constraints']:
        p=c['point'];n=np.asarray(c['normal'])
        freedom=np.asarray(c['freedom'])
        if abs(float(freedom@n))<.0626:raise ValueError('ill-conditioned freedom vector')
        assembly+=push(*np.rint(n*16384).astype(int))+['SPVFS[ ]']
        assembly+=push(*np.rint(freedom*16384).astype(int))+['SFVFS[ ]']
        kind=c['kind'];rounded=c.get('round',True)
        if kind=='Abs':assembly+=push(p,cvt_id(c['value']))+['MIAP[1]' if rounded else 'MIAP[0]']
        elif kind=='PAbs':assembly+=push(p,cvt_id(c['value']))+['MIAP[1]' if rounded else 'MIAP[0]']
        elif kind in ('Dist','PDist'):
            assembly+=push(c['sources'][0])+['SRP0[ ]']
            if kind=='PDist':assembly+=push(p,cvt_id(abs(c['value'])))+['MIRP[00100]' if rounded else 'MIRP[00000]']
            else:assembly+=push(p)+['MDRP[00100]' if rounded else 'MDRP[00000]']
        elif kind in ('Ratio','PRatio'):
            coefficient=ratio_coefficient(c);a,b=c['sources']
            if coefficient in (0,16384):
                source=a if coefficient==0 else b
                assembly+=push(p,source)+['GC[0]','SCFS[ ]']
                continue
            # Freeze the original Ratio at 14-bit precision. IP would round
            # its projected original distances to whole font units before
            # dividing, which can change narrow-span ratios substantially.
            # Coefficient quantization contributes at most |current span|/32768
            # pixels; GC/MUL/DIV/SCFS additionally use native 26.6 arithmetic.
            assembly+=push(p,a)+['GC[0]']+push(b)+['GC[0]']+push(a)+['GC[0]','SUB[ ]']
            assembly+=push_integer(coefficient)+['MUL[ ]']+push(16384)+['DIV[ ]','ADD[ ]','SCFS[ ]']
        else:raise ValueError(f'unsupported constraint {kind}')
    return assembly
