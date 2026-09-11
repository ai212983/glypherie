"""Declared alignment-tolerance experiment; never changes the baseline default.

Build all81 Roboto14 glyphs at each bound so recurring measurements use the same
repertoire. The scoped from_font override is the experiment mechanism and is
recorded explicitly; baseline source algorithms otherwise remain identical.
"""
import argparse
from contextlib import contextmanager
import html
import json
from pathlib import Path
import shutil
import freetype as ft
from PIL import Image, ImageDraw
import shamir_model
from check_shamir_baseline import digest, coordinate_check, graph_issues
from compare_shamir_pipeline import CHARS
from compare_paper_prototypes import render, pixels, draw_glyph
from render_shamir_baseline import extent, native_text

HERE=Path(__file__).resolve().parent
BOUNDS=(.012,.024,.048)
REPORTED='GSKJM+XxVvbdghjmnpq15'
LABELS=('Unhinted input','Reference 0.012em','Experiment 0.024em','Experiment 0.048em')


@contextmanager
def alignment_override(bound):
    original=shamir_model.from_font
    def configured(*args,**kwargs):
        model=original(*args,**kwargs)
        model['alignment_tolerance']=bound*model['em']
        return model
    shamir_model.from_font=configured
    try:yield
    finally:shamir_model.from_font=original


def image_row(glyphs,char):
    x0,y0,x1,y1=extent(glyphs);scale=8;pad=16
    width=max(205,(x1-x0)*scale+pad*2)
    image=Image.new('RGB',(width*4,(y1-y0)*scale+76),'white');draw=ImageDraw.Draw(image)
    draw.text((pad,5),f'Roboto14 U+{ord(char):04X} {char!r}',fill='black')
    for i,(glyph,label) in enumerate(zip(glyphs,LABELS)):
        draw.text((width*i+pad,25),label,fill='black')
        draw_glyph(draw,glyph,width*i+pad-x0*scale,54-y0*scale,scale)
    return image


def run(source,output):
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('preserve earlier evidence; output must be empty')
    sources=sorted(HERE.glob('*.py'));hashes={p.name:digest(p) for p in sources}
    (output/'sources').mkdir()
    for path in sources:shutil.copy2(path,output/'sources'/path.name)
    frozen=output/'roboto-14-source.ttf';shutil.copy2(source,frozen)
    builds=[]
    for bound in BOUNDS:
        target=output/f'roboto-14-alignment-{bound:.3f}.ttf'
        with alignment_override(bound):
            result=shamir_model.build_font(frozen,target,CHARS,profile='baseline',ppem=14)
        result['experiment_override']=dict(setting='curved_alignment_em',value=bound,
            classification='comparison reference' if bound==.012 else 'experimental numeric setting',
            mechanism='scoped from_font alignment_tolerance override',baseline_default_changed=False)
        face=ft.Face(str(target));checks=[]
        for char,record in result['records'].items():
            check=coordinate_check(face,char,14,record['graph'])
            issues=graph_issues(record['graph'])+graph_issues(record['reduced_graph'])
            checks.append(dict(char=char,native=check,graph_issues=issues))
        (output/f'model-{bound:.3f}.json').write_text(json.dumps(result,indent=2)+'\n')
        builds.append(dict(alignment_em=bound,font=target.name,font_sha256=digest(target),
                           experiment_override=result['experiment_override'],checks=checks))
        print(f'{bound:.3f}: {len(checks)} cases checked',flush=True)
    if hashes!={p.name:digest(p) for p in sources}:raise RuntimeError('sources changed during experiment')
    faces=[ft.Face(str(frozen))]+[ft.Face(str(output/b['font'])) for b in builds]
    rows=[];figures=[]
    for char in CHARS:
        glyphs=[render(face,char,14,hinted=bool(i)) for i,face in enumerate(faces)]
        inks=[pixels(g) for g in glyphs]
        row=dict(char=char,pixel_counts=list(map(len,inks)),
                 differences_from_reference=[len(inks[i]^inks[1]) for i in (2,3)])
        if char in REPORTED:
            name=f'u{ord(char):04x}.png';image_row(glyphs,char).save(output/name);row['image']=name
        rows.append(row)
    for char in REPORTED:
        row=next(r for r in rows if r['char']==char)
        figures.append(f'<figure id="u{ord(char):04x}"><img src="{row["image"]}" alt="{html.escape(char,quote=True)} four-way tolerance comparison"></figure>')
    text=[]
    for i,(face,label) in enumerate(zip(faces,LABELS)):
        for j,line in enumerate(('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz','0123456789 .,;:!?%°+-/()[]"\'=')):
            name=f'native-{i}-{j}.png';im=native_text(face,line,14,bool(i));im.save(output/name)
            text.append(f'<div><span>{label}</span><img src="{name}" width="{im.width}" height="{im.height}"></div>')
    report=dict(experiment='curved-extremum alignment sensitivity',status='experimental settings; no baseline promotion',
                source_hashes=hashes,input_sha256=digest(frozen),freetype=ft.version(),characters=CHARS,
                reported_characters=REPORTED,bounds=BOUNDS,builds=builds,bitmap_comparison=rows)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    passed=all(c['native']['passed'] and not c['graph_issues'] for b in builds for c in b['checks'])
    title='Roboto14 alignment-tolerance experiment'
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>'+title+'</title>'
        '<style>body{font:16px system-ui;margin:24px}.notice{background:#fff1ce;padding:16px}figure{margin:12px 0;overflow:auto}img{max-width:none;image-rendering:pixelated}div{display:flex;align-items:center;gap:16px;overflow:auto}span{min-width:185px}</style>'
        '<h1>'+title+'</h1><p class="notice">Experimental numeric settings, not a new baseline. Left to right in every glyph row: unhinted input; current 0.012em reference; 0.024em experiment; 0.048em experiment. '
        'All builds use the complete 81-glyph repertoire for global measurements. Only alignment tolerance changes. No setting is selected by this gallery.</p>'
        f'<p>243 native coordinate and graph cases: {"passed" if passed else "FAILURES — inspect report"}. Enlarged views use 8× native pixels. <a href="report.json">Evidence report</a></p>'
        '<h2>Native-size text</h2>'+''.join(text)+'<h2>Reported cases</h2>'+''.join(figures))
    if not passed:raise ValueError('experimental coordinate/graph checks failed; report preserved')
    print(json.dumps(dict(gallery=str(output/'index.html'),changed_glyphs=[sum(r['differences_from_reference'][i]>0 for r in rows) for i in (0,1)])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=HERE/'out/shamir-baseline-v3/inputs/roboto-14-source.ttf')
    parser.add_argument('--output',type=Path,default=HERE/'out/shamir-tolerance-comparison')
    args=parser.parse_args();run(args.source,args.output)
