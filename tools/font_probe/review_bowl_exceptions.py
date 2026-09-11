"""Render recorded exceptions for human review; leaves fitting rules unchanged."""
import hashlib
import json
from pathlib import Path

from PIL import Image,ImageDraw
from paper_gridfit import ft,bitmap

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'tools/font_probe/out/paper-bowls/review'
SCALE=7


def draw_glyph(draw,glyph,x,baseline,scale):
    for i,value in enumerate(glyph['pixels']):
        if value:
            px=x+(glyph['left']+i%glyph['width'])*scale
            py=baseline+(glyph['top']+i//glyph['width'])*scale
            draw.rectangle((px,py,px+scale-1,py+scale-1),fill='black')


def source_reference(name,record,digest):
    jobpath=ROOT/f'tools/font_generator/examples/{name}.json'
    job=json.loads(jobpath.read_text());font=(jobpath.parent/job['font']).resolve()
    assert hashlib.sha256(font.read_bytes()).hexdigest()==digest
    face=ft.Face(str(font));axes=face.get_variation_info().axes
    face.set_var_design_coords([record['axes'].get(a.tag,a.default) for a in axes])
    # Same variation coordinates, unhinted outline sampled at seven times size.
    face.set_pixel_sizes(0,record['size']*SCALE)
    face.load_char(record['char'],ft.FT_LOAD_NO_HINTING|ft.FT_LOAD_NO_BITMAP)
    return bitmap(face,record['char'])


def sheet(cases,filename,title,out=None):
    width=880;cell=440;rowheight=220
    im=Image.new('RGB',(width,45+((len(cases)+1)//2)*rowheight),'white')
    draw=ImageDraw.Draw(im);draw.text((12,10),title,fill='black')
    for i,case in enumerate(cases):
        x=(i%2)*cell;y=45+(i//2)*rowheight
        draw.text((x+12,y),f"{i+1}. {case['font']} / {case['size']}px / {case['char']}",fill='black')
        draw.text((x+12,y+17),case['reason'],fill='black')
        for col,(label,glyph,scale) in enumerate(case['columns']):
            left=x+12+col*140
            draw.text((left,y+38),label,fill='black')
            if glyph is None:
                draw.text((left,y+78),'Stopped before',fill='black')
                draw.text((left,y+92),'rasterization',fill='black')
                continue
            draw_glyph(draw,glyph,left,y+173,scale)
        draw.line((x+8,y+212,x+cell-8,y+212),fill='#dddddd')
    im.save((out or OUT)/filename)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    topology=[];anchors=[];inputs={}
    for name in ('roboto','literata','source-sans-3'):
        path=OUT.parent/f'{name}.json';raw=path.read_bytes();inputs[str(path.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest()
        data=json.loads(raw)
        for r in data['records']:
            d=r.get('diagnostics',{});change=d.get('bowl_topology_rejection')
            conflict=d.get('vertical_stems',{}).get('bowl_rejection')
            if not (change or conflict):continue
            reference=source_reference(name,r,data['font_sha256'])
            case=dict(font=name,size=r['size'],char=r['char'])
            if change:
                case.update(reason=f"Enclosed white regions: {change['before'][1]} -> {change['after'][1]}",
                            columns=[('Source outline',reference,1),('Retained',r['glyph'],SCALE),('Rejected candidate',change['candidate_glyph'],SCALE)])
                topology.append(case)
            else:
                case.update(reason=conflict['status'].replace('; native fallback',''),
                            columns=[('Source outline',reference,1),('Retained',r['glyph'],SCALE),('No candidate',None,SCALE)])
                anchors.append(case)
        if name=='literata':
            r=next(r for r in data['records'] if r['char']=='E' and r['size']==14)
            priorpath=OUT.parent.parent/'paper-stems/literata.json'
            raw=priorpath.read_bytes();inputs[str(priorpath.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest()
            prior=next(p for p in json.loads(raw)['records'] if p['char']=='E' and p['size']==14)
            topology.append(dict(font=name,size=14,char='E',reason='Earlier stem-stage issue; current output shown',
                                 columns=[('Source outline',source_reference(name,r,data['font_sha256']),1),('Before stems',prior['baseline_glyph'],SCALE),('Current output',r['glyph'],SCALE)]))
    sheet(topology,'topology-and-e.png','Outline reference / retained output / rejected candidate (E uses before/current)')
    sheet(anchors,'anchor-conflicts.png','Anchor conflicts: source outline and retained output; no candidate was rasterized')
    manifest=dict(inputs=inputs,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  reference='Unhinted source, same axes, sampled at 7x size; visual shape reference, not a target bitmap.',
                  topology_and_e=topology,anchor_conflicts=anchors)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'{len(topology)} topology/E panels; {len(anchors)} anchor panels')


if __name__=='__main__':main()
