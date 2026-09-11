"""Compare local thinning with one-pixel relocation at unresolved source joins."""
import hashlib
import itertools
import json
from pathlib import Path

from PIL import Image, ImageDraw
from shapely.geometry import box

from analyze_features import ROOT
from calibrate import components, topology
from correct_pixels import TARGET, mask, remove
from track_features import pocket, bitmap_shape, solid, survival

OUT=ROOT/'tools/font_probe/out/join-repairs'


def xy(g,i):return g['left']+i%g['width'],g['top']+i//g['width']


def connectivity_reason(before,after,mode):
    if topology(after,1)!=topology(before,1):return 'ink/counter topology'
    if mode=='move' and len(components(mask(after)))>len(components(mask(before))):
        return 'new diagonal-only connection'
    return None


def repair(record,start,mode):
    if mode not in ('thin','move'):raise ValueError('unknown repair mode')
    current=start;events=[]
    regions=[pocket(f['grown']['feature'],record['grown']['boundary'])
             if f['grown']['feature'] else None for f in record['tracking']]
    outline=solid(record['grown']['boundary'])
    for fi,region in enumerate(regions):
        if region is None:continue
        old=[survival(r,bitmap_shape(current)) if r is not None else None for r in regions]
        if old[fi] is None or old[fi]>=TARGET:continue
        removals=[i for i,v in enumerate(current['pixels']) if v and
                  region.intersection(box(*xy(current,i),xy(current,i)[0]+1,xy(current,i)[1]+1)).area>1e-6]
        proposals=[];reasons={}
        for count in ((1,2) if mode=='thin' else (1,)):
            for cut in itertools.combinations(removals,count):
                if set(cut)&set(record.get('protected_pixels',[])):
                    reasons['source stem']=reasons.get('source stem',0)+1;continue
                additions=[None]
                if mode=='move':
                    x,y=xy(current,cut[0])
                    additions=[i for i,v in enumerate(current['pixels']) if not v and
                               max(abs(xy(current,i)[0]-x),abs(xy(current,i)[1]-y))<=2]
                for add in additions:
                    changed=remove(current,cut)
                    if add is not None:changed['pixels'][add]=1
                    reason=connectivity_reason(current,changed,mode)
                    if reason:
                        reasons[reason]=reasons.get(reason,0)+1;continue
                    shape=bitmap_shape(changed)
                    values=[survival(r,shape) if r is not None else None for r in regions]
                    if values[fi]<TARGET:continue
                    if any(a is not None and b+1e-9<a for a,b in zip(old,values)):
                        reasons['other junction worsens']=reasons.get('other junction worsens',0)+1;continue
                    cost=shape.symmetric_difference(outline).area
                    proposals.append((count+int(add is not None),cost,-values[fi],cut,
                                      -1 if add is None else add,changed,values))
            if proposals:break
        if proposals:
            _,cost,_,cut,add,current,values=min(proposals,key=lambda p:p[:5])
            events.append(dict(feature_id=fi+1,status='candidate',removed=[xy(start,i) for i in cut],
                               added=[] if add<0 else [xy(start,add)],before=old[fi],after=values[fi],
                               outline_difference_area=cost,rejections=reasons))
        else:events.append(dict(feature_id=fi+1,status='unresolved',removed=[],added=[],rejections=reasons))
    return dict(after=current,events=events,topology=topology(current,1),
                four_connected_components=len(components(mask(current))),
                ink_pixels=sum(current['pixels']),
                retention=[survival(r,bitmap_shape(current)) if r is not None else None for r in regions])


def sheet(records):
    image=Image.new('RGB',(864,790),'white');d=ImageDraw.Draw(image)
    for row,(title,key,highlight) in enumerate([
            ('A: previous guarded corrections','before',False),
            ('B: allow local thinning / diagonal connection','thin',False),
            ('C: relocate one pixel / retain edge connectivity','move',False),
            ('C changes: orange removed, blue added','move',True)]):
        y=25+row*190;d.text((12,y),title,fill='black')
        for col,r in enumerate(records):
            g=r['before'] if key=='before' else r[key]['after']
            ox=12+120*col;oy=y+150;s=7
            d.text((ox,y+20),r['character'],fill='black')
            for i,v in enumerate(g['pixels']):
                if v:
                    x,yy=xy(g,i);xx=ox+(x+2)*s;py=oy+yy*s
                    d.rectangle((xx,py,xx+s-1,py+s-1),fill='black')
                    d.point((650+25*col+x,y+12+yy),fill='black')
            if highlight:
                for e in r[key]['events']:
                    for what,color in [('removed','#ed8a36'),('added','#158acc')]:
                        for x,yy in e[what]:
                            xx=ox+(x+2)*s;py=oy+yy*s
                            d.rectangle((xx,py,xx+s-1,py+s-1),fill=color)
    image.save(OUT/'comparison.png')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    tracking_path=ROOT/'tools/font_probe/out/feature-tracking/results.json'
    correction_path=ROOT/'tools/font_probe/out/pixel-correction/results.json'
    track=json.loads(tracking_path.read_text());previous=json.loads(correction_path.read_text())
    if previous['input_sha256']!=hashlib.sha256(tracking_path.read_bytes()).hexdigest():
        raise ValueError('corrections belong to another tracking run')
    records=[]
    for r,p in zip(track['glyphs'],previous['glyphs']):
        if r['character']!=p['character']:raise ValueError('glyph order mismatch')
        records.append(dict(character=r['character'],before=p['after'],
                            thin=repair(r,p['after'],'thin'),move=repair(r,p['after'],'move')))
    result=dict(input_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (tracking_path,correction_path)},
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                dependency_hashes={n:hashlib.sha256((ROOT/'tools/font_probe'/n).read_bytes()).hexdigest()
                                   for n in ('analyze_features.py','calibrate.py','correct_pixels.py','track_features.py')},
                parameters=dict(trial_target=TARGET,thin_max_removals=2,move_removals=1,move_additions=1,
                                addition_chebyshev_radius=2),
                limits='Both arms permit local stroke thinning; thin arm permits diagonal-only joins. '
                       'Move arm preserves 4-connected component count. Unchanged ink/counter topology '
                       'does not guarantee acceptable local weight. Greedy bounded search; human review pending.',glyphs=records)
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n');sheet(records)
    for r in records:
        print(r['character'],{m:[(e['feature_id'],e['status'],e['removed'],e['added']) for e in r[m]['events']]
                             for m in ('thin','move')})


if __name__=='__main__':main()
