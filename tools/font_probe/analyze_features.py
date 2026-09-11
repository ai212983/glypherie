"""Analysis-only source concavity detector; no letter-specific feature locations.

Flatten source curves, measure inward contour turns at a declared spatial scale,
and report local bitmap differences. These are candidate junctions, not semantic
stem/bowl classifications or automatic quality verdicts.
"""
import bisect
import hashlib
import json
import math
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
import shapely
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union
from shapely.geometry.polygon import orient

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'tools/font_probe/out/feature-analysis'


class FlattenPen(BasePen):
    def __init__(self, glyphset, scale):
        super().__init__(glyphset)
        self.scale = scale
        self.contours = []

    def point(self, p):
        return (p[0]*self.scale, -p[1]*self.scale)

    def _moveTo(self, p):
        self.current = [self.point(p)]

    def _lineTo(self, p):
        self.current.append(self.point(p))

    def _qCurveToOne(self, p1, p2):
        a = self.current[-1]; b = self.point(p1); c = self.point(p2)
        for i in range(1, 65):
            t = i/64; s = 1-t
            self.current.append(tuple(s*s*a[k]+2*s*t*b[k]+t*t*c[k] for k in (0,1)))

    def _curveToOne(self, p1, p2, p3):
        a = self.current[-1]; b,c,d = map(self.point, (p1,p2,p3))
        for i in range(1,65):
            t=i/64; s=1-t
            self.current.append(tuple(s**3*a[k]+3*s*s*t*b[k]+3*s*t*t*c[k]+t**3*d[k] for k in (0,1)))

    def _closePath(self):
        self.contours.append(self.current)


def area(poly):
    return sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1]))/2


def resample(poly, step=0.04):
    closed = poly+poly[:1]
    distances = [0.0]
    for a,b in zip(closed,closed[1:]):
        distances.append(distances[-1]+math.dist(a,b))
    n = max(3, math.ceil(distances[-1]/step))
    result = []
    for i in range(n):
        s = i*distances[-1]/n
        j = min(bisect.bisect_right(distances,s)-1,len(poly)-1)
        t = (s-distances[j])/(distances[j+1]-distances[j])
        result.append(tuple(closed[j][k]*(1-t)+closed[j+1][k]*t for k in (0,1)))
    return result, distances[-1]/n


def detect(contours, reach=0.4, min_angle=45):
    # Font contour winding establishes which side is filled, including holes.
    outer = max(contours, key=lambda c: abs(area(c)))
    sign = 1 if area(outer)>0 else -1
    candidates = []
    for ci, poly in enumerate(contours):
        points, step = resample(poly)
        offset = max(1,round(reach/step))
        for i,p in enumerate(points):
            a,b = points[(i-offset)%len(points)],points[(i+offset)%len(points)]
            u=(p[0]-a[0],p[1]-a[1]); v=(b[0]-p[0],b[1]-p[1])
            angle=math.degrees(math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1]))
            if angle*sign < -min_angle:
                candidates.append(dict(point=p, angle_degrees=abs(angle), contour=ci))
    selected=[]
    for c in sorted(candidates,key=lambda c:-c['angle_degrees']):
        if all(math.dist(c['point'],s['point'])>0.7 for s in selected):
            selected.append(c)
    return sorted(selected,key=lambda c:(c['point'][1],c['point'][0]))


def filled(point, contours):
    # Nonzero winding, matching font fill semantics.
    x,y=point; winding=0
    for poly in contours:
        for a,b in zip(poly,poly[1:]+poly[:1]):
            cross=(b[0]-a[0])*(y-a[1])-(x-a[0])*(b[1]-a[1])
            if a[1]<=y<b[1] and cross>0: winding+=1
            elif b[1]<=y<a[1] and cross<0: winding-=1
    return winding!=0


def bitmap_ink(g,x,y):
    col,row=math.floor(x)-g['left'],math.floor(y)-g['top']
    return (0<=col<g['width'] and 0<=row<g['height'] and
            bool(g['pixels'][row*g['width']+col]))


def visible_boundary(contours):
    linework=unary_union([LineString(poly+poly[:1]) for poly in contours])
    cells=list(polygonize(linework))
    solid=unary_union([cell for cell in cells
                       if filled(tuple(cell.representative_point().coords)[0],contours)])
    polygons=[solid] if solid.geom_type=='Polygon' else list(solid.geoms)
    result=[]
    for polygon in polygons:
        polygon=orient(polygon,sign=1)
        result.append(list(polygon.exterior.coords)[:-1])
        result.extend(list(ring.coords)[:-1] for ring in polygon.interiors)
    return result


def measure(feature, contours, g):
    # Local 1.2px square, sampled on a 20x20 grid. Compare origins, not crops.
    x,y=feature['point']; extra=missing=0
    n=20
    for j in range(n):
        for i in range(n):
            p=(x-0.6+(i+0.5)*1.2/n,y-0.6+(j+0.5)*1.2/n)
            source=filled(p,contours); target=bitmap_ink(g,*p)
            extra+=target and not source
            missing+=source and not target
    return dict(extra_ink_area_px2=extra*1.44/n**2,missing_ink_area_px2=missing*1.44/n**2)


def draw_sheet(records, path):
    scale=13; cell=220; row_h=215
    image=Image.new('RGB',(3*cell+50,len(records)*row_h+55),'white')
    draw=ImageDraw.Draw(image)
    for col,label in enumerate(('Source outlines','Baseline bitmap','Current candidate')):
        draw.text((35+col*cell,12),label,fill='black')
    for row,r in enumerate(records):
        y=50+row*row_h
        draw.text((6,y+65),r['character'],fill='black')
        for col in range(3):
            ox=45+col*cell; oy=y+165
            if col==0:
                contours=r['contours']; sign=1 if area(max(contours,key=lambda c:abs(area(c))))>0 else -1
                for poly in sorted(contours,key=lambda c:-abs(area(c))):
                    draw.polygon([(ox+x*scale,oy+yy*scale) for x,yy in poly],
                                 fill='black' if area(poly)*sign>0 else 'white')
            else:
                g=r['baseline' if col==1 else 'candidate']
                for gy in range(g['height']):
                    for gx in range(g['width']):
                        if g['pixels'][gy*g['width']+gx]:
                            x=ox+(g['left']+gx)*scale; yy=oy+(g['top']+gy)*scale
                            draw.rectangle((x,yy,x+scale-1,yy+scale-1),fill='black')
            for i,f in enumerate(r['features']):
                x,yy=f['point']; x=ox+x*scale; yy=oy+yy*scale
                draw.rectangle((x-9,yy-9,x+9,yy+9),outline='#d34a00',width=2)
                draw.text((x+10,yy-12),str(i+1),fill='#b53600')
    image.save(path)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    input_path=ROOT/'tools/font_probe/out/join-experiment/results.json'
    prior=json.loads(input_path.read_text())
    fontpath=ROOT/'tools/font_probe/fonts/Roboto.ttf'
    digest=hashlib.sha256(fontpath.read_bytes()).hexdigest()
    if digest!=prior['font_sha256']: raise ValueError('source identity mismatch')
    font=TTFont(fontpath); gs=font.getGlyphSet(location=prior['axes']); cmap=font.getBestCmap()
    records=[]
    for baseline,candidate in zip(prior['baseline'],prior['candidates'][0]['glyphs']):
        pen=FlattenPen(gs,16/font['head'].unitsPerEm)
        gs[cmap[baseline['codepoint']]].draw(pen)
        boundary=visible_boundary(pen.contours)
        features=detect(boundary)
        for f in features:
            f['baseline']=measure(f,boundary,baseline)
            f['candidate']=measure(f,boundary,candidate)
        records.append(dict(character=chr(baseline['codepoint']),contours=boundary,
                            features=features,baseline=baseline,candidate=candidate))
    result=dict(font_sha256=digest,shapely_version=shapely.__version__,input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                parameters=dict(size_px=16,axes=prior['axes'],curve_samples=64,arc_step_px=0.04,
                                turn_reach_px=0.4,min_concave_angle_degrees=45,suppression_radius_px=0.7),
                limits='Source inward-turn candidates only; finite-scale approximation; local area differences include grid fitting and are not loss verdicts; not a stem/bowl classifier',
                glyphs=records)
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    draw_sheet(records,OUT/'comparison.png')
    draw_sheet([r for r in records if r['character'] in 'bhd'],OUT/'focus.png')
    print({r['character']:len(r['features']) for r in records})


if __name__=='__main__': main()
