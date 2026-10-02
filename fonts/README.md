# Font assets

The specimen generator and its tests load font files from this directory. Roboto, Literata, and Source Sans 3 were moved
here from the probe directory with their bytes unchanged. Their original download URLs and upstream revisions are
unverified; retain their SHA-256 identities when reproducing results.

The current generator resolves these assets directly.

| File              | Embedded version                     | Embedded vendor | Embedded license declaration |
| ----------------- | ------------------------------------ | --------------- | ---------------------------- |
| `Roboto.ttf`      | 3.015; 2026                          | Google          | SIL Open Font License 1.1    |
| `Literata.ttf`    | 3.103;gftools[0.9.29]                | TypeTogether    | SIL Open Font License 1.1    |
| `SourceSans3.ttf` | 3.052;hotconv 1.1.0;makeotfexe 2.6.0 | Adobe           | SIL Open Font License 1.1    |

These declarations were read from the actual fonts' name tables. An older survey script labeled Roboto as Apache; this
file's embedded declaration is OFL 1.1.

```text
Roboto.ttf       d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134
Literata.ttf     b41138c9373112f32abb589cc22e8674b06ed4048b0c513be922bdd26f274440
SourceSans3.ttf  042fe2cc0b933e328410d7acbd0aa6a1873dca5aef81875f4bc214b08825c7b9
```

| File              | Variation axes with minimum, default, maximum |
| ----------------- | --------------------------------------------- |
| `Roboto.ttf`      | `wght`: 100, 400, 900; `wdth`: 75, 100, 100   |
| `Literata.ttf`    | `opsz`: 7, 12, 72; `wght`: 200, 400, 900      |
| `SourceSans3.ttf` | `wght`: 200, 200, 900                         |

The [specimen configuration](../tools/generator/specimens.json) explicitly selects weight 400. Literata optical size
follows the selected pixel size. Source Sans 3's embedded default weight is 200, so omitted axes do not reproduce the
configured specimens.

Small original test fonts live in `tools/generator/tests/fixtures`. The generator verifies font hashes; it does not
download fonts or establish their original provenance.
