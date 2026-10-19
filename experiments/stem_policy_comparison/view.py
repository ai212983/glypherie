"""Present actual captures; no fitting, rasterization or quality scoring.

The viewer displays the actual capture commands and delivered pixels from the
existing generator fitting implementation; it adds no recognizer, width solver
or font-specific adjustment. Outline coordinates are Y-up; bitmap coordinates
are Y-down. An inspection row Y through Y+1 maps to bitmap row -Y-1-top. Black
spans are contiguous pixel runs from left to right; they are observations, not
recognized semantic stems or an optical acceptance score. The default witness
rows for m/u/t are the reported straight-span intervals, not fitting parameters.
"""

import argparse
import shutil
from pathlib import Path

HTML = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Stem fitting comparison</title>
<link rel="icon" href="data:,"><style>
body{font:16px system-ui;max-width:1050px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#222}
h1{font-size:1.7rem}select,input{font:inherit;padding:.3rem}label{display:inline-block;margin-right:1rem}
#columns{display:grid;grid-template-columns:1fr 1fr;gap:1rem}article{padding:1rem;background:#fafafa;border:1px solid #ccc}
svg{width:100%;height:290px;background:white}canvas{image-rendering:pixelated;display:block;margin:1rem 0;background:white}
.key{color:#555}pre{white-space:pre-wrap}a{color:#174c85}h2{font-size:1.15rem}
@media(max-width:650px){#columns{grid-template-columns:1fr}}
</style><h1>Uneven stem widths: fitting comparison</h1>
<p>Two existing Skrifa fitting strategies, with the same candidate raster and source layout.
StrokeStyles is parked. Font hints first is the default; automatic Mono is the control.</p>
<label>Font and size <select id="case"></select></label>
<label>Glyph <select id="glyph"></select></label>
<label>Inspect Y-up row <input id="row" type="number" value="2" step="1" style="width:4rem"></label>
<p class="key">Outline: dashed gray = unhinted source; blue = fitted.
Bitmaps: actual delivered 1-bit pixels at 4×. The row readout lists contiguous black spans from left to right.</p>
<div id="columns"></div><p><a href="captures.json">Capture data and provenance</a></p>
<p><strong>Upstream fitting comparison:</strong> the default uses font-provided instructions when available,
with upstream automatic fallback. The control always uses the automatic hinter. Both use the same project raster
and source advances. Outlines are unchanged from the selected library hinter; optical acceptance is assessed separately.</p>
<p><strong>Known limits:</strong> at Roboto 14px, font hints first retains the uneven m/u/t stem widths.
Automatic Mono equalizes those straight stems but makes A's right leg heavier. Italic m remains uneven in both policies.
These findings do not establish a general fix.</p>
<script type="module">
const $=id=>document.getElementById(id),data=await(await fetch('captures.json')).json();
for(const[c,i]of data.cases.map((c,i)=>[c,i]))$('case').add(new Option(`${c.family} ${c.size_px}px${c.axes.slnt?' slant '+c.axes.slnt:''}`,i));
$('case').value='1';for(const c of 'mutAvo')$('glyph').add(new Option(c,c));
function path(commands){return commands.map(c=>({move_to:`M${c.x},${-c.y}`,line_to:`L${c.x},${-c.y}`,quad_to:`Q${c.x1},${-c.y1} ${c.x},${-c.y}`,curve_to:`C${c.x1},${-c.y1} ${c.x2},${-c.y2} ${c.x},${-c.y}`,close:'Z'})[c.op]).join(' ')}
function spans(r,y){const row=-y-1-r.top;if(row<0||row>=r.height)return[];const result=[];let count=0;for(let x=0;x<=r.width;x++){if(x<r.width&&r.pixels[row*r.width+x])count++;else if(count){result.push(count);count=0}}return result}
function show(){const c=data.cases[Number($('case').value)],cp=$('glyph').value.codePointAt(0),y=Number($('row').value);
const record=k=>c[k].records.find(r=>r.codepoint===cp),source=record('source');
const records=[record('font_hints_first'),record('upstream_mono')];const all=[source,...records];
const left=Math.min(...all.map(r=>r.left))-2,top=Math.min(...all.map(r=>r.top))-2,right=Math.max(...all.map(r=>r.left+r.width))+2,bottom=Math.max(...all.map(r=>r.top+r.height))+2,w=right-left,h=bottom-top;
$('columns').replaceChildren();for(const[i,key]of ['font_hints_first','upstream_mono'].entries()){const r=records[i],a=document.createElement('article');a.dataset.strategy=key;
const title=document.createElement('h2');title.textContent=i?'Control: automatic Mono':'Default: font hints first';a.append(title);
const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox',`${left} ${top} ${w} ${h}`);
for(const[commands,color,dash]of [[source.fitted_commands,'#888','.15,.1'],[r.fitted_commands,'#206cc3','']]){const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',path(commands));p.setAttribute('fill','none');p.setAttribute('stroke',color);p.setAttribute('stroke-width','.065');p.setAttribute('stroke-dasharray',dash);svg.append(p)}a.append(svg);
const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;canvas.style.width=`${w*4}px`;canvas.style.height=`${h*4}px`;const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,w,h);ctx.fillStyle='black';for(let iy=0;iy<r.height;iy++)for(let ix=0;ix<r.width;ix++)if(r.pixels[iy*r.width+ix])ctx.fillRect(r.left-left+ix,r.top-top+iy,1,1);a.append(canvas);
const text=document.createElement('pre');text.textContent=`Y ${y}..${y+1}: black spans ${JSON.stringify(spans(r,y))}\nSource advance: ${r.advance_26_6/64}px\nEngine: ${r.selected_engine} (policy: ${c[key].hinting_requested})\nFitting target: ${c[key].target}${c[key].smooth_mode?' / '+c[key].smooth_mode:''}\nRaster: ${r.raster_policy}`;a.append(text);$('columns').append(a);}}
$('case').addEventListener('change',show);$('glyph').addEventListener('change',()=>{$('row').value=({m:2,u:5,t:5})[$('glyph').value]??4;show()});$('row').addEventListener('input',show);show();
</script></html>"""


def build(captures, output):
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(captures, output / "captures.json")
    (output / "index.html").write_text(HTML)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.captures, args.output)
