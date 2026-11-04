"""Regenerate native FontForge goldens; Rust is never called by this script.

Inputs are retained contextual-spacing capture JSON and the pinned C driver's
executable/build identity. The fixture retains every command needed for tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

FIELDS = {
    'move_to': ('M', ('x', 'y')),
    'line_to': ('L', ('x', 'y')),
    'quad_to': ('Q', ('x1', 'y1', 'x', 'y')),
    'curve_to': ('C', ('x1', 'y1', 'x2', 'y2', 'x', 'y')),
    'close': ('Z', ()),
}


def native(executable, inputs, em):
    lines = [f'{em} 200 {len(inputs)}']
    for item in inputs:
        lines.append(str(len(item['commands'])))
        for cmd in item['commands']:
            op, fields = FIELDS[cmd['op']]
            lines.append(' '.join([op, *(repr(cmd[key] * item['scale']) for key in fields)]))
    return json.loads(subprocess.run([str(executable)], input='\n'.join(lines)+'\n',
        text=True, capture_output=True, check=True).stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', required=True, type=Path)
    parser.add_argument('--identity', required=True, type=Path)
    parser.add_argument('--captures', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    def rectangle(x, y, w, h):
        return [dict(op='move_to',x=x,y=y),dict(op='line_to',x=x+w,y=y),
            dict(op='line_to',x=x+w,y=y+h),dict(op='line_to',x=x,y=y+h),dict(op='close')]
    synthetic = [
        dict(label='rectangle',scale=1,commands=rectangle(0,0,100,100)),
        dict(label='negative_rectangle',scale=1,commands=rectangle(-23,-20,100,100)),
        dict(label='boundary_contact',scale=1,commands=rectangle(0,100,100,100)),
        dict(label='detached_marks',scale=1,commands=rectangle(0,0,100,20)+rectangle(20,80,30,20)),
        dict(label='quadratic_x_extremum',scale=1,commands=[dict(op='move_to',x=0,y=0),
            dict(op='quad_to',x1=200,y1=50,x=0,y=100),dict(op='close')]),
        dict(label='cubic_x_extremum',scale=1,commands=[dict(op='move_to',x=0,y=0),
            dict(op='curve_to',x1=300,y1=100,x2=300,y2=200,x=0,y=300),dict(op='close')]),
        dict(label='cubic_y_extremum',scale=1,commands=[dict(op='move_to',x=0,y=0),
            dict(op='curve_to',x1=0,y1=300,x2=100,y2=300,x=100,y=0),dict(op='close')]),
        dict(label='opposing_wedge',scale=1,commands=[dict(op='move_to',x=0,y=0),
            dict(op='line_to',x=200,y=0),dict(op='line_to',x=0,y=800),dict(op='close')]),
    ]
    cases = [dict(font='synthetic-'+str(em), inputs=synthetic, native=native(args.native,synthetic,em))
        for em in [1000,2048]]
    for name in ['Literata-reading', 'Roboto', 'RobotoFlex', 'SourceSans3']:
        path = args.captures / name / 'capture.json'
        capture = json.loads(path.read_text())
        glyphs = {g['codepoint']: g for g in capture['glyphs']}
        inputs = []
        # Includes curved, diagonal, detached-mark and upright source/fitted paths.
        for geometry, key in [('source', 'source_commands'), ('fitted', 'produced_commands')]:
            for char in 'AOTVgijo':
                g = glyphs[ord(char)]
                commands = [{k: v for k, v in cmd.items() if not k.endswith('_bits')}
                    for cmd in g[key]]
                inputs.append(dict(label=geometry + ':' + char, commands=commands,
                    scale=1 if geometry == 'source' else capture['units_per_em'] / capture['size_px']))
        cases.append(dict(font=name, capture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            inputs=inputs, native=native(args.native, inputs, capture['units_per_em'])))
    result = dict(schema='fontforge-maintained-reference-v1',
        native_build_identity=json.loads(args.identity.read_text()),
        native_binary_sha256=hashlib.sha256(args.native.read_bytes()).hexdigest(),
        cases=cases)
    args.output.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
