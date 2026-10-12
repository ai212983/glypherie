# Working in this repository

Read the documents relevant to the task before making changes. Follow their linked contracts when the work crosses
component boundaries.

Before tackling a problem, follow the [research workflow](docs/evaluation.md#research-before-implementation).

- Use sourced, general geometric models; do not tune individual glyphs for pixel gains.
- Classify findings before requesting review or publishing; tests do not establish optical acceptance.
- Preserve the agreed preview scope and separate approved baseline.
- Keep rules and current state in their owner documents; link rather than duplicate.

Read first, according to the task:

- Fitting, spacing, raster changes or evaluation tests: [evaluation rules](docs/evaluation.md).
- Renderer routing, settings or native layout: [generator API](tools/generator/README.md).
- Preview generation, comparison or publication: [generator contract](tools/generator/CONTRACT.md) and
  [review rules](docs/evaluation.md#review-and-decision).
- Web presentation or interaction: [web contract](tools/web/CONTRACT.md); setup and commands in the
  [web README](tools/web/README.md).
- WASM interface or build: [WASM README](tools/wasm/README.md).
- Iteration scope, decisions or closure: [revision guide](docs/revisions/README.md) and the relevant revision index.
- Formatting and checks: [task recipes](justfile) and [hook configuration](lefthook.yml).
- Commit messages: [commit rules](commitlint.config.cjs) and [allowed scopes](commit-scopes.json).

For model work, use the [revision guide](docs/revisions/README.md) to locate the relevant revision index and affected
iteration document before changing behavior. Revision indexes own approved/candidate identities; configuration and
policy files own the published preview selections.
