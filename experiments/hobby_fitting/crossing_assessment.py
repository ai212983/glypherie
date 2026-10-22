"""Inspect source contrast and delivered crossing balance without fitting changes."""

# cspell:words Roboto fontTools Cmap instancer

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.hobby_fitting import direct_diagonal_run as run, intervals, text_review

FRACTIONS = (0.125, 0.25, 0.75, 0.875)


def segments(commands):
    pen = start = None
    for c in commands:
        op = c['op']
        if op == 'move_to':
            pen = start = (c['x'], c['y'])
        elif op in ('line_to', 'quad_to'):
            end = (c['x'], c['y'])
            yield (pen, end) if op == 'line_to' else (pen, (c['x1'], c['y1']), end)
            pen = end
        elif op == 'close':
            if pen != start:
                yield pen, start
            pen = start
        else:
            raise ValueError('unsupported command for analytic section: ' + op)


def roots(a, b, c):
    if a == 0:
        return [] if b == 0 else [-c / b]
    disc = b * b - 4 * a * c
    if disc < 0:
        return []
    if disc == 0:
        return [-b / (2 * a)]
    q = -0.5 * (b + math.copysign(math.sqrt(disc), b))
    return [q / a, c / q]


def section(commands, y):
    events = []
    for pts in segments(commands):
        if len(pts) == 2:
            p, q = pts
            if not min(p[1], q[1]) <= y < max(p[1], q[1]):
                continue
            t = (y-p[1])/(q[1]-p[1])
            events.append((p[0]+t*(q[0]-p[0]), 1 if q[1] > p[1] else -1))
            continue
        else:
            p, q, r = pts
            a, b = p[1]-2*q[1]+r[1], 2*(q[1]-p[1])
            cuts = [0., 1.]
            if a and 0 < -b/(2*a) < 1:
                cuts.insert(1, -b/(2*a))
            ts = roots(a, b, p[1]-y)
            for lo, hi in zip(cuts, cuts[1:]):
                ylo, yhi = [a*t*t+b*t+p[1] for t in (lo, hi)]
                if not min(ylo, yhi) <= y < max(ylo, yhi):
                    continue
                candidates = [t for t in ts if lo-1e-12 <= t <= hi+1e-12]
                if len(candidates) != 1:
                    raise ValueError('uncertain quadratic intersection')
                t = min(hi, max(lo, candidates[0]))
                x = (1 - t)**2 * p[0] + 2 * t * (1 - t) * q[0] + t*t*r[0]
                events.append((x, 1 if yhi > ylo else -1))
    winding, start, spans = 0, None, []
    for x, sign in sorted(events):
        previous = winding
        winding += sign
        if not previous and winding:
            start = x
        elif previous and not winding:
            spans.append([start, x])
    if winding:
        raise ValueError('unclosed section winding')
    return [span for span in spans if span[1] > span[0]]


def y_bounds(commands):
    values = []
    for pts in segments(commands):
        values.extend((pts[0][1], pts[-1][1]))
        if len(pts) == 3:
            p, q, r = [p[1] for p in pts]
            a = p - 2 * q + r
            if a:
                t = (p - q) / a
                if 0 < t < 1:
                    values.append((1-t)**2*p + 2*t*(1-t)*q + t*t*r)
    return min(values), max(values)


def describe(spans):
    result = dict(spans=spans)
    if len(spans) == 2:
        left, right = spans
        a, b = left[1] - left[0], right[1] - right[0]
        result.update(left_width=a, right_width=b, ratio=a/b,
                      gap=right[0]-left[1], midpoint=(left[0]+right[1])/2)
    return result


def profiles(commands, tile=None):
    lo, hi = y_bounds(commands)
    rows = []
    for fraction in FRACTIONS:
        y = lo + fraction * (hi - lo)
        row = dict(fraction=fraction, y=y, geometry=describe(section(commands, y)))
        if tile is not None:
            index = math.floor(-y - tile['top'])
            if not 0 <= index < tile['height']:
                raise ValueError('profile row outside raster frame')
            spans, start = [], None
            pixels = tile['pixels'][index*tile['width']:(index+1)*tile['width']]
            for i, value in enumerate(pixels + [0]):
                if value and start is None:
                    start = i
                elif not value and start is not None:
                    spans.append([tile['left']+start, tile['left']+i])
                    start = None
            row['raster'] = dict(describe(spans), y=-(tile['top']+index+0.5), row=index)
        rows.append(row)
    return rows


def raw_commands(font, char, size):
    from fontTools.pens.basePen import BasePen

    class Recorder(BasePen):
        def __init__(self):
            super().__init__(None)
            self.commands = []

        def point(self, point):
            return dict(x=point[0]*size/font['head'].unitsPerEm,
                        y=point[1]*size/font['head'].unitsPerEm)

        def _moveTo(self, point):
            self.commands.append(dict(op='move_to', **self.point(point)))

        def _lineTo(self, point):
            self.commands.append(dict(op='line_to', **self.point(point)))

        def _qCurveToOne(self, control, end):
            p = self.point(control)
            self.commands.append(dict(op='quad_to', x1=p['x'], y1=p['y'], **self.point(end)))

        def _closePath(self):
            self.commands.append(dict(op='close'))

    pen = Recorder()
    font.getGlyphSet()[font.getBestCmap()[ord(char)]].draw(pen)
    return pen.commands


def pair_measurements(pairs, stages, raw):
    result = []
    for pair in pairs:
        entries = re.findall(r'[ab]\((\d+),(\d+),([\d.]+),([\d.]+)\)', pair['id'])
        if len(entries) != 2 or any(int(e[0]) != 0 for e in entries):
            raise ValueError('unsupported frozen pair identity')
        source_segments = list(segments(stages['source']['commands']))
        edges = [source_segments[int(e[1])] for e in entries]
        if any(len(e) != 2 for e in edges):
            raise ValueError('frozen straight pair references a curve')
        corridor = intervals.corridor(*edges)
        normal = corridor['u']
        feet = pair['feet'][0]
        fractions = [float(e[2]) + (float(e[3])-float(e[2]))*sum(feet[k])/2
                     for e, k in zip(entries, ('a', 'b'))]
        measured = {}
        for label, commands in [('raw_source', raw)] + [(k, s['commands']) for k, s in stages.items()]:
            parts = list(segments(commands))
            chosen = [parts[int(e[1])] for e in entries]
            points = [(edge[0][0]+t*(edge[1][0]-edge[0][0]),
                       edge[0][1]+t*(edge[1][1]-edge[0][1])) for edge, t in zip(chosen, fractions)]
            width = abs(sum((b-a)*n for a, b, n in zip(points[0], points[1], normal)))
            measured[label] = dict(width=width, contacts=points,
                                   angles=[math.degrees(math.atan2(abs(b[1]-a[1]), abs(b[0]-a[0])))
                                           for a, b in chosen])
        for stage, field in (('upstream', 'upstream_width'), ('width_only', 'candidate_width')):
            if not math.isclose(measured[stage]['width'], pair[field], rel_tol=1e-7, abs_tol=1e-7):
                raise ValueError('frozen source-normal measurement mismatch: ' + stage)
        result.append(dict(id=pair['id'], normal=normal, measurements=measured,
                           source_medial_diameter=pair['source_width'],
                           frozen_width_only=pair['candidate_width']))
    return result


def build(out):
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    import fontTools

    if out.exists():
        raise ValueError('output exists; preserve prior diagnostics')
    out.mkdir(parents=True)
    joint_root = ROOT / 'out/diagnostics/shape-balance-next/review'
    final_root = ROOT / 'out/diagnostics/attached-diagonal/review'
    binary = str(ROOT / run.DEFAULT_ADAPTER)
    hashes, compact, matrix = {}, [], []

    def digest(path):
        name = str(path.relative_to(ROOT))
        if name not in hashes:
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes[name]

    for family in ('SourceSans3', 'Roboto'):
        font_path = ROOT / 'fonts' / (family + '.ttf')
        font = TTFont(font_path)
        axes = {'wght': 400}
        if family == 'Roboto':
            axes['wdth'] = 100
        font = instantiateVariableFont(font, axes, inplace=False)
        digest(font_path)
        for size in (12, 14, 16, 20):
            capture_path = ROOT / 'out/diagnostics/direct-diagonal/text-review/ascii-captures' / f'{family}-400-{size}.json'
            capture = json.loads(capture_path.read_text())[0]
            digest(capture_path)
            for hint in ('selective_default', 'auto_default'):
                name = f'{family}-400-{size}-{hint}'
                prior_path, final_path = joint_root/name/'data.json', final_root/name/'data.json'
                prior, final = [json.loads(p.read_text()) for p in (prior_path, final_path)]
                for packet in (prior, final):
                    for path, sha in packet['provenance'].items():
                        if digest(ROOT/path) != sha:
                            raise ValueError('stale packet: ' + path)
                if prior['layout'] != final['layout']:
                    raise ValueError('layout mismatch')
                for p in (prior_path, final_path):
                    digest(p)
                records = {r['codepoint']: r for r in capture['modes'][hint]['records']}
                width_path = ROOT / 'out/diagnostics/direct-diagonal/coverage-review/cells' / f'{family}_{float(size)}_400_{hint}.json'
                width_packet = json.loads(width_path.read_text())
                digest(width_path)
                glyphs = []
                with tempfile.TemporaryDirectory() as scratch:
                    for char in 'xX':
                        code = ord(char)
                        p = next(g for g in prior['glyphs'] if g['codepoint'] == code)
                        g = next(g for g in final['glyphs'] if g['codepoint'] == code)
                        record = records[code]
                        assert g['source'] == p['source'] == record['source_commands']
                        assert g['old'] == p['new'] and g['preferred_commands'] == p['commands']
                        run.check_parity(binary, record, scratch)
                        raw = raw_commands(font, char, size)
                        assert [c['op'] for c in raw] == [c['op'] for c in g['source']]
                        delta = max(abs(c[k] - r[k]) for c, r in zip(g['source'], raw)
                                    for k in r if k != 'op')
                        stages = {}
                        for label, commands in [('source', g['source']), ('upstream', g['original_upstream_commands']),
                                                ('width_only', p['preferred_commands']), ('combined', g['commands'])]:
                            rendered = run.arm_pixels(binary, record, commands, scratch)
                            tile = {k: rendered[k] for k in ('left', 'top', 'width', 'height', 'pixels')}
                            if label in ('width_only', 'combined'):
                                assert tile == (p['old'] if label == 'width_only' else g['new'])
                            stages[label] = dict(commands=commands, tile=tile, profiles=profiles(commands, tile))
                        glyph = dict(char=char, raw_source=raw, raw_profiles=profiles(raw),
                                     source_rounding_max=delta, native_axes=g['native_axes'], stages=stages,
                                     joint_reason=p['result']['reason'], attached_reason=g['result']['reason'])
                        frozen = next(w for w in width_packet['glyphs'] if w['codepoint'] == code)['candidate']
                        assert frozen['candidate_commands'] == p['preferred_commands']
                        glyph['pairs'] = pair_measurements(frozen['pairs'], stages, raw)
                        glyph['attached_pairs'] = g['result'].get('pairs', [])
                        glyph['curvature'] = []
                        for i, (raw_seg, source_seg) in enumerate(zip(segments(raw), segments(g['source']))):
                            if len(raw_seg) != 3:
                                continue
                            def cross(pts):
                                a, b, c = pts
                                return (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
                            glyph['curvature'].append(dict(segment=i, raw_cross=cross(raw_seg),
                                                           captured_cross=cross(source_seg)))
                        glyphs.append(glyph)
                        compact.append(dict(case=name, char=char, source_rounding_max=delta,
                                            raw_profiles=glyph['raw_profiles'],
                                            stages={k: v['profiles'] for k, v in stages.items()},
                                            pairs=glyph['pairs'], attached_pairs=glyph['attached_pairs'],
                                            curvature=glyph['curvature'],
                                            joint_reason=glyph['joint_reason'], attached_reason=glyph['attached_reason']))
                baseline_tiles = {g['codepoint']: g['old'] for g in prior['glyphs']}
                final_tiles = {g['codepoint']: g['new'] for g in final['glyphs']}
                lines = [dict(text_review.compose_line_common(line, baseline_tiles, final_tiles), text=line['text'])
                         for i, line in enumerate(final['layout']['lines']) if i in (1, 3)]
                data = dict(family=family, size=size, hint=hint, weight=400, glyphs=glyphs, text_lines=lines,
                            layout=final['layout'], font_sha256=digest(font_path))
                (out/(name+'.json')).write_text(json.dumps(data))
                matrix.append(dict(family=family, size=size, hint=hint, file=name+'.json'))
    template = Path(__file__).with_suffix('.html')
    for p in (Path(__file__), template, Path(run.__file__), Path(text_review.__file__), Path(intervals.__file__), Path(binary)):
        digest(p)
    (out/'index.html').write_bytes(template.read_bytes())
    (out/'matrix.json').write_text(json.dumps(matrix))
    (out/'measurements.json').write_text(json.dumps(compact, indent=2))
    report = dict(cells=len(matrix), glyphs=len(compact), fonttools=fontTools.__version__,
                  fractions=FRACTIONS, exact_raster_replay=True, layout_identical=True, provenance=hashes)
    (out/'audit.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'provenance'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    build(parser.parse_args().out.resolve())
