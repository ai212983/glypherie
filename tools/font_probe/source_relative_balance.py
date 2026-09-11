"""Source-relative opposing stroke goals; geometry-only, single-counter scope."""
import numpy as np
from shapely.affinity import scale as mirror
from repeated_rings import contours
from outline_relationships import samples
from cross_section_widths import system
from joint_stroke_fit import constrained_fit


def crossings(weights,points,axis,level):
    xy=weights@points;result=[]
    for i,a in enumerate(xy):
        j=(i+1)%len(xy);b=xy[j]
        if (a[axis]<=level<b[axis]) or (b[axis]<=level<a[axis]):
            t=(level-a[axis])/(b[axis]-a[axis]);result.append((1-t)*weights[i]+t*weights[j])
    return sorted(result,key=lambda w:float(w@points[:,1-axis]))


def fit(points,current,ends,tags,scale,em,record,ownership=(),strength=4.):
    p=np.asarray(points,float);q=np.asarray(current,float);cs=contours(p,tags,ends)
    if len(cs)!=2:return q,dict(status='no-match')
    outer=next((i for i,c in enumerate(cs) if c['poly'].contains(cs[1-i]['poly'])),None)
    if outer is None:return q,dict(status='no-match')
    hull=cs[outer]['poly'].convex_hull
    if hull.area<=0 or (hull.area-cs[outer]['poly'].area)/hull.area>.01:
        return q,dict(status='no-match')
    inner=1-outer;shape=cs[outer]['poly'].difference(cs[inner]['poly'])
    center=((shape.bounds[0]+shape.bounds[2])/2,(shape.bounds[1]+shape.bounds[3])/2)
    error=shape.boundary.hausdorff_distance(mirror(shape,xfact=-1,yfact=1,origin=center).boundary)
    if error>em/64:return q,dict(status='no-match')
    curves=samples(p,ends,tags);profiles=[];goals=list(np.eye(q.size));targets=list(q.ravel())
    for fixed in (0,1):
        moving=1-fixed
        lo,hi=cs[inner]['lo'][fixed],cs[inner]['hi'][fixed]
        for fraction in (.2,.3,.4,.5,.6,.7,.8):
            level=lo+(hi-lo)*fraction
            outside=crossings(curves[outer],p,fixed,level);inside=crossings(curves[inner],p,fixed,level)
            if len(outside)!=2 or len(inside)!=2:continue
            a,d=outside;b,c=inside
            difference=b-a-d+c
            row=np.zeros(q.size);row[moving::2]=difference
            source=float(difference@p[:,moving]*scale)
            goals.append(strength*row);targets.append(strength*source)
            # Corresponding source sections should stay at one fitted level.
            for other in (b,c,d):
                alignment=np.zeros(q.size);alignment[fixed::2]=other-a
                goals.append(strength*alignment);targets.append(0.)
            profiles.append(dict(axis=moving,fraction=fraction,source_difference_px=source,
                before_difference_px=float(row@q.ravel()),row=row))
    if not profiles:return q,dict(status='no-match')
    rows,_=system(record['graph'],len(p),scale)
    protected=[i for i,c in enumerate(record['graph']['constraints']) if c.get('metric') or c['kind'].startswith('P')]
    hard=list(rows[protected]);values=list(rows[protected]@q.ravel())
    for o in ownership:
        row=np.zeros(q.size);row[2*o['point']+o['axis']]=1;hard.append(row);values.append(o['value'])
    for axis in (0,1):
        # Retain outer bounds and inner extent, permitting counter translation.
        a=int(cs[outer]['ids'][np.argmin(p[cs[outer]['ids'],axis])]);b=int(cs[outer]['ids'][np.argmax(p[cs[outer]['ids'],axis])])
        for i in (a,b):
            row=np.zeros(q.size);row[2*i+axis]=1;hard.append(row);values.append(q[i,axis])
        a=int(cs[inner]['ids'][np.argmin(p[cs[inner]['ids'],axis])]);b=int(cs[inner]['ids'][np.argmax(p[cs[inner]['ids'],axis])])
        row=np.zeros(q.size);row[2*b+axis]=1;row[2*a+axis]=-1;hard.append(row);values.append(q[b,axis]-q[a,axis])
    candidate=constrained_fit(hard,values,goals,targets).reshape(-1,2)
    for profile in profiles:
        row=profile.pop('row');profile['after_difference_px']=float(row@candidate.ravel())
    return candidate,dict(status='fitted',profiles=profiles,strength=strength,
        source_reflection_error_units=error,max_hard_residual_px=float(np.max(abs(np.asarray(hard)@candidate.ravel()-values))))
