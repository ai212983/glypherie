#!/usr/bin/env python3
"""Run the configured generator calibration matrix and retain host diagnostics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).with_name('calibration.json')


def components(mask, diagonal=False):
    """Component sizes; ink uses 8-connectivity, background uses 4-connectivity."""
    cells = {(x, y) for y, row in enumerate(mask) for x, value in enumerate(row) if value}
    sizes = []
    neighbors = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if diagonal:
        neighbors += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
    while cells:
        pending = [cells.pop()]
        size = 0
        while pending:
            x, y = pending.pop()
            size += 1
            for dx, dy in neighbors:
                point = x + dx, y + dy
                if point in cells:
                    cells.remove(point)
                    pending.append(point)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def topology(glyph, bits):
    w, h = glyph['width'], glyph['height']
    cutoff = (1 << bits) // 2
    mask = [[glyph['pixels'][y*w+x] >= cutoff for x in range(w)] for y in range(h)]
    padded = [[True] * (w+2)]
    padded += [[True] + [not value for value in row] + [True] for row in mask]
    padded += [[True] * (w+2)]
    return len(components(mask, True)), len(components(padded)) - 1


def matrix(config, config_path):
    cases = []
    for font in config['fonts']:
        job_path = (config_path.parent / font['job']).resolve()
        template = json.loads(job_path.read_text())
        font_path = (job_path.parent / template['font']).resolve()
        for panel, sizes in font['sizes'].items():
            for role, size in zip(config['roles'], sizes, strict=True):
                for weight in config['weights']:
                    settings = dict(template['settings'])
                    settings['axes'] = dict(settings['axes'], wght=weight)
                    if 'opsz' in settings['axes']:
                        settings['axes']['opsz'] = min(72, max(7, size))
                    settings.update(size_px=size, mono_threshold=128,
                                    characters=config['ambient_characters'] if role.startswith('ambient') else config['characters'])
                    variants = [(1, 128, {})]
                    if panel == 'inkplate':
                        variants += [(3, 128, {})]
                    if size <= 20:
                        variants += [(1, 96, {})]
                    if panel == 'waveshare' and role == 'caption':
                        variants += [(1, 128, axes) for axes in font['axis_probes']]
                    for bits, threshold, axes in variants:
                        chosen = dict(settings, output_bits=bits, mono_threshold=threshold,
                                      axes=dict(settings['axes'], **axes))
                        suffix = ''.join(f'-{k}{v}' for k, v in sorted(axes.items()))
                        case_id = f"{font['name'].lower()}-{panel}-{role}-w{weight}-b{bits}-t{threshold}{suffix}"
                        cases.append({'id':case_id, 'font':font['name'], 'panel':panel,
                                      'role':role, 'artifact':f'glyphs/{case_id}.json',
                                      'settings':chosen, '_font_path':font_path,
                                      '_provenance':template['provenance']})
    for probe in config.get('diagnostic_probes', []):
        base = next(c for c in cases if c['font'] == probe['font']
                    and c['panel'] == probe['panel'] and c['role'] == probe['role']
                    and c['settings']['axes']['wght'] == probe['weight']
                    and c['settings']['output_bits'] == 1
                    and c['settings']['mono_threshold'] == 128)
        for threshold in probe['thresholds']:
            settings = dict(base['settings'], mono_threshold=threshold,
                            axes=dict(base['settings']['axes'], **probe['axes']))
            suffix = ''.join(f'-{k}{v}' for k,v in sorted(probe['axes'].items()))
            case = dict(base, id=base['id'].replace('-t128', f'-t{threshold}')+suffix,
                        settings=settings, diagnostic_probe=True)
            case['artifact'] = f"glyphs/{case['id']}.json"
            cases.append(case)
    return cases


def diagnose(generated):
    glyphs = {chr(g['codepoint']): g for g in generated['glyphs']}
    bits = generated['config']['output_bits']
    anomalies = []
    for char, holes in {'b':1, 'h':0, 'm':0, 'n':0, 'p':1, 'o':1, '0':1, '8':2}.items():
        if char in glyphs:
            actual = topology(glyphs[char], bits)
            if actual != (1, holes):
                anomalies.append({'character':char, 'ink_components':actual[0],
                                  'counters':actual[1], 'expected':[1, holes]})
    x = glyphs.get('x')
    cutoff = (1 << bits) // 2
    x_height = sum(any(v >= cutoff for v in x['pixels'][row*x['width']:(row+1)*x['width']])
                   for row in range(x['height'])) if x else None
    pairs = {(p['left'], p['right']):p['adjustment_26_6'] for p in generated['kerning']}
    runs = []
    for text in ['AVATAR To Wa', 'minimum 08:38', '21.5°C 48%']:
        if all(c in glyphs for c in text):
            width = sum(glyphs[c]['advance_26_6'] for c in text)
            kern = sum(pairs.get((ord(a),ord(b)),0) for a,b in zip(text,text[1:]))
            runs.append({'text':text, 'advance_px':(width+kern)/64, 'kerning_px':kern/64})
    return {'x_height_px':x_height, 'topology':anomalies, 'spacing':runs}


def retain_image(glyph, bits, destination):
    from PIL import Image
    maximum = (1 << bits)-1
    image = Image.new('L', (glyph['width'], glyph['height']))
    image.putdata([255-round(255*v/maximum) for v in glyph['pixels']])
    image.resize((image.width*12,image.height*12), Image.Resampling.NEAREST).save(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--out', type=Path, default=DEFAULT_CONFIG.parent/'out/calibration')
    args = parser.parse_args()
    config_path, out = args.config.resolve(), args.out.resolve()
    config = json.loads(config_path.read_text())
    cases = matrix(config, config_path)
    manifest_path = ROOT/'tools/font_generator/Cargo.toml'
    subprocess.run(['cargo','+stable','build','--locked','--release','--manifest-path',str(manifest_path)], check=True)
    metadata = json.loads(subprocess.check_output(['cargo','+stable','metadata','--no-deps','--format-version','1','--manifest-path',str(manifest_path)]))
    binary = Path(metadata['target_directory'])/'release/font_generator'
    for folder in ['jobs','glyphs','failures']:
        (out/folder).mkdir(parents=True,exist_ok=True)
    toolchain = subprocess.check_output(['rustc','+stable','-vV'],text=True).strip()
    (out/'calibration.json').write_bytes(config_path.read_bytes())
    source_paths = [Path(__file__).resolve(), ROOT/'tools/font_generator/src/lib.rs',
                    ROOT/'tools/font_generator/src/raster.rs', ROOT/'tools/font_generator/src/spacing.rs',
                    ROOT/'tools/font_generator/src/main.rs', ROOT/'tools/font_generator/Cargo.lock']
    source_hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    manifest = {'schema_version':1, 'source_sha256':source_hashes, 'config_sha256':hashlib.sha256(config_path.read_bytes()).hexdigest(),
                'toolchain':toolchain, 'cases':[], 'summary':{}}
    for index, case in enumerate(cases):
        font_path, provenance = case.pop('_font_path'), case.pop('_provenance')
        job = {'font':os.path.relpath(font_path, out/'jobs'), 'provenance':provenance,'settings':case['settings']}
        job_path = out/'jobs'/f"{case['id']}.json"
        job_path.write_text(json.dumps(job,indent=2)+'\n')
        artifact = out/case['artifact']
        subprocess.run([str(binary),str(job_path),str(artifact)],check=True)
        data = json.loads(artifact.read_text())
        case['artifact_sha256'] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        case['diagnostics'] = diagnose(data['generated'])
        for anomaly in case['diagnostics']['topology']:
            glyph = next(g for g in data['generated']['glyphs'] if g['codepoint']==ord(anomaly['character']))
            image_path = f"failures/{case['id']}-U{glyph['codepoint']:04X}.png"
            retain_image(glyph, case['settings']['output_bits'], out/image_path)
            anomaly['image'] = image_path
        manifest['cases'].append(case)
        if (index+1)%20 == 0:
            print(f"calibration: {index+1}/{len(cases)} cases", flush=True)
    anomalies = [(c,a) for c in cases for a in c['diagnostics']['topology']]
    manifest['summary'] = {'case_count':len(cases), 'topology_anomalies':len(anomalies),
                           'physical_evaluation':'pending',
                           'topology_method':'8-connected ink and 4-connected background at half coverage; gray threshold is a diagnostic projection',
                           'topology_interpretation':'Flags require glyph inspection; these Latin shapes expect one connected body and their conventional counters.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    lines = ['# Host calibration', '', f"Cases: {len(cases)}. Topology flags: {len(anomalies)}. Physical evaluation: pending.", '',
             'Topology uses 8-connected ink and 4-connected background. Gray output is projected at half coverage for this diagnostic.',
             'Measurements describe raster structure and advances; panel recognition and comfort require recorded physical evaluation.', '',
             '| Case | x-height (px) | Topology flags |', '| --- | ---: | ---: |']
    lines += [f"| {c['id']} | {c['diagnostics']['x_height_px']} | {len(c['diagnostics']['topology'])} |" for c in cases]
    if anomalies:
        lines += ['', '## Retained flags', '']
        lines += [f"- {c['id']}, `{a['character']}`: {a['ink_components']} components, {a['counters']} counters; [image]({a['image']})." for c,a in anomalies]
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    print(f"calibration complete: {len(cases)} cases, {len(anomalies)} topology flags; {out/'manifest.json'}")


if __name__ == '__main__':
    main()
