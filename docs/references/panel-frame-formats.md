# Panel specimen frame formats

Inkplate and Waveshare specimen viewers consume different packed image formats. Preserve their bit order, grayscale
polarity, and file framing when adding a panel exporter to the current generator.

This document extracts the conventions implemented by the former probe exporters, `render_specimens.py::pack` and
`src/bin/specimen.rs`, and checked by `tests/test_render_specimens.py`. The Rust exporter comments record hardware
confirmation of Inkplate grayscale polarity. These are the historical specimen viewer contracts; firmware readers and
panel rotation must be checked when integrating a new exporter.

## Dimensions and coordinates

Pixels are stored row by row, from left to right and then top to bottom. The Inkplate viewer used 600 × 600 frames. The
Waveshare viewer used 400 × 300 landscape frames on the 300 × 400 panel. Width and height describe the exported frame
orientation.

The generator's glyph pixels represent ink: zero is white and the maximum level is black. Convert that representation
according to the output format below. Compose the complete page at native resolution before packing it.

## Binary packing

Both formats use one bit per pixel, with one representing black and zero representing white. Each row occupies
`ceil(width / 8)` bytes; padding bits in the last byte are zero. Start each new row on a byte boundary.

| Format           | Bit for pixel x within a byte | First pixel black and seven white pixels | File framing                      |
| ---------------- | ----------------------------- | ---------------------------------------- | --------------------------------- |
| Inkplate binary  | `1 << (x % 8)`                | `01`                                     | 16-byte header followed by pixels |
| Waveshare binary | `1 << (7 - x % 8)`            | `80`                                     | Raw pixels without a header       |

The examples are hexadecimal bytes. For a 9 × 2 image containing black pixels at `(8, 0)` and `(0, 1)`, the payload is
`00 01 01 00` for Inkplate and `00 80 80 00` for Waveshare. A 600 × 600 Inkplate binary file has 45,000 payload bytes
and 45,016 total bytes. A 400 × 300 Waveshare file has exactly 15,000 bytes.

## Inkplate grayscale packing

The viewer uses two four-bit fields per byte to carry eight grayscale levels. The left pixel at an even x coordinate
occupies the high nibble; the next pixel occupies the low nibble. Width must be even and the row stride is `width / 2`.

Stored nibbles use even values only. Higher values are lighter: black is `0`, white is `14`, and intermediate values are
`2, 4, 6, 8, 10, 12`. For generator ink level `q` in `0..7`, the stored nibble is `2 * (7 - q)`. Two adjacent pixels are
packed as `(left_nibble << 4) | right_nibble`.

Eight pixels consisting of one black pixel followed by seven white pixels produce `0e ee ee ee`. A 600 × 600 grayscale
frame has 180,000 payload bytes and 180,016 total bytes. The old Waveshare exporter supported binary output only.

## Inkplate file header

Both Inkplate formats begin with this 16-byte header. Multi-byte integers are little-endian.

| Byte offset | Length | Value                                      |
| ----------- | ------ | ------------------------------------------ |
| 0           | 4      | ASCII `MDFR`                               |
| 4           | 1      | Version `1`                                |
| 5           | 1      | Format `0` for binary or `1` for grayscale |
| 6           | 2      | Width in pixels                            |
| 8           | 2      | Height in pixels                           |
| 10          | 6      | Reserved, all zero                         |

For an 8 × 1 binary image with only its first pixel black, the complete file is:

```text
4d 44 46 52 01 00 08 00 01 00 00 00 00 00 00 00 01
```

## Viewer loading conventions

The Waveshare specimen viewer embedded raw frames in a Rust module, so changing the selected session required a rebuild.
The Inkplate viewer read frames from `/assets/spec` on an SD card and used a compiled list of selected files. Its
exporter used the first eight hexadecimal characters of the frame SHA-256, uppercase, plus `.BIN`, as the short
filename. The selection list determined which files entered a session.

## Grayscale verification frame

The old Inkplate exporter included a dedicated 600 × 600 verification page containing all eight stored levels. Its
recipe remains useful when checking a new panel adapter:

- Draw eight vertical bands, each 75 pixels wide, from y = 90 through y = 469.
- Label the bands 0 through 7 beneath the swatches using full black text on a white background.
- For band level `l`, use generator ink level `7 - l`, producing stored nibble `2 * l`. Band 0 is black and band 7 is
  white.
- Show the frame through a dedicated viewer. The old exporter comments record that the product UI repainted over images
  drawn behind it, preventing that route from serving as a stable verification display.

Verify the order of lightness, visibility of the intermediate levels, and correct placement of both pixels in each byte
on the actual panel. A host image verifies encoding; it does not establish the panel's response.

The exporters displayed pre-rendered pages. Their frames establish packing and display conventions; evaluation of live
layouts, refresh behavior, and physical readability still requires the panel workflow in
[font evaluation](font-evaluation.md).
