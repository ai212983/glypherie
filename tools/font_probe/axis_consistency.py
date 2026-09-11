"""Experimental source-axis fitting with native raster validation; geometry only."""
import itertools
import numpy as np
from outline_relationships import samples


def mismatch(ink, axes):
    if not ink:return 0
    result=0
    for axis in axes:
        lo=min(v[axis] for v in ink);hi=max(v[axis] for v in ink)
        reflected={tuple(lo+hi-v[j] if j==axis else v[j] for j in (0,1)) for v in ink}
        result+=len(ink^reflected)
    return result


def candidates(points,ends,flags,current,scale):
    p=np.asarray(points,float)*scale;q=np.asarray(current,float);loops=[];start=0
    for end in ends:loops.append(np.arange(start,end+1));start=end+1
    # Orthogonal source contours: jointly grid source coordinate levels. This
    # keeps split collinear boundaries together instead of moving vertices alone.
    orthogonal=len(loops)==1 and all(flags[i]&1 for i in loops[0])
    if orthogonal:
        d=p-np.roll(p,1,axis=0);orthogonal=bool(np.all(np.min(abs(d),axis=1)<1e-8))
    if orthogonal:
        levels=[np.unique(p[:,ax]) for ax in (0,1)]
        # Bounded level lattice: supports simple orthogonal components, with no
        # character/contour-point-count lookup. Complex contours remain unchanged.
        if any(len(v)>4 for v in levels):return
        if any(np.max(abs(v+v[::-1]-(v[0]+v[-1])))>.5 for v in levels):return
        options=[]
        for ax,v in enumerate(levels):
            labels=np.argmin(abs(p[:,ax,None]-v),axis=1);centres=np.array([np.mean(q[labels==j,ax]) for j in range(len(v))])
            poss=[]
            for grid in itertools.product(*[range(int(np.floor(c))-1,int(np.ceil(c))+2) for c in centres]):
                grid=np.asarray(grid,float)
                if np.any(np.diff(grid)<=0) or np.ptp(grid+grid[::-1])>1e-9:continue
                if np.max(abs(grid-centres))>1.01:continue
                poss.append(grid[labels])
            options.append(poss)
        for x,y in itertools.product(*options):yield np.column_stack([x,y]),dict(kind='orthogonal-levels',axes=[0,1])
        return
    # Separate, vertically stacked, almost coaxial source components. Their
    # source curves are retained under positive affine maps; centres share a phase.
    boxes=[(p[ids].min(axis=0),p[ids].max(axis=0)) for ids in loops]
    if any(np.any(hi-lo<=1e-8) for lo,hi in boxes):return
    centres=[(lo[0]+hi[0])/2 for lo,hi in boxes]
    if np.ptp(centres)>.15:return
    by_y=sorted(boxes,key=lambda b:b[0][1])
    if any(a[1][1]>=b[0][1] for a,b in zip(by_y,by_y[1:])):return
    if len(loops)==1 and (boxes[0][1][1]-boxes[0][0][1])<2*(boxes[0][1][0]-boxes[0][0][0]):return
    if len(loops)>3:return
    for cloud,(lo,hi) in zip(samples(p,ends,flags),boxes):
        xy=cloud@p;mirrored=xy.copy();mirrored[:,0]=lo[0]+hi[0]-xy[:,0]
        if np.sqrt(np.min(np.sum((xy[:,None,:]-mirrored[None,:,:])**2,axis=2),axis=0)).max()>.15:return
    centre=np.mean([(q[ids,0].min()+q[ids,0].max())/2 for ids in loops])
    widths=[max(1.,float(np.ptp(q[ids,0]))) for ids in loops]
    choices=[sorted({max(1.,round(w)+d) for d in (-1,0,1)}) for w in widths]
    for axis,widths in itertools.product([round(centre*2)/2+d for d in (-.5,0,.5)],itertools.product(*choices)):
        after=q.copy()
        for ids,(lo,hi),width in zip(loops,boxes,widths):
            after[ids,0]=axis+(p[ids,0]-(lo[0]+hi[0])/2)*width/(hi[0]-lo[0])
            ymin,ymax=q[ids,1].min(),q[ids,1].max()
            height=ymax-ymin
            if .75<=(hi[1]-lo[1])/(hi[0]-lo[0])<=1.33:
                # Compact round components retain source aspect under scaling.
                height=width*(hi[1]-lo[1])/(hi[0]-lo[0])
                ymin=(ymin+ymax-height)/2
            after[ids,1]=ymin+(p[ids,1]-lo[1])*height/(hi[1]-lo[1])
        yield after,dict(kind='coaxial-components',axes=[0],axis_px=axis)


def fit(points,ends,flags,current,scale,raster,ownership=()):
    q=np.asarray(current,float);p=np.asarray(points,float)*scale;before=raster(q);best=None;count=0
    for after,audit in candidates(points,ends,flags,q,scale):
        count+=1
        old=mismatch(before,audit['axes'])
        if old==0:return q,dict(status='already-symmetric')
        if np.max(abs(after-p))>2:continue
        if any(abs(after[o['point'],o['axis']]-q[o['point'],o['axis']])>1/64 for o in ownership):continue
        ink=raster(after);error=mismatch(ink,audit['axes'])
        # Require exact symmetry in the delivered raster for every selected axis.
        if error:continue
        loss=float(.5*np.mean((after-q)**2)+.5*np.mean((after-p)**2));area=abs(len(ink)-len(before))/max(1,len(before))
        score=loss+area
        if best is None or score<best[0]:best=(score,after,dict(audit,score=score,before_mismatch=old,after_mismatch=error))
    if best:return best[1],dict(best[2],status='candidate',trials=count)
    return q,dict(status='held' if count else 'unaffected',trials=count)
