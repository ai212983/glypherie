"""Python 2 driver for an unchanged, externally pinned TypeFacet checkout.

No algorithm is reimplemented here. The driver creates UFO inputs, invokes the
original process(), and retains its profiles, advances and actual UFO output.
"""
from __future__ import print_function
import json
import os
import sys

from robofab.world import NewFont
from autokern.Autokern import Autokern, AutokernSettings, TFSMap, TFSFontFromFile


def draw(pen, commands):
    for command in commands:
        op = command['op']
        if op == 'move_to':
            pen.moveTo((command['x'], command['y']))
        elif op == 'line_to':
            pen.lineTo((command['x'], command['y']))
        elif op == 'quad_to':
            pen.qCurveTo((command['x1'], command['y1']), (command['x'], command['y']))
        elif op == 'curve_to':
            pen.curveTo((command['x1'], command['y1']), (command['x2'], command['y2']), (command['x'], command['y']))
        elif op == 'close':
            pen.closePath()
        else:
            raise ValueError('unknown contour command: ' + op)


def run(request_path, directory):
    request = json.load(open(request_path))
    if os.path.exists(directory):
        raise ValueError('capture output directory must be new')
    os.makedirs(directory)
    src, dst = os.path.join(directory, 'input.ufo'), os.path.join(directory, 'output.ufo')
    font = NewFont()
    font.info.familyName = 'TypeFacet diagnostic'
    font.info.styleName = 'Regular'
    font.info.unitsPerEm = request['units_per_em']
    font.info.ascender = request['ascender']
    font.info.descender = request['descender']
    for record in request['glyphs']:
        glyph = font.newGlyph(record['name'])
        glyph.unicode = record['codepoint']
        glyph.width = record['advance']
        draw(glyph.getPen(), record['commands'])
        if record.get('component'):
            glyph.appendComponent(record['component'])
    font.save(src)
    pairs = request['pairs']
    argv = ['typefacet_capture', '--ufo-src-path', src, '--ufo-dst-path', dst,
            '--do-not-modify-side-bearings', '--kerning-threshold-ems', '0', '--disparity-log-count', '0']
    for key, value in sorted(request['parameters'].items()):
        argv.extend(['--'+key.replace('_', '-'), str(value)])
    argv.append('--glyph-pairs-to-kern')
    argv.extend([name for pair in pairs for name in pair])
    sys.argv = argv
    args = TFSMap()
    AutokernSettings(args).getCommandLineSettings()
    model = Autokern(args)
    AutokernSettings(model).getCommandLineSettings()
    model.process()
    if not os.path.isdir(dst):
        raise ValueError('upstream process did not write the UFO output')
    output = TFSFontFromFile(dst)
    profiles = {}
    for record in request['glyphs']:
        glyph = model.srcUfoFont.getGlyphByName(record['name'])
        contours = model.srcCache.getGlyphContours(glyph)
        profiles[record['name']] = dict(raw=model.makeProfile(paths=contours),
            minimum=model.makeInflatedProfile(contours, model.min_distance*.5),
            maximum=model.makeInflatedProfile(contours, model.max_distance*.5),
            contours=len(contours), advance=glyph.width)
    records = []
    for left, right in pairs:
        advance = model.advanceMap.get((left, right))
        kerning = output.rffont.kerning.get((left, right), 0)
        width = output.getGlyphByName(left).width
        # Bundled RoboFab BaseKerning.asDict(returnIntegers=True) rounds
        # kerning on UFO save. Fractional captured source widths therefore
        # need not sum back to the selector's integer font-unit advance.
        if advance is not None and kerning != int(round(advance-width)):
            raise ValueError('UFO kerning disagrees with bundled RoboFab export rounding')
        records.append(dict(left=left, right=right, selected_advance=advance,
                            emitted_ufo_advance=width+kerning, ufo_kerning=kerning,
                            ufo_rounding_residual=None if advance is None else width+kerning-advance))
    result = dict(schema='typefacet-reference-capture-v1', parameters=request['parameters'],
                  units_per_em=model.units_per_em, precision=model.precision, ascender=model.ascender,
                  profile_min_y_units=model.profileMinYunits, profile_max_y_units=model.profileMaxYunits,
                  profiles=profiles, pairs=records, python=sys.version)
    with open(os.path.join(directory, 'capture.json'), 'w') as handle:
        json.dump(result, handle, sort_keys=True)
    print('CAPTURE_COMPLETE', directory, len(records))


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
