"""Read-only renderer audit: execute instruction prefixes in temporary fonts."""
import json,tempfile
from pathlib import Path
import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
from compare_paper_prototypes import HERE,digest


def measure(face,char,size,hinted=True):
    face.set_pixel_sizes(0,size)
    flags=ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_TARGET_MONO
    flags|=ft.FT_LOAD_PEDANTIC|ft.FT_LOAD_NO_AUTOHINT if hinted else ft.FT_LOAD_NO_HINTING
    face.load_char(char,flags);p=np.array(face.glyph.outline.points,dtype=float).reshape(-1,2)/64
    box=face.glyph.outline.get_bbox()
    return dict(points=p.tolist(),width=(box.xMax-box.xMin)/64,advance=face.glyph.advance.x/64)


def main():
    base=HERE/'out/shamir-controlled';candidate=base/'segments';report=json.loads((candidate/'report.json').read_text())
    paths=list(base.glob('*.ttf'))+list(candidate.glob('*.ttf'));hashes={str(p.relative_to(HERE)):digest(p) for p in paths}
    records=[]
    with tempfile.TemporaryDirectory() as tmp:
        for build in report['builds']:
            name,size=build['font'],build['size'];fontpath=candidate/f'{name}-{size}.ttf'
            source=ft.Face(str(base/f'{name}-{size}-source.ttf'));original=ft.Face(str(base/f'{name}-{size}-shamir.ttf'));full=ft.Face(str(fontpath))
            stages={}
            for stage in ('axes','diagonals'):
                font=TTFont(fontpath,recalcTimestamp=False)
                for char in build['records']:
                    g=font['glyf'][font.getBestCmap()[ord(char)]]
                    if not hasattr(g,'program'):continue
                    asm=[a.split('/*')[0].strip() for a in g.program.getAssembly()]
                    x=[i for i,a in enumerate(asm) if a=='SVTCA[1]'];interp=x[1] if len(x)>1 else len(asm)
                    cut=next((i for i,a in enumerate(asm[:interp]) if a=='SPVFS[ ]'),interp) if stage=='axes' else interp
                    g.program.fromAssembly(asm[:cut])
                path=Path(tmp)/f'{stage}.ttf';font.save(path);stages[stage]=ft.Face(str(path))
            for char in build['records']:
                data=dict(source=measure(source,char,size,False),baseline=measure(original,char,size),
                          prepared=measure(full,char,size,False),axes=measure(stages['axes'],char,size),
                          diagonals=measure(stages['diagonals'],char,size),full=measure(full,char,size))
                p=np.array(data['prepared']['points']);q=np.array(data['full']['points'])
                records.append(dict(font=name,size=size,char=char,stages=data,
                    maximum_point_move=float(np.max(np.linalg.norm(q-p,axis=1))) if len(p) else 0))
    assert hashes=={str(p.relative_to(HERE)):digest(p) for p in paths}
    out=candidate/'constraint-audit.json';out.write_text(json.dumps(dict(input_hashes=hashes,records=records),indent=2)+'\n')
    for r in records:
        if r['char'] in 'X!' and r['size']==14:
            print(r['font'],r['char'],{k:round(v['width'],3) for k,v in r['stages'].items()},'maxmove',round(r['maximum_point_move'],3))

if __name__=='__main__':main()
