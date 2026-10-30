# Front-page converter comparisons

<!-- cspell:words Adafruit Crosspoint cpfont fontconvert sdcard thresholding pdfontconv Tophat GFXfont HarfBuzz -->

The web app's [capture commands](../../apps/web/README.md#front-page-samples) compare the same static font instance,
native pixel size, sample text, baseline and origin. Converters retain their exported advances; source kerning is
enabled with zero tracking, and Glypherie retains its fitted pair corrections. Capture records preserve settings, source
identities, original exports and repeated-export verification. Mechanical fidelity does not establish optical
acceptance.

## Source kerning

Glypherie, pdfontconv, LVGL and Crosspoint use their exported pair data. The pdfontconv capture explicitly sets Canvas
[`fontKerning=normal`](https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/fontKerning) before its
stock measured-pair export, avoiding the browser's small-size `auto` policy. LVGL and Crosspoint retain their signed 4.4
pair storage; LVGL rounds each combined advance and pair step to whole pixels, while Crosspoint accumulates fractional
positions. Playdate pairs are whole pixels.

Tophat's stock outline import does not import source kerning, and Adafruit's `GFXfont` has no kerning table. Their
comparison composition adds source-font pair adjustments from [HarfBuzz](https://github.com/harfbuzz/uharfbuzz), with
ligatures and contextual alternates disabled, rounded to whole pixels. Glyph exports and advances remain unchanged.
These two images demonstrate supplemented composition, rather than stock converter layout. The adapter rejects
substitutions or positioning that cannot be represented by one horizontal pair adjustment. Capture records name the pair
source, and each run retains the applied pair values beside the original exports.

If LVGL's source parser exports no pairs although HarfBuzz finds nonzero source adjustments, its composition also uses
HarfBuzz pairs. This applies to the current Literata samples. Native exported advances remain intact; pair values follow
LVGL's 4.4 scaling and combined-step rounding. Captures explicitly identify this fallback. Nonempty native tables are
used directly, without adding source adjustments a second time.

## Crosspoint

The capture uses
[`fontconvert_sdcard.py` at revision 10709120](https://github.com/crosspoint-reader/crosspoint-reader/blob/10709120e66c0e0604aebc4991cc69830fb4c2b2/lib/EpdFont/scripts/fontconvert_sdcard.py),
which exports `.cpfont` v4 with four coverage levels and fractional advances. Its point-size call at 150 DPI is replaced
with an exact pixel-size call, as in the existing Adafruit adapter. Glyph loading, native hinting, quantization and
packing remain upstream behavior. Source and adapted script hashes are recorded separately. This is a normalized
comparison, not a capture of the stock command at the same numeric point size.

The monochrome sample follows the firmware's
[BW glyph drawing rule](https://github.com/crosspoint-reader/crosspoint-reader/blob/10709120e66c0e0604aebc4991cc69830fb4c2b2/lib/GfxRenderer/GlyphBitmap.h):
coverage 0 stays white; levels 1, 2 and 3 become black. This differs from midpoint thresholding. The adapter preserves
packed bit order, glyph bearings and 12.4 advances; native source kerning is applied and ligatures are disabled. The
original gray-level `.cpfont` export remains in the run directory. The front page shows composed font output, not a
device screenshot or the firmware's complete text-layout engine.

With anti-aliasing enabled, Crosspoint renders a black-and-white base and gray masks. On supported panels, the display
driver uses grayscale update waveforms to produce intermediate tones. A strictly binary update cannot show those tones.
The SDK's
[grayscale capabilities](https://github.com/Free-Ink/freeink-sdk/blob/946e6ac3d7a9d590ba3224428e6183d55ac7917c/docs/grayscale-capabilities.md)
describe support, plane encoding and fallback; support alone does not establish physical tone fidelity.

## CrossGlyph

[CrossGlyph](https://github.com/CrazyCoder/crossglyph/tree/7c106a5ec3d4cc9aa783e432434e5bacb2b1790b) is a separate
converter fork with tuning controls, including a true monochrome rasterization option. Its
[internals](https://github.com/CrazyCoder/crossglyph/blob/7c106a5ec3d4cc9aa783e432434e5bacb2b1790b/docs/internals.md)
describe the fork and a preview built from Crosspoint's rendering code. Its mono-rasterization setting changes the
generated glyphs; its preview's anti-aliasing switch changes how existing coverage levels are painted. It is a separate
potential comparison entry, not the converter used for the Crosspoint sample.
