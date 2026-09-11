import freetype as ft
REPO="../.."
PLEX=f"{REPO}/assets/fonts/IBMPlexSans-Variable.ttf"
face = ft.Face(PLEX)
mm = face.get_variation_info()
print("axes:", [(a.tag, a.minimum, a.default, a.maximum) for a in mm.axes])
print("named instances (wght, wdth):", [tuple(i.coords) for i in mm.instances])

def render(text, px, wght, mono=True):
    f = ft.Face(PLEX); f.set_pixel_sizes(0, px)
    f.set_var_design_coords([wght, 100])
    rows={}; pen=0
    for ch in text:
        f.load_char(ch, ft.FT_LOAD_RENDER | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_MONOCHROME)
        g=f.glyph; bm=g.bitmap
        for y in range(bm.rows):
            for x in range(bm.width):
                if (bm.buffer[y*bm.pitch+(x>>3)] >> (7-(x&7))) & 1:
                    rows.setdefault(g.bitmap_top-y,set()).add(pen+g.bitmap_left+x)
        pen += g.advance.x >> 6
    return rows

def show(rows,label):
    ys=sorted(rows,reverse=True); xs=max(max(s) for s in rows.values())
    print(f"  {label}")
    for y in range(ys[0], ys[-1]-1, -1):
        s=rows.get(y,set()); print("   |"+"".join("#" if x in s else "." for x in range(xs+1)))

for w in (400, 600):
    show(render("Meditamer", 18, w), f"IBM Plex wght={w}, 18px, hinted mono")
