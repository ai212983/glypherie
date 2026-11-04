<!-- cspell:words YinYangFit TypeFacet Autokern Kernagic HTLetterspacer Letterspacer HTLS BubbleKern ElectricBubble Kosch Cozens Schwartz Kindersley Zapf Karow Hu sidebearings sortsmill hodefoting chemoelectric Tosche huertatipografica charlesmchen aldusleaf RoboFab FontForge GlyphsApp AppKit NumPy TensorFlow WebGPU lib2to3 izip xrange intrudingAdvance findBestDistance minClip dataSync conv2d tfjs Colab rd ri ca bd du ff cc zz os GPL yinyang sidebearing inspectable rythm autofit Minkowski nonseparable nonconstant opentype counterforms rerasterizing Vanilla -->

# Geometric alternatives cited by YinYangFit

Research only, 2026-10-31. **No replacement is ready to recommend for production. TypeFacet Autokern is the best bounded
new reference experiment; Electric Bubble is a more speculative recovery project.** Neither has demonstrated an optical
improvement over Hu on our delivered glyphs. This report examines the geometric families in
[YinYangFit's prior art and linked appendices][yy], rather than treating that article's summaries as implementation
evidence.

## Decision and scope

Ranked by usefulness for this task, rather than by advertised output quality:

1. **TypeFacet:** a real, inspectable pair-dependent profile selector, with no missing learned checkpoint. Its intrusion
   calculation preserves spatial relationships that a shared wall average loses. It remains a manually configured gap
   heuristic, needs legacy-runtime reproduction, and has no established automatic configuration for uploaded fonts.
2. **Electric Bubble:** real browser-oriented interaction code and a recovered primary article, but unfinished fitting,
   fragile selection and numerical questions. Recovering it is substantially less bounded than testing TypeFacet.
3. **BubbleKern generated envelopes:** an executable pair-contact heuristic, but its offset generation depends on Glyphs
   filters and manually chosen settings. Useful as a simple envelope control, with no established advantage over our
   existing geometry and safeguards.

HT Letterspacer and Kernagic are executable individual-glyph spacing methods. They supply no convincing new mechanism
for the unresolved pair-specific problem; replacing one reduced wall statistic with another is not a reason to port
them.

Anchor spacing requires designer-authored metadata absent from arbitrary uploads. BubbleKern can generate offset
envelopes, but its parameters and editor dependency remain obstacles to automatic use. iKern is a service, not a
disclosed reusable engine. Kindersley and Hz are historical context here. The sections below provide the source evidence
behind these judgments.

The task's control remains `hu_fitted_full_density_conserved_touch`. The complete bitmap-cell ablation tightens `os` and
widens `rd`/`ri`/`ca`, without a clear overall preference. CounterSpace has already been reproduced with source and
delivered calibration; `bd`/`du` and `ff`/`cc`/`zz` remain concerns. These are supplied assessment context, not new
results from this audit. The older CounterSpace recommendation in [pair-model research](optical-spacing-pair-models.md)
is not a new experiment. The [YinYangFit audit](yinyangfit-feasibility.md) owns its current zero stub, feature-only JAX
notebook, and historical Torch scorer without recovered fitted state; none was rerun here.

Work stays within the [spacing design](../designs/text-layout/contextual-spacing-and-healing.md) and
[evaluation rules](../evaluation.md). Delivered 1-bit glyphs remain unchanged, contact is allowed, occupied-cell overlap
and same-row facing-wall inversion are forbidden, and fixed-pitch/tabular preservation remains mandatory. No solver,
renderer, dependency installation, comparison page or preview selection changed.

## Evidence boundary and pinned sources

**Observed** below means source inspection, except where execution is explicitly stated. **Inference** identifies a
portability or suitability judgment. **Unresolved** means the audit did not establish the claim. Source availability is
not a successful package run, browser benchmark or optical assessment.

Six default-branch snapshots were cloned into
[`out/diagnostics/contextual-spacing/yinyang-alternatives/`](../../out/diagnostics/contextual-spacing/yinyang-alternatives/).
The [source manifest](../../out/diagnostics/contextual-spacing/yinyang-alternatives/source-manifest.json) records full
revisions, dates, tracked-file counts, page fetch outcomes and hashes. Scope is these snapshots and the primary updates
linked below, not every historical commit or fork.

| Family          | Inspected revision                         | Executable path inspected                                    | License / actual required state                                                                                      |
| --------------- | ------------------------------------------ | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| Kernagic        | `30be68c06a7bf6010d26eefd45ee9504d1239f44` | `ufo-glyph-parser.c`, `gap.c`, `rythm.c`                     | [GPL-3.0-or-later][kern-gap]; geometry, settings, optional rhythm overrides                                          |
| Anchor spacing  | `90b97a9296582211a133970bb577013c9c86ed81` | `tools/spacing_by_anchors.py`                                | [MIT header in the script][anchors]; authored spacing anchors and font database settings                             |
| HT Letterspacer | `b4ad60bd36284f87edf9f2145d38bbf87b2e9909` | `htls/engine.py`, `rules.py`, `config.py` in the main plugin | [GPL-3.0 code; CC-BY-4.0 documentation][ht-readme]; master parameters, reference/rule configuration                  |
| TypeFacet       | `8c6db26d0c599ece16f3704696811275120a4044` | `Autokern.py`, `AutokernSettings.py`, `TFSGlyph.py`          | [Apache-2.0][tf-license]; UFO contours and manually supplied spacing parameters                                      |
| BubbleKern      | `e2d2a3b02e91da0c1e1cb45075ca979b68e5b0a0` | reporter's `BubbleKern.py`, bubble creation helper           | [Apache-2.0][bk-readme]; authored/generated bubble layers and chosen pair list                                       |
| Electric Bubble | `31ce15a56429b67e2c759fcb625e78db3a17e9d3` | `src/App.js`, `autofit.js`, `kernels.js`                     | [Package declares MIT][eb-package]; no standalone license file found; numeric UI defaults, no recovered fitted state |

The first five are geometric rules or designer-driven tools: they do not require model training data or checkpoints to
evaluate their declared methods. Their examples/configurations are not a learned universal spacing model. Electric
Bubble's repository has calculation code and numeric defaults, not a demonstrated trained model. No conventional model
checkpoint path was found in these six tracked-file inventories; this bounded check does not establish that external
state never existed. Licenses above describe inspected upstream declarations, not a completed dependency-license audit.

## TypeFacet Autokern: strongest limited experiment

### Actual algorithm and selection

**Observed:** this is substantially more than its [manual][tf-manual]. At the pinned revision,
[`Autokern.py`][tf-engine] implements the complete route from profiles to selected pair advance:

- `makeProfile` (lines 1472–1559) samples minimum/maximum outline x coordinates by y. Curves are evaluated at a fixed
  segment precision, then placed on the configured vertical sampling grid.
- `makeInflatedProfile` / `inflateSegmentLeft` (1873–1955) offset segments and add endpoint rounding, with radii of half
  the configured minimum/maximum distance. This is the implementation's approximate outline inflation, not a verified
  exact Minkowski sum.
- `findMinProfileAdvance` (1809–1824) takes the maximum same-row difference between facing profiles: first contact of
  those profiles. `isValidProfileIntrusion` (1562–1806) forms pair-dependent row offsets, splits sections around large
  gaps, trims large end gaps, caps protrusion, and bounds intrusion by both a powered intrusion/protrusion balance and
  mean intrusion tolerance. Both full-height and baseline-to-ascender checks participate.
- `findMinProfileAdvance_withIntrusion` (1827–1870) binary-searches an allowed intrusion offset. `processKerningPair`
  (1958–2153) combines that result with the minimum-distance bound, tracking and x-extrema overlap controls, then writes
  `advanceMap`. `process()` calls pair processing and kerning/sidebearing updates and saves the UFO (3185–3254).

This is a genuine selection rule, not a zero penalty or a feature visualization. It is also **not** a learned perceptual
cost or a whole-image interaction model. Profile inflation, pair-dependent sections and nonlinear intrusion tests make
it nonseparable into one precomputed left/right wall average. Interior ink topology with identical exterior profiles is
still largely invisible to it. All of these conclusions follow from the inspected calculation, not advertised quality.

### What actually executed

The [smoke probe](../../out/diagnostics/contextual-spacing/yinyang-alternatives/typefacet-profile-probe.py) ran three
AST-extracted methods after standard-library `lib2to3` syntax translation, using synthetic fully populated profiles. It
did not import the application, construct UFO glyphs, inflate outlines or render text. The
[record](../../out/diagnostics/contextual-spacing/yinyang-alternatives/typefacet-profile-probe.json) retains
interpreter, source hash and inputs. Both profiles have mean `8/3`; rearranging one profile's rows changes contact
advance from 0 to 8 and intrusion-selected advance from 0 to 2. These numbers are synthetic profile units, not glyph
pixels or timings. They establish nonconstant, alignment-sensitive primitive behavior only. They do not establish an
advantage over our existing collision guard or parity with the original Python 2 runtime.

**Initial audit limit:** the original file fails Python 3 parsing at line 81. It uses Python 2 syntax, `xrange`, `izip`,
RoboFab and other legacy support libraries. No full CLI execution was attempted and no dependencies were installed.
Mechanical syntax conversion is insufficient evidence of a faithful port: division/rounding and mixed `None`/numeric
comparisons need explicit treatment. The [upstream TODO][tf-todo] also lists italic/oblique support, components,
argument checks and a sidebearing audit. [`TFSGlyph.getContours`][tf-glyph] reads actual contours without an explicit
component decomposition pass. Arbitrary compiled fonts therefore require proper instance extraction and component
handling; the source does not establish that all uploaded fonts work.

**Subsequent reproduction:** the
[bounded trial](../../out/diagnostics/contextual-spacing/typefacet-experiment/verified/findings.md) now runs the
original Python 2 application and bundled dependencies through actual UFO output, including source and delivered-cell
analyses for frozen Literata. The reference gate passes with explicit export-rounding records, but the author-example
settings remain uncalibrated and produce mixed pair changes. Coordinate scaling affects some rounded source decisions,
and a component-only glyph receives no selection. No reading preview or browser port follows from this result.

The [reference-family calibration](../../out/diagnostics/contextual-spacing/typefacet-calibration/fit-03/findings.md)
then fits the manual's four parameter roles without reported-pair tuning. Its single global vector remains ambiguous:
near-equal reference fits produce different lowercase placements, and the selected vector expands overall density. This
bounds the attempted automatic calibration; it does not disprove manual or category-based use of the original tool.

### Inputs, calibration and browser suitability

The [manual][tf-manual] requires font-specific adjustment of minimum distance, normal/maximum distance, intrusion
tolerance, extrema overlap and precision. It suggests reference pairs and repeated inspection; there is no supplied
automatic per-font fitting procedure. UFO is the input/output format. Sidebearings can be preserved with the documented
option, but that does not by itself implement our bitmap/fixed-pitch/tabular policy. No trained state is missing because
the method is rule-based, not because a universal calibration has been established.

**Inference:** arrays, outline offsets, row reductions and a bounded search can be implemented in Rust/WASM inside the
existing worker; neither FFT nor WebGPU is intrinsic to this method. The Python/RoboFab application is not a browser
library. A bitmap adapter could analyze the union of actual occupied pixel-cell rectangles, preserving their coordinates
and leaving displayed ink unchanged. Upstream instead analyzes source outlines. This is a project adaptation requiring
reference parity and a calibration comparison, not a supported upstream bitmap input mode.

The intrusion power is `1.15`, compared against a linear protrusion total, and there are font-unit rounding and fixed
curve-sampling choices. Consequently a naive change from font units to 16 px coordinates need not preserve the decision.
Use one declared coordinate scale; do not transfer source-calibrated numeric parameters directly to unrelated bitmap
units. Performance, search assumptions after section splitting, parameter stability and usefulness at integer pixel
placements remain unmeasured. Calling the routine executable does not resolve those issues.

## Electric Bubble: recovered code, unfinished model

The originally cited Aldusleaf URL returned HTTP 404. The [author's current homepage][eb-author] links a live
[ElectricBubble article][eb-article] and its [source repository][eb-tree]. The author marks it superseded by YinYangFit.
The article proposes filtered glyph fields, a differentiable approximate Euclidean distance transform, and attention
weights from equidistance, opposing gradients, mean gradient angle and vertical position. Interaction divided by total
attention is the proposed pair quantity. Its status section explicitly describes fitting degeneracy: parameter fits can
flatten the distance response instead of recovering useful distances. These are the author's hypotheses and reported
limitations, not perceptual facts established here.

**Observed code:** [`App.js`][eb-app] creates ink/whitespace saliency by `conv2d`, raises combined saliency to a power,
convolves with an inverse-power kernel, applies inverse powers/clipping, and calculates gradients.
[`autofit.js`][eb-fit] builds equidistance and gradient-angle factors, then actually evaluates `sum(attention *
(leftBubble + rightBubble)) / sum(attention)`. It iterates integer overlap toward `desiredInteraction` and returns a
distance. Thus public pair scoring/selection source exists; claiming only a vanished article would be incorrect. The
browser code does not implement every optional component in the article: `yFactors` is parsed but not applied, and
[`kernels.js`][eb-kernel] uses an isotropic distance kernel.

However, this is a prototype, not a completed reusable package:

- The selector has an 80-attempt limit and a threshold-following update, not exhaustive feasible-distance minimization.
  Its loop repeats the first bubble's width check; it can exit without a convergence or feasibility result. It has no
  occupied-cell or same-row wall-inversion guard. A zero attention sum has no explicit division guard.
- `App.js` renders uploaded outlines through old `opentype.js`/Canvas, at a default 72 px, initially preparing only
  Latin lowercase glyphs. That is not our Rust-rendered 16 px binary input. Its default filters are 20/60 pixels wide,
  with powers up to 22. `Number.MIN_VALUE` as a tensor floor also needs checking against backend numeric precision;
  these are portability/numerical concerns from source inspection, not observed runtime failures.
- The repository provides manual parameter defaults, but no observed optimizer, training dataset, exported fitted state
  or held-out evaluation. The linked [Colab][eb-colab] exposed a sign-in shell to the research fetch, not notebook
  cells; its actual objective, state and availability remain unresolved. No private access was attempted.

**Inference:** image-tensor input could accept delivered masks, but choosing size-dependent filters and calibrating on
source images versus binary masks is unresolved. A browser-shaped implementation is useful evidence of intended
portability, not evidence of a working current deployment. The declared dependency is TensorFlow.js `^0.15.3`
([manifest][eb-package]); source uses direct convolutions, powers, gradients and reductions, not an explicit FFT route.
A current JS/WebGPU version or a Rust/WASM implementation would need numerical and reference checks. Neither WebGPU nor
FFT is automatically required; neither has been benchmarked here. Per-font fitting is an unsolved part of the proposal,
so this is not an easier finished substitute for YinYangFit. The entire app was not built or executed.

## Individual spacing and authored-envelope tools

### Kernagic

**Observed:** [`gen_debug` in `ufo-glyph-parser.c`][kern-parser] computes an x-height-band ink projection and chooses
rhythm positions from cumulative ink in the outer portions of the glyph width. [`gap.c`][kern-gap] uses first/last
rhythm points, desired gap, snap period, tracking and larger-glyph scaling to assign each glyph's left/right bearings.
Manual rhythm overrides are supported. [`rythm.c`][kern-rhythm] provides another individual-glyph rhythm calculation.
These are real implementations; the [README][kern-readme] describes the tool as semi-automatic and anticipates manual
fine-tuning. It reads/writes UFO; its C application depends on Cairo/GTK.

**Inference:** the projection/spacing arithmetic could be ported to WASM and fed bitmap data, with font-unit/size
conversion and native UI removed. No weights, FFT or optimizer are required. But it chooses independent bearings, not a
pair interaction score. Moving from Hu to this rule does not restore pair-specific spatial information. Its snapping
also needs deliberate compatibility with fixed/tabular widths. No native or browser execution was performed.

### HT Letterspacer, including the current update

The live [homepage][ht-site] and [upstream README][ht-readme] now describe a Glyphs 3 plugin; the inspected 2026 source
is newer than the old link in YinYangFit. [`htls/engine.py`][ht-engine] scans outline margins, selects a reference
height range, handles italic slant, caps depth, closes open counterforms with a 45-degree envelope and integrates a
polygon area. `calculateSBValue` subtracts measured area from a configured area target and divides by reference height;
`setSpace` computes independent left/right bearings. The current source includes explicit tabular-width handling and
rules for reference glyphs, sides and parameter overrides. It is more elaborate than simply measuring an unmodified
baseline-to-x-height gap, but it still has no pair-dependent scoring/selection path.

**Inference:** its geometry could be re-expressed on cell boundaries in Rust/WASM without ML, FFT or WebGPU. GlyphsApp,
Objective-C/Foundation intersections and editor callbacks are not portable as-is. Area, depth, overshoot, reference
rules and sampling remain configurable per font/master. Applying the defaults to every upload does not establish optical
calibration. Its reduced side areas are another separable spacing heuristic; not a new answer to Hu's missing pair
interaction. No plugin run or delivered-bitmap evaluation was performed.

### Anchor spacing and BubbleKern

[`spacing_by_anchors.py`][anchors] is a real FontForge tool, not just a description of stem spacing. It sets bearings
from authored anchor extrema, groups glyphs by anchor signatures, and `calculate_kerning` selects the largest compatible
anchor offset at matching heights (with named special-case support). It can emit feature/Graphite kerning. This can
produce pair-specific output, but the spatial judgment comes from manually placed anchors and configuration, not an
automatic inference from occupied ink. FontForge font objects and helper modules are required upstream. The arithmetic
is portable; missing anchors in arbitrary uploads are the substantive blocker.

Likewise, [`BubbleKern.py`][bk-engine] collects authored `bubble` layers, including component transforms, samples their
left/right boundaries every 10 font units, and selects first contact by the minimum summed facing bubble sidebearings.
It writes kerning for a designer-selected pair list, with magnitude thresholds and a width-based fallback. The
[README][bk-readme] explicitly places bubble shape and pair choice under designer control.
[`MakeBubbleLayers.py`][bk-helper] can also generate initial envelopes: copy outline paths, apply user-selected
horizontal and vertical offsets, remove counter contours/overlaps, optionally nudge or trim to existing sidebearings,
and round corners. It delegates offsetting/rounding to Glyphs filters rather than supplying their geometry
implementation. Thus generated bubbles are a real alternative contact heuristic, not an unavailable feature. Source
format is Glyphs layers/masters and the implementation uses GlyphsApp/AppKit/Vanilla.

**Inference for both:** after metadata preparation, contact evaluation uses array/anchor arithmetic; no timing was
measured. Neither requires FFT or learned weights. Anchor spacing cannot infer the missing anchors from an unchanged
bitmap. BubbleKern's supplied offset construction could be adapted to bitmap envelopes, but choosing offsets and
sidebearing adherence automatically for every upload has not been validated. This is another configurable
clearance/envelope heuristic, not demonstrated perceptual improvement over Hu. Their envelope contact also cannot
replace our independent occupied-cell and wall-order checks. No editor execution was performed.

## iKern and historical context

The current [iKern service][ik-service] accepts outlines, preferably UFO and also other font formats, and returns
metrics through an individual customer workflow. Its [method description][ik-method] discusses a proximity model, an air
model, classification and parameters, but explicitly withholds the equations. No downloadable implementation, model
state or browser embedding license was identified on these primary pages. Pair-specific behavior is described by the
author; the actual calculation is not inspectable. Commercially generated tables for selected fonts would not supply an
engine for arbitrary browser-local uploads. No service submission, timing validation or reverse engineering was
attempted.

For **Hz**, the [cited patent, EP0466953B1][hz], describes paragraph justification with stored normal/narrower/wider
pair-distance tables and character-width variants. It does not supply an automatic optical scorer that derives those
tables for an arbitrary uploaded font. Shape-changing variants also depart from our unchanged-glyph constraint. A table
consumer can be implemented, but the missing pair-distance generator is exactly this task's problem.

For **Kindersley**, YinYangFit describes a historical area/moment wedge method. This audit recovered no primary
executable implementation, reusable parameter set or delivered-bitmap validation for it. That is an availability limit,
not evidence for repeating the article's negative optical judgment as established fact. No verified reusable algorithm
or license is recommended from the name alone. Both families stay historical context, outside the shortlist.

## Browser execution and arbitrary uploads

The current [worker](../../apps/web/src/app/renderer/font-worker.ts) owns Rust/WASM font parsing and rendering; the
[web contract](../../apps/web/CONTRACT.md) keeps uploads local. None of the audited packages directly supplies an
integration with that worker and the exact delivered binary surface. The following are design implications, not
implemented behavior or measured budgets:

- **Analyze actual delivered cells.** Preserve original origins, baseline, bearings, axes and integer cell extents.
  Upsampling those cells for analysis may preserve shape; rerasterizing outlines through Canvas or an unrelated font
  engine does not establish equality. Analysis filters must not modify the displayed glyphs.
- **Calibrate in a declared domain.** Source-design spacings can supply font-wide style references. Source outlines,
  high-resolution gray images and 16 px delivered bitmaps are distinct geometry domains. Compare source-calibrated and
  delivered-calibrated parameters separately; never call transferred parameters calibrated merely because the code is
  shared. None of these families supplies a verified automatic per-upload solution to this problem.
- **Retain independent feasibility.** Upstream profile/bubble contact is not our pixel occupancy test. Enumerate only
  placements satisfying occupied-cell non-overlap and same-row facing-wall order, permitting exact contact. Retain
  fixed-pitch, tabular, empty-glyph and other existing eligibility behavior. Record when a preferred target is
  infeasible.
- **Cache by actual inputs.** Precompute profiles/fields per font content, instance axes, renderer configuration, size,
  delivered bitmap identity, model and calibration. Cache pair results lazily for encountered pairs. An all-pairs table
  grows quadratically; shipped static tables cover only known inputs, not arbitrary uploads or axis instances. Reusable
  algorithm code and local per-upload calculation are still needed even if the eventual layout lookup is a table.
- **Measure before porting broadly.** TypeFacet/HT/Kernagic use profiles and reductions; Electric Bubble adds padded
  fields, convolutions and powers. A worker moves work off the UI thread but does not bound latency or peak memory.
  Measure cold preparation, per-font calibration, distinct-glyph/pair growth, cancellation and cache memory. No timing,
  memory, WASM throughput or WebGPU compatibility result was obtained here.

## Smallest falsifiable next experiment

**Proposal only: TypeFacet primitive/reference fidelity, then one frozen capture.** Do not build a plugin integration,
automatic font fitter or new preview page first.

1. Reproduce the pinned TypeFacet path on one declared outline fixture, including inflation, intrusion, final advance
   and actual UFO output. The synthetic extraction above is not this gate. Use an isolated compatible runtime in a
   separately scoped experiment; retain dependencies, parameters, emitted results and failures. Check zero-distance
   contact, disjoint height ranges, components and unit/rounding behavior. Reject silent partial execution or fixes
   represented as unchanged upstream behavior.
2. Freeze Literata `wght=400`, 16 px, `opsz=16`, delivered bitmaps and metric origins. Compare source-outline analysis
   and a disclosed exact cell-geometry adapter in the same declared physical/font-unit coordinates. Keep all glyph ink
   identical. Include an aligned/rearranged synthetic control to establish interaction **beyond** existing feasibility
   clamps, rather than interpreting contact differences alone as a perceptual gain.
3. Declare one font-wide configuration from a source-backed reference set before inspecting problem pairs. Hold out
   `rd`, `ri`, `ca`, `os`, `bd`, `du`, `ff`, `cc`, `zz`. TypeFacet supplies manual controls, so automatic parameter
   fitting would be an additional project hypothesis requiring a separate specification; do not hide it inside an
   adapter. Retain all calibration references and residuals, then score/select feasible integer positions with the
   unchanged safeguards. Report source-relative width drift, clamp activity, parameter/scale sensitivity, ties and
   failures.
4. Stop if the result reduces to existing collision bounds, needs per-pair tuning, is unstable under coordinate/sample
   changes, or cannot produce meaningful held-out choices. Only after those gates should the existing comparison flow be
   used for native-size reading assessment against B. Mechanical success leaves optical status **pending assessment**.
   Broader fonts/sizes and upload/runtime measurements are required before any production recommendation.

This can falsify TypeFacet's usefulness without completing YinYangFit. It cannot establish a universal perceptual
spacing model. If it fails, this bounded family search offers no ready new recommendation; recovering Electric Bubble
would require an explicit decision to take on another unfinished model.

[yy]: https://skosch.github.io/YinYangFit/#prior-art
[kern-readme]: https://github.com/hodefoting/kernagic/blob/30be68c06a7bf6010d26eefd45ee9504d1239f44/README.md
[kern-parser]: https://github.com/hodefoting/kernagic/blob/30be68c06a7bf6010d26eefd45ee9504d1239f44/ufo-glyph-parser.c#L427-L496
[kern-gap]: https://github.com/hodefoting/kernagic/blob/30be68c06a7bf6010d26eefd45ee9504d1239f44/gap.c
[kern-rhythm]: https://github.com/hodefoting/kernagic/blob/30be68c06a7bf6010d26eefd45ee9504d1239f44/rythm.c
[anchors]: https://github.com/chemoelectric/sortsmill/blob/90b97a9296582211a133970bb577013c9c86ed81/tools/spacing_by_anchors.py
[ht-site]: https://letterspacer.htfonts.com/
[ht-readme]: https://github.com/huertatipografica/HTLetterspacer/blob/b4ad60bd36284f87edf9f2145d38bbf87b2e9909/README.md
[ht-engine]: https://github.com/huertatipografica/HTLetterspacer/blob/b4ad60bd36284f87edf9f2145d38bbf87b2e9909/HTLetterspacer.glyphsPlugin/Contents/Resources/htls/engine.py
[tf-license]: https://github.com/charlesmchen/typefacet/blob/8c6db26d0c599ece16f3704696811275120a4044/License.txt
[tf-manual]: https://charlesmchen.github.io/typefacet/topics/autokern/typefacet-autokern-manual.html
[tf-engine]: https://github.com/charlesmchen/typefacet/blob/8c6db26d0c599ece16f3704696811275120a4044/python/src-main/autokern/Autokern.py
[tf-todo]: https://github.com/charlesmchen/typefacet/blob/8c6db26d0c599ece16f3704696811275120a4044/python/src-main/autokern/TODO.md
[tf-glyph]: https://github.com/charlesmchen/typefacet/blob/8c6db26d0c599ece16f3704696811275120a4044/python/src-main/tfs/common/TFSGlyph.py#L82-L130
[bk-readme]: https://github.com/Tosche/BubbleKern/blob/e2d2a3b02e91da0c1e1cb45075ca979b68e5b0a0/README.md
[bk-engine]: https://github.com/Tosche/BubbleKern/blob/e2d2a3b02e91da0c1e1cb45075ca979b68e5b0a0/ShowKernBubbles.glyphsReporter/Contents/Resources/BubbleKern.py#L664-L760
[eb-author]: https://aldusleaf.org/
[eb-article]: https://skosch.github.io/electricbubble/
[eb-tree]: https://github.com/skosch/electricbubble/tree/31ce15a56429b67e2c759fcb625e78db3a17e9d3
[eb-package]: https://github.com/skosch/electricbubble/blob/31ce15a56429b67e2c759fcb625e78db3a17e9d3/package.json
[eb-app]: https://github.com/skosch/electricbubble/blob/31ce15a56429b67e2c759fcb625e78db3a17e9d3/src/App.js
[eb-fit]: https://github.com/skosch/electricbubble/blob/31ce15a56429b67e2c759fcb625e78db3a17e9d3/src/autofit.js
[eb-kernel]: https://github.com/skosch/electricbubble/blob/31ce15a56429b67e2c759fcb625e78db3a17e9d3/src/kernels.js
[eb-colab]: https://colab.research.google.com/drive/1sp21g2-z_u2ypgHabL23APKnAERJQPi7
[ik-service]: https://www.ikern.space/the-service/details
[ik-method]: https://www.ikern.space/letter-fitting-ikern/ikern
[hz]: https://patents.google.com/patent/EP0466953B1/en

[bk-helper]: https://github.com/Tosche/BubbleKern/blob/e2d2a3b02e91da0c1e1cb45075ca979b68e5b0a0/ShowKernBubbles.glyphsReporter/Contents/Resources/MakeBubbleLayers.py#L242-L334
