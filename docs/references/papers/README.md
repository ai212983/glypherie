# Reference papers

<!-- cspell:words Germer BRDF Ferwerda Herle docling Tesseract -->

Each folder contains the original PDF, agent-readable Markdown, figure images, extraction provenance, and copyright or
license information. The [research corpus](CORPUS.md) groups research sources and supporting references by topic. Read
`paper.md` for searchable text and consult `paper.pdf` when exact notation or visual evidence matters. Each folder's
README records retrieval and extraction dates.

| Folder                                                    | Paper                                                                                                                  |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| [1993-hersch](1993-hersch/)                               | Roger D. Hersch, _Font Rasterization: the State of the Art_                                                            |
| [1993-hobby](1993-hobby/)                                 | John D. Hobby, _Generating Automatically Tuned Bitmaps from Outlines_ (report version)                                 |
| [1998-kelley](1998-kelley/)                               | Edward F. Kelley, George R. Jones & Thomas A. Germer, _Display reflectance model based on the BRDF_                    |
| [2003-shamir](2003-shamir/)                               | Ariel Shamir, _Constraint-Based Approach for Automatic Hinting of Digital Typefaces_                                   |
| [2003-turner-lemberg](2003-turner-lemberg/)               | David Turner & Werner Lemberg, _Real-Time Grid Fitting of Typographic Outlines_                                        |
| [2006-gallager-quantization](2006-gallager-quantization/) | Robert Gallager, _Quantization_ (course text, Chapter 3)                                                               |
| [2012-darling-ferwerda](2012-darling-ferwerda/)           | Benjamin A. Darling & James A. Ferwerda, _Seeing Virtual Objects: Simulating Reflective Surfaces on Emissive Displays_ |
| [2024-herle](2024-herle/)                                 | Dorian Herle et al., _Emulating paper: a review of reflective display technologies_                                    |

## Paper rules

When a paper is needed for research or implementation:

1. Look for it in this directory first and read the local extraction and original figures as needed.
2. If it is absent, search online for the original paper. Prefer the publisher, an author or university site, or an
   established public archive. Download the original PDF and keep its bytes unchanged.
3. Create a folder named `YYYY-author`, or `YYYY-author-author` for the existing two-author convention. Add a short
   topic suffix if needed to distinguish papers with the same year and author. Store the original as `paper.pdf`.
4. Add a folder `README.md` with the full citation, source URL, retrieval date, and SHA-256 hash. Add `LICENSE.txt` with
   the applicable license or copyright notice and its source. If no explicit license is supplied, record that fact;
   availability for download does not establish an open license. Do not apply the repository's code license to a paper.
5. Convert the complete paper to `paper.md`: retain section and equation numbering, use LaTeX math, preserve tables and
   code, link figure crops in `figures/`, and retain PDF and printed-page references. Save extraction provenance in
   `extraction.json`. Regenerate via [Extraction](#extraction); add the new paper to [catalog.json](catalog.json) and
   its corrections to [review.json](review.json) when using it.
6. Check formulas, mathematical symbols, tables, code, reading order, and figure coverage against the original. Repair
   extraction errors and record corrections. Mark remaining uncertainties explicitly; distinguish transcription notes
   from the paper's own claims.
7. Add a link to the paper's **folder** in this index and use folder links in repository documentation. Cite sections,
   printed pages, equations, or figures when relying on the paper for an implementation decision.

## Accuracy and review

Check the PDF for exact notation and figures. Consult the paper's README and `extraction.json` for recorded checks,
corrections, and uncertainties.

Identify figures by their captions and printed numbers, rather than extraction filenames.

## Extraction

Regenerate `paper.md`, `figures/` and `extraction.json` with the external `paper-extract` engine, run from the
repository root with `PAPER_EXTRACT_ROOT` set to a `paper-extract` checkout (environment setup is in that checkout's
README). Corpus-specific text normalization lives in [extraction_adapter.py](extraction_adapter.py).

```sh
"$PAPER_EXTRACT_ROOT/.venv/bin/python" "$PAPER_EXTRACT_ROOT/extract.py" \
  --papers-dir docs/references/papers \
  --catalog docs/references/papers/catalog.json \
  --patches docs/references/papers/review.json \
  --adapter docs/references/papers/extraction_adapter.py \
  --review-guidance ../README.md#accuracy-and-review \
  --cache ~/.cache/font-generator-docling/documents
```

Pass catalog keys to select papers; omit them to extract all catalog entries. `--reuse` regenerates from cached
documents, `--enrich` enables neural formula and code recognition, `--ocr` uses full-page Tesseract OCR; the catalog
selects OCR and enrichment per paper, and review patches must match the conversion mode. The `--cache` value reuses the
existing conversion checkpoints.

If an agent finds an extractor bug, it must flag the bug to the user and ask for a fix. Pause extraction until the user
confirms how to proceed.
