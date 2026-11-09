"""Python 2 adapter: original profiles/predicates, exhaustive integer origins.

The selector's minimum-admissible-advance principle is preserved. Enumeration
replaces upstream binary search and both placement-rounding stages. In
particular, radius-zero contact is NOT first rounded to a whole font unit:
62.5 FU is a valid one-pixel contact at 1000 UPM / 16 px.
"""
from __future__ import print_function
import json
import math
import os
import sys

from robofab.world import NewFont
from autokern.Autokern import Autokern, AutokernSettings, TFSMap
from typefacet_capture import draw


def run(request_path, directory):
    request = json.load(open(request_path))
    if os.path.exists(directory):
        raise ValueError('integer output must be new')
    os.makedirs(directory)
    src = os.path.join(directory, 'input.ufo')
    font = NewFont()
    font.info.familyName = 'TypeFacet integer diagnostic'
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
    unit = float(request['units_per_em'])/request['size_px']
    caches, results = {}, []
    for candidate in request['candidates']:
        params = candidate['parameters']
        if params['min_distance_ems'] != 0:
            raise ValueError('this experiment fixes zero additional minimum distance')
        sys.argv = ['typefacet_integer', '--ufo-src-path', src, '--ufo-dst-path', os.path.join(directory,'unused.ufo'),
                    '--do-not-modify-side-bearings', '--kerning-threshold-ems', '0', '--disparity-log-count', '0']
        for key, value in sorted(params.items()):
            sys.argv.extend(['--'+key.replace('_','-'),str(value)])
        sys.argv.append('--glyph-pairs-to-kern')
        sys.argv.extend([name for pair in request['pairs'] for name in pair])
        args = TFSMap()
        AutokernSettings(args).getCommandLineSettings()
        model = Autokern(args)
        AutokernSettings(model).getCommandLineSettings()
        model.configure()
        if model.x_extrema_overlap_scaling != 1. or model.tracking != 0:
            raise ValueError('unexpected additional placement transform')
        cache_key = (model.precision,model.profileMinYunits,model.profileMaxYunits)
        if not request.get('cold_cache',False):
            if cache_key in caches:
                model.dstCache = caches[cache_key]
            else:
                caches[cache_key] = model.dstCache
        profile_cache = {}
        def profiles(glyph):
            if glyph.name not in profile_cache:
                contours = model.dstCache.getGlyphContours(glyph)
                def raw():
                    return model.makeProfile(paths=contours)
                def zero():
                    return model.makeInflatedProfile(contours,0.)
                def maximum():
                    return model.makeInflatedProfile(contours,model.max_distance*.5)
                profile_cache[glyph.name] = dict(
                    raw=model.dstCache.getCachedValue('integer raw '+glyph.name,raw),
                    zero=model.dstCache.getCachedValue('integer zero '+glyph.name,zero),
                    maximum=model.dstCache.getCachedValue('integer max %s %f' % (glyph.name,model.max_distance),maximum))
            return profile_cache[glyph.name]
        pairs = []
        for left, right in request['pairs']:
            pair = left+right
            a, b = [model.dstUfoFont.getGlyphByName(name) for name in (left,right)]
            pa, pb = profiles(a), profiles(b)
            ba, bb = model.dstCache.getContoursMinmax(a), model.dstCache.getContoursMinmax(b)
            aa, ab = model.dstCache.getAdjMinmax(a,model), model.dstCache.getAdjMinmax(b,model)
            minimum = model.findMinProfileAdvance(pa['zero'][1],pb['zero'][0])
            if minimum is None:
                minimum = ba.maxX-bb.minX
            maximum = model.findMinProfileAdvance(pa['maximum'][1],pb['maximum'][0])
            if maximum is None:
                maximum = ba.maxX+model.max_distance-bb.minX
            cap = model.getGlyphPair_max_x_extrema_overlap(a,b)
            cap_bound = aa.maxX-ab.minX-cap if aa is not None and ab is not None else minimum
            lower = request['bitmap_minimums'].get(pair)
            # An absent same-row bitmap bound cannot imply a negative or empty
            # search domain. The original minimum-profile fallback still applies.
            first = int(lower) if lower is not None else int(math.floor(minimum/unit))
            last = int(math.ceil(max(minimum,maximum,cap_bound,first*unit)/unit))
            if last-first > 128:
                raise ValueError('integer domain exceeds the declared work bound')
            tested, chosen = [], None
            for step in xrange(first,last+1):
                advance = step*unit
                min_ok, cap_ok = advance >= minimum, advance >= cap_bound
                full = ascender = False
                if min_ok and cap_ok:
                    full = model.isValidProfileIntrusion(pa['maximum'][1],pb['maximum'][0],
                        (pa['raw'][1],pb['raw'][0]),advance,model.max_distance,model.intrusion_tolerance)
                    ascender = model.isValidProfileIntrusion(pa['maximum'][1],pb['maximum'][0],
                        (pa['raw'][1],pb['raw'][0]),advance,model.max_distance,model.intrusion_tolerance,withinAscender=True)
                accepted = min_ok and cap_ok and full and ascender
                tested.append(dict(step=step,minimum_ok=min_ok,extrema_ok=cap_ok,full=full,ascender=ascender,accepted=accepted))
                if accepted and chosen is None:
                    chosen = step
            if chosen is None:
                raise ValueError('no feasible integer: '+pair)
            pairs.append(dict(pair=pair,step_px=chosen,minimum_units=minimum,cap_bound_units=cap_bound,
                              maximum_contact_units=maximum,first=first,last=last,tested=tested))
        results.append(dict(id=candidate['id'],parameters=params,pairs=pairs,
                            precision=model.precision,profile_bounds=cache_key[1:]))
        print('INTEGER_CANDIDATE',candidate['id'],len(pairs))
        sys.stdout.flush()
    output = dict(schema='typefacet-integer-v1',units_per_em=request['units_per_em'],size_px=request['size_px'],
                  python=sys.version,candidates=results)
    with open(os.path.join(directory,'integer.json'),'w') as handle:
        json.dump(output,handle,sort_keys=True)
    print('INTEGER_COMPLETE',len(results))


if __name__ == '__main__':
    run(sys.argv[1],sys.argv[2])
