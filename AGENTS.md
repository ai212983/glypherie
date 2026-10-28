# Working in this repository

Read the documents relevant to the task before making changes. Follow their linked contracts when the work crosses
component boundaries.

Before tackling a problem, follow the [research workflow](docs/evaluation.md#research-before-implementation).

- Use sourced, general geometric models; do not tune individual glyphs for pixel gains.
- Classify findings before requesting review or publishing; tests do not establish optical acceptance.
- Preserve the agreed preview scope and separate approved baseline.
- Use the shared shadcn Tooltip component for web tooltips instead of native `title` attributes.
- Keep rules and current state in their owner documents; link rather than duplicate.
- Keep contracts and READMEs concise. Apply this test to every contract statement: if changing it would break another
  component or an external consumer of its inputs, outputs, published formats, routes, forwarded requests, or build
  outcomes, it belongs; if only a person viewing the page would notice, it belongs in code and tests, not the contract.
  That excludes presentation, layout, display modes, control behavior, and formats produced and consumed inside one
  component. The root README introduces the project's purpose, motivation and contents alongside development guidance.
  Component READMEs state setup, commands and configuration only. Keep implementation mechanics and change history in
  their owner documents; link rather than restating their rules.

## Code placement

Applications live in `apps/`; shared Rust packages live in `crates/`; GitHub Actions helpers live in `.github/scripts/`
with repository-level checks in `tests/tooling/`; exploratory prototypes, harnesses and adapters live in `experiments/`.
Corpus-specific adapters live beside their corpus. Read [experiment guidance](experiments/AGENTS.md) before adding or
moving experiment code. Extend the owning component rather than creating a parallel helper project. Maintained
components never depend on `experiments/`; experiments may use maintained APIs. Extract shared code only for concrete
consumers. Record adoption of an experiment in the owning design or iteration document, with the verification and
interfaces that adoption requires.

## Task guidance

Read first, according to the task:

- Fitting, spacing, raster changes or evaluation tests: [evaluation rules](docs/evaluation.md).
- Renderer routing, settings or native layout: [generator API](crates/generator/API.md).
- Preview generation, comparison or publication: [generator contract](crates/generator/CONTRACT.md) and
  [review rules](docs/evaluation.md#review-and-decision).
- Web boundaries or publication: [web contract](apps/web/CONTRACT.md); setup and commands in the
  [web README](apps/web/README.md).
- WASM interface or build: [WASM README](crates/wasm/README.md).
- Experiments, prototypes or harnesses: [experiment guidance](experiments/AGENTS.md).
- Iteration scope, decisions or closure: [revision guide](docs/revisions/README.md) and the relevant revision index.
- Formatting and checks: [task recipes](justfile) and [hook configuration](lefthook.yml).
- Commit messages: [commit rules](commitlint.config.ts) and [allowed scopes](commit-scopes.json).

For model work, use the [revision guide](docs/revisions/README.md) to locate the relevant revision index and affected
iteration document before changing behavior. Revision indexes own approved/candidate identities; configuration and
policy files own the published preview selections.
