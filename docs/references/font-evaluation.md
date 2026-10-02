# Font sizing and rendering evaluation

Recommended sizes for Inkplate and Waveshare, with methods for comparing font rendering and evaluating text on
monochrome and low-bit-depth displays. Research sources and their scope are listed in the
[research corpus](papers/CORPUS.md).

## Reading and viewing distances

Use **38 px on Inkplate and 20 px on Waveshare for normal reading**, and **94 px and 50 px for the main message read at
a glance**.

| Mode    | Use                             | Viewing distance |
| ------- | ------------------------------- | ---------------- |
| Reading | Using the device                | 40–50 cm         |
| Ambient | Occasional glance at the screen | 80–100 cm        |

The sizes below use the longest distance in each range: **50 cm for reading** and **100 cm for ambient glances**.

## How size is chosen

Font sizes are in **screen pixels (px)**. A lowercase letter such as `x` is usually shorter than the font's stated size.
Its height is called **x-height**. The table assumes this is **half the font size**, consistent with IBM Plex Sans
measurements: 16 px gives an 8 px x-height, and 24 px gives 12 px. Under this assumption, a 38 px font has a 19 px
x-height. Sizes are rounded up to even numbers.

| Device           | Resolution   | Screen diagonal | Pixel width  |
| ---------------- | ------------ | --------------- | ------------ |
| Inkplate Tempera | 600 × 600 px | 3.8 in          | 0.1137 mm/px |
| Waveshare RLCD42 | 300 × 400 px | 4.2 in          | 0.2134 mm/px |

A letter looks smaller as viewing distance increases. Researchers describe its apparent height as an **angle in
degrees**. [Legge and Bigelow (2011)][legge] found that people with normal vision can read at full speed over a range of
roughly **0.2–2° of x-height**, with book text averaging **0.24°**. We use 0.20° for small labels and 0.24° for normal
text. Smaller text can still be read.

In [Dobres et al. (2016)][glance], larger text was easier to recognise during brief glances. The larger sizes below are
suggestions for making the main message stand out, based on this research.

Record pixel pitch `p`, viewing distance `d`, and rendered x-height `h` in pixels. Angular height is `2 * atan((h * p) /
(2 * d))`, with `p` and `d` in the same units; convert radians to degrees. Derive em size from the face's measured
x-height ratio and verify the actual raster. Evaluate both ends of the distance range and the intended recognition task.

## Recommended sizes

| Mode    | Use                    | Target x-height angle | Inkplate  | Waveshare |
| ------- | ---------------------- | --------------------- | --------- | --------- |
| Reading | Small label or caption | 0.20°                 | 32 px     | 18 px     |
| Reading | Normal text or menu    | 0.24°                 | **38 px** | **20 px** |
| Reading | Heading or larger text | 0.30°                 | 48 px     | 26 px     |
| Ambient | Smaller label          | 0.24°                 | 74 px     | 40 px     |
| Ambient | Main message           | 0.30°                 | **94 px** | **50 px** |
| Ambient | Large clock or number  | 0.42°                 | 130 px    | 70 px     |

At twice the distance, a font needs to be about twice as large to look the same size. Inkplate needs about **1.88 times
as many pixels** as Waveshare for letters of the same physical height. Numbers and icons can have different heights from
lowercase letters, so these sizes are starting points for them.

## Other fonts and smaller text

Fonts with taller lowercase letters can use a smaller font size. If lowercase letters are 60% of the font size, instead
of the assumed 50%, the font can be about 17% smaller and look equally tall. In general, multiply the table size by
`0.50 / x-height fraction` and round up.

Smaller text fits more content but is harder to read. On Waveshare, **14 px** with lowercase letters at half the font
size gives **0.214° at 40 cm** but **0.171° at 50 cm**. It reaches the 0.20° reading target at 40 cm, but falls below it
at 50 cm. Use such sizes for optional details.

## Separate the rendering variables

Separate the variables: `face/axes → hinting → coverage → positioning/compositing → quantization → panel`. Change one at
a time. Equal em sizes do not equalize visible height; compare weights, polarities, and actual glyph geometry. Luminance
thresholds and ink-coverage thresholds have different effects. Test dithering across fragmented redraws and measure
panel response and refresh history when gray-level fidelity matters.

## Reproducible comparisons

For comparisons, retain font hashes, licenses, axes, repertoire, sizes, engine versions, hinting, placement, thresholds,
and bit depth. Use identical outlines and glyph origins/baselines. FreeType measures implementation fidelity, not
reading superiority; mono dropout handling differs from AA-then-threshold. Test shaped text runs as well as pairs:
legacy kerning alone does not cover GPOS, substitutions, or marks.

## Measurements and their limits

| Measure                         | Use                                 | Limit                                                       |
| ------------------------------- | ----------------------------------- | ----------------------------------------------------------- |
| Stroke/counter topology         | Broken joins and closed counters    | Define connectivity and verify against the intended glyph   |
| X-height, cap height, stem runs | Grid fitting and weight consistency | Overshoot and varying widths may be intentional             |
| Pairwise pixel difference       | Candidate glyph confusions          | Alignment-sensitive; not a human confusion rate             |
| Perimetric complexity           | Shape complexity                    | Renderer ranking extrapolates from identification research  |
| Spatially filtered difference   | Quantization error                  | Requires viewing/luminance assumptions; not reading success |
| Changed pixels/repeatability    | Redraw instability                  | Does not establish physical readability                     |

## Image review and panel evaluation

[Panel frame formats](panel-frame-formats.md) records the binary bit order, grayscale polarity, and file framing used by
the specimen viewers. Keep coverage quantization separate from conversion into the panel's stored pixel values.

Review native-pixel specimens and enlarged strokes/counters across glyphs, sizes, families, and polarities. Turn
repeated defects into diagnostics with saved settings and images; scalar scores and topology checks alone cannot
establish quality.

Then test actual UI layouts on the panel, including digits, punctuation, units, and confusable groups (`Il1 O0 5S 8B 69
rn`). Record lighting, distance, refresh history, and observer responses. Keep generated output, panel appearance, and
reader performance as separate evidence.

[legge]: https://legge.psych.umn.edu/sites/legge.psych.umn.edu/files/2020-08/Legge%20Bigelow%202011%20Does%20size%20matter%20for%20reading%3F%20A%20review%20of%20findings%20from%20vision%20science%20and%20typography.pdf
[glance]: https://jdobr.es/pdf/Dobres-etal-2016-Ergonomics-Typeface.pdf
