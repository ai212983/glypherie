# Local spec copies

Microsoft OpenType 1.8.4 spec pages vendored for the CVT cut-in
investigation (literata-16 thin stems). Retrieved 2026-09-15.
Vendored as files rather than a submodule: the upstream source is
the MicrosoftDocs/typography docs monorepo (Win.typography depot),
not a focused spec repo, so a submodule would drag the whole docs
tree; file copies with hashes match the `papers/` convention.

| File | Page | Source |
| --- | --- | --- |
| `truetype-instruction-set-otspec184.md` | TrueType Instruction Set (MIAP/MIRP/MDRP cut-in tests, SCVTCI, SSWCI/SSW, minimum_distance) | `https://learn.microsoft.com/en-us/typography/opentype/otspec184/tt_instructions` |
| `truetype-fundamentals-otspec184.md` | TrueType fundamentals (CVT purpose: regularize stem weights) | `https://learn.microsoft.com/en-us/typography/opentype/otspec184/ttch01` |
| `cvt-table-otspec184.md` | cvt table definition | `https://learn.microsoft.com/en-us/typography/opentype/otspec184/cvt` |

Upstream git: `https://github.com/MicrosoftDocs/typography`, all three
at commit `a52fe69` (`typographydocs/opentype/otspec184/`). Original
`.docx`/`.htm` sources are linked in each file's front matter.

SHA-256:
- `truetype-instruction-set-otspec184.md`: `0ce55a77…c53421`
- `truetype-fundamentals-otspec184.md`: `de0b30b6…f138263d`
- `cvt-table-otspec184.md`: `16cde12b…89bbf74`

Full hashes: record with `sha256sum docs/reference/fonts/specs/*.md`.
Check Microsoft's terms before redistributing beyond this checkout.
