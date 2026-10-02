# Evaluation principles for font fitting

## Model and sources

Prefer a general, robust model with a clear geometric explanation. Begin with the feature being fitted, the source that
supports the approach and the design relationship it should preserve. Explain why the approach applies beyond the
reported glyph. Label project hypotheses explicitly and distinguish them from claims supported by the sources.

[Hersch 1993, sections 5–6](references/papers/1993-hersch/paper.md) explains how shape, placement on the pixel grid,
width relationships and continuity affect rendering. [Shamir 2003, section 3](references/papers/2003-shamir/paper.md)
grounds feature classification and preservation of geometric intent. Use these foundations to explain the model and
interpret its effects.

## Interpreting evidence

Judge changes against the source design. Do not optimize individual glyphs or rows for a tiny increase or decrease in
pixel count. Added ink can restore a stroke or damage a counter; removed ink can preserve contrast or disconnect a join.
Neither direction alone proves improvement or regression. Consider stroke weight, thick/thin contrast, joins, counters,
terminals and serifs together.

Mechanical checks establish comparable inputs and intact outputs. Preserving geometric relationships and optical quality
requires further judgment. Treat measurements as evidence to interpret:

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
and cases where fitting should safely leave the source unchanged, especially joins, crossings and conflicting point
ownership. Use exact pixels for an explicit identity contract, such as independent-reference parity or an untouched
rendering path.

Previously accepted glyphs may change during later model work. The user explicitly permits some rendering volatility:
acceptance describes the reviewed state rather than freezing its pixels or outline. Favor improvements to the general
model over preserving those snapshots, and do not add glyph exceptions or identity requirements to keep them fixed.
Assess subsequent changes for meaningful effects on source relationships and optical quality. Ordinary variation does
not automatically invalidate acceptance or require another review; a demonstrated defect or substantive unresolved
concern does. Record that concern and its inspection question in Attention. Explicit contracts, including disabled
reference parity, untouched profiles and layout invariants, still apply.

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

Use the current web preview for optical review alongside the Rust evaluator and tests. Explain the model's behavior and
tradeoffs before interpreting pixel changes. Preserve the agreed preview matrix; compare the working candidate with the
approved baseline, or the approved baseline with reference when there is no newer candidate. Renderer roles are
independent of revision/iteration identities. State uncertainty and limitations. Passing mechanical checks alone does
not establish optical acceptance. Iteration acceptance and closure require agreement with the user on the problem's
outcome and any remaining work.

## Attention card

Classification is part of the agent's work on every batch, not a deterministic rendering or evaluation algorithm. Before
updating marks, identify what actually changed in the relevant source feature against the selected baseline and record
the evidence in the iteration notes. Choose the inspection question from that assessment:

- Thinning: inspect continuity and retained shape, especially joins and terminals.
- Thickening: inspect optical weight and balance against neighboring strokes.
- Mixed thinning/thickening: inspect both affected roles and retained contrast; a single net ink change hides this case.
- Shape or placement changes: inspect the affected curve, alignment or attachment.
- Unchanged output: distinguish an existing reported concern from a change introduced by this batch.

These are judgment categories, not automatic sign tests or an exhaustive fixed taxonomy. Local taper/placement changes
and rounding can differ from the main stroke intervention. Explain those distinctions rather than deriving a verdict or
review group from a scalar measurement. Tooling only validates and displays the agent's supplied inspection text; it
must not assign semantic classifications. Reassess marks when subsequent fitting changes invalidate their descriptions.

Check the final published output for the marked profile as well as the outline. When geometric or coverage changes
produce an identical final bitmap, describe the visible concern as unchanged output; record the geometric intervention
separately in the iteration notes. Do not imply visible thinning or thickening from subpixel outline movement alone.

Record symbols needing assessment in [attention.json](../tools/generator/attention.json). The comparison configuration
links this file through its optional `attention` path. The file uses schema `symbol-attention-v1`, the current iteration
`version`, a relative `specimens` configuration path, and a `symbols` array. Each entry supplies:

- A stable `id`, `family_id`, one-character `character`, `size_px`, all resolved `axes`, and `profile`.
- `status`: `pending` for unassessed observations, `confirmed` for demonstrated regressions, or `accepted` for an
  assessed allowable deviation.
- A required concise `inspection` naming what to assess, such as "Thinning: check continuity". The UI groups symbols by
  this type. An optional short `description` identifies a specific part, such as "Lower tail" for Q. For a confirmed
  defect, record supporting evidence in the iteration notes.
- For `accepted`, a required `disposition` recording the assessment and rationale. Accepted marks leave the Attention
  card; their record stays in the configuration as historical evidence, not a rendering freeze. Reopen a mark when
  subsequent agent assessment identifies a meaningful concern. Do not remove pending marks just because tests pass.

Each marked family/size section of the index shows its own Attention card, grouping that section's symbols by inspection
type. Each tile shows only the symbol and an optional short hint; hide axes and status metadata, diagnostic labels and
introductory subtitles. Each symbol opens aligned reference/current/difference images with the same inspection type and
hint. Marked cases move out of the ordinary changed-symbol block for that exact profile/size/axis combination. They
remain visible when pixels are unchanged. Sections without marks show no card. Rendering differences without a specific
concern remain in the ordinary block; neither membership is an optical score.

Attention obeys the same published preview scope as regular specimens, including family, size, axes, profile and symbol
coverage. Reuse the canonical images; do not generate additional diagnostic renders for the card. The exporter rejects
out-of-scope marks before updating the comparison pointer, and the web independently checks every active comparison
surface against the selected specimen matrix. Broader findings stay in iteration notes and isolated diagnostics until a
preview-scope change is explicitly agreed. Keep annotations tied to the current iteration and rebuild with `just
preview-build`. Annotation IDs and scope affect presentation only, never fitting.

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
