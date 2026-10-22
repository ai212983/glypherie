"""Internal comparison of joint fitting against the preferred native-width packet."""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import concurrent.futures
import subprocess

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.hobby_fitting import direct_diagonal_run as run
from experiments.hobby_fitting import curved_width
from experiments.hobby_fitting import shape_balance_review as checks
from experiments.hobby_fitting import text_review as text


def ink(tile):
    return {(tile['left'] + i % tile['width'], tile['top'] + i // tile['width'])
            for i, value in enumerate(tile['pixels']) if value}


def validate_result(source, upstream, result, axes):
    commands = result['candidate_commands']
    if not result['applied']:
        if not checks.commands_equal(upstream, commands):
            raise ValueError('abstention changed input commands')
        return
    if not checks.same_skeleton(upstream, commands):
        raise ValueError('command skeleton changed')
    if not all(checks.valid_command(c) for c in commands):
        raise ValueError('invalid coordinates or float32 bits')
    if not checks.respects_pins(upstream, commands, axes):
        raise ValueError('native coordinate ownership changed')
    retained = result.get('diagnostics', {}).get('retained_upstream_axes', axes)
    if not checks.respects_pins(upstream, commands, retained):
        raise ValueError('retained upstream coordinate changed')
    upright = result.get('diagnostics', {}).get('upright_x_pins', [])
    if upright:
        from experiments.hobby_fitting.real_outline import parse_commands
        old_points, new_points = parse_commands(upstream)['oncurve'], parse_commands(commands)['oncurve']
        if any(checks.f32_bits(old_points[i][0]) != checks.f32_bits(new_points[i][0]) for i in upright):
            raise ValueError('upright anchor coordinate changed')
    topology = curved_width._substitution_gate(source, upstream, commands)
    if not topology['ok']:
        raise ValueError('independent topology check failed')
    result['host_topology'] = topology


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', default='Roboto')
    parser.add_argument('--size', type=int, default=16)
    parser.add_argument('--weight', type=int, default=400)
    parser.add_argument('--hint', default='selective_default',
                        choices=['selective_default', 'auto_default'])
    parser.add_argument('--model', required=True, choices=['diagonal', 'curve'])
    parser.add_argument('--glyphs', default='')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--matrix', action='store_true')
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    if args.matrix:
        jobs = [(family, size, weight, hint) for family in ['Roboto', 'SourceSans3']
                for size in [12, 14, 16, 18, 20, 24] for weight in [300, 400, 700]
                for hint in ['selective_default', 'auto_default']]
        def build(job):
            family, size, weight, hint = job
            name = f'{family}-{weight}-{size}-{hint}'
            cmd = [sys.executable, str(Path(__file__).resolve()), '--model', args.model,
                   '--family', family, '--size', str(size), '--weight', str(weight),
                   '--hint', hint, '--out', str(args.out / name)]
            if args.glyphs:
                cmd += ['--glyphs', args.glyphs]
            process = subprocess.run(cmd, capture_output=True, text=True)
            if process.returncode:
                raise RuntimeError(process.stdout + process.stderr)
            return dict(family=family, size=size, weight=weight, hint=hint,
                        directory=name, counts=json.loads(process.stdout))
        args.out.mkdir(parents=True, exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            cells = list(pool.map(build, jobs))
        (args.out / 'matrix.json').write_text(json.dumps(cells))
        (args.out / 'index.html').write_text((ROOT / 'experiments/hobby_fitting/joint_review_matrix.html').read_text())
        print(json.dumps(dict(cells=len(cells), glyphs=sum(c['counts']['probed'] for c in cells),
                              applied=sum(c['counts']['applied'] for c in cells),
                              changed=sum(c['counts']['changed'] for c in cells))))
        return
    baseline = ROOT / 'out/diagnostics/direct-diagonal/coverage-review/cells' / (
        f'{args.family}_{float(args.size)}_{args.weight}_{args.hint}.json')
    capture = ROOT / 'out/diagnostics/direct-diagonal/text-review/ascii-captures' / (
        f'{args.family}-{args.weight}-{args.size}.json')
    cell = json.loads(baseline.read_text())
    case = json.loads(capture.read_text())[0]
    records = {r['codepoint']: r for r in case['modes'][args.hint]['records']}
    module = importlib.import_module('experiments.hobby_fitting.' + (
        'joint_diagonal' if args.model == 'diagonal' else 'smooth_curve_fit'))
    binary = str(ROOT / 'tools/generator/target/debug/strokestyles-fit-adapter')
    selected = set(map(ord, args.glyphs)) if args.glyphs else set(records)
    old_tiles, new_tiles, glyphs = {}, {}, []
    with tempfile.TemporaryDirectory() as scratch:
        for glyph in cell['glyphs']:
            code = glyph['codepoint']
            preferred = glyph['candidate']['candidate_commands']
            old = dict(glyph['candidate']['frame'], pixels=glyph['candidate']['pixels'])
            old_tiles[code] = new_tiles[code] = old
            if code not in selected:
                continue
            record = records[code]
            source, upstream = record['source_commands'], record['fitted_commands']
            axes = glyph['native_axes']
            run.check_parity(binary, record, scratch)
            replay = run.arm_pixels(binary, record, preferred, scratch)
            if any(replay[k] != old[k] for k in ('left', 'top', 'width', 'height', 'pixels')):
                raise ValueError('preferred replay mismatch')
            fit_input = upstream if args.model == 'diagonal' else preferred
            fit = module.fit if args.model == 'diagonal' else module.fit_horizontal_glyph
            result = fit(source, fit_input, args.size, cell['reference'], tuple(axes))
            validate_result(source, fit_input, result, axes)
            delivered = result['candidate_commands'] if result['applied'] else preferred
            rendered = run.arm_pixels(binary, record, delivered, scratch)
            new = {k: rendered[k] for k in ('left', 'top', 'width', 'height', 'pixels')}
            if len(new['pixels']) != new['width'] * new['height']:
                raise ValueError('invalid raster frame')
            new_tiles[code] = new
            glyphs.append(dict(char=chr(code), codepoint=code, source=source,
                               preferred_commands=preferred, commands=delivered,
                               old=old, new=new, changed=ink(old) != ink(new),
                               result=result, native_axes=axes))
    lines = [dict(text.compose_line_common(line, old_tiles, new_tiles), text=line['text'])
             for line in cell['layout']['lines']]
    dependencies = [Path(__file__).resolve(), Path(module.__file__).resolve(),
                    ROOT / 'experiments/hobby_fitting/joint_review.html',
                    ROOT / 'experiments/hobby_fitting/text_review.py', baseline, capture,
                    Path(binary)]
    dependencies.append(ROOT / 'out/diagnostics/direct-diagonal/exact-topology/bin/exact_topology')
    dependencies += [ROOT / 'experiments/hobby_fitting' / (name + '.py')
                     for name in ['direct_diagonal', 'direct_diagonal_run', 'shape_balance_review',
                                  'curved_width', 'curve_clearance', 'curve_contacts', 'exact_topology',
                                  'prototype', 'real_outline', 'intervals', 'symmetry_placement']]
    provenance = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in dependencies}
    data = dict(family=args.family, size=args.size, weight=args.weight, hint=args.hint,
                model=args.model, probed=sorted(selected), glyphs=glyphs, lines=lines,
                layout=cell['layout'], provenance=provenance)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'data.json').write_text(json.dumps(data))
    (args.out / 'index.html').write_text(
        (ROOT / 'experiments/hobby_fitting/joint_review.html').read_text())
    print(json.dumps(dict(probed=len(glyphs), applied=sum(g['result']['applied'] for g in glyphs),
                          changed=sum(g['changed'] for g in glyphs), out=str(args.out))))


if __name__ == '__main__':
    main()
