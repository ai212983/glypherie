<!-- cspell:words Xteink TEMPERA RLCD Waveshare Soldered Midas MDTR ST7305 ED038TH2 Panic precached precaches datasheet datasheets unparseable Picco BOOX boox -->

# Device previews

Fixed-framebuffer font previews inside original vector shells for supported reflective devices. Scope is preview
presentation, not hardware truth: appearance palettes stay illustrative, and nothing here claims firmware, packing, or
optical calibration.

## Catalog

`apps/web/src/app/devices/devices.json` (validated by `catalog.ts`) is the single device registry. Each entry carries a
stable kebab-case `id`, a human `label`, the native `widthPx`/`heightPx` framebuffer, a finite positive `ppi` with its
`ppiBasis` (`advertised` vendor nominal or `derived` from documented dimensions), and a `shell` reference with `src`,
`viewBox`, and `screenRect`.

Rules enforced at load and in tests:

- IDs unique; labels short human text.
- Framebuffer sides integers within 1..4096.
- Shell `src` a relative `shells/*.svg` asset path.
- `screenRect` inside `viewBox`; its aspect equals `widthPx`/`heightPx`.
- SVGs vector-only: no raster, `image`, or linked content.

Adding a device is data/assets work: one JSON entry plus one SVG. No code switch tables. Shell SVGs ship as static files
under `devices/shells/` beneath the hosting prefix and are precached offline by the service worker's existing svg glob.
`deviceById` returns null for unknown IDs; the UI falls back to the responsive specimen with a notice.

## Profiles and evidence

Research checked November 2026 against primary visual sources (official front renderings/photos, manuals, dimension
diagrams, open-source enclosure CAD). Shell geometry below is sourced, not symbolic. Colors are never device claims; see
the [reflective appearance model](reflective-display-model.md). Shell viewBox units are 0.1 mm so body dimensions read
directly off the artwork.

### Xteink X4 (`xteink-x4`)

- Frame 480 × 800 portrait; 220 PPI advertised nominal.
- Vendor comparison names a 4.3-inch screen at 220 PPI:
  [X4 vs Kindle Basic](https://www.xteink.com/blogs/product/xteink-x4-vs-kindle-basic).
- This is the original X4 (114 × 69 × 5.9 mm, ~77 g per the instruction manual and reviews), not X4 Classic/Pro. Shell
  follows the official front render: black slab, glass to near the edges, two flush bottom rockers in a recessed tray,
  short upper plus long lower key on the right edge, shallow groove low on the left edge, no front branding.
- Portrait orientation follows CrossGlyph's logical 480 × 800 page.

### Xteink X3 (`xteink-x3`)

- Frame 528 × 792 portrait; 259 PPI advertised nominal.
- The [X3 product page](https://www.xteink.com/products/xteink-x3) lists a 3.7-inch display at 259 PPI in a 97.6 × 63.7
  × 5.1 mm, 58 g body.
- Shell follows the official front render: black slab, two flush bottom rockers in a recessed tray, one page key on each
  side edge, two nubs on the top edge (tall right, low flat left), no front branding.
- Portrait orientation follows CrossGlyph's logical 528 × 792 page.

### Inkplate 4 TEMPERA (`inkplate-4-tempera`)

- Frame 600 × 600; 223.3 PPI derived from 600√2 px over the 3.8-inch diagonal (848.5 / 3.8 ≈ 223.3).
- [Overview](https://docs.soldered.com/inkplate/4tempera/overview/) and the
  [datasheets](https://docs.soldered.com/inkplate/4tempera/hardware/design/) specify a 3.8-inch 600 × 600 ED038TH2 touch
  panel; the shell follows the white 3D-printed case with the square glass set high and a wider lower chin, no front
  buttons, text, or screws.
- Enclosed face is the published 90 × 83 × 24 mm nominal, read as 83 mm wide × 90 mm tall: the vendor lists the three
  dimensions without axis labels, and the 90 mm side maps to height (taller-than-wide front in the official front photos
  and [shop photography](https://soldered.com/products/inkplate-4-tempera)). Earlier enclosure-CAD bounding-box readings
  are not used for the face; the STEP files model printed shells, not the assembled front projection. All shell
  dimensions here are nominal manufacturer figures, not measured acceptance.
- Touch is capacitive through the screen; interaction is the touchscreen, not front buttons. Grayscale capability is
  panel fact; the preview keeps the app's own palette machinery with paper as entry 0.

### Waveshare ESP32-S3-RLCD-4.2 (`waveshare-esp32-s3-rlcd-4-2`)

- Frame 400 × 300 landscape; 119.8 PPI derived from the Midas MDTR0420A-SPI active area 84.8 × 63.6 mm as mounted (400 /
  3.3386 ≈ 119.8; vertical agrees). The dot matrix is identical to the panel-native 300 × 400; the product presents it
  landscape.
- Official [dimension diagram](https://docs.waveshare.com/ESP32-S3-RLCD-4.2) (92.50 × 69.10 face, 84.80 × 63.60 active),
  product photography, demo firmware (400 × 300), and the
  [vendor listing](https://www.waveshare.com/esp32-s3-rlcd-4.2.htm?sku=33298) agree on landscape use; the earlier
  portrait catalog entry was a defect and is corrected here. Module datasheet:
  [MDTR0420A-SPI](https://midasdisplays.com/wp-content/uploads/2024/12/MDTR0420A-SPI.pdf).
- Shell is the module face: thin dark frame nearly filled by the panel, orange flex-tab sliver at the right edge.
  Screws, stand, battery, and connectors live on the back/edges and are not front-visible.

### Playdate (`playdate`)

- Frame 400 × 240; 173 PPI advertised by [Panic](https://help.play.date/developer/designing-for-playdate/).
- Shell follows Panic's documented layout on the 76 × 74 mm face: left-offset screen (device center at screen x 228)
  with a 3 mm bezel, right column with face screw, small round menu key and vertical speaker slot, D-pad and A/B below,
  three face screws, lock tab on the top edge, crank docked in a recess on the right edge. The docked crank arm/handle
  is inferred from the open-crank hub position and docked side photos, not from an orthographic docked source.

### BOOX Picco (`boox-picco`)

- Frame 480 × 800 portrait; 235 PPI advertised nominal.
- The [Picco product page](https://shop.boox.com/products/picco) lists a 3.97-inch monochrome display at 235 PPI in a
  105.5 × 62 × 5.5 mm body with capacitive touch, front light, physical buttons, microSD slot, and USB-C port.
- Shell follows the official front render: light slab with rounded corners, screen set high with a wider lower chin, one
  nub low on the left edge, short upper plus long lower key on the right edge, no front branding (the BOOX mark sits on
  the back). Edge ports and slots are not front-visible and are omitted. Side key positions are estimated from front
  product photos, not from a dimension diagram.
- Portrait orientation follows CrossGlyph's logical 480 × 800 page.

### Verification (November 2026)

All six profiles rechecked against live primary sources; the five earlier profiles needed no changes:

- X4: instruction manual (114 × 69 × 5.9 mm, 4.3-inch 480 × 800 at 220 PPI). Art height is the nominal 114 mm body; art
  width is the 69 mm body plus protruding side keys.
- X3: [product page](https://www.xteink.com/products/xteink-x3) (97.6 × 63.7 × 5.1 mm, 3.7-inch at 259 PPI). Pixel
  diagonal agrees within 1%; art contains the nominal body plus side keys, top nubs, and margins.
- Waveshare SKU 33298: [vendor listing](https://www.waveshare.com/esp32-s3-rlcd-4.2.htm?sku=33298) (300 × 400 panel) and
  [dimension diagram](https://docs.waveshare.com/ESP32-S3-RLCD-4.2) (92.50 × 69.10 face, 84.80 × 63.60 active). Art
  matches the face exactly; the aperture matches the active area and the 119.8 PPI derives from it.
- Playdate: [Panic](https://help.play.date/developer/designing-for-playdate/) (400 × 240 at 173 PPI, 3 mm bezel, device
  center at screen x 228) on the 76 × 74 mm face. The aperture matches the PPI size, the offset reproduces 28 px from
  the body center, and the bezel keeps the 3 mm minimum.
- Picco: [product page](https://shop.boox.com/products/picco) (105.5 × 62 × 5.5 mm, 3.97-inch 480 × 800 at 235 PPI).
  Pixel diagonal agrees within 1%; art contains the nominal body plus protruding side keys. The aperture matches the PPI
  active size, sits high with a wider lower chin per the official front render, and carries no front branding. Side key
  positions are estimated from front product photos, not measured.
- Every aperture aspect equals its native aspect exactly; every shipped SVG viewBox matches its catalog entry. Nominal
  body bounds and full art bounds stay distinct: art includes protruding keys, crank, lock tab, and margins where the
  device has them.

## Presentation

- The render always targets the full native frame; viewport resize and zoom never rewrap text or resize the bitmap.
- Actual size renders at `96 / ppi` CSS px per device pixel: the 96 CSS reference density, which is unmeasured. The
  browser exposes no physical monitor width, so no universal formula can recover true physical size; only Pixel 1:1 is
  exact.
- Pixel 1:1 renders at `1 / devicePixelRatio` CSS px per device pixel, so one device pixel covers one physical monitor
  pixel at any DPR.
- Backing stays an integer multiple of the framebuffer; only CSS scales.
- Shell and screen scale together from the aperture via `deviceLayout`.

## Screen monitor info

The standalone Screen page (`/screen/`) centers on the device selector, the device readout, the rendered shell, and one
quiet "Preview size is approximate." note. A closed-by-default "Display details" disclosure holds only what the browser
can actually measure: screen area in CSS px and the live device pixel ratio, plus a Preview size slider (50–150%,
default 100%) that multiplies the reference-size scale for body and paper together, and an approximate 50 mm ruler (5 mm
divisions, numbered every 10 mm) following the same percentage with a match-to-physical-ruler hint. Physical length
stays approximate; no standard browser API exposes physical monitor size or true PPI. The readout refreshes on resize
and DPR transitions with no permission flow.

## Viewing preferences

Stored under `font-preview.device` (viewer state only; never in font settings, URLs, or saved variants):

- `device`: catalog ID or null for the responsive specimen.
- `scale`: `actual` or `one-to-one`.

The Screen preview-size percentage is stored separately under `font-preview.screen.size` (viewer state only; same
exclusions). Absent, malformed, or unreadable storage means 100%; out-of-range values clamp to 50–150%.

A legacy `calibration` field (previously backing manual monitor calibration) is dropped by an explicit read-time
migration that preserves the selected device and scale and rewrites only `font-preview.device`. The Screen page's device
choice stays local page state and never writes the editor's selected `device` or `scale`.

Unknown stored IDs recover to the specimen; stale `scale` values recover to `actual`; unparseable storage recovers to
defaults.
