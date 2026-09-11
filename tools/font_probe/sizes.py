"""Per-face, per-panel size sets.

em is derived from a target angular x-height, each face's own measured
x-height/em ratio, the panel's pixel pitch, and the FAR end of the mode's
distance range (so the size holds across the whole range).

    em_px = tan(theta) * distance / (pitch * xheight_ratio)

Angular targets follow Legge & Bigelow (2011): fluent range 0.2-2.0 deg of
x-height, books at 0.24 deg.
"""
import math

MM_IN = 25.4
PANELS = {  # name: (px_w, px_h, diagonal_in, usable_width_px)
    "Inkplate":  (600, 600, 3.8, 600),
    "Waveshare": (300, 400, 4.2, 300),
}
# measured with tools/font_probe/faces.py
XH = {
    "IBM Plex Sans": 0.521,
    "Roboto":        0.531,
    "Literata":      0.510,
    "Source Sans 3": 0.490,
}
# role: (mode, near_mm, far_mm, target_deg)
ROLES = [
    ("ambient-primary",   "ambient", 800, 1000, 0.42),
    ("ambient-secondary", "ambient", 800, 1000, 0.24),
    ("reading-heading",   "reading", 400,  500, 0.31),
    ("reading-body",      "reading", 400,  500, 0.24),
    ("reading-caption",   "reading", 400,  500, 0.20),
]

def pitch(p):
    w, h, d, _ = PANELS[p]
    return MM_IN / (math.hypot(w, h) / d)

def em_for(face, panel, deg, dist):
    return math.tan(math.radians(deg)) * dist / (pitch(panel) * XH[face])

def ang(face, panel, em, dist):
    return math.degrees(math.atan2(em * XH[face] * pitch(panel), dist))

def even(x):
    return max(2, int(round(x / 2.0)) * 2)

for panel in PANELS:
    print(f"\n{'='*96}\n{panel}  --  {MM_IN/pitch(panel)*1:.0f} DPI equivalent, pitch {pitch(panel):.4f} mm\n{'='*96}")
    print(f"{'role':<19}{'target':>7}" + "".join(f"{f:>17}" for f in XH))
    for role, mode, near, far, deg in ROLES:
        cells = []
        for face in XH:
            em = even(em_for(face, panel, deg, far))
            xh = em * XH[face]
            a_near = ang(face, panel, em, near)
            a_far = ang(face, panel, em, far)
            cells.append(f"{em:>4}px x{xh:>4.1f} {a_far:.2f}d")
        print(f"{role:<19}{deg:>6.2f}d" + "".join(f"{c:>17}" for c in cells))

    print(f"\n  {'role':<19}{'chars/line at that em (panel width / 0.5 em)':<45}")
    for role, mode, near, far, deg in ROLES:
        cs = []
        for face in XH:
            em = even(em_for(face, panel, deg, far))
            cs.append(f"{PANELS[panel][3]/(em*0.5):>5.0f}")
        print(f"  {role:<19}" + "".join(f"{c:>17}" for c in cs))

print("\n\nNotes")
print("-----")
print("em rounded to even so x-height stays a whole number of pixels where possible.")
print("x-height below ~7px is fragile in 1-bit: counters start closing and stems drop out.")
print("Angular value shown is at the FAR end of the mode (1 m ambient, 50 cm reading);")
print("at the near end every size is correspondingly larger and still inside the fluent range.")
print("\nx-height/em ratios measured (faces.py):")
for f, r in sorted(XH.items(), key=lambda kv: -kv[1]):
    print(f"  {f:<16}{r:.3f}")
