"""Compare the compact inline font's evaluated outlines with its source font.

Usage: python test_browser_font.py FULL_PAGE_DIRECTORY INLINE_HTML [REPORT_JSON]
Requires requirements-inline.txt. This checks geometry, not antialiasing pixels.
"""
import sys,json,re,gzip,base64,struct,io,math
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen
# Read the compressed resource without running the table decoder.
root=Path(sys.argv[1])
html=Path(sys.argv[2]).read_text()
payload=re.search(r'<script id="spacing-data" type="application/octet-stream">(.*?)</script>',html,re.S).group(1)
raw=gzip.decompress(base64.b64decode(payload));n=struct.unpack('<I',raw[:4])[0];font=json.loads(raw[4:4+n])['page']['cases'][0]
reference=font['browserReference'];derived=TTFont(io.BytesIO(base64.b64decode(reference['dataUrl'].split(',')[1])))
full=json.loads((root/'page-data.json').read_text())['cases'][0]
capture=json.loads(Path(full['capturePath']).read_text())
assert reference['sourceSha256']==full['sourceSha256']
original=TTFont(capture['font_path'])
a=original.getGlyphSet(location=font['axes']);b=derived.getGlyphSet(location={k:v for k,v in font['axes'].items() if k not in reference['pinnedDefaultAxes']})
maximum=0;checked=0
for cp in font['codepoints']:
 x=original.getBestCmap()[cp];y=derived.getBestCmap()[cp]
 p=DecomposingRecordingPen(a);q=DecomposingRecordingPen(b);a[x].draw(p);b[y].draw(q)
 assert len(p.value)==len(q.value)
 for (cmd,points),(other,coords) in zip(p.value,q.value):
  assert cmd==other and len(points)==len(coords)
  for v,w in zip(points,coords):
   if v is None or w is None:assert v==w;continue
   for one,two in zip(v,w):
    maximum=max(maximum,abs(one-two));assert math.isclose(one,two,abs_tol=1e-9,rel_tol=0)
 assert math.isclose(a[x].width,b[y].width,abs_tol=1e-9,rel_tol=0)
 checked+=1
report=dict(status='passed',codepoints=checked,maximumCoordinateDifferenceDesignUnits=maximum,
            note='Equivalent source outlines and advances; browser antialiasing pixel identity is not asserted.')
if len(sys.argv)>3:Path(sys.argv[3]).write_text(json.dumps(report,indent=2)+'\n')
print(report)
