# Contextual spacing and texture healing

<!-- cspell:words FontForge AutoWidth AutoKern rint Monaspace Hu -->

**Status: proposed.** The next step is a source-relative optical-spacing experiment. Generalized healing follows a
separate research gate. The [spacing guide](../../guides/text-layout/spacing-models.md) describes current behavior;
[revision 001.03](../../revisions/001/03-spacing-kerning.md#pair-spacing-and-kerning) records assessment and adoption.

## Purpose and scope

Improve reading rhythm and the distribution of ink and whitespace while preserving the typeface's identity. The system
should support fonts whose source files supply ordinary glyphs without contextual healing alternates.

Two capabilities share geometric analysis:

- **Optical spacing** preserves a source pair's estimated separation after fitting and rendering change its shapes.
- **Texture healing** redistributes ink or available room to improve a cramped or airy source combination. It can move
  ink within a glyph's advance or propose a geometric variant.

These capabilities have different targets. Source-relative spacing preserves the source relationship, including when
source and produced shapes are identical. Healing needs a separately justified redistribution target. Its research gate
will select the relationships it preserves and the compromises it may change.

Visual weight belongs to glyph production: the policy that selects the font instance, fits shapes and rasterizes them.
Healing variants use that same policy and retain the selected weight, contrast and character identity. The generated
result consists of glyph forms, placements and context rules. Future export formats follow this model.

## Sources and candidate methods

| Source                                                                                                                                                                                      | Contribution                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [FreeType metrics](https://freetype.org/freetype2/docs/glyphs/glyphs-3.html) and [kerning](https://freetype.org/freetype2/docs/glyphs/glyphs-4.html)                                        | Distinguish images, bearings, advances and pair positioning; explain interactions between neighboring adjustments.                                                                        |
| [FontForge's estimator](https://fontforge.org/docs/ui/dialogs/autowidth.html)                                                                                                               | Estimate optical separation from facing outline edges. Preserving each source pair's own estimate is our adaptation.                                                                      |
| [Hersch et al., 1995](https://lspwww.epfl.ch/publications/typography/ptgogf_95.pdf), pp. 85–88, and [Hu, 1998](https://lspwww.epfl.ch/publications/typography/sopfbsc.pdf), §4.4, pp. 88–91 | Estimate perceived space using transformed outlines or filtered image boundaries, including open cavities such as `c`. These are alternatives if the first estimator proves insufficient. |
| [Monaspace](https://monaspace.githubnext.com/#texture-healing) and its [technical guide](https://github.com/githubnext/monaspace/blob/main/docs/Texture%20Healing.md)                       | Demonstrate contextual redistribution with designed alternate glyphs while preserving the monospace grid. Automatic synthesis for ordinary fonts remains our research question.           |
| [Hersch §§5–6](../../references/papers/1993-hersch/paper.md), [Shamir §3](../../references/papers/2003-shamir/paper.md) and [Hobby](../../references/papers/1993-hobby/paper.md)            | Ground geometric relationships, feature intent and constrained fitting.                                                                                                                   |

The source-relative target and any automatic healing adaptation are project hypotheses. Their suitability for small
bitmap text requires the experiments below. Optical assessment follows the [evaluation rules](../../evaluation.md).

## Text units and controls

Initial experiments use the current
[supported scalar repertoire](../../../crates/generator/API.md#supported-input-and-output): lookup resolves each
supported character to one source glyph at the selected axes. Each generated variant retains that character and source
glyph identity, plus its own variant identity. This lineage supplies its source metrics and target. A richer shaping
adapter would define its spacing units and source mapping before extending this scope.

For these experiments, a text span is a run of supported characters separated by ordinary spaces (`U+0020`) or explicit
line breaks. Punctuation stays inside its span. The proposed controls are:

| Control                          | Meaning                                                                              |
| -------------------------------- | ------------------------------------------------------------------------------------ |
| Source kerning strength, `k`     | Scale the source pair adjustment from disabled (`0`) to full strength (`1`).         |
| Optical correction strength, `o` | Blend current metric placement (`0`) toward source-relative optical placement (`1`). |
| Texture healing                  | Enable a defined set of contextual ink or shape adaptations.                         |
| Letter spacing                   | Add separation between adjacent glyphs inside a span.                                |
| Word spacing                     | Add separation to each ordinary space advance, including repeated spaces.            |

Letter spacing applies at internal span gaps; span ends retain their ordinary terminal advance. Explicit line breaks
reset context. Richer word segmentation, other separators, control ranges and migration from today's uniform tracking
are integration decisions. Existing saved tracking keeps the policy described in the spacing guide until that migration
is agreed.

## Placement and ownership

The spacing module resolves automatic pair placement. The placement stage owns the deliberate user offsets:

```text
automatic_adjustment = signed_pixel_round(blend(metric_adjustment(k), optical_adjustment(k), o))
resolved_step = finalized_advance_left + automatic_adjustment + user_offset
```

The metric alternative follows the existing source-kerning and bearing-compensation policy, including its quantization.
The final blend rounds the signed adjustment. Deliberate offsets are resolved to the chosen output grid once by the
placement stage. With optical correction and healing disabled and deliberate offsets zero, the result reproduces the
current metric policy at the existing source-kerning endpoints. Continuous strengths can produce plateaus in whole-pixel
output.

For a span gap, `user_offset` is letter spacing. A space receives the word-spacing addition in its advance. The
placement stage applies each offset once. Healing reads the resulting available room and evaluates candidates against
the requested relationship, including that offset.

Drawing, measurement and wrapping consume the same resolved forms and positions. Fixed-grid experiments preserve
required cell advances; source-tabular digit pairs preserve their common advance relationships. Initial fixed-grid
controls use neutral deliberate spacing; combined spacing controls are an integration decision.

## Glyph production and contextual healing

The experimental lifecycle has a finite candidate set:

1. **Produce originals.** Glyph production returns the original forms, metrics and actual output geometry. Analysis
   records their source relationships, facing edges, counters and relevant stroke relationships.
2. **Propose candidates.** Healing derives candidates from those originals and a declared context. Every proposal names
   its source glyph, coordinate system and application stage. Shape changes enter glyph production before fitting;
   ink-position changes use the output-grid policy. The candidate set is fixed before selection.
3. **Produce and measure candidates.** Glyph production applies the same appearance policy to every candidate. Analysis
   measures the forms actually delivered, including their resulting metrics and boundaries.
4. **Resolve the context.** The resolver selects compatible candidates and automatic placements using these
   measurements. It checks dependent changes as a group. An invalid group falls back to its original forms and metric
   placement, with the reason recorded. Original forms remain candidates throughout selection.
5. **Finalize placement.** The placement stage adds the deliberate offsets and returns the resolved result. Caches
   retain the selected variant identities and the measurements used to place them.

In `lmi`, for example, the middle `m` may receive room from both sides. Resolution must choose one compatible form for
that occurrence and account for the space assigned to each neighbor.

The [healing research gate](#healing-research-gate) defines the experimental policy. During resolution, identical inputs
within the declared context select the same forms. Pair-only optical placement depends only on the two glyphs in the
pair.

Initial healing specimens use explicit line breaks and unwrapped spans. Placement-only experiments exercise wrapping.
Combining healing with wrapping requires a finite line-boundary policy that resolves the effect of a break on selected
forms and line width before integration.

## Source-relative optical-spacing experiment

**Hypothesis:** preserving each source pair's estimated optical separation through glyph production can retain reading
rhythm better than metric compensation alone. This experiment retains glyph images, bitmap offsets and finalized
advances.

The reference is the
[pinned FontForge implementation](https://github.com/fontforge/fontforge/blob/c41bdb922285f35defd1e1385adfd13bde1ab32a/fontforge/autowidth2.c).
It weights facing outline-edge separations by `1 / (separation + em_size / 50)^2`, excluding empty shared bands. Its
AutoWidth default uses em/100 bands; native pair paths use em/200. Native envelopes are floored in font design units,
the upper loop band is excluded, and the result uses C `rint`. The parity experiment records the chosen parameters,
coordinate conversions and reference license. Pixel-space flooring would define a different adaptation.

Let `S` be the estimated separation with adjacent bounding boxes and `d` the origin step. Source and produced quantities
use a common baseline and measurement unit:

```text
D(d) = d + xmin_right - xmax_left + S
d_source(k) = source_advance_left + k * source_pair_adjustment
D_produced(d_required) = D_source(d_source(k))
optical_adjustment(k) = d_required - finalized_advance_left
```

Calculate the estimator weights once at adjacent boxes. The result supplies `optical_adjustment(k)` in the
[placement formula](#placement-and-ownership).

The first optical experiment retains metric placement for fixed-pitch fonts, source-tabular digit pairs, empty glyphs
and unusable measurement bands, recording each reason. Non-finite geometry produces an explicit error. Signed source
overlaps retain their meaning. Estimator parameters and geometric rules come from the selected sources and invariants;
reported pairs serve as inspection cases rather than production exceptions.

## Healing research gate

Before implementing a transformation, define its redistribution target, allowed movement and geometric ownership, its
sourced foundation, and the relationships it preserves. The model declaration also specifies its finite neighbor states,
selection rule and reasons for keeping the original form. Establish what contextual ink translation achieves first, then
investigate geometric redistribution where it offers an additional benefit. Stroke contrast, counters, joins, selected
weight and required advances need separate evidence; a smaller whitespace measurement alone establishes a spacing
change.

Verify selected transformations on controlled geometry before a font sweep. Compare placement-only and shape-changing
results separately, then assess their combined behavior.

## Preview, full generation and resources

Preview and full generation use the same solver and settings. Preview requests the forms, ordered pairs and context
states needed by its text. Full generation requests every ordered pair in the selected repertoire, including repeated
glyphs, and all reachable states in the declared context model. For `N` source glyphs, the initial pair domain has `N²`
entries before sparse omission. The context gate must establish coverage of the additional variant states.

Cache identities include font bytes, axes, size, production policy and the solver inputs that affect a stored result.
Geometric analysis can be reused across control changes when its inputs stay identical. The result must be independent
of request order and cache history for completed calculations. Generation retains identities, resolved settings,
variants, targets, placements, context rules and abstentions so a result can be reproduced.

A resource gate measures cold and warm preview latency, peak memory, candidate-production cost, pair-domain growth and
context-state growth on the agreed browser and native targets. These measurements set preview response budgets, work
limits, cancellation behavior and the supported scope before expansion. Repeat the gate when healing adds variants.

Each result identifies completion, cancellation, an exceeded work limit or unsupported input. A complete generation has
covered its declared domain; an interrupted attempt retains its incomplete status. Preview can retain the preceding
completed view while a replacement is pending, with its status visible. Solver-level limits are shared configuration in
both paths, so identical inputs retain identical results. Sparse output represents zero corrections or explicit
abstentions, while the generation record accounts for the entire domain.

## Delivery and assessment

| Stage                | Deliverable and decision boundary                                                                                                                                            |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reference parity     | Match the pinned estimator on rectangles, curves, open envelopes, empty bands and disconnected marks; verify translation, scale and unchanged-source identity.               |
| Placement comparison | Compare current and optical placement with unchanged forms and neutral user offsets, using the existing source-kerning endpoints.                                            |
| Control composition  | Add gradual kerning, optical strength and deliberate spacing; verify each offset's single application and the disabled endpoints.                                            |
| Resource gate        | Set measured latency, memory and work budgets before expanding the matrix; repeat for shape-changing candidates.                                                             |
| Healing and context  | Select a sourced transformation and redistribution target; validate the candidate lifecycle, two-sided requests and finite coverage.                                         |
| Integration          | Resolve tracking migration, richer text units where needed and healing-aware line breaks; share the accepted result across native preview, WASM, layout and full generation. |

The first isolated optical matrix retains Roboto, Roboto Flex, Source Sans 3 and Literata at 12/14/16/18/20/24 px,
weights 300/400/700, default remaining axes and independent optical-size endpoints. Include fixed/tabular controls,
punctuation, supported accented scalars, repeated letters, words, straight/curved/diagonal pairs and alternate prefixes.
Keep automatic, selective, overlay and supported Gray pipelines distinct. The healing gate defines its broader corpus.

Mechanical verification covers source parity, determinism, geometry, movement ownership, required advances, control
composition, cache independence and preview/full-generation agreement. Optical assessment inspects identity, contrast,
rhythm, punctuation and word boundaries at native and enlarged sizes in the browser. The separate approved baseline and
published preview selections retain their existing scope. Findings and adoption decisions belong to the revision record.
