"""Experimental junction correspondence and survival measurement across stages."""
import ctypes
import hashlib
import json
import math
from pathlib import Path

import freetype as ft
from PIL import Image, ImageDraw
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from analyze_features import (ROOT, FlattenPen, detect, visible_boundary, resample, area)
from outline_experiment import render, diagnose

OUT=ROOT/'tools/font_probe/out/feature-tracking'


def snapshot(face, char, flags, grow=False):
    face.load_char(char,flags|ft.FT_LOAD_NO_BITMAP)
    outline=face.glyph.outline
    if grow:
        error=ft.FT_Outline_EmboldenXY(ctypes.byref(outline._FT_Outline),24,0)
        if error: raise ft.FT_Exception(error)
        ft.FT_Outline_Translate(ctypes.byref(outline._FT_Outline),-4,0)
    pen=FlattenPen(None,1/64)
    def move(p,ctx):
        if hasattr(pen,'current'): pen._closePath()
        pen._moveTo((p.x,p.y))
    outline.decompose(move_to=move,
                      line_to=lambda p,c:pen._lineTo((p.x,p.y)),
                      conic_to=lambda a,b,c:pen._qCurveToOne((a.x,a.y),(b.x,b.y)),
                      cubic_to=lambda a,b,d,c:pen._curveToOne((a.x,a.y),(b.x,b.y),(d.x,d.y)))
    pen._closePath()
    return dict(raw=pen.contours,boundary=visible_boundary(pen.contours),
                tags=[tag & 3 for tag in outline.tags],ends=list(outline.contours))


def project(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    if dx*dx+dy*dy==0: return 0,a
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return t,(a[0]+t*dx,a[1]+t*dy)


def predict(p,source,target):
    """Interpolate the corresponding flattened segment; topology must match."""
    if len(source)!=len(target) or any(len(a)!=len(b) for a,b in zip(source,target)):
        raise ValueError('outline segment correspondence changed')
    choices=[]
    for ci,poly in enumerate(source):
        for i,a in enumerate(poly):
            j=(i+1)%len(poly); t,q=project(p,a,poly[j])
            ta,tb=target[ci][i],target[ci][j]
            choices.append((math.dist(p,q),(ta[0]+t*(tb[0]-ta[0]),ta[1]+t*(tb[1]-ta[1]))))
    return min(choices,key=lambda c:c[0])


def match_features(source_features,source,target):
    if source['tags']!=target['tags'] or source['ends']!=target['ends']:
        raise ValueError('control topology changed')
    found=detect(target['boundary']); matches=[]
    for f in source_features:
        error,p= predict(f['point'],source['raw'],target['raw'])
        distances=sorted((math.dist(p,g['point']),i) for i,g in enumerate(found))
        accepted=bool(distances and distances[0][0]<=0.75 and
                      (len(distances)==1 or distances[1][0]-distances[0][0]>=0.15))
        index=distances[0][1] if accepted else None
        matches.append(dict(predicted=p,source_projection_error=error,
                            index=index,feature=found[index] if index is not None else None,
                            residual=distances[0][0] if distances else None))
    # Collisions are uncertain, never silently assign two identities to one junction.
    for match in matches:
        if match['index'] is not None and sum(m['index']==match['index'] for m in matches)>1:
            match['collision']=True
    for match in matches:
        if match.get('collision'): match['feature']=None
    return matches


def solid(contours):
    positives=[Polygon(c) for c in contours if area(c)>0]
    negatives=[Polygon(c) for c in contours if area(c)<0]
    return unary_union(positives).difference(unary_union(negatives))


def pocket(feature,boundary):
    """Exterior wedge between concavity and chord, at 0.8px contour reach."""
    poly=boundary[feature['contour']]; points,step=resample(poly)
    i=min(range(len(points)),key=lambda i:math.dist(points[i],feature['point']))
    n=round(0.8/step)
    tri=Polygon([points[(i-n)%len(points)],points[i],points[(i+n)%len(points)]])
    return tri.difference(solid(boundary))


def bitmap_shape(g):
    return unary_union([box(g['left']+x,g['top']+y,g['left']+x+1,g['top']+y+1)
                        for y in range(g['height']) for x in range(g['width'])
                        if g['pixels'][y*g['width']+x]])


def survival(region,bitmap):
    if region.area<1e-6: return None
    ratio=region.difference(bitmap).area/region.area
    return 0.0 if ratio<1e-9 else min(1.0,ratio)


def sheet(records):
    selected=[r for r in records if r['character'] in 'bhd']
    im=Image.new('RGB',(1000,700),'white');d=ImageDraw.Draw(im)
    titles=['Source','After hinting','After thickening','Final pixels']
    for col,title in enumerate(titles): d.text((20+col*250,12),title,fill='black')
    for row,r in enumerate(selected):
        by=210+row*225
        for col,stage in enumerate(('source','hinted','grown','bitmap')):
            ox=25+col*250;scale=12
            d.text((ox,by-170),r['character'],fill='black')
            if stage=='bitmap':
                g=r['bitmap']
                for y in range(g['height']):
                    for x in range(g['width']):
                        if g['pixels'][y*g['width']+x]:
                            xx=ox+(g['left']+x)*scale;yy=by+(g['top']+y)*scale
                            d.rectangle((xx,yy,xx+scale-1,yy+scale-1),fill='black')
            else:
                for poly in sorted(r[stage]['boundary'],key=lambda p:-abs(area(p))):
                    d.polygon([(ox+x*scale,by+y*scale) for x,y in poly],fill='black' if area(poly)>0 else 'white')
            for i,f in enumerate(r['tracking']):
                item=f['source'] if stage=='source' else f['hinted' if stage=='hinted' else 'grown']['feature']
                if item:
                    x,y=item['point'];x=ox+x*scale;y=by+y*scale
                    d.ellipse((x-6,y-6,x+6,y+6),outline='#e65b00',width=2)
                    d.text((x+8,y-10),str(i+1),fill='#b53600')
    im.save(OUT/'stages.png')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    path=ROOT/'tools/font_probe/out/feature-analysis/results.json'
    prior=json.loads(path.read_text())
    font=ROOT/'tools/font_probe/fonts/Roboto.ttf'
    if hashlib.sha256(font.read_bytes()).hexdigest()!=prior['font_sha256']:raise ValueError('font changed')
    face=ft.Face(str(font));face.set_var_design_coords([400,100]);face.set_pixel_sizes(0,16)
    records=[]; lines=['# Junction tracking','',
        'Roboto 16px; void retention is a local geometric diagnostic, not a readability score.','',
        '| Glyph/id | Hint shift px | Hint void area px² | Grown void area px² | Baseline void retained | Thickened void retained | Final void retained |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    for previous in prior['glyphs']:
        char=previous['character']
        source=snapshot(face,char,ft.FT_LOAD_NO_HINTING)
        hinted=snapshot(face,char,ft.FT_LOAD_TARGET_MONO)
        grown=snapshot(face,char,ft.FT_LOAD_TARGET_MONO,True)
        raw_bitmap=render(face,char,24,8)
        features=previous['features']
        # Carry the reviewed source IDs, projecting to corresponding FT source segments.
        hm=match_features(features,source,hinted)
        gm=match_features(features,source,grown)
        base_pixels=bitmap_shape(previous['baseline']); pixels=bitmap_shape(previous['candidate'])
        raw_pixels=bitmap_shape(raw_bitmap)
        tracking=[]
        for i,(f,h,g) in enumerate(zip(features,hm,gm)):
            item=dict(source=f,hinted=h,grown=g)
            if h['feature'] and g['feature']:
                hp=pocket(h['feature'],hinted['boundary']);gp=pocket(g['feature'],grown['boundary'])
                item.update(hint_shift_px=math.dist(f['point'],h['feature']['point']),
                            hinted_void_area=hp.area,grown_void_area=gp.area,
                            baseline_void_retention=survival(hp,base_pixels),
                            thickened_void_retention=survival(gp,raw_pixels),
                            final_void_retention=survival(gp,pixels))
                fmt=lambda v:'unmeasurable' if v is None else f'{v:.1%}'
                lines.append(f"| {char}/{i+1} | {item['hint_shift_px']:.2f} | {hp.area:.3f} | {gp.area:.3f} | {fmt(item['baseline_void_retention'])} | {fmt(item['thickened_void_retention'])} | {fmt(item['final_void_retention'])} |")
            else:lines.append(f'| {char}/{i+1} | uncertain correspondence | — | — | — | — | — |')
            tracking.append(item)
        records.append(dict(character=char,source=source,hinted=hinted,grown=grown,
                            bitmap=previous['candidate'],raw_bitmap=raw_bitmap,tracking=tracking))
    summaries={}
    for name,glyphs,key in [('baseline',[p['baseline'] for p in prior['glyphs']],'baseline_void_retention'),
                            ('thickened',[r['raw_bitmap'] for r in records],'thickened_void_retention'),
                            ('constrained',[r['bitmap'] for r in records],'final_void_retention')]:
        metrics=diagnose(glyphs)
        metrics['fully_filled_pockets']=sum(f.get(key)==0 for r in records for f in r['tracking'])
        summaries[name]=metrics
    lines+=['','## Candidate diagnostics','',
            '| Candidate | Stroke-band penalty | Fully filled pockets | Expected topology |',
            '| --- | --- | --- | --- |']
    for name,m in summaries.items():
        lines.append(f"| {name} | {m['two_pixel_band_penalty']} | {m['fully_filled_pockets']} | {m['topology_ok']} |")
    lines+=['','Pocket survival measures only a small exterior wedge at each matched junction. '
            'It does not establish contour quality, minimum readable opening, or an acceptance threshold. '
            'Source-to-hinted correspondence is interpolated and bounded, not a control-point proof.']
    result=dict(input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),font_sha256=prior['font_sha256'],
                freetype_version=ft.version(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependency_hashes={name:hashlib.sha256((ROOT/'tools/font_probe'/name).read_bytes()).hexdigest()
                                   for name in ('analyze_features.py','outline_experiment.py','calibrate.py')},
                candidate_diagnostics=summaries,
                parameters=dict(size_px=16,axes={'wght':400,'wdth':100},growth_26_6=24,translation_26_6=-4,
                                match_radius_px=0.75,ambiguity_margin_px=0.15,pocket_reach_px=0.8),
                limits='Flattened segment interpolation plus bounded junction matching; no semantic loss threshold; 4-connected ink not required; void retention allows partial survival',glyphs=records)
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'report.md').write_text('\n'.join(lines)+'\n')
    sheet(records)
    print('\n'.join(lines))


if __name__=='__main__':main()
