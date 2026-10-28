# Font assets

The specimen generator and its tests load font files from this directory. Roboto, Literata, and Source Sans 3 were moved
here from the probe directory with their bytes unchanged. Their original download URLs and upstream revisions are
unverified; retain their SHA-256 identities when reproducing results.

Roboto Italic is the authentic upstream italic variable font, fetched from the pinned Google Fonts revision below and
stored as `Roboto-Italic.ttf`. Its license text is kept alongside as `OFL-Roboto.txt`, scoped to the Roboto family.

Roboto Flex is the authentic upstream variable font, fetched from the same pinned Google Fonts revision and stored as
`RobotoFlex.ttf`. Its license text is kept alongside as `OFL-RobotoFlex.txt`, scoped to the Roboto Flex family.

Literata and Source Sans 3 license texts are the authentic upstream OFL 1.1 texts, kept alongside as `OFL-Literata.txt`
and `OFL-SourceSans3.txt`. Both match the OFL 1.1 declarations in the fonts' name tables; Source Sans 3 additionally
carries the Reserved Font Name `Source`, present in its upstream text.

The current generator resolves these assets directly.

| File                | Embedded version                     | Embedded vendor | Embedded license declaration |
| ------------------- | ------------------------------------ | --------------- | ---------------------------- |
| `Roboto.ttf`        | 3.015; 2026                          | Google          | SIL Open Font License 1.1    |
| `Roboto-Italic.ttf` | 3.015; 2026                          | Google          | SIL Open Font License 1.1    |
| `RobotoFlex.ttf`    | 3.200;gftools[0.9.32]                | Google          | SIL Open Font License 1.1    |
| `Literata.ttf`      | 3.103;gftools[0.9.29]                | TypeTogether    | SIL Open Font License 1.1    |
| `SourceSans3.ttf`   | 3.052;hotconv 1.1.0;makeotfexe 2.6.0 | Adobe           | SIL Open Font License 1.1    |

These declarations were read from the actual fonts' name tables. An older survey script labeled Roboto as Apache; this
file's embedded declaration is OFL 1.1. The italic file additionally declares style Italic (`head.macStyle` and
`OS/2.fsSelection` italic bits set) with the same version string as the upright Roboto.

```text
Roboto.ttf       d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134
Roboto-Italic.ttf 9725a847af6b460ffca162ae66d20dad48b01876137947180b42d7dcd7887182
RobotoFlex.ttf 9b523f7d82593df0107173849ebb8c817471a1df4b4fb2c3cbf40cfd810c8281
Literata.ttf     b41138c9373112f32abb589cc22e8674b06ed4048b0c513be922bdd26f274440
SourceSans3.ttf  042fe2cc0b933e328410d7acbd0aa6a1873dca5aef81875f4bc214b08825c7b9
```

Provenance: `Roboto-Italic.ttf` is byte-identical to `ofl/roboto/Roboto-Italic[wdth,wght].ttf` at
[google/fonts](https://github.com/google/fonts/blob/bd8f81ddb5c74d5c8897b36ad88b440266245103/ofl/roboto/METADATA.pb)
commit `bd8f81ddb5c74d5c8897b36ad88b440266245103`, which declares the italic style under the OFL license with `wdth`
75–100 and `wght` 100–900. `OFL-Roboto.txt` is the `ofl/roboto/OFL.txt` text from that same commit.

Provenance: `RobotoFlex.ttf` is byte-identical to
`ofl/robotoflex/RobotoFlex[GRAD,XOPQ,XTRA,YOPQ,YTAS,YTDE,YTFI,YTLC,YTUC,opsz,slnt,wdth,wght].ttf` at
[google/fonts](https://github.com/google/fonts/blob/bd8f81ddb5c74d5c8897b36ad88b440266245103/ofl/robotoflex/METADATA.pb)
commit `bd8f81ddb5c74d5c8897b36ad88b440266245103`, which declares the family under the OFL license with `opsz` 8–144,
`slnt` -10–0, `wdth` 25–151 and `wght` 100–1000, plus custom parametric axes. `OFL-RobotoFlex.txt` is the
`ofl/robotoflex/OFL.txt` text from that same commit.

Provenance: `OFL-Literata.txt` is the `OFL.txt` text from
[literata repository](https://github.com/googlefonts/literata/blob/main/OFL.txt), whose header (`Copyright 2017 The
Literata Project Authors`) matches the `Literata.ttf` name table. `OFL-SourceSans3.txt` is the `LICENSE.md` text from
[adobe-fonts/source-sans](https://github.com/adobe-fonts/source-sans/blob/release/LICENSE.md) (`Copyright 2010-2024
Adobe`, Reserved Font Name `Source`), matching the `SourceSans3.ttf` name table.

| File                | Variation axes with minimum, default, maximum |
| ------------------- | --------------------------------------------- |
| `Roboto.ttf`        | `wght`: 100, 400, 900; `wdth`: 75, 100, 100   |
| `Roboto-Italic.ttf` | `wght`: 100, 400, 900; `wdth`: 75, 100, 100   |
| `Literata.ttf`      | `opsz`: 7, 12, 72; `wght`: 200, 400, 900      |
| `SourceSans3.ttf`   | `wght`: 200, 200, 900                         |

Roboto Flex exposes thirteen axes in source order, read from the actual font's variation table:

| Axis   | Minimum | Default | Maximum | Hidden |
| ------ | ------- | ------- | ------- | ------ |
| `opsz` | 8       | 14      | 144     | no     |
| `wght` | 100     | 400     | 1000    | no     |
| `GRAD` | -200    | 0       | 150     | no     |
| `wdth` | 25      | 100     | 151     | no     |
| `slnt` | -10     | 0       | 0       | no     |
| `XOPQ` | 27      | 96      | 175     | yes    |
| `YOPQ` | 25      | 79      | 135     | yes    |
| `XTRA` | 323     | 468     | 603     | yes    |
| `YTUC` | 528     | 712     | 760     | yes    |
| `YTLC` | 416     | 514     | 570     | yes    |
| `YTAS` | 649     | 750     | 854     | yes    |
| `YTDE` | -305    | -203    | -98     | yes    |
| `YTFI` | 560     | 738     | 788     | yes    |

The [specimen configuration](../crates/generator/specimens.json) explicitly selects weight 400. Literata optical size
follows the selected pixel size, as does Roboto Flex optical size; its configured `wght` 400, `wdth` 100 and `slnt` 0
equal the embedded defaults, and remaining axes use those defaults. Source Sans 3's embedded default weight is 200, so
omitted axes do not reproduce the configured specimens.

Small original test fonts live in `crates/generator/tests/fixtures`. The generator verifies font hashes; it does not
download fonts or establish their original provenance.
