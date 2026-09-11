"""Check fixed preferred join-repair rules across a repertoire and nearby sizes."""
import hashlib
import json
import string
import argparse
from pathlib import Path

import freetype as ft
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

from analyze_features import ROOT, FlattenPen, detect, visible_boundary
from track_features import snapshot, match_features, solid
from outline_experiment import render
from correct_pixels import correct
from compare_join_repairs import repair
from calibrate import topology
from classify_junctions import classify
from protect_stems import stem_regions, protected_pixels

OUT=ROOT/'tools/font_probe/out/transfer-check'
SIZES=(14,16,18,20)
CHARS=string.ascii_uppercase+string.ascii_lowercase+string.digits


def source_topology(boundary):
    geometry=solid(boundary)
    polygons=[geometry] if geometry.geom_type=='Polygon' else list(geometry.geoms)
    return [len(polygons),sum(len(p.interiors) for p in polygons)]


def specimen(records,size):
    subset=[r for r in records if r['size_px']==size and 'error' not in r]
    left=min(r[k]['left'] for r in subset for k in ('raw','final'))
    right=max(r[k]['left']+r[k]['width'] for r in subset for k in ('raw','final'))
    side=(right-left)*4+14;cell=2*side+12;columns=6
    image=Image.new('RGB',(columns*cell+24,((len(subset)+columns-1)//columns)*130+60),'white');d=ImageDraw.Draw(image)
    d.text((12,10),f'Roboto {size}px, weight 400 / fixed settings | each pair: before > after (4x)',fill='black')
    for i,r in enumerate(subset):
        ox=12+(i%columns)*cell;oy=110+(i//columns)*130
        d.text((ox,oy-72),r['character'],fill='black')
        for column,key in enumerate(('raw','final')):
            g=r[key];x0=ox+column*side-left*4
            for j,v in enumerate(g['pixels']):
                if v:
                    x=x0+(g['left']+j%g['width'])*4;y=oy+(g['top']+j//g['width'])*4
                    d.rectangle((x,y,x+3,y+3),fill='black')
        if r['changed_pixels']:d.text((ox,oy+22),f"{r['changed_pixels']} px",fill='#a04400')
        if r['topology_source']!=r['topology_final']:d.text((ox+45,oy+22),'shape flag',fill='#c00000')
    image.save(OUT/f'roboto-{size}.png')


def main(classified=False,protect=False):
    global OUT
    if classified:OUT=ROOT/'tools/font_probe/out/classified-transfer'
    if protect:OUT=ROOT/'tools/font_probe/out/stem-protected-transfer'
    OUT.mkdir(parents=True,exist_ok=True)
    fontpath=ROOT/'tools/font_probe/fonts/Roboto.ttf'
    font=TTFont(fontpath);gs=font.getGlyphSet(location={'wght':400,'wdth':100});cmap=font.getBestCmap()
    face=ft.Face(str(fontpath));face.set_var_design_coords([400,100])
    seedpath=ROOT/'tools/font_probe/out/join-repairs/results.json'
    seeds={r['character']:r['thin']['after'] for r in json.loads(seedpath.read_text())['glyphs']}
    records=[];summary=[]
    for size in SIZES:
        face.set_pixel_sizes(0,size)
        for char in CHARS:
            r=dict(character=char,size_px=size)
            try:
                pen=FlattenPen(gs,size/font['head'].unitsPerEm);gs[cmap[ord(char)]].draw(pen)
                boundary=visible_boundary(pen.contours);features=detect(boundary)
                source=snapshot(face,char,ft.FT_LOAD_NO_HINTING)
                grown=snapshot(face,char,ft.FT_LOAD_TARGET_MONO,True)
                matches=match_features(features,source,grown)
                classifications=[classify(f,boundary,size) for f in features] if classified else None
                active_matches=[dict(m,feature=None) if classified and not c['eligible'] else m
                                for m,c in zip(matches,classifications or [None]*len(matches))]
                raw=render(face,char,24,8)
                record=dict(character=char,grown=grown,raw_bitmap=raw,
                            tracking=[dict(source=f,grown=m) for f,m in zip(features,active_matches)])
                if protect:
                    region=stem_regions(grown['raw'],grown['boundary'],size)
                    record['protected_pixels']=protected_pixels(raw,region)
                    r['protected_pixels']=record['protected_pixels']
                    r['source_stem_area']=region.area
                guarded=correct(record);thinned=repair(record,guarded['after'],'thin');final=thinned['after']
                r.update(raw=raw,final=final,features=features,matches=matches,classifications=classifications,
                         guarded_events=guarded['events'],thin_events=thinned['events'],
                         final_retention=thinned['retention'],
                         changed_pixels=sum(a!=b for a,b in zip(raw['pixels'],final['pixels'])),
                         topology_source=source_topology(boundary),topology_raw=list(topology(raw,1)),
                         topology_final=list(topology(final,1)))
                if size==16 and char in seeds:
                    r['seed_matches']=final==seeds[char]
            except Exception as error:
                # Preserve each failure as evidence; report the matrix as incomplete.
                r['error']=f'{type(error).__name__}: {error}'
            records.append(r)
        batch=[r for r in records if r['size_px']==size];ok=[r for r in batch if 'error' not in r]
        s=dict(size_px=size,cases=len(batch),errors=sum('error' in r for r in batch),
               changed_glyphs=sum(r['changed_pixels']>0 for r in ok),
               removed_pixels=sum(r['changed_pixels'] for r in ok),
               detected=sum(len(r['features']) for r in ok),
               unmatched=sum(m['feature'] is None for r in ok for m in r['matches']),
               excluded=sum(not c['eligible'] for r in ok for c in (r['classifications'] or [])),
               unresolved=sum(v is not None and v<0.25 for r in ok for v in r['final_retention']),
               topology_regressions=[r['character'] for r in ok if r['topology_raw']!=r['topology_final']],
               source_topology_flags=[r['character'] for r in ok if r['topology_source']!=r['topology_final']])
        summary.append(s);specimen(records,size)
        print(json.dumps(s),flush=True)
    evidence=dict(font_sha256=hashlib.sha256(fontpath.read_bytes()).hexdigest(),freetype_version=ft.version(),
                  seed_sha256=hashlib.sha256(seedpath.read_bytes()).hexdigest(),
                  code_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                              [Path(__file__)]+[ROOT/'tools/font_probe'/n for n in
                              ('analyze_features.py','track_features.py','correct_pixels.py','compare_join_repairs.py','calibrate.py','outline_experiment.py','classify_junctions.py','protect_stems.py')]},
                  parameters=dict(sizes=SIZES,characters=CHARS,axes={'wght':400,'wdth':100},
                                  growth_26_6=24,phase_26_6=8,classification_enabled=classified,stem_protection=protect,
                                  settings='repair unchanged; optional source classification; see code hashes'),
                  summary=summary,glyphs=records,
                  limits='Single family; automatic topology guards do not establish visual quality; source topology flags can predate correction; unmatched features remain uncertain')
    (OUT/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    lines=['# '+('Stem-protected' if protect else 'Classified' if classified else 'Fixed-rule')+' transfer check','',
           '| Size | Changed glyphs | Pixels removed | Detected / unmatched junctions | Below trial target | Source topology flags |',
           '| --- | --- | --- | --- | --- | --- |']
    for s in summary:
        lines.append(f"| {s['size_px']} | {s['changed_glyphs']} | {s['removed_pixels']} | {s['detected']} / {s['unmatched']} | {s['unresolved']} | {', '.join(s['source_topology_flags']) or 'none'} |")
    seed_results=[r['seed_matches'] for r in records if 'seed_matches' in r]
    seeds_ok=len(seed_results)==len(seeds) and all(seed_results)
    lines+=['',f'Previous 16px seed glyphs reproduce exactly: {seeds_ok}.',
            f"Errors: {sum(s['errors'] for s in summary)}. Topology changes introduced by correction: {sum(len(s['topology_regressions']) for s in summary)}.",
            '', 'These checks measure structural behavior; image review and wider families remain open.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n')
    focus(records)
    if classified:comparison(records,protect)
    if (not protect and not seeds_ok) or any(s['errors'] or s['topology_regressions'] for s in summary):
        raise SystemExit('Transfer check incomplete or regressed; inspect results.json')


def focus(records):
    chars='HXe69';scale=6;cell=225
    im=Image.new('RGB',(len(chars)*cell+24,4*190+50),'white');d=ImageDraw.Draw(im)
    d.text((12,10),'Fixed-rule review | each pair: before > after (6x) | H, X, e, 6, 9',fill='black')
    lookup={(r['size_px'],r['character']):r for r in records if 'error' not in r}
    for row,size in enumerate(SIZES):
        y=48+row*190
        for col,char in enumerate(chars):
            r=lookup[size,char];ox=12+col*cell
            d.text((ox,y),f'{char} / {size}px',fill='black')
            for column,key in enumerate(('raw','final')):
                g=r[key]
                for j,v in enumerate(g['pixels']):
                    if v:
                        x=ox+column*110+(g['left']+j%g['width'])*scale
                        yy=y+140+(g['top']+j//g['width'])*scale
                        d.rectangle((x,yy,x+scale-1,yy+scale-1),fill='black')
    im.save(OUT/'focus.png')


def comparison(records,protect=False):
    directory='classified-transfer' if protect else 'transfer-check'
    previous=json.loads((ROOT/f'tools/font_probe/out/{directory}/results.json').read_text())
    lookup={r['character']:r for r in records if r['size_px']==16 and 'error' not in r}
    old={r['character']:r for r in previous['glyphs'] if r['size_px']==16 and 'error' not in r}
    chars='HXbhdep';image=Image.new('RGB',(910,385),'white');d=ImageDraw.Draw(image)
    labels=('Filtered rule / 16px','With source-derived stem protection / 16px') if protect else (
        'Previous correction rule / 16px','With source-geometry classification / 16px')
    for row,label in enumerate(labels):
        y=15+row*185;d.text((12,y),label,fill='black')
        for col,char in enumerate(chars):
            g=(old if row==0 else lookup)[char]['final'];ox=12+col*128
            d.text((ox,y+20),char,fill='black')
            for i,v in enumerate(g['pixels']):
                if v:
                    x=ox+(g['left']+i%g['width'])*8;yy=y+140+(g['top']+i//g['width'])*8
                    d.rectangle((x,yy,x+7,yy+7),fill='black')
    image.save(OUT/'classification-comparison.png')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--classify',action='store_true')
    parser.add_argument('--protect-stems',action='store_true')
    args=parser.parse_args()
    main(args.classify or args.protect_stems,args.protect_stems)
