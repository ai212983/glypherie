# FreeType monochrome scanner

Upstream: FreeType 2.15.0, tag `VER-2-15-0`, commit
`37515cf56ba3349656049edbed89ffc6f6466f2d`.
Sources: `src/raster/ftraster.c`, `src/raster/ftmisc.h`, `include/freetype/ftimage.h`.
Distributed under the FreeType License in [FTL.TXT](FTL.TXT); retain upstream copyright notices.

The scanner's geometry, center-fill, two-pass smart dropout, stub and overshoot rules are unchanged.
`ftraster.c` includes `platform.h` instead of libc's `string.h`. `ftmisc.h` uses that same header and
`stdint.h`, and defines FreeType 2.15's allocation hooks against the supplied `FT_Memory` arena.
`platform.h` declares the compiler-builtins memset for freestanding WASM.
`adapter.c` supplies per-call raster state and bounded caller-owned aligned scratch; it avoids the
standalone constructor's shared mutable singleton. The size estimate follows `ft_black_render`.
No C heap, font parser, interpreter, autohinter or platform FreeType library is linked.

Updates must retain source provenance and license, compare scanner output with an independently built
full FreeType at the same pin, and check native/WASM parity, bounds and concurrent rendering.
The owning model and assessment are in [iteration 001.03](../../../../docs/revisions/001/03-spacing-kerning.md).
