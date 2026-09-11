import json, freetype as ft
recs=json.load(open('out/rasters1.json'))
by={(r['ch'],r['px']):r for r in recs}
face=ft.Face('out/Plex400.ttf')
def ft_set(ch,px):
    face.set_pixel_sizes(0,int(px))
    face.load_char(ch, ft.FT_LOAD_RENDER|ft.FT_LOAD_TARGET_MONO|ft.FT_LOAD_MONOCHROME)
    g=face.glyph; bm=g.bitmap; s=set()
    for y in range(bm.rows):
        for x in range(bm.width):
            if (bm.buffer[y*bm.pitch+(x>>3)]>>(7-(x&7)))&1: s.add((g.bitmap_left+x, g.bitmap_top-y))
    return s
def arm_set(r,sec,ras):
    s=r[sec]; w=s['w']; out=set()
    for y in range(s['h']):
        for x in range(w):
            if s[ras][y*w+x]: out.add((s['l']+x, s['t']-y))
    return out
CH=[chr(c) for c in range(0x21,0x7f)]
ARMS=[(('u','zeno'),"UNHINTED + threshold  (today's pipeline)"),
      (('h','zeno'),"Target::Mono + zeno + threshold"),
      (('h','tsk'),"Target::Mono + tiny-skia + threshold"),
      (('h','abg'),"Target::Mono + ab_glyph + threshold")]
print("1-bit vs FreeType FT_RENDER_MODE_MONO (true mono rasterizer, with dropout control).")
print("Aligned on the glyph origin; a differing pixel is one set in exactly one of the two.\n")
print(f"{'size':>5}  {'arm':<40} {'differing px':>13} {'% of ref ink':>13} {'glyphs identical':>17}")
for px in [12.0,16.0,18.0,24.0]:
    refs={ch:ft_set(ch,px) for ch in CH if (ch,px) in by}
    ink=sum(len(v) for v in refs.values())
    for (sec,ras),label in ARMS:
        d=0; same=0
        for ch,ref in refs.items():
            a=arm_set(by[(ch,px)],sec,ras)
            d+=len(a^ref)
            if a==ref: same+=1
        print(f"{int(px):>4}px  {label:<40} {d:>13} {100*d/ink:>12.1f}% {same:>10}/{len(refs)}")
    print()
