"""Geometry-only opposing outer-terminal experiment; project-authored policy.

Recognize right-facing top/bottom arms with short tip edges and curved returns.
Keep each arm fixed; place tips relative to its outer edge, preserving source tip
slope. The shared variant averages pair lengths and tip-edge magnitudes.
"""
import numpy as np


def detect(points, ends, flags, em):
    p=np.asarray(points,float); found=[]; start=0
    for end in ends:
        ids=list(range(start,end+1));start=end+1
        def walk(i,d):return ids[(ids.index(i)+d)%len(ids)]
        for base in ids:
            if not flags[base]&1:continue
            for d in (-1,1):
                previous=walk(base,-d);outer=walk(base,d);inner=walk(outer,d)
                if not all(flags[i]&1 for i in (previous,outer,inner)):continue
                if p[previous,1]!=p[base,1] or p[previous,0]>=p[base,0]:continue
                if p[base,1] not in (p[:,1].min(),p[:,1].max()):continue
                sign=1 if p[base,1]==p[:,1].max() else -1
                length=sign*(p[base,1]-p[outer,1]);tip=p[inner]-p[outer]
                if not .1*em<length<.4*em or not 0<np.linalg.norm(tip)<.15*em or tip[0]>=0:continue
                if sign*(p[base,1]-p[inner,1])<=0:continue
                chain=[inner];anchor=None
                for _ in range(min(20,len(ids)-1)):
                    nxt=walk(chain[-1],d)
                    if flags[chain[-1]]&1 and flags[nxt]&1 and p[nxt,1]==p[chain[-1],1] and p[nxt,0]<p[chain[-1],0]:
                        anchor=chain[-1];break
                    chain.append(nxt)
                if anchor is None or not any(not flags[i]&1 for i in chain):continue
                if not 0<sign*(p[base,1]-p[anchor,1])<length:continue
                found.append(dict(base=base,outer=outer,inner=inner,anchor=anchor,
                                  members=chain[:-1],sign=sign,length_fu=float(length),
                                  tip_vector=tip.tolist(),contour=end))
    pairs=[]
    for top in (r for r in found if r['sign']==1):
        for bottom in (r for r in found if r['sign']==-1):
            if top['contour']!=bottom['contour']:continue
            a={top['outer'],*top['members']};b={bottom['outer'],*bottom['members']}
            if a&b:continue
            pairs.append([top,bottom])
    return pairs


def fit(points, before, pair, scale, shared=False):
    p=np.asarray(points,float);out=np.asarray(before,float).copy()
    lengths=[r['length_fu'] for r in pair]
    widths=[np.linalg.norm(r['tip_vector']) for r in pair]
    audit=[]
    for r,width in zip(pair,widths):
        length=np.mean(lengths) if shared else r['length_fu']
        fitted_length=float(np.floor(length*scale+.5))
        tip=np.asarray(r['tip_vector'])*scale
        if shared:tip*=float(np.mean(widths))/width
        outer,inner,anchor=r['outer'],r['inner'],r['anchor']
        out[outer,1]=out[r['base'],1]-r['sign']*fitted_length
        out[inner]=out[outer]+tip
        for i in r['members'][1:]:
            for axis in (0,1):
                distance=p[anchor,axis]-p[inner,axis]
                if distance==0:raise ValueError('degenerate return-curve interpolation')
                t=(p[i,axis]-p[inner,axis])/distance
                out[i,axis]=out[inner,axis]+t*(out[anchor,axis]-out[inner,axis])
        audit.append(dict(length_px=fitted_length,tip_vector_px=tip.tolist()))
    return out,audit
