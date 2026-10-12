# Light weight continuity

<!-- cspell:words SCANTYPE -->

Binary conversion can erase light strokes; independent width minima overweight diagonals, and integer shared widths
create abrupt transitions. The model combines outline-driven visibility with fractional width coordination.

## Foundation and invariant

[Hersch §§5–7](../../references/papers/1993-hersch/paper.md) grounds width, placement and interior-span dropout control.
[TrueType SCANTYPE](https://learn.microsoft.com/en-us/typography/opentype/spec/tt_instructions#scantype) and the
[scan-converter specification](https://learn.microsoft.com/en-us/typography/opentype/spec/ttch01#the-scan-converter)
ground midpoint selection and stub handling.
[Pinned FreeType width fitting](https://github.com/freetype/freetype/blob/57617782464411201ce7bbc93b086c1b4d7d84a5/src/autofit/aflatin.c)
preserves extra-light widths below 5/8 pixel and supplies fractional horizontal fitting.
[Shamir §3](../../references/papers/2003-shamir/paper.md) grounds shared widths and relative source dimensions.

Preserve source thickness and contrast, anchors, tangents and ownership while keeping narrow filled strokes visible. The
coverage-based dropout adaptation and shared-width transfer are **project hypotheses** applying these mechanisms.

## Topics

### 01. Binary continuity

Subpixel filled spans in fitted line, quadratic and cubic contours receive a midpoint pixel when ordinary binary
conversion leaves them without a black pixel center. Horizontal and vertical scans use nonzero-winding interiors and
combine their rescue pixels against the same original bitmap. Stubs are included; midpoint ties use the left/bottom
convention.

Visibility changes only the binary bitmap, preserving fitted outlines, raw coverage and threshold 128. Invalid winding
or excessive scan work fails explicitly. This adapts TrueType dropout principles rather than reproducing its scan
converter or FreeType pixels.

### 02. Extra-light weight coordination

For an extra-light horizontal standard, diagonals keep perpendicular source thickness: transfer ratio one, without a
dominant-axis pixel floor. Dropout supplies visibility while anchors, tangents, ownership, movement bounds and rounding
separation constrain fitting.

### 03. Shared width transitions

The horizontal standard uses the inherited smooth width branch for automatic Mono/default-script fitting, including
glyphs without diagonals. Each diagonal receives `source thickness × fitted standard / scaled standard`, projected onto
its dominant control axis. Outside extra-light fitting, the existing rounding bound remains.

All diagonal classes share that horizontal reference; bars use the vertical standard. Assess contrast against stems and
bars separately. Placement, Y snapping and blue zones use ordinary fitting.

## Scope and limits

The changes concern automatic Mono fitting and binary visibility. Accepted review covers Roboto/Literata/Source Sans 3
at 14/16/18/20 px, weight 400, Roboto width 100, Literata optical size equal to pixel size and both configured profiles.
Roboto 14 px weights 100/200 and width-transition probes are isolated diagnostic witnesses.

Fractional widths remove the shared fitted-width cliff but cannot make binary coverage or inherited placement
continuous. The upright-column step near Roboto 14 px weight 465 and placement steps are accepted limitations. Dropout
can add terminal ink without changing outlines, requiring separate continuity, weight and contrast assessment.
