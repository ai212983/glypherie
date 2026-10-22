# StrokeStyles fitting regression fixture

`roboto400-regression.json` is a minimized deterministic subset of real pipeline outputs, not a full runtime cache:
analysis glyphs `lIkA` (strokes, connectivity, junctions, conventions) and the Roboto400 capture blocks the cold tests
read (16px `selective_default`, 12px `auto_default`), with records pruned to codepoint and source/fitted commands.

Provenance: upstream StrokeStyles extraction (`out/diagnostics/strokestyles-fitting/extraction/roboto-cold-01.json`,
pinned Docker run) plus the host capture baseline
(`out/diagnostics/strokestyles-fitting/verification/host-baseline-with-donors.json`). Envelope `selection` records both
source paths, the sha256 of each original full artifact, and the selected chars/sizes/modes.

Rebuild from the same captured artifacts (numbers unaltered): keep `lIkA` glyph strokes, connectivity, junctions and
convention strings; keep Roboto wght400/wdth100 records for `lIkA` in the 16px `selective_default` and 12px
`auto_default` blocks with codepoint, `source_commands` and `fitted_commands` plus block/entry identity (`axes`,
`source_sha256`, family, size); drop the other blocks, raster/report record fields and per-glyph extraction duplication;
dump JSON with sorted keys, repository formatting and a trailing newline. Rebuilding must reproduce the committed bytes
exactly; verify with `sha256sum`.

Fresh extraction runs retain new timing metadata and source-artifact hashes. Compare geometry before replacing this
fixture; a fresh run need not reproduce its timing bytes.
