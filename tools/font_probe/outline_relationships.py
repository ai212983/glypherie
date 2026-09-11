"""Source contour-order constraints and sampled-curve reflection correspondence."""
import numpy as np
from joint_stroke_fit import constrained_fit
from cross_section_widths import system


def reversed_edges(source, fitted, ends, flags):
    p,q=np.asarray(source),np.asarray(fitted); result=[];start=0
    for end in ends:
        for a in range(start,end+1):
            b=a+1 if a<end else start
            if not(flags[a]&1 and flags[b]&1):continue
            delta=p[b]-p[a]
            axes=np.flatnonzero(abs(delta)>1e-8)
            if len(axes)!=1:continue
            axis=int(axes[0])
            if delta[axis]*(q[b,axis]-q[a,axis]) < -1e-7:
                result.append(dict(a=a,b=b,axis=axis,value=float(delta[axis]),stage='contour-order'))
        start=end+1
    return result


def recover_order(points, fitted, ends, flags, record, scale):
    source=np.asarray(points)*scale
    claims=reversed_edges(source,fitted,ends,flags)
    if not claims:return np.asarray(fitted),claims
    rows,values=system(record['graph'],len(source),scale)
    ids=[i for i,c in enumerate(record['graph']['constraints']) if c.get('metric') or c['kind'].startswith('P')]
    hard=list(rows[ids]);targets=list(values[ids])
    for c in claims:
        row=np.zeros(source.size);row[2*c['b']+c['axis']]=1;row[2*c['a']+c['axis']]=-1
        hard.append(row);targets.append(c['value'])
    q=constrained_fit(hard,targets,np.eye(source.size),np.asarray(fitted).ravel()).reshape(-1,2)
    if reversed_edges(source,q,ends,flags):raise ValueError('contour-order recovery leaves an inversion')
    return q,claims


def samples(points, ends, flags, count=256):
    """Arc-length samples as linear combinations of quadratic outline points."""
    p=np.asarray(points,float);basis=np.eye(len(p));result=[];start=0
    for end in ends:
        ids=list(range(start,end+1));start=end+1
        on=next((i for i in ids if flags[i]&1),None)
        if on is None:
            initial=(basis[ids[-1]]+basis[ids[0]])/2;remaining=ids[:]
        else:
            k=ids.index(on);ids=ids[k:]+ids[:k];initial=basis[ids[0]];remaining=ids[1:]
        current=initial;nodes=[];i=0
        while i<=len(remaining):
            if i==len(remaining):
                target=initial;nodes.extend([(1-t)*current+t*target for t in np.linspace(0,1,17)[:-1]]);break
            j=remaining[i]
            if flags[j]&1:
                target=basis[j];nodes.extend([(1-t)*current+t*target for t in np.linspace(0,1,17)[:-1]]);current=target;i+=1
            else:
                control=basis[j]
                if i+1==len(remaining):target=initial;i+=1
                elif flags[remaining[i+1]]&1:target=basis[remaining[i+1]];i+=2
                else:target=(control+basis[remaining[i+1]])/2;i+=1
                nodes.extend([(1-t)**2*current+2*t*(1-t)*control+t*t*target for t in np.linspace(0,1,17)[:-1]]);current=target
        nodes=np.array(nodes+[initial]);xy=nodes@p
        lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
        keep=np.r_[True,np.diff(lengths)>1e-10];nodes=nodes[keep];lengths=lengths[keep]
        if len(lengths)<2:raise ValueError('degenerate contour')
        distances=np.arange(count)*lengths[-1]/count
        slots=np.minimum(np.searchsorted(lengths,distances,side='right')-1,len(lengths)-2)
        t=(distances-lengths[slots])/(lengths[slots+1]-lengths[slots])
        result.append(nodes[slots]*(1-t[:,None])+nodes[slots+1]*t[:,None])
    return result


def curve_correspondence(points, ends, flags, em):
    p=np.asarray(points,float);contours=samples(p,ends,flags);xy=[c@p for c in contours]
    axis=(min(c[:,0].min() for c in xy)+max(c[:,0].max() for c in xy))/2
    matches=[]
    for a in xy:
        mirrored=a.copy();mirrored[:,0]=2*axis-a[:,0];choices=[]
        for j,b in enumerate(xy):
            scores=[float(np.max(np.linalg.norm(mirrored-np.roll(b[::-1],s,axis=0),axis=1))) for s in range(len(b))]
            s=int(np.argmin(scores));choices.append((scores[s],j,s))
        choices.sort()
        if choices[0][0]>em/512:return dict(status='not-matched',source_error_units=choices[0][0])
        if len(choices)>1 and choices[1][0]<=em/512:return dict(status='ambiguous')
        matches.append(choices[0])
    if any(matches[j][1]!=i for i,(_,j,_) in enumerate(matches)):
        return dict(status='ambiguous')
    pairs=[]
    for i,(_,j,shift) in enumerate(matches):
        other=np.roll(contours[j][::-1],shift,axis=0)
        pairs.extend((a,b) for a,b in zip(contours[i][::16],other[::16]))
    return dict(status='coordinated',pairs=pairs,source_residual_units=max(m[0] for m in matches),
                contour_pairs=[m[1] for m in matches])
