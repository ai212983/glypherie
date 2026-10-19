# Experiments

Follow the [root agent instructions](../AGENTS.md) and the [evaluation rules](../docs/evaluation.md); this file adds
only experiment placement rules and does not restate evaluation policy.

Each experiment needs an owning design or iteration document that states its question, source-backed approach, inputs,
controls and decision boundary before implementation. Keep dependencies and reference revisions isolated and pinned.
Distinguish source behavior, reference behavior and project adaptations. Retain identities, configuration, coordinate
conventions, provenance and failures so runs stay reproducible.

Write generated artifacts under `out/diagnostics/<experiment>/`, preserving existing output directory names. Keep each
experiment README to setup, commands and configuration only; put findings and design in the owning document. Route
verification controls and the classification or optical assessment of results through the evaluation rules.
