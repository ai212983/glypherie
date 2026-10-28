# skrifa-scan: metadata-only scan-state snapshot

Base: registry Skrifa 0.48.0, upstream checksum
`a5213b4825bac3587046330052d61bfac7bd3bd0d203c758d7c2ef726fcea034`
(from `crates/generator/Cargo.lock`, package `skrifa` 0.48.0).
Source registry path used for the copy:
`/Users/dimitri/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/skrifa-0.48.0`.
Reproduce the snapshot diff with `diff -r` of that source against this directory,
excluding `Cargo.toml` (renamed below), removed `tests/` and `Cargo.lock`.

The original MIT and Apache-2.0 licenses are retained (`LICENSE-MIT`,
`LICENSE-APACHE`). The package and library are renamed `skrifa` to
`skrifa_scan`; upstream version 0.48.0 and dependencies are preserved
(`read-fonts` 0.45.0, `bytemuck` 1.14.0). There is no Cargo `[patch]`
global replacement: the registry `skrifa` dependency remains the
independent reference renderer and stays in use for manual rendering,
reference captures, and Gray. `tests/` and the published `Cargo.lock`
are dropped following the `skrifa-baseline` vendor convention; unit
tests live in `src/` modules. The pinned `font-test-data` 0.10.0 dev
dependency supports the upstream unit suite plus the scan tests below.

## Patch surface (metadata only; no fitting, control-flow, or geometry change)

## Retained automatic-fitting bearing residuals

- `src/outline/mod.rs`: `AdjustedMetrics` gains
  `autohint_deltas_26_6: Option<[i32; 2]>`, documented with the
  autofit loader anchors. All non-autohint constructions set `None`.
- `src/outline/autohint/instance.rs`: `draw` retains `[rounded pp1x
  minus pre-rounding pp1x, rounded pp2x minus pre-rounding pp2x]`
  after the small-bearing adjustments, zeroed where the loader
  forces the advance (fixed pitch or same-width digits), never
  zeroed on the light path, and returns them in
  `autohint_deltas_26_6`. The values are read from already-computed
  phantom points; fitting arithmetic, outline translation and the
  returned advance are untouched.
- Foundation: the same autofit loader accounting as the validated
  diagnostic probe (rounded point minus pre-rounding value;
  fixed-advance zeroing):
  <https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/afloader.c#L462>
  <https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/afloader.c#L540>
  <https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/afloader.c#L552>
- Limits: residuals describe the automatic hinter only. Every draw
  through `HinterKind::Auto` (explicit `Engine::Auto`, whatever the
  outline format) reports them, including CFF/CFF2 outlines, which the
  autohint instance draws directly. Native-hinted draws report `None`:
  the TrueType interpreter and the PostScript interpreter (native
  CFF/CFF2 under fallback or interpreter selection), plus unhinted,
  VARC, HarfBuzz and scan-conversion draws. Consumers must apply the
  project fixed-pitch/tabular exclusions and engine/target gates; this
  field is a faithful reading, not a placement decision.

- `src/outline/mod.rs`: new public `ScanControl { enabled, scan_type: u16 }`
  and `ScanConversion { control, contour_modes: Vec<Option<u8>> }`;
  `AdjustedMetrics` gains `scan_conversion: Option<ScanConversion>` and
  loses `Copy`. All non-Glyf-interpreter constructions set the field to
  `None` (unhinted, Auto, CFF/CFF2, VARC, HarfBuzz paths).
- `src/outline/glyf/hint/instance.rs`: new `GlyphScanState`; `HintInstance::hint`
  returns it alongside the existing result, snapshotted from the retained
  graphics state even when a non-pedantic program fails (geometry and error
  handling unchanged); new `retained_scan_state` exposes the `prep` outcome.
- `src/outline/glyf/mod.rs`: `FreeTypeScaler` carries running dropout state
  seeded from retained `prep` state plus per-contour marker modes (allocated
  only on the interpreter path). Each executed simple/component program stamps
  its range-first contour per FreeType `ttgload.c` `TT_Hint_Glyph`
  (`tags[0] |= (scan_type << 5) | HAS_SCANMODE`). A composite program adopts
  state without marking: its zone is prepared on the base outline
  (`TT_Process_Composite_Glyph`) while the stamp targets `current`, so child
  first-point markers stand unchanged. `scale` returns the `ScanConversion`
  with the full low-16-bit `scan_type` and 3-bit marker modes.
- `ScanConversion.hinting_axes` records axes read or constrained by executed glyph instructions. The dispatcher
  observes projection, dual-projection and freedom vectors, so zero moves reserve an axis; a no-op IUP does not.
  Ownership survives UTP. Point-defined vectors, intersections, composite programs with constraints and failed
  execution conservatively reserve both axes. Recording never changes native coordinates or control flow.
- `src/outline/cff/mod.rs` and `src/outline/mod.rs`: descriptive PostScript hint presence/axis queries evaluate stem
  operators, including subroutines, and Private DICT alignment zones. Transformed subfonts reserve both axes;
  unrecognized data returns unknown. These queries do not apply fitting.
- `src/outline/hint.rs`, `src/outline/autohint/instance.rs`: plumb the new
  field (`None` outside the Glyf interpreter path).
- `src/outline/glyf/mod.rs` tests: four synthetic-glyph tests (BeBuffer-built
  `glyf`/`loca` over `TTHINT_SUBSET` metrics): prep/glyph threshold
  enable/disable, simple modes with contour order and `0x108` truncation,
  two components with distinct modes where the composite override adopts
  state without marking, and repeated-draw isolation.

## Semantic limits

- Read-only recording of executed `SCANCTRL` (reuses the interpreter's own
  `ppem`/target evaluation) and `SCANTYPE` state; no engine selection, fit,
  raster, or `INSTCTRL` behavior change.
- `contour_modes` length always equals the emitted contour count; `None` means
  that contour's range ran no bytecode, never a reset.
- Markers exist only where simple/component bytecode executed;
  empty-instruction ranges and composite programs record no marker (control
  state still advances).
- Global mode decisions must use the full 16-bit `scan_type`, never the
  truncated 3-bit marker.
- Raw engine executions are out of scope: e.g. Skrifa masks `SCANTYPE` to the
  low 16 bits (so a sign-extended negative push wraps) while FreeType ignores
  negative values. Metadata records what the bundled interpreter executed.

## Validation

Run `cargo test --manifest-path crates/generator/vendor/skrifa-scan/Cargo.toml
--lib scan_` from the repo root with an isolated target dir. The four
`scan_*` tests plus the untouched upstream unit suite must pass.
