"""Python 2 batch caller of original TypeFacet configure/processKerningPair.

Only geometry caches are shared, keyed by the complete sampling window and
precision. Parameter-sensitive profile keys are supplied by upstream itself.
Full UFO runs independently check this acceleration before its results are used.
"""
from __future__ import print_function
import json
import os
import sys

from robofab.world import NewFont
from autokern.Autokern import Autokern, AutokernSettings, TFSMap
from typefacet_capture import draw


def run(request_path, directory):
    request = json.load(open(request_path))
    if os.path.exists(directory):
        raise ValueError('batch output directory must be new')
    os.makedirs(directory)
    src = os.path.join(directory, 'input.ufo')
    dst = os.path.join(directory, 'unused-output.ufo')
    font = NewFont()
    font.info.familyName = 'TypeFacet calibration diagnostic'
    font.info.styleName = 'Regular'
    font.info.unitsPerEm = request['units_per_em']
    font.info.ascender = request['ascender']
    font.info.descender = request['descender']
    for record in request['glyphs']:
        glyph = font.newGlyph(record['name'])
        glyph.unicode = record['codepoint']
        glyph.width = record['advance']
        draw(glyph.getPen(), record['commands'])
    font.save(src)
    caches, results = {}, []
    for candidate in request['candidates']:
        pairs = candidate.get('pairs', request['pairs'])
        sys.argv = ['typefacet_batch', '--ufo-src-path', src, '--ufo-dst-path', dst,
                    '--do-not-modify-side-bearings', '--kerning-threshold-ems', '0', '--disparity-log-count', '0']
        for key, value in sorted(candidate['parameters'].items()):
            sys.argv.extend(['--'+key.replace('_', '-'), str(value)])
        sys.argv.append('--glyph-pairs-to-kern')
        sys.argv.extend([name for pair in pairs for name in pair])
        args = TFSMap()
        AutokernSettings(args).getCommandLineSettings()
        model = Autokern(args)
        AutokernSettings(model).getCommandLineSettings()
        model.configure()
        # Changing max distance changes upstream's global profile extent.
        # Reusing profiles solely by radius or glyph name would be incorrect.
        key = (model.precision, model.profileMinYunits, model.profileMaxYunits)
        if not request.get('disable_cache_sharing', False):
            if key in caches:
                model.dstCache = caches[key]
            else:
                caches[key] = model.dstCache
        for left, right in pairs:
            model.processKerningPair(model.dstUfoFont.getGlyphByName(left), model.dstUfoFont.getGlyphByName(right))
        values = dict((left+right, model.advanceMap.get((left, right))) for left, right in pairs)
        if any(value is None for value in values.values()):
            raise ValueError('missing reference selection')
        results.append(dict(id=candidate['id'], parameters=candidate['parameters'], advances=values,
                            precision=model.precision, profile_bounds=key[1:]))
    with open(os.path.join(directory, 'batch.json'), 'w') as handle:
        json.dump(dict(schema='typefacet-batch-v1', units_per_em=request['units_per_em'], python=sys.version,
                       candidates=results), handle, sort_keys=True)
    print('BATCH_COMPLETE', len(results))


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2])
