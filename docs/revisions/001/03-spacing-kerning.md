# Monochrome geometry and spacing

<!-- cspell:words HarfBuzz GSUB GPOS ttfautohint unhinted Skia PathOps autofit afloader rekerning SCANCTRL SCANTYPE fpgm maxp VARC thresholded unrepresentable quantizer CGAL Adafruit pdfontconv Tophat rint -->

Combine native and automatic Mono fitting on independent axes, preserve source shape and weight relationships, and
assess continuity and reading rhythm under bitmap placement. Fitting, scan conversion and layout remain separate:
changing a scanner preserves fitted geometry and metrics; changing fitting can legitimately change both.

The [revision index](README.md) owns renderer identities and iteration status; the
[generator API](../../../crates/generator/API.md) owns runtime contracts; [Hobby fitting](../../hobby-fitting.md) owns
geometric models and adoption mechanics. Findings retain their stated font, size, axes and review scope. Classification
follows the [evaluation rules](../../evaluation.md): mechanical parity does not extend an optical approval beyond its
reviewed scope.

<a id="topics"></a>

## Fitting and source geometry

### Selective native hints and automatic fitting

The working Mono preview uses automatic fitting with an optional **Use font hints** preference. Native instructions own
axes they constrain or measure; automatic fitting supplies independent remaining axes. Disabling hints selects upstream
automatic Mono on both axes. Historical controls, settings and compatibility mappings belong to the
[generator API](../../../crates/generator/API.md#working-candidate-fitting).

[Turner and Lemberg](../../references/papers/2003-turner-lemberg/paper.md) ground independent X/Y analysis.
[TrueType projection, freedom and interpolation](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions)
ground ownership: measurements reserve axes, unchanged coordinates may still be constrained, UTP can clear touched
flags, and IUP without touched points contributes no ownership. PostScript stems/alignment zones provide analogous
source evidence.

**Project adaptation:** combine corresponding native/automatic coordinates only on demonstrably independent axes.
Native-controlled coordinates remain exact; horizontal metrics follow the X owner. Failed execution, explicit native
hint disabling, point-defined vector dependencies, constrained composites, implicit unreserved-axis movement,
transformed PostScript outlines or incompatible commands retain the complete native fit. This is axis fallback, not
per-point completion. Wholly automatic glyphs retain eligible source-relative correction; executed scan state remains
authoritative.

**Confirmed geometric correction; scoped browser assessment:** Roboto 400/16, `wdth=100`, has nearly equal source `i t
f` stems but native Y-only instructions leave unequal X widths. Automatic X restores equal bodies with native dot/hook
heights; inspection at 12/20 px supports local continuity and balance. Broader weight, counter and spacing assessment
remains pending. Both-axis native ownership intentionally retains native output despite possible imbalance.

### Mono fitting and engine selection

Upstream controls use registry Skrifa `Target::Mono`: font hints first selects `Engine::AutoFallback`, while Automatic
Mono forces `Engine::Auto(None)`. Both consume runtime font bytes without family, glyph, size or axis exceptions. The
[engine interface](https://docs.rs/skrifa/0.48.0/skrifa/outline/enum.Engine.html) and
[FreeType load targets](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_load_target_xxx)
distinguish engine selection from scanning. Instructions alone do not establish suitability for binary output.

These controls retain the selected upstream outline exactly and can feed independent scanners. Gray retains upstream
Normal automatic fitting. The former `vertical_only`/`vertical-01` composition of source X and Smooth Light Y is retired
and rejected, not an alias for the current policy. Its findings are retained under earlier controls below.

### Scan-control-only program fallback

**Confirmed selection defect, corrected:** Literata 400/16, `opsz=12`, has equal 93-unit `i`/`j` stems. A seven-byte
scan-only `prep`, no `fpgm` and no glyph programs caused upstream selection to retain interpreter outlines, delivering
two versus one columns. Automatic Mono fits both bodies to two columns.

[prep](https://learn.microsoft.com/en-us/typography/opentype/spec/prep) cannot move glyph outline points;
[SCANCTRL/SCANTYPE](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scan-conversion-control)
govern scanning. The font-wide structural adaptation selects automatic fitting only when simple/composite glyph streams
and `fpgm` are absent and `prep` is absent or scan-only. Other fonts retain upstream selection, including CFF/CFF2/VARC
and explicit engine requests. Font bytes are unchanged. Broader stem-weight assessment remains pending.

### Source-defined x-height alignment

Explicit Mono pipelines recover missed source top-zone associations before optional stroke fitting. Literata's light
sloped serifs can miss the automatic hinter's horizontal-direction test.
[FreeType blue zones](https://freetype.org/autohinting/blues.html) supply references and association ranges;
[Hobby §3.3](../../references/papers/1993-hobby/paper.md#33-fitting-verticals-and-horizontals-to-the-pixel-grid) grounds
interpolation between retained references.

The adaptation captures FreeType's fixed Latin donors independently of requested text. Variation-aware source x-height
seeds association; agreeing grid-aligned donor tops supply fitted height. A straight source top must span at least one
pixel inside the association band, with at least half a pixel of excess. Monotone contraction retains lower geometry,
baseline-crossing curve hulls and X. Overlapping contour bounds, conflicting donors or missing references abstain. The
one-pixel eligibility rule conservatively adapts upstream edge eligibility.

Detached marks follow through source white-distance constraints, adapting
[TrueType relative movement](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#move-direct-relative-point)
and [Shamir §3.2](../../references/papers/2003-shamir/paper.md#32-constraints-and-point-relations). One isolated mark
and one baseline-reaching body must share source/fitted/corrected horizontal projection; the mark's lower source/fitted
extrema must be on-curve. Translate the whole mark by the rounded original gap. Ambiguous owners, multiple marks,
collapsed/colliding gaps or preceding gaps outside the half-pixel rounding allowance retain the whole preceding glyph.

**Confirmed correction; broader optical assessment pending:** Literata 16 px, `wght=252.22`, `opsz=16`, aligns `i`/`j`
bodies with `n`. Body-only correction enlarged the dot gap from two rows to three; relative positioning restores two
blank rows from the 1.92 px source gap while retaining dot shape. Native-owned axes, Gray, historical controls and
spacing remain outside this correction.

### Source-relative straight-stroke correction

[Hobby's coupled-width model](../../hobby-fitting.md#valid-straight-medial-intervals) relates valid straight source
medial-axis portions. Third-boundary contacts end a portion rather than vetoing the pair or being ignored. Source
normals/radii define relative width error; sample pairs carry their equation (17) arc-length product. An upstream
rectilinear stem anchors the change, with its shared attachment fixed. Curves, multiple contours, ownership conflicts
and uncertain/invalid solves abstain. The explicit `source_relative` policy remains a control; selective fitting retains
this correction on wholly automatic glyphs.

**Confirmed scoped weight correction:** Roboto Flex Regular 16 px at default axes loses the heavy upper-left `1` head.
Its normal-width proxy falls from about 1.395 to 1.016 px against a fixed 1 px stem; attachment and advances stay fixed.
Shape terms allow local taper/direction changes, not exact border-direction preservation. Browser inspection at 12/16/20
px supports the local result. Additional `7` leg/end changes retain inspected continuity but broader shape/weight
assessment remains pending. Some apostrophe and 20–23 px `1` geometry changes leave ink unchanged; Source Sans 3
ExtraLight `L` at 20 px gains only an empty frame row. Neither is a visible improvement claim.

### Coupled whole-outline widths

The [coupled model](../../hobby-fitting.md#coupled-whole-outline-widths) shares straight/curve controls in a
source-relative X solve. Upright X anchors and upstream Y stay fixed; axis-aligned angular attachments retain tangent
directions. Certified exterior straight-site gaps constrain whitespace; exact polynomial reassembly removes equivalent
subdivision. The native-Y/automatic-X slice requires one closed line/quadratic contour, exact paired reassembly and
lossless command representation. Unsupported geometry retains the preceding sequence.

**Approved comparison scope:** the 58-glyph comparison approved on 2026-10-27 supports adoption. Roboto 400/16 `c` thins
end-region normal widths and cap spans from about 1.44 to 1.05/0.95 px, retaining its 1 px upright, 3 px opening and
four end tangents. Six pixels are removed. Review against `e o s` supports the retained shape and weight in scope.

| Additional scope    | Assessment question                                          |
| ------------------- | ------------------------------------------------------------ |
| Roboto 400/12 `c`   | One pixel removed; inspect end continuity and curve weight.  |
| Roboto 400/16 `C`   | Four pixels removed; inspect opening and curve/end balance.  |
| Roboto 400/18 `C c` | Mixed ink changes; inspect placement, stepping and contrast. |
| Roboto 400/20 `c`   | Two pixels removed; inspect end shape against the upright.   |

Regular 14 px and tested 16 px weights 300/700 retain bitmaps despite geometric changes. Source Sans `h`/`m` and Roboto
Flex `k`/`s` controls abstain under correspondence limits. Multi-contour shapes, moving joins and unrecognized curved
white features remain unresolved; unchanged output does not establish their correction.

### Local curved-stroke widths

The [curved-width model](../../hobby-fitting.md#joint-placement-and-smooth-curve-continuation) measures source thickness
through certified opposing borders regardless of orientation. Straight/curve attachment polynomials stay fixed while
interior controls can join the source-relative solve, replacing whole-outline exclusion caused by tiny vertical
terminals. Local ownership adapts Hobby §6 and Hersch §2; segment length is not an eligibility threshold. Exact constant
lines are omitted from certificate adjacency without changing source operators/coordinates; real edges and independent
source/upstream/candidate certificates remain authoritative.

**Confirmed height defect, corrected:** Roboto Flex Regular `k`, 16 px at default axes, has a flat source cap below a
taller upright. A former terminal solve raised one endpoint from 9 to 9.3125 px because a global cap box missed that
edge. [Reference-height constraints](../../hobby-fitting.md#terminal-reference-height-constraints) retain both at 9 px
inside the width solve. Independent geometry and browser output support the correction.

**Pending placement/width assessment:** Roboto/Roboto Flex/Source Sans 3 controls span 12/14/16/18/20/24 px, weights
300/400/700 and both hint modes. Against the preceding local-curve candidate, changes are confined to `k x z` (184
outlines, 39 bitmaps); all 2,771 terminal reference edges retain height. Quantized horizontal `x`/`y` edges with nonzero
unrounded source slopes correctly receive no height constraint. Evidence: `out/diagnostics/robotoflex-k-cap-20261022/`.

Roboto Flex Regular 16 px `s` thins three middle-width samples from about 1.60 to 1.30–1.34 px and removes two pixels,
with attachments/Y fixed. Inspect curvature, staircase continuity and upright balance. At 12 px ink is unchanged; 14/18
px thin locally, 20 px mixes additions/removals and 24 px adds ink. Source Sans `h`/`m` attachment controls retain
preceding output. Assessment of `5 G J S U c s` and mixed outlines remains open; retaining Y limits nearly horizontal
corrections, and a two-dimensional placement solve is outside this slice.

### Equal-source upright weight investigation

**Confirmed inherited defect:** earlier main-page Literata 400/16, `opsz=16`, delivered a one-column `t` body against
two-column `i f l` despite equal 93-unit (1.488 px) source uprights. Upstream automatic fitting already placed `t` at
X=2–3 versus `i` at X=1–3. Engine, correction and scanner controls did not remove the discrepancy.
[Hersch §6](../../references/papers/1993-hersch/paper.md) and
[FreeType width normalization](https://freetype.org/autohinting/widths.html) ground the equal-source relationship.

The diagnostic hint plan supports an internal cause: the 93-unit body and narrower head share the source right edge at
X=208.
[Upstream edge-link selection](https://github.com/googlefonts/fontations/blob/skrifa-v0.48.0/skrifa/src/outline/autohint/topo/edges.rs#L230-L263)
prefers the narrower separation, collapsing both left edges to X=2. The public ahead-of-time plan is not a runtime
trace; runtime captures independently confirm unequal bodies. With matching optical size, 12/14 px bodies are one column
throughout, 15/16 px show the mismatch, and 17/18/20 px are two columns. Evidence:
`out/diagnostics/literata-t-20261029/`.

The [shared-border candidate](../../hobby-fitting.md#shared-border-upright-normalization) used certified unanimous
integer donors, related upper/body widths and one shared displacement. It corrected body weight but was rejected for
source-detail loss and attachment distortion. The [paper comparison](../../references/upright-stem-consistency.md)
records the sourced alternatives; the accepted replacement follows.

#### Source-detail review: candidate requires revision

**Historical rejection, superseded below:** Literata 400/16, `opsz=16`, retained only 1.25 px of a 1.776 px raw source
head profile (1.765625 px in captured source), with the upper tangent's horizontal component lost upstream. Translating
the compressed hinted chain could not restore it. Differential movement also fixed the cap between moved borders and
reversed an attached foot quadratic's curvature despite prior topology/tangent checks. These were confirmed
source-fidelity defects, not acceptable deviations. The
[source-detail review](../../../out/diagnostics/upright-stem-implementation-20261029/verification/upper-stem-detail-review.md)
records why source curve, tangent, cap and attachment relationships must participate in one solve.

#### Source-shape correction: approved with limits

The [automatic-Y coupled shape model](../../hobby-fitting.md#automatic-y-coupled-shape-mode) translates the raw source
head profile and couples it to the certified body standard in one bounded whole-outline solve. Source-relative cap and
curve relationships replace hinted-chain translation. Smooth interior knots remain free under retained Y; source-sharp
corners retain orientation. Quantization reserve stays inside original per-owner movement caps. Runtime/capture
identities and historical replay ownership belong to the [revision index](README.md) and owning model.

**User approval, 2026-10-29:** the reviewed 19-case comparison accepts the changed Literata `t` at 15/16 px, weight 400
and matching optical size, with the shown Mono settings. Approval covers body weight, restored upper-left outline, cap
relationship and changed crossbar/foot appearance. The top three bitmap rows remain unchanged despite restored source
profile and upper tangent: an accepted limitation, not approval of unseen corpus cases. The separate approved baseline
remains independent.

The [source-shape report](../../../out/diagnostics/upright-source-shape-20261029/report.md) retains detailed evidence.
The [delivery report](../../../out/diagnostics/approved-main-refresh-20261029/REPORT.md) verifies native/browser/export
agreement at 15/16 px and the existing main-page matrix: only its Literata 16 px image package changed. Rejected
historical packets retain their original replay interpretation.

### Roboto c source correspondence

**Pending existing imbalance:** default Roboto 400/16 `c` has heavy ends relative to its upright. The source-only
investigation attributes it to upstream fitted geometry; retained attachments and same-outline scanner controls
reproduce it without dropout rescue. This is not a regression introduced by the probe.

The [correspondence study](../../hobby-fitting.md#source-feature-correspondence-probe) tests analytic source events,
opposing borders and shared dependencies without StrokeStyles. Six extrema survive exact subdivision, but eight
certified curve contacts become twenty-four: primitive counts are not canonical identities or fitting weights. Source
Sans single-contour controls fail substitution certification; tested multi-contour controls abstain. Feature extent,
shared ownership and apertures remain unresolved, so attachment pins cannot simply be released.

Exact rational subdivision abstains when coordinates cannot be represented in the diagnostic binary format. Four Source
Sans controls hit that limit; earlier rounded results do not establish exact invariance. Evidence remains under
`out/diagnostics/source-correspondence-20261027/`, with preceding captures/research under
`out/diagnostics/roboto-c-20261026/` and `out/diagnostics/roboto-c-terminal-model-20261026/`.

### Fast-math visual assessment

**Declined: confirmed reviewed regression.** [Global fast-math](../../hobby-fitting.md#global-fast-math-experiment)
changes Mono pixels with layout retained, negates much of the reviewed diagonal compensation and loses compensated
arithmetic. A [selective solver experiment](../../hobby-fitting.md#selective-solver-arithmetic-experiment) investigates
a narrower arithmetic seam while keeping geometry strict.

At 16 px, weight 400, selective hints and FreeType Mono, paired views show heavier diagonal spans in Roboto `2 M V Y w
y` and Source Sans `< Z z`. Changes in `* ^ S # K k s` include tips, corners and curves. Local shape/contrast questions
remain pending; counts do not establish improvements or fitting exceptions.

## Scan conversion and preview

### Native monochrome scan conversion

Candidate Mono uses
[FreeType 2.15.0's monochrome scanner](https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c) on
the whole fitted outline. Nonzero-winding center fill and two-direction dropout replace the former thresholded
coverage/dropout approximation. Zeno coverage remains diagnostic for Mono; Gray, baseline and independent reference
retain their own policies. The [generator API](../../../crates/generator/API.md#working-candidate-fitting) owns scan
controls and coordinate rounding.

Executed TrueType
[SCANCTRL/SCANTYPE](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scan-conversion-control)
state follows [FreeType loader semantics](https://github.com/freetype/freetype/blob/VER-2-15-0/src/truetype/ttgload.c),
including component markers and final composite global state. This transports metadata without changing fitting or
engine selection. Automatic fitting executes no bytecode and uses its fallback; live defaults come from the
[shared policy](../../../apps/web/src/app/renderer/preview-policy.ts).

**Confirmed scoped continuity correction:** Source Sans 3 ExtraLight 200/16 regains the source-connected `e` crossbar
attachment and shortened `x c k w` ends on identical outlines, matching independent full FreeType. Browser inspection at
14/16/20 px weight 200 and 16 px weights 400/700 supports those local corrections. Restored ends add ink; this is not
general weight preservation or broad font-mode acceptance.

**Unresolved controls:** font hints first at Roboto 400/14, `wdth=100`, retains unequal `m`/`u` principal stems against
`n`. Current selective automatic-X/native-Y captures at 12/14/16 px measure 1 px straight spans throughout; that
native-X defect is not reproduced there. Shoulders/bowls remain pending, including a two-column 14 px `u` bowl. The
[Roboto investigation](../../references/roboto-stem-balance.md) owns that distinction. Literata 400/16, `opsz=12`,
retains equal inspected `i`/`j` bodies; default Roboto Flex 16 px retains readable inspected joins/counters. Neither
extends approval to other weights or sizes.

### Curve scan precision

Candidate Mono requests FreeType's
[high-precision hint](https://freetype.org/freetype2/docs/reference/ft2-outline_processing.html#ft_outline_xxx). Its
[subdivision policy](https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c#L522-L563) uses finer
intersections for small bitmaps while preserving supplied geometry, origin, metrics and dropout semantics.

**Confirmed scan defect, corrected:** Roboto Flex Regular 16 px, default axes, diagonal fitting off, had an extra
lower-right bowl pixel in `q`/`g`. The curve lies about 0.013 px above the pixel center but ordinary subdivision rounds
onto it. High precision removes the pixel, matching independent full FreeType on identical geometry; the local
correction also applies at 15/17 px.

**Broader assessment pending:** five-family controls cover 12/14/16/18/20/24 px, weights 300/400/700 and Source Sans 3
200, both hint preferences. Roboto Italic 300/12 quotation strokes and Source Sans 3 200/300 at 20 px percent-sign parts
separate. Component increases alone do not demonstrate broken strokes; inspect curve weight, counters, joins and size
transitions.

### Terminal tips and junction continuity

Roboto Flex default 400/16 has a confirmed lower-right `k` extension from stub rescue, also seen at 12–19, 21–22 and 24
px. Global exclusion removes it but breaks the ExtraLight Source Sans 3 200/12 `R` leg and opens source-connected
`6`/`9` bowls at 12–13/12–15 px. **Global exclusion is held for those confirmed regressions.** Simple/smart dropout and
ordinary/high precision do not provide join protection.

[FreeType's recognizer](https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c) classifies scan
profiles and extrema, not semantic endpoints/junctions.
[Hobby §3.2](../../references/papers/1993-hobby/paper.md#32-width-control) grounds a broader medial-axis hypothesis for
terminal branches and counter paths. Filled shapes, overlaps, holes, ambiguous ownership and movement-free raster
integration require a separate design; uncertainty must retain the scan.

The narrower supporting-cap adaptation below proves a straight cap supports the whole filled shape and both adjacent
borders continue into the filled half-plane. Curves, internal junctions, holes and ambiguous overlaps remain unchanged.
The same geometric rule must suppress terminal extensions while retaining source-connected joins.

Default Roboto Flex 400/16 `1` has a separate upstream imbalance unaffected by stub policy: automatic fitting narrows
its stem from 1.5 to 1 px while retaining roughly the slanted head's source thickness. The
[source-relative correction](#source-relative-straight-stroke-correction) owns that scoped fitting change.

#### Supporting-cap correction assessment

The explicit `free_type_mono_terminals` stage adopts the conservative supporting-cap correction. Matching source/fitted
ownership, a whole-outline supporting half-plane, adjacent-border continuation and a unique finite cap crossing the
rescued pixel square are required. Other boundaries, curve hulls and uncertain predicates veto suppression; optional
work exhaustion keeps the original scan. This is not general medial-axis terminal recognition.

**Confirmed scoped correction:** browser inspection supports removal of the extra default 16 px `k` tip pixel while
retaining ExtraLight `R 6 9` attachments at 12 px and original scans at their other affected sizes. Geometry, coverage,
frames and metrics stay fixed. The 52-case sweep removes 217 certified rescue pixels from 150 glyphs without changed
component/counter counts; broader terminal shape/weight assessment remains pending. Supporting long borders can pass
eligibility: cap-square/other-boundary gates are safeguards, not semantic ownership proofs.

The `k` extension is suppressed at 13/16/19/22 px in the 12–24 px sweep; other sizes can abstain and retain it.
Historical roles, Gray and the separate approved baseline remain outside this stage.

### Landing comparison scan parity

**Confirmed correction:** Rouge Script Regular 20 px previously lost the `t` tip/crossbar and `d` bowl attachment when
landing capture disabled stub rescue. Rescue alone restores three `t` and two `d` pixels without changing outlines,
coverage, bounds or advances. Disabling fitting or terminal suppression does not remove that cause.

Captures share the [working-preview policy](../../../apps/web/src/app/renderer/preview-policy.ts); compatibility and
stale-capture rejection belong to the [web contract](../../../apps/web/CONTRACT.md), converter adaptations to the
[methodology](../../references/font-converters.md). Earlier 16-case scan/shared-policy controls remain under
`out/diagnostics/landing-samples/preview-scan-correction-20261027/` and
`out/diagnostics/shared-preview-settings-20261027/`. Other changes, including mixed Literata 16 px and Rouge Script 8–16
px ink redistribution, retain pending optical status. Historical sweeps do not define current publication scope.

### Defined preview palettes

Browser-local palettes provide 2/4/8/16 coverage colors, defaulting to Monochrome. Gray retains upstream Normal fitting
and Alpha coverage; palettes do not change geometry/layout. This extends
[scalar quantization](../../references/papers/2006-gallager-quantization/paper.md), not fitting. Coverage-index behavior
belongs to the [WASM contract](../../../crates/wasm/README.md#render-spec-controls). Palette-lab browser masks and
nearest-level linear-light specimens are illustrative and need not match native quantization.

## Spacing, glyph selection and display

### Coordinate-selected scalar glyphs

OpenType
[required variation alternates](https://learn.microsoft.com/en-us/typography/opentype/spec/features_pt#tag-rvrn) and
[GSUB variations](https://learn.microsoft.com/en-us/typography/opentype/spec/gsub#featurevariations-table) can select
another outline for a scalar. Resolve it at the requested axes before drawing; Unicode identity stays fixed while
geometry, metrics and pair expectations follow the selected glyph.

Compare shaped advance with the shaper's
[own metric callback](https://docs.rs/harfrust/0.14.0/harfrust/trait.FontFuncs.html) in its integer domain, avoiding
confusion between variation-delta rounding and positioning. Roboto Flex `$`, 14 px, `opsz=14`, `wdth=100`, selects glyph
7 at weight 400 and glyph 602 at 700, for slant 0 and -10. This fixes the previous capability rejection across
rendering/kerning inspection. Contextual substitutions, count/order changes and unrepresentable positioning remain
outside the [supported input contract](../../../crates/generator/README.md#supported-input-and-output).

### Pair spacing and kerning

The [bitmap policy](../../../crates/generator/API.md#live-spacing-api) separates images, advances and pair adjustments.
Fitted advances are used when available, otherwise rounded source advances. Fixed-pitch cells and source-tabular digits
retain common source relationships. Source kerning and available bearing correction resolve once into sparse integer
adjustments; integer accumulation makes each pair prefix-independent. Nearest rounding uses signed half ties away from
zero. Intentional overhang remains, without a neutral blank-column floor. Reference/historical source-linear layout is a
diagnostic control; integer metrics are deliberate, not a bitmap-format requirement.

Foundations are [FreeType metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html),
[kerning](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html),
[Turner–Lemberg metric fitting](../../references/papers/2003-turner-lemberg/paper.md) and
[Hersch §§5–6](../../references/papers/1993-hersch/paper.md). Candidate Gray shares captures/metrics with specimens and
exports; its previous production-target preview is not a pixel-identity reference. Broader Gray assessment remains
pending. The removed projected-gap algorithm was internally consistent in the Roboto 400/14 `AV`/`VA` control, but
perceived diagonal separation was unassessed; it is not a current layout mode.

**Pending Literata spacing assessment:** at 400/16, `opsz=16`, `ck`, `ic` in “quick” and `or` in “liquor” have these
source-to-fitted measurements:

| Pair | Source kern (px, 26.6) | Residual difference (1/64 px) | Outline gap increase (px) |
| ---- | ---------------------: | ----------------------------: | ------------------------: |
| `ck` |              −0.109375 |                            28 |                     0.499 |
| `ic` |              −0.015625 |                            30 |                     0.484 |
| `or` |              −0.156250 |                            14 |                     0.391 |

Each source adjustment rounds to zero and each residual stays below the one-pixel correction boundary. No correction is
missing or doubled. Fitted `c`/`o` advances are 9/10 px versus source 7.984375/9.375 px; the three delivered ink boxes
each leave two blank columns. Bounds do not estimate optical space: the open `c` bowl and facing curves contribute
different whitespace by row. Native captures match publication; overlay-off, forced-auto and hints-first controls retain
the same pair metrics. `ck`/`ic` gap changes reverse at 8/20 px and are small positive at 12 px. These observations do
not establish a contract failure or universal correction. Evidence: `out/diagnostics/literata-spacing-20261029/`.

Front-page comparisons enable source kerning with zero extra tracking. The
[methodology](../../references/font-converters.md#source-kerning) owns native support and composition adaptations;
enabling kerning does not itself resolve these optical concerns.

#### Fitting-bearing compensation investigation

Automatic-Mono captures retain left/right metric-point rounding residuals. Selective fitting carries those of the X
owner identically across scanners. Independent reference, native/interpreter, unhinted, Gray and non-Mono captures
contribute none; fixed-pitch and source-tabular digits have zero residuals.

[FreeType's integer-positioning example](https://freetype.org/freetype2/docs/reference/ft2-glyph_retrieval.html#ft_glyphslotrec)
compares preceding right and current left residuals at its half-pixel boundaries. The
[pinned loader](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/afloader.c#L462)
defines them as rounded minus pre-rounding metric position after small-bearing adjustments. Skrifa's
[`AdjustedMetrics`](https://docs.rs/skrifa/0.48.0/skrifa/outline/struct.AdjustedMetrics.html) exposes the rounded
advance and optional bearing but discards these intermediates; the integrated snapshot retains them. Final
bounds/advances cannot uniquely reconstruct that error.

Independent FreeType controls remain under `out/diagnostics/fitting-compensation-20261026/`. Skrifa's empty-outline
phantom fallback differs from FreeType's skip, without integer placement impact at the approved setting. A historical
full-ASCII Literata probe encountered 27 unsupported pairs: a strict shaping-coverage limit, not evidence that supported
subsets cannot use source kerning.

#### Compensated-spacing runtime adoption (open iteration)

Compensation is adopted. Human approval covers the reviewed Roboto 16 px, `wght=400`, `wdth=100`, forced automatic Mono,
FreeTypeMono, diagonal fitting on, source kerning on and zero tracking. Broader combined-policy optical assessment
remains open.

#### Browser comparison for optical assessment (question, not a verdict)

The [approved-setting proof](../../../out/diagnostics/fitting-compensation-review/www/proof-kerning-on/index.html)
compares original, recovered-residual and FreeType-vector-substitution arms on identical glyphs, advances and bitmaps.
Its [rework proposal](../../../out/diagnostics/fitting-compensation-review/rework-proposal.md) records ArrowType control
strings/corpus provenance. Other frozen packets remain diagnostics; canvas agreement establishes comparable output only.

#### Fractional source advances and bitmap placement

**Confirmed prefix-dependent defect, corrected:** default Roboto Flex 14 px had equal 7.90625 px source digit advances.
Fractional accumulation placed the final `98` at a 7 px step in `909192939495969798` and 8 px in `09192939495969798`,
causing touching versus a blank column. Kerning was irrelevant. Fitted automatic advances are 8 px, matching independent
FreeType. Bitmap placement retains that step in both strings, Mono/Gray and both engine policies. Width/wrapping changes
are intentional: eighteen advances total 144 rather than 142.3125 px. Broader optical assessment remains pending.

#### Proposed optical pair-spacing experiment

**Project hypothesis; unimplemented and not adopted:** preserve each source pair's estimated optical separation through
fitting, changing placement while retaining final outlines, rasters, offsets and advances. This is separate from metric
residual recovery and is not an optical improvement claim.

[FontForge's estimator](https://fontforge.org/docs/ui/dialogs/autowidth.html) weights facing outline-envelope
separations by `1 / (separation + em_size / 50)^2`, excluding empty shared bands. Resolve documentation/native
differences against the
[pinned implementation](https://github.com/fontforge/fontforge/blob/c41bdb922285f35defd1e1385adfd13bde1ab32a/fontforge/autowidth2.c):
documented/AutoWidth bands default to em/100, native pair paths to em/200; envelopes are floored in design units, the
upper loop band is excluded, and rounding uses C `rint`. Preserve its license and record parameters. Flooring directly
in pixels would be a different adaptation.

For selected source/fitted outlines in a common baseline frame, let `S` be adjacent-box optical separation and `d` the
origin step. FontForge's translation assumption gives:

```text
D(d) = d + xmin_right - xmax_left + S
d_source = source_advance_left + source_pair_adjustment
D_fitted(d_required) = D_source(d_source)
pair_adjustment = round(d_required - finalized_advance_left)
```

Calculate weights once at adjacent boxes. Round the signed adjustment once, not the absolute step; replace the pair
adjustment rather than adding kerning/bearing compensation again. Apply tracking afterward. The source-pair target is
our adaptation: FontForge normally targets a common chosen separation.

Empty glyphs, spaces, no-shared-band pairs, fixed-pitch fonts and source-tabular digit pairs retain placement with
recorded abstentions. Preserve source overlaps and unsupported-shaping errors; non-finite geometry fails. Do not add
collision clamps, blank-column targets or glyph exceptions.

First verify pinned-estimator parity, translation, scale, unchanged-source identity, rectangles, curves and empty bands;
failure stops expansion. Then compare kerning off/on, available residual compensation and optical placement over Roboto,
Roboto Flex, Source Sans 3 and Literata at 12/14/16/18/20/24 px, weights 300/400/700, default remaining axes and
independent optical-size endpoints. Include fixed/tabular controls, punctuation, supported accented scalars, repeated
letters, words, straight/curved/diagonal pairs and alternate prefixes. Keep automatic, selective, overlay and supported
Gray pipelines distinct.

Retain identities, exact settings, envelopes, fractional targets, integer tables and abstentions. Verify unchanged
images/advances, single pair application, prefix independence, tracking separation and shared measurement/wrapping
inputs. Use an isolated browser comparison for native/enlarged assessment of rhythm, punctuation and word boundaries.
Adoption requires optical assessment and shared finalized metrics; preview scope and the separate approved baseline stay
unchanged.

### Tracking and word separation

[FreeType metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) and
[BMFont](https://www.angelcode.com/products/bmfont/doc/file_format.html) separate images, advances and pair adjustments;
Hersch §5 explains why fractional movement changes raster phase. The explicit pipeline adds signed whole-pixel tracking
uniformly to finalized advances, including spaces and the final glyph, in Mono and Gray. Negative tracking can narrow
word gaps or overlap glyphs; zero is identity, with no clearance floor or word-gap refund.

Export bakes tracking into advances and retains pair adjustments once. The
[tracking contract](../../../crates/generator/API.md#tracking-policy) owns ranges, historical protected behavior and
adapter representability. Static comparisons retain zero unless requested. This is not optical rekerning or acceptance
of a chosen spacing value.

### Source-kerning inspection

Authentic source pair adjustments are exposed independently of experimental placement through the
[WASM inspection interface](../../../crates/wasm/README.md#kerning-pairs).

### Preview display scaling

Fractional browser composition can make equal native stems appear unequal.
[devicePixelRatio](https://developer.mozilla.org/en-US/docs/Web/API/Window/devicePixelRatio),
[CSS image rendering](https://drafts.csswg.org/css-images-3/#the-image-rendering) and
[Chromium canvas snapping](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/core/paint/html_canvas_painter.cc)
ground the optional [display policy](../../../apps/web/src/app/renderer/display-scaling.ts): align origins/extents and
show native pixels as equal integer blocks of physical pixels. Controlled fractional composition reproduces the
artifact; the user's specific cause and other compositors remain unassessed.

## Earlier controls and remaining findings

These findings retain their captured policies. Retired candidates and isolated comparisons below do not describe the
current default or establish new optical approvals.

### Symmetry and grid placement

At Roboto 400/14, `wdth=100`, Mono threshold 128, preceding baseline/candidate native/browser outputs agree. **Confirmed
former imbalance:** nearly equal source `A` legs became about 0.98/1.22 px; source apex offset about −0.007 px grew to
−0.383 px upstream and −0.516 px in the project fit. Different prepared slopes and independent width rounding amplified
it. Source slopes alone could not apply one leg at 14–16 px within movement bounds; a source-endpoint experiment
restored the relationship at 13–20 px while accepting fewer constraints elsewhere. Ownership/fallback remained
unresolved.

**Pending phase findings:** diagnostic `o` centering from 3.90625 to 4 px and `v` translation by 0.125 px restored
binary symmetry at that coordinate without proving a general placement rule.
[Hersch](../../references/papers/1993-hersch/paper.md) explains phase sensitivity;
[Shamir](../../references/papers/2003-shamir/paper.md) grounds ownership/conflict resolution. Neither supplies a
glyph-specific mirror target.

#### Vertical-only candidate findings

Retired source-X fitting corrected the `A` apex displacement to about −0.008 px at 14 px and retained the relationship
at 13/15/16/18/20 px. This was geometric correction, not complete optical acceptance. At 14 px, `o` became
binary-symmetric; source-centered `v` stayed asymmetric with a dropout terminal pixel. Phase/weight questions were not
resolved by forcing mirrors or centering witnesses.

#### Native-coverage A asymmetry: overlap coverage and phase

**Confirmed superseded-raster limitation:** Roboto 400/14 `A`, `wdth=100`, threshold 128, had one unequal below-crossbar
pixel pair despite source X, matched Y and no dropout. Three same-winding overlapping contours produce Zeno coverage
133/96. Independent filled-union clipping/integration gives about 113.88/81.07; equivalent-union raster gives 113/81 and
removes the extra pixel.

The source center is 4.578125 versus bitmap axis 4.5 px. A diagnostic −0.078125 px shift also hides the pixel but
changes placement and conceals the overlap issue. Union coverage and other checked sizes remain asymmetric. Source,
outline, coverage and binary symmetry differ. This motivated
[FreeType overlap mitigation](https://freetype.org/freetype2/docs/reference/ft2-outline_processing.html#ft_outline_xxx),
not a centering rule.

#### Overlap-aware raster investigation

The historical experiment adapted
[FreeType's overlap raster](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/smooth/ftsmooth.c#L317-L436):
scale an already fitted outline 4×, reduce on the native grid with per-contribution rounding/saturation, threshold once,
then apply original-outline dropout once. One-final-round averaging was a diagnostic alternative, not FreeType parity.
Neither changed fitting size, origin or metrics. Integer-aligned tiles bounded temporary coverage storage, each
receiving the full path to preserve winding contributions.

For 14 px `A`, reductions gave 115/86 or 115/85 versus 133/96, mitigating the extra pixel. **Residual limitation:**
duplicated contours still changed coverage (an identical rectangle totaled 734 versus 859 in one-round 4× coverage).
Opposite-winding disjoint strips could cancel within one native pixel; oversampling separated them. Non-overlapping
paths also changed quantization. Finite oversampling did not establish filled-set invariance.

The five-family 1,900-glyph sweep found no increased component counts, but Source Sans 3 400/14 `!` connected dot/body
at coverage 128 and 400/16 `[` changed three components to one. Mark clearance, weight, joins and counters remained
pending independently of counts. Relevant witnesses did not set the overlap flag.

[FontTools overlap removal](https://fonttools.readthedocs.io/en/latest/ttLib/removeOverlaps.html) and
[Skia Simplify](https://github.com/google/skia/blob/main/include/pathops/SkPathOps.h#L52-L65) were alternatives for a
temporary filled raster path, requiring hole/component preservation, failure handling and dependency assessment.
Rewriting fonts can alter hints/bearings; intersection removal alone misses disjoint signed-area cancellation. Native
Mono scan conversion supersedes this coverage experiment.

#### Terminal stubs and dropout

The former threshold/dropout adaptation excluded caps closing before the next pixel-center scan line using actual arc
continuation/extrema, following
[SCANTYPE mode 5](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scantype) and the
[FreeType recognizer](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/raster/ftraster.c#L2206-L2242).
It did not reproduce TrueType center fill or overshoot exceptions and is not current scanner policy.

**Confirmed historical terminal defect:** default Roboto Flex 400/16 `x` had equal source/interpreter terminal heights
at 8.21875 px, but rescue promoted left-cap coverage 34/255 to ink and added one arm's row. Exclusion removed it and
analogous additions at 14/18/20 px. **Pending:** Literata 400, matching optical size, `E` at 14/16/18 px and `@` at 14
px opened small terminal white regions without principal-stroke breaks. Serif attachment, shoulder balance and counter
openness were unassessed. Tiny marks could disappear when all rescues were stubs; complex contours could exhaust bounded
work rather than bypass the rule.

#### Binary stem weight and source phase

**Confirmed source-X/binary-coverage defect:** Roboto 400/14, `wdth=100`, threshold 128, delivered two-column `m`
middle, `u` right and `t` stems against one-column neighbors. All `m` source stems are 1.265625 px yet rasterize
one/two/one. Source/candidate X match; dropout/overlaps do not explain the straight spans. Adjacent coverage examples
are 128/196 (`m`), 132/196 (`u`) and 148/176 (`t`).

[Hersch §§5–6](../../references/papers/1993-hersch/paper.md#5-basic-grid-constraints) and
[ttfautohint](https://freetype.org/ttfautohint/doc/ttfautohint.html#smooth-hinting) explain one/two-column phase changes
for fractional widths. The 4× raster added four `m` pixels at an analytic half-coverage edge but left `u`/`t` unchanged;
one-final-round averaging retained the doubling. Overlap removal, tie adjustment or thickening normal neighbors did not
resolve the full defect.

##### Main-page source-stem calibration

Earlier captures chose one global family/size weight so source `H I l` body sections fit within one pixel. This
controlled common inputs, not every serif/join/diagonal. The current
[configuration](../../../apps/web/scripts/landing-samples/main-page.json) supersedes calibration. Earlier native
converter differences remain **pending weight/continuity assessment**:

| Family/size      | Earlier axes              | Converter                    | Witness                     |
| ---------------- | ------------------------- | ---------------------------- | --------------------------- |
| Roboto 12        | `wght=367.07`, `wdth=100` | pdfontconv, Tophat, Adafruit | `H` has one/two-pixel runs. |
| Roboto Italic 12 | `wght=372.63`, `wdth=100` | pdfontconv, Tophat           | `H` has one/two-pixel runs. |
| Roboto Italic 20 | `wght=253.69`, `wdth=100` | pdfontconv, Tophat, LVGL     | `H` has one/two-pixel runs. |
| Literata 16      | `wght=252.22`, `opsz=16`  | pdfontconv, Tophat           | `H I` have two-pixel runs.  |

#### Coupled width geometry: research direction

[Hobby](../../references/papers/1993-hobby/README.md) motivated source-normal widths, shared relative errors and
whitespace features rather than orientation-specific fixes. The
[equation audit](../../references/papers/1993-hobby/audit.md) and
[prototype](../../../experiments/hobby_fitting/README.md) retain the original research. Sampled curve strain was a
project adaptation; normals alone allowed excessive movement. Real recognition, integer targets, ownership and
center-fill compatibility required further validation. Later adopted slices do not imply a general solution for all
curves, joins and counters.

#### Upstream Mono assessment

**Confirmed existing control imbalance:** Roboto 400/14, `wdth=100`, hints first retained one/two/one `m`, one/two `u`
and two-column `t`; italic `m` retained one/one/two. Automatic fitting restored equal regular stems but made `A` legs
one/two at Y=4–6; `v` stayed two/one. Neither justified per-glyph engine selection. Skrifa 0.48.0/HarfRust 0.14.0
controls reproduced earlier automatic pixels; upgrading dependencies alone was not the remedy. Commands belong to the
[comparison tool](../../../experiments/stem_policy_comparison/README.md). Current selective straight-span findings are
recorded under native scan conversion above.

### Compact marks and stem ownership

The earlier compact-mark experiment assigned detached convex quadratic contours independent dimensions/clearance,
grounded in [Microsoft dot values](https://learn.microsoft.com/en-us/typography/truetype/from-typeface-to-font-file),
[Google Fonts dot guidance](https://googlefonts.github.io/how-to-hint-variable-fonts/),
[Shamir §3](../../references/papers/2003-shamir/paper.md) and
[FreeType widths](https://freetype.org/autohinting/widths.html). It was superseded by now-retired source-X fitting and
is not a current mark owner or one-pixel floor. Balance, tangency and clearance across `! . : ; ? i j` remain pending;
earlier assessment does not approve later geometry. Current body/mark positioning belongs to
[x-height alignment](#source-defined-x-height-alignment).

### Remaining stroke balance

The earlier [joint/smooth-curve candidate](../../hobby-fitting.md#joint-placement-and-smooth-curve-continuation)
retained native coordinates/layout. Its Roboto 400/16, `wdth=100`, Mono, hints-on findings remain scoped questions:

| Feature | Change                                                             | Pending question                                                         |
| ------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| `s`     | Ink 29→25; frame 7→8 px.                                           | Lower bowl, terminals, continuity and spacing of the lighter/wider form. |
| `x`     | Width about 0.89–0.92→1.11–1.15 px; ink 18→23; symmetric crossing. | Weight, half-pixel phase and side-bearing balance.                       |
| `S`     | Ink 32→26; frame 8→10 px.                                          | Contrast, terminals, openings and spacing.                               |
| `X`     | Phase about +0.5 px; mean width 1.49→1.18 px; ink 28→32.           | Crossing, arm and side-bearing balance.                                  |

Default `2` retained divergent borders (47.24°/43.61°) and a heavy lower staircase: fixed curve-incident endpoints
conflicted with grid/parallelism constraints, motivating attached-diagonal continuation.

**Confirmed excluded regressions:** free-Y broke Source Sans 400/14 `h` and 300/12 `m`; retained-Y broke 300/14 `h` and
400/14 `m`; upright-X pins still broke 300/12 `h`, in both hint modes. The isolated candidate abstained on
source-vertical mixed outlines, preserving those attachments and leaving `c 5 G J U` unchanged. Later eligibility does
not erase those regression controls or the unresolved moving-join problem.

### Attached diagonal consistency

The [attached model](../../hobby-fitting.md#attached-diagonal-and-curve-constraints) shares straight/curve variables
with Y, upright X anchors and layout retained. Sharp corners may rotate without reversing orientation; curve joins
retain signed cross (zero at source-smooth joins), with curvature/tangent inequalities protecting bowls.

**Scoped visual acceptance:** Roboto 400/16, `wdth=100`, hints on, `2` was accepted on 2026-10-21 in the
[comparison](https://solitaire.taile005dc.ts.net:8909/). Ink fell 30→26 with a thinner continuous staircase and
connected bowl/baseline. Only that default `2` is accepted. **Pending:** default `5` redistributes stem/bowl/top-bar ink
without changing its total; 14 px `2` thins, the 300/12 control stays unchanged, and Source Sans 400/16 `v`
redistributes terminal/apex ink. Broader `2 5 V v W w X x Y y S` cases require their own weight, join and spacing
review.

### Combined text assessment

The [combined comparison](https://solitaire.taile005dc.ts.net:8910/) retains identical advances/pair placements against
its width-only control. Inspected Roboto 300/12/16, 400/12/14/16/20 and 700/12/16 hints on, plus 400/700 at 16 px hints
off, and Source Sans 300/12, 400/14/16 and 700/14 support retained attachments/readability without a demonstrated new
break or collision. This is a bounded observation, not full-matrix approval.

| Scope                              | Pending tradeoff                                                                   |
| ---------------------------------- | ---------------------------------------------------------------------------------- |
| Roboto 400/16 `x X`, hints on/off  | Heavier symmetric crossing and changed placement.                                  |
| Roboto 400/20 `s`, hints on        | Flatter/squarer upper shoulder.                                                    |
| Roboto 700/12 `S`, hints on        | Wider form; ink 37→42; terminal/opening contrast.                                  |
| Source Sans 700/14 `s`, both modes | Pinched upper aperture enclosing one white pixel under four-neighbor connectivity. |

Roboto 300/16 `5` loses an enclosed white pixel but retains an open connected source-like lower bowl; default `5` keeps
its attachment, with weight still under assessment. Source Sans 300/12 stays unchanged. The 386 changed bitmaps across
6,840 cases and unchanged ink-component counts establish scope only; 18/24 px and remaining combinations stay pending.

### Source Sans crossing balance

The [source assessment](../../hobby-fitting.md#source-contrast-and-crossing-assessment) finds small real arm contrast:
Source Sans 400/16 `x` widths about 1.125/1.186 px and `X` about 1.185/1.245 px, not exact reflection.

**Confirmed unresolved fitting/raster imbalance:** default 16 px `x` gains an upper-right row despite equal terminal
heights and approximately preserved source contrast; it predates the combined candidate. Restoring automatic Y in a
causality control removes that row but leaves unequal terminal ink. At 14 px the geometrically thinner arm has a
two-pixel lower terminal against one on the other; staircase significance remains pending. The crowded 12 px `X`
crossing is inherited; 16/20 px separation equalization trades away source contrast without eliminating all staircase
asymmetry.

**Confirmed representation limit:** captured collinear quadratics make attached fitting abstain on `x` at 14/16/20 px
and `X` at 12/14 px, although unrounded 16 px `x` source curves have nonzero curvature (maximum discrepancy about 0.013
px). Weakening the gate cannot recover lost information. Retain unrounded features while keeping delivered
rounding/native coordinates authoritative.

The [curved continuation](../../hobby-fitting.md#curved-crossing-prototype) supplies an isolated X solve with finite
source-relative reflection/width terms, retained Y/layout and quadratic attachments. A separate-hook fork is not a
common four-arm crossing. **Pending:** default Source Sans 400/16 `x` loses the isolated row but retains unequal
terminal footprints; `X` changes crossing/terminal ink and widens its extent. The
[comparison](https://solitaire.taile005dc.ts.net:8912/) does not establish optical acceptance by itself.

### Terminal reference heights

The [terminal model](../../hobby-fitting.md#terminal-reference-height-constraints) holds recognized source-horizontal
caps at automatic/native heights inside the width solve, retaining X at source-vertical attachments. Unsupported or
already correct geometry retains the preceding result.

**Confirmed placement correction:** default Source Sans 400/16, both hint modes, removes two below-baseline `A` pixels
and `y`'s extra upper-left row, retaining recognized feet at Y=0 and caps at Y=8. This is a constrained solve, not
bitmap repair. Default `x X` stay unchanged. `K` loses one upper-tip pixel while retaining top ink height; neighboring
weight and attachment assessment remains pending.

**Pending:** `*` redistributes arm ink with a new diagonal tip/center contact; the grave accent widens into a horizontal
step. Source Sans 400/14 `A y` geometry changes leave bitmaps unchanged, with unequal `A` foot stepping still an
existing concern. At 20 px `A` changes while `y` does not. Roboto 400/16 hints on stays unchanged; hints-off
terminal/diagonal changes and broader weights/sizes remain unassessed.

**Adoption approval, 2026-10-21:** the [terminal comparison](https://solitaire.taile005dc.ts.net:8913/) was approved for
the reviewed sequence, superseding prototype-only status without resolving unrelated curve/aperture findings. The
[adoption record](../../hobby-fitting.md#approved-fitting-sequence-adoption) owns implementation/verification.

### Native adoption verification

Adoption reproduced the approved 72-cell, 6,840-case Roboto/Source Sans 3 comparison over weights 300/400/700, sizes
12/14/16/18/20/24 and both hint modes. **Accepted delivery deviations:** Roboto 300/14 `x` and Source Sans 3 300/18 `x`,
both modes, differ only at 26.6 outline rounding with identical pixels/frames. Roboto 300/18 hints-off `~` retains the
preceding outline after bounded initialization fails, also matching reviewed delivery; that numerical fallback remains a
geometry follow-up, not a glyph exception. Evidence: `out/diagnostics/approved-fitting-native/`.

Native/WASM/export parity supports delivery, not closure of pending optical findings. A historical concurrent-run host
measurement of the adopted 16 px weight-400 pangram was about 3.6–4.4 s for Roboto and 6.5–6.8 s for Source Sans 3,
versus 26–69 ms without fitting. This is a recorded performance limitation, not a current-build benchmark. Measurements
remain in `wasm-runtime-final.json` under the same evidence directory; current identities/default selection belong to
the [revision index](README.md).
