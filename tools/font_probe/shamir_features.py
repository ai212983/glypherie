"""Typed basic features from Shamir/Rappoport 1996 sections 4.1--4.3.

Recognition only: serif automata, compound junctions, counters and ladders
remain explicit later stages. No point movement or hint instructions occur here.
"""
import numpy as np
from shamir_geometry import at,unit


def cross(a,b):return float(a[0]*b[1]-a[1]*b[0])


def quadratic_range(values):
    """Exact scalar image of a line or quadratic Bézier segment."""
    bounds=[values[0],values[-1]]
    if len(values)==3:
        den=values[0]-2*values[1]+values[2]
        if den:
            t=(values[0]-values[1])/den
            if 0<t<1:bounds.append((1-t)**2*values[0]+2*(1-t)*t*values[1]+t*t*values[2])
    return min(bounds),max(bounds)


def side_is_cardinal(model,side,axis):
    """1996 §3 definitions 2–3: coordinate extent, separately from angle matching.

    Use the curve's geometric box, not its wider control polygon. Multi-segment
    sides are measured over their full extent. Lines include the epsilon
    boundary (definition 2); curved sides use the strict bound in definition 3.
    """
    values=[];curved=False
    for sid in side['segments']:
        c=np.asarray(model['segments'][sid]['control'],float)[:,axis]
        values.extend(quadratic_range(c))
        curved|=len(c)==3
    if not values:return False
    span=max(values)-min(values);eps=model['tolerances']['distance']
    return span<eps if curved else span<=eps


class Interior:
    def __init__(self,model):
        self.controls=[np.asarray(s['control'],float) for s in model['segments']]
        self.baseline=model.get('baseline',False)

    def contains(self,p):
        # Solve exact line/quadratic intersections with a horizontal ray.
        # Half-open endpoint ownership counts each contour crossing once.
        winding=0;x,y=p
        for c in self.controls:
            if not min(c[0,1],c[-1,1])<=y<max(c[0,1],c[-1,1]):continue
            if len(c)==2:
                dy=c[1,1]-c[0,1]
                roots=[] if abs(dy)<1e-12 else [(y-c[0,1])/dy]
            else:
                a=c[0,1]-2*c[1,1]+c[2,1];b=2*(c[1,1]-c[0,1]);d=c[0,1]-y
                if abs(a)<1e-12:roots=[] if abs(b)<1e-12 else [-d/b]
                else:
                    discriminant=b*b-4*a*d
                    roots=[] if discriminant<0 else [(-b-np.sqrt(discriminant))/(2*a),(-b+np.sqrt(discriminant))/(2*a)]
            for t in set(roots):
                if not -1e-12<=t<=1+1e-12:continue
                if at(c,t)[0]>x:
                    winding+=1 if c[-1,1]>c[0,1] else -1
                    break
        return winding!=0

    def between(self,a,b):
        if self.baseline:return self.segment_inside(a,b)
        return all(self.contains(a+(b-a)*t) for t in (.1,.3,.5,.7,.9))

    def segment_inside(self,a,b):
        """Test every open interval cut by exact line/quadratic intersections.

        Tangencies may add a harmless cut. Endpoints may lie on the boundary;
        a positive-length boundary overlap is conservatively not an interior.
        """
        a=np.asarray(a,float);b=np.asarray(b,float);d=b-a;length2=float(d@d)
        if length2<=1e-18:return False
        cuts=[0.,1.]
        for c in self.controls:
            if len(c)==2:
                coefficients=[cross(d,c[1]-c[0]),cross(d,c[0]-a)]
            else:
                coefficients=[cross(d,c[0]-2*c[1]+c[2]),
                              cross(d,2*(c[1]-c[0])),cross(d,c[0]-a)]
            # Strip exact zeros; np.roots then covers lines and quadratics.
            while coefficients and coefficients[0]==0:coefficients.pop(0)
            if not coefficients:
                projected=[float((p-a)@d)/length2 for p in c]
                if min(1.,max(projected))-max(0.,min(projected))>1e-12:return False
                continue
            for root in np.roots(coefficients):
                if abs(float(np.imag(root)))>1e-10:continue
                t=float(np.real(root))
                if not -1e-12<=t<=1+1e-12:continue
                u=float((at(c,min(1.,max(0.,t)))-a)@d)/length2
                if 0<u<1:cuts.append(u)
        cuts=sorted(set(cuts))
        return all(self.contains(a+d*((x+y)/2)) for x,y in zip(cuts,cuts[1:]) if y-x>1e-12)

    def region_inside(self,vertices,filled=True):
        """Certify one fill state throughout an open convex polygon.

        Partition every boundary curve at its intersections with polygon edge
        lines. A boundary inside any partition means the polygon spans more than
        one fill region. Tangencies and coincident polygon edges are allowed.
        Near-straight curved sides are conservative: intrusion into their chord
        strip rejects that strip instead of assuming the unsampled area is ink.
        """
        vertices=np.asarray(vertices,float)
        edges=[(a,b-a) for a,b in zip(vertices,np.roll(vertices,-1,axis=0))]
        area=sum(cross(a,b) for a,b in zip(vertices,np.roll(vertices,-1,axis=0)))
        if abs(area)<=1e-12:return False
        sign=1 if area>0 else -1
        tolerance=1e-10*max(1.,max(float(d@d) for a,d in edges))
        def strictly_inside(p):return all(sign*cross(d,p-a)>tolerance for a,d in edges)
        # Restrict the API to convex polygons rather than silently interpreting
        # a concave or crossed footprint as a collection of halfplanes.
        if any(sign*cross(d,p-a)<-tolerance for a,d in edges for p in vertices):
            raise ValueError('interior region must be convex')
        for c in self.controls:
            cuts=[0.,1.]
            for a,d in edges:
                coefficients=([cross(d,c[1]-c[0]),cross(d,c[0]-a)] if len(c)==2 else
                              [cross(d,c[0]-2*c[1]+c[2]),cross(d,2*(c[1]-c[0])),cross(d,c[0]-a)])
                while coefficients and coefficients[0]==0:coefficients.pop(0)
                if len(coefficients)<2:continue
                for root in np.roots(coefficients):
                    if abs(float(np.imag(root)))<=1e-10 and 0<float(np.real(root))<1:
                        cuts.append(float(np.real(root)))
            cuts=sorted(set(cuts))
            if any(strictly_inside(at(c,(x+y)/2)) for x,y in zip(cuts,cuts[1:]) if y-x>1e-12):return False
        return self.contains(np.mean(vertices,axis=0))==filled


def recognize(model, *, curved_support=False):
    eps=model['tolerances']['distance'];angle=model['tolerances']['angle_radians']
    interior=Interior(model);sides=[];alignment=model.get('alignment_tolerance',.012*model['em'])
    def within_line(controls,origin,direction):
        projected=[cross(direction,c-origin) for c in controls]
        bounds=quadratic_range(projected) if model.get('baseline',False) else projected
        return max(map(abs,bounds))<=eps
    for loop in model['contours']:
        local=[]
        for sid in loop:
            s=model['segments'][sid];p=np.asarray(s['control']);d=unit(p[-1]-p[0])
            # Encoding subdivisions can be shorter than the feature tolerance.
            # Preserve them while assembling runs; discard only zero-length data.
            if np.linalg.norm(p[-1]-p[0])<=1e-9:continue
            # Baseline near-straight curves use their exact chord-normal range;
            # the experimental profile retains its control-polygon test.
            if not within_line(p,p[0],d):continue
            if local and local[-1]['end']==s['start'] and np.dot(local[-1]['direction'],d)>=np.cos(angle):
                last=local[-1];origin=np.asarray(last['a'])
                if within_line(p,origin,np.asarray(last['direction'])):
                    last.update(end=s['end'],b=p[-1].tolist());last['segments'].append(sid);continue
            local.append(dict(start=s['start'],end=s['end'],a=p[0].tolist(),b=p[-1].tolist(),
                              direction=d.tolist(),segments=[sid]))
        # Merge a straight run crossing the arbitrary start of a contour.
        if len(local)>1:
            first,last=local[0],local[-1];d=np.asarray(last['direction']);origin=np.asarray(last['a'])
            if last['end']==first['start'] and np.dot(d,first['direction'])>=np.cos(angle) and abs(cross(d,np.asarray(first['b'])-origin))<=eps:
                first.update(start=last['start'],a=last['a'],segments=last['segments']+first['segments']);local.pop()
        for side in local:
            side['id']=len(sides);side['direction']=unit(np.asarray(side['b'])-side['a']).tolist();sides.append(side)
    merged=[]
    for side in sides:
        d=np.asarray(side['direction']);a=np.asarray(side['a'])
        match=next((g for g in merged if np.dot(d,g['direction'])>=np.cos(angle) and
                    max(abs(cross(d,np.asarray(g[k])-a)) for k in ('a','b'))<=eps),None)
        if match is None:merged.append(dict(side));continue
        match['segments'].extend(side['segments'])
        ends=[(match['start'],np.asarray(match['a'])),(match['end'],np.asarray(match['b'])),
              (side['start'],np.asarray(side['a'])),(side['end'],np.asarray(side['b']))]
        low=min(ends,key=lambda item:item[1]@d);high=max(ends,key=lambda item:item[1]@d)
        match.update(start=low[0],a=low[1].tolist(),end=high[0],b=high[1].tolist())
    sides=merged
    for i,side in enumerate(sides):side['id']=i
    def supported(side,level,direction):
        return any(min(np.asarray(model['segments'][s]['control'][0])@direction,np.asarray(model['segments'][s]['control'][-1])@direction)-1e-9<=level<=max(np.asarray(model['segments'][s]['control'][0])@direction,np.asarray(model['segments'][s]['control'][-1])@direction)+1e-9 for s in side['segments'])
    def side_position(side,level,direction,chord):
        if not model.get('baseline',False) or any(len(model['segments'][s]['control'])!=2 for s in side['segments']):
            return chord
        # A tolerance-merged line run can bend slightly. Its enclosing chord
        # is not the boundary: intersect the actual piecewise lines instead.
        matches=[]
        for sid in side['segments']:
            a,b=np.asarray(model['segments'][sid]['control'],float);delta=b-a
            span=float(delta@direction)
            if not span:continue
            t=float((level-a@direction)/span)
            if -1e-12<=t<=1+1e-12:matches.append(a+min(1.,max(0.,t))*delta)
        if not matches or any(np.linalg.norm(p-matches[0])>1e-9 for p in matches[1:]):return None
        return matches[0]
    features=[]
    def add(kind,a,b,**extra):
        width=(abs(float((b-a)[extra['axis']])) if model.get('baseline',False) and 'axis' in extra
               else float(np.linalg.norm(b-a)))
        features.append(dict(id=len(features),kind=kind,a=a.tolist(),b=b.tolist(),
                             width=width,**extra))
    for i,a in enumerate(sides):
        p=np.asarray(a['a']);q=np.asarray(a['b']);d=unit(q-p);normal=np.array([-d[1],d[0]])
        for b in sides[i+1:]:
            r=np.asarray(b['a']);s=np.asarray(b['b'])
            if np.dot(d,b['direction'])>-np.cos(angle):continue
            lo=max(float(p@d),float(min(r@d,s@d)));hi=min(float(q@d),float(max(r@d,s@d)))
            if hi-lo<=eps:continue
            cuts=sorted({lo,hi}|{float(np.asarray(model['segments'][sid]['control'][k])@d)
                         for side in (a,b) for sid in side['segments'] for k in (0,-1)
                         if lo<float(np.asarray(model['segments'][sid]['control'][k])@d)<hi})
            spans=[]
            for x,y in zip(cuts,cuts[1:]):
                if not (supported(a,(x+y)/2,d) and supported(b,(x+y)/2,d)):continue
                # Consecutive occupied cells are one interval regardless of how
                # either boundary is subdivided. An unoccupied cell stays a gap.
                if spans and spans[-1][1]==x:spans[-1]=(spans[-1][0],y)
                else:spans.append((x,y))
            spans=[(x,y) for x,y in spans if y-x>eps]
            widths=[];links=[]
            def section(level):
                left=p+d*(level-p@d)
                right=r+(s-r)*((level-r@d)/((s-r)@d))
                return side_position(a,level,d,left),side_position(b,level,d,right)
            for level in [x+(y-x)*t for x,y in spans for t in (.2,.5,.8)]:
                left,right=section(level)
                if left is None or right is None:links=[];widths=[];break
                links.append((left,right));widths.append(abs((right-left)@normal))
            if not widths or min(widths)<=eps or not all(interior.between(x,y) for x,y in links):continue
            if model.get('baseline',False):
                # Preserve every boundary knot even when occupied support
                # cells were merged for feature length and interval reporting.
                cells=[(x,y) for x,y in zip(cuts,cuts[1:]) if any(lo<=x and y<=hi for lo,hi in spans)]
                regions=[[*section(x),*reversed(section(y))] for x,y in cells]
                if any(any(p is None for p in region) or not interior.region_inside(region) for region in regions):continue
            if model.get('baseline',False):
                kind=('stem' if all(side_is_cardinal(model,side,0) for side in (a,b)) else
                      'bar' if all(side_is_cardinal(model,side,1) for side in (a,b)) else 'slant')
            else:kind='stem' if abs(d[0])<=np.sin(angle) else 'bar' if abs(d[1])<=np.sin(angle) else 'slant'
            add(kind,*links[len(links)//2],sides=[a['id'],b['id']],
                width_range=[float(min(widths)),float(max(widths))],
                support_direction=d.tolist(),support_intervals=[list(span) for span in spans],
                length=float(sum(y-x for x,y in spans)))
    for axis in (0,1):
        other=1-axis
        extrema=[p for p in model['points'] if p['kind']!='corner' and str(axis) in p['extrema']]
        if curved_support:
            from curved_pair_support import pairs
            for a,b in pairs(model,axis,interior):
                add('bow' if axis==0 else 'arc',np.asarray(a['position']),np.asarray(b['position']),
                    points=[a['id'],b['id']],axis=axis)
        for i,a in enumerate(extrema):
            p=np.asarray(a['position'])
            for b in extrema[i+1:]:
                if curved_support:continue
                q=np.asarray(b['position'])
                if a['extrema'][str(axis)]!=b['extrema'][str(axis)] or abs(p[other]-q[other])>alignment:continue
                if np.dot(a['outgoing'],b['outgoing'])>-np.cos(angle):continue
                if np.linalg.norm(p-q)>eps and interior.between(p,q):
                    add('bow' if axis==0 else 'arc',p,q,points=[a['id'],b['id']],axis=axis)
            for side in sides:
                r=np.asarray(side['a']);s=np.asarray(side['b']);d=unit(s-r)
                cardinal=side_is_cardinal(model,side,axis) if model.get('baseline',False) else abs(d[axis])<=np.sin(angle)
                if not cardinal or min(r[other],s[other])>p[other] or max(r[other],s[other])<p[other]:continue
                if s[other]==r[other]:continue
                if not supported(side,p[other],np.eye(2)[other]):continue
                q=r+(s-r)*((p[other]-r[other])/(s[other]-r[other]))
                if (q[axis]-p[axis])*(1 if a['extrema'][str(axis)]=='min' else -1)>=-eps:continue
                if np.dot(a['outgoing'],d)>-np.cos(angle):continue
                if interior.between(p,q):add('curve_stem' if axis==0 else 'curve_bar',p,q,points=[a['id']],sides=[side['id']],axis=axis)
    return dict(sides=sides,features=features,
        limitations=['serif automata and compound junctions not implemented',
                     'counters and ladders not implemented',
                     'broken collinear runs preserve separate support intervals',
                     'analytic curve-ray intersections; cross-stroke samples and tolerances are project choices',
                     'candidate matches require internal conflict resolution'])
