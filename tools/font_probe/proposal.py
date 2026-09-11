import math
MM_IN=25.4; SIG=2.33
PANELS={"Inkplate":(600,600,3.8,600),"Waveshare":(300,400,4.2,300)}
def pitch(n):
    w,h,d,_=PANELS[n]; return MM_IN/(math.hypot(w,h)/d)
def ang(n,em,dist): return math.degrees(math.atan2(em/2*pitch(n), dist))
def sigr(n,em,dist):
    apx=math.degrees(math.atan2(pitch(n),dist))*60.0
    return (SIG/apx)/(em/2)
PROPOSAL=[
 ("Inkplate","ambient-primary",  (800,1000),128,"clock"),
 ("Inkplate","ambient-secondary",(800,1000), 72,"environment / status"),
 ("Inkplate","reading-heading",  (400,500),  48,"screen titles"),
 ("Inkplate","reading-body",     (400,500),  36,"body / controls"),
 ("Inkplate","reading-caption",  (400,500),  32,"captions / overlays"),
 ("Waveshare","ambient-primary", (800,1000), 64,"clock"),
 ("Waveshare","ambient-secondary",(800,1000),40,"environment / status"),
 ("Waveshare","reading-heading", (400,500),  26,"screen titles"),
 ("Waveshare","reading-body",    (400,500),  20,"body / controls"),
 ("Waveshare","reading-caption", (400,500),  16,"captions / overlays"),
 ("Waveshare","DEVIATION",       (400,500),  14,"crash screen (declared)"),
]
print(f"{'panel':<11}{'role':<19}{'em':>4}{'x-ht':>6}   angular near..far   verdict          sig/xh  chars/line  what")
for n,role,(near,far),em,what in PROPOSAL:
    a_near=ang(n,em,near); a_far=ang(n,em,far)
    ok = "fluent" if a_far>=0.20 else ("marginal" if a_far>=0.17 else "BELOW (declared)")
    r=sigr(n,em,far); cpl=PANELS[n][3]/(em*0.5)
    print(f"{n:<11}{role:<19}{em:>4}{em//2:>6}   {a_near:.3f}..{a_far:.3f} deg   {ok:<16}{r:>6.2f}{cpl:>10.0f}      {what}")
print("\nchars/line assumes average advance ~0.5 em (measured for IBM Plex Sans).")
print("sig/xh <= 0.20 means the perimetric-complexity metric discriminates at that size.")
