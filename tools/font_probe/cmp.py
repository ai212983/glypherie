import freetype as ft
from freetype import FT_LOAD_NO_HINTING, FT_LOAD_TARGET_MONO, FT_LOAD_RENDER, FT_LOAD_TARGET_LIGHT, FT_LOAD_MONOCHROME

REPO="../.."
PLEX=f"{REPO}/assets/fonts/IBMPlexSans-Variable.ttf"

def render(path, text, px, mode, wght=None):
    face = ft.Face(path)
    face.set_pixel_sizes(0, px)
    if wght is not None:
        try: face.set_var_design_coords([wght])
        except Exception as e: print("   (variation failed:", e, ")")
    rows = {}
    pen = 0
    boxes=[]
    for ch in text:
        if mode == "aa_nohint":
            face.load_char(ch, FT_LOAD_RENDER | FT_LOAD_NO_HINTING)
        elif mode == "mono_hinted":
            face.load_char(ch, FT_LOAD_RENDER | FT_LOAD_TARGET_MONO | FT_LOAD_MONOCHROME)
        elif mode == "light_hinted":
            face.load_char(ch, FT_LOAD_RENDER | FT_LOAD_TARGET_LIGHT)
        g = face.glyph; bm = g.bitmap
        boxes.append((ch, bm.width, bm.rows, g.bitmap_top))
        for y in range(bm.rows):
            for x in range(bm.width):
                if bm.pixel_mode == 1:  # mono
                    v = (bm.buffer[y*bm.pitch + (x>>3)] >> (7-(x&7))) & 1
                    on = v == 1
                else:
                    on = bm.buffer[y*bm.pitch + x] >= 128
                if on:
                    rows.setdefault(g.bitmap_top - y, set()).add(pen + g.bitmap_left + x)
        pen += g.advance.x >> 6
    return rows, boxes

def show(rows, label):
    if not rows: return
    ys = sorted(rows.keys(), reverse=True)
    xs = max(max(s) for s in rows.values() if s)
    print(f"  {label}")
    for y in range(ys[0], ys[-1]-1, -1):
        s = rows.get(y, set())
        print("   |" + "".join("#" if x in s else "." for x in range(0, xs+1)))

TEXT = "Meditamer Home"
for px in (18, 24):
    print(f"\n{'='*70}\nIBM Plex Sans @ {px}px  --  text: {TEXT!r}\n{'='*70}")
    a,ba = render(PLEX, TEXT, px, "aa_nohint")
    show(a, f"A. unhinted AA + threshold>=128  (what tools/lvgl_font_compiler does today)")
    b,bb = render(PLEX, TEXT, px, "mono_hinted")
    show(b, f"B. FreeType TARGET_MONO, hinted   (grid-fitted, drop-out control)")
    # consistency metric: heights of round vs flat lowercase
    da = {c:(h,t) for c,w,h,t in ba}
    db = {c:(h,t) for c,w,h,t in bb}
    print("\n   per-glyph (height, top) -- A unhinted vs B hinted:")
    for c in "Meditam":
        print(f"     {c!r}: A={da[c]}  B={db[c]}")
