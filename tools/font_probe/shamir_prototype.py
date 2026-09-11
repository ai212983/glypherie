"""Bounded Shamir 2003 experiment using native TrueType instructions.

Sections 3.3--3.6 motivate feature extraction, font-wide width clusters and
priority-ordered constraint graphs; section 4 motivates CVT/MIAP/MIRP/IUP.
This is NOT a reproduction of the full recognizer: axis-aligned straight and
explicit quadratic tangent sides only. The extraction thresholds, clustering
and deterministic tie resolution are experiment choices. Serif templates,
slants, counters, ladders, implicit extrema and optical overshoot parameters
are unsupported. Height zones use OS/2 metadata, not recurring-height extraction.
"""
from array import array
from pathlib import Path
import hashlib
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.instancer import instantiateVariableFont
from stem_gridfit import geometry, contains
from paper_gridfit import bitmap

PAPER = 'https://doi.org/10.1145/636886.636887'

LIMITATIONS = ['axis-aligned straight and explicit quadratic tangent sides only',
               'no serif templates, slant constraints, implicit extrema or overshoot model',
               'project feature thresholds, width clusters and deterministic tie handling',
               'IUP contour interpolation instead of explicit Ratio constraint graph',
               'no counter-width or ladder constraints',
               'height zones use baseline and OS/2 x-height/cap-height, not recurring-height extraction',
               'width statistics cover only the requested repertoire',
               'round-to-grid and 100px CVT cut-in are fixed experiment settings']


def features(points, tags, ends, em, opposed_sides=False):
    """Recognize explicit straight/tangent sides and opposed ink-width pairs."""
    _, segments = geometry(points, tags, ends, em)
    output=[]
    for axis in (0, 1):
        other=1-axis; sides=[]; start=0
        for end in ends:
            ids=list(range(start,end+1));start=end+1
            for k,i in enumerate(ids):
                prev,nxt=ids[k-1],ids[(k+1)%len(ids)]
                if not tags[i]:continue
                equal=[j for j in (prev,nxt) if abs(points[j,axis]-points[i,axis])<1e-6]
                for j in equal:
                    extent=abs(points[j,other]-points[i,other])
                    if extent < .025*em:continue
                    kind='straight' if tags[j] else 'curve'
                    # Curved support extent is deliberately conservative: the
                    # tangent control point bounds the local support interval.
                    lo,hi=sorted((float(points[i,other]),float(points[j,other])))
                    direction=float(np.sign(points[j,other]-points[i,other])) * (1 if j==nxt else -1)
                    item=dict(point=i,coordinate=float(points[i,axis]),lo=lo,hi=hi,kind=kind,direction=direction)
                    if item not in sides:sides.append(item)
        pairs=[]
        for i,a in enumerate(sides):
            for b in sides[i+1:]:
                if opposed_sides and a['direction']*b['direction']>=0:continue
                width=abs(a['coordinate']-b['coordinate'])
                lo=max(a['lo'],b['lo']);hi=min(a['hi'],b['hi'])
                if not .015*em<=width<=.18*em or hi-lo<.015*em:continue
                good=True
                for u in (.2,.5,.8):
                    for v in (.2,.5,.8):
                        p=[0.,0.];p[axis]=a['coordinate']+(b['coordinate']-a['coordinate'])*u;p[other]=lo+(hi-lo)*v
                        if not contains(segments,*p):good=False
                if not good:continue
                left,right=(a,b) if a['coordinate']<b['coordinate'] else (b,a)
                pairs.append(dict(axis=axis,start=left['point'],end=right['point'],width=width,
                                  kind='curve' if 'curve' in (a['kind'],b['kind']) else 'straight'))
        # One geometric relation per representative point pair.
        unique={}
        for p in sorted(pairs,key=lambda p:(p['width'],p['start'],p['end'])):
            unique.setdefault((p['start'],p['end']),p)
        output.extend(unique.values())
    return output


def select_constraints(constraints):
    """Select one incoming relation per point, reject cycles, topologically sort."""
    chosen={};rejected=[]
    for c in sorted(constraints,key=lambda c:(-c['priority'],c['point'],c.get('source',-1),c['kind'])):
        p=c['point']
        if p in chosen:
            rejected.append(dict(constraint=c,reason='lower priority or deterministic tie'));continue
        current=c.get('source');seen={p}
        while current is not None and current not in seen:
            seen.add(current);current=chosen.get(current,{}).get('source')
        if current is not None:
            rejected.append(dict(constraint=c,reason='dependency cycle'));continue
        chosen[p]=c
    ordered=[];pending=dict(chosen)
    while pending:
        ready=[p for p,c in pending.items() if c.get('source') not in pending]
        if not ready:raise RuntimeError('constraint cycle survived selection')
        for p in sorted(ready):ordered.append(pending.pop(p))
    return ordered,rejected


def width_clusters(all_features, em):
    tables={}
    for axis in (0,1):
        for kind in ('straight','curve'):
            groups=[]
            for width in sorted(p['width'] for p in all_features if p['axis']==axis and p['kind']==kind):
                if groups and width-sum(groups[-1])/len(groups[-1])<=.015*em:groups[-1].append(width)
                else:groups.append([width])
            tables[(axis,kind)]=[round(sum(g)/len(g)) for g in groups]
    return tables


def push(*values):
    return ['PUSHW[ ]',*[str(int(v)) for v in values]]


def build_font(source_path, output_path, size, axes, chars, *, opposed_sides=False):
    source_path=Path(source_path);font=TTFont(source_path,recalcTimestamp=False)
    if 'glyf' not in font:raise ValueError('Shamir subset requires TrueType quadratic outlines')
    if 'fvar' in font:
        allowed={a.axisTag:a.defaultValue for a in font['fvar'].axes}
        unknown=set(axes)-set(allowed)
        if unknown:raise ValueError(f'unsupported axes: {sorted(unknown)}')
        allowed.update(axes);font=instantiateVariableFont(font,allowed,inplace=True)
    elif axes:raise ValueError('axes supplied for a static font')
    for tag in ('fpgm','prep','cvt ','hdmx','LTSH','VDMX','gasp'):
        if tag in font:del font[tag]
    glyf=font['glyf'];em=font['head'].unitsPerEm;cmap=font.getBestCmap()
    for g in glyf.glyphs.values():g.expand(glyf);g.program=Program();g.program.fromAssembly([])
    records={};all_features=[]
    for char in dict.fromkeys(chars):
        if ord(char) not in cmap:raise ValueError(f'missing glyph U+{ord(char):04X}')
        name=cmap[ord(char)];g=glyf[name]
        if g.isComposite():
            records[char]=dict(status='unsupported composite-level constraints; component hints may execute',
                               components=[component.glyphName for component in g.components],
                               features=[],feature_counts={'straight':0,'curve':0});continue
        coords,ends,flags=g.getCoordinates(glyf);points=np.array(coords,dtype=float).reshape(-1,2)
        tags=[int(v)&1 for v in flags]
        detected=features(points,tags,ends,em,opposed_sides=opposed_sides) if len(points) else []
        metric_points=[];start=0
        for end in ends:
            ids=list(range(start,end+1));start=end+1
            for k,i in enumerate(ids):
                prev,nxt=ids[k-1],ids[(k+1)%len(ids)]
                y=points[i,1]
                if tags[i] and (points[prev,1]-y)*(points[nxt,1]-y)>=0:
                    metric_points.append(i)
        records[char]=dict(status='native hint subset',features=detected,points=points,metric_points=metric_points,
                           feature_counts={kind:sum(p['kind']==kind for p in detected) for kind in ('straight','curve')})
        all_features.extend(detected)
    tables=width_clusters(all_features,em);cvt=[]
    def cvt_id(value):
        value=round(value)
        if value not in cvt:cvt.append(value)
        return cvt.index(value)
    os2=font['OS/2'];metrics=sorted({0,getattr(os2,'sxHeight',0),getattr(os2,'sCapHeight',0)})
    for char,r in records.items():
        points=r.pop('points',None)
        if points is None or not len(points):continue
        assembly=['RTG[ ]']+push(6400)+['SCVTCI[ ]'] # Widths follow shared CVT, no native cutoff override.
        r['axes']=[]
        for axis in (0,1):
            constraints=[]
            for p in r['features']:
                if p['axis']!=axis:continue
                width=min(tables[(axis,p['kind'])],key=lambda w:abs(w-p['width']))
                constraints.extend([dict(kind='Abs',point=p['start'],priority=10),
                                    dict(kind='PDist',point=p['end'],source=p['start'],value=width,priority=30)])
            # Global height zones take priority over local width/position hints.
            if axis==1:
                for p in r['metric_points']:
                    coord=points[p,axis]
                    nearby=[m for m in metrics if abs(coord-m)<=.01*em]
                    if nearby:constraints.append(dict(kind='PAbs',point=p,value=min(nearby,key=lambda m:abs(coord-m)),priority=40))
            ordered,rejected=select_constraints(constraints)
            assembly.append(f'SVTCA[{1-axis}]')
            touched=set()
            for c in ordered:
                p=c['point']
                if c['kind']=='Abs':assembly+=push(p)+['MDAP[1]']
                elif c['kind']=='PAbs':assembly+=push(p,cvt_id(c['value']))+['MIAP[1]']
                else:
                    source=c['source']
                    if source not in touched:assembly+=push(source)+['MDAP[1]'];touched.add(source)
                    assembly+=push(source)+['SRP0[ ]']+push(p,cvt_id(c['value']))+['MIRP[01100]']
                touched.add(p)
            assembly.append(f'IUP[{1-axis}]')
            r['axes'].append(dict(axis=axis,constraints=ordered,rejected=rejected))
        program=Program();program.fromAssembly(assembly);glyf[cmap[ord(char)]].program=program
        r['instruction_bytes']=len(program.getBytecode())
        if not r['features']:r['status']='height anchors only; no recognized width features'
    font['cvt ']=newTable('cvt ');font['cvt '].values=array('h',cvt)
    maxp=font['maxp'];maxp.maxZones=2;maxp.maxTwilightPoints=0;maxp.maxStorage=0
    maxp.maxFunctionDefs=0;maxp.maxInstructionDefs=0;maxp.maxStackElements=8
    maxp.maxSizeOfInstructions=max((len(g.program.getBytecode()) for g in glyf.glyphs.values()),default=0)
    output_path=Path(output_path);output_path.parent.mkdir(parents=True,exist_ok=True);font.save(output_path)
    return dict(method='Shamir 2003 native TrueType subset',paper=PAPER,limitations=LIMITATIONS,
                source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),size=size,
                opposed_sides=opposed_sides,
                axes=axes,cvt=cvt,height_zones=dict(source='baseline plus OS/2 sxHeight and sCapHeight',values=metrics),
                width_statistics_repertoire=''.join(dict.fromkeys(chars)),records=records)


def render(font_path,char,size):
    face=ft.Face(str(font_path));face.set_pixel_sizes(0,size)
    face.load_char(char,ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_PEDANTIC)
    return bitmap(face,char),dict(interpreter='FreeType native TrueType',pedantic=True)
