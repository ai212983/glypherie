"""Normalize the filled boundary before Shamir feature extraction.

The related Shamir/Rappoport preparation work includes contour interpenetration
correction. fontTools/Skia is our implementation choice, not their recovered code.
Work on the in-memory static font; preserve the original input file.
"""
from fontTools.ttLib.removeOverlaps import removeOverlaps
import pathops


def normalize_boundaries(font,chars):
    cmap=font.getBestCmap();names=list(dict.fromkeys(cmap[ord(c)] for c in chars))
    def geometry(name):
        g=font['glyf'][name]
        points,ends,flags=g.getCoordinates(font['glyf'])
        return (tuple(points),tuple(ends),tuple(int(f)&1 for f in flags))
    before={name:geometry(name) for name in names}
    metrics=dict(font['hmtx'].metrics)
    removeOverlaps(font,names,removeHinting=True,ignoreErrors=False)
    # fontTools canonicalizes side bearings to xMin when replacing a glyph.
    # Preserve the font's authored placement independently of outline bounds.
    font['hmtx'].metrics.update(metrics)
    changed=[]
    for name in names:
        after=geometry(name)
        if after!=before[name]:
            changed.append(dict(glyph=name,contours_before=len(before[name][1]),
                                contours_after=len(after[1]),points_before=len(before[name][0]),points_after=len(after[0])))
    return dict(method='fontTools.removeOverlaps / Skia nonzero filled boundary',
                pathops_version=pathops.__version__,changed=changed)
