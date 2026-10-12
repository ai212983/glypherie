# Development revisions

Revisions group iterations; each iteration groups related topics for review: corrections, improvements, capabilities or
investigations.

## Folder structure

- `README.md`: this guide.
- `NNN/README.md`: revision starting point, renderer identities and iteration index with brief outcomes or status.
- `NNN/NN-topic.md`: iteration design and decision note; for example, `001/02-light-continuity.md` is iteration 001.02.

## Iteration documents

Write a design and decision note, grouping topics by a shared goal, model or invariant rather than by glyph or work
step:

- **Title and introduction:** motivation and adopted approach.
- **Foundation and invariant:** shared sources and preserved relationships. Follow the
  [evaluation rules](../evaluation.md); label project hypotheses. Put distinct foundations beside their topics.
- **Topics:** one subsection per topic, numbered when useful, explaining the logic change and rationale. Retain rejected
  alternatives only when they explain a decision or constraint.
- **Scope and limits:** applicability, accepted review scope, limitations and unresolved work or assigned follow-up.
  Keep essential assessment evidence beside the relevant topic or limitation.

Describe the resulting behavior, not its implementation, testing or publication history. Replace superseded proposals;
omit file maps, handoffs, command/build logs, verification ledgers and artifact metadata. Keep detailed diagnostics
elsewhere. Avoid repeated status, unchanged-state reminders and document-routing prose; unchanged behavior matters only
as an invariant or scope boundary.

## Documentation ownership

The revision index owns lifecycle status, closure dates and renderer identities; iteration notes own model decisions and
scoped assessment. Evaluation principles belong in the [evaluation guide](../evaluation.md); commands, APIs and
interface contracts belong in tool documentation. Preview selections belong in configuration and policy files. Link to
the owner rather than repeat its content. Vendored baseline/candidate documentation remains independent.

## Iteration lifecycle

Feedback may extend an iteration's agreed topics. Close only with explicit user agreement and a disposition for each:
completed, accepted with limits, declined or deferred to a specific follow-up. Passing tests, publishing a preview or
completing one topic does not close the group. Advance numbering after closure, with the next scope agreed from
feedback.
