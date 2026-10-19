# Paper extraction

<!-- cspell:words Docling PDFium Tesseract unreviewed -->

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

For PDFs whose native font encoding cannot be decoded reliably, use `--ocr`. This follows Docling's
[full-page OCR example](https://docling-project.github.io/docling/_generated/examples/full_page_ocr/) with the PDFium
backend and Tesseract CLI in English at a configured scale of 4 (288 DPI). Install `tesseract` and its English and
orientation data first. OCR text stays separate from native PDF text recovery. The catalog can select OCR and formula
enrichment per paper; Hobby's Type 3 font report uses both by default:

```sh
~/.cache/paper-extract/venv/bin/python tools/paper_extract/extract.py \
  hobby-1993-automatically-tuned-bitmaps --enrich --reuse
```

Native, enriched, OCR and enriched OCR caches are separate and keyed by the source PDF hash. A review entry's `mode`
must match the conversion (`native`, `enriched`, `ocr-native` or `ocr-enriched`); omitted modes mean `native` for
existing patches. `figure_regions` can replace detected figures with reviewed source crops, anchored before their
captions. Illustration OCR wholly contained within those regions is omitted; `keep_text` retains its text, or
`transcription` supplies a checked replacement alongside the crop. Region bounds use PDF points with a top-left origin.

The catalog's `page_batch_size` enables resumable page batches for slow conversions. With `--reuse`, completed batches
are reused after interruption and concatenated in source page order. Batch size is part of the cache identity; original
page ranges are checked before concatenation.

Outputs are staged and checked before installation. Failed conversion, invalid decoded characters or missing searchable
page text leave the accepted copy intact. These checks do not prove transcription accuracy. The review status reports an
unreviewed machine extraction until corrections have actually been applied; even corrected output requires checking the
PDF for exact mathematics.

To add a paper, register its folder, source URL, and first printed page in `CATALOG` in `extract.py`, then place the
original at `docs/references/papers/<folder>/paper.pdf`. The tool writes `paper.md`, `figures/`, and `extraction.json`
beside it. Record verified transcription corrections in `review.json`.

Follow the [paper collection rules](../../docs/references/papers/README.md#paper-rules) for acquisition, licensing, and
review.

Run extractor regression checks in the same Python environment:

```sh
~/.cache/paper-extract/venv/bin/python -m unittest discover -s tools/paper_extract -p 'test_*.py'
```
