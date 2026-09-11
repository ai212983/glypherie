"""Audit every displaced alignment, including constraints rejected by the solver."""
import argparse,json
from collections import Counter
from pathlib import Path
import freetype as ft
import numpy as np
from compare_paper_prototypes import HERE,digest


def audit(path):
    report=json.loads(path.read_text());cases=[];counts=Counter()
    for name,sha in report['source_hashes'].items():
        if digest(HERE/name)!=sha:raise ValueError(f'stale source: {name}')
    for build in report['builds']:
        font=path.parent/f"{build['font']}-{build['size']}.ttf"
        if digest(font)!=build['font_sha256']:raise ValueError(f'stale font: {font.name}')
        face=ft.Face(str(font));face.set_pixel_sizes(0,build['size'])
        for char,record in build['records'].items():
            face.load_char(char,ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_HINTING)
            original=np.asarray(face.glyph.outline.points,float).reshape(-1,2)/64
            face.load_char(char,ft.FT_LOAD_NO_BITMAP|ft.FT_LOAD_NO_AUTOHINT|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_PEDANTIC)
            points=np.asarray(face.glyph.outline.points,float).reshape(-1,2)/64
            for entry in record['attachment_resolution']:
                c=entry['constraint'];counts[entry['status']]+=1
                zero=abs(c['value'])<=1e-7
                counts['zero_distance' if zero else 'nonzero_distance']+=1
                a=c['sources'][0];p=c['point']
                expected=float((original[p]-original[a])@c['normal'])
                error=abs(float((points[p]-points[a])@c['normal'])-expected)
                if error<=.065:continue
                winners=[w for w in record['graph']['constraints'] if w['point']==p]
                family='cycle' if entry['reason']=='dependency cycle' else '+'.join(sorted(w['kind']+(' metric' if w.get('metric') else '') for w in winners))
                cases.append(dict(font=build['font'],size=build['size'],char=char,error_px=error,
                                  family=family,zero_distance=zero,expected_offset_px=expected,**entry,winners=winners))
    cases.sort(key=lambda c:-c['error_px'])
    return dict(conformance_sha256=digest(path),audit_sha256=digest(Path(__file__)),
                freetype_version=ft.version(),counts=dict(counts),displaced=len(cases),
                displaced_zero=sum(c['zero_distance'] for c in cases),
                displaced_nonzero=sum(not c['zero_distance'] for c in cases),
                reasons=dict(Counter(c['reason'] for c in cases)),families=dict(Counter(c['family'] for c in cases)),cases=cases)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('report',type=Path);args=parser.parse_args()
    result=audit(args.report);output=args.report.parent/'alignment-audit.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))

if __name__=='__main__':main()
