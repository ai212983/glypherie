# Font fitting and evaluation

Read [.agents/memory/constraints.md](.agents/memory/constraints.md) before font-fitting work and
[docs/evaluation.md](docs/evaluation.md) before judging a candidate or designing evaluation tests.

Prefer generality, robustness and the logic of a sourced geometric model. A few added or removed pixels do not, by
themselves, mean improvement or regression. Do not tune thresholds, phase choices, point exceptions or glyph-specific
rules to chase isolated pixel gains/losses.

State the feature, source foundation and geometric invariant first. Label project hypotheses explicitly. Check source
thickness/contrast, anchors, tangents, ownership and transformed synthetic geometry. Separate hard contracts from
quality signals; detector counts, ink area, coverage and topology are diagnostics, not an optical acceptance score.
Use exact pixel identity only when the contract calls for an unchanged rendering path or independent-reference parity.

Distinguish confirmed regressions from unassessed deviations. A confirmed regression violates an explicit contract or
has demonstrated damage to a source design relationship. Pixel/component-count changes alone are review signals.
Record suspicious cases as pending assessment; allow deviations when geometry and visual evidence support them, with
the rationale and scope recorded. Conservative regression guards are not proof of optical damage; do not silently
relax them or introduce production exceptions to obtain passing tests.

User-accepted cases may change as the general model evolves; some rendering volatility is acceptable. Acceptance
records a reviewed state, not a pixel or outline freeze. Do not constrain the model or add identity tests merely to
preserve accepted glyphs. Assess later changes against geometric intent and explicit contracts; reopen attention only
for a meaningful concern, with the changed feature and inspection question recorded, rather than every difference.

Classify findings as part of every batch's agent work, before publishing or asking for visual assessment. Inspect the
actual source-feature changes against the selected baseline: thinning, thickening, mixed changes, shape/placement changes
or unchanged output with a reported concern. Record evidence and choose the specific inspection question yourself;
tooling must not infer classification from pixel totals, width thresholds or automatic scores. Thinning calls for
continuity/shape assessment; thickening calls for optical-weight assessment; mixed changes need both and contrast checks.

Record unresolved symbol findings in `tools/generator/attention.json` before publishing a preview. Each mark must identify
the exact family, symbol, size, axes and output profile, distinguish pending assessment from a confirmed regression, and
name the inspection type. Group symbols by that type in the UI, with only an optional short per-symbol hint (for example,
"Lower tail"). Do not display status badges, axes, diagnostic labels or explanatory subtitles on review cards. Marks must
match the agreed published family/size/axes/profile scope and symbol coverage. Keep broader findings in iteration notes
and isolated diagnostics; never bypass the preview guard through an
Attention card. Mark relevant unchanged output too; do not mark every pixel difference as a defect.
The web index moves marked cases into the Attention card of their own family/size section. Keep marks pending until their disposition is supported and
recorded; an accepted deviation needs a rationale. Review annotations must never affect font fitting.

Use the current Rust evaluator and tests with the web preview. Passing mechanical checks does not establish optical
acceptance or close an iteration. Preserve the agreed preview matrix. Compare the working candidate with the approved baseline; with no newer candidate,
compare the approved baseline with reference. Renderer roles stay reference/baseline/candidate across all versions; never
add revision/iteration-specific production feature guards. Production must use the separate approved baseline snapshot.
