"""Inspect captured pair metrics and show existing renderings; no new spacing model.

Bounds follow FreeType's advance/bearing distinction:
https://freetype.org/freetype2/docs/glyphs/glyphs-3.html
Bounding-box gaps and row gaps are measurements, not optical scores.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

from fontTools.pens.boundsPen import BoundsPen

ROOT = Path(__file__).resolve().parents[2]
PAIRS = ['ck', 'ic', 'or', 'co', 'ci', 'oo', 'nn', 'on', 'rn', 'ri']


def bounds(commands):
    pen = BoundsPen(None)
    for c in commands:
        op = c['op']
        if op == 'move_to':
            pen.moveTo((c['x'], c['y']))
        elif op == 'line_to':
            pen.lineTo((c['x'], c['y']))
        elif op == 'quad_to':
            pen.qCurveTo((c['x1'], c['y1']), (c['x'], c['y']))
        elif op == 'curve_to':
            pen.curveTo((c['x1'], c['y1']), (c['x2'], c['y2']), (c['x'], c['y']))
        elif op == 'close':
            pen.closePath()
        else:
            raise ValueError('Unknown outline command: ' + op)
    return pen.bounds


def points(record):
    return {(record['left'] + x, record['top'] + y)
            for y in range(record['height']) for x in range(record['width'])
            if record['pixels'][y * record['width'] + x]}


def indexes(capture):
    source = {chr(r['codepoint']): r for r in capture['source']['records']}
    fitted = {chr(r['codepoint']): r for r in capture['fitted']['records']}
    advances = {chr(r['codepoint']): r['advance_26_6'] / 64 for r in capture['finalized_advances']}
    pairs = {(chr(r['left']), chr(r['right'])): r['adjustment_26_6'] / 64 for r in capture['finalized_pairs']}
    kern = {(chr(r['left']), chr(r['right'])): r['adjustment_26_6'] / 64 for r in capture['source_kerning']['pairs']}
    return source, fitted, advances, pairs, kern


def measurements(capture):
    source, fitted, advances, pairs, kern = indexes(capture)
    output = []
    for a, b in PAIRS:
        if a not in source or b not in source:
            continue
        sa, sb = bounds(source[a]['fitted_commands']), bounds(source[b]['fitted_commands'])
        fa, fb = bounds(fitted[a]['fitted_commands']), bounds(fitted[b]['fitted_commands'])
        if not all([sa, sb, fa, fb]):
            continue
        source_step = source[a]['advance_26_6'] / 64 + kern.get((a, b), 0)
        fitted_step = advances[a] + pairs.get((a, b), 0)
        source_gap = source_step + sb[0] - sa[2]
        fitted_gap = fitted_step + fb[0] - fa[2]
        left, right = points(fitted[a]), points(fitted[b])
        ys = sorted({p[1] for p in left} & {p[1] for p in right})
        row_gaps = [{'y': y, 'blank_pixels': fitted_step + min(x for x, row in right if row == y)
                     - max(x for x, row in left if row == y) - 1} for y in ys]
        ldelta = fitted[a].get('side_bearing_deltas_26_6', [0, 0])
        rdelta = fitted[b].get('side_bearing_deltas_26_6', [0, 0])
        output.append(dict(pair=a + b, source_advance=source[a]['advance_26_6'] / 64,
                           source_kern=kern.get((a, b), 0), fitted_advance=advances[a],
                           residual_difference_26_6=ldelta[1] - rdelta[0],
                           finalized_pair=pairs.get((a, b), 0), source_origin_step=source_step,
                           fitted_origin_step=fitted_step, source_outline_gap=source_gap,
                           fitted_outline_gap=fitted_gap, outline_gap_change=fitted_gap-source_gap,
                           bitmap_blank_columns=fitted_step + min(x for x, _ in right)
                           - max(x for x, _ in left) - 1,
                           median_row_gap=statistics.median(r['blank_pixels'] for r in row_gaps),
                           row_gaps=row_gaps))
    return output


def verify_export(capture, landing):
    sys.path.insert(0, str(ROOT / 'apps/web/scripts/landing-samples'))
    import generate
    directory = landing / f'literata-{int(capture["settings"]["size_px"])}'
    if hashlib.sha256((directory / 'input.ttf').read_bytes()).hexdigest() != capture['fitted']['source_sha256']:
        raise ValueError('font identity mismatch')
    glyphs, pairs = generate.playdate_glyphs(directory / 'repo')
    _, fitted, advances, native_pairs, _ = indexes(capture)
    for ch, record in fitted.items():
        image, advance, left, top = glyphs[ch]
        exported = {(left + x, top + y) for y in range(image.height) for x in range(image.width) if image.getpixel((x, y))}
        if exported != points(record):
            raise ValueError(f'bitmap mismatch: {ch!r}')
        if advance != advances[ch]:
            raise ValueError(f'advance mismatch: {ch!r}')
    if pairs != native_pairs:
        raise ValueError('pair table mismatch')


def compact(capture, source=False):
    src, fit, advances, pairs, kern = indexes(capture)
    records = src if source else fit
    return dict(records={ch: {key: r[key] for key in ['left', 'top', 'width', 'height', 'pixels']} for ch, r in records.items()},
                advances={ch: r['advance_26_6'] / 64 for ch, r in src.items()} if source else advances,
                pairs={a + b: value for (a, b), value in (kern if source else pairs).items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--landing-root', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    captures = [json.loads(line) for line in args.captures.read_text().splitlines()]
    metrics, display, verified = [], {}, 0
    for capture in captures:
        size = str(int(capture['settings']['size_px']))
        pipeline = capture['pipeline']
        mode = 'current' if pipeline.get('diagonal_fitting') else pipeline['fitting']
        metrics.append(dict(size_px=int(size), mode=mode, pairs=measurements(capture)))
        modes = display.setdefault(size, {})
        modes[mode] = compact(capture)
        modes.setdefault('source', compact(capture, source=True))
        if mode == 'current' and args.landing_root:
            verify_export(capture, args.landing_root)
            verified += 1
    (args.out / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
    (args.out / 'verification.json').write_text(json.dumps({'captures': len(captures), 'exact_export_parity_cases': verified,
        'capture_sha256': hashlib.sha256(args.captures.read_bytes()).hexdigest(), 'optical_assessment': 'pending'}, indent=2) + '\n')
    template = (Path(__file__).with_name('review.html')).read_text()
    payload = json.dumps({'display': display, 'metrics': metrics}).replace('<', '\\u003c')
    parity = (f'Export parity was verified for {verified} current captures.'
              if verified else 'Export parity was not checked.')
    (args.out / 'index.html').write_text(template.replace('/*CAPTURE_DATA*/', payload)
                                      .replace('<!--EXPORT_PARITY-->', parity))
    print(f'{len(captures)} captures; {verified} cases exactly match published glyphs, advances and pairs. Optical assessment pending.')


if __name__ == '__main__':
    main()
