"""Whole-point dependency scheduling for the Shamir 2003 comparison.

Constraint selection, defaults, priorities and native translation are shared with
scalar mode. Every declared source must complete before its target point. Cycle
removal discards the lowest-priority participating relation, retaining the shared
unrounded original-position fallback. Declaration order resolves equal priorities.
"""
import numpy as np


def schedule(points,chosen,rejected,warnings):
    from shamir_constraints import priority
    while True:
        deps={p:{s for c in group for s in c['sources']} for p,group in chosen.items()}
        pending=set(chosen);order=[]
        while pending:
            ready=sorted(p for p in pending if not pending.intersection(deps[p]))
            if not ready:break
            order.extend(ready);pending.difference_update(ready)
        if not pending:break
        def reaches(start,target,seen):
            if start==target:return True
            if start in seen:return False
            seen.add(start)
            return any(reaches(s,target,seen) for s in deps[start])
        cyclic=[c for p in pending for c in chosen[p]
                if any(reaches(s,p,set()) for s in c['sources'])]
        c=min(cyclic,key=lambda c:(priority(c),-c['id']))
        rejected.append(dict(constraint=dict(c),reason='dependency cycle'))
        c.update(kind='Abs',sources=[],value=float(points[c['point']]@np.asarray(c['normal'])),
                 round=False,default=True,default_reason='dependency cycle')
        warnings.append(dict(kind='cycle removed',constraint=c['id']))
    constraints=[c for p in order for c in chosen[p]]
    for c in constraints:
        c['depends_on']=sorted({a['id'] for s in c['sources'] for a in chosen[s]})
    return dict(order=order,scalar_order=[c['id'] for c in constraints],constraints=constraints,
                rejected=rejected,warnings=warnings,scheduler='point')
