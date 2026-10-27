#!/usr/bin/env python3
"""Capture the five landing-page converters from one font instance.

Instancing: https://fonttools.readthedocs.io/en/latest/varLib/instancer.html
Adapters retain exported pixels/metrics; source kerning is disabled throughout.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).resolve().parent
ASSETS = ROOT / 'tools/web/src/app/features/landing/assets/rasterizers'
ASCII = ''.join(chr(c) for c in range(32, 127))
DEFAULT_TEXT = ('Pack my box with five dozen liquor jugs.\n'
                'The quick brown fox jumps over the lazy dog.\n'
                'Minimum effort, maximum clarity: AVATAR To Wa 0123456789.')
ADAFRUIT_REVISION = '978b9f83edb0a335dbd996753a4a865137f325db'
TOOLS = {
    'repo': ('Glypherie', 'https://github.com/ai212983/glypherie', 'Playdate'),
    'pdfontconv': ('pdfontconv', 'https://pdfontconv.frozenfractal.com/', 'Playdate'),
    'tophat': ('Tophat', 'https://kaasiand.cool/tophat/', 'Playdate'),
    'lvgl': ('LVGL Font Converter', 'https://github.com/lvgl/lv_font_conv', 'LVGL'),
    'adafruit': ('Adafruit Font Converter', 'https://github.com/adafruit/Adafruit-GFX-Library', 'Adafruit GFX'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def execute(args, directory, name):
    result = subprocess.run([str(a) for a in args], cwd=ROOT, capture_output=True)
    (directory / f'{name}.log').write_bytes(result.stdout + result.stderr)
    write_json(directory / f'{name}.command.json', {'argv': [str(a) for a in args], 'exit_code': result.returncode})
    if result.returncode:
        raise ValueError(f'{name} failed; see {directory / (name + ".log")}')
    return result.stdout


def fetch_pinned_font(url, digest, destination):
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('font_sha256 must be a 64-character lowercase hex digest')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=120) as response:
        data = response.read()
    if sha(data) != digest:
        raise ValueError(f'Downloaded font identity mismatch: {url}')
    destination.write_bytes(data)


def resolve_renderer_policy(case):
    """Resolve explicit overrides; absent/None values inherit the shared policy."""
    bridge = SCRIPT / 'preview-policy-bridge.ts'
    declared = {key: case[key] for key in ['fitting', 'rasterization', 'diagonal_fitting', 'dropout', 'include_stubs', 'font_instructions'] if case.get(key) is not None}
    try:
        completed = subprocess.run(['node', str(bridge)], input=json.dumps(declared), capture_output=True, text=True, cwd=ROOT)
    except OSError as error:
        raise ValueError(f'renderer policy bridge failed: {error}')
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or '').strip()
        raise ValueError(f'renderer policy rejected: {detail or "unknown bridge error"}')
    try:
        resolved = json.loads(completed.stdout)
        policy, fingerprint = resolved['policy'], resolved['fingerprint']
    except (ValueError, KeyError, TypeError):
        raise ValueError('renderer policy bridge returned invalid JSON')
    if not isinstance(policy, dict) or not isinstance(fingerprint, str) or not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
        raise ValueError('renderer policy bridge returned invalid policy or fingerprint')
    return declared, policy, fingerprint


# Include shared policy dependencies in the mid-capture source-change check.
SHARED_RENDERER_SOURCES = ['tools/web/src/app/renderer/preview-policy.ts', 'tools/web/scripts/policy-fingerprint.ts']


def source_state():
    paths = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', 'tools/generator', str(SCRIPT.relative_to(ROOT))], cwd=ROOT).decode().split('\0')
    state = {p: sha((ROOT / p).read_bytes()) for p in sorted(set(paths)) if p and (ROOT / p).is_file()}
    for extra in SHARED_RENDERER_SOURCES:
        state[extra] = sha((ROOT / extra).read_bytes())
    return state


def prepare_tools(cache):
    cache.mkdir(parents=True, exist_ok=True)
    lvgl = cache / 'lvgl/node_modules/.bin/lv_font_conv'
    if not lvgl.exists():
        execute(['npm', 'install', '--prefix', cache / 'lvgl', '--ignore-scripts', '--no-audit', '--no-fund', 'lv_font_conv@1.5.3'], cache, 'install-lvgl')
    directory = cache / 'adafruit'
    (directory / 'fontconvert').mkdir(parents=True, exist_ok=True)
    for name in ['fontconvert/fontconvert.c', 'gfxfont.h']:
        destination = directory / name
        if not destination.exists():
            url = f'https://raw.githubusercontent.com/adafruit/Adafruit-GFX-Library/{ADAFRUIT_REVISION}/{name}'
            with urlopen(url, timeout=60) as response:
                destination.write_bytes(response.read())
    source = (directory / 'fontconvert/fontconvert.c').read_text()
    original = 'FT_Set_Char_Size(face, size << 6, 0, DPI, 0);'
    if source.count(original) != 1:
        raise ValueError('Adafruit source no longer matches the exact-pixel-size adapter')
    # Upstream uses points at 141 DPI. This sole API substitution supplies the
    # same requested ppem as the other tools; glyph loading/packing is upstream.
    adapted = source.replace(original, 'FT_Set_Pixel_Sizes(face, 0, (FT_UInt)size);')
    (directory / 'fontconvert/fontconvert-px.c').write_text(adapted)
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'freetype2'], text=True))
    binary = directory / 'fontconvert-px'
    execute(['cc', '-include', 'stdlib.h', '-include', 'string.h', directory / 'fontconvert/fontconvert-px.c', '-o', binary, *flags], cache, 'build-adafruit')
    probe = directory / 'freetype-version.c'
    probe.write_text('#include <stdio.h>\n#include <ft2build.h>\n#include FT_FREETYPE_H\nint main(void) { FT_Library lib; FT_Int a,b,c; if (FT_Init_FreeType(&lib)) return 1; FT_Library_Version(lib,&a,&b,&c); printf("%d.%d.%d\\n",a,b,c); FT_Done_FreeType(lib); return 0; }\n')
    execute(['cc', probe, '-o', directory / 'freetype-version', *flags], cache, 'build-freetype-version')
    freetype_version = execute([directory / 'freetype-version'], cache, 'freetype-version').decode().strip()
    return lvgl, binary, {
        'lv_font_conv': '1.5.3',
        'lvgl_package_lock_sha256': sha((cache / 'lvgl/package-lock.json').read_bytes()),
        'adafruit_revision': ADAFRUIT_REVISION,
        'adafruit_source_sha256': sha(source.encode()),
        'adafruit_adapter_sha256': sha(adapted.encode()),
        'adafruit_adapter': 'FT_Set_Char_Size(points at 141 DPI) replaced with FT_Set_Pixel_Sizes(ppem); all other converter code unchanged.',
        'adafruit_freetype': freetype_version,
    }


def prepare_font(source, axes, destination):
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    font = TTFont(source, recalcTimestamp=False)
    available = {a.axisTag: a for a in font['fvar'].axes} if 'fvar' in font else {}
    if set(axes) - available.keys():
        raise ValueError(f'Unknown axes for {source.name}: {sorted(set(axes) - available.keys())}')
    resolved = {tag: axes.get(tag, a.defaultValue) for tag, a in available.items()}
    for tag, value in resolved.items():
        if not math.isfinite(value) or not available[tag].minValue <= value <= available[tag].maxValue:
            raise ValueError(f'Axis {tag}={value} is outside the font range')
    family = font['name'].getBestFamilyName() or source.stem
    if available:
        font = instantiateVariableFont(font, resolved, inplace=False)
        font.recalcTimestamp = False
        font.save(destination)
    else:
        shutil.copyfile(source, destination)
    if 'fvar' in font:
        raise ValueError('Instancing did not produce a static font')
    missing = [ch for ch in ASCII if ord(ch) not in font.getBestCmap()]
    if missing:
        raise ValueError(f'Comparison requires printable ASCII; missing {missing!r}')
    font.close()
    return family, resolved


def playdate_glyphs(directory, metadata=None):
    from PIL import Image
    text = (directory / 'font.fnt').read_text()
    properties, entries, pairs = {}, [], {}
    for line in text.splitlines():
        if not line or line.startswith('--'):
            continue
        if '=' in line and line.split('=', 1)[0] in {'data', 'datalen', 'width', 'height', 'tracking'}:
            key, value = line.split('=', 1)
            properties[key] = value
        else:
            key, value = line.rsplit(None, 1)
            if key == 'space':
                key = ' '
            elif re.fullmatch(r'U\+[0-9A-Fa-f]+', key):
                key = chr(int(key[2:], 16))
            if len(key) == 1:
                entries.append((key, int(value)))
            elif metadata is None:
                # Disabling source kerning still exports fitted pair corrections.
                # Preserve them; see tools/generator/API.md.
                pair = re.fullmatch(r'U\+([0-9A-Fa-f]+)U\+([0-9A-Fa-f]+)', key)
                if pair:
                    pairs[(chr(int(pair[1], 16)), chr(int(pair[2], 16)))] = int(value)
            # Hosted converter source-kerning entries are deliberately omitted.
    if 'data' in properties:
        atlas = Image.open(io.BytesIO(base64.b64decode(properties['data'], validate=True))).convert('RGBA')
        w, h = int(properties['width']), int(properties['height'])
    else:
        atlas = Image.open(directory / 'font.png').convert('RGBA')
        w, h = metadata['cell_width'], metadata['cell_height']
    baseline_match = re.search(r'^--metrics=(.+)$', text, re.M)
    baseline = json.loads(baseline_match[1])['baseline'] if baseline_match else metadata['baseline']
    inset_match = re.search(r'^--origin_x=(\d+)$', text, re.M)
    inset = int(inset_match[1]) if inset_match else (metadata or {}).get('offset_x', 0)
    if atlas.width % w or atlas.height % h or not entries or (metadata and len(entries) != 95):
        raise ValueError(f'{directory.name}: invalid atlas or repertoire')
    if any(a not in (0, 255) or (a and (r, g, b) != (0, 0, 0)) for r, g, b, a in atlas.getdata()):
        raise ValueError(f'{directory.name}: expected binary black/transparent glyphs')
    memory = json.loads((directory / 'memory.json').read_text()) if metadata else None
    result = {}
    for i, (ch, advance) in enumerate(entries):
        x, y = i % (atlas.width // w) * w, i // (atlas.width // w) * h
        image = atlas.crop((x, y, x + w, y + h)).getchannel('A')
        advance += int(properties.get('tracking', 0))
        if memory and (list(image.getdata()) != memory[ch]['alpha'] or advance != memory[ch]['advance']):
            raise ValueError(f'{directory.name}: export differs from browser glyph {ch!r}')
        result[ch] = (image, advance, -inset, -baseline)
    if (metadata and set(result) != set(ASCII)) or set(result) - set(ASCII):
        raise ValueError(f'{directory.name}: missing exported characters')
    return result, pairs


def lvgl_glyphs(path):
    from PIL import Image
    info = json.loads(path.read_text())
    glyphs = {}
    for g in info['glyphs']:
        box = g['bbox']
        w, h = box['width'], box['height']
        pixels = [p for row in g['pixels'] for p in row]
        if set(pixels) - {0, 255}:
            raise ValueError('LVGL export is not binary')
        image = Image.new('L', (w, h))
        image.putdata(pixels)
        # LVGL v8/v9 uses 4 fractional advance bits and nearest pen rounding.
        # https://github.com/lvgl/lvgl/blob/master/src/font/lv_font_fmt_txt.c
        glyphs[chr(g['code'])] = (image, math.floor(g['advanceWidth'] * 16 + 0.5) / 16, box['x'], -(box['y'] + h))
    return glyphs


def adafruit_glyphs(path):
    from PIL import Image
    source = path.read_text()
    blob = source.split('Bitmaps[] PROGMEM = {')[1].split('};')[0]
    data = bytes(int(t, 16) for t in re.findall(r'0x([0-9A-Fa-f]{2})', blob))
    rows = re.findall(r'\{\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(-?\d+),\s*(-?\d+)\s*\}', source.split('Glyphs[] PROGMEM = {')[1])
    if len(rows) != 95:
        raise ValueError('Adafruit export does not contain printable ASCII')
    result = {}
    for ch, row in zip(ASCII, rows, strict=True):
        offset, w, h, advance, x, y = map(int, row)
        image = Image.new('L', (w, h))
        image.putdata([255 if data[offset + k // 8] & (128 >> (k % 8)) else 0 for k in range(w * h)])
        result[ch] = (image, advance, x, y)
    return result


def compose(glyphs, text, canvas, origin, baselines, pair_adjustments=None):
    from PIL import Image, ImageChops
    image = Image.new('L', canvas, 255)
    for line, baseline in zip(text.split('\n'), baselines, strict=True):
        pen = origin
        previous = None
        for ch in line:
            pen += (pair_adjustments or {}).get((previous, ch), 0)
            glyph, advance, left, top = glyphs[ch]
            x, y = math.floor(pen + 0.5) + left, baseline + top
            bounds = glyph.getbbox()
            if bounds and (x + bounds[0] < 0 or y + bounds[1] < 0 or x + bounds[2] > canvas[0] or y + bounds[3] > canvas[1]):
                raise ValueError(f'Canvas clips {ch!r}; increase --width or --line-step')
            # Composite ink only: transparent cell padding cannot erase overlaps.
            ink = Image.new('L', canvas)
            ink.paste(glyph, (x, y))
            image = ImageChops.darker(image, ImageChops.invert(ink))
            pen += advance
            previous = ch
    return image


def glypherie_request(text, size, policy):
    """Use native advances and fitted pairs without source kerning or extra tracking."""
    return {
        'config': {'size_px': size, 'axes': {}, 'hinting': policy['hinting'], 'output_bits': policy['output_bits'], 'mono_threshold': policy['mono_threshold'], 'gray_gamma': policy['gray_gamma'], 'characters': ''.join(sorted(set(text.replace('\n', '') + 'HIl'))), 'missing_glyphs': policy['missing_glyphs'], 'kerning': False, 'metric_rounding': policy['metric_rounding'], 'mono_raster': policy['mono_raster']},
        'pipeline': {'fitting': policy['fitting'], 'rasterization': policy['rasterization'], 'diagonal_fitting': policy['diagonal_fitting']},
        'letter_spacing_px': 0,
    }


def generate_case(case, directory, binaries, source_snapshot):
    from PIL import ImageChops
    directory.mkdir()
    for tool in TOOLS:
        (directory / tool).mkdir()
    font = directory / 'input.ttf'
    selected_axes, calibration = case['axes'], None
    if case.get('stem_target_px') is not None:
        from stems import calibrate
        selected_axes, calibration = calibrate(Path(case['font']), selected_axes, case['size_px'], case['stem_target_px'])
    family, axes = prepare_font(Path(case['font']), selected_axes, font)
    family = case.get('family_label') or family
    size, text = case['size_px'], case['text']
    line_step = case.get('line_step') or size * 3
    origin = max(16, size)
    baselines = [size * 3 + i * line_step for i in range(len(text.split('\n')))]
    canvas = (case.get('width', 2400), baselines[-1] + size * 3)
    inputs = dict(family=family, size_px=size, source_font=str(case['font']), source_font_sha256=sha(Path(case['font']).read_bytes()), font_sha256=sha(font.read_bytes()), source_axes=axes, text=text, text_sha256=sha(text.encode()), canvas=canvas, origin_x=origin, baselines_y=baselines, source_kerning=False, threshold=case['threshold'], spacing='Each converter retains native advances. Glypherie retains fitted pair corrections with source kerning disabled and neutral tracking.')
    inputs.update(family_id=case.get('family_id'), stem_calibration=calibration)
    write_json(directory / 'inputs.json', inputs)
    declared, policy, fingerprint = resolve_renderer_policy(case)
    request = glypherie_request(text, size, policy)
    write_json(directory / 'request.json', request)
    print(f"Generating {case['id']}: {family}, {size} px, {axes}", flush=True)
    execute(['node', SCRIPT / 'capture.mjs', directory, font, directory / 'inputs.json'], directory, 'browser-capture')
    browser = json.loads((directory / 'browser.json').read_text())
    if browser['font_sha256'] != inputs['font_sha256']:
        raise ValueError('Browser captured different font bytes')
    lvgl, adafruit, generator = binaries
    glyphs, pair_adjustments, verification = {}, {}, {}
    for repeat in ['font', 'repeat']:
        execute([generator, font, directory / 'request.json', directory / 'repo' / f'{repeat}.fnt'], directory, f'generate-{repeat}')
        execute([lvgl, '--font', font, '-r', '0x20-0x7E', '--size', size, '--format', 'dump', '--bpp', '1', '--no-kerning', '--full-info', '-o', directory / 'lvgl' / repeat], directory, f'lvgl-{repeat}')
        header = execute([adafruit, font, size], directory, f'adafruit-{repeat}')
        (directory / 'adafruit' / f'{repeat}.h').write_bytes(header)
    for tool, first, repeat in [('repo', 'font.fnt', 'repeat.fnt'), ('pdfontconv', 'font.fnt', 'repeat.fnt'), ('pdfontconv', 'font.png', 'repeat.png'), ('tophat', 'font.fnt', 'repeat.fnt'), ('lvgl', 'font/font_info.json', 'repeat/font_info.json'), ('adafruit', 'font.h', 'repeat.h')]:
        if (directory / tool / first).read_bytes() != (directory / tool / repeat).read_bytes():
            raise ValueError(f'{tool}: repeated exports differ')
    for tool in ['repo', 'pdfontconv', 'tophat']:
        glyphs[tool], pair_adjustments[tool] = playdate_glyphs(directory / tool, browser['samples'].get(tool))
    glyphs['lvgl'] = lvgl_glyphs(directory / 'lvgl/font/font_info.json')
    glyphs['adafruit'] = adafruit_glyphs(directory / 'adafruit/font.h')
    images = {tool: compose(data, text, canvas, origin, baselines, pair_adjustments.get(tool)) for tool, data in glyphs.items()}
    bounds = [ImageChops.invert(image).getbbox() for image in images.values()]
    if not all(bounds):
        raise ValueError('Samples contain no ink')
    crop = (max(0, min(b[0] for b in bounds) - 8), max(0, min(b[1] for b in bounds) - 8), min(canvas[0], max(b[2] for b in bounds) + 8), min(canvas[1], max(b[3] for b in bounds) + 8))
    crops = {tool: image.crop(crop) for tool, image in images.items()}
    rows = sorted({y for image in crops.values() for y in range(image.height) if image.crop((0, y, image.width, y + 1)).getextrema()[0] == 0})
    bands = []
    for y in rows:
        if bands and y == bands[-1]['top'] + bands[-1]['height']:
            bands[-1]['height'] += 1
        else:
            bands.append({'top': y, 'height': 1})
    samples = []
    for tool, (label, url, output) in TOOLS.items():
        image, display = images[tool], crops[tool]
        ink = image.histogram()[0]
        retained = sum(display.crop((0, band['top'], display.width, band['top'] + band['height'])).histogram()[0] for band in bands)
        if retained != ink:
            raise ValueError(f'{tool}: crop or line bands lost ink')
        image.save(directory / tool / 'paragraph.png')
        display.save(directory / f'{tool}.png')
        verification[tool] = {'repeat_exports_identical': True, 'all_ink_preserved': True, 'paragraph_ink_pixels': ink, 'matches_browser_memory': True if tool in browser['samples'] else None, 'applied_fitted_pair_count': len(pair_adjustments.get(tool, {}))}
        if calibration:
            from stems import native_widths
            verification[tool]['principal_stem_runs'] = native_widths(glyphs[tool], calibration)
        samples.append({'id': tool, 'label': label, 'source_url': url, 'output': output, 'file': f'{tool}.png', 'original': f'{tool}/paragraph.png', 'sha256': sha((directory / tool / 'paragraph.png').read_bytes()), 'display_sha256': sha((directory / f'{tool}.png').read_bytes()), 'capture': browser['samples'].get(tool), 'export_verification': verification[tool]})
    manifest = {'inputs': inputs, 'display_crop': crop, 'display_size': [crop[2] - crop[0], crop[3] - crop[1]], 'display_lines': bands, 'display_line_gap': 2, 'glypherie_pipeline': request['pipeline'], 'glypherie_scan': request['config']['mono_raster'], 'renderer_inputs': declared, 'renderer_policy': policy, 'renderer_fingerprint': fingerprint, 'samples': samples, 'source_snapshot_sha256': sha(json.dumps(source_snapshot, sort_keys=True).encode()), 'source_run': str(directory.relative_to(ROOT)) if directory.is_relative_to(ROOT) else str(directory), 'updated_at': datetime.now(timezone.utc).isoformat(), 'assessment': 'Pending optical assessment. Native converter output; no quality ranking.', 'browser': browser['browser'], 'platform': browser['platform'], 'source_files': browser['sources']}
    write_json(directory / 'capture.json', manifest)
    return manifest


def write_gallery(output, manifests):
    sections = []
    for case_id, manifest in manifests.items():
        inputs = manifest['inputs']
        title = html.escape(f"{inputs['family']} · {inputs['size_px']} px · {inputs['source_axes']}")
        cards = []
        for sample in manifest['samples']:
            lines = ''.join(f'<div style="height:{b["height"]}px"><img src="{case_id}/{sample["file"]}" style="top:-{b["top"]}px" alt=""></div>' for b in manifest['display_lines'])
            cards.append(f'<figure><figcaption>{html.escape(sample["label"])}</figcaption>{lines}</figure>')
        sections.append(f'<section><h2>{title}</h2><p>Pending optical assessment</p>{"".join(cards)}</section>')
    (output / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Front page samples</title><style>body{font:16px system-ui;margin:24px;background:#fafafa;color:#222}figure{margin:16px 0;padding:16px;border:1px solid #ccc;overflow:auto;background:white}figcaption{margin-bottom:12px}figure div{position:relative;overflow:hidden;margin-bottom:2px}img{position:relative;image-rendering:pixelated;max-width:none}section{margin-bottom:40px}</style><h1>Front page samples</h1>' + ''.join(sections) + '</html>')


def publish_case(directory, manifest, destination):
    # Validate the complete set before replacing any web assets.
    payloads = {}
    for sample in manifest['samples']:
        data = (directory / sample['file']).read_bytes()
        if sha(data) != sample['display_sha256']:
            raise ValueError(f'Publication checksum mismatch: {sample["id"]}')
        payloads[sample['id']] = data
    if set(payloads) != set(TOOLS):
        raise ValueError('Publication requires all five converters')
    for tool, data in payloads.items():
        (destination / f'{tool}.png').write_bytes(data)
    write_json(destination / 'capture.json', manifest)


def publish_matrix(output, manifests, destination):
    cases, families = [], {}
    for case_id, manifest in manifests.items():
        inputs = manifest['inputs']
        family = inputs['family_id']
        if not family:
            raise ValueError('Matrix publication requires a family_id on every case')
        families[family] = inputs['family']
        identity = sha(''.join(sample['display_sha256'] for sample in manifest['samples']).encode())[:12]
        relative = f'samples/{case_id}-{identity}'
        target = destination / relative
        target.mkdir(parents=True, exist_ok=True)
        publish_case(output / case_id, manifest, target)
        cases.append({'id': case_id, 'family_id': family, 'family_label': inputs['family'], 'size_px': inputs['size_px'], 'axes': inputs['source_axes'], 'display_size': manifest['display_size'], 'display_lines': manifest['display_lines'], 'display_line_gap': manifest['display_line_gap'], 'samples': [{key: sample[key] for key in ['id', 'label', 'source_url']} | {'file': f'{relative}/{sample["file"]}'} for sample in manifest['samples']]})
    sizes = sorted({case['size_px'] for case in cases})
    pairs = {(case['family_id'], case['size_px']) for case in cases}
    if not cases or len(pairs) != len(cases):
        raise ValueError('Matrix publication requires unique family/size cases')
    matrix = {'families': [{'id': key, 'label': label} for key, label in families.items()], 'sizes': sizes, 'cases': cases}
    temporary = destination / 'matrix.json.tmp'
    write_json(temporary, matrix)
    temporary.replace(destination / 'matrix.json')


def arguments():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--font', type=Path, default=ROOT / 'fonts/Roboto.ttf')
    parser.add_argument('--size', type=int, action='append', help='Pixel size; repeat for a sweep (default: 16)')
    parser.add_argument('--axis', action='append', default=[], metavar='TAG=VALUE')
    parser.add_argument('--text', default=DEFAULT_TEXT, help='Sample text; LF separates lines')
    parser.add_argument('--text-file', type=Path)
    parser.add_argument('--threshold', type=int, default=128, help='Hosted converter alpha threshold, 1..254')
    # None distinguishes inherited policy from an explicit CLI override.
    parser.add_argument('--fitting', choices=['font_hints_auto', 'font_hints_first', 'source_relative', 'upstream_mono'], default=None)
    parser.add_argument('--rasterization', choices=['free_type_mono', 'free_type_mono_terminals'], default=None)
    parser.add_argument('--diagonal-fitting', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--dropout', choices=['smart', 'simple', 'off'], default=None)
    parser.add_argument('--include-stubs', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--font-instructions', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--width', type=int, default=2400, help='Uncropped canvas width')
    parser.add_argument('--line-step', type=int, help='Baseline interval; default 3 × size')
    parser.add_argument('--config', type=Path, help='JSON array of cases; paths relative to this file')
    parser.add_argument('--stem-target-px', type=float, help='Choose a global weight coordinate from source stem geometry')
    parser.add_argument('--output', type=Path, help='New output directory; never overwrites a run')
    parser.add_argument('--cache', type=Path, default=ROOT / 'out/diagnostics/landing-samples/_tools')
    publication = parser.add_mutually_exclusive_group()
    publication.add_argument('--publish', action='store_true', help='Replace the legacy single-case assets after one complete, verified case')
    publication.add_argument('--publish-matrix', action='store_true', help='Replace the front page family/size matrix after all cases pass')
    return parser.parse_args()


def cases_from(args):
    axes = {}
    for item in args.axis:
        tag, value = item.split('=', 1)
        if tag in axes:
            raise ValueError(f'Duplicate axis {tag}')
        axes[tag] = float(value)
    defaults = {key: getattr(args, key) for key in ['threshold', 'fitting', 'rasterization', 'diagonal_fitting', 'dropout', 'include_stubs', 'font_instructions', 'width', 'line_step']}
    defaults.update(font=str(args.font.resolve()), axes=axes, text=args.text_file.read_text() if args.text_file else args.text, stem_target_px=args.stem_target_px, family_id=None, family_label=None, font_url=None, font_sha256=None)
    entries = json.loads(args.config.read_text()) if args.config else [{'id': f'size-{size}', 'size_px': size} for size in (args.size or [16])]
    if not isinstance(entries, list) or not entries:
        raise ValueError('Config must be a nonempty array of cases')
    cases, ids = [], set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - (set(defaults) | {'id', 'size_px'}):
            raise ValueError('Case contains unknown settings')
        case = {**defaults, **entry}
        if 'id' not in case or not isinstance(case['id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', case['id']) or case['id'] in ids:
            raise ValueError('Every case needs a unique safe id')
        ids.add(case['id'])
        source = Path(case['font'])
        case['font'] = str(((args.config.resolve().parent / source) if args.config and not source.is_absolute() else source).resolve())
        font_path, font_url, font_digest = Path(case['font']), case.get('font_url'), case.get('font_sha256')
        if font_url is not None and (not isinstance(font_url, str) or not font_url.startswith(('https://', 'http://'))):
            raise ValueError('font_url must be an http(s) URL')
        if font_digest is not None and (not isinstance(font_digest, str) or not re.fullmatch(r'[0-9a-f]{64}', font_digest)):
            raise ValueError('font_sha256 must be a 64-character lowercase hex digest')
        if font_url is None and font_digest is None:
            if not font_path.is_file():
                raise ValueError(f'Font not found: {case["font"]}')
        else:
            if font_url is not None and font_digest is None:
                raise ValueError('font_url requires a pinned font_sha256')
            if font_path.is_file() and font_digest is not None and sha(font_path.read_bytes()) == font_digest:
                pass
            elif font_url is None:
                raise ValueError(f'Font identity mismatch: {case["font"]}')
            else:
                fetch_pinned_font(font_url, font_digest, font_path)
        if type(case.get('size_px')) is not int or not 4 <= case['size_px'] <= 96:
            raise ValueError('size_px must be an integer in 4..96')
        if type(case['threshold']) is not int or not 1 <= case['threshold'] <= 254:
            raise ValueError('threshold must be an integer in 1..254')
        if not isinstance(case['text'], str) or not case['text'].strip() or len(case['text']) > 8192 or any(ch not in ASCII + '\n' for ch in case['text']):
            raise ValueError('Text must contain printable ASCII and LF only, with visible text and at most 8192 characters')
        if not isinstance(case['axes'], dict) or any(not isinstance(k, str) or len(k) != 4 or type(v) not in (int, float) or not math.isfinite(v) for k, v in case['axes'].items()):
            raise ValueError('axes must map four-character tags to finite numbers')
        if case['stem_target_px'] is not None and (type(case['stem_target_px']) not in (int, float) or not 0.5 <= case['stem_target_px'] <= 4):
            raise ValueError('stem_target_px must be in 0.5..4')
        if case['family_id'] is not None and (not isinstance(case['family_id'], str) or not re.fullmatch(r'[a-z0-9-]+', case['family_id'])):
            raise ValueError('family_id must be a safe lowercase identifier')
        if case['family_label'] is not None and (not isinstance(case['family_label'], str) or not case['family_label'].strip()):
            raise ValueError('family_label must be a nonempty string')
        if type(case['width']) is not int or not 64 <= case['width'] <= 16384 or (case['line_step'] is not None and (type(case['line_step']) is not int or not 1 <= case['line_step'] <= 1024)):
            raise ValueError('width must be 64..16384; line_step must be 1..1024')
        canvas_height = case['size_px'] * 6 + (len(case['text'].split('\n')) - 1) * (case['line_step'] or case['size_px'] * 3)
        if canvas_height * case['width'] > 16_777_216:
            raise ValueError('Uncropped canvas exceeds 16,777,216 pixels; reduce text, size, width or line_step')
        # Validate the effective combination before building tools or capturing.
        for key in ['diagonal_fitting', 'include_stubs', 'font_instructions']:
            if case[key] is not None and type(case[key]) is not bool:
                raise ValueError(f'{key} must be boolean')
        if (case['fitting'] is not None and case['fitting'] not in ['font_hints_auto', 'font_hints_first', 'source_relative', 'upstream_mono']) or (case['rasterization'] is not None and case['rasterization'] not in ['free_type_mono', 'free_type_mono_terminals']) or (case['dropout'] is not None and case['dropout'] not in ['smart', 'simple', 'off']):
            raise ValueError('Invalid Glypherie pipeline or scan settings')
        resolve_renderer_policy(case)
        cases.append(case)
    if args.publish and len(cases) != 1:
        raise ValueError('--publish requires exactly one case')
    return cases


def main():
    args = arguments()
    cases = cases_from(args)
    # Import after --help and argument validation so setup/errors stay usable.
    import fontTools
    import PIL
    output = (args.output or ROOT / 'out/diagnostics/landing-samples' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        write_json(output / 'cases.json', cases)
        before = source_state()
        write_json(output / 'source-snapshot.json', before)
        print('Preparing pinned converters and building Glypherie…', flush=True)
        lvgl, adafruit, versions = prepare_tools(args.cache.resolve())
        target = args.cache.resolve() / 'glypherie-target'
        execute(['cargo', 'build', '--locked', '--manifest-path', ROOT / 'tools/generator/Cargo.toml', '--bin', 'font_playdate', '--target-dir', target], output, 'build-glypherie')
        generator = target / 'debug/font_playdate'
        manifests = {case['id']: generate_case(case, output / case['id'], (lvgl, adafruit, generator), before) for case in cases}
        if before != source_state():
            raise ValueError('Generator source changed during capture; rerun against stable sources')
        versions.update(fonttools=fontTools.__version__, pillow=PIL.__version__, python=sys.version, node=subprocess.check_output(['node', '--version'], text=True).strip(), adapter_sources={p.name: sha(p.read_bytes()) for p in SCRIPT.iterdir() if p.suffix in ['.py', '.mjs', '.ts', '.txt']}, git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
        write_json(output / 'verification.json', {'complete': True, 'source_stable': True, 'versions': versions, 'cases': list(manifests)})
        write_gallery(output, manifests)
        if args.publish:
            manifest = next(iter(manifests.values()))
            case_dir = output / cases[0]['id']
            publish_case(case_dir, manifest, ASSETS)
        if args.publish_matrix:
            publish_matrix(output, manifests, ASSETS)
        print(f'Generated {len(cases)} case(s): {output / "index.html"}', flush=True)
        from urllib.parse import quote
        print(f'Preview with the dev server: http://localhost:8903/@fs{quote(str(output))}/index.html', flush=True)
    except Exception as error:
        write_json(output / 'failure.json', {'complete': False, 'error': str(error)})
        raise


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, ImportError) as error:
        sys.exit(f'landing-samples: {error}')
