"""Automatic vertical stem anchors and proportional curve interpolation.

Hersch's shared widths/support-point interpolation motivate the constraints;
feature thresholds and anchor fitting here are experimental project choices.
"""
import math
import numpy as np


def geometry(points,tags,ends,size):
    # Pair opposed vertical line segments. Winding at the overlap midpoint
    # distinguishes solid strips from counters; quadratic curves are subdivided.
    if any(t==2 for t in tags):return [],[]
    edges=[];segments=[];start=0
    for end in ends:
        ids=list(range(start,end+1));start=end+1
        expanded=[]
        for k,i in enumerate(ids):
            j=ids[(k+1)%len(ids)]
            expanded.append((points[i],tags[i]))
            if tags[i]==tags[j]==0:expanded.append(((points[i]+points[j])/2,1))
            if tags[i]==tags[j]==1 and abs(points[i,0]-points[j,0])<1e-5 and abs(points[i,1]-points[j,1])>=size*.15:
                edges.append((i,j))
        first=next((i for i,p in enumerate(expanded) if p[1]==1),None)
        if first is None:continue
        expanded=expanded[first:]+expanded[:first];expanded.append(expanded[0]);k=0
        while k<len(expanded)-1:
            a=expanded[k][0]
            if expanded[k+1][1]==1:
                segments.append((a,expanded[k+1][0]));k+=1
            else:
                b=expanded[k+1][0];c=expanded[k+2][0];last=a
                for t in np.linspace(0,1,25)[1:]:
                    p=(1-t)**2*a+2*t*(1-t)*b+t*t*c
                    segments.append((last,p));last=p
                k+=2
    return edges,segments


def contains(segments,x,y):
    winding=0
    for a,b in segments:
        if min(a[1],b[1])<=y<max(a[1],b[1]):
            cross=a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])
            if cross>x:winding+=1 if b[1]>a[1] else -1
    return winding!=0


def stems(points,tags,ends,size):
    edges,segments=geometry(points,tags,ends,size)
    found=[]
    for k,e in enumerate(edges):
        a,b=points[list(e)]
        for f in edges[k+1:]:
            c,d=points[list(f)]
            if (b[1]-a[1])*(d[1]-c[1])>=0:continue
            lo=max(min(a[1],b[1]),min(c[1],d[1]));hi=min(max(a[1],b[1]),max(c[1],d[1]))
            width=abs(a[0]-c[0])
            if hi-lo<size*.15 or not .4<=width<=size*.16:continue
            if not all(contains(segments,a[0]+(c[0]-a[0])*t,lo+(hi-lo)*u) for t in (.2,.5,.8) for u in (.2,.5,.8)):continue
            left,right=(e,f) if a[0]<c[0] else (f,e)
            found.append(dict(left=left,right=right,width=width))
    used=set();chosen=[]
    for p in sorted(found,key=lambda p:p['width']):
        if p['left'] in used or p['right'] in used:continue
        chosen.append(p);used.update((p['left'],p['right']))
    return chosen


def fit_stems(source,hinted,tags,ends,size,table,bowls=False):
    detected=stems(source,tags,ends,size)
    curved=[]
    if bowls:
        from bowl_gridfit import bowl_pairs
        curved=bowl_pairs(source,tags,ends,size)
    info=dict(status='no vertical stems',stems=detected,curved_sides=curved)
    detected=detected+curved
    if not detected:return hinted,info
    anchors={}
    for stem in detected:
        left,right=stem['left'],stem['right']
        width=min(table,key=lambda r:abs(r['source']-stem['width']))['target']
        centre=(hinted[list(left),0].mean()+hinted[list(right),0].mean())/2
        target_left=math.floor(centre-width/2+.5)
        stem['target']=width
        for edge,target in ((left,target_left),(right,target_left+width)):
            x=float(source[edge[0],0]);anchors.setdefault(x,[]).append(target)
    if any(max(v)!=min(v) for v in anchors.values()):
        info['status']='conflicting stem anchors; native fallback';return hinted,info
    xs=np.array(sorted(anchors));ys=np.array([anchors[x][0] for x in xs])
    if np.any(np.diff(ys)<=0):
        info['status']='collapsed anchor interval; native fallback';return hinted,info
    result=hinted.copy()
    # Preserve source proportions between supports, and translate outside them.
    result[:,0]=np.interp(source[:,0],xs,ys)
    low=source[:,0]<xs[0];high=source[:,0]>xs[-1]
    result[low,0]=source[low,0]+ys[0]-xs[0]
    result[high,0]=source[high,0]+ys[-1]-xs[-1]
    displacement=float(np.max(np.abs(result-hinted)))
    info['max_displacement_px']=displacement
    if displacement>1:
        info['status']='stem displacement exceeds 1px; native fallback';return hinted,info
    info['status']='stem outlines constrained'
    return result,info
