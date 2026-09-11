"""Experimental stem strips from paired straight outline edges, before union."""
import math

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from track_features import solid


def stem_regions(raw,boundary,size):
    minimum=size*0.18
    edges=[]
    for poly in raw:
        for a,b in zip(poly,poly[1:]+poly[:1]):
            length=math.dist(a,b)
            if length>=minimum:
                edges.append((a,b,((b[0]-a[0])/length,(b[1]-a[1])/length),length))
    strips=[]
    for i,(a,b,u,length) in enumerate(edges):
        n=(-u[1],u[0])
        for c,d,v,_ in edges[i+1:]:
            if u[0]*v[0]+u[1]*v[1]>-0.999:continue
            off=(c[0]-a[0])*n[0]+(c[1]-a[1])*n[1]
            if not 0.4<=abs(off)<=size*0.2:continue
            project=lambda p:(p[0]-a[0])*u[0]+(p[1]-a[1])*u[1]
            lo=max(0,min(project(c),project(d)));hi=min(length,max(project(c),project(d)))
            if hi-lo<minimum:continue
            point=lambda t,s:(a[0]+u[0]*t+n[0]*s,a[1]+u[1]*t+n[1]*s)
            strip=Polygon([point(lo,0),point(hi,0),point(hi,off),point(lo,off)])
            # Avoid interpreting a long counter as a stroke between parallel edges.
            if solid(boundary).intersection(strip).area>=0.95*strip.area:strips.append(strip)
    return unary_union(strips)


def protected_pixels(g,region):
    return [i for i,value in enumerate(g['pixels']) if value and region.intersection(
        box(g['left']+i%g['width'],g['top']+i//g['width'],
            g['left']+i%g['width']+1,g['top']+i//g['width']+1)).area>=0.5]
