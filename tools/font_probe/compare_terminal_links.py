"""Native terminal-link comparison; preserves parent-anchor-v1 unrounded fonts."""
import json
import argparse
import shutil
from array import array
from pathlib import Path
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables.ttProgram import Program
from check_shamir_baseline import digest
from compare_paper_prototypes import render,pixels
from compare_shamir_representatives import comparison
from serif_reference_view import prepend_reference
from shamir_baseline_solver import _round_pixel
from vtt_terminal_links import detect,program,values

HERE=Path(__file__).resolve().parent


def coordinates(face,size,hinted):
    face.set_pixel_sizes(0,size)
    flags=ft.FT_LOAD_NO_BITMAP | (ft.FT_LOAD_PEDANTIC|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO if hinted else ft.FT_LOAD_NO_HINTING)
    face.load_char('F',flags)
    return np.asarray(face.glyph.outline.points,float)/64


def run(shorter=False, paired=False):
    reference=HERE/'out/parent-anchor-v1'
    output=HERE/'out'/('terminal-shorter-v1' if shorter else 'terminal-links-v1')
    policies=('down','smaller') if shorter else ('separate','shared')
    labels=['Both extensions rounded down','Smaller source value (nearest)'] if shorter else ['Separate extension values','Shared extension value']
    if paired:
        output=HERE/'out/terminal-paired-v1'
        policies=('down','paired')
        labels=['Separate values rounded down','Shared smaller value rounded down']
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('output must be empty')
    (output/'sources').mkdir();hashes={p.name:digest(p) for p in HERE.glob('*.py')}
    for name in hashes:shutil.copy2(HERE/name,output/'sources'/name)
    cases=[];figures=[];inputs={}
    for size in (14,16,18,20):
        key=f'literata-{size}';source=reference/f'{key}-unrounded.ttf';inputs[source.name]=digest(source)
        shutil.copy2(source,output/source.name)
        baseline=ft.Face(str(source));before=coordinates(baseline,size,True);original=coordinates(baseline,size,False)
        variants=[];faces=[baseline]
        for policy in policies:
            font=TTFont(source);g=font['glyf'][font.getBestCmap()[70]];points,ends,flags=g.getCoordinates(font['glyf'])
            roles=detect(points,flags,ends);cvts=values(points,roles,policy=='shared')
            if policy in ('smaller','paired'):cvts=[min(cvts)]*2
            round_down=policy in ('down','paired')
            if 'cvt ' not in font:font['cvt ']=newTable('cvt ');font['cvt '].values=array('h')
            first=len(font['cvt '].values);font['cvt '].values.extend(cvts)
            assembly=g.program.getAssembly()
            assert assembly[-1].startswith('EIF[ ]')
            assembly=assembly[:-1]+program(roles,[first,first+1],round_down=round_down)+assembly[-1:]
            g.program=Program();g.program.fromAssembly(assembly)
            font['maxp'].maxSizeOfInstructions=max(font['maxp'].maxSizeOfInstructions,len(g.program.getBytecode()))
            font['maxp'].maxStackElements=max(font['maxp'].maxStackElements,16)
            target=output/f'{key}-{policy}.ttf';em=font['head'].unitsPerEm
            font.save(target);font.close();face=ft.Face(str(target));faces.append(face)
            actual=coordinates(face,size,True);expected=before.copy()
            for parent,child,value in [(roles['upper_arm'],roles['top'],cvts[0]),(roles['lower_arm'],roles['bottom'],cvts[1])]:
                scaled=np.floor(value*size/em*64+.5)/64
                assert abs(abs(original[child,1]-original[parent,1])-scaled)<1
                distance=np.floor(scaled) if round_down else _round_pixel(scaled)
                expected[child,1]=before[parent,1]+np.sign(original[child,1]-original[parent,1])*distance
            for a,b,children in [(roles['upper_arm'],roles['top'],roles['upper']),
                                  (roles['bottom'],roles['lower_arm'],roles['lower']),
                                  (roles['top'],roles['bottom'],roles['tip'])]:
                for i in children:
                    t=(points[i][1]-points[a][1])/(points[b][1]-points[a][1])
                    expected[i,1]=expected[a,1]+t*(expected[b,1]-expected[a,1])
            error=float(np.max(abs(actual-expected)))
            assert error<=1/64+1e-7
            touched={roles['top'],roles['bottom'],*roles['upper'],*roles['lower'],*roles['tip']}
            assert np.array_equal(before[:,0],actual[:,0])
            assert all(np.array_equal(before[i],actual[i]) for i in range(len(before)) if i not in touched)
            if policy=='paired':
                assert actual[roles['top'],1]-actual[roles['upper_arm'],1]==actual[roles['lower_arm'],1]-actual[roles['bottom'],1]
            variants.append(dict(policy=policy,roles=roles,cvts_fu=cvts,native_points=actual.tolist(),
                                 extensions_px=[float(actual[roles['top'],1]-actual[roles['upper_arm'],1]),
                                                float(actual[roles['lower_arm'],1]-actual[roles['bottom'],1])],
                                 oracle_error_px=error,oracle_tolerance_px=1/64,
                                 same_bitmap=pixels(render(baseline,'F',size,hinted=True))==pixels(render(face,'F',size,hinted=True))))
        glyphs=[render(f,'F',size,hinted=True) for f in faces]
        panel=comparison(glyphs,['Current reference',*labels],f'{key} F')
        name=f'{key}.png';prepend_reference(baseline,'F',size,f'{key} F',glyphs,panel).save(output/name)
        cases.append(dict(key=key,variants=variants));figures.append(f'<figure><img src="{name}" alt="{key} F"></figure>')
    assert hashes=={name:digest(HERE/name) for name in hashes}
    assert inputs=={name:digest(reference/name) for name in inputs}
    (output/'report.json').write_text(json.dumps(dict(sources=hashes,inputs=inputs,cases=cases,
        policy='Native MIRP grey links, 1px CVT cut-in, no minimum override, native unrounded IP. Arm and x coordinates fixed. Down uses separate source values with RDTG; smaller uses the minimum source value for both with RTG; shared uses their rounded mean with RTG; paired uses the minimum for both with RDTG. These choices are project policies, not a recovered SERIF recipe.'),indent=2)+'\n')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Terminal links</title><style>img{max-width:100%;image-rendering:pixelated}</style>'
        '<h1>Terminal links</h1><p>Columns: smooth source, current reference, '+', '.join(labels)+'. '
        'Native MIRP/IP instructions; terminal mapping and value selection are experimental. Stem and serif treatment fixed.</p>'+''.join(figures))
    print('8 native variants verified')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--shorter',action='store_true',help='Compare floor rounding and the smaller source measurement')
    group.add_argument('--paired',action='store_true',help='Compare separate and shared smaller measurements, both rounded down')
    args=parser.parse_args()
    run(args.shorter,args.paired)
