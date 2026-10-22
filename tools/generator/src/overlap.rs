//! Bounded 4x candidate Mono overlap mitigation with FreeType-style reduction.
//!
//! Source foundation: FreeType's overlap raster at pin
//! `57617782464411201ce7bbc93b086c1b4d7d84a5`, `src/smooth/ftsmooth.c`
//! (overlap path): scale the already fitted outline by four in each direction,
//! render antialiased spans, and accumulate reduced coverage into native
//! pixels. Each high-resolution sample is rounded with `(v + 8) / 16` before
//! accumulation, and the accumulated result saturates at 255. There is no
//! refit at a larger size. The overlap-flag documentation promises mitigation,
//! not exact filled-area coverage.
//!
//! Project adaptation: the AA kernel stays Zeno, so there is no claim of
//! FreeType byte identity or exact filled-union coverage; finite oversampling
//! mitigates double counting rather than removing it (duplicated
//! same-winding contours still change sampled coverage). Reduction applies
//! uniformly to every candidate Mono glyph, never gated on the fitted
//! overlap flag (the reported Roboto A has that flag false). Original fitted
//! commands, native integer grid/bounds, source advances and kerning are kept;
//! coverage is thresholded once at native resolution, then smart dropout
//! excluding terminal stubs runs once on the original geometry with raw coverage
//! untouched. No glyph tuning and no phase/threshold search.
//!
//! Storage bound: the full high-resolution image is never allocated.
//! Original paths are validated against the existing coordinate and native
//! size limits first (a natively valid 600x600 path stays valid; a small
//! rectangle at X 8300 stays valid even though its scaled coordinate 33200
//! exceeds the point bound). High-resolution rendering is tiled in
//! native-pixel units with at most 1 MiB of scratch per tile; every tile
//! feeds the full path with the correct global integer origin (including
//! negative origins), so tile clipping loses no winding and introduces no
//! edge seams. Limit violations and non-mono use are errors, never a silent
//! fallback that would bypass the mitigation.
use crate::{
    fail,
    probe::{self, FittedCommand, RasterOutput},
    Config, Error,
};
use zeno::{Fill, Format, Mask, Origin, Placement, Transform, Vector};

const SCALE: f32 = 4.0;
/// Native pixels per tile are capped so the high-resolution scratch buffer
/// (16 bytes per native pixel) never exceeds 1 MiB.
const TILE_NATIVE_PIXELS: u64 = 65_536;
const MAX_TILE_BYTES: usize = 1_048_576;
const MAX_PIXELS: u64 = 4_194_304;
const COORD_BOUND: f32 = 32768.0;

/// Reduce one native pixel's sixteen high-resolution samples FreeType-style:
/// each sample rounds with `(v + 8) / 16` before accumulation, and the total
/// saturates at 255 (sixteen fully covered samples sum to 256).
fn reduce_block(samples: &[u8; 16]) -> u8 {
    let mut acc = 0u32;
    for &v in samples {
        acc += (u32::from(v) + 8) / 16;
    }
    acc.min(255) as u8
}

/// Bounded 4x overlap-aware Mono rasterization for the candidate. Returns the
/// native grid, thresholded pixels and reduced coverage; dropout rescues are
/// applied to the pixels only, on the original geometry.
pub fn rasterize(commands: &[FittedCommand], config: &Config) -> Result<RasterOutput, Error> {
    #[cfg(test)]
    crate::source::raster_counter::record_logical(1);
    if commands.is_empty() {
        return Ok(RasterOutput {
            pixels: vec![],
            coverage: vec![],
            left: 0,
            top: 0,
            width: 0,
            height: 0,
        });
    }
    if config.output_bits != 1 {
        return Err(fail("overlap 4x raster requires 1-bit mono output"));
    }
    // Validate the original fitted outline against the existing bounds; the
    // scaled coordinates are never checked against the point bound.
    let zeno = probe::to_zeno(commands);
    let mut min_x = f32::INFINITY;
    let mut min_y = f32::INFINITY;
    let mut max_x = f32::NEG_INFINITY;
    let mut max_y = f32::NEG_INFINITY;
    let mut check = |x: f32, y: f32| -> Result<(), Error> {
        if !x.is_finite() || !y.is_finite() || x.abs() > COORD_BOUND || y.abs() > COORD_BOUND {
            return Err(fail("outline coordinate exceeds supported bounds"));
        }
        min_x = min_x.min(x);
        min_y = min_y.min(y);
        max_x = max_x.max(x);
        max_y = max_y.max(y);
        Ok(())
    };
    for command in &zeno {
        match *command {
            zeno::Command::MoveTo(p) | zeno::Command::LineTo(p) => check(p.x, p.y)?,
            zeno::Command::QuadTo(a, b) => {
                check(a.x, a.y)?;
                check(b.x, b.y)?;
            }
            zeno::Command::CurveTo(a, b, c) => {
                check(a.x, a.y)?;
                check(b.x, b.y)?;
                check(c.x, c.y)?;
            }
            zeno::Command::Close => {}
        }
    }
    // Same native control-point limit as the retained rasterizer.
    let control_w = max_x.ceil() - min_x.floor();
    let control_h = max_y.ceil() - min_y.floor();
    if f64::from(control_w) * f64::from(control_h) > MAX_PIXELS as f64 {
        return Err(fail("glyph bitmap exceeds 4 Mi pixels"));
    }
    // Native placement identical to the retained rasterizer: full-curve Zeno
    // bounds with floor/ceil integer grid, not the control-point box above.
    let bounds = zeno::bounds(zeno.as_slice(), Fill::NonZero, None);
    let (_, placement) = Placement::compute(Origin::TopLeft, Vector::ZERO, &bounds);
    let (left, top, width, height) = (
        placement.left,
        placement.top,
        placement.width,
        placement.height,
    );
    let native_len = u64::from(width)
        .checked_mul(u64::from(height))
        .ok_or_else(|| fail("glyph bitmap exceeds 4 Mi pixels"))?;
    if native_len > MAX_PIXELS {
        return Err(fail("glyph bitmap exceeds 4 Mi pixels"));
    }
    if width == 0 || height == 0 || native_len == 0 {
        return Ok(RasterOutput {
            pixels: vec![],
            coverage: vec![],
            left,
            top,
            width,
            height,
        });
    }
    // Global high-resolution shift anchoring every tile to the native grid:
    // high-resolution pixel (0, 0) covers scaled coords [4*left, 4*left + 1).
    // All values are small integers, exactly representable in f32.
    let tile_w = width.min(256).max(1);
    let tile_h = height
        .min((TILE_NATIVE_PIXELS / u64::from(tile_w)) as u32)
        .max(1);
    let transform = Transform::scale(SCALE, SCALE);
    let mut coverage = vec![0u8; native_len as usize];
    let mut ty = 0u32;
    while ty < height {
        let ty1 = (ty + tile_h).min(height);
        let mut tx = 0u32;
        while tx < width {
            let tx1 = (tx + tile_w).min(width);
            let hr_w = (tx1 - tx) * 4;
            let hr_h = (ty1 - ty) * 4;
            let tile_len = (hr_w as usize)
                .checked_mul(hr_h as usize)
                .ok_or_else(|| fail("overlap tile exceeds work limit"))?;
            if tile_len > MAX_TILE_BYTES {
                return Err(fail("overlap tile exceeds work limit"));
            }
            let mut tile = vec![0u8; tile_len];
            // Tile origin in global high-resolution pixels is (4*tx, 4*ty),
            // so this tile's shift is the global shift minus that origin.
            let shift_x = -4.0 * (i64::from(left) + i64::from(tx)) as f32;
            let shift_y = -4.0 * (i64::from(top) + i64::from(ty)) as f32;
            let mut mask = Mask::new(zeno.as_slice());
            mask.format(Format::Alpha);
            mask.transform(Some(transform));
            mask.size(hr_w, hr_h);
            mask.render_offset(Vector::new(shift_x, shift_y));
            mask.render_into(&mut tile, None);
            for ny in ty..ty1 {
                for nx in tx..tx1 {
                    let base_x = (nx - tx) * 4;
                    let base_y = (ny - ty) * 4;
                    let mut samples = [0u8; 16];
                    for dy in 0..4 {
                        let row = (base_y + dy) * hr_w;
                        for dx in 0..4 {
                            samples[(dy * 4 + dx) as usize] = tile[(row + base_x + dx) as usize];
                        }
                    }
                    coverage[(ny * width + nx) as usize] = reduce_block(&samples);
                }
            }
            tx = tx1;
        }
        ty = ty1;
    }
    let pixels: Vec<u8> = coverage
        .iter()
        .map(|&v| u8::from(v >= config.mono_threshold))
        .collect();
    let mut raster = RasterOutput {
        pixels,
        coverage,
        left,
        top,
        width,
        height,
    };
    // SCANTYPE rule 6 excludes terminal caps; legacy dropout stays separate.
    // Threshold once above, scan the original geometry, keep raw coverage.
    crate::dropout::apply_without_stubs(commands, &mut raster)?;
    Ok(raster)
}

#[cfg(test)]
mod tests {
    use super::reduce_block;

    #[test]
    fn per_sample_rounding_matches_freetype_not_final_average() {
        // Sixteen half-covered high-resolution cells: per-sample
        // (127 + 8) / 16 = 8 accumulates to 128 (ink at threshold 128),
        // while averaging before one final rounding would stay at 127.
        assert_eq!(reduce_block(&[127; 16]), 128);
        assert_eq!(reduce_block(&[0; 16]), 0);
        // Sixteen fully covered samples sum to 256 and saturate at 255.
        assert_eq!(reduce_block(&[255; 16]), 255);
    }
}
