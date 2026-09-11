"""Typeface comparison on metrics that have citations.

Perimetric complexity is used here as Pelli et al. (2006) intended -- comparing
TYPEFACES rather than renderings -- which is its validated application.
Lower complexity = higher letter-identification efficiency.
"""
import math, sys
from collections import deque
import freetype as ft
from PIL import Image, ImageChops

S = "/System/Library/Fonts/Supplemental/"
# (label, path, variation coords by axis tag, licence)
FACES = [
    ("IBM Plex Sans", "../../assets/fonts/IBMPlexSans-Variable.ttf", {'wght': 400, 'wdth': 100}, "OFL"),
    ("Source Sans 3", "fonts/SourceSans3.ttf", {'wght': 400}, "OFL"),
    ("Literata",      "fonts/Literata.ttf", {'opsz': 16, 'wght': 400}, "OFL"),
    ("Roboto",        "fonts/Roboto.ttf", {'wght': 400, 'wdth': 100}, "Apache"),
    ("Verdana*",      S + "Verdana.ttf", None, "proprietary"),
    ("Arial*",        S + "Arial.ttf", None, "proprietary"),
    ("Tahoma*",       S + "Tahoma.ttf", None, "proprietary"),
]

def load(path, coords):
    f = ft.Face(path)
    if coords:
        try:
            axes = [a.tag.decode() if isinstance(a.tag, bytes) else a.tag
                    for a in f.get_variation_info().axes]
            f.set_var_design_coords([float(coords.get(t, 0)) for t in axes])
        except Exception as e:
            print(f"    (variation failed: {e})", flush=True)
    return f

def mono(f, ch, px):
    f.set_pixel_sizes(0, px)
    f.load_char(ch, ft.FT_LOAD_RENDER | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_MONOCHROME)
    g = f.glyph; bm = g.bitmap
    grid = [[(bm.buffer[y * bm.pitch + (x >> 3)] >> (7 - (x & 7))) & 1
             for x in range(bm.width)] for y in range(bm.rows)]
    return grid, g.bitmap_left, g.bitmap_top

def cc(g, val, c8):
    if not g or not g[0]: return 0
    H, W = len(g), len(g[0]); seen = [[0] * W for _ in range(H)]; n = 0
    nb = [(-1,0),(1,0),(0,-1),(0,1)] + ([(-1,-1),(-1,1),(1,-1),(1,1)] if c8 else [])
    for y in range(H):
        for x in range(W):
            if g[y][x] == val and not seen[y][x]:
                n += 1; q = deque([(y, x)]); seen[y][x] = 1
                while q:
                    cy, cx = q.popleft()
                    for dy, dx in nb:
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < H and 0 <= nx < W and not seen[ny][nx] and g[ny][nx] == val:
                            seen[ny][nx] = 1; q.append((ny, nx))
    return n

def topo(g):
    if not g or not g[0]: return (0, 0)
    H, W = len(g), len(g[0])
    pad = [[0]*(W+2)] + [[0] + r + [0] for r in g] + [[0]*(W+2)]
    comps = cc(pad, 1, True)
    seen = [[0]*(W+2) for _ in range(H+2)]; q = deque([(0, 0)]); seen[0][0] = 1
    while q:
        cy, cx = q.popleft()
        for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < H+2 and 0 <= nx < W+2 and not seen[ny][nx] and pad[ny][nx] == 0:
                seen[ny][nx] = 1; q.append((ny, nx))
    inner = [[1 if (pad[y][x] == 0 and not seen[y][x]) else 0 for x in range(W+2)] for y in range(H+2)]
    return comps, cc(inner, 1, False)

def complexity(f, ch, px=96):
    f.set_pixel_sizes(0, px)
    f.load_char(ch, ft.FT_LOAD_RENDER | ft.FT_LOAD_NO_HINTING)
    bm = f.glyph.bitmap
    if bm.rows == 0 or bm.width == 0: return None
    im = Image.new('L', (bm.width, bm.rows))
    im.putdata([255 if bm.buffer[y * bm.pitch + x] >= 128 else 0
                for y in range(bm.rows) for x in range(bm.width)])
    A = im.histogram()[255]
    if A == 0: return None
    P = 0
    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
        sh = ImageChops.offset(im, dx, dy)
        if dx: sh.paste(0, (0,0,1,sh.height) if dx > 0 else (sh.width-1,0,sh.width,sh.height))
        if dy: sh.paste(0, (0,0,sh.width,1) if dy > 0 else (0,sh.height-1,sh.width,sh.height))
        P += ImageChops.darker(im, ImageChops.invert(sh)).histogram()[255]
    return (P * P) / (4 * math.pi * A)

CONF = [("I","l"),("l","1"),("I","1"),("O","0"),("5","S"),("8","B"),("c","e"),("r","n"),("g","9")]
TRUE = {'a':(1,1),'b':(1,1),'d':(1,1),'e':(1,1),'o':(1,1),'p':(1,1),'q':(1,1),
        'A':(1,1),'B':(1,2),'D':(1,1),'O':(1,1),'P':(1,1),'R':(1,1),
        '0':(1,1),'8':(1,2),'6':(1,1),'9':(1,1)}

rows = []
for name, path, coords, lic in FACES:
    print(f"measuring {name} ...", flush=True)
    f = load(path, coords)
    xh = max(len(mono(f, c, 96)[0]) for c in "xzvw") / 96
    cap = max(len(mono(f, c, 96)[0]) for c in "HEFT") / 96
    cs = [c for c in (complexity(f, ch) for ch in "abcdefghijklmnopqrstuvwxyz") if c]
    comp = sum(cs) / len(cs)
    # stem width = horizontal ink run at mid x-height of 'l', NOT bitmap width
    # (bitmap width counts serifs on a serif face).
    def stem(px):
        g = mono(f, 'l', px)[0]
        if not g: return 0
        row = g[len(g) // 2]
        best = run = 0
        for v in list(row) + [0]:
            if v: run += 1
            else: best = max(best, run); run = 0
        return best
    stems = {px: stem(px) for px in (16, 20, 26)}
    terr = {}
    for px in (16, 20):
        e = 0
        for ch, exp in TRUE.items():
            got = topo(mono(f, ch, px)[0])
            e += abs(got[0] - exp[0]) + abs(got[1] - exp[1])
        terr[px] = e
    tot = 0.0; n = 0
    for a, b in CONF:
        ga, la, ta = mono(f, a, 16); gb, lb, tb = mono(f, b, 16)
        pa = {(la+x, ta-y) for y, r in enumerate(ga) for x, v in enumerate(r) if v}
        pb = {(lb+x, tb-y) for y, r in enumerate(gb) for x, v in enumerate(r) if v}
        d = min(len(pa), len(pb))
        if d: tot += len(pa ^ pb) / d; n += 1
    rows.append((name, lic, xh, cap, comp, stems, terr[16], terr[20], tot / n))

print()
print(f"{'face':<16}{'licence':<13}{'x-ht/em':>8}{'cap/em':>8}{'cmplx':>8}"
      f"{'stem16':>7}{'stem20':>7}{'stem26':>7}{'topo16':>8}{'topo20':>8}{'confuse':>9}")
print("-" * 101)
for name, lic, xh, cap, comp, st, t16, t20, cf in sorted(rows, key=lambda r: -r[2]):
    print(f"{name:<16}{lic:<13}{xh:>8.3f}{cap:>8.3f}{comp:>8.1f}"
          f"{st[16]:>7}{st[20]:>7}{st[26]:>7}{t16:>8}{t20:>8}{cf:>9.3f}")
print("\n* proprietary: benchmark only, cannot ship. Sorted by x-height/em (higher = more")
print("  effective size per em, the property the e-ink study's winners share).")
print("cmplx: mean perimetric complexity of lowercase. Pelli 2006: efficiency ~ 1/complexity, LOWER better.")
print("stemN: stem pixels for 'l' at N px em. topoN: counters/strokes lost at N px em (0 = none).")
print("confuse: symmetric difference over 9 confusable pairs at 16px, normalised by the")
print("  smaller glyph's ink so stroke weight does not dominate. HIGHER better.")
