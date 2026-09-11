"""Experimental, bounded representative coordination before point scheduling.

Only existing on-curve segment members are candidates. The score counts rejected
relations by published priority (highest first), then cycle removals. No pixel
coordinates or ppem enter selection. Font measurements and authored templates
are held fixed. This search policy is not specified by Shamir 2003.
"""
from contextlib import contextmanager
from itertools import combinations, product
import numpy as np
from shamir_constraints import priority
from shamir_segment_dominance import dominant_relations
from shamir_shared_roles import close_shared_roles
from shamir_baseline_solver import resolve_baseline


def evaluate(model, tables, em, construct):
    cs, links, reps = construct(model, tables, em, baseline=True)
    cs, _ = dominant_relations(cs)
    templates = model.get('template_constraints', [])
    cs += [c for c in templates if not c.get('template_member')]
    links += [c for c in templates if c.get('template_member')]
    reps.update(c['point'] for c in templates if not c.get('template_member'))
    reps.update(s for c in templates for s in c['sources'])
    roles = close_shared_roles(cs, links, reps)
    ids = sorted(reps); index = {p:i for i,p in enumerate(ids)}
    candidates = [dict(c, point=index[c['point']], sources=[index[s] for s in c['sources']])
                  for c in roles['reduced_candidates']]
    graph = resolve_baseline(model['points'][ids], candidates)
    rejected = graph['rejected']
    priorities = [(a,b,c) for a in (1,0) for b in (1,0) for c in (1,0)]
    score = tuple(sum(priority(r['constraint']) == p for r in rejected) for p in priorities)
    cycles = sum(r['reason'] == 'dependency cycle' for r in rejected)
    return score + (cycles,), cycles


def coordinate_representatives(model, tables, em, construct, budget=256):
    groups = [i for i,g in enumerate(model['groups']) if g['members']]
    points = np.asarray(model['points'])
    def point_key(p): return tuple(points[p])
    groups.sort(key=lambda i:(tuple(model['groups'][i]['normal']),
                             tuple(sorted(point_key(p) for p in model['groups'][i]['members']))))
    original = tuple(model['groups'][i]['rep'] for i in groups)
    options = [[p for p in sorted(model['groups'][i]['members'], key=point_key)
                if model['glyph'].flags[p] & 1] for i in groups]
    score, cycles = evaluate(model,tables,em,construct)
    initial_score, initial_cycles = score, cycles
    evaluations = 1; sweeps = 0; changed = True
    # Preserve already acyclic constructions. Otherwise coordinate descent uses
    # strict improvement, geometry-ordered traversal and a declared work bound.
    while cycles and changed and evaluations < budget:
        changed = False; sweeps += 1
        for i, candidates in zip(groups, options):
            incumbent = model['groups'][i]['rep']; best = incumbent
            best_score, best_cycles = score, cycles
            for p in candidates:
                if p == incumbent: continue
                if evaluations >= budget: break
                model['groups'][i]['rep'] = p
                trial, count = evaluate(model,tables,em,construct); evaluations += 1
                if trial < best_score: best, best_score, best_cycles = p, trial, count
            model['groups'][i]['rep'] = best
            if best != incumbent: changed = True
            score, cycles = best_score, best_cycles
        if not changed and cycles and evaluations < budget:
            # A shared corner can require coordinated changes to two segments.
            # Try pairs only after a single-coordinate sweep stalls.
            best_pair = None; best_score, best_cycles = score, cycles
            for a,b in combinations(range(len(groups)),2):
                ga,gb=groups[a],groups[b]
                olda,oldb=model['groups'][ga]['rep'],model['groups'][gb]['rep']
                for pa,pb in product(options[a],options[b]):
                    if pa==olda or pb==oldb: continue
                    if evaluations>=budget: break
                    model['groups'][ga]['rep']=pa;model['groups'][gb]['rep']=pb
                    trial,count=evaluate(model,tables,em,construct);evaluations+=1
                    if trial<best_score:
                        best_pair=(ga,pa,gb,pb);best_score,best_cycles=trial,count
                model['groups'][ga]['rep']=olda;model['groups'][gb]['rep']=oldb
                if evaluations>=budget: break
            if best_pair:
                ga,pa,gb,pb=best_pair
                model['groups'][ga]['rep']=pa;model['groups'][gb]['rep']=pb
                score,cycles=best_score,best_cycles;changed=True
        if not changed: break
    selected = tuple(model['groups'][i]['rep'] for i in groups)
    return dict(classification='experimental representative coordination',
                budget=budget, evaluations=evaluations, sweeps=sweeps,
                initial_score=initial_score, selected_score=score,
                initial_cycles=initial_cycles, selected_cycles=cycles,
                budget_exhausted=evaluations>=budget,
                changes=[dict(group=i, before=a, after=b) for i,a,b in zip(groups,original,selected) if a!=b],
                selection_uses_pixels=False, measurements='fixed before search')


@contextmanager
def representative_override(budget=256):
    import shamir_model
    original = shamir_model.constraints_for
    audits = []
    def configured(model,tables,em,baseline=False):
        if baseline:
            audits.append(coordinate_representatives(model,tables,em,original,budget))
        return original(model,tables,em,baseline=baseline)
    shamir_model.constraints_for = configured
    try: yield audits
    finally: shamir_model.constraints_for = original
