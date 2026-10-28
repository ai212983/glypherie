# Playdate Font Lab staging

Builds `out/playdate-font-lab/FontLab.pdx` from `apps/playdate-fontlab/Source/` plus generated fonts.

## Setup

Install the Playdate SDK 3.1.2 (provides `bin/pdc` and the Simulator) and point at it:

```sh
export PLAYDATE_SDK_PATH="$HOME/Developer/PlaydateSDK"
```

Needs Node and, for the default export, Rust/Cargo with a C compiler. Generated output under `out/playdate-font-lab/` is
not committed. SDK fonts and installed SDK assets are never copied into the repo.

## Commands

```sh
node apps/playdate-fontlab/build.mjs --help
node apps/playdate-fontlab/build.mjs
node apps/playdate-fontlab/build.mjs --font path/to/custom.fnt --run
```

## Configuration

- `--sdk PATH` overrides `PLAYDATE_SDK_PATH`; with neither set, falls back to `~/Developer/PlaydateSDK`. An explicit
  `--sdk` or a set `PLAYDATE_SDK_PATH` without `bin/pdc` stops the build instead of falling back.
- Without `--font`, exports repo `fonts/Roboto.ttf` and `fonts/SourceSans3.ttf` at 16/24 px via `cargo run --bin
  font_playdate`, one kerned/plain partner pair each; request JSON lands in `out/playdate-font-lab/requests/`.
- `--font PATH` (repeatable) stages an existing Playdate `.fnt` without invoking Rust; entries carry no `unkerned`
  partner and coverage is derived from the file. Staged copies are named `provided-<n>-<slug>.fnt`; labels keep the
  original filename.
- `--text TEXT` / `--text-file PATH` (repeatable, combine in argument order) stage custom inspection phrases in
  `Source/phrases.lua`, always written and empty when none. A file's whole UTF-8 content is one phrase; tabs become
  spaces. Empty phrases, control characters other than LF, malformed UTF-8, phrases over 4096 scalars, and more than 16
  phrases stop the build.
- Without `--font`, phrase scalars join the printable-ASCII repertoire at the default 16/24 px sizes; missing glyphs
  fail the export. Imported `--font` coverage is unchanged, so phrases render only supported glyphs.
- `--run` opens the compiled `.pdx` in the SDK Simulator.
