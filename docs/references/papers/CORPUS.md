# Research corpus

Research sources relevant to the project, grouped by topic. Local papers are listed in the
[collection index](README.md); follow its [paper rules](README.md#paper-rules) when a required paper is missing.

## Outline geometry and font models

- [Shamir & Rappoport (1996), Extraction of Typographic Elements from Outline Representations of Fonts](https://cris.huji.ac.il/en/publications/extraction-of-typographic-elements-from-outline-representations-o/)
  ([full text](https://pages.cs.huji.ac.il/sites/www-arir/storage/extraction-typographic-elements.pdf)) — stems, serifs,
  bows, arcs, and curved strokes. Sections 3–4 require prepared curve points and tolerance-aware classification; serif
  detection uses finite automata. Full text reviewed.
- [Shamir & Rappoport (1997), Quality Enhancements of Digital Outline Fonts](https://doi.org/10.1016/S0097-8493(97)00049-6)
  ([abstract](https://pages.cs.huji.ac.il/sites/www-arir/storage/quality-abs.html)) — contour orientation and
  interpenetration correction. The complete algorithm remains unverified; modern Boolean normalization is an
  implementation choice.
- [Shamir & Rappoport (1997), LiveType: A Parametric Font Model Based on Features and Constraints](https://history.siggraph.org/wp-content/uploads/2022/11/SIGGRAPH-1997-Visual-Proceedings.pdf)
  — Visual Proceedings, p. 160: acyclic constraint graphs without a detailed shared-corner algorithm. Distinct from
  TR-97-11.
- [Shamir & Rappoport (1998), Feature-based Design of Fonts Using Constraints](https://www.researchgate.net/publication/2506331_Feature-based_design_of_fonts_using_constraints)
  — §4.2 separates X/Y dependency graphs and refers to TR-97-11. It does not establish the 2003 autohinter's overlap
  policy.
- [Berio et al. (2022), StrokeStyles](https://doc.gold.ac.uk/autograff/post/papers/strokestyles_2022/)
  ([code](https://github.com/autograff-devel/strokestyles)) — stroke/junction extraction using geometry and medial axes,
  without templates or training examples. Demonstrated for stylization; grid fitting needs separate validation.

## Hinting and grid fitting

- [Hersch (1993), Font Rasterization: The State of the Art](1993-hersch/) — survey of scan conversion and grid fitting.
  Sections 5–6, pp. 90–99, cover shared widths, symmetry, and diagonals; Figure 25 fits parallel borders to integer
  horizontal separation.
- [Hobby (1993), Generating Automatically Tuned Bitmaps from Outlines](1993-hobby/) — stored report version; automatic
  bitmap generation using distortion, stroke/white-space features, approximate symmetry, diagonal integer offset vectors
  and font-wide consistency (§§2–4), including curved outlines (§6). The diagonal argument assumes center-fill scan
  conversion, so adaptation to coverage threshold conversion needs separate validation.
- [Herz & Hersch (1994), Towards a Universal Auto-Hinting System for Typographic Shapes](https://lspwww.epfl.ch/publications/typography/tuahsts.pdf)
  — black/white stem detection, shared metrics, and ordered displacement; curved stems and terminals remain future work.
- [Hersch & Bétrisey (1991), Model-based Matching and Hinting of Fonts](https://lspwww.epfl.ch/publications/typography/mbmahof.pdf)
  — transfers hints through structural letter models; requires model descriptions and shape variants.
- [Zongker, Wade & Salesin, Example-Based Hinting of TrueType Fonts](https://grail.cs.washington.edu/wp-content/uploads/2015/08/Zongker2000.pdf)
  — transfers model-font hints between matched glyphs using shared control values, with human refinement.
- [Shamir (2003), Constraint-Based Approach for Automatic Hinting of Digital Typefaces](2003-shamir/)
  ([publisher](https://doi.org/10.1145/636886.636887), [reader](https://dl.acm.org/doi/epdf/10.1145/636886.636887)) —
  feature extraction, shared measurements, conflict removal, and ordered hint generation (§§3.3–3.6). Complex features
  need predefined/declarative constraints (§3.5); expert manual hinting remains better in some cases.
- [Turner & Lemberg (2003), Real-Time Grid Fitting of Typographic Outlines](2003-turner-lemberg/) — segments, stem
  pairing, serif relationships, alignment zones, and ordered fitting. Some placement details are left to FreeType code;
  its descendant [ttfautohint](https://freetype.org/ttfautohint/doc/ttfautohint.html) gives diagonals no special
  handling.
- [Stamm, Hitchcock & Duggan, Iteratively solving constraints in a font-hinting language](https://patents.google.com/patent/US7187382B2)
  — repeated native hint operations with movement tolerance and an iteration cap. Termination does not establish
  accuracy.
- [Microsoft VTT: SERIF](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/doc/VTT%20Language%20Reference/vttlang.html#L827-L876)
  and
  [compiler](https://github.com/microsoft/VisualTrueType/blob/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/src/TTGenerator.cpp#L1600-L1810)
  — stem/baseline prerequisites and vertical/diagonal half-serif recipes. Useful for Shamir's declarative route;
  historical VTT equivalence remains unverified.
- [Microsoft: fixing rasterization issues](https://learn.microsoft.com/en-us/typography/truetype/fixing-rasterization-issues)
  and [diagonal hinting](https://learn.microsoft.com/en-us/typography/truetype/italic-hinting-examples) — linked
  distances, interpolation, rounding conflicts, and parent anchoring before diagonal control.
- [FreeType driver properties](https://freetype.org/freetype2/docs/reference/ft2-properties.html) — hinting and
  stem-darkening controls.

## Rasterization and filtering

- [FreeType: text rendering](https://freetype.org/freetype2/docs/hinting/text-rendering-general.html) — explains how
  hinting, coverage, blending, and weight interact.
- [Kajiya & Ullner, Filtering High Quality Text for Display on Raster Scan Devices](https://www.cs.jhu.edu/~misha/ReadingSeminar/Papers/Kajiya81.pdf)
  — filtering for grayscale CRT text; relevant to offset averaging, with different display assumptions from bilevel
  panels.
- [Anderson, Shamir & Fried (2022), Neural Font Rendering](https://arxiv.org/abs/2211.14802) — learns size-dependent
  glyph images from raster examples. Target-image memorization and remaining curved-glyph artifacts limit transfer to
  arbitrary source outlines.

## Quantization

- [Gallager (2006), Quantization](2006-gallager-quantization/) — §3.2.1, p. 65, derives nearest-point selection for
  minimum squared error with fixed levels. This supports coverage quantization; panel tone mapping requires separate
  evidence.

## Reading and letter recognition

- [Legge & Bigelow (2011), Does print size matter for reading?](https://pmc.ncbi.nlm.nih.gov/articles/PMC3428264/) —
  relates reading speed to angular x-height. The approximate fluent range of 0.2–2 degrees concerns primarily normally
  sighted readers; it is not a universal cutoff for symbols, glanceable displays, or low vision.
- [Pelli et al. (2006), Feature detection and letter identification](https://denispelli.com/pubs/pelli2006letters.pdf) —
  relates identification in visual noise to perimetric complexity, without establishing a general UI readability score.
- [Developing a Typeface for Low Resolution E-Ink Displays](https://www.researchgate.net/publication/324671274_Developing_a_Typeface_for_Low_Resolution_E-Ink_Displays)
  — inspect device, fonts, tasks, and reader population before transferring its results to another panel.

## Image complexity and perceptual comparison

- [Watson (2012), Perimetric complexity of binary digital images](https://www.mathematica-journal.com/2012/02/17/perimetric-complexity-of-binary-digital-images/)
  — covers pixel-grid perimeter measurement and blur-aware complexity; exposed-edge counts are a different model.
- [Zhang & Wandell, S-CIELAB implementation](https://github.com/wandell/SCIELAB-1996) and
  [Zhang et al. (1997), spatial color fidelity](https://web.stanford.edu/~jefarrel/Publications/1990s/1997_Zhang_Silverstein_Farrell_Wandell.pdf)
  — spatial filtering for image comparison. Grayscale adaptations need explicit luminance, viewing geometry, and
  filters.

## Reflective display optics

<!-- cspell:words BRDF Kelley Germer Darling Ferwerda Herle Hertel Penczek -->

- [Kelley, Jones & Germer (1998), Display reflectance model based on the BRDF](1998-kelley/) — diffuse, specular and
  haze decomposition; §§2–3 and Eqs. (1)–(12) checked against the original.
- [Darling & Ferwerda (2012), Seeing Virtual Objects](2012-darling-ferwerda/) — reflective surface rendering on emissive
  monitors; spectral rendering, calibration and reproduction limits.
- [Herle et al. (2024), Emulating paper](2024-herle/) — technology survey; §§2, 4–5 inform the scope, not target-panel
  calibration or universal readability thresholds.
- [Hertel & Penczek (2020), Evaluating Display Reflections in Reflective Displays and Beyond](https://sid.onlinelibrary.wiley.com/doi/10.1002/msid.1099)
  — full publisher text inspected; source superposition and geometry-dependent reflective-display response. Original PDF
  retrieval returned HTTP 403. Access boundaries and the complete literature list are recorded in the
  [reflective display model](../../reflective-display-model.md#literature-and-technical-sources).

## Font formats and conversion

- [LVGL fonts](https://lvgl.io/docs/open/9.4/details/main-modules/font.html) and
  [lv_font_conv](https://github.com/lvgl/lv_font_conv) — font tables, bit depth, compression, and conversion; match the
  version in use.
- [mkttf](https://github.com/Tblue/mkttf) — BDF-to-TTF conversion; verify native-size raster preservation.

## Typeface resources

- [Atkinson Hyperlegible](https://www.brailleinstitute.org/freefont/) and [Luciole](https://www.luciole-vision.com/) —
  letterform distinction.
- [Literata](https://github.com/googlefonts/literata), [Source Sans 3](https://github.com/adobe-fonts/source-sans), and
  [Roboto](https://github.com/googlefonts/roboto) — outlines and variable axes.
- [Pixel Operator](https://notabug.org/HarvettFox96/ttf-pixeloperator),
  [X11 Adobe BDF](https://github.com/toitlang/pkg-font-x11-adobe),
  [Ark Pixel](https://github.com/TakWolf/ark-pixel-font), and
  [Fusion Pixel](https://github.com/TakWolf/fusion-pixel-font) — native-grid examples.
- [pixelfonts.org](https://pixelfonts.org/) and [ebook-fonts](https://github.com/nicoverbruggen/ebook-fonts) — bitmap
  designs and e-reader metrics. Verify each asset's license and supported sizes before use.

## Research collections

- [EPFL/LSP typography publications](https://lspwww.epfl.ch/publications/typography/lptgf.html) — grayscale and bilevel
  research. Physical gray-level benefits do not establish benefits from binary spatial dithering.
