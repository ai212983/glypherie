<!-- cspell:words RLCD TEMPERA Playdate Soldered Waveshare uncalibrated RRGGBB MDTR -->

# Reflective display appearance model

This document describes the static appearance palettes used to preview monochrome font specimens as if on reflective
displays. Scope is appearance preview, not a physical optical simulator: no lighting transport, spectra, or device
calibration is modeled. Actual readability remains a separate question under the [evaluation rules](evaluation.md).

## Direct appearance palettes

A config holding a device preset plus optional paper/ink colors maps to an opaque two-entry mono palette: index 0 is
paper (no ink) and index 1 is ink (full ink). The provider returns colors only; it does not define layout, native frame,
or pixel-grid reproduction. Native frame orientation and packing follow the
[panel frame reference](references/panel-frame-formats.md); physical sizing follows
[font evaluation](references/font-evaluation.md).

Custom colors are freely editable with no imposed brightness order between paper and ink. Colors are strict opaque
6-digit hex (`#RRGGBB`, [W3C CSS Color 4 §5.2](https://www.w3.org/TR/2026/CRD-css-color-4-20261009/#hex-notation));
lowercase input normalizes to uppercase. Each field records its own origin: the device default or a custom override.

## Device presets

| Device                      | Native frame | Default paper | Default ink |
| --------------------------- | ------------ | ------------- | ----------- |
| Waveshare ESP32-S3-RLCD-4.2 | 300 × 400    | `#999999`     | `#282828`   |
| Inkplate 4TEMPERA           | 600 × 600    | `#999999`     | `#2D2D2D`   |
| Playdate                    | 400 × 240    | `#686868`     | `#191919`   |

The defaults are carried-forward illustrative preview choices, NOT manufacturer-specified colors, measured reflectances,
or calibrated hardware values. Do not read brightness differences between presets as device rankings. The provider does
not reproduce the native frame or pixel grid.

An illustrative warm-paper pair is `#F4ECDC` paper with `#000000` ink; it infers nothing about any panel.

Device identity, native frames and documentation links below are specified vendor data; the default colors are assumed.
No per-device optics beyond these colors is modeled.

## Literature and technical sources

Research checked in October 2026. Module specifications identify the display technology family behind each preset; they
do not supply the illustrative default colors.

- **[R9]** W3C, _CSS Color Module Level 4_,
  [9 October 2026 snapshot](https://www.w3.org/TR/2026/CRD-css-color-4-20261009/), especially §5.2 hex notation.
  Relevant definitions inspected; no runtime dependency selected.
- **[R15]** Midas Displays, _MDTR0420A-SPI_, Version 1, cover dated 23 November 2023
  ([manufacturer PDF](https://midasdisplays.com/wp-content/uploads/2024/12/MDTR0420A-SPI.pdf)). Monochrome reflective
  TFT, ST7305, 300 × 400. Technology-family reference for the Waveshare preset; its optical table is not adopted.
- **[R16]** E Ink Holdings, _ED060SC7_, Version 2.0, P-511-608(V:2), 15 November 2010
  ([manufacturer-authored PDF, distributor mirror](https://static1.1.sqspcdn.com/static/f/489821/26341974/1435253853757/ED060SC7.pdf)).
  Electrophoretic module. Technology-family reference for the Inkplate preset, not an ED038TH2 specification.
- **[R17]** Sharp, _LS027B7DH01_, LCP-2110015A, first edition 21 June 2010
  ([manufacturer-authored PDF mirror](https://s3.amazonaws.com/snapeda/datasheet/LS027B7DH01A_Sharp_Microelectronics.pdf)).
  400 × 240 Memory LCD. Technology-family reference for the Playdate preset; exact Playdate part identity is not
  established.

### Device documentation

- **[D1]** Waveshare, [ESP32-S3-RLCD-4.2](https://docs.waveshare.com/ESP32-S3-RLCD-4.2). Manufacturer overview
  inspected; not a measured optical model.
- **[D2]** Soldered, [Inkplate 4TEMPERA overview](https://docs.soldered.com/inkplate/4tempera/overview/) and
  [display modes](https://docs.soldered.com/inkplate/4tempera/basics/basic-display-modes/). Specifications inspected;
  front-light presence does not establish an optical output curve.
- **[D3]** Panic, [Designing for Playdate](https://help.play.date/developer/designing-for-playdate/), “Screen” and
  “Simulator appearance.” Manufacturer/developer documentation inspected.
