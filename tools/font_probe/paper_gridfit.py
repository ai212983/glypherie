"""Research outline fitter: Hersch 1993 sections 5–6, with explicit scope limits.

Native hints supply CVT/alignment behavior. Added constraints fit straight diagonal
border pairs and source-confirmed reflection axes before scan conversion. Pair
detection and least-squares projection are our implementation choices, not a
reproduction of the paper's manually specified hint/model system.
"""
import math

import freetype as ft
import numpy as np
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union


def load(face,char,size):
    face.load_char(char,ft.FT_LOAD_NO_SCALE|ft.FT_LOAD_NO_HINTING|ft.FT_LOAD_NO_BITMAP)
    o=face.glyph.outline
    source=np.array(o.points,dtype=float).reshape(-1,2)*size/face.units_per_EM
    tags=[t&3 for t in o.tags];ends=list(o.contours)
    face.load_char(char,ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_NO_BITMAP)
    o=face.glyph.outline
    if tags!=[t&3 for t in o.tags] or ends!=list(o.contours):
        raise ValueError('native hinting changed outline topology')
    return source,np.array(o.points,dtype=float).reshape(-1,2)/64,tags,ends


def pairs(points,tags,ends,size):
    # Straight contours only; avoid treating a curve's control polygon as ink.
    if any(t!=1 for t in tags):return []
    edges=[];polys=[];start=0
    for end in ends:
        polys.append(Polygon(points[start:end+1]))
        edges.extend((i,start if i==end else i+1) for i in range(start,end+1))
        start=end+1
    # This subset uses simple solid contours; enclosed contours are ambiguous here.
    if any(not p.is_valid for p in polys):return []
    if any(a.contains(b) for i,a in enumerate(polys) for j,b in enumerate(polys) if i!=j):return []
    shape=unary_union(polys);found=[]
    def xat(edge,y):
        a,b=points[list(edge)];return a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1])
    for i,e in enumerate(edges):
        a,b=points[list(e)];dy=b[1]-a[1]
        if abs(dy)<size*.15:continue
        slope=(b[0]-a[0])/dy
        if not .2<=abs(slope)<=3:continue
        for f in edges[i+1:]:
            c,d=points[list(f)];otherdy=d[1]-c[1]
            if dy*otherdy>=0 or abs(otherdy)<size*.15:continue
            other=(d[0]-c[0])/otherdy
            if abs(slope-other)>.15:continue
            lo=max(min(a[1],b[1]),min(c[1],d[1]));hi=min(max(a[1],b[1]),max(c[1],d[1]))
            if hi-lo<size*.15:continue
            y=(lo+hi)/2;xe,xf=xat(e,y),xat(f,y);width=abs(xe-xf)
            if not .4<=width<=size*.3:continue
            if not all(shape.covers(Point(xe+(xf-xe)*t,y)) for t in (.2,.5,.8)):continue
            left,right=(e,f) if xe<xf else (f,e)
            found.append(dict(left=left,right=right,width=width))
    selected=[];used=set()
    for p in sorted(found,key=lambda p:p['width']):
        if p['left'] in used or p['right'] in used:continue
        selected.append(p);used.update((p['left'],p['right']))
    return selected


def width_table(widths):
    groups=[]
    for w in sorted(widths):
        if groups and abs(w-sum(groups[-1])/len(groups[-1]))<=.125:groups[-1].append(w)
        else:groups.append([w])
    return [dict(source=sum(g)/len(g),target=max(1,math.floor(sum(g)/len(g)+.5)),count=len(g)) for g in groups]


def fit(source,hinted,tags,ends,size,table):
    n=len(source);rows=[];targets=[];diagonals=pairs(source,tags,ends,size)
    for pair in diagonals:
        target=min(table,key=lambda e:abs(e['source']-pair['width']))['target']
        left,right=pair['left'],pair['right']
        lo=max(min(hinted[i,1] for i in left),min(hinted[i,1] for i in right))
        hi=min(max(hinted[i,1] for i in left),max(hinted[i,1] for i in right))
        if hi-lo<1e-6:continue
        for y in (lo,hi):
            row=np.zeros(n)
            for edge,sign in ((left,-1),(right,1)):
                a,b=edge;t=(y-hinted[a,1])/(hinted[b,1]-hinted[a,1])
                row[a]+=sign*(1-t);row[b]+=sign*t
            rows.append(row);targets.append(target)
        pair['target']=target
    symmetry=[]
    if n:
        cx=(source[:,0].min()+source[:,0].max())/2
        for i,p in enumerate(source):
            distances=np.linalg.norm(source-np.array([2*cx-p[0],p[1]]),axis=1)
            j=int(distances.argmin())
            if distances[j]>1e-5 or tags[i]!=tags[j]:symmetry=[];break
            symmetry.append(j)
    phase=None
    if symmetry:
        phase=round((hinted[:,0].min()+hinted[:,0].max()))/2
        for i,j in enumerate(symmetry):
            if i>j:continue
            row=np.zeros(n);row[i]+=1;row[j]+=1
            rows.append(row);targets.append(2*phase)
    output=hinted.copy();status='native hints only';residual=0.0
    if rows:
        a=np.array(rows);b=np.array(targets);x=hinted[:,0]
        delta=np.linalg.lstsq(a,b-a@x,rcond=None)[0]
        residual=float(np.max(np.abs(a@(x+delta)-b)))
        if residual>1e-5:status='conflicting constraints; native fallback'
        elif np.max(np.abs(delta))>1:status='displacement exceeds 1px; native fallback'
        else:
            output[:,0]=x+delta;status='outline constrained'
    output=np.round(output*64).astype(int)
    # Quantize paired points together so rounding preserves the accepted axis.
    if symmetry and status=='outline constrained':
        for i,j in enumerate(symmetry):
            if i<=j:output[j,0]=round(2*phase*64)-output[i,0]
    quantized_residual=float(np.max(np.abs(a@(output[:,0]/64)-b))) if rows else 0.0
    return output,dict(quantized_constraint_residual_px=quantized_residual,status=status,diagonal_pairs=diagonals,symmetry_axis=phase,
                       constraint_residual_px=residual,max_displacement_px=float(np.max(np.abs(output/64-hinted))) if n else 0)


def generate(face,char,size,table,stem_table=None,bowls=False,source_aware=False,curves=False):
    source,hinted,tags,ends=load(face,char,size)
    stem_info=None
    if stem_table is not None:
        from stem_gridfit import fit_stems
        original_hinted=hinted
        hinted,stem_info=fit_stems(source,hinted,tags,ends,size,stem_table,bowls)
        if bowls and 'fallback' in stem_info['status']:
            rejected=stem_info
            hinted,stem_info=fit_stems(source,original_hinted,tags,ends,size,stem_table)
            stem_info['bowl_rejection']=rejected
    points,diagnostics=fit(source,hinted,tags,ends,size,table)
    if stem_info is not None:diagnostics["vertical_stems"]=stem_info
    if curves:
        from curve_gridfit import fit_curves
        fitted,diagnostics['curve_constraints']=fit_curves(source,points/64,tags,ends,size,stem_table or [])
        points=np.round(fitted*64).astype(int)
    outline=face.glyph.outline._FT_Outline
    for i,(x,y) in enumerate(points):outline.points[i].x=int(x);outline.points[i].y=int(y)
    glyph=bitmap(face,char)
    if source_aware:
        from source_constraints import source_shape,select
        baseline,_=generate(face,char,size,table,stem_table)
        def render_shift(dy):
            load(face,char,size)
            outline=face.glyph.outline._FT_Outline
            for i,(x,y) in enumerate(points):
                outline.points[i].x=int(x);outline.points[i].y=int(y)+dy
            return bitmap(face,char)
        glyph,diagnostics['source_constraints']=select(source_shape(source,tags,ends,size),baseline,glyph,render_shift)
    elif bowls:
        from calibrate import topology
        baseline,_=generate(face,char,size,table,stem_table)
        before=list(topology(baseline,1));after=list(topology(glyph,1))
        if before!=after:
            diagnostics['bowl_topology_rejection']=dict(before=before,after=after,candidate_glyph=glyph)
            glyph=baseline
    return glyph,diagnostics


def bitmap(face,char):
    face.glyph.render(ft.FT_RENDER_MODE_MONO)
    s=face.glyph;b=s.bitmap;buf=b.buffer
    if b.pitch<0 or b.pixel_mode!=ft.FT_PIXEL_MODE_MONO:raise ValueError('unexpected bitmap format')
    glyph=dict(codepoint=ord(char),left=s.bitmap_left,top=-s.bitmap_top,width=b.width,height=b.rows,
               advance_26_6=s.advance.x,pixels=[(buf[y*b.pitch+x//8]>>(7-x%8))&1 for y in range(b.rows) for x in range(b.width)])
    return glyph
