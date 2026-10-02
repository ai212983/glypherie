# Reference papers

Each folder contains the original PDF, agent-readable Markdown, figure images, extraction provenance, and copyright or
license information. The [research corpus](CORPUS.md) groups research sources and supporting references by topic. Read
`paper.md` for searchable text and consult `paper.pdf` when exact notation or visual evidence matters. Each folder's
README records retrieval and extraction dates.

| Folder                                                    | Paper                                                                                |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| [1993-hersch](1993-hersch/)                               | Roger D. Hersch, _Font Rasterization: the State of the Art_                          |
| [2003-shamir](2003-shamir/)                               | Ariel Shamir, _Constraint-Based Approach for Automatic Hinting of Digital Typefaces_ |
| [2003-turner-lemberg](2003-turner-lemberg/)               | David Turner & Werner Lemberg, _Real-Time Grid Fitting of Typographic Outlines_      |
| [2006-gallager-quantization](2006-gallager-quantization/) | Robert Gallager, _Quantization_ (course text, Chapter 3)                             |

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
   `extraction.json`. The [extraction tool](../../../tools/paper_extract/) documents the local workflow; add a catalog
   entry for a new paper when using it.
6. Check formulas, mathematical symbols, tables, code, reading order, and figure coverage against the original. Repair
   extraction errors and record corrections. Mark remaining uncertainties explicitly; distinguish transcription notes
   from the paper's own claims.
7. Add a link to the paper's **folder** in this index and use folder links in repository documentation. Cite sections,
   printed pages, equations, or figures when relying on the paper for an implementation decision.

## Accuracy and review

Check the PDF for exact notation and figures. Consult the paper's README and `extraction.json` for recorded checks,
corrections, and uncertainties.

Identify figures by their captions and printed numbers, rather than extraction filenames.

See the [extraction tool](../../../tools/paper_extract/) for regeneration instructions.
