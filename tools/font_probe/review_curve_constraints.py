"""Compare curved-stroke experiment with source-aware baseline."""
import hashlib
import json
from review_bowl_exceptions import ROOT,sheet,source_reference,SCALE

OUT=ROOT/'tools/font_probe/out/paper-curves/review'


def main():
    OUT.mkdir(parents=True,exist_ok=True);cases=[];inputs={}
    for name,char,size in [('roboto','6',18),('literata','g',20),('roboto','6',16),('literata','g',18)]:
        data=[]
        for stage in ('paper-source-aware','paper-curves'):
            path=ROOT/f'tools/font_probe/out/{stage}/{name}.json';raw=path.read_bytes()
            inputs[str(path.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest();data.append(json.loads(raw))
        before,after=[next(r for r in d['records'] if r['char']==char and r['size']==size) for d in data]
        cases.append(dict(font=name,char=char,size=size,reason='Curved-stroke thickness experiment',columns=[
            ('Source outline',source_reference(name,after,data[1]['font_sha256']),1),
            ('A: previous',before['glyph'],SCALE),('B: curved fit',after['glyph'],SCALE)]))
    sheet(cases,'comparison.png','Source / A: previous / B: curved-stroke constraints',OUT)
    (OUT/'manifest.json').write_text(json.dumps(dict(inputs=inputs,cases=cases),indent=2)+'\n')


if __name__=='__main__':main()
