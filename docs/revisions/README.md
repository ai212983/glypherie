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

The current diagonal-weight problem remains open as 001.01. Its source-relative width correction is a tweak within
001.01. See the [iteration record](001/01-diagonal-weight.md) for findings, remaining actions, and current status.

## Index

- [001](001/README.md): optional Skrifa fitting experiments; independent upstream reference retained.
