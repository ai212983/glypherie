# John D. Hobby (1993)

<!-- cspell:words CSTR KaTeX -->

_Generating Automatically Tuned Bitmaps from Outlines_

John D. Hobby. _Journal of the ACM_ 40(1), January 1993, pp. 48–94.
[DOI: 10.1145/138027.138040](https://doi.org/10.1145/138027.138040).

This folder contains the 43-page CSTR 148 report version, not a verified copy of the journal typesetting. The
[Bell Labs report archive index](https://www.vector.comm.sfu.ca/pups/Documentation/TechReports/Bell_Labs/CSTRs/readme.html)
dates CSTR 148 to February 1990. The author's [publication list](https://9p.io/who/hobby/pubs.html) also links a 43-page
version under the journal citation. The [focused fitting audit](audit.md) compares selected mathematical passages
between the two report copies; differences from the final journal publication have not been established. Section and
printed-page references here refer to the stored report.

- [Agent-readable Markdown](paper.md)
- [Original downloaded PDF](paper.pdf)
- [Author-hosted report copy](author-report.pdf), with separate [provenance and mathematical audit](audit.md)
- [Figure images](figures/)
- [Extraction provenance and review notes](extraction.json)
- [Copyright and licensing record](LICENSE.txt)

Source: [archived CSTR 148 PDF](https://telecom.wiki/download/attachments/819301/CSTR%20148.pdf), retrieved 2026-10-15.
The original downloaded bytes are unchanged.

SHA-256: `c97bd9a7bcebfeda5ea3d62bce266372f59fbc3c466239e222cf9b8c2465ff87`.

## Extraction and review

Prepared 2026-10-15 with full-page English OCR and formula recognition. The native attempt failed because the old Type 3
font encoding produced missing prose, repeated fragments and corrupted numbers. The repaired extractor preserves OCR
text, splits paragraphs by source character provenance and caches six-page batches so interruptions can be resumed. See
the [extractor workflow](../../../../tools/paper_extract/README.md) for regeneration.

The transcription covers all 43 PDF pages, all 41 numbered figures have checked source crops, and the 33 numbered
equations retain their printed labels. The four algorithm figures (35, 36, 39 and 40) have manually checked text
transcriptions alongside the images. The focused audit checks the bodies of equations (1)–(22), (31)–(33), their
displayed definitions/weights and selected necessary inline definitions. Equation (26) also received a targeted check.
Individual checks are recorded in `extraction.json` and strict regeneration patches in
`tools/paper_extract/review.json`.

This is not a fully proofread mathematical transcription. Other prose, inline notation and section 5 mathematics still
require source checks. All 71 display-math blocks parse with KaTeX 0.16.22; that establishes syntax, not mathematical
accuracy. Source discrepancies in symmetry, width mapping and the coefficient count remain faithfully transcribed and
are explained separately in the [audit](audit.md), including supported alternative formulas and a derived correction.

## Relevance and review scope

The introduction and Figure 2 show equal-width `m` stems acquiring different bitmap widths. Sections 2 and 3.4 address
diagonal strokes through integer offset vectors; §§3.2 and 3.6 measure stroke and white-space relationships, §3.5
handles approximate symmetry, and §4 links related features across a font. Section 5 describes preprocessing and
encoding; §6 extends the distortion measures to curved outlines, using polygonal approximations for intermediate feature
analysis while retaining curves in the adjusted output.

This is a complete proposed bitmap-generation pipeline, not a coverage filter for the current generator. In particular,
the integer offset argument in §2 assumes center-fill scan conversion. Its behavior cannot be transferred unchanged to
the project's 4× coverage and threshold raster without validation.

The report begins with an unnumbered abstract, followed by printed pages 1–42. The abstract has an explicit unnumbered
page label; numbered body-page references start at PDF page 2. Follow the
[collection review guidance](../README.md#accuracy-and-review) and the extraction notes before using equations as an
implementation specification.
