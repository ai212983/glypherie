"""Experimental sampled normal-width constraints for quadratic curved strokes.

Paired curve samples share the font's measured width references. Detection,
regularization and bounds are project choices; no glyph names or pixel edits.
"""
import numpy as np
from shapely.geometry import Point
from source_constraints import source_shape
from stem_gridfit import stems


def samples(points,tags,ends):
    n=len(points);basis=np.eye(n);result=[];start=0
    if any(t==2 for t in tags):return result
    for end in ends:
        ids=list(range(start,end+1));start=end+1;expanded=[]
        for k,i in enumerate(ids):
            j=ids[(k+1)%len(ids)];expanded.append((basis[i],tags[i]))
            if tags[i]==tags[j]==0:expanded.append(((basis[i]+basis[j])/2,1))
        first=next((k for k,(_,tag) in enumerate(expanded) if tag==1),None)
        if first is None:continue
        expanded=expanded[first:]+expanded[:first];expanded.append(expanded[0]);k=0
        while k<len(expanded)-1:
            a=expanded[k][0]
            if expanded[k+1][1]==1:k+=1;continue
            b,c=expanded[k+1][0],expanded[k+2][0]
            for t in np.linspace(.1,.9,5):
                w=(1-t)**2*a+2*t*(1-t)*b+t*t*c
                derivative=(2*(1-t)*(b-a)+2*t*(c-b))@points
                length=np.linalg.norm(derivative)
                if length>1e-8:result.append((w,w@points,derivative/length))
            k+=2
    return result


def fit_curves(source,current,tags,ends,size,table):
    info=dict(status='no paired curves',pairs=0)
    if stems(source,tags,ends,size):
        info['status']='mixed straight stems and curves; retained outline'
        return current,info
    start=0
    for end in ends:
        for i in range(start,end+1):
            j=start if i==end else i+1;dx,dy=source[j]-source[i]
            if tags[i]==tags[j]==1 and abs(dy)>size*.15 and .2<abs(dx/dy)<3:
                info['status']='long straight diagonals; retained outline'
                return current,info
        start=end+1
    sampled=samples(source,tags,ends)
    if not sampled or not table:return current,info
    shape=source_shape(source,tags,ends,size)
    positions=np.array([s[1] for s in sampled]);directions=np.array([s[2] for s in sampled])
    constraints=[];targets=[];seen=set();n=len(source)
    for i,(weights,p,tangent) in enumerate(sampled):
        offsets=positions-p;normal=np.array([-tangent[1],tangent[0]])
        along=np.abs(offsets@tangent);distance=np.linalg.norm(offsets,axis=1)
        eligible=np.where((distance>=.4)&(distance<=size*.16)&(along<distance*.12)&(directions@tangent<-.85))[0]
        for j in sorted(eligible,key=lambda j:distance[j]):
            pair=tuple(sorted((i,int(j))))
            if pair in seen:break
            q=positions[j]
            if not all(shape.covers(Point(*(p+(q-p)*t))) for t in (.2,.5,.8)):continue
            separation=float((q-p)@normal)
            reference=min(table,key=lambda r:abs(r['source']-abs(separation)))
            if abs(abs(separation)-reference['source'])>reference['source']*.25:continue
            # Preserve within-stroke source variation around its shared reference.
            target=separation*reference['target']/reference['source']
            row=np.zeros((n,2));row[:,0]=(sampled[j][0]-weights)*normal[0];row[:,1]=(sampled[j][0]-weights)*normal[1]
            constraints.append(row.ravel());targets.append(target);seen.add(pair);break
    info['pairs']=len(constraints)
    if not constraints:return current,info
    # Preserve fitted straight stems and the vertical extrema used for alignment.
    pinned=set()
    for stem in stems(source,tags,ends,size):
        for i in stem['left']+stem['right']:pinned.update((2*i,2*i+1))
    for i in range(n):
        if abs(source[i,1]-source[:,1].min())<1e-5 or abs(source[i,1]-source[:,1].max())<1e-5:pinned.add(2*i+1)
    free=[i for i in range(2*n) if i not in pinned]
    if not free:info['status']='all curve points anchored';return current,info
    a=np.array(constraints);base=current.ravel();rhs=np.array(targets)-a@base
    # Soft constraints accommodate differing curvature and imperfect sample pairs.
    reduced=a[:,free];regularizer=.2
    matrix=np.vstack([reduced,regularizer*np.eye(len(free))])
    delta=np.linalg.lstsq(matrix,np.r_[rhs,np.zeros(len(free))],rcond=None)[0]
    info['max_displacement_px']=float(np.max(np.abs(delta)))
    if info['max_displacement_px']>.5:
        info['status']='curve displacement exceeds 0.5px; retained outline';return current,info
    result=base.copy();result[free]+=delta
    info.update(status='curved stroke constrained',residual_before=float(np.sqrt(np.mean(rhs**2))),
                residual_after=float(np.sqrt(np.mean((a@result-np.array(targets))**2))))
    return result.reshape((-1,2)),info
