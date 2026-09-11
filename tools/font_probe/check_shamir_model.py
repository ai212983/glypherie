"""Internal model conformance checks; no visual candidate selection."""
import argparse,json,math
from pathlib import Path
import fontTools,pathops
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont
from shamir_geometry import from_font,prepare
from shamir_templates import recognize_templates,calibration_templates
from compare_paper_prototypes import HERE,digest,render,pixels
from compare_shamir_pipeline import CHARS,SIZES
from shamir_model import build_font


def rounded(v):return math.copysign(math.floor(abs(v)+.5),v)


def residuals(face,char,size,graph,em):
    face.set_pixel_sizes(0,size);face.load_char(char,ft.FT_LOAD_NO_SCALE|ft.FT_LOAD_NO_HINTING|ft.FT_LOAD_NO_BITMAP)
    original=np.asarray(face.glyph.outline.points,float).reshape(-1,2)
    # FreeType 2.13.2 ttobjs.c scales CVT values using scale >> 6.
    def cvt_scaled(value):
        v=round(value)*64*(face.size.x_scale >> 6)/65536
        return math.copysign(math.floor(abs(v)+.5),v)/64
    face.load_char(char,ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_PEDANTIC|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_NO_BITMAP)
    actual=np.asarray(face.glyph.outline.points,float).reshape(-1,2)/64;errors=[]
    for c in graph['constraints']:
        p=c['point'];n=np.asarray(c['normal']);kind=c['kind'];sources=c['sources']
        if kind in ('Abs','PAbs'):value=cvt_scaled(c['value']);value=rounded(value) if c.get('round',True) else value
        elif kind in ('Dist','PDist'):
            a=sources[0];distance=round(round(float((original[p]-original[a])@n))*size/em*64)/64
            if kind=='PDist':distance=math.copysign(cvt_scaled(abs(c['value'])),distance)
            if c.get('round',True):distance=rounded(distance)
            value=float(actual[a]@n)+distance
        else:
            a,b=sources;den=float((original[b]-original[a])@n)
            t=round(c['value']*16384)/16384 if kind=='PRatio' else float((original[p]-original[a])@n)/den if abs(den)>1e-9 else 0
            value=float(((1-t)*actual[a]+t*actual[b])@n)
        error=abs(float(actual[p]@n)-value)
        if error>.065:errors.append(dict(point=p,kind=kind,error=error,constraint=c))
    return errors


def outline_diagnostics(face,char,size):
    """Independent geometric observations, not a proof of typographic quality."""
    face.set_pixel_sizes(0,size)
    face.load_char(char,ft.FT_LOAD_NO_HINTING|ft.FT_LOAD_NO_BITMAP)
    original=np.asarray(face.glyph.outline.points,float).reshape(-1,2)/64
    face.load_char(char,ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_PEDANTIC|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_NO_BITMAP)
    actual=np.asarray(face.glyph.outline.points,float).reshape(-1,2)/64
    if not len(original):return dict(max_movement_px=0,bounds_expansion_px=0)
    movements=np.linalg.norm(actual-original,axis=1)
    expansion=max(0,float(np.max(original.min(axis=0)-actual.min(axis=0))),float(np.max(actual.max(axis=0)-original.max(axis=0))))
    p=int(np.argmax(movements))
    return dict(max_movement_px=float(movements[p]),bounds_expansion_px=expansion,
                worst_point=p,original=original[p].tolist(),actual=actual[p].tolist())


def attachment_diagnostics(face,char,size,attachments):
    """Measure every proposed segment relationship, including rejected links."""
    face.set_pixel_sizes(0,size)
    face.load_char(char,ft.FT_LOAD_NO_HINTING|ft.FT_LOAD_NO_BITMAP)
    original=np.asarray(face.glyph.outline.points,float).reshape(-1,2)/64
    face.load_char(char,ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_PEDANTIC|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_NO_BITMAP)
    actual=np.asarray(face.glyph.outline.points,float).reshape(-1,2)/64
    observations=[]
    for item in attachments:
        c=item['constraint'];p=c['point'];a=c['sources'][0];n=np.asarray(c['normal'])
        change=float(((actual[p]-actual[a])-(original[p]-original[a]))@n)
        observations.append(dict(point=p,source=a,normal=c['normal'],feature=c['feature'],
                                 status=item['status'],reason=item['reason'],change_px=change))
    return observations


def template_invariance(source,char):
    m=from_font(TTFont(source),char);templates=calibration_templates()
    expected=sorted(t['name'] for t in recognize_templates(m,templates))
    loops=[[np.array(m['segments'][sid]['control']) for sid in loop] for loop in m['contours']]
    for mirror,reverse in [(-1,False),(1,True),(-1,True)]:
        contours=[[(s*np.array([mirror,1])).tolist() for s in (loop if not reverse else [s[::-1] for s in loop[::-1]])] for loop in loops]
        actual=sorted(t['name'] for t in recognize_templates(prepare(contours,m['em']),templates))
        if actual!=expected:return False
    return True


def construction_checks(face,char,size,record):
    """Check intended relationships independently of which equations survived."""
    face.set_pixel_sizes(0,size)
    face.load_char(char,ft.FT_LOAD_NO_SCALE|ft.FT_LOAD_NO_HINTING|ft.FT_LOAD_NO_BITMAP)
    original=np.asarray(face.glyph.outline.points,float).reshape(-1,2)
    face.load_char(char,ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_PEDANTIC|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_NO_BITMAP)
    actual=np.asarray(face.glyph.outline.points,float).reshape(-1,2)/64
    if char=='m':
        strokes=[f for f in record['features'] if f['kind']=='stem' and f.get('length',0)>=2*f['width']]
        strokes.sort(key=lambda f:min(original[p,0] for p in f['points']))
        sides=[sorted(zip(f['points'],f['groups']),key=lambda pair:original[pair[0],0]) for f in strokes]
        widths=[float(actual[b[0],0]-actual[a[0],0]) for a,b in sides]
        gaps=[float(actual[b[0][0],0]-actual[a[1][0],0]) for a,b in zip(sides,sides[1:])]
        counters=all(any(f['kind']=='counter-x' and set(f['groups'])=={a[1][1],b[0][1]} for f in record['features']) for a,b in zip(sides,sides[1:]))
        lengths=[f['length'] for f in strokes]
        passed=(len(widths)==3 and counters and min(widths+gaps)>0 and np.ptp(widths)<=.065 and np.ptp(gaps)<=.065)
        return dict(passed=bool(passed),stem_widths_px=widths,counter_widths_px=gaps,
                    supported_lengths_units=lengths,ladder_recognized=any(f['kind']=='ladder-x' for f in record['features']),
                    length_similarity_limit_units=max(.003*face.units_per_EM,.1*max(lengths,default=0)))
    remaining=pixels(render(face,char,size,hinted=True));components=0
    while remaining:
        components+=1;pending=[remaining.pop()]
        while pending:
            x,y=pending.pop()
            neighbors={(x+dx,y+dy) for dx in (-1,0,1) for dy in (-1,0,1)}&remaining
            remaining.difference_update(neighbors);pending.extend(neighbors)
    tapers=[]
    for hit in record['templates']['matches']:
        if hit['name']!='TaperedStroke':continue
        a,b,c,d=hit['native_points'];n=np.array(hit['frame'][0])
        wide=float((actual[b]-actual[a])@n);narrow=float((actual[d]-actual[c])@n)
        expected=float(((original[d]-original[c])@n)/((original[b]-original[a])@n))
        selected=record['graph']['constraints']
        ratios=all(any(r.get('feature')=='TaperedStroke' and r['kind']=='Ratio' and r['point']==p and r['sources']==[a,b] for r in selected) for p in (c,d))
        error=abs(narrow-wide*expected)
        wide_fitted=abs(wide-rounded(wide))<=.065
        tapers.append(dict(wide_px=wide,narrow_px=narrow,expected_ratio=expected,ratio_error_px=error,
                           ratios_selected=ratios,wide_cap_fitted=wide_fitted,passed=bool(wide>0 and narrow>0 and ratios and wide_fitted and error<=.065)))
    ordinary=[]
    for f in record['features']:
        if f['kind'] not in ('stem','curve_stem'):continue
        a,b=sorted(f['points'],key=lambda p:original[p]@np.asarray(f['normal']))
        width=float((actual[b]-actual[a])@np.asarray(f['normal']))
        ordinary.append(dict(width_px=width,passed=width>0))
    widths_pass=all(t['passed'] for t in tapers) if tapers else bool(ordinary) and all(f['passed'] for f in ordinary)
    return dict(passed=widths_pass and components==2,tapers=tapers,ordinary_strokes=ordinary,
                bitmap_components=components,expected_components=2)


def main():
    if ft.version()!=(2,13,2):raise ValueError('numeric oracle requires FreeType 2.13.2; review CVT scaling for this version')
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=HERE/'out/shamir-model')
    parser.add_argument("--scheduler",choices=("scalar","point"),default="scalar")
    args=parser.parse_args()
    source_hashes={name:digest(HERE/name) for name in ('shamir_model.py','shamir_constraints.py','shamir_point_schedule.py','shamir_templates.py','shamir_features.py','shamir_geometry.py','shamir_boundary.py','shamir_segment_fit.py','shamir_prototype.py','check_shamir_model.py')}
    out=args.output;out.mkdir(parents=True,exist_ok=True);records=[];builds=[]
    for name in ('roboto','literata','source-sans-3'):
        for size in SIZES:
            src=HERE/f'out/shamir-controlled/{name}-{size}-source.ttf';dst=out/f'{name}-{size}.ttf';before=digest(src)
            build=build_font(src,dst,CHARS,scheduler=args.scheduler);face=ft.Face(str(dst));errors=[];geometry=[]
            for char,r in build['records'].items():
                issues=residuals(face,char,size,r['graph'],face.units_per_EM)
                errors.extend(dict(char=char,**i) for i in issues)
                geometry.append(dict(char=char,**outline_diagnostics(face,char,size),
                                     attachments=attachment_diagnostics(face,char,size,r['attachment_resolution'])))
            assert before==digest(src)
            construction={c:construction_checks(face,c,size,build['records'][c]) for c in ('m','!')}
            coverage={
                'e_arc':any(f['kind']=='arc' for f in build['records']['e']['features']),
                'X_slant':any(f['kind']=='slant' for f in build['records']['X']['features']),
                'm_native_rhythm':construction['m']['passed'],
                'exclamation_stroke':construction['!']['passed'],
                'template_invariance':template_invariance(src,'!') and (name!='literata' or template_invariance(src,'h')),
                'configured_recipes':not any(r['templates']['unconfigured'] for r in build['records'].values()),
            }
            if name=='literata':coverage['bracketed_feet']=all(any(t['name']=='BracketedFoot' for t in build['records'][c]['templates']['matches']) for c in 'hmnp')
            summary=dict(font=name,size=size,cases=len(build['records']),violations=len(errors),worst=max((i['error'] for i in errors),default=0),coverage=coverage,
                         max_movement_px=max(g['max_movement_px'] for g in geometry),
                         max_bounds_expansion_px=max(g['bounds_expansion_px'] for g in geometry))
            print(json.dumps(summary),flush=True);records.append(dict(**summary,errors=errors,geometry=geometry,construction=construction));builds.append(dict(font=name,size=size,source_sha256=before,font_sha256=digest(dst),**build))
    assert source_hashes=={name:digest(HERE/name) for name in source_hashes},'source changed during conformance run'
    (out/'conformance.json').write_text(json.dumps(dict(scheduler=args.scheduler,records=records,builds=builds,source_hashes=source_hashes,freetype_version=ft.version(),fonttools_version=fontTools.__version__,pathops_version=pathops.__version__,residual_tolerance_px=.065),indent=2)+'\n')
    if any(r['violations'] or not all(r['coverage'].values()) for r in records):raise SystemExit('internal construction or native constraint check failed')

if __name__=='__main__':main()
