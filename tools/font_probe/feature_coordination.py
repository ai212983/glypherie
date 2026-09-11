"""Experimental complete-stem caps, related width classes and outline symmetry."""
import numpy as np


def shared_diagonal_widths(features, constraints):
    groups=[]
    for i,f in enumerate(features):
        if f['kind']!='slant' or min(abs(np.asarray(f['normal'])))<.1:continue
        for group in groups:
            if all(abs(f['width']/features[j]['width']-1)<=.05 and
                   abs(f['length']/features[j]['length']-1)<=.05 and
                   np.max(abs(abs(np.asarray(f['normal']))-abs(np.asarray(features[j]['normal']))))<=.01 for j in group):
                group.append(i);break
        else:groups.append([i])
    audit=[]
    for group in groups:
        if len(group)<2:continue
        width=float(np.mean([features[j]['width'] for j in group]))
        changes=[]
        for c in constraints:
            if c.get('feature') in {f'width-{j}' for j in group} and c['kind'] in ('Dist','PDist'):
                changes.append(dict(id=c['id'],before=c['value']));c['value']=float(np.sign(c['value'])*width)
        audit.append(dict(features=group,width=width,changes=changes))
    return audit


def reflected_outline(points, fitted, ends, flags, em):
    """Require a reversed cyclic contour correspondence, including point tags."""
    p=np.asarray(points,float);q=np.asarray(fitted,float).copy()
    source_axis=(p[:,0].min()+p[:,0].max())/2
    reflected=p.copy();reflected[:,0]=2*source_axis-p[:,0]
    pairs=[];start=0;residual=0.
    for end in ends:
        ids=np.arange(start,end+1);matches=[]
        for shift in range(len(ids)):
            partner=ids[(shift-np.arange(len(ids)))%len(ids)]
            if any(flags[a]!=flags[b] for a,b in zip(ids,partner)):continue
            error=float(np.max(np.linalg.norm(reflected[ids]-p[partner],axis=1)))
            if error<=em/512:matches.append((error,partner))
        if not matches:return q,dict(status='not-matched')
        matches.sort(key=lambda x:x[0]);error,partner=matches[0]
        if len(matches)>1:return q,dict(status='ambiguous')
        pairs.extend(zip(ids.tolist(),partner.tolist()));residual=max(residual,error);start=end+1
    axis=(q[:,0].min()+q[:,0].max())/2
    for a,b in pairs:
        q[a,0]=(fitted[a,0]+2*axis-fitted[b,0])/2
        q[a,1]=(fitted[a,1]+fitted[b,1])/2
    return q,dict(status='coordinated',source_residual_units=residual,axis_px=float(axis),
                  pairs=pairs,max_adjustment_px=float(np.max(abs(q-fitted))))


def diagnostics(fitted, supports, symmetry):
    p=np.asarray(fitted);rows=[]
    for support in supports:
        axis=support['axis'];outer=p[support['outer_points'],axis];inner=p[support['inner_points'],axis]
        rows.append(dict(stem=support['stem'],target_width=support['fitted_width'],
                         measured_width=float(abs(np.mean(inner)-np.mean(outer))),
                         side_spread=float(max(np.ptp(inner),np.ptp(outer))),
                         outer_height=[float(p[support['outer_points'],1-axis].min()),float(p[support['outer_points'],1-axis].max())]))
    residual=None
    if symmetry['status']=='coordinated':
        residual=max(float(np.linalg.norm(p[a]-[2*symmetry['axis_px']-p[b,0],p[b,1]])) for a,b in symmetry['pairs'])
    return dict(stems=rows,reflection_residual_px=residual)
