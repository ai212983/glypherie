"""Joint placement extension: preserve source center vectors around an isolated bar.

Geometry only. Keeps fitted contour shapes, shared dimensions and ring grid phase.
Search is bounded to one pixel around source-relative ring positions. The bar
moves rigidly in 26.6 units. Objective weights are experimental, not paper rules.
"""
from itertools import product
import numpy as np
from repeated_rings import contours


def center(p):
    return (p.min(axis=0)+p.max(axis=0))/2


def place(source, fitted, tags, ends, em, ppem, pairs):
    source=np.asarray(source,float)*ppem/em; fitted=np.asarray(fitted,float)
    cs=contours(source,tags,ends); result=fitted.copy(); records=[]
    for pair in pairs:
        ring_ids=[np.concatenate([cs[c]['ids'] for c in ring]) for ring in pair['contours']]
        outer_ids=[cs[ring[0]]['ids'] for ring in pair['contours']]
        excluded={c for ring in pair['contours'] for c in ring}
        sc=np.array([center(source[ids]) for ids in outer_ids]); choices=[]
        for i,c in enumerate(cs):
            if i in excluded or not c['poly'].is_valid:continue
            p=source[c['ids']]; centroid=center(p)
            _,singular,vectors=np.linalg.svd(p-p.mean(0),full_matrices=False)
            if singular[-1]<=1e-9 or singular[0]/singular[-1]<3:continue
            axis=vectors[0];normal=np.array([-axis[1],axis[0]])
            if np.prod((sc-centroid)@normal)>=0:continue
            delta=sc[1]-sc[0]; along=float((centroid-sc[0])@delta/(delta@delta))
            if not 0<along<1:continue
            if any(c['poly'].intersects(d['poly']) for j,d in enumerate(cs) if j!=i):continue
            choices.append(i)
        if len(choices)!=1:
            records.append(dict(status='held',reason='requires one isolated elongated separator'));continue
        bar=choices[0]; ids=cs[bar]['ids']; bc=center(fitted[ids]); source_bc=center(source[ids]); desired=sc-source_bc
        old_centers=np.array([center(fitted[i]) for i in outer_ids]); size=np.array(pair['outer_px'])
        nearest=np.floor(bc+desired-size/2+.5)
        best=None
        for offsets in product((-1,0,1),repeat=4):
            origins=nearest+np.array(offsets).reshape(2,2); centers=origins+size/2
            proposed_bc=bc+np.rint((np.mean(centers-desired,axis=0)-bc)*64)/64
            relative=centers-proposed_bc-desired
            movement=np.sum((centers-old_centers)**2)+np.sum((proposed_bc-bc)**2)
            score=float(np.sum(relative**2)+.05*movement)
            key=(score,float(movement),tuple(origins.flat))
            if best is None or key<best[0]:best=(key,centers,proposed_bc,relative)
        _,new_centers,new_bc,error=best
        for group,old,new in zip(ring_ids,old_centers,new_centers):result[group]+=new-old
        result[ids]+=new_bc-bc
        records.append(dict(status='placed',separator_contour=bar,source_center_vectors=desired.tolist(),
            center_vectors_before=(old_centers-bc).tolist(),center_vectors_after=(new_centers-new_bc).tolist(),
            relative_error_before_px=float(np.linalg.norm(old_centers-bc-desired)),
            relative_error_after_px=float(np.linalg.norm(error)),
            ring_translations_px=(new_centers-old_centers).tolist(),separator_translation_px=(new_bc-bc).tolist()))
    return np.rint(result*64)/64,records
