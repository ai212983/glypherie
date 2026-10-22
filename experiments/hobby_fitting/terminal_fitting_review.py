"""Replay terminal reference-height constraints against the frozen crossing candidate."""

# cspell:words Roboto fontTools instancer oncurve offcurve

import argparse
import concurrent.futures
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.hobby_fitting import curved_width, direct_diagonal as diagonal, direct_diagonal_run as run
from experiments.hobby_fitting.crossing_assessment import profiles
from experiments.hobby_fitting import shape_balance_review as checks, text_review
from experiments.hobby_fitting.real_outline import parse_commands


def load(path):
    return json.loads(path.read_text())


def topology(source, upstream, candidate):
    return curved_width._substitution_gate(source, upstream, candidate)


def raw_commands(font, glyph_id, size):
    from fontTools.pens.basePen import BasePen

    glyphs = font.getGlyphSet()

    class Recorder(BasePen):
        def __init__(self):
            super().__init__(glyphs)
            self.commands = []

        def point(self, point, suffix=''):
            return {'x'+suffix: point[0]*size/font['head'].unitsPerEm,
                    'y'+suffix: point[1]*size/font['head'].unitsPerEm}

        def _moveTo(self, point):
            self.commands.append(dict(op='move_to', **self.point(point)))

        def _lineTo(self, point):
            self.commands.append(dict(op='line_to', **self.point(point)))

        def _qCurveToOne(self, control, end):
            self.commands.append(dict(op='quad_to', **self.point(control,'1'), **self.point(end)))

        def _curveToOne(self, first, second, end):
            self.commands.append(dict(op='curve_to', **self.point(first,'1'),
                                     **self.point(second,'2'), **self.point(end)))

        def _closePath(self):
            self.commands.append(dict(op='close'))

    pen = Recorder()
    glyphs[font.getGlyphOrder()[glyph_id]].draw(pen)
    return pen.commands


def build_cell(args):
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    import fontTools
    import numpy
    import scipy
    from experiments.hobby_fitting import terminal_fitting

    name = f'{args.family}-{args.weight}-{args.size}-{args.hint}'
    prior_path = ROOT / 'out/diagnostics/curved-crossing/review-final' / name / 'data.json'
    capture_path = ROOT / 'out/diagnostics/direct-diagonal/text-review/ascii-captures' / f'{args.family}-{args.weight}-{args.size}.json'
    ref_path = ROOT / 'out/diagnostics/direct-diagonal/coverage-review/cells' / f'{args.family}_{float(args.size)}_{args.weight}_{args.hint}.json'
    prior, capture, reference = load(prior_path), load(capture_path)[0], load(ref_path)
    for path, sha in prior['provenance'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == sha, path
    assert prior['layout'] == reference['layout']
    font_path = ROOT / 'fonts' / f'{args.family}.ttf'
    font = instantiateVariableFont(TTFont(font_path), capture['axes'], inplace=False)
    records = {r['codepoint']: r for r in capture['modes'][args.hint]['records']}
    selected = set(map(ord, args.glyphs)) if args.glyphs else set(records)
    binary = str(ROOT / run.DEFAULT_ADAPTER)
    old_tiles, new_tiles, glyphs = {}, {}, []
    with tempfile.TemporaryDirectory() as scratch:
        for g in prior['glyphs']:
            code = g['codepoint']
            old_tiles[code] = new_tiles[code] = g['new']
            if code not in selected:
                continue
            record = records[code]
            raw = raw_commands(font, record['glyph_id'], args.size)
            source, upstream = record['source_commands'], record['fitted_commands']
            assert source == g['source']
            run.check_parity(binary, record, scratch)
            baseline = run.arm_pixels(binary, record, g['commands'], scratch)
            assert all(baseline[k] == g['new'][k] for k in ('left','top','width','height','pixels'))
            started = time.perf_counter()
            result = terminal_fitting.fit(raw, source, upstream, args.size, reference['reference'],
                                         tuple(g['native_axes']), topology_checker=topology)
            runtime_ms = 1000*(time.perf_counter()-started)
            assert isinstance(result, dict) and type(result['applied']) is bool
            if result['applied']:
                old_points = parse_commands(g['commands'])['oncurve']
                up_points = parse_commands(upstream)['oncurve']
                cap_vertices = {v for cap in result['caps'] for v in cap['vertices']}
                assert cap_vertices
                if all(old_points[v][1] == up_points[v][1] for v in cap_vertices):
                    result = dict(result, applied=False, candidate_commands=upstream,
                                  reason='terminal-heights-already-held')
            candidate = result['candidate_commands']
            assert checks.same_skeleton(upstream, candidate)
            assert all(checks.valid_command(c) for c in candidate)
            if result['applied']:
                assert checks.respects_pins(upstream, candidate, tuple(g['native_axes']))
                assert topology(raw, upstream, candidate)['ok']
                assert topology(source, upstream, candidate)['ok']
                parsed = parse_commands(raw)
                previous, fitted = [parse_commands(c) for c in (upstream, candidate)]
                points = parsed['oncurve'] + parsed['offcurve']
                new_points = fitted['oncurve'] + fitted['offcurve']
                old_points = previous['oncurve'] + previous['offcurve']
                movement = max((math.dist(a, b) for a, b in zip(old_points, new_points)), default=0)
                captured = parse_commands(source)
                portions, _, loops, flats = diagonal._split_visible(captured, canonical=True)
                source_pairs, _ = diagonal._recognize(portions, loops, ownership='interval')
                borders = diagonal._visible_borders(portions)
                limits = {}
                covered = set()
                expected = {p['id'] for p in result['pairs']}
                for pair in source_pairs:
                    if diagonal._upright_pairs([pair]):
                        continue
                    info, why = diagonal._prepare_pair(
                        pair, borders, loops, loops, flats, flats, previous['oncurve'], args.size,
                        exact_curves=diagonal._curve_controls(captured))
                    if why is not None or info['id'] not in expected:
                        continue
                    expected.remove(info['id'])
                    bound = min(info['src_widths'])/2 - diagonal.HEADROOM
                    for edge in (info['a'], info['b']):
                        for v in (edge['i0'], edge['i1']):
                            covered.add(v)
                            limits[v] = min(limits.get(v, float('inf')), bound + diagonal.HEADROOM)
                assert not expected, expected
                for v, (before, after) in enumerate(zip(old_points, new_points)):
                    if before != after:
                        assert v in covered, (code, v)
                        assert math.dist(before, after) <= limits[v] + 1e-12, (code, v, limits[v])
                for contour in previous['contours']:
                    if not contour or contour[-1][0] != 'line':
                        continue
                    first, duplicate, last = contour[0][-2], contour[-1][-2], contour[-1][-1]
                    if last == first and duplicate != first and old_points[duplicate] == old_points[first]:
                        assert new_points[duplicate] == new_points[first]
                for curve in curved_width.curves_of(parsed):
                    ids = curve['idx']
                    assert all(previous['offcurve'][i] == fitted['offcurve'][i] for i in range(len(previous['offcurve'])))
                    assert all(previous['oncurve'][v] == fitted['oncurve'][v] for v in (ids[0], ids[-1]))
                for v in {v for cap in result['caps'] for v in cap['vertices']}:
                    assert fitted['oncurve'][v][1] == previous['oncurve'][v][1]
                vertical = {v for contour in parsed['contours'] for s in contour if s[0]=='line'
                            and points[s[1]][0]==points[s[2]][0] and points[s[1]][1]!=points[s[2]][1]
                            for v in (s[1],s[2])}
                assert all(checks.f32_bits(previous['oncurve'][i][0]) == checks.f32_bits(fitted['oncurve'][i][0])
                           for i in vertical), (code, sorted((i, previous['oncurve'][i], fitted['oncurve'][i])
                                                            for i in vertical if previous['oncurve'][i][0] != fitted['oncurve'][i][0]))
            else:
                assert candidate == upstream
            delivered = candidate if result['applied'] else g['commands']
            raster = run.arm_pixels(binary, record, delivered, scratch)
            tile = {k:raster[k] for k in ('left','top','width','height','pixels')}
            new_tiles[code] = tile
            sections = None
            if result['applied']:
                sections = dict(raw_source=profiles(raw), automatic=profiles(upstream),
                                previous=profiles(g['commands'], g['new']),
                                experiment=profiles(delivered, tile))
            ink = lambda t: {(t['left']+i%t['width'],t['top']+i//t['width'])
                             for i,v in enumerate(t['pixels']) if v}
            glyphs.append(dict(char=chr(code), codepoint=code, source=source, raw_source=raw,
                               original_upstream_commands=upstream, preferred_commands=g['commands'],
                               commands=delivered, old=g['new'], new=tile, changed=ink(tile)!=ink(g['new']),
                               native_axes=g['native_axes'], result=result, sections=sections,
                               runtime_ms=runtime_ms))
    lines = [dict(text_review.compose_line_common(line, old_tiles, new_tiles), text=line['text'])
             for line in prior['layout']['lines']]
    folder = ROOT / 'experiments/hobby_fitting'
    dependencies = [prior_path,capture_path,ref_path,font_path,Path(binary),Path(__file__),
                    folder/'terminal_fitting_review.html',
                    ROOT/'out/diagnostics/direct-diagonal/exact-topology/bin/exact_topology']
    dependencies += [p for p in folder.glob('*.py')]
    provenance = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies}
    args.out.mkdir(parents=True, exist_ok=True)
    data = dict(family=args.family,size=args.size,weight=args.weight,hint=args.hint,model='terminal-reference-heights',
                glyphs=glyphs,probed=sorted(selected),lines=lines,layout=prior['layout'],provenance=provenance,
                runtime=dict(fonttools=fontTools.__version__,numpy=numpy.__version__,scipy=scipy.__version__))
    (args.out/'data.json').write_text(json.dumps(data))
    (args.out/'index.html').write_bytes((folder/'terminal_fitting_review.html').read_bytes())
    return dict(probed=len(glyphs),applied=sum(g['result']['applied'] for g in glyphs),
                changed=sum(g['changed'] for g in glyphs),runtime_ms=sum(g['runtime_ms'] for g in glyphs))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--family',choices=['Roboto','SourceSans3'],default='SourceSans3')
    parser.add_argument('--weight',type=int,default=400)
    parser.add_argument('--size',type=int,default=16)
    parser.add_argument('--hint',choices=['auto_default','selective_default'],default='selective_default')
    parser.add_argument('--glyphs',default='')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--matrix',action='store_true')
    parser.add_argument('--jobs',type=int,default=4,choices=range(1,9))
    args = parser.parse_args()
    if not args.matrix:
        print(json.dumps(build_cell(args)))
        return
    jobs = [(f,w,s,h) for f in ('Roboto','SourceSans3') for w in (300,400,700)
            for s in (12,14,16,18,20,24) for h in ('selective_default','auto_default')]
    def build(job):
        family,weight,size,hint = job
        name = f'{family}-{weight}-{size}-{hint}'
        cmd = [sys.executable,str(Path(__file__).resolve()),'--family',family,'--weight',str(weight),
               '--size',str(size),'--hint',hint,'--out',str(args.out/name)]
        if args.glyphs:
            cmd += ['--glyphs',args.glyphs]
        proc = subprocess.run(cmd,capture_output=True,text=True)
        if proc.returncode:
            raise RuntimeError(name+': '+proc.stdout+proc.stderr)
        return dict(family=family,weight=weight,size=size,hint=hint,directory=name,counts=json.loads(proc.stdout))
    args.out.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        cells = list(pool.map(build,jobs))
    (args.out/'matrix.json').write_text(json.dumps(cells))
    (args.out/'index.html').write_bytes((ROOT/'experiments/hobby_fitting/terminal_fitting_review_matrix.html').read_bytes())
    print(json.dumps(dict(cells=len(cells),glyphs=sum(c['counts']['probed'] for c in cells),
                         applied=sum(c['counts']['applied'] for c in cells),
                         changed=sum(c['counts']['changed'] for c in cells))))


if __name__ == '__main__':
    main()
