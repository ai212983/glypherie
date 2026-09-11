"""Show the specific discussed regions alongside the retained earlier variants.

Uses recorded pixels, preserving what was previously reviewed. Earlier pipeline
scan/dropout settings differ from the normalized prototype comparison; this is
a visual history comparison, not an isolated algorithm benchmark.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw
from compare_paper_prototypes import ROOT, draw_glyph, check_bounds

OUT = ROOT / 'tools/font_probe/out/paper-prototypes'
CASES = [('6', 'Lower bowl transition', (0, -4, 9, 1)),
         ('b', 'Lower-left stem / bowl join', (0, -3, 5, 1)),
         ('h', 'Upper shoulder', (0, -9, 9, -5)),
         ('n', 'Upper shoulder', (0, -10, 9, -5))]


def main():
    paths = [OUT / 'report.json', OUT.parent / 'paper-source-aware/roboto.json',
             OUT.parent / 'paper-curves/roboto.json']
    documents = [json.loads(p.read_text()) for p in paths]
    image = Image.new('RGB', (860, 75 + len(CASES) * 230), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((12, 10), 'Roboto 16px / recorded variants / 7x pixels. Blue boxes mark the region under discussion.', fill='black')
    draw.text((12, 28), 'Our pipeline = source-aware stage. Our curve fit = subsequent curved-width experiment.', fill='black')
    draw.text((12, 46), 'Earlier variants retain their original scan settings; Hobby/Shamir use common dropout-off MONO.', fill='#555555')
    manifest = []
    for row, (char, reason, region) in enumerate(CASES):
        current = next(r for r in documents[0]['records'] if r['font']=='roboto' and r['size']==16 and r['char']==char)
        old = [next(r for r in d['records'] if r['size']==16 and r['char']==char) for d in documents[1:]]
        source_sha = documents[0]['inputs']['roboto']['font_sha256']
        if any(d['font_sha256'] != source_sha for d in documents[1:]):
            raise ValueError('font source mismatch')
        if any(r['axes'] != current['axes'] for r in old):
            raise ValueError('variation axes mismatch')
        y = 75 + row * 230
        draw.text((12, y), f'{row+1}. {char} / {reason}', fill='black')
        columns = [('Source outline', current['reference'], 1),
                   ('Our pipeline', old[0]['glyph'], 7), ('Our curve fit', old[1]['glyph'], 7),
                   ('A: Hobby subset', current['hobby'], 7), ('B: Shamir subset', current['shamir'], 7)]
        for col, (label, glyph, scale) in enumerate(columns):
            left, baseline = 18 + col * 170, y + 178
            draw.text((left, y+23), label, fill='black')
            check_bounds(glyph, left, baseline, scale, (left-12,y+42,left+153,y+213))
            draw_glyph(draw, glyph, left, baseline, scale)
            x0,y0,x1,y1 = region
            draw.rectangle((left+x0*7-2,baseline+y0*7-2,left+x1*7+1,baseline+y1*7+1),outline='#6291b8',width=1)
            if scale == 7:
                draw_glyph(draw, glyph, left+108, baseline, 1)
        draw.line((12,y+222,848,y+222),fill='#dddddd')
        manifest.append(dict(char=char,size=16,font='roboto',region=region,reason=reason))
    image.save(OUT / 'concerns-with-earlier-variants.png')
    (OUT / 'concerns-manifest.json').write_text(json.dumps(dict(
        inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cases=manifest,
        scope='Recorded visual comparison; earlier scan settings differ from prototype controls'),indent=2)+'\n')


if __name__ == '__main__':
    main()
