"""Prepared quadratic geometry for Shamir 2003's 1996 extraction prerequisite.

Virtual points preserve the curves exactly. IDs refer to prepared geometry,
not TrueType point indices; source_segment and t_range preserve provenance.
"""
import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.misc.bezierTools import splitQuadraticAtT


def unit(v):
    length=float(np.linalg.norm(v))
    return v/length if length else np.zeros(2)


def at(control,t):
    p=np.asarray(control,dtype=float)
    if len(p)==2:return (1-t)*p[0]+t*p[1]
    return (1-t)**2*p[0]+2*t*(1-t)*p[1]+t*t*p[2]


class OutlinePen(BasePen):
    def __init__(self,glyphset):
        super().__init__(glyphset)
        self.skipMissingComponents=False
        self.contours=[];self.current=[];self.position=None;self.start=None

    def _moveTo(self,p):
        self.current=[];self.position=p;self.start=p

    def _lineTo(self,p):
        if p!=self.position:self.current.append([self.position,p])
        self.position=p

    def _qCurveToOne(self,c,p):
        self.current.append([self.position,c,p]);self.position=p

    def _curveToOne(self,*args):
        raise ValueError('prepared Shamir geometry currently supports quadratic outlines')

    def _closePath(self):
        self._lineTo(self.start)
        if self.current:self.contours.append(self.current)
        self.current=[]

    def _endPath(self):
        raise ValueError('open font contour')


def merge_collinear_lines(contour):
    """Remove redundant static-outline joins without straightening the outline."""
    contour=[list(segment) for segment in contour]
    changed=True
    while changed and len(contour)>1:
        changed=False
        for i,a in enumerate(contour):
            j=(i+1)%len(contour);b=contour[j]
            if len(a)!=2 or len(b)!=2 or not np.array_equal(a[-1],b[0]):continue
            u=np.asarray(a[-1],float)-a[0];v=np.asarray(b[-1],float)-b[0]
            # No recognition epsilon here: a shallow real corner is geometry.
            if float(u[0]*v[1]-u[1]*v[0])!=0 or float(u@v)<=0:continue
            if j==0:
                contour[0]=[a[0],b[-1]];contour.pop()
            else:
                contour[i]=[a[0],b[-1]];contour.pop(j)
            changed=True;break
    return contour


def prepare(contours,em,epsilon=.003,angle_tolerance=.04,baseline=False):
    """Split exact extrema and classify joins. Tolerances are project choices."""
    segments=[];points=[];loops=[];source_id=0
    for contour_id,contour in enumerate(contours):
        if baseline:contour=merge_collinear_lines(contour)
        loop=[]
        for controls in contour:
            p=np.asarray(controls,dtype=float);roots=[]
            if len(p)==3:
                denominator=p[0]-2*p[1]+p[2]
                for axis in (0,1):
                    if abs(denominator[axis])>1e-12:
                        t=(p[0,axis]-p[1,axis])/denominator[axis]
                        if 1e-9<t<1-1e-9:roots.append(float(t))
            roots=sorted(set(round(t,12) for t in roots));cuts=[0.]+roots+[1.]
            pieces=splitQuadraticAtT(*p,*roots) if roots else [p]
            for k,piece in enumerate(pieces):
                sid=len(segments);pid=len(points);control=np.asarray(piece,dtype=float)
                points.append(dict(id=pid,position=control[0].tolist(),contour=contour_id,
                                   source_segment=source_id,t=cuts[k],inserted=cuts[k]!=0))
                segments.append(dict(id=sid,start=pid,control=control.tolist(),contour=contour_id,
                                     source_segment=source_id,t_range=[cuts[k],cuts[k+1]],
                                     kind='line' if len(control)==2 else 'quadratic'))
                loop.append(sid)
            source_id+=1
        if not loop:continue
        loops.append(loop)
        for k,sid in enumerate(loop):
            s=segments[sid];s['end']=segments[loop[(k+1)%len(loop)]]['start']
            previous=segments[loop[k-1]];a=np.asarray(previous['control']);b=np.asarray(s['control'])
            incoming=unit(a[-1]-a[-2]);outgoing=unit(b[1]-b[0])
            if not np.any(incoming):incoming=unit(a[-1]-a[0])
            if not np.any(outgoing):outgoing=unit(b[-1]-b[0])
            smooth=float(np.dot(incoming,outgoing))>=np.cos(angle_tolerance)
            curved=(len(a)==3,len(b)==3)
            kind='corner' if not smooth else ('tangent' if curved[0]!=curved[1] else 'curve' if curved[0] else 'line')
            p=points[s['start']];p.update(kind=kind,incoming=incoming.tolist(),outgoing=outgoing.tolist())
            # Samples determine extremum type at corners and zero derivatives.
            center=np.asarray(p['position']);before=at(a,.99);after=at(b,.01);extrema={}
            for axis in (0,1):
                u,v=before[axis]-center[axis],after[axis]-center[axis]
                if min(u,v)>=-1e-9 and max(u,v)>1e-9:extrema[str(axis)]='min'
                elif max(u,v)<=1e-9 and min(u,v)<-1e-9:extrema[str(axis)]='max'
            p['extrema']=extrema
            categories=[{'corner':'C','tangent':'T','curve':'CT','line':'line'}[kind]]
            for axis,label in (('0','V'),('1','H')):
                if axis in extrema:categories.append(('C' if kind=='corner' else '')+label)
            if kind=='corner':
                vertical=any(float(np.ptp(c[:,0]))<=epsilon*em and float(np.ptp(c[:,1]))>epsilon*em for c in (a,b))
                horizontal=any(float(np.ptp(c[:,1]))<=epsilon*em and float(np.ptp(c[:,0]))>epsilon*em for c in (a,b))
                if vertical:categories.append('VR')
                if horizontal:categories.append('HR')
                if vertical and horizontal:categories.append('LR')
                if len(extrema)==2:categories.append('S')
            if smooth and len(a)==len(b)==3:
                def turn(c):
                    u,v=c[1]-c[0],c[2]-c[1]
                    return float(u[0]*v[1]-u[1]*v[0])
                if turn(a)*turn(b)<0:categories.append('I')
            p['categories']=categories
    return dict(em=em,baseline=baseline,tolerances=dict(distance=epsilon*em,angle_radians=angle_tolerance),
                points=points,segments=segments,contours=loops,
                provenance='exact quadratic subdivision; component transforms resolved by fontTools BasePen')


def from_font(font,char,**kwargs):
    if 'glyf' not in font:raise ValueError('TrueType quadratic font required')
    cmap=font.getBestCmap()
    if ord(char) not in cmap:raise ValueError(f'missing glyph U+{ord(char):04X}')
    glyphset=font.getGlyphSet();pen=OutlinePen(glyphset);glyphset[cmap[ord(char)]].draw(pen)
    model=prepare(pen.contours,font['head'].unitsPerEm,**kwargs)
    model.update(glyph=cmap[ord(char)],composite=font['glyf'][cmap[ord(char)]].isComposite())
    return model
