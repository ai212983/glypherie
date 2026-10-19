# Evaluation principles for font fitting

## Research before implementation

Before tackling a problem or proposing a fix, search the project's papers and reference sources, reference
implementations and the web for existing solutions to that problem or its broader class. Prefer primary papers,
specifications and implementation sources. Check how each approach works, its assumptions and its applicability to the
project's constraints.

Present the best applicable approach to the user before implementation, with sources, the proposed adaptation, the
relationship it preserves and any limitations or departures from the original method. Prefer adapting an established
solution over inventing a new one.

Develop a new approach only as a last resort, after explaining why the researched solutions cannot reasonably be
adapted. Ground it in published principles, source geometry or established mechanisms; identify the novel part as a
project hypothesis and explain how it will be tested. A lack of a ready-made solution does not justify an unsupported
rule.

## Model and sources

Prefer a general, robust model with a clear geometric explanation. Begin with the feature being fitted, the source that
supports the approach and the geometric invariant it should preserve. Explain why the approach applies beyond the
reported glyph. Label project hypotheses explicitly and distinguish them from claims supported by the sources.

Every fitting decision, algorithm and logic change must have an external source foundation. An exception must be
explicitly specified and justified in both the code comment and the test; labelling a project hypothesis does not waive
this requirement. Compare implementation behavior with the cited sources and independently captured reference output.
Per-glyph or per-row rules need a computable, sourced geometric separator rather than isolated exceptions.

[Hersch 1993, sections 5–6](references/papers/1993-hersch/paper.md) explains how shape, placement on the pixel grid,
width relationships and continuity affect rendering. [Shamir 2003, section 3](references/papers/2003-shamir/paper.md)
grounds feature classification and preservation of geometric intent. Use these foundations to explain the model and
interpret its effects.

## Interpreting evidence

Judge changes against the source design. Do not optimize individual glyphs or rows for a tiny increase or decrease in
pixel count. Do not search for thresholds, phase choices, parameters or point exceptions to gain or remove pixels in a
reported glyph. Added ink can restore a stroke or damage a counter; removed ink can preserve contrast or disconnect a
join. Neither direction alone proves improvement or regression. Consider stroke weight, thick/thin contrast, joins,
counters, terminals and serifs together.

Hard contracts include determinism, required independent-reference parity, advances/layout, profile behavior, outline
validity and bounded movement/ownership. Mechanical checks establish comparable inputs and intact outputs. Preserving
geometric relationships and optical quality requires further judgment. Do not combine quality signals into an
unexplained acceptance score. Treat measurements as evidence to interpret:

- Point movement describes changes to corresponding endpoints and controls, not the distance between whole shapes.
  Interpret source-to-upstream, source-to-candidate and upstream-to-candidate changes separately, within each size.
- Connected ink and enclosed white regions need design context. A separate mark may be intentional; a new break may
  damage a join; a tiny counter may reasonably disappear at low resolution. Sensitivity to nearby coverage thresholds
  calls for investigation, while behavior across sizes, grid placements and axes needs broader evidence. Gray coverage
  samples describe hypothetical binary images rather than the delivered gray image.
- Ink area and feature counts describe activity, not quality. More detected or applied pairs can reflect broader
  coverage or mistaken classification. Check widths across source and fitted strokes, thick/thin contrast, fixed points,
  curve directions and which feature may move each point. A thin stroke gaining the weight of a thick stroke can lose
  intentional contrast despite gaining ink.

Favor tests of geometric relationships over a preferred pixel count. Include supported examples, transformed geometry
and cases where fitting should safely leave the source unchanged, especially joins, crossings, anchors, tangents and
conflicting point ownership. Compare source design and the independent reference across the agreed corpus and isolated
broader sweeps. Use exact pixels for an explicit identity contract, such as independent-reference parity or an untouched
rendering path.

Previously accepted glyphs may change during later model work. The user explicitly permits some rendering volatility:
acceptance describes the reviewed state rather than freezing its pixels or outline. Favor improvements to the general
model over preserving those snapshots, and do not add glyph exceptions or identity requirements to keep them fixed.
Assess subsequent changes for meaningful effects on source relationships and optical quality. Ordinary variation does
not automatically invalidate acceptance or require another review; a demonstrated defect or substantive unresolved
concern does. Record that concern and its inspection question in the affected iteration notes. Explicit contracts,
including disabled reference parity, untouched profiles and layout invariants, still apply.

## Review and decision

Classify findings by evidence rather than by difference from reference:

| Status               | Evidence                                                                                                                        | Required action                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Confirmed regression | An explicit contract fails, or geometric/visual evidence demonstrates damaged stroke continuity, contrast, shape or legibility. | Fix the cause, or explicitly agree a limitation/follow-up.                           |
| Pending assessment   | A pixel, topology, width or size-transition difference raises concern, but damage has not been demonstrated.                    | Inspect source and fitted geometry, coverage and the web comparison before deciding. |
| Acceptable deviation | The output differs while preserving the intended relationships, and visual assessment supports the tradeoff.                    | Record the rationale and applicable scope; no compensating fix is required.          |

An increase in connected-component count establishes a change in a binary image. It does not locate the change or prove
that a principal stroke has broken: a small terminal, serif or marginal connection can change the count. A visible gap
damaging a source-connected stroke is stronger evidence than the count alone. Conversely, equal counts can hide damage.
Examine the location, geometric cause and behavior across relevant sizes/axes.

Conservative connectivity tests can pause a change for investigation without serving as an optical verdict. Historical
fixture names such as `known_join_failures` identify captured observations, not independently confirmed defects or
permission to accept them. Do not silently weaken a guard; an accepted deviation needs an explicit, recorded basis and
test expectations appropriate to that basis, without a glyph-specific production exception.

Use the current Rust evaluator and tests alongside the project's browser preview. Present glyphs and visual findings
through the browser app; do not present standalone images or local image links in chat. Only link rebuilt app content
reflecting the current changes. Explain model behavior and tradeoffs before interpreting pixel changes, and state
uncertainty and limitations. Select comparison inputs and preserve publication scope according to the
[generator contract](../tools/generator/CONTRACT.md#generation-selection). Passing mechanical checks alone does not
establish optical acceptance; closure follows the [iteration lifecycle](revisions/README.md#iteration-lifecycle).

## Review questions and findings

Classification is part of the agent's work on every batch, not a deterministic rendering or evaluation algorithm. Before
requesting review, identify what actually changed in the relevant source feature against the selected baseline and
record the evidence in the iteration notes. Choose the inspection question from that assessment:

- Thinning: inspect continuity and retained shape, especially joins and terminals.
- Thickening: inspect optical weight and balance against neighboring strokes.
- Mixed thinning/thickening: inspect both affected roles and retained contrast; a single net ink change hides this case.
- Shape or placement changes: inspect the affected curve, alignment or attachment.
- Unchanged output: distinguish an existing reported concern from a change introduced by this batch.

These are judgment categories, not automatic sign tests or an exhaustive fixed taxonomy. Local taper/placement changes
and rounding can differ from the main stroke intervention. Explain those distinctions rather than deriving a verdict or
review group from a scalar measurement. Rendering and evaluation tools must not assign semantic classifications.
Reassess findings when subsequent fitting changes invalidate their descriptions.

Check the final published output for the reviewed profile as well as the outline. When geometric or coverage changes
produce an identical final bitmap, describe the visible concern as unchanged output; record the geometric intervention
separately in the iteration notes. Do not imply visible thinning or thickening from subpixel outline movement alone.

Record unresolved findings in the affected iteration before requesting visual assessment. Identify family, symbol, size,
axes and output profile, the inspection question, evidence and disposition. Keep unassessed cases pending; accepted
deviations need a rationale and scope. Passing tests alone does not resolve a finding. Findings must not become fitting
exceptions. Broader diagnostic findings stay in iteration notes and isolated output until a publication-scope change is
agreed.

## Usage

Run from the repository root:

```sh
mkdir -p out/diagnostics
cargo run --locked --manifest-path tools/generator/Cargo.toml \
  --bin font_evaluate -- tools/generator/specimens.json out/diagnostics/evaluation.json
```

The command evaluates the configuration's latest selected variant across its existing size/axis/profile matrix,
comparing independent source without hinting, independent upstream hinting and the candidate. It writes JSON; preview
publication is separate and the matrix stays unchanged.

A hard check failure writes JSON and returns a nonzero exit status. Input or capture errors abort the run. Diagnostics
alone leave the exit status successful. Read the report alongside geometric tests and the web preview; a successful run
confirms mechanical checks, not optical acceptance.
