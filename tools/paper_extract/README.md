# Paper extraction

Convert reference PDFs into Markdown with LaTeX math, figure images, page references, and extraction provenance.

If an agent finds an extractor bug, it must flag the bug to the user and ask for a fix. Pause extraction until the user
confirms how to proceed.

## Setup

With `uv` installed, create an isolated Python 3.12 environment:

```sh
uv venv --python 3.12 ~/.cache/paper-extract/venv
uv pip sync --python ~/.cache/paper-extract/venv/bin/python \
  tools/paper_extract/requirements.lock \
  --extra-index-url https://download.pytorch.org/whl/cpu
```

## Usage

From the repository root:

```sh
~/.cache/paper-extract/venv/bin/python tools/paper_extract/extract.py
```

Pass catalog keys to select papers; omit them to extract all registered papers. Use `--reuse` to regenerate from cached
documents or `--enrich` to enable neural formula and code recognition. Review patches must match the conversion mode.

To add a paper, register its folder, source URL, and first printed page in `CATALOG` in `extract.py`, then place the
original at `docs/references/papers/<folder>/paper.pdf`. The tool writes `paper.md`, `figures/`, and `extraction.json`
beside it. Record verified transcription corrections in `review.json`.

Follow the [paper collection rules](../../docs/references/papers/README.md#paper-rules) for acquisition, licensing, and
review.
