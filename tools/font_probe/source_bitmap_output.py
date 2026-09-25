"""Export/presentation boundary for the source-to-bitmap pipeline.

``build_source_bitmap.py`` owns fitting and the generation pipeline; this
module owns everything after the final render is verified: per-face
bitmap/metric JSON records, native-scale and enlarged PNG specimens, and
the per-glyph HTML panels that reference them. It takes coordinates,
bitmap dictionaries and metric tuples only: no character, font-family or
size exception tables.
"""

import json
import platform
from pathlib import Path

import freetype as ft
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
ENLARGE = 8
DEFAULT_ZOOM = 2


BASE_CSS = (
    'body{font:16px sans-serif;margin:24px}'
    '.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));'
    'gap:12px;margin-top:16px}'
    '.cell{border:1px solid #ccc;padding:8px;margin:0;text-align:center;'
    'font:12px sans-serif;overflow:hidden}'
    '.cell figcaption{margin-bottom:6px;word-break:break-all}'
    '.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}'
    '.dot-retained{background:#2a2}.dot-changed{background:#e80}'
    '#zoombar button{margin-right:6px}table{border-collapse:collapse;margin:12px 0}'
    'th,td{border:1px solid #ccc;padding:4px 10px;text-align:left;font-size:14px}'
    '.grid.dense{display:block}'
    '.grid.dense .cell{display:inline;margin:0 1px 0 0;border:none;padding:0}'
    '.grid.dense .cell-img{vertical-align:bottom}'
    '.grid.dense figcaption{display:none}'
    '.family{margin-top:24px}'
    '.toollink{color:#888;font-size:12px;margin-top:32px}'
)

GRID_JS = """\
<script>
function setZoom(z){document.querySelectorAll('.grid').forEach(function(g){
g.dataset.zoom=z;});
document.querySelectorAll('.cell-img').forEach(function(img){
var big=(z>2);
img.src=big?img.dataset.large:img.dataset.native;
var m=big?8:z;
img.style.width=(+img.dataset.w*m)+'px';img.style.height=(+img.dataset.h*m)+'px';});
document.querySelectorAll('#zoombar button[data-z]').forEach(function(b){
b.disabled=(+b.dataset.z===z);});}
function applyFilters(){var f=document.getElementById('facefilter').value;
var s=document.getElementById('statusfilter').value;
document.querySelectorAll('.cell').forEach(function(c){
c.style.display=((f==='all'||c.dataset.face===f)&&(s==='all'||c.dataset.status===s))?'':'none';});
document.querySelectorAll('.sizes').forEach(function(g){
var anyVisible=Array.prototype.some.call(g.querySelectorAll('.cell'),
function(c){return c.style.display!=='none';});
g.style.display=anyVisible?'':'none';});
document.querySelectorAll('.family').forEach(function(g){
var anyVisible=Array.prototype.some.call(g.querySelectorAll('.sizes'),
function(s){return s.style.display!=='none';});
g.style.display=anyVisible?'':'none';});}
function toggleText(){var on=document.querySelectorAll('.grid.dense').length===0;
document.querySelectorAll('.grid').forEach(function(g){
if(on){g.classList.add('dense');}else{g.classList.remove('dense');}});
document.getElementById('textview').textContent=on?'Grid view':'Text view';}
window.addEventListener('DOMContentLoaded',function(){setZoom(%d);});
</script>""" % DEFAULT_ZOOM


def repo_relative(path):
    """Reusable repo-relative display path for a generation input."""
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(resolved)


def environment():
    """Tool versions that produced an export (no local paths)."""
    import fontTools
    versions = {
        'python': platform.python_version(),
        'freetype': list(ft.version()),
        'fonttools': fontTools.__version__,
        'numpy': np.__version__,
        'pillow': Image.__version__,
    }
    return versions


def glyph_record(char, size, glyph, native_points, advance_hmtx):
    """One reviewable record from the exact final render of a glyph.

    ``glyph`` is the ``bitmap()`` dictionary from the exported font,
    ``native_points`` the verified native coordinates, ``advance_hmtx``
    the ``(advanceWidth, leftSideBearing)`` tuple from the exported font.
    """
    from compare_paper_prototypes import pixels
    ink = sorted(pixels(glyph))
    return {
        'char': char,
        'codepoint': glyph['codepoint'],
        'size': size,
        'width': glyph['width'],
        'height': glyph['height'],
        'left': glyph['left'],
        'top': glyph['top'],
        'advance_26_6': glyph['advance_26_6'],
        'advance_hmtx': list(advance_hmtx),
        'pixels': list(glyph['pixels']),
        'ink': [list(p) for p in ink],
        'native_points_px': np.asarray(native_points, float).tolist(),
    }


def write_face_json(output, key, size, records):
    """Write ``{key}-bitmap.json``; return its repo-relative display path."""
    path = Path(output) / f'{key}-bitmap.json'
    path.write_text(json.dumps(
        {'key': key, 'size': size, 'glyphs': records}, indent=1) + '\n')
    return path


def write_specimens(output, key, char, glyph):
    """Native-scale and nearest-neighbor enlarged PNGs for one glyph.

    Returns ``(native_name, large_name)`` relative to the output root.
    Blank (zero-area) renders get a 1x1 white placeholder so every
    admitted glyph stays reviewable.
    """
    code = f'u{ord(char):04x}'
    native_name = f'img/{key}-{code}-native.png'
    large_name = f'img/{key}-{code}-x{ENLARGE}.png'
    width, height = max(1, glyph['width']), max(1, glyph['height'])
    image = Image.new('1', (width, height), 1)
    for i, value in enumerate(glyph['pixels']):
        if value and glyph['width'] and glyph['height']:
            image.putpixel((i % glyph['width'], i // glyph['width']), 0)
    native = image.convert('L')
    native.save(Path(output) / native_name)
    native.resize((width * ENLARGE, height * ENLARGE),
                  Image.NEAREST).save(Path(output) / large_name)
    return native_name, large_name


def panel_html(key, char, status, delta, record, native_name, large_name):
    """Per-glyph HTML section with reviewable specimens and metrics."""
    import html as html_mod
    code = f'u{ord(char):04x}'
    return (
        f'<section id="{key}-{code}"><h2>{html_mod.escape(key)} '
        f'{html_mod.escape(char)}</h2>'
        f'<p>{status}; {delta} pixels from pre-recovery input. '
        f'advance {record["advance_hmtx"][0]}/{record["advance_26_6"]} '
        f'bearings ({record["left"]},{record["top"]}) '
        f'{record["width"]}x{record["height"]}.</p>'
        f'<img class="px" src="{native_name}" alt="{html_mod.escape(char)} native"> '
        f'<img class="px" src="{large_name}" alt="{html_mod.escape(char)} enlarged '
        f'x{ENLARGE}" width="{max(1, record["width"]) * ENLARGE}" '
        f'height="{max(1, record["height"]) * ENLARGE}"></section>')


def grid_page(cells):
    """All-glyph inspection grid with a 1x/2x/8x zoom toggle and filters.

    ``cells`` holds dicts with key/char/code/status/large/native/w/h.
    Each zoom shows exact pixels, never a resampled image: 1x/2x use the
    native PNG (2x upscaled with crisp pixels), 8x swaps in the enlarged
    PNG at natural size. The default zoom is 2x. Cells are grouped by
    font family and size; each cell links to its per-face detail
    section.
    """
    import html as html_mod
    faces = sorted({c['key'] for c in cells})
    families = {}
    for cell in cells:
        family, _, size = cell['key'].rpartition('-')
        families.setdefault(family, {}).setdefault(
            int(size), []).append(cell)
    sections = []
    for family in sorted(families):
        subs = []
        for size in sorted(families[family]):
            figures = []
            for cell in families[family][size]:
                key = html_mod.escape(cell['key'])
                char = html_mod.escape(cell['char'])
                status = html_mod.escape(cell['status'])
                figures.append(
                    f'<figure class="cell" data-face="{key}" '
                    f'data-status="{status}">'
                    f'<figcaption><span class="dot dot-{status}"></span>{char} '
                    f'<a href="{key}.html#{key}-{cell["code"]}">{key}</a>'
                    f'</figcaption>'
                    f'<img class="cell-img px" src="{cell["native"]}" '
                    f'alt="{char}" '
                    f'data-native="{cell["native"]}" '
                    f'data-large="{cell["large"]}" '
                    f'data-w="{max(1, cell["w"])}" data-h="{max(1, cell["h"])}" '
                    f'style="width:{max(1, cell["w"]) * DEFAULT_ZOOM}px;'
                    f'height:{max(1, cell["h"]) * DEFAULT_ZOOM}px;"></figure>')
            subs.append(
                f'<section class="sizes"><h3>{size}px</h3>'
                f'<div class="grid">{"".join(figures)}</div></section>')
        sections.append(
            f'<section class="family"><h2>{html_mod.escape(family)}</h2>'
            f'{"".join(subs)}</section>')
    face_options = ''.join(
        f'<option value="{html_mod.escape(f)}">{html_mod.escape(f)}</option>'
        for f in faces)
    return (
        '<!DOCTYPE html><meta charset="utf-8"><style>' + BASE_CSS + '</style>'
        '<h1>Specimen grid</h1>'
        '<p id="zoombar">Zoom: '
        '<button data-z="1" onclick="setZoom(1)">1x</button>'
        '<button data-z="2" onclick="setZoom(2)">2x</button>'
        '<button data-z="8" onclick="setZoom(8)">8x</button> '
        '<button id="textview" onclick="toggleText()">Text view</button></p>'
        f'<p>Face: <select id="facefilter" onchange="applyFilters()">'
        f'<option value="all">all</option>{face_options}</select> '
        f'Status: <select id="statusfilter" onchange="applyFilters()">'
        f'<option value="all">all</option><option value="retained">retained'
        f'</option><option value="changed">changed</option></select></p>'
        f'<p>Text view hides the captions and gaps so the grid reads as '
        f'typed text.</p>'
        f'{"".join(sections)}' + GRID_JS)


def rejected_at(stages):
    """First pipeline stage that rejected a case, in emission order."""
    for stage, value in (stages or {}).items():
        if value == 'rejected':
            return stage
    return 'unknown'


def human_reason(row):
    """One-line human reason for an excluded case."""
    if row.get('reason'):
        return str(row['reason'])
    return 'rejected at %s; downstream stages skipped' % rejected_at(
        row.get('stages'))


def reason_pattern(reason):
    """Group key for reasons: numeric values masked so one pattern with
    different measurements stays one group."""
    import re
    return re.sub(r'[\d.]+', '#', str(reason))


def diagnostics_page(failures):
    """Human-readable unresolved cases: grouped summary plus a table.

    ``failures`` holds the excluded case rows. Groups share a reason
    pattern (measurements masked); rows keep verbatim reasons. Raw
    machine detail stays in report.json, linked below.
    """
    import html as html_mod
    groups = {}
    for row in failures:
        groups.setdefault(reason_pattern(human_reason(row)), []).append(row)
    parts = ['<!DOCTYPE html><meta charset="utf-8"><style>' + BASE_CSS
             + '</style><h1>Unresolved cases</h1>'
             '<p>%d excluded glyphs in %d groups.</p>'
             % (len(failures), len(groups))]
    parts.append('<p class="toollink">Raw detail for tooling and tests: '
                 '<a href="report.json">report.json</a>.</p>')
    for pattern, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        parts.append('<h2>%s (%d)</h2>' % (html_mod.escape(pattern), len(rows))
                     + '<table><tr><th>face</th><th>size</th><th>char</th>'
                       '<th>rejected at</th><th>reason</th></tr>')
        for row in sorted(rows, key=lambda r: (r.get('key', ''),
                                               r.get('char', ''))):
            family, _, size = str(row.get('key', '')).rpartition('-')
            parts.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                         '<td>%s</td></tr>'
                         % (html_mod.escape(family), html_mod.escape(size),
                            html_mod.escape(str(row.get('char', ''))),
                            html_mod.escape(rejected_at(row.get('stages'))),
                            html_mod.escape(human_reason(row))))
        parts.append('</table>')
    return ''.join(parts)


def change_attribution(row):
    """Which recovery stages changed a glyph and by how many pixels."""
    stages = [s for s, v in (row.get('stages') or {}).items() if v == 'changed']
    return stages, int(row.get('changed_pixels', 0) or 0)


CHANGES_PURPOSE = (
    '<p>These glyphs are where a recovery stage deliberately altered pixels '
    'relative to the pre-recovery input: proposed improvements queued for '
    'approval, not defects. Approving keeps them as generated; rejecting one '
    'sends it back to the named stage. Each entry names the responsible '
    'stage and the pixel count.</p>')


def change_panel(key, char, status, delta, record, native_name, large_name,
                 stages):
    """Per-glyph panel plus recovery-stage attribution for the changes page."""
    import html as html_mod
    panel = panel_html(key, char, status, delta, record, native_name,
                       large_name)
    names = ', '.join(html_mod.escape(s) for s in stages) or 'unknown stage'
    return panel.replace('</section>',
                         f'<p>Changed by {names}; {int(delta)} pixels from '
                         f'pre-recovery input.</p></section>')


def changes_page(entries):
    """Proposed-changes page: purpose header plus attributed entries."""
    return ('<!DOCTYPE html><meta charset="utf-8"><style>' + BASE_CSS
            + '</style><h1>Proposed changes awaiting approval</h1>'
            + CHANGES_PURPOSE + ''.join(entries))


def index_page(face_rows, counts, pages):
    """Dashboard: per-face status table plus links to every view."""
    import html as html_mod
    parts = ['<!DOCTYPE html><meta charset="utf-8"><style>' + BASE_CSS
             + '</style><h1>Source-to-bitmap specimen</h1>'
             '<p>Admitted glyphs regenerate from source fonts and '
             'configuration. Unresolved cases are excluded from font '
             'character maps.</p>'
             '<p><a href="grid.html">Specimen grid</a> · '
             '<a href="changes.html">Proposed changes</a> · '
             '<a href="diagnostics.html">Unresolved cases</a></p>'
             '<table><tr><th>face</th><th>retained</th><th>changed</th>'
             '<th>excluded</th></tr>']
    for key, retained, changed, excluded in face_rows:
        parts.append('<tr><td><a href="%s.html">%s</a></td><td>%d</td><td>%d</td>'
                     '<td>%d</td></tr>'
                     % (html_mod.escape(key), html_mod.escape(key),
                        retained, changed, excluded))
    parts.append('</table><p>Total: %s.</p>'
                 % html_mod.escape(str(counts)))
    parts.append('<ul>' + ''.join(
        '<li><a href="%s.html">%s</a></li>' % (html_mod.escape(p),
                                              html_mod.escape(p))
        for p in pages) + '</ul>')
    parts.append('<p class="toollink">Raw data for tooling and tests, '
                 'not for human review: <a href="report.json">report.json'
                 '</a>.</p>')
    return ''.join(parts)


def check_face_agreement(face_json, ttf_path):
    """Re-render the exported TTF and compare every exported record.

    Returns a list of ``(char, problem)`` pairs; empty means the JSON
    agrees with the font it was exported from.
    """
    from audit_terminal_coverage import coords
    from compare_paper_prototypes import render
    data = json.loads(Path(face_json).read_text())
    size = data['size']
    problems = []
    face = ft.Face(str(ttf_path))
    with TTFont(str(ttf_path)) as font:
        cmap = font.getBestCmap()
        for char, record in data['glyphs'].items():
            fresh = render(ft.Face(str(ttf_path)), char, size, hinted=True)
            for field in ('codepoint', 'width', 'height', 'left', 'top',
                          'advance_26_6', 'pixels'):
                if fresh[field] != record[field]:
                    problems.append((char, f'{field} drift'))
            advance = list(font['hmtx'][cmap[ord(char)]])
            if advance != record['advance_hmtx']:
                problems.append((char, 'advance drift'))
            actual = coords(face, char, size)
            if np.max(abs(actual - np.asarray(record['native_points_px']))) > 1e-9:
                problems.append((char, 'native coordinate drift'))
    return problems
