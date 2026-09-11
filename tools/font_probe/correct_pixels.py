"""Bounded source-junction-guided pixel removal experiment, outside production."""
import hashlib
import itertools
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import box

from analyze_features import ROOT
from calibrate import components, topology
from track_features import pocket, bitmap_shape, survival, solid

OUT=ROOT/'tools/font_probe/out/pixel-correction'
TARGET=0.25


def mask(g):
    return [g['pixels'][y*g['width']:(y+1)*g['width']] for y in range(g['height'])]


def stable_runs(g):
    """Protect horizontal ink runs repeated in at least three consecutive rows."""
    rows=[]
    for row in mask(g):
        spans=[];x=0
        while x<len(row):
            if not row[x]:x+=1;continue
            start=x
            while x<len(row) and row[x]:x+=1
            spans.append((start,x))
        rows.append(spans)
    protected=set()
    for y in range(len(rows)-2):
        for start,end in set(rows[y]) & set(rows[y+1]) & set(rows[y+2]):
            for yy in range(y,y+3):
                protected.update(yy*g['width']+x for x in range(start,end))
    return protected


def remove(g, indices):
    result=dict(g,pixels=list(g['pixels']))
    for i in indices:result['pixels'][i]=0
    return result


def valid(before,after,indices,protected):
    if set(indices)&protected:return 'stable stroke'
    if topology(before,1)!=topology(after,1):return 'ink/counter topology'
    if len(components(mask(after)))>len(components(mask(before))):return 'new diagonal-only join'
    return None


def correct(record):
    original=record['raw_bitmap'];current=original
    protected=stable_runs(original)|set(record.get('protected_pixels',[]))
    features=[f['grown']['feature'] for f in record['tracking']]
    regions=[pocket(f,record['grown']['boundary']) if f else None for f in features]
    outline=solid(record['grown']['boundary'])
    events=[]
    for feature_id,region in enumerate(regions):
        event=dict(feature_id=feature_id+1,removed=[],rejections={})
        events.append(event)
        if region is None or region.area<1e-6:
            event['status']='uncertain feature';continue
        shape=bitmap_shape(current)
        old=[survival(r,shape) if r is not None else None for r in regions]
        event['before']=old[feature_id]
        if old[feature_id]>=TARGET:
            event.update(status='already meets trial target',after=old[feature_id]);continue
        candidates=[]
        for i,value in enumerate(current['pixels']):
            if not value:continue
            x=current['left']+i%current['width'];y=current['top']+i//current['width']
            if region.intersection(box(x,y,x+1,y+1)).area>1e-6:candidates.append(i)
        options=[]
        for count in (1,2):
            for indices in itertools.combinations(candidates,count):
                changed=remove(current,indices)
                reason=valid(current,changed,indices,protected)
                if reason:
                    event['rejections'][reason]=event['rejections'].get(reason,0)+1;continue
                values=[survival(r,bitmap_shape(changed)) if r is not None else None for r in regions]
                if any(a is not None and b+1e-9<a for a,b in zip(old,values)):
                    raise AssertionError('removal reduced white area')
                if values[feature_id]<TARGET:continue
                cost=sum(outline.intersection(box(current['left']+i%current['width'],
                          current['top']+i//current['width'],current['left']+i%current['width']+1,
                          current['top']+i//current['width']+1)).area for i in indices)
                options.append((count,cost,-values[feature_id],indices,changed,values))
            if options:break
        if options:
            _,cost,_,indices,current,values=min(options,key=lambda o:o[:4])
            event.update(status='candidate',removed=[(original['left']+i%original['width'],
                         original['top']+i//original['width']) for i in indices],
                         source_ink_removed_area=cost,after=values[feature_id])
        else:event.update(status='no passing correction',after=old[feature_id])
    final_shape=bitmap_shape(current)
    return dict(character=record['character'],before=original,after=current,events=events,
                topology_before=topology(original,1),topology_after=topology(current,1),
                final_retention=[survival(r,final_shape) if r is not None else None for r in regions])


def sheet(records):
    scale=7;cell=120;height=180
    image=Image.new('RGB',(865,3*height+45),'white');d=ImageDraw.Draw(image)
    for row,title in enumerate(('A: shared thickening, before corrections',
                                'B: source-guided pixel corrections',
                                'C: removed pixels highlighted in orange')):
        y=35+row*height;d.text((12,y-20),title,fill='black')
        for col,r in enumerate(records):
            g=r['before'] if row==0 else r['after'];ox=12+col*cell;oy=y+130
            d.text((ox,y),r['character'],fill='black')
            for j,value in enumerate(g['pixels']):
                x=g['left']+j%g['width'];yy=g['top']+j//g['width']
                if value:
                    xx=ox+(x+2)*scale;py=oy+yy*scale
                    d.rectangle((xx,py,xx+scale-1,py+scale-1),fill='black')
                    d.point((650+col*25+x,y-10+yy+12),fill='black')
            if row==2:
                for e in r['events']:
                    for x,yy in e['removed']:
                        xx=ox+(x+2)*scale;py=oy+yy*scale
                        d.rectangle((xx,py,xx+scale-1,py+scale-1),fill='#ed8a36')
    image.save(OUT/'comparison.png')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    path=ROOT/'tools/font_probe/out/feature-tracking/results.json'
    prior=json.loads(path.read_text())
    records=[correct(r) for r in prior['glyphs']]
    result=dict(input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependency_hashes={n:hashlib.sha256((ROOT/'tools/font_probe'/n).read_bytes()).hexdigest()
                                   for n in ('track_features.py','analyze_features.py','calibrate.py')},
                parameters=dict(trial_void_retention_target=TARGET,max_removals_per_feature=2,
                                protected_run_consecutive_rows=3,feature_order='source y then x'),
                limits='Greedy bounded search; bitmap run protection is a proxy for stroke consistency; no readability guarantee or validated acceptance threshold; manual review required',glyphs=records)
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    sheet(records)
    for r in records: print(r['character'],[(e['feature_id'],e['status'],e['removed']) for e in r['events']])


if __name__=='__main__':main()
