"""Compare checked scalar/point builds, recording graph, coordinate and pixel changes."""
import argparse,json,html
from pathlib import Path
import freetype as ft
import numpy as np
from PIL import Image,ImageDraw
from compare_paper_prototypes import HERE,digest,render,pixels,draw_glyph


def compare(scalar,point,out):
    reports=[json.loads((p/'conformance.json').read_text()) for p in (scalar,point)]
    if [r['scheduler'] for r in reports]!=['scalar','point']:raise ValueError('expected scalar then point reports')
    if reports[0]['source_hashes']!=reports[1]['source_hashes']:raise ValueError('different model sources')
    for name,sha in reports[0]['source_hashes'].items():
        if digest(HERE/name)!=sha:raise ValueError(f'stale source: {name}')
    out.mkdir(parents=True,exist_ok=True);rows=[]
    for a,b in zip(reports[0]['builds'],reports[1]['builds'],strict=True):
        if (a['font'],a['size'],a['source_sha256'])!=(b['font'],b['size'],b['source_sha256']):raise ValueError('different inputs')
        name,size=a['font'],a['size'];faces=[]
        for folder,build in ((scalar,a),(point,b)):
            path=folder/f'{name}-{size}.ttf'
            if digest(path)!=build['font_sha256']:raise ValueError('stale font')
            faces.append(ft.Face(str(path)))
        for char,ar in a['records'].items():
            br=b['records'][char]
            for field in ('features','templates','template_ownership','extraction'):
                if ar[field]!=br[field]:raise ValueError(f'changed construction: {field}')
            coords=[]
            for face in faces:
                face.set_pixel_sizes(0,size)
                face.load_char(char,ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_PEDANTIC|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_NO_BITMAP)
                coords.append(np.asarray(face.glyph.outline.points,float).reshape(-1,2)/64)
            ga,gb=[render(face,char,size,hinted=True) for face in faces];pa,pb=pixels(ga),pixels(gb)
            def signatures(record):
                return sorted((c['point'],tuple(c['normal']),c['kind'],tuple(c['sources']),c['value'],c.get('round',True)) for c in record['graph']['constraints'])
            def cycles(record):
                return {stage:[r['constraint']['id'] for r in record[stage]['rejected'] if r['reason']=='dependency cycle'] for stage in ('reduced_graph','graph')}
            delta=np.linalg.norm(coords[1]-coords[0],axis=1)
            row=dict(font=name,size=size,char=char,relations_changed=signatures(ar)!=signatures(br),
                     cycles_scalar=cycles(ar),cycles_point=cycles(br),
                     max_coordinate_delta_px=float(delta.max()) if len(delta) else 0,
                     changed_points=int(np.count_nonzero(delta)),removed=sorted(pa-pb),added=sorted(pb-pa))
            if pa!=pb:
                image=Image.new('RGB',(640,400),'white');d=ImageDraw.Draw(image)
                d.text((8,8),f'{name} {size}px U+{ord(char):04X} {char!r} | scalar / point',fill='black')
                draw_glyph(d,ga,40,290,10);draw_glyph(d,gb,360,290,10)
                row['crop']=f'{name}-{size}-u{ord(char):04x}.png';image.save(out/row['crop'])
            rows.append(row)
    summary=dict(cases=len(rows),relations_changed=sum(r['relations_changed'] for r in rows),
                 coordinates_changed=sum(r['changed_points']>0 for r in rows),
                 bitmaps_changed=sum(bool(r['removed'] or r['added']) for r in rows),
                 cycles={mode:sum(len(r[f'cycles_{mode}'][stage]) for r in rows for stage in ('reduced_graph','graph')) for mode in ('scalar','point')},
                 max_coordinate_delta_px=max(r['max_coordinate_delta_px'] for r in rows))
    result=dict(summary=summary,report_hashes=[digest(p/'conformance.json') for p in (scalar,point)],
                comparison_sha256=digest(Path(__file__)),cases=rows)
    (out/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    pairs=[r for r in rows if r.get('crop')]
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Scheduler comparison</title>'
        '<style>body{font-family:sans-serif}img{max-width:100%}figure{display:inline-block;margin:8px}</style>'
        '<h1>Scalar / point scheduler</h1><p>Internal comparison. Each pair shows scalar on the left '
        'and point on the right. Neither column is a new approved candidate.</p>'+
        ''.join('<figure><img src="'+r['crop']+'"><figcaption>'+
                html.escape(f"{r['font']} {r['size']}px {r['char']}: {len(r['removed'])} pixels removed, {len(r['added'])} added")+
                '</figcaption></figure>' for r in pairs))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scalar',type=Path,default=HERE/'out/shamir-scheduler-scalar')
    parser.add_argument('--point',type=Path,default=HERE/'out/shamir-scheduler-point')
    parser.add_argument('--output',type=Path,default=HERE/'out/shamir-scheduler-comparison')
    args=parser.parse_args();compare(args.scalar,args.point,args.output)
