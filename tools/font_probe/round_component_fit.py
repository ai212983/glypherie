"""Source-curve grid-phase experiment for isolated counter-bearing components."""
import numpy as np
from shapely.affinity import scale as mirror
from repeated_rings import contours,fit as ring_fit
from joint_ring_placement import place
from cross_section_widths import system
from joint_stroke_fit import constrained_fit


def mismatch(ink,axis):
    if not ink:return 0
    xs=[x for x,y in ink];ys=[y for x,y in ink]
    reflected={(min(xs)+max(xs)-x if axis==0 else x,min(ys)+max(ys)-y if axis==1 else y) for x,y in ink}
    return len(ink^reflected)


def normalized(ink):
    if not ink:return frozenset()
    x0=min(x for x,y in ink);y0=min(y for x,y in ink)
    return frozenset((x-x0,y-y0) for x,y in ink)


def fit(source,current,tags,ends,em,size,record,ownership,raster, percentage=False):
    p,q=np.asarray(source,float),np.asarray(current,float);cs=contours(p,tags,ends);out=q.copy();audit=[]
    rows,_=system(record['graph'],len(p),size/em)
    protected=[i for i,c in enumerate(record['graph']['constraints']) if c.get('metric') or c['kind'].startswith('P')]
    hard=rows[protected]
    def allowed(trial):
        if len(hard) and np.max(abs(hard@(trial-q).ravel()))>1/128:return False
        return all(abs(trial[o['point'],o['axis']]-o['value'])<=1/128 for o in ownership)
    parents=[[j for j,d in enumerate(cs) if j!=i and d['poly'].contains(c['poly'])] for i,c in enumerate(cs)]
    groups=[]
    for i,c in enumerate(cs):
        children=[j for j,pa in enumerate(parents) if pa==[i]]
        if parents[i] or not children or not c['poly'].is_valid:continue
        if any(k not in [i,*children] and c['poly'].intersects(d['poly']) for k,d in enumerate(cs)):continue
        ids=np.concatenate([cs[k]['ids'] for k in [i,*children]])
        if all(tags[j]&1 for j in ids):continue
        poly=c['poly']
        for j in children:poly=poly.difference(cs[j]['poly'])
        if not poly.is_valid:continue
        center=((poly.bounds[0]+poly.bounds[2])/2,(poly.bounds[1]+poly.bounds[3])/2)
        axes=[axis for axis in (0,1) if poly.boundary.hausdorff_distance(mirror(poly,xfact=-1 if axis==0 else 1,yfact=-1 if axis==1 else 1,origin=center).boundary)<=em/64]
        if axes:groups.append((i,ids,axes))
    # Multiple counter-bearing components require joint placement, handled below.
    if len(groups)==1:
        outer,ids,axes=groups[0];entry=dict(stage='round-phase',contours=[int(i) for i in ids],axes=axes);audit.append(entry)
        ink=raster(q,ids,1)
        if all(mismatch(ink,a)==0 for a in axes):entry['status']='already-symmetric'
        else:
            src=p[ids]*size/em;lo=src.min(0);span=np.ptp(src,axis=0)
            old=q[ids];targetspan=np.ptp(old,axis=0);origin=old.min(0)
            if np.any(span<=0):entry['status']='held-degenerate';return out,audit
            shape=(src-lo)/span*targetspan+origin
            design=np.zeros((q.size,4));constant=q.ravel().copy()
            for point in ids:
                design[2*point]=[p[point,0]*size/em,0,1,0]
                design[2*point+1]=[0,p[point,1]*size/em,0,1]
                constant[2*point:2*point+2]=0
            equations=list(hard);targets=list(hard@q.ravel())
            for owner in ownership:
                row=np.zeros(q.size);row[2*owner['point']+owner['axis']]=1
                equations.append(row);targets.append(owner['value'])
            equations=np.asarray(equations).reshape(-1,q.size)
            affine_hard=equations@design;affine_values=np.asarray(targets)-equations@constant
            candidates=[]
            for dx in (-.5,-.25,0,.25,.5):
                for dy in (-.5,-.25,0,.25,.5):
                    trial=q.copy();trial[ids]=shape+[dx,dy]
                    try:
                        parameters=constrained_fit(affine_hard,affine_values,design,trial.ravel()-constant)
                    except ValueError:continue
                    if min(parameters[:2])<=0:continue
                    trial=(design@parameters+constant).reshape(-1,2)
                    if not allowed(trial):continue
                    if np.max(abs(np.ptp(trial[ids],axis=0)-targetspan))>1/64:continue
                    cells=raster(trial,ids,1)
                    if not cells:continue
                    fine=raster(trial,ids,8);coverage={}
                    for x,y in fine:coverage[x//8,y//8]=coverage.get((x//8,y//8),0)+1/64
                    fidelity=sum((coverage.get(cell,0)-(cell in cells))**2 for cell in set(coverage)|cells)/len(cells)
                    symmetry=sum(mismatch(cells,a) for a in axes)/len(cells)
                    movement=float(np.mean((trial[ids]-old)**2))
                    candidates.append((symmetry,fidelity+.02*movement,movement,dx,dy,trial))
            if candidates:
                best=min(candidates,key=lambda c:c[:5]);old_error=sum(mismatch(ink,a) for a in axes)/max(1,len(ink))
                if best[0]<old_error:
                    out=best[-1];entry.update(status='fitted',symmetry_before=old_error,symmetry_after=best[0])
                else:entry['status']='held-no-improvement'
            else:entry['status']='held-metrics'
    elif len(groups)>1 and not percentage:
        audit.append(dict(stage='joint-rings',status='deferred'))
    elif len(groups)>1:
        entry=dict(stage='joint-rings');audit.append(entry)
        ink=raster(q,list(range(len(p))),1)
        xs=[x for x,y in ink];ys=[y for x,y in ink]
        rotated={(min(xs)+max(xs)-x,min(ys)+max(ys)-y) for x,y in ink} if ink else set()
        if ink and ink==rotated:entry['status']='already-balanced';return out,audit
        candidate,pairs=ring_fit(p,q,tags,ends,em,size)
        if not pairs:entry['status']='held-no-repeated-ring-match';return out,audit
        candidate,placement=place(p,candidate,tags,ends,em,size,pairs)
        entry.update(pairs=pairs,placement=placement)
        if not placement or any(c['status']!='placed' for c in placement):entry['status']='held-placement'
        elif not allowed(candidate):entry['status']='held-metrics'
        else:
            before=sum(c['relative_error_before_px'] for c in placement);after=sum(c['relative_error_after_px'] for c in placement)
            if after>before+1e-8:entry['status']='held-balance-regression'
            else:out=candidate;entry['status']='fitted'
    return out,audit
