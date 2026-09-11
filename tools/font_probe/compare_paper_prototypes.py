"""Independent Hobby/Shamir subset comparison with common outlines and scan flags.

This harness measures prototypes, not relative quality of the complete papers.
No raster corrections, phase search, candidate selection, or native-hint seed.
"""
import argparse
import hashlib
import json
import string
from pathlib import Path

import fontTools
import freetype as ft
import numpy as np
from PIL import Image, ImageDraw

from paper_gridfit import bitmap
from source_constraints import source_shape, assess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CHARS = string.ascii_uppercase + string.ascii_lowercase + string.digits
FLAGS = (ft.FT_OUTLINE_IGNORE_DROPOUTS | ft.FT_OUTLINE_SMART_DROPOUTS |
         ft.FT_OUTLINE_INCLUDE_STUBS | ft.FT_OUTLINE_SINGLE_PASS)
SOURCES = ('compare_paper_prototypes.py', 'hobby_prototype.py', 'shamir_prototype.py',
           'source_constraints.py', 'stem_gridfit.py', 'paper_gridfit.py', 'calibrate.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_outline(face, char, size):
    face.load_char(char, ft.FT_LOAD_NO_SCALE | ft.FT_LOAD_NO_HINTING | ft.FT_LOAD_NO_BITMAP)
    outline = face.glyph.outline
    return (np.asarray(outline.points, dtype=float).reshape(-1, 2) * size / face.units_per_EM,
            [t & 3 for t in outline.tags], list(outline.contours))


def render(face, char, size, points=None, hinted=False):
    face.set_pixel_sizes(0, size)
    flags = ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_TARGET_MONO
    flags |= (ft.FT_LOAD_PEDANTIC | ft.FT_LOAD_NO_AUTOHINT) if hinted else ft.FT_LOAD_NO_HINTING
    face.load_char(char, flags)
    outline = face.glyph.outline._FT_Outline
    if points is not None:
        if len(points) != outline.n_points:
            raise ValueError('outline point count changed')
        for i, (x, y) in enumerate(np.rint(points * 64).astype(int)):
            outline.points[i].x = int(x)
            outline.points[i].y = int(y)
    # A common scan converter, with dropout repair disabled for every method.
    outline.flags = (outline.flags & ~FLAGS) | ft.FT_OUTLINE_IGNORE_DROPOUTS
    return bitmap(face, char)


def pixels(glyph):
    return {(glyph['left'] + i % glyph['width'], glyph['top'] + i // glyph['width'])
            for i, value in enumerate(glyph['pixels']) if value}


def draw_glyph(draw, glyph, x, baseline, scale):
    if glyph is None:
        draw.text((x, baseline - 50), 'Unavailable: see report', fill='#aa2222')
        return
    for gx, gy in pixels(glyph):
        px, py = x + gx * scale, baseline + gy * scale
        draw.rectangle((px, py, px + scale - 1, py + scale - 1), fill='black')


def check_bounds(glyph, x, baseline, scale, bounds):
    if glyph is None:
        return
    points = pixels(glyph)
    if not points:
        return
    x0, y0, x1, y1 = bounds
    if any(not (x0 <= x + gx * scale and x + (gx + 1) * scale <= x1 and
                y0 <= baseline + gy * scale and baseline + (gy + 1) * scale <= y1)
           for gx, gy in points):
        raise ValueError('glyph would clip or overlap its review cell')


def review_sheet(records, out):
    requested = [('roboto', '6', 18), ('literata', 'g', 20),
                 ('roboto', '6', 16), ('literata', 'g', 18),
                 ('literata', 'E', 14), ('roboto', 'E', 16),
                 ('roboto', 'X', 16), ('literata', 'X', 16),
                 ('source-sans-3', 'X', 18), ('source-sans-3', 'g', 18)]
    index = {(r['font'], r['char'], r['size']): r for r in records}
    cases = [index[k] for k in requested if k in index]
    if not cases:
        cases = records[:10]
    image = Image.new('RGB', (1280, 45 + 245 * ((len(cases) + 1) // 2)), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((12, 10), 'Common MONO, dropout off. A/B are experimental subsets; source is a shape reference.', fill='black')
    for i, record in enumerate(cases):
        x, y = (i % 2) * 640, 45 + (i // 2) * 245
        draw.text((x + 12, y), f"{i + 1}. {record['font']} {record['size']}px / {record['char']}", fill='black')
        for col, (label, key, scale) in enumerate([
                ('Source outline', 'reference', 1), ('Unhinted', 'unhinted', 7),
                ('A: Hobby subset', 'hobby', 7), ('B: Shamir subset', 'shamir', 7)]):
            left = x + 12 + col * 158
            draw.text((left, y + 22), label, fill='black')
            check_bounds(record.get(key), left, y + 180, scale,
                         (left - 10, y + 36, left + 148, y + 232))
            draw_glyph(draw, record.get(key), left, y + 180, scale)
        draw.line((x + 8, y + 237, x + 632, y + 237), fill='#dddddd')
    image.save(out / 'comparison.png')
    return [{k: r[k] for k in ('font', 'char', 'size')} for r in cases]


def group_sheet(records, name, out):
    chars = 'bhmnpdqX'; index = {(r['size'], r['char']): r for r in records}
    sizes = [s for s in (16, 18) if any(r['size'] == s for r in records)]
    image = Image.new('RGB', (1140, 35 + 180 * 3 * len(sizes)), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((12, 8), f'{name}: shared scan conversion / 7x enlargement', fill='black')
    for row, (size, key, label) in enumerate((s, k, label) for s in sizes for k, label in
                [('unhinted', 'Unhinted'), ('hobby', 'A: Hobby subset'), ('shamir', 'B: Shamir subset')]):
        y = 35 + row * 180
        draw.text((12, y), f'{size}px / {label}', fill='black')
        for col, char in enumerate(chars):
            r = index.get((size, char))
            if r:
                x = 12 + col * 140
                check_bounds(r.get(key), x, y + 140, 7, (x - 10, y + 18, x + 130, y + 178))
                draw_glyph(draw, r.get(key), x, y + 140, 7)
    image.save(out / f'{name}-joins.png')


def native_sheet(records, name, out):
    """Whole repertoire in actual bitmap pixels, plus exact inverse pixels."""
    sizes = sorted({r['size'] for r in records})
    image = Image.new('RGB', (1100, 45 + len(sizes) * 170), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((12, 10), f'{name}: native-size glyph strips, fixed cells (spacing is not evaluated)', fill='black')
    for row, size in enumerate(sizes):
        rs = [r for r in records if r['size'] == size]
        for method, key in enumerate(('unhinted', 'hobby', 'shamir')):
            y = 45 + row * 170 + method * 54
            draw.text((12, y), f'{size}px {key}', fill='black')
            # 31 fixed cells per line leave each source advance out of this shape test.
            for j, r in enumerate(rs):
                x, baseline = 150 + (j % 31) * 30, y + 18 + (j // 31) * 24
                draw_glyph(draw, r.get(key), x, baseline, 1)
    image.save(out / f'{name}-native.png')
    Image.fromarray(255 - np.asarray(image)).save(out / f'{name}-inverse.png')


def main():
    source_hashes = {name: digest(HERE / name) for name in SOURCES}
    from hobby_prototype import fit, measure, aggregate_measurements
    from shamir_prototype import build_font
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=Path, nargs='+', default=[
        ROOT / f'tools/font_generator/examples/{name}.json'
        for name in ('roboto', 'literata', 'source-sans-3')])
    parser.add_argument('--sizes', type=int, nargs='+', default=[14, 16, 18, 20])
    parser.add_argument('--chars', default=CHARS)
    parser.add_argument('--out', type=Path, default=HERE / 'out/paper-prototypes')
    args = parser.parse_args(); out = args.out.resolve()
    out.relative_to(ROOT)  # Artifact paths in evidence remain repository-relative.
    if any(s <= 0 for s in args.sizes) or not args.chars:
        parser.error('positive sizes and at least one character required')
    out.mkdir(parents=True, exist_ok=True)
    records = []; builds = []; inputs = {}; measurements = {}
    for jobpath in args.jobs:
        jobpath = jobpath.resolve(); job = json.loads(jobpath.read_text())
        font = (jobpath.parent / job['font']).resolve(); name = jobpath.stem
        sha = digest(font)
        if sha != job['provenance']['expected_sha256']:
            raise ValueError(f'{name}: font checksum mismatch')
        inputs[name] = dict(font_sha256=sha, job_sha256=digest(jobpath))
        for size in args.sizes:
            face = ft.Face(str(font)); axes = dict(job['settings']['axes']); axes['wght'] = 400
            if face.has_multiple_masters:
                for axis in face.get_variation_info().axes:
                    if axis.tag == 'opsz': axes['opsz'] = min(axis.maximum, max(axis.minimum, size))
            generated = out / f'{name}-{size}-shamir.ttf'
            build = build_font(font, generated, size, axes, args.chars)
            builds.append(dict(font=name, size=size, diagnostics=build, font_sha256=digest(generated)))
            common = ft.Face(str(generated)); sampled = {}; widths = []
            for char in args.chars:
                if not common.get_char_index(ord(char)):
                    raise ValueError(f'{name}: missing character {char!r}')
                source, tags, ends = raw_outline(common, char, size)
                sampled[char] = source, tags, ends
                widths.extend(measure(source, tags, ends, size))
            table = aggregate_measurements(widths)
            measurements[f'{name}-{size}'] = table
            for char in args.chars:
                source, tags, ends = sampled[char]
                r = dict(font=name, char=char, size=size, axes=axes,
                         diagnostics={'shamir': build['records'][char]})
                shape = source_shape(source, tags, ends, size)
                r['reference'] = render(common, char, size * 7)
                for key in ('unhinted', 'hobby', 'shamir'):
                    try:
                        points = None
                        if key == 'hobby':
                            points, r['diagnostics'][key] = fit(source, tags, ends, size, table)
                        glyph = render(common, char, size, points, hinted=key == 'shamir')
                        r[key] = glyph
                        if shape is not None:
                            r.setdefault('structure', {})[key] = assess(shape, glyph)
                    except Exception as error:
                        r.setdefault('errors', {})[key] = f'{type(error).__name__}: {error}'
                if r.get('hobby') and r.get('shamir'):
                    r['different_pixels_ab'] = len(pixels(r['hobby']) ^ pixels(r['shamir']))
                records.append(r)
            print(json.dumps(dict(font=name, size=size, cases=len(args.chars),
                                  errors=sum(bool(r.get('errors')) for r in records if r['font']==name and r['size']==size))), flush=True)
    selected = review_sheet(records, out)
    for name in inputs:
        subset = [r for r in records if r['font'] == name]
        group_sheet(subset, name, out); native_sheet(subset, name, out)
    summary = dict(cases=len(records), errors=sum(bool(r.get('errors')) for r in records),
                   differing_ab=sum(bool(r.get('different_pixels_ab')) for r in records),
                   nonconverged_hobby=sum(not r.get('diagnostics', {}).get('hobby', {}).get('converged', False)
                                         for r in records),
                   advance_differences_ab=sum(r.get('hobby', {}).get('advance_26_6') !=
                                             r.get('shamir', {}).get('advance_26_6') for r in records),
                   structural_flags={key: sum(bool(r.get('structure', {}).get(key, {}).get('defect_count'))
                                              for r in records) for key in ('unhinted', 'hobby', 'shamir')})
    if source_hashes != {name: digest(HERE / name) for name in SOURCES}:
        raise RuntimeError('Prototype source changed during run; regenerate evidence')
    evidence = dict(scope='Independent experimental subsets; not complete-paper quality comparison.',
                    scan_conversion='FreeType MONO; dropout disabled uniformly; no raster repairs or selection',
                    common_source='Same per-size instantiated TrueType outlines loaded with NO_HINTING',
                    versions=dict(freetype=ft.version(), numpy=np.__version__, fonttools=fontTools.__version__),
                    source_hashes=source_hashes,
                    inputs=inputs, measurements=measurements, builds=builds, review_cases=selected,
                    summary=summary, records=records)
    (out / 'report.json').write_text(json.dumps(evidence, indent=2, allow_nan=False) + '\n')
    print(json.dumps(summary), flush=True)
    if summary['errors']:
        raise SystemExit('Prototype errors recorded; inspect report.json')


if __name__ == '__main__':
    main()
