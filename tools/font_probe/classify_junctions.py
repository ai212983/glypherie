"""Experimental curved-entry versus straight-intersection classification.

Measure each contour arm away from the inward corner. Straight/straight corners
stay solid; a turning arm makes a detail eligible for the existing repair search.
This is a geometric proxy, not a semantic classification of a typeface's design.
"""
import math

from analyze_features import resample


def angle(a,b,c):
    u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
    if math.hypot(*u)<1e-8 or math.hypot(*v)<1e-8:return None
    return abs(math.degrees(math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1])))


def classify(feature,boundary,size_px):
    points,step=resample(boundary[feature['contour']])
    i=min(range(len(points)),key=lambda j:math.dist(points[j],feature['point']))
    distances=[size_px*v for v in (0.02,0.055,0.09)]
    turns=[]
    for direction in (-1,1):
        a,b,c=[points[(i+direction*round(d/step))%len(points)] for d in distances]
        turns.append(angle(a,b,c))
    eligible=all(t is not None for t in turns) and max(turns)>=5
    return dict(eligible=eligible,arm_turn_degrees=turns,
                category='curved entry candidate' if eligible else 'straight intersection or uncertain',
                parameters=dict(probe_distances_em=[0.02,0.055,0.09],minimum_arm_turn_degrees=5))
