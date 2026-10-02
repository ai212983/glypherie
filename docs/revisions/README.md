# Development revisions

Revisions group development work across issues.

## Iteration lifecycle

Each iteration is dedicated to fixing one specific problem identified by user feedback. Continue implementation changes,
experiments, tweaks, diagnostics, and validation for that problem under the same iteration identity.

An iteration closes only when user and agent agree there are no further actions for that problem. Record the agreed
outcome: resolved/closed, not fixable, or remaining work assigned to a specific follow-up. The user must explicitly
agree to closure; an agent must not infer it from passing tests, published comparisons, or a new implementation
approach. If there is still action to take on the current problem, keep the iteration open. Advance iteration numbering
only after that agreement and identify the next problem from user feedback.

The diagonal-weight problem in 001.01 is closed and accepted for production on 2026-10-02, following explicit user
acceptance of the current quality. See the
[iteration record](001/01-diagonal-weight.md#acceptance-and-production-promotion-2026-10-02) for the accepted scope and
retained follow-up observations. [001.02](001/02-light-continuity.md) is accepted and closed on 2026-10-02. Production
uses its approved light-continuity and fractional shared-width model; the remaining binary weight step is an accepted
limitation. The index subtitle shows only the active 001.02 identity.

## Index

- [001](001/README.md): accepted diagonal fitting promoted to production; independent upstream reference retained.
