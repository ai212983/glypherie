"""Compare the isolated attached-diagonal fit with the preceding joint packet."""

import argparse
import concurrent.futures
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.hobby_fitting import curved_width, direct_diagonal_run as run
from experiments.hobby_fitting import joint_comparison, joint_review, text_review
from experiments.hobby_fitting import shape_balance_review as checks
from experiments.hobby_fitting.real_outline import parse_commands


def load(path):
    return json.loads(path.read_text())


def topology(source, upstream, candidate):
    return dict(curved_width._substitution_gate(source, upstream, candidate), supported=True)


def build_cell(args):
    import numpy
    import scipy
    from experiments.hobby_fitting import attached_diagonal

    name = f'{args.family}-{args.weight}-{args.size}-{args.hint}'
    baseline = ROOT / 'out/diagnostics/shape-balance-next/review' / name / 'data.json'
    capture = ROOT / 'out/diagnostics/direct-diagonal/text-review/ascii-captures' / (
        f'{args.family}-{args.weight}-{args.size}.json')
    reference_file = ROOT / 'out/diagnostics/direct-diagonal/coverage-review/cells' / (
        f'{args.family}_{float(args.size)}_{args.weight}_{args.hint}.json')
    prior, reference = load(baseline), load(reference_file)
    joint_comparison.check_provenance(prior)
    assert prior['layout'] == reference['layout']
    assert [g['codepoint'] for g in prior['glyphs']] == list(range(32, 127))
    case = load(capture)[0]
    records = {r['codepoint']: r for r in case['modes'][args.hint]['records']}
    selected = set(map(ord, args.glyphs)) if args.glyphs else set(records)
    binary = str(ROOT / 'tools/generator/target/debug/strokestyles-fit-adapter')
    old_tiles, new_tiles, glyphs = {}, {}, []
    with tempfile.TemporaryDirectory() as scratch:
        for glyph in prior['glyphs']:
            code = glyph['codepoint']
            preferred, old = glyph['commands'], glyph['new']
            old_tiles[code] = new_tiles[code] = old
            if code not in selected:
                continue
            record = records[code]
            source, upstream = record['source_commands'], record['fitted_commands']
            assert source == glyph['source']
            axes = glyph['native_axes']
            run.check_parity(binary, record, scratch)
            replay = run.arm_pixels(binary, record, preferred, scratch)
            if any(replay[k] != old[k] for k in ('left', 'top', 'width', 'height', 'pixels')):
                raise ValueError('preceding joint packet replay mismatch')
            result = attached_diagonal.fit(source, upstream, args.size, reference['reference'],
                                           tuple(axes), topology_checker=topology)
            joint_review.validate_result(source, upstream, result, axes)
            if result['applied']:
                commands = result['candidate_commands']
                if not checks.respects_pins(upstream, commands, (axes[0], True)):
                    raise ValueError('retained Y or native X changed')
                src, before, after = [parse_commands(c) for c in (source, upstream, commands)]
                points = src['oncurve']
                pins = {v for contour in src['contours'] for seg in contour
                        if seg[0] == 'line' and points[seg[1]][0] == points[seg[2]][0]
                        and points[seg[1]][1] != points[seg[2]][1] for v in (seg[1], seg[2])}
                if any(checks.f32_bits(before['oncurve'][i][0]) !=
                       checks.f32_bits(after['oncurve'][i][0]) for i in pins):
                    raise ValueError('source upright X anchor changed')
            delivered = result['candidate_commands'] if result['applied'] else preferred
            rendered = run.arm_pixels(binary, record, delivered, scratch)
            new = {k: rendered[k] for k in ('left', 'top', 'width', 'height', 'pixels')}
            if len(new['pixels']) != new['width'] * new['height']:
                raise ValueError('invalid raster frame')
            new_tiles[code] = new
            glyphs.append(dict(char=chr(code), codepoint=code, source=source,
                               original_upstream_commands=upstream, preferred_commands=preferred,
                               commands=delivered, old=old, new=new,
                               changed=joint_review.ink(old) != joint_review.ink(new),
                               result=result, native_axes=axes))
    lines = [dict(text_review.compose_line_common(line, old_tiles, new_tiles), text=line['text'])
             for line in prior['layout']['lines']]
    folder = ROOT / 'experiments/hobby_fitting'
    dependencies = [Path(__file__).resolve(), folder / 'attached_review.html',
                    folder / 'attached_review_matrix.html', baseline, capture, reference_file,
                    folder / 'requirements.txt', Path(binary),
                    ROOT / 'out/diagnostics/direct-diagonal/exact-topology/bin/exact_topology']
    dependencies += [folder / (name + '.py') for name in [
        'attached_diagonal', 'smooth_curve_fit', 'joint_diagonal', 'joint_review',
        'joint_comparison', 'text_review', 'direct_diagonal_run', 'direct_diagonal',
        'curved_width', 'curve_clearance', 'curve_contacts', 'exact_topology',
        'prototype', 'real_outline', 'intervals', 'shape_balance_review', 'symmetry_placement']]
    provenance = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in dependencies}
    data = dict(family=args.family, size=args.size, weight=args.weight, hint=args.hint,
                model='attached', baseline='joint-stroke-candidate', probed=sorted(selected),
                glyphs=glyphs, lines=lines, layout=prior['layout'], provenance=provenance,
                runtime=dict(python=platform.python_version(), numpy=numpy.__version__,
                             scipy=scipy.__version__, platform=platform.platform()))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'data.json').write_text(json.dumps(data))
    (args.out / 'index.html').write_text((folder / 'attached_review.html').read_text())
    return dict(probed=len(glyphs), applied=sum(g['result']['applied'] for g in glyphs),
                changed=sum(g['changed'] for g in glyphs), out=str(args.out))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', default='Roboto', choices=['Roboto', 'SourceSans3'])
    parser.add_argument('--size', type=int, default=16)
    parser.add_argument('--weight', type=int, default=400)
    parser.add_argument('--hint', default='selective_default', choices=['selective_default', 'auto_default'])
    parser.add_argument('--glyphs', default='')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--matrix', action='store_true')
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    if not args.matrix:
        print(json.dumps(build_cell(args)))
        return
    jobs = [(f, s, w, h) for f in ['Roboto', 'SourceSans3'] for s in [12, 14, 16, 18, 20, 24]
            for w in [300, 400, 700] for h in ['selective_default', 'auto_default']]

    def build(job):
        family, size, weight, hint = job
        name = f'{family}-{weight}-{size}-{hint}'
        cmd = [sys.executable, str(Path(__file__).resolve()), '--family', family,
               '--size', str(size), '--weight', str(weight), '--hint', hint,
               '--out', str(args.out / name)]
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
    (args.out / 'index.html').write_text(
        (ROOT / 'experiments/hobby_fitting/attached_review_matrix.html').read_text())
    print(json.dumps(dict(cells=len(cells), glyphs=sum(c['counts']['probed'] for c in cells),
                          applied=sum(c['counts']['applied'] for c in cells),
                          changed=sum(c['counts']['changed'] for c in cells))))


if __name__ == '__main__':
    main()
