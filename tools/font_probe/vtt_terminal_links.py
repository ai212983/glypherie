"""Bounded terminal-role detection and native MIRP/IP experiment.

Role selection and shared-value averaging are project policies. Instruction
semantics follow VTT's cardinal Link and unrounded Interpolate primitives.
"""
import numpy as np
from shamir_prototype import push


def candidates(points, flags, ends, audit=None):
    p=np.asarray(points); hits=[];start=0
    for end in ends:
        contour=list(range(start,end+1));start=end+1
        on=[i for i in contour if flags[i]&1]
        def walk(i,d):return contour[(contour.index(i)+d)%len(contour)]
        def bracket(i,d):
            ids=[i]
            for _ in range(20):
                j=walk(ids[-1],d)
                if flags[ids[-1]]&1 and flags[j]&1 and p[j,1]==p[ids[-1],1] and p[j,0]!=p[ids[-1],0]:
                    return ids
                ids.append(j)
            return None
        for a in on:
            b=walk(a,1)
            if not flags[b]&1 or p[a,0]!=p[b,0] or p[a,1]<=p[b,1]:continue
            upper=bracket(a,-1);lower=bracket(b,1)
            if upper is None or lower is None:continue
            u,l=upper[-1],lower[-1]
            def reject(reason):
                if audit is not None:audit.append(dict(edge=[a,b],upper_arm=u,lower_arm=l,reason=reason))
            if not (p[a,1]>p[u,1]>p[l,1]>min(p[i,1] for i in lower)):
                reject('extensions do not bracket ordered arm anchors');continue
            if not (p[u,0]<p[a,0] and p[l,0]<p[b,0]):
                reject('arm anchors are not both left of the terminal');continue
            bottom=min(lower,key=lambda i:p[i,1])
            if not flags[bottom]&1 or bottom==l:
                reject('lower extremum is not a distinct on-curve endpoint');continue
            hits.append(dict(top=a,bottom=bottom,upper_arm=u,lower_arm=l,
                             upper=upper[1:-1],lower=lower[lower.index(bottom)+1:-1],
                             tip=lower[:lower.index(bottom)]))
    return hits


def detect(points, flags, ends):
    hits=candidates(points,flags,ends)
    if len(hits)!=1:raise ValueError(f'expected one supported right terminal; found {len(hits)}')
    return hits[0]


def program(roles, cvt_indices, *, round_down=False):
    # CVT cut-in of one pixel includes our near-equal shared measurements.
    a=['SVTCA[0]','RDTG[ ]' if round_down else 'RTG[ ]','FLIPON[ ]']+push(64)+['SCVTCI[ ]']+push(0)+['SSWCI[ ]']
    for parent,child,cvt in [(roles['upper_arm'],roles['top'],cvt_indices[0]),
                             (roles['lower_arm'],roles['bottom'],cvt_indices[1])]:
        a+=push(parent)+['SRP0[ ]']+push(child)+push(cvt)+['MIRP[00100]']
    for first,last,children in [(roles['upper_arm'],roles['top'],roles['upper']),
                                 (roles['bottom'],roles['lower_arm'],roles['lower']),
                                 (roles['top'],roles['bottom'],roles['tip'])]:
        a+=push(first)+['SRP1[ ]']+push(last)+['SRP2[ ]']
        for child in children:a+=push(child)+['IP[ ]']
    return a


def values(points, roles, shared):
    upper=int(points[roles['top']][1]-points[roles['upper_arm']][1])
    lower=int(points[roles['lower_arm']][1]-points[roles['bottom']][1])
    return [int(np.floor((upper+lower)/2+.5))]*2 if shared else [upper,lower]
