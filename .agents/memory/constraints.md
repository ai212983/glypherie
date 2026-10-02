---
type: project
---

# Working constraint (stated 2026-09-15, twice): reference-first logic

Every decision, algorithm, and logic change in the font hinting work must have a foundation in external references (VTT sources, Shamir 2003, CVT/TrueType spec, Turner-Lemberg, Hersch, scaler witnesses) — i.e. based on something besides our own invention. Exception only when explicitly specified AND explained why, in the code comment and test.

Consequences in force:
- Compare implementation behavior with cited sources and independently captured reference output.
- Diagnostics and validation use the current Rust generator and its tests.
- Per-glyph/per-row carve-outs without a computable sourced separator are overfitting — the foundry's per-glyph line needs role-aware classification work, not choke-point exceptions.

# Working constraint (stated 2026-10-01): visual review through the web

All visual communication goes through the project's web preview. Use web specimen and comparison pages when presenting
glyphs or visual findings; do not present standalone images or local image links in chat.

# Working constraint (stated 2026-10-01): latest web preview and revision baseline

The web index `/` ALWAYS shows the latest iteration of the latest revision. Compare revision and iteration numbers
numerically. The 2026-10-02 renderer-role decision supersedes the earlier previous-revision comparison rule: compare a
working candidate with the approved baseline; with no newer candidate, compare baseline with reference (currently
approved 001.02 versus reference).
Do not create a separate `/reviews/` folder or endpoint. Update guidance, generator selection, comparison export,
and the web together. Only link rebuilt web content that reflects the current changes.

# Working constraint (stated 2026-10-01): preserve preview scope during diagnostics

The normal preview matrix is agreed separately from diagnostic sweeps. Roboto, Literata, and Source Sans 3 use
14/16/18/20 px. Font investigations must not expand or shrink these selections incidentally. The checked-in specimen
configuration keeps its independent preview-policy guard enabled. Change the matrix, policy, or guard expectations
only when the user's task includes that scope change. Run broader diagnostics through Rust requests/tests or temporary
configurations with isolated output; do not publish them into the normal preview output.

# Working constraint (stated 2026-10-01): problem-scoped iteration lifecycle

Each iteration is dedicated to fixing one specific problem identified by user feedback. Fixes, tweaks, experiments,
diagnostics, and validation for that problem stay in the same iteration. An iteration is not over unless the user
explicitly agrees and user and agent agree there are no further actions for that problem: resolved/closed, not fixable,
or remaining work explicitly assigned to an agreed follow-up. Record that decision and follow-up scope before advancing
iteration identity. Passing tests, publishing output, or adopting a new algorithm does not imply closure.
001.01 closed on 2026-10-02 following explicit user acceptance of all current quality and authorization to promote it
to production. Its source-relative width and terminal corrections belong to that accepted iteration.

# Working scope (agreed 2026-10-01): Literata diagonal coverage

Include Literata 14 px Q's lower tail, x, and y in the still-open 001.01 diagonal-weight problem. Identical output to
reference does not exclude an existing diagonal-weight coverage issue. Roboto 16 px t's upright stem is a separate
stem-weight issue. The Literata cases were initially unresolved under this scope agreement; the 2026-10-02 acceptance below supersedes
that pending disposition.

# Working constraint (stated 2026-10-01): model-first evaluation

Pixel gains or losses, especially isolated pixels, do not by themselves establish improvement or regression. Prefer the
generality, robustness, and logic of the sourced model. Do not search for parameters, point exceptions, thresholds, or
phase choices merely to gain/remove pixels in a reported glyph.

- State the geometric feature and source-backed invariant before changing fitting logic. Mark project hypotheses explicitly.
- Separate hard contracts (determinism, independent-reference parity when disabled, advances/layout, profile behavior,
  outline validity, bounded motion/ownership) from quality signals (coverage, ink count, connectivity, counters, threshold
  stability, source-relative thickness/contrast). Never combine these signals into an unexplained acceptance score.
- Test generic geometry, transformed/synthetic cases, ownership conflicts, anchors and tangents; use reported glyphs as
  witnesses. Do not require pixel count to move in a preferred direction or bless an isolated pixel difference as a fix.
- Compare against source design and the independent reference across the agreed corpus and isolated broader sweeps.
  Explain model behavior and tradeoffs before interpreting raster changes. Existing intentional dots/counters/serifs mean
  topology counts need context; new breaks in previously connected alphabetic witnesses remain regression controls.
- Use the Rust evaluator and web preview together. Neither automated measurements nor passing tests establish optical
  acceptance or close an iteration; user agreement is still required.

Detailed evaluation rules: [docs/evaluation.md](../../docs/evaluation.md).

# Working constraint (stated 2026-10-01): regression versus deviation

Distinguish a confirmed regression requiring correction from a rendering deviation that may be allowed after geometric
and visual assessment. Added/removed pixels or connected components alone establish a diagnostic difference, not damage.
Keep unassessed cases pending rather than labelling them confirmed defects or accepted deviations. Record the evidence,
rationale and scope of each disposition. Conservative test guards remain investigation triggers; do not silently weaken
them or add glyph-specific production exceptions. The three historical broader join observations in 001.01 are pending
assessment, not independently confirmed regressions solely from their component counts.

# Working constraint (stated 2026-10-01): symbols requiring attention

Mark unresolved symbol findings in `tools/generator/attention.json`. Every mark records internal status, the inspection
type and an optional short hint identifying the part to inspect, with font/size/axes/profile scope. The web index puts marked cases
in the Attention card of their own font/size section instead of the ordinary changed-symbol block. Marked unchanged
output must remain reviewable.
Attention must obey the same published preview scope as regular specimens; do not publish broader diagnostic sizes or
axes through another card. Broader findings remain in iteration notes and isolated captures. Pending marks need
assessment; accepted deviations need a recorded rationale. Annotations must not become production fitting exceptions.

# Working constraint (stated 2026-10-01): concise assessment UI

Each font/size section gets an Attention card when applicable, grouping its symbols by inspection type. The surrounding
section identifies font and size; each tile shows only the symbol and an optional short hint such as
"Lower tail" for Q. Remove the explanatory subtitle, diagnostic labels, axes information and Attention/status badges
from the assessment UI. Keep scope and disposition metadata in tooling. Apply the published-preview guard to every
rendered surface, including Attention, rather than only regular specimens; diagnostic sizes/axes remain isolated.

# Working constraint (stated 2026-10-01): agent-owned inspection classification

During every batch, the agent must classify the actual changes before marking symbols or requesting assessment. Assess
thinning, thickening, mixed interventions, shape/placement changes and unchanged reported concerns from feature geometry,
source roles and the selected baseline. Thinning/continuity and thickening/optical weight are different review questions.
Mixed changes need both and contrast assessment. Choose concise, specific inspection groups and record the evidence in
iteration notes. Do not encode deterministic semantic classification in rendering/evaluation code or infer it from net
ink counts or width thresholds. Tooling displays the agent's annotations; later changes require agent reassessment.

# Working preference (stated 2026-10-01): accepted cases may evolve

The user permits changes to previously accepted glyphs and accepts some rendering volatility during model work.
Acceptance records the reviewed state; it does not freeze pixels or outlines. Prefer a general, robust model over
preserving accepted snapshots, and do not create glyph exceptions or identity tests merely to keep them unchanged.
Assess later changes for meaningful damage or uncertainty in source relationships and optical quality. Reopen Attention
for such concerns with a specific inspection question, not for every difference. Ordinary variation need not trigger
another user review. This permission does not relax explicit mechanical contracts or close the iteration.

# Latest user assessment (2026-10-01): remaining weight corrections

Within open 001.01, correct excessive thickness in Literata 14 px Q's lower tail and x/y terminals, and Source Sans 3
16 px w/x/y. The user accepted everything else in the reviewed normal preview. This does not dispose of unpublished
diagnostic findings. Accepted cases may evolve under the volatility preference above; reassess meaningful concerns
without treating every difference as a regression or a reason for another review.

# Latest user decision (2026-10-02): accepted and promoted 001.01

The user accepted all current published quality, requested iteration closure and authorized production promotion.
001.01 is resolved/closed; all six remaining published Attention cases are accepted. Production automatic 1-bit fitting
uses this model, with automatic hinting and threshold 128 as job defaults. Keep the independent upstream reference,
explicit interpreter/unhinted semantics, gray fitting and layout contracts. No new iteration has been started.
Broader unpublished topology observations remain for future investigation outside this accepted preview scope; they
are not demonstrated contract failures or blockers to promotion. Preserve their captures and conservative guards.
See the acceptance and production record in docs/revisions/001/01-diagonal-weight.md. Earlier open/pending notes in this
memory are historical and superseded for the published cases. Some rendering volatility remains acceptable.

# Renderer roles (2026-10-02)

Use three stable roles: independent upstream reference, approved baseline with revision/iteration metadata, and working
candidate with revision/iteration metadata. Do not create Cargo feature guards for individual iterations. Production
always uses the separate approved baseline fitter source; only candidate tooling is optional. Keep one baseline source
snapshot and one candidate copy, sharing generator/raster/output code. Promotion replaces the baseline snapshot after
explicit acceptance and updates its version metadata. Baseline and candidate source hashes remain separate. The accepted
001.01 preview renders the baseline against reference; a future candidate compares with that approved baseline.

# Current problem (2026-10-02): Roboto light weight continuity

001.02 implements the Roboto 14 px weights 200/100 continuity correction as a working candidate: outline-driven
monochrome dropout plus extra-light diagonal width transfer using the shared horizontal standard. Foundation:
Hersch §7 and TrueType SCANTYPE, adapted to coverage as an explicit project hypothesis. Preserve independent raw
coverage and threshold 128; gray and disabled paths stay unchanged. Production remains approved 001.01. Candidate
preview compares with that baseline and the interactive tester switches the same axes/text across roles.
Low weights stay outside the weight-400 publication matrix and Attention scope. See docs/revisions/001/02-light-continuity.md
for classification, checks, independent witnesses and pending optical assessment. 001.02 remains open until explicit
user acceptance and an agreed disposition of remaining actions.


# Current experiment (2026-10-02): shared monochrome width transition

Checkpoint d9ba93f preserves the light-continuity candidate. Open 001.02 now reuses the inherited smooth horizontal
stem-width branch for candidate Mono/default scripts and transfers the actual fitted standard to diagonals. This is a
project hypothesis grounded in pinned FreeType stem_width and Shamir shared source widths. At Roboto14 wdth100
459/460 it removes the 1→2 px fitted-width cliff; inherited placement and binary steps remain. Preserve the approved
baseline, source contrast, conservative join guards, gray/disabled identity and preview scope. Candidate regular-weight
geometry may change; review meaningful thinning, thickening and placement questions recorded in the iteration notes
and scoped Attention, without freezing accepted glyph pixels. Optical assessment remains open.


# Latest acceptance (2026-10-02): 001.02

User: "really good result. lets commit it as 001.02". Accepted and closed 001.02 includes light-stroke dropout,
extra-light width coordination and fractional shared horizontal fitting. Promote the accepted source to the separate
baseline snapshot, production version 001.02; candidate tooling remains optional. All 13 pending published Attention
cases are accepted tradeoffs with recorded source-geometry rationale. The disclosed binary upright step near 465 and
inherited placement steps are accepted limitations, not a claim of fully smooth optical weight. No new iteration starts.
Earlier open/pending and approved00101 statements are historical and superseded. Preserve normal preview scope and
independent reference, gray/disabled/layout contracts. The index subtitle shows only the active iteration (001.02),
without comparison names or an arrow, per the user's explicit follow-up. Version roles and symbol routes retain their
reference/baseline/candidate semantics.
