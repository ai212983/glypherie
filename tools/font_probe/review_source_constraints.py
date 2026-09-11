"""Compare the previous experiment preferred by the user with source-aware output."""
import hashlib
import json
from pathlib import Path
from review_bowl_exceptions import ROOT,sheet,SCALE

OUT=ROOT/'tools/font_probe/out/paper-source-aware/review'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    previous=ROOT/'tools/font_probe/out/paper-bowls/review/manifest.json'
    raw=previous.read_bytes();old=json.loads(raw);cases=[]
    inputs={str(previous.relative_to(ROOT)):hashlib.sha256(raw).hexdigest()}
    for case in old['topology_and_e']:
        path=OUT.parent/f"{case['font']}.json";raw=path.read_bytes()
        inputs[str(path.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest()
        data=json.loads(raw)
        new=next(r for r in data['records'] if r['char']==case['char'] and r['size']==case['size'])
        diagnostics=new['diagnostics']['source_constraints']
        cases.append(dict(font=case['font'],size=case['size'],char=case['char'],
                          reason=f"New: {diagnostics['selected']['raster_counters']} enclosed white region(s)",
                          columns=[case['columns'][0],('A: previous experiment',case['columns'][2][1],SCALE),
                                   ('B: new',new['glyph'],SCALE)]))
    sheet(cases,'comparison.png','Source outline / A: previous experiment / B: source-aware result',OUT)
    (OUT/'manifest.json').write_text(json.dumps(dict(inputs=inputs,cases=cases),indent=2)+'\n')
    print(f'{len(cases)} source/A/B comparisons')


if __name__=='__main__':main()
