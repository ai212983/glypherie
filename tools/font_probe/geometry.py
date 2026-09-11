"""Angular type size vs Legge & Bigelow (2011) fluent range.

Fluent range: x-height 0.2 deg to 2 deg. Newspapers 0.23 deg, books 0.24 deg.
IBM Plex Sans x-height measured from our own hinted renders = em/2 exactly
(16px em -> 8px x-height, 24px em -> 12px).
"""
import math
MM_IN = 25.4
def dpi(px_w, px_h, diag_in): return math.hypot(px_w, px_h) / diag_in
def pitch_mm(d): return MM_IN / d
def ang_deg(px, pitch, dist_mm): return math.degrees(math.atan2(px * pitch, dist_mm))

PANELS = {
    "Inkplate Tempera": (600, 600, 3.8),
    "Waveshare RLCD42": (300, 400, 4.2),
}
for name,(w,h,d) in PANELS.items():
    dd = dpi(w,h,d); p = pitch_mm(dd)
    print(f"{name}: {w}x{h} on {d}\"  ->  {dd:.1f} DPI, pitch {p:.4f} mm, panel {w*p:.1f} x {h*p:.1f} mm")

print("\nx-height = em/2 (measured). Fluent range 0.20-2.0 deg; books 0.24 deg.\n")
for name,(w,h,d) in PANELS.items():
    p = pitch_mm(dpi(w,h,d))
    dists = [800] if "Inkplate" in name else [800, 500, 400]
    for dist in dists:
        print(f"  {name} @ {dist/10:.0f} cm")
        for em in (12,16,18,24,32,48,64,128):
            a = ang_deg(em/2, p, dist)
            verdict = "FLUENT" if a>=0.20 else ("below fluent" if a>=0.05 else "very small")
            mark = "  <- book-equivalent" if abs(a-0.24)<0.02 else ""
            print(f"    em {em:>4}px  x-height {em/2:>5.1f}px = {em/2*p:>5.2f} mm  ->  {a:.3f} deg  {verdict}{mark}")
        # em needed for fluent minimum and for book size
        for target,lbl in ((0.20,"fluent min"),(0.24,"book")):
            need_mm = math.tan(math.radians(target))*dist
            print(f"    -> {lbl} ({target} deg) needs x-height {need_mm/p:.1f}px, i.e. em ~{2*need_mm/p:.0f}px")
        print()
