# Font legibility on low-bit-depth displays

Research, rendering theory, and evaluation methods for text on monochrome and
low-bit-depth displays. This reference does not prescribe the shipping fonts,
size table, or generator implementation. Those decisions and their status live
in the [active plan](../plans/font-legibility-improvements.md); commands live in
[font_probe](../../tools/font_probe/README.md).

## Reading order and papers

1. [FreeType: hinting, text rendering, stem darkening and LCD filters](https://freetype.org/freetype2/docs/hinting/text-rendering-general.html)
   explains how grid fitting, coverage, blending, and weight interact. Use it to
   distinguish a glyph-outline problem from a compositing or quantization problem.
2. [Legge & Bigelow (2011), Does print size matter for reading?](https://pmc.ncbi.nlm.nih.gov/articles/PMC3428264/)
   relates physical size and viewing distance to reading speed. Its approximate
   fluent range is 0.2–2 degrees of angular **x-height**, not nominal em size.
   This describes maximum reading speed, primarily for normally sighted readers;
   it is neither a universal readability cutoff nor a validation of glanceable
   digits, symbols, or accessibility for low-vision users.
3. [Pelli et al. (2006), Feature detection and letter identification](https://denispelli.com/pubs/pelli2006letters.pdf)
   relates letter-identification efficiency in visual noise to perimetric
   complexity. It motivates comparing letterforms, but does not establish a
   universal score for UI readability or renderer quality.
4. [Watson (2012), Perimetric complexity of binary digital images](https://www.mathematica-journal.com/2012/02/17/perimetric-complexity-of-binary-digital-images/)
   explains why perimeter measurement on a pixel grid needs care and introduces
   visual complexity that accounts for visual blur. Read before implementing a
   complexity metric; counting exposed pixel edges is not an interchangeable model.
5. [Zhang & Wandell, S-CIELAB implementation](https://github.com/wandell/SCIELAB-1996)
   and [Zhang et al. (1997), spatial color fidelity study](https://web.stanford.edu/~jefarrel/Publications/1990s/1997_Zhang_Silverstein_Farrell_Wandell.pdf)
   provide spatial filtering methods for image-difference evaluation. A grayscale
   adaptation needs explicit luminance, viewing geometry, and filtering choices;
   a generic blurred pixel difference should not be labelled validated S-CIELAB.

Further reading:

- [Hobby, Generating Automatically-Tuned Bitmaps from Outlines (1993)](https://doi.org/10.1145/138027.138040)
  ([technical-report text](https://telecom.wiki/download/attachments/819301/CSTR%20148.pdf))
  targets automatic outline-to-bitmap conversion without hand editing. The report's
  section 3 combines shape/position distortion, stroke and white-space features,
  grid restrictions and font-wide consistency; section 6 discusses curved outlines.
- [Herz & Hersch, Towards a Universal Auto-Hinting System for Typographic Shapes (1994)](https://lspwww.epfl.ch/publications/typography/tuahsts.pdf)
  gives automatic black/white stem detection, shared metrics and an ordered
  displacement procedure. Section 3 explicitly leaves curved stems and terminal
  elements to future work; it is not a complete solution for curved bowl defects.
- [Hersch & Bétrisey, Model-based Matching and Hinting of Fonts (1991)](https://lspwww.epfl.ch/publications/typography/mbmahof.pdf)
  matches outlines to structural letter models, then transfers applicable hints.
  The method requires model descriptions and shape variants.

- [Hersch, Font Rasterization: The State of the Art (1993)](https://lspwww.epfl.ch/publications/typography/frsa.pdf)
  surveys scan conversion and grid fitting. Sections 5–6 (printed pp. 90–99) cover
  shared stroke widths, symmetry-axis placement and diagonal border constraints.
  Figure 25 fits parallel diagonal borders to an integer horizontal separation.
- [Zongker, Wade & Salesin, Example-Based Hinting of TrueType Fonts](https://grail.cs.washington.edu/wp-content/uploads/2015/08/Zongker2000.pdf)
  transfers hints from annotated model fonts between matched glyphs, using shared
  control values across fonts.
  It addresses both local features and consistent stem sizes, with human refinement.
- [Shamir & Rappoport, Extraction of Typographic Elements from Outline Representations of Fonts (1996)](https://cris.huji.ac.il/en/publications/extraction-of-typographic-elements-from-outline-representations-o/)
  ([author's full text](https://pages.cs.huji.ac.il/sites/www-arir/storage/extraction-typographic-elements.pdf))
  describes extracting stems, serifs, bows, arcs and curved strokes, with an
  automatic hinting application. Sections 3–4 require prepared curve points,
  tolerance-aware segment classification and separate feature definitions.
  Serif recognition uses reusable finite automata. Full text reviewed.
- [Shamir & Rappoport, Quality Enhancements of Digital Outline Fonts (1997)](https://doi.org/10.1016/S0097-8493(97)00049-6)
  — outline preparation, including contour orientation and interpenetration
  correction. The [coauthor's abstract](https://pages.cs.huji.ac.il/sites/www-arir/storage/quality-abs.html)
  establishes the scope; the complete preparation algorithm has not been verified.
  Modern Boolean boundary normalization is an implementation choice, not recovered
  source code from this paper.
- [Shamir & Rappoport, LiveType: A Parametric Font Model Based on Features and Constraints (1997)](https://history.siggraph.org/wp-content/uploads/2022/11/SIGGRAPH-1997-Visual-Proceedings.pdf)
  — SIGGRAPH Visual Proceedings, p.160. Describes conversion to an acyclic graph,
  but supplies no detailed shared-corner algorithm; distinct from technical report TR-97-11.
- [Shamir & Rappoport, Feature-based Design of Fonts Using Constraints (1998)](https://www.researchgate.net/publication/2506331_Feature-based_design_of_fonts_using_constraints)
  — §4.2 explicitly separates dependencies into X- and Y-oriented graphs and
  refers to TR-97-11 for details. This predecessor design system informs solver
  alternatives, but does not establish the 2003 autohinter's overlap policy.
- [Shamir, Constraint-based Approach for Automatic Hinting of Digital Typefaces (2003)](https://doi.org/10.1145/636886.636887)
  — [local full text](fonts/papers/shamir-2003-constraint-based-hinting.pdf)
  ([full-text reader](https://dl.acm.org/doi/epdf/10.1145/636886.636887))
  extracts typographic features, links point constraints to font-wide measurements,
  removes lower-priority conflicting constraints and orders the remainder before
  emitting hints. Sections 3.3–3.6 cover detection and graph resolution; section
  3.5 requires predefined constraints or declarative hints for complex features
  such as serifs. The method acknowledges a gap to expert manual hinting.
- [Microsoft VTT language reference: SERIF](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/doc/VTT%20Language%20Reference/vttlang.html#L827-L876)
  documents stem/baseline prerequisites and separate vertical and diagonal
  half-serif recipes. The [compiler implementation](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L1600-L1810)
  uses serif extension, thickness and height control values. This is a concrete
  reference for the declarative route in Shamir 2003; equivalence to its historical
  VTT version remains unverified. [Microsoft's grid-fitting tutorial](https://learn.microsoft.com/en-us/typography/truetype/fixing-rasterization-issues)
  explains linked distances, interpolation and conflicting rounding requirements.
  [Microsoft's diagonal-hinting examples](https://learn.microsoft.com/en-us/typography/truetype/italic-hinting-examples)
  establish parent coordinates before relative diagonal control; the serif example
  uses unrounded/interpolated parent placement. This supports investigating local
  parent anchoring separately from rounded diagonal widths.
- [Stamm, Hitchcock & Duggan, Iteratively solving constraints in a font-hinting language](https://patents.google.com/patent/US7187382B2)
  — Microsoft technical disclosure describing repeated native hint operations
  for coupled constraints. Its stopping rules include a movement tolerance and
  an iteration cap; termination alone does not establish an accurate solution.
- [Turner & Lemberg, Real-Time Grid Fitting of Typographic Outlines (2003)](https://www.tug.org/TUGboat/tb24-3/lemberg.pdf)
  describes segment grouping, mutual-best stem pairing, serif relationships,
  round/flat classification, font-wide alignment zones and ordered fitting.
  Opposite contour directions are one part of this system. The paper explicitly
  leaves some placement details to its FreeType implementation. Its practical
  descendant [ttfautohint](https://freetype.org/ttfautohint/doc/ttfautohint.html)
  documents that diagonal lines receive no special handling.
- [Berio et al., StrokeStyles (2022)](https://doc.gold.ac.uk/autograff/post/papers/strokestyles_2022/)
  extracts strokes and junctions using outline geometry and interior/exterior
  medial axes, with [implementation code](https://github.com/autograff-devel/strokestyles).
  It supports structural analysis without training examples or templates;
  its demonstrated application is stylization. Low-resolution grid fitting would
  require a separate method and validation.
- [Anderson, Shamir & Fried, Neural Font Rendering (2022)](https://arxiv.org/abs/2211.14802)
  learns size-dependent glyph images from existing raster examples. It studies
  multi-scale rendering directly, but relies on memorizing target images and
  reports remaining artifacts, including difficulty with complex curved glyphs.
  It provides an alternative representation rather than a demonstrated automatic
  repair method for arbitrary source outlines.
- [Kajiya & Ullner, Filtering High Quality Text for Display on Raster Scan Devices](https://www.cs.jhu.edu/~misha/ReadingSeminar/Papers/Kajiya81.pdf)
  studies text filtering for grayscale CRT displays. Its filtering rationale is
  relevant to offset averaging; its display assumptions differ from bilevel panels.
- [Microsoft, Fixing rasterization issues at low resolutions](https://learn.microsoft.com/en-us/typography/truetype/fixing-rasterization-issues)
  is a practical companion on grid fitting and defects such as unequal stems and
  disjoined arches, rather than a research paper.

- [Developing a Typeface for Low Resolution E-Ink Displays](https://www.researchgate.net/publication/324671274_Developing_a_Typeface_for_Low_Resolution_E-Ink_Displays)
  is a directly relevant study to inspect for its fonts, device, tasks, and reader
  population before transferring any ranking to another panel.
- [EPFL/LSP typography publications](https://lspwww.epfl.ch/publications/typography/lptgf.html)
  collect grayscale and bilevel typography work. Benefits of physical gray levels
  do not by themselves demonstrate benefits from binary spatial dithering.

## Separate the rendering variables

A useful experimental decomposition is:

`face and axes -> hinting -> raster coverage -> positioning/compositing -> quantization -> panel`

Change one dimension at a time when attributing an improvement. A different face,
weight, size, or optical-size axis can outweigh a rasterizer change. Comparing
fonts at the same em size does not equalize their visible letter height.

- **Hinting** adjusts outlines to the pixel grid. Hand-drawn bitmap fonts are
  another way to control that grid at their native sizes; they are not the only
  way to produce useful 1-bit text. Non-integer scaling needs fresh evaluation.
- **Coverage and bit depth** are distinct from the panel's available gray levels.
  An antialiased glyph can be thresholded to binary, but the result depends on its
  outline, hinting, and placement. A multibit font does not ensure physical gray.
- **Weight** should preserve strokes without closing counters. Test several
  weights when needed; semibold is a candidate, not a universal optimum.
- **Threshold polarity matters.** Raising a threshold on composited luminance
  thickens dark text and thins light text. Lowering a threshold on a glyph's ink
  coverage is a different operation, performed before foreground/background
  composition. Test both text polarities rather than treating these as equivalent.
- **Spatial dithering** may preserve average tone while introducing texture into
  small strokes. Test deterministic absolute coordinates and fragmented redraws;
  error propagation across independently flushed regions can create seams.
- **Physical quantization** should be assessed against measured panel response
  when gray-level fidelity matters. Equal code steps need not give equal perceived
  steps. Account for refresh history as well as the resulting static bitmap.

For panel formats and refresh transitions, use the separate
[display refresh reference](display-refresh.md). Font experiments must respect
that contract rather than infer interaction behavior from panel bit depth alone.

## Size by viewing geometry

Record active panel dimensions or pixel pitch, viewing distance, actual rendered
x-height, and intended task. Keep ambient glances and close reading distinct.
For a glyph height `h` pixels, pitch `p` mm/pixel, and distance `d` mm:

```text
angular height = 2 * atan((h * p) / (2 * d))
```

At these small angles, `atan(h * p / d)` is a useful approximation. Convert radians
to degrees explicitly. To propose an em size, use the selected face's measured
x-height/em ratio; then verify the actual raster at that size. Hinting and variable
axes, especially optical size, can change the ratio.

Evaluate at the far end of the intended distance range, then check layout capacity
and comfort at the near end. For clocks and symbols, inspect their actual visible
height and recognition task rather than assigning a prose-reading verdict from
x-height alone. A size below a research benchmark may be a deliberate tradeoff;
record the task and reason without calling it unreadable or exempting it from
physical evaluation.

## Compare engines reproducibly

Record font source and checksum, license, axes, character repertoire, sizes,
engine versions, hinting mode, threshold, rounding, and output bit depth with each
result. Keep raw output and representative images beside the measurements.

For a rasterizer-only comparison, feed identical outlines at identical locations
to each rasterizer. Align results on glyph origin and baseline, not just cropped
bitmap boxes. Report coverage error and differences after target quantization;
inspect where the errors occur, especially at joins and counters.

FreeType is a useful comparison implementation, not perceptual ground truth.
Its true mono scan conversion includes dropout behavior that AA-then-threshold
need not reproduce. Matching it measures fidelity, not superiority in reading.

For spacing, compare actual text runs as well as pair adjustments. Use the same
variation location and shaping features. Legacy `kern` coverage alone does not
establish GPOS coverage. Pair-derived kerning is not a substitute for full shaping
when substitutions, marks, or contextual positioning matter. Verify cumulative
advance rounding and the target font format's numeric units.

Useful tool references:

- [FreeType driver properties](https://freetype.org/freetype2/docs/reference/ft2-properties.html)
  for hinting and stem-darkening controls.
- [LVGL font documentation](https://lvgl.io/docs/open/9.4/details/main-modules/font.html)
  and [lv_font_conv](https://github.com/lvgl/lv_font_conv) for font-table semantics,
  bit depth, compression, and conversion options. Check the version actually used.
- [mkttf](https://github.com/Tblue/mkttf) for investigating a BDF-to-TTF conversion;
  verify the resulting native-size raster rather than assuming tracing preserves it.

## Measurements and their limits

| Measure | Useful for | Limit |
| --- | --- | --- |
| Stroke/counter topology | Finding disconnected joins and closed counters | Define connectivity and reference per glyph; a supersampled raster is still a renderer output |
| X-height, cap height, stem runs | Diagnosing inconsistent grid fitting or weight | Overshoot and differing stroke widths can be intentional letterform design |
| Pairwise pixel difference | Finding similar-looking glyph pairs to inspect | Not a measured human confusion rate; sensitive to alignment and weight |
| Perimetric complexity | Investigating shape complexity under a specified model | Within-face renderer ranking is an extrapolation from letter-identification research |
| Spatially filtered image difference | Investigating visible quantization error | Requires a justified viewing and luminance model; does not measure reading success |
| Changed pixels and repeatability | Detecting redraw instability | Cannot establish physical readability |

Use structural defects as explicit review gates. A scalar score must not hide a
severed stroke, and an automatic topology mismatch must be checked against the
actual letterform. Declare model parameters, including blur scale relative to
letter height. Earlier exploratory blur cutoffs are not universal validity bounds.

## Image review before physical evaluation

Use human review to guide development of rendering methods that generalize across
fonts and sizes with minimal intervention. Start with individual glyphs and related
groups: compare stem weight, joins, counters, and proportions within and across
letters, allowing for intentional typeface differences. Check promising changes
across the wider repertoire, nearby sizes, and additional families.

Turn repeatable observed defects into diagnostics and regression cases, retaining
the source settings and images. Assess those checks against human observations;
passing topology alone leaves weight and shape consistency unverified. Prefer
general rendering improvements or reproducible automatic setting selection. Use outline constraints to preserve shared widths and source geometry before
scan conversion; evaluate any remaining intervention separately.

Review labelled generated images with the observer first. Use native-pixel views
for text and nearest-neighbour enlargements for strokes and counters. Compare
normal/inverse text, spacing, and ambiguous characters; record feedback against
exact settings and revise the samples before selecting cases for board testing.
Screen scaling and contrast limit conclusions about physical reading comfort.

## Physical evaluation

Use labelled specimens at native resolution, then test actual UI layouts. Include
ordinary text, digits, punctuation, units, and confusable groups such as
`Il1 O0 5S 8B 69 rn`. Cover the intended repertoire, not just printable ASCII.

Record board, frame identity, font settings, lighting, distance, polarity, refresh
mode/history, and observer responses. Separate transcription or recognition errors,
comfort/preference, and rendering defects. Compare the same task and conditions;
a photograph is useful evidence but changes scale and contrast when viewed later.

Check normal and inverse text, clipping and spacing, full versus partial redraws,
repeated refreshes, and recovery after switching display modes. Host output proves
what was generated; panel observation proves what appeared; reader performance is
needed to substantiate a readability claim. Keep these evidence levels separate.

## Typeface resources

These are research resources, not a product selection list:

- [Atkinson Hyperlegible](https://www.brailleinstitute.org/freefont/) and
  [Luciole](https://www.luciole-vision.com/) for letterform distinction.
- [Literata](https://github.com/googlefonts/literata),
  [Source Sans 3](https://github.com/adobe-fonts/source-sans), and
  [Roboto](https://github.com/googlefonts/roboto) for outline/axis exploration.
- [Pixel Operator](https://notabug.org/HarvettFox96/ttf-pixeloperator),
  [X11 Adobe BDF collection](https://github.com/toitlang/pkg-font-x11-adobe),
  [Ark Pixel](https://github.com/TakWolf/ark-pixel-font), and
  [Fusion Pixel](https://github.com/TakWolf/fusion-pixel-font) for native-grid examples.
- [pixelfonts.org](https://pixelfonts.org/) for inspecting bitmap designs, and
  [ebook-fonts](https://github.com/nicoverbruggen/ebook-fonts) for e-reader metrics
  examples. Verify each actual asset's license and supported sizes before use.

The [archived generator survey](../archive/fonts/font-generator-options-2026-09-04.md)
retains the earlier Plex/Ark measurements and tool comparisons. Treat them as
historical evidence with their original test scope, not results for other faces.
