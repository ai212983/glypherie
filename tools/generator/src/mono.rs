//! FreeType monochrome scanning of Skrifa-fitted outlines.
//! Source provenance: vendor/freetype-mono/PATCH.md.
//! Zeno coverage is diagnostic and does not select monochrome pixels.
use crate::{
    fail,
    probe::{self, FittedCommand, RasterOutput},
    Config, Error, MonoDropoutMode,
};
use std::ffi::{c_int, c_long};

pub const VERSION: &str = "2.15.0";
pub const SOURCE_SHA256: &str = env!("FREETYPE_MONO_SHA256");
const MAX_POINTS: usize = u16::MAX as usize;
const MAX_SCRATCH_BYTES: usize = 16 * 1024 * 1024;

#[repr(C)]
struct Point {
    x: c_long,
    y: c_long,
}
extern "C" {
    fn font_mono_scratch_words(width: u32, height: u32) -> usize;
    fn font_mono_render(
        points: *const Point,
        tags: *const u8,
        ends: *const u16,
        point_count: u16,
        contour_count: u16,
        width: u32,
        height: u32,
        buffer: *mut u8,
        scratch: *mut usize,
        scratch_bytes: usize,
        outline_flags: c_int,
    ) -> c_int;
}

/// Rasterize a closed outline at its integer origin.
/// Points round to 26.6 with FT_PIX_ROUND ties toward positive infinity.
/// Translation into the bitmap preserves the outline's pixel-grid phase.
pub fn rasterize(commands: &[FittedCommand], config: &Config) -> Result<RasterOutput, Error> {
    rasterize_with_scan_state(commands, config, None)
}

pub fn rasterize_with_scan_state(
    commands: &[FittedCommand],
    config: &Config,
    font_scan: Option<&crate::reference::FontScanState>,
) -> Result<RasterOutput, Error> {
    if config.output_bits != 1 {
        return Err(fail("FreeType mono raster requires 1-bit output"));
    }
    let mut points = Vec::new();
    let mut tags = Vec::new();
    let mut ends = Vec::new();
    let mut open = false;
    fn add(
        points: &mut Vec<Point>,
        tags: &mut Vec<u8>,
        x: f32,
        y: f32,
        tag: u8,
    ) -> Result<(), Error> {
        if !x.is_finite() || !y.is_finite() || x.abs() > 32768.0 || y.abs() > 32768.0 {
            return Err(fail("outline coordinate exceeds supported bounds"));
        }
        if points.len() >= MAX_POINTS {
            return Err(fail("FreeType mono outline exceeds point limit"));
        }
        points.push(Point {
            x: (f64::from(x) * 64.0 + 0.5).floor() as c_long,
            y: (f64::from(y) * 64.0 + 0.5).floor() as c_long,
        });
        tags.push(tag);
        Ok(())
    }
    for command in commands {
        match *command {
            FittedCommand::MoveTo(x, y) => {
                if open {
                    return Err(fail("mono outline has unclosed contour"));
                }
                open = true;
                add(&mut points, &mut tags, x, y, 1)?;
            }
            FittedCommand::Close => {
                if !open {
                    return Err(fail("mono outline closes no contour"));
                }
                ends.push((tags.len() - 1) as u16);
                open = false;
            }
            _ if !open => return Err(fail("mono outline segment has no contour")),
            FittedCommand::LineTo(x, y) => add(&mut points, &mut tags, x, y, 1)?,
            FittedCommand::QuadTo(x1, y1, x, y) => {
                add(&mut points, &mut tags, x1, y1, 0)?;
                add(&mut points, &mut tags, x, y, 1)?;
            }
            FittedCommand::CurveTo(x1, y1, x2, y2, x, y) => {
                add(&mut points, &mut tags, x1, y1, 2)?;
                add(&mut points, &mut tags, x2, y2, 2)?;
                add(&mut points, &mut tags, x, y, 1)?;
            }
        }
    }
    if open {
        return Err(fail("mono outline has unclosed contour"));
    }
    if let Some(scan) = font_scan {
        if !config.mono_raster.font_instructions
            || scan.source_sha256 != crate::font_scan::SOURCE_SHA256
            || scan.contour_modes.len() != ends.len()
            || scan.contour_modes.iter().flatten().any(|&mode| mode > 7)
        {
            return Err(fail("invalid font scan state or identity"));
        }
        // FreeType ttgload.c stamps a component's first point; ftraster.c
        // Decompose_Curve inherits that mode until another contour marker.
        // https://github.com/freetype/freetype/blob/VER-2-15-0/src/truetype/ttgload.c
        let mut first = 0;
        for (&end, mode) in ends.iter().zip(&scan.contour_modes) {
            if let Some(mode) = mode {
                tags[first] |= 4 | (mode << 5);
            }
            first = usize::from(end) + 1;
        }
    }
    // Reuse the coverage raster's bounds and diagnostic samples.
    let mut output = probe::rasterize(commands, config)?;
    if output.width == 0 || output.height == 0 {
        return Ok(output);
    }
    if ends.len() > MAX_POINTS {
        return Err(fail("FreeType mono outline exceeds contour limit"));
    }
    let bottom = -i64::from(output.top) - i64::from(output.height);
    for point in &mut points {
        point.x -= c_long::from(output.left) * 64;
        point.y -= (bottom * 64) as c_long;
    }
    let pitch = output.width.div_ceil(8) as usize;
    let mut packed = vec![0; pitch * output.height as usize];
    // SAFETY: probe::rasterize validated nonzero dimensions and at most 4 Mi pixels.
    let words = unsafe { font_mono_scratch_words(output.width, output.height) };
    let bytes = words
        .checked_mul(std::mem::size_of::<usize>())
        .filter(|n| *n <= MAX_SCRATCH_BYTES)
        .ok_or_else(|| fail("FreeType mono scratch exceeds allocation limit"))?;
    let mut scratch = vec![0usize; words];
    // FreeType ignores stub control when IGNORE_DROPOUTS is set.
    const IGNORE_DROPOUTS: c_int = 0x8;
    const SMART_DROPOUTS: c_int = 0x10;
    const INCLUDE_STUBS: c_int = 0x20;
    let manual_flags = match config.mono_raster.dropout {
        MonoDropoutMode::Off => IGNORE_DROPOUTS,
        MonoDropoutMode::Simple => 0,
        MonoDropoutMode::Smart => SMART_DROPOUTS,
    } | if config.mono_raster.include_stubs {
        INCLUDE_STUBS
    } else {
        0
    };
    // FreeType refines small-bitmap curve intersections; its size guard selects the fallback.
    // https://github.com/freetype/freetype/blob/VER-2-15-0/src/raster/ftraster.c#L522-L563
    const HIGH_PRECISION: c_int = 0x100;
    // Match TT_Load_Glyph's full SCANTYPE switch. Only per-contour tags
    // truncate the mode to three bits; invalid global values disable dropout.
    let outline_flags = font_scan.map_or(manual_flags, |scan| {
        if !scan.enabled {
            return IGNORE_DROPOUTS;
        }
        match scan.scan_type {
            0 => INCLUDE_STUBS,
            1 => 0,
            4 => SMART_DROPOUTS | INCLUDE_STUBS,
            5 => SMART_DROPOUTS,
            _ => IGNORE_DROPOUTS,
        }
    }) | HIGH_PRECISION;
    // SAFETY: repr(C) Point matches FT_Vector's two signed longs. Arrays have
    // matching bounded lengths; ends are increasing indices into points, tags
    // encode only valid on/conic/cubic sequences, and every contour is closed.
    // C writes only the packed buffer and aligned arena for this call. It keeps
    // no pointers and uses local state; all allocations outlive the call.
    let error = unsafe {
        font_mono_render(
            points.as_ptr(),
            tags.as_ptr(),
            ends.as_ptr(),
            points.len() as u16,
            ends.len() as u16,
            output.width,
            output.height,
            packed.as_mut_ptr(),
            scratch.as_mut_ptr(),
            bytes,
            outline_flags,
        )
    };
    if error != 0 {
        return Err(fail(format!(
            "FreeType mono scan conversion failed ({error})"
        )));
    }
    for y in 0..output.height as usize {
        for x in 0..output.width as usize {
            output.pixels[y * output.width as usize + x] =
                u8::from(packed[y * pitch + x / 8] & (0x80 >> (x % 8)) != 0);
        }
    }
    Ok(output)
}
