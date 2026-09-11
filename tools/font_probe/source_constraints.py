"""Source-counter correspondence and bounded outline phase selection.

This is a project heuristic, not a published perceptual-quality metric. It uses
source regions to distinguish intended counters from raster-created white gaps.
"""
from shapely.geometry import LineString,Polygon,box
from shapely.ops import polygonize,unary_union
from stem_gridfit import geometry,contains
from calibrate import topology


def polygons(shape):
    if shape.is_empty:return []
    return [shape] if shape.geom_type=='Polygon' else [p for p in shape.geoms if p.geom_type=='Polygon']


def source_shape(points,tags,ends,size):
    if any(t==2 for t in tags):return None
    _,segments=geometry(points,tags,ends,size)
    cells=polygonize(unary_union([LineString([a,b]) for a,b in segments if (a!=b).any()]))
    return unary_union([p for p in cells if contains(segments,p.representative_point().x,p.representative_point().y)])


def raster_shape(g):
    return unary_union([box(g['left']+i%g['width'],-g['top']-i//g['width']-1,
                           g['left']+i%g['width']+1,-g['top']-i//g['width'])
                        for i,v in enumerate(g['pixels']) if v])


def counters(shape):
    return [Polygon(r) for p in polygons(shape) for r in p.interiors]


def raster_counters(g):
    # Four-connected white regions, matching the binary topology convention.
    # Polygon interiors alone incorrectly let white escape through corner contact.
    w,h=g['width'],g['height']
    white={(x,y) for y in range(h) for x in range(w) if not g['pixels'][y*w+x]}
    result=[]
    while white:
        first=white.pop();region={first};pending=[first];outside=False
        while pending:
            x,y=pending.pop()
            if x in (0,w-1) or y in (0,h-1):outside=True
            for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if p in white:white.remove(p);region.add(p);pending.append(p)
        if not outside:
            result.append(unary_union([box(g['left']+x,-g['top']-y-1,g['left']+x+1,-g['top']-y) for x,y in region]))
    return result


def assess(source,g):
    raster=raster_shape(g);expected=counters(source);actual=raster_counters(g)
    # One-to-one region correspondence; a split source counter cannot count twice.
    # A half-pixel tolerance accommodates alignment without matching distant holes.
    options=[]
    for actual_hole in actual:
        matches=[]
        for j,hole in enumerate(expected):
            overlap=actual_hole.intersection(hole.buffer(.5)).area
            if overlap>=.25*actual_hole.area:matches.append(j)
        options.append(matches)
    assigned={}
    def augment(i,seen):
        for j in options[i]:
            if j in seen:continue
            seen.add(j)
            if j not in assigned or augment(assigned[j],seen):assigned[j]=i;return True
        return False
    matched=sum(augment(i,set()) for i in range(len(actual)))
    missing=len(expected)-matched;extra=len(actual)-matched
    component_error=abs(topology(g,1)[0]-len(polygons(source)))
    return dict(source_counters=len(expected),raster_counters=len(actual),matched_counters=matched,
                missing_counters=missing,extra_counters=extra,component_error=component_error,
                defect_count=missing+extra+component_error,
                outline_difference_area=float(source.symmetric_difference(raster).area))


def select(source,baseline,candidate,render_shift):
    if source is None:return baseline,dict(status='unsupported source curves; retained baseline')
    before=assess(source,baseline);current=assess(source,candidate)
    choices=[dict(kind='candidate',shift_26_6=0,glyph=candidate,assessment=current),
             dict(kind='baseline',shift_26_6=0,glyph=baseline,assessment=before)]
    # Leave structurally sound candidates untouched, including approved samples.
    if current['defect_count']:
        for dy in (-16,16,-32,32):
            glyph=render_shift(dy)
            choices.append(dict(kind='aligned candidate',shift_26_6=dy,glyph=glyph,assessment=assess(source,glyph)))
    best=min(choices,key=lambda c:(c['assessment']['defect_count'],
                                  c['kind']=='baseline',abs(c['shift_26_6']),c['assessment']['outline_difference_area']))
    # Equal structural quality is insufficient reason to replace a sound candidate.
    if current['defect_count']==0:best=choices[0]
    diagnostics=dict(status=best['kind'],selected_shift_26_6=best['shift_26_6'],
                     baseline=before,unshifted_candidate=current,selected=best['assessment'],
                     trials=[{k:v for k,v in c.items() if k!='glyph'} for c in choices])
    return best['glyph'],diagnostics
