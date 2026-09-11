"""Recognition review for the feature stage required by Shamir 2003."""
import argparse
import html
import json
from collections import Counter
from pathlib import Path
from fontTools.ttLib import TTFont
from compare_paper_prototypes import HERE,digest
from shamir_geometry import from_font
from shamir_features import recognize

CHARS='eX.,:;!?acsvxKWY'
COLORS={'stem':'#087f23','bar':'#8b31af','slant':'#d45b00','bow':'#006bc9',
        'arc':'#006bc9','curve_stem':'#00818a','curve_bar':'#00818a'}


def drawing(model,path):
    pts=[p['position'] for p in model['points']]
    if not pts:raise ValueError('empty review glyph')
    xmin=min(p[0] for p in pts);xmax=max(p[0] for p in pts)
    ymin=min(p[1] for p in pts);ymax=max(p[1] for p in pts)
    scale=min(330/max(xmax-xmin,1),330/max(ymax-ymin,1))
    def point(p,offset):return (offset+55+(p[0]-xmin)*scale,420-(p[1]-ymin)*scale)
    def xy(p,offset):return ','.join(f'{v:.4f}' for v in point(p,offset))
    def segment(s,offset):
        c=s['control'];return f'M{xy(c[0],offset)} '+('L' if len(c)==2 else 'Q')+' '.join(xy(p,offset) for p in c[1:])
    def outline(offset):
        paths=[]
        for loop in model['contours']:
            c=model['segments'][loop[0]]['control'];parts=[f'M{xy(c[0],offset)}']
            for sid in loop:
                c=model['segments'][sid]['control'];parts.append(('L' if len(c)==2 else 'Q')+' '.join(xy(p,offset) for p in c[1:]))
            paths.append(' '.join(parts)+' Z')
        return ' '.join(paths)
    content=['<svg xmlns="http://www.w3.org/2000/svg" role="img" width="900" height="470" viewBox="0 0 900 470">',
             '<title>'+html.escape(model['glyph'])+': source outline and recognized features</title>',
             '<rect width="900" height="470" fill="white"/>',
             '<text x="30" y="30" font-family="sans-serif" font-size="18">Source outline</text>',
             '<text x="480" y="30" font-family="sans-serif" font-size="18">Feature candidates</text>']
    for offset in (0,450):content.append(f'<path d="{outline(offset)}" fill="'+('#222' if offset==0 else '#ddd')+'" fill-rule="nonzero"/>')
    for p in model['points']:
        if p['extrema']:
            x,y=point(p['position'],450)
            content.append(f'<circle cx="{x}" cy="{y}" r="3" fill="white" stroke="'+('#d00077' if p['inserted'] else '#555')+'"/>')
    for f in model['features']:
        color=COLORS[f['kind']];content.append(f'<g data-feature="{f["id"]}" stroke="{color}" fill="none" stroke-width="2">')
        for sid in f.get('sides',[]):
            for segment_id in model['sides'][sid]['segments']:
                content.append(f'<path d="{segment(model["segments"][segment_id],450)}"/>')
        content.append(f'<path d="M{xy(f["a"],450)} L{xy(f["b"],450)}" stroke-dasharray="4 3"/>')
        for p in (f['a'],f['b']):
            x,y=point(p,450);content.append(f'<circle cx="{x}" cy="{y}" r="4" fill="white"/>')
        content.append('</g>')
    content.append('</svg>');path.write_text('\n'.join(content))


def gallery(out):
    (out/'index.html').write_text('''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shamir 2003 feature review</title><style>body{font:16px system-ui;margin:20px;background:#eee}select{font:inherit;margin:8px}p{max-width:900px}#image{width:900px}header{position:sticky;top:0;background:#eee;padding:10px 0;z-index:1}</style>
<header><b>Shamir 2003 — feature recognition review</b><p>These are outline annotations, before grid fitting. Review which candidate pairs correspond to strokes and curved parts. Existing Shamir bitmaps are unchanged.</p>
<label>Font<select id="font"><option>roboto</option><option>literata</option><option>source-sans-3</option></select></label>
<label>Size<select id="size"><option>14</option><option>16</option><option>18</option><option>20</option></select></label>
<label>Glyph<select id="char"></select></label><label>Feature<select id="feature"></select></label></header>
<p id="caption"></p><div id="image"></div><p>Solid colored lines mark paired sides; dashed lines connect measured features. Circles mark extrema; pink marks inserted extrema. Select one feature to inspect it alone.</p>
<p>Green: stems. Purple: bars. Orange: diagonals. Blue: paired curved extrema. Teal: a curve paired with a straight side. Serif and junction models, counter relationships and fitting remain to be implemented.</p>
<script>const f=document.querySelector('#font'),s=document.querySelector('#size'),c=document.querySelector('#char'),h=document.querySelector('#feature'),im=document.querySelector('#image');let data,serial=0;
function select(){im.querySelectorAll('[data-feature]').forEach(g=>g.style.display=h.value==='all'||g.dataset.feature===h.value?'':'none')}
async function show(){if(!data)return;const n=++serial,r=data.records.find(r=>r.font===f.value&&r.size===+s.value&&r.char===c.value);h.replaceChildren(new Option('All features','all'),...r.model.features.map(x=>new Option(x.kind+' '+(x.id+1),x.id)));document.querySelector('#caption').textContent=r.model.features.length+' features; '+r.model.points.filter(p=>p.inserted).length+' inserted extrema. '+(r.model.composite?'Composite outline resolved for analysis.':'');const svg=await fetch(r.image).then(r=>r.text());if(n===serial){im.innerHTML=svg;select()}}
[f,s,c].forEach(x=>x.addEventListener('change',show));h.addEventListener('change',select);fetch('report.json').then(r=>r.json()).then(r=>{data=r;c.replaceChildren(...Array.from(r.characters,x=>new Option(x,x)));show()});</script>''')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=HERE/'out/shamir-controlled/features')
    args=parser.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    sources={p:digest(HERE/p) for p in ('shamir_geometry.py','shamir_features.py','review_shamir_features.py')}
    base=HERE/'out/shamir-controlled';baseline=json.loads((base/'report.json').read_text());records=[];coverage=[]
    for build in baseline['builds']:
        name,size=build['font'],build['size'];path=base/f'{name}-{size}-source.ttf'
        if digest(path)!=build['source_sha256']:raise ValueError('source font changed')
        font=TTFont(path,recalcTimestamp=False)
        for char in baseline['characters']:
            model=from_font(font,char);model.update(recognize(model))
            coverage.append(dict(font=name,size=size,char=char,features=dict(Counter(f['kind'] for f in model['features']))))
            if char not in CHARS:continue
            filename=f'{name}-{size}-{ord(char)}.svg';drawing(model,out/filename)
            records.append(dict(font=name,size=size,char=char,image=filename,model=model))
        print(name,size,flush=True)
    if sources!={p:digest(HERE/p) for p in sources}:raise ValueError('source changed during analysis')
    report=dict(scope='Prepared geometry and basic recognition for Shamir 2003; no fitting changes',
        characters=CHARS,baseline_report_sha256=digest(base/'report.json'),
        sources=sources,
        records=records,coverage=coverage)
    (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');gallery(out)


if __name__=='__main__':main()
