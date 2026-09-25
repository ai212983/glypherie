"""Zero-drift guard: settled-exact glyphs stay settled-exact.

Compares hinted rasters of candidate fonts across three probe output
dirs: SETTLED (the reference), BASE (last shipped) and NEW (this
run). Any glyph pixel-identical between SETTLED and BASE must be
pixel-identical in NEW. Verdict batteries cannot see exact-to-drifted
(the v35 cap-entry normalize moved 53 settled-exact glyphs up to
47px off reference while the 48-case oracle stayed green), so this
exactness check stands beside them. Intentional moves (e.g. an
oracle-APPROVEd fix like v36 literata-16 S) go in a waivers file as
explicit ``"face char": reason`` entries; unwaived violations exit
nonzero.
"""
import argparse
import json
from pathlib import Path

import freetype as ft

HERE = Path(__file__).resolve().parent


def rasterize(ttf_path, size):
    """Hinted mono ink per char: ``{char: frozenset((x, y))}``."""
    face = ft.Face(str(ttf_path))
    face.set_pixel_sizes(0, size)
    out = {}
    code, _gid = face.get_first_char()
    codes = []
    while _gid:
        codes.append(code)
        code, _gid = face.get_next_char(code, _gid)
    for code in codes:
        char = chr(code)
        try:
            face.load_char(char,
                           ft.FT_LOAD_RENDER | ft.FT_LOAD_TARGET_MONO)
        except Exception:
            continue
        glyph = face.glyph
        bitmap = glyph.bitmap
        if not bitmap.width or not bitmap.rows:
            out[char] = frozenset()
            continue
        buf = bytes(bitmap.buffer)
        left, top = glyph.bitmap_left, -glyph.bitmap_top
        out[char] = frozenset(
            (left + x, top + y)
            for y in range(bitmap.rows)
            for x in range(bitmap.width)
            if buf[y * bitmap.pitch + x // 8] & (0x80 >> (x % 8)))
    return out


def load_dir(directory):
    """Map ``face-tag -> {char: pixels}`` for candidate fonts."""
    faces = {}
    for path in sorted(Path(directory).glob('*-candidate.ttf')):
        tag = path.name.removesuffix('-candidate.ttf')
        try:
            size = int(tag.rsplit('-', 1)[1])
        except ValueError:
            continue
        faces[tag] = rasterize(path, size)
    return faces


def audit_drift(settled, base, new, waivers=None):
    """Pure core over ``{face: {char: pixels}}`` maps.

    Returns ``dict(violations, moved, missing)``: violations are
    ``(face, char, base_dist, new_dist)`` for settled-exact glyphs
    that moved without a waiver; moved lists non-exact glyphs whose
    raster changed either way; missing lists glyphs absent from NEW
    (holds are the census's domain, reported not failed).
    """
    waivers = waivers or {}
    violations, moved, missing = [], [], []
    for face, glyphs in base.items():
        for char, pixels in glyphs.items():
            ref = (settled.get(face) or {}).get(char)
            if ref is None:
                continue
            if ref != pixels:
                current = (new.get(face) or {}).get(char)
                if current is not None and current != pixels:
                    moved.append((face, char, len(pixels ^ ref),
                                  len(current ^ ref)))
                continue
            current = (new.get(face) or {}).get(char)
            if current is None:
                missing.append((face, char))
            elif current != ref:
                key = f'{face} {char}'
                if key in waivers:
                    moved.append((face, char, 0, len(current ^ ref)))
                else:
                    violations.append((face, char, 0,
                                       len(current ^ ref)))
    return {'violations': violations, 'moved': moved, 'missing': missing}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--settled', required=True,
                    help='reference output dir (e.g. arch-probe-v28)')
    ap.add_argument('--base', required=True,
                    help='last shipped output dir (e.g. arch-probe-v34)')
    ap.add_argument('--new', required=True,
                    help='candidate output dir under test')
    ap.add_argument('--waive', default=None,
                    help='JSON file mapping "face char" to reason')
    args = ap.parse_args(argv)
    waivers = {}
    if args.waive:
        waivers = json.loads(Path(args.waive).read_text())
    report = audit_drift(load_dir(args.settled), load_dir(args.base),
                         load_dir(args.new), waivers)
    for face, char, _old, dist in report['violations']:
        print(f'DRIFT {face} {char!r}: settled-exact moved {dist}px')
    for face, char, _old, dist in report['moved']:
        print(f'moved {face} {char!r}: now {dist}px off settled')
    for face, char in report['missing']:
        print(f'missing {face} {char!r}: absent from new')
    print(f"{len(report['violations'])} violations, "
          f"{len(report['moved'])} moved, "
          f"{len(report['missing'])} missing")
    return 1 if report['violations'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
