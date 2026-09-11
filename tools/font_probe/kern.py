import uharfbuzz as hb, freetype as ft, itertools, string
REPO="../.."
FONTS={
 "IBMPlexSans-Variable": f"{REPO}/assets/fonts/IBMPlexSans-Variable.ttf",
 "ArkPixel-16px-Prop":   f"{REPO}/assets/fonts/ArkPixel-16px-Proportional-Latin.ttf",
 "ArkPixel-12px-Prop":   f"{REPO}/assets/fonts/ArkPixel-12px-Proportional-Latin.ttf",
}
ASCII = "".join(chr(c) for c in range(0x20,0x7f))

def kern_pairs(path, px, variations=None):
    blob = hb.Blob.from_file_path(path); face = hb.Face(blob); font = hb.Font(face)
    upem = face.upem; font.scale = (px*64, px*64)
    if variations: font.set_variations(variations)
    def adv(s):
        buf = hb.Buffer(); buf.add_str(s); buf.guess_segment_properties()
        hb.shape(font, buf, {"kern": True})
        return sum(p.x_advance for p in buf.glyph_positions)
    solo = {c: adv(c) for c in ASCII}
    pairs = {}
    for a, b in itertools.product(ASCII, repeat=2):
        d = adv(a+b) - solo[a] - solo[b]
        if d: pairs[(a,b)] = d/64.0
    return pairs

for name, path in FONTS.items():
    px = 18 if "Plex" in name else (16 if "16px" in name else 12)
    p = kern_pairs(path, px)
    print(f"\n{name} @ {px}px -- {len(p)} kerning pairs over printable ASCII (from GPOS)")
    strong = sorted(p.items(), key=lambda kv: kv[1])[:12]
    print("   strongest negative pairs (px):")
    print("   " + "  ".join(f"{a}{b}:{d:+.2f}" for (a,b),d in strong))
    nonzero_int = sum(1 for d in p.values() if abs(d) >= 0.5)
    print(f"   pairs that move a whole pixel or more: {nonzero_int}")

# variable axis reachability
print("\n" + "="*70)
print("IBM Plex variable axes (fvar):")
face = ft.Face(FONTS["IBMPlexSans-Variable"])
print("   is_variable:", bool(face.is_scalable and face.has_multiple_masters))
mm = face.get_variation_info()
for a in mm.axes:
    print(f"   axis {a.tag.decode() if isinstance(a.tag,bytes) else a.tag}: min={a.minimum/65536} def={a.default/65536} max={a.maximum/65536}")
print("   named instances:")
for i in mm.instances[:12]:
    print("     ", [c/65536 for c in i.coords])
