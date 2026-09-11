"""Angular type scale for two viewing modes.

Fluent range (Legge & Bigelow 2011): angular x-height 0.2-2.0 deg.
Books 0.24 deg, newspapers 0.23 deg. Watson visual blur sigma = 2.33 arcmin;
the perimetric-complexity metric needs sigma/x-height <= ~0.20 to discriminate.
"""
import math
MM_IN=25.4; SIG=2.33
PANELS={"Inkplate":(600,600,3.8),"Waveshare":(300,400,4.2)}
MODES={"ambient":(800,1000),"reading":(400,500)}
def pitch(n):
    w,h,d=PANELS[n]; return MM_IN/(math.hypot(w,h)/d)
def em_for(n, deg, dist):
    """em px so that x-height (= em/2) subtends `deg` at `dist` mm."""
    return 2*math.tan(math.radians(deg))*dist/pitch(n)
def ang(n, em, dist):
    return math.degrees(math.atan2(em/2*pitch(n), dist))
def sig_ratio(n, em, dist):
    apx=math.degrees(math.atan2(pitch(n),dist))*60.0
    return (SIG/apx)/(em/2)

print("Recommended em px, so x-height lands in the fluent range\n")
print(f"{'panel':<11}{'mode':<9}{'distance':<11}{'fluent min 0.20':>17}{'book 0.24':>12}{'generous 0.30':>15}")
for n in PANELS:
    for m,(near,far) in MODES.items():
        for dist in (near,far):
            print(f"{n:<11}{m:<9}{dist/10:>4.0f} cm    "
                  f"{em_for(n,0.20,dist):>14.0f}px{em_for(n,0.24,dist):>10.0f}px{em_for(n,0.30,dist):>13.0f}px")
    print()

print("Sizes actually in use, judged at the mode they belong to\n")
CURRENT=[
 ("Inkplate","ambient",1000,128,"Ambient clock (compiled)"),
 ("Inkplate","ambient",1000, 64,"Ambient environment (compiled)"),
 ("Inkplate","ambient", 800,128,"Ambient clock"),
 ("Inkplate","ambient", 800, 64,"Ambient environment"),
 ("Inkplate","reading", 400, 32,"Montserrat 32 (carousel arrows)"),
 ("Inkplate","reading", 400, 24,"Montserrat 24 (titles)"),
 ("Inkplate","reading", 500, 24,"Montserrat 24 (titles)"),
 ("Inkplate","reading", 400, 18,"Montserrat 18 (body)"),
 ("Inkplate","reading", 400, 14,"Montserrat 14 (catalogue/overlay)"),
 ("Waveshare","reading",400, 16,"Ark Pixel 16 (Home heading)"),
 ("Waveshare","reading",500, 16,"Ark Pixel 16 (Home heading)"),
 ("Waveshare","reading",400, 14,"GohuFont 14 (crash screen)"),
 ("Waveshare","reading",400, 12,"Ark Pixel 12 (Home caption)"),
 ("Waveshare","reading",500, 12,"Ark Pixel 12 (Home caption)"),
]
print(f"{'panel':<11}{'mode':<9}{'dist':>6}{'em':>5}{'x-ht':>6}{'angular':>10}{'verdict':<16}{'metric':<12} what")
for n,m,dist,em,what in CURRENT:
    a=ang(n,em,dist); r=sig_ratio(n,em,dist)
    v = "FLUENT" if a>=0.20 else ("marginal" if a>=0.17 else "below fluent")
    mt = "applicable" if r<=0.20 else ("marginal" if r<=0.35 else "not applicable")
    print(f"{n:<11}{m:<9}{dist/10:>4.0f}cm{em:>5}{em/2:>6.0f}{a:>9.3f}d  {v:<16}{mt:<12} {what}")
