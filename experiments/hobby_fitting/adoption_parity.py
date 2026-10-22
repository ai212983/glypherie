"""Native reproduction of the approved terminal fitting delivery.

The frozen packet is an independent test oracle, never a runtime input.
Both supplied f64 source and live font-source extraction can be checked.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.hobby_fitting.real_outline import parse_commands
from experiments.hobby_fitting.native_parity import command_bits, close_enough

DONORS = set(map(ord, 'itflInhkyxzvAVW'))


def raw_outline(commands):
    parsed = parse_commands(commands)
    contours = []
    for contour in parsed['contours']:
        converted = []
        for segment in contour:
            if segment[0] == 'line':
                converted.append({'Line':dict(a=segment[1],b=segment[2])})
            elif segment[0] == 'quad':
                converted.append({'Quad':dict(c=segment[1],a=segment[2],b=segment[3])})
            else:
                converted.append({'Cubic':dict(c1=segment[1],c2=segment[2],a=segment[3],b=segment[4])})
        contours.append(converted)
    return dict(oncurve=parsed['oncurve'],offcurve=parsed['offcurve'],contours=contours)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--source-mode',choices=['provided','runtime'],default='provided')
    parser.add_argument('--mode',choices=['sequence','terminal','joint','curve','attached','crossing'],default='sequence')
    parser.add_argument('--family',choices=['Roboto','SourceSans3'])
    parser.add_argument('--weight',type=int)
    parser.add_argument('--size',type=int)
    parser.add_argument('--glyphs',default='')
    parser.add_argument('--diagnostics',action='store_true')
    parser.add_argument('--applied-only',action='store_true')
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    frozen = ROOT/'out/diagnostics/terminal-fitting/review-final'
    cells = json.loads((frozen/'matrix.json').read_text())
    cells = [c for c in cells if all(getattr(args,k) is None or c[k]==getattr(args,k) for k in ('family','size','weight'))]
    mismatches, provenance, counts = [], {}, dict(cells=0,glyphs=0,applied=0)
    binary_digest = hashlib.sha256(args.binary.read_bytes()).hexdigest()
    process = subprocess.Popen([str(args.binary.resolve())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    started = time.perf_counter()
    for cell in cells:
        name = cell['directory']
        stage_folders = {
            'joint':'out/diagnostics/shape-balance-next/diagonal-matrix',
            'curve':'out/diagnostics/shape-balance-next/curve-matrix-scoped',
            'attached':'out/diagnostics/attached-diagonal/review',
            'crossing':'out/diagnostics/curved-crossing/review-final',
        }
        packet_path = (ROOT/stage_folders[args.mode] if args.mode in stage_folders else frozen)/name/'data.json'
        packet = json.loads(packet_path.read_text())
        final_packet = json.loads((frozen/name/'data.json').read_text())
        raw_by_code = {g['codepoint']:g['raw_source'] for g in final_packet['glyphs']}
        provenance[str(packet_path.relative_to(ROOT))] = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        captured = json.loads((ROOT/f"out/diagnostics/direct-diagonal/text-review/ascii-captures/{cell['family']}-{cell['weight']}-{cell['size']}.json").read_text())[0]
        records = captured['modes'][cell['hint']]['records']
        selected = [g for g in packet['glyphs'] if (not args.glyphs or g['char'] in args.glyphs)
                    and (not args.applied_only or g['result']['applied'])]
        by_code = {g['codepoint']:g for g in selected}
        requested = [dict(r,native_axes=by_code[r['codepoint']]['native_axes'],
                          raw_outline=raw_outline(raw_by_code[r['codepoint']]),
                          preferred_commands=by_code[r['codepoint']]['preferred_commands'])
                     for r in records if r['codepoint'] in by_code]
        request = dict(font=str(ROOT/f"fonts/{cell['family']}.ttf"),size=cell['size'],axes=captured['axes'],
                       donors=[r for r in records if r['codepoint'] in DONORS],records=requested,
                       source_mode=args.source_mode,mode=args.mode,diagnostics=args.diagnostics)
        process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
        line = process.stdout.readline()
        if not line: raise RuntimeError(f'{name}: native adapter stopped with {process.poll()}')
        output = json.loads(line)
        expected_reference = json.loads((ROOT/f"out/diagnostics/direct-diagonal/coverage-review/cells/{cell['family']}_{float(cell['size'])}_{cell['weight']}_{cell['hint']}.json").read_text())['reference']
        assert len(expected_reference['anchors'])==len(output['reference']['anchors'])
        for old,new in zip(expected_reference['anchors'],output['reference']['anchors'],strict=True):
            assert all(close_enough(new[k],old[k]) for k in old),(name,'reference')
        assert len(output['results'])==len(selected)
        for result in output['results']:
            expected = by_code[result['codepoint']]
            counts['glyphs']+=1;counts['applied']+=result['applied']
            if args.mode!='sequence' and not expected['result']['applied']:
                continue
            commands = expected['commands'] if args.mode=='sequence' else expected['result']['candidate_commands']
            wrong_commands = command_bits(result['commands'])!=command_bits(commands)
            wrong_raster = args.mode=='sequence' and result['raster']!=expected['new']
            if wrong_commands or wrong_raster:
                mismatches.append(dict(cell=name,char=expected['char'],commands=wrong_commands,raster=wrong_raster,
                                       actual=result,expected_commands=commands,expected_raster=expected['new']))
        counts['cells']+=1
        print(json.dumps(dict(cell=name,glyphs=len(selected),mismatches=len(mismatches))),flush=True)
    process.stdin.close()
    assert process.wait()==0
    args.out.mkdir(parents=True,exist_ok=True)
    report = dict(**counts,mismatches=len(mismatches),source_mode=args.source_mode,
                  runtime_ms=1000*(time.perf_counter()-started),provenance=provenance,
                  binary_sha256=binary_digest)
    (args.out/'summary.json').write_text(json.dumps(report,indent=2))
    (args.out/'mismatches.json').write_text(json.dumps(mismatches,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='provenance'}))
    return bool(mismatches)


if __name__=='__main__':
    raise SystemExit(main())
