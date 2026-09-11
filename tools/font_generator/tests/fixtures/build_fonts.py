"""Rebuild original, minimal CFF fixtures using fontTools 4.64.0.

Run from the repository root with tools/font_probe/.venv/bin/python
 tools/font_generator/tests/fixtures/build_fonts.py

Geometry is an original rectangle, authored here for format testing. These
fixtures contain no third-party font outlines. Generated timestamps are fixed.
"""
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.misc.psCharStrings import T2CharString

HERE = Path(__file__).resolve().parent


def build(variable):
    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder([".notdef", "space", "A"])
    builder.setupCharacterMap({32: "space", 65: "A"})
    builder.setupHorizontalMetrics({".notdef": (600, 0), "space": (300, 0), "A": (600, 50)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Generator Format Fixture", "styleName": "Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    if variable:
        builder.setupFvar([("wght", 100, 100, 900, "Weight")], [])
        # At default weight A is 300 units wide; at maximum it is 400.
        charstrings = {name: T2CharString(program=[]) for name in (".notdef", "space")}
        charstrings["A"] = T2CharString(program=[
            50, 0, "rmoveto", 300, 100, 1, "blend", 0, "rlineto",
            0, 700, "rlineto", -300, -100, 1, "blend", 0, "rlineto",
        ])
        builder.setupCFF2(charstrings, regions=[{"wght": (0, 1, 1)}])
    else:
        charstrings = {}
        for name in (".notdef", "space", "A"):
            pen = T2CharStringPen(300 if name == "space" else 600, None)
            if name == "A":
                pen.moveTo((50, 0))
                pen.lineTo((350, 0))
                pen.lineTo((350, 700))
                pen.lineTo((50, 700))
                pen.closePath()
            charstrings[name] = pen.getCharString()
        builder.setupCFF("GeneratorFormatFixture", {"FullName": "Generator Format Fixture"}, charstrings, {})
    builder.font["head"].created = 2082844800
    builder.font["head"].modified = 2082844800
    builder.font.recalcTimestamp = False
    builder.save(HERE / ("variable-cff2.otf" if variable else "static-cff.otf"))


build(False)
build(True)
