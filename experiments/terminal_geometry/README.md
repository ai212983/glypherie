# Terminal geometry experiment

Owning design: `docs/revisions/001/03-spacing-kerning.md`, terminal-tips section, supporting-cap paragraph. This README
holds setup, commands and configuration only; findings live in the owning document.

## Run

Python standard library only:

```sh
python3 -m unittest discover -s experiments/terminal_geometry/tests -t . -v
python3 -m experiments.terminal_geometry.replay
```

Replay reads `out/diagnostics/terminal-stub-correction-20261020/corpus.json` (before/after fixed FreeType scans) crossed
with `out/diagnostics/source-feature-work-20261020/source-controls.json` (source outlines) and writes
`out/diagnostics/source-feature-work-20261020/terminal-report.json` (parent-assigned path, kept out of
`out/diagnostics/terminal_geometry/`). The maintained kernel is `tools/generator/src/terminal_caps.rs`; adoption and
assessment live in the owning iteration.
