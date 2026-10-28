//! Playdate source fonts: https://sdk.play.date/Inside%20Playdate.html#_fonts
//!
//! Cells share a baseline and have no per-glyph X offset. Following
//! https://github.com/ttencate/pdfontconv/blob/main/main.js, shift every cell
//! right by a common inset covering the leftmost actual ink and fold it into
//! shared negative tracking, so width plus tracking still equals each
//! finalized advance and interglyph spacing is unchanged. Like Bits'N'Picas'
//! Playdate exporter, shared negative tracking also retains right overhangs:
//! https://github.com/kreativekorp/bitsnpicas/blob/master/main/java/BitsNPicas/src/com/kreative/bitsnpicas/exporter/PlaydateBitmapFontExporter.java
use crate::{fail, renderer::RenderPipeline, Config, Error, GeneratedFont};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fmt::Write;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExportRequest {
    pub config: Config,
    pub pipeline: RenderPipeline,
    #[serde(default)]
    pub letter_spacing_px: f32,
}

/// Generate a standalone UTF-8 .fnt, including its base64 PNG image table.
/// No filesystem or browser dependencies; returned bytes belong to the caller.
pub fn export(data: &[u8], request: &ExportRequest) -> Result<Vec<u8>, Error> {
    if request.config.output_bits != 1 {
        return Err(fail("Playdate export requires monochrome (1-bit) output"));
    }
    validate_characters(&request.config.characters)?;
    #[cfg(feature = "candidate")]
    {
        let font = crate::candidate::generate_monochrome_font_with_pipeline(
            data,
            &request.config,
            request.pipeline,
            request.letter_spacing_px,
        )?;
        encode(&font)
    }
    #[cfg(not(feature = "candidate"))]
    {
        let _ = data;
        Err(fail("Playdate export requires the candidate Cargo feature"))
    }
}

fn validate_characters(characters: &str) -> Result<(), Error> {
    let count = characters.chars().collect::<BTreeSet<_>>().len();
    if count == 0 || count > 1024 {
        return Err(fail(
            "Playdate export requires 1 to 1024 distinct characters",
        ));
    }
    for ch in characters.chars() {
        if (ch as u32) < 0x20 || ch as u32 > 0x3ffff || ch.is_control() {
            return Err(fail(format!(
                "Playdate export cannot encode U+{:04X}",
                ch as u32
            )));
        }
    }
    Ok(())
}

/// Serialize finalized whole-pixel metrics without reapplying fitting or tracking.
pub fn encode(font: &GeneratedFont) -> Result<Vec<u8>, Error> {
    if font.config.output_bits != 1 {
        return Err(fail("Playdate export requires monochrome (1-bit) output"));
    }
    if !font.missing_codepoints.is_empty() {
        return Err(fail(format!(
            "Playdate export has missing glyphs: {:?}",
            font.missing_codepoints
        )));
    }
    let mut glyphs: Vec<_> = font.glyphs.iter().collect();
    glyphs.sort_by_key(|g| g.codepoint);
    let characters: String = glyphs
        .iter()
        .filter_map(|g| char::from_u32(g.codepoint))
        .collect();
    validate_characters(&characters)?;
    if characters.chars().count() != glyphs.len()
        || glyphs.windows(2).any(|g| g[0].codepoint == g[1].codepoint)
    {
        return Err(fail(
            "Playdate export requires unique Unicode scalar glyphs",
        ));
    }
    // Match surface.rs: baseline is ceil(ascent), line step is ceil(ascent -
    // descent + gap). The portable export subset uses byte-sized dimensions.
    let baseline = (i64::from(font.metrics.ascent_26_6) + 63).div_euclid(64);
    let height = ((i64::from(font.metrics.ascent_26_6) - i64::from(font.metrics.descent_26_6)
        + i64::from(font.metrics.line_gap_26_6)
        + 63)
        / 64)
        .max(1);
    if !(1..=255).contains(&height) || !(0..=height).contains(&baseline) {
        return Err(fail(
            "Playdate export requires a line height of 1..255 px and an in-cell baseline",
        ));
    }
    // The common left inset covers the leftmost actual ink over every
    // exported glyph. Scanner bounds may include transparent padding, and only
    // ink constrains the inset; discarding transparent padding changes no pixels.
    let mut min_ink_x = 0i64;
    let mut ink_rights = Vec::with_capacity(glyphs.len());
    for g in &glyphs {
        let advance = whole(g.advance_26_6)?;
        if !(0..=255).contains(&advance) {
            return Err(fail(format!(
                "Playdate advance for U+{:04X} must be 0..255 px",
                g.codepoint
            )));
        }
        if g.pixels.len() as u64 != u64::from(g.width) * u64::from(g.height)
            || g.pixels.iter().any(|p| *p > 1)
        {
            return Err(fail(format!(
                "Invalid Playdate bitmap for U+{:04X}",
                g.codepoint
            )));
        }
        let mut ink_right: Option<i64> = None;
        for (i, pixel) in g.pixels.iter().enumerate() {
            if *pixel == 0 {
                continue;
            }
            let x = i64::from(g.left) + (i % g.width as usize) as i64;
            let y = baseline + i64::from(g.top) + (i / g.width as usize) as i64;
            if y < 0 || y >= height {
                return Err(fail(format!(
                    "Playdate cannot preserve '{}' (U+{:04X}) within the selected line height",
                    char::from_u32(g.codepoint).unwrap(),
                    g.codepoint
                )));
            }
            min_ink_x = min_ink_x.min(x);
            ink_right = Some(ink_right.map_or(x + 1, |right| right.max(x + 1)));
        }
        ink_rights.push(ink_right);
    }
    let origin_x = -min_ink_x;
    let mut tracking = 0i64;
    for (g, ink_right) in glyphs.iter().zip(ink_rights) {
        let advance = whole(g.advance_26_6)?;
        // Translated ink extents keep width plus tracking equal to each
        // finalized advance, so the inset changes no pen steps. Glyphs without
        // ink keep the legacy 1px floor with no inset added.
        let bound = match ink_right {
            Some(right) => (right + origin_x).max(1),
            None => 1,
        };
        tracking = tracking.min(advance - bound);
    }
    if tracking < -128 {
        return Err(fail("Playdate export requires tracking within -128..0 px"));
    }
    let widths: Vec<_> = glyphs
        .iter()
        .map(|g| whole(g.advance_26_6).unwrap() - tracking)
        .collect();
    let width = *widths.iter().max().unwrap();
    if !(1..=255).contains(&width) {
        return Err(fail(
            "Playdate export requires cell widths within 1..255 px",
        ));
    }
    let cols = glyphs.len().min(16);
    let rows = glyphs.len().div_ceil(cols);
    let sheet_width = cols * width as usize;
    let sheet_height = rows * height as usize;
    // Keep the same 16M-texel allocation ceiling as the renderer.
    if sheet_width * sheet_height > 16_777_216 {
        return Err(fail("Playdate image table exceeds 16M pixels"));
    }
    let mut pixels = vec![0u8; sheet_width * sheet_height * 4];
    for (i, g) in glyphs.iter().enumerate() {
        for y in 0..g.height as usize {
            for x in 0..g.width as usize {
                if g.pixels[y * g.width as usize + x] == 0 {
                    continue;
                }
                let dx =
                    i % cols * width as usize + (origin_x + i64::from(g.left) + x as i64) as usize;
                let dy =
                    i / cols * height as usize + (baseline + i64::from(g.top) + y as i64) as usize;
                pixels[(dy * sheet_width + dx) * 4 + 3] = 255;
            }
        }
    }
    let mut png = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut png, sheet_width as u32, sheet_height as u32);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().map_err(|e| fail(e.to_string()))?;
        writer
            .write_image_data(&pixels)
            .map_err(|e| fail(e.to_string()))?;
    }
    let data = base64(&png);
    let mut out = format!("-- Playdate font\n--metrics={{\"baseline\":{baseline}}}\n");
    // Informational metadata ignored by Playdate: the common left inset
    // applied to every cell. Omitted when zero so those outputs stay identical.
    if origin_x != 0 {
        write!(out, "--origin_x={origin_x}\n").unwrap();
    }
    write!(
        out,
        "datalen={}\ndata={data}\nwidth={width}\nheight={height}\ntracking={tracking}\n",
        data.len()
    )
    .unwrap();
    let cps: BTreeSet<_> = glyphs.iter().map(|g| g.codepoint).collect();
    for (g, w) in glyphs.iter().zip(widths) {
        writeln!(out, "U+{:04X}\t{w}", g.codepoint).unwrap();
    }
    let mut pairs: Vec<_> = font.kerning.iter().collect();
    pairs.sort_by_key(|p| (p.left, p.right));
    if pairs
        .windows(2)
        .any(|p| (p[0].left, p[0].right) == (p[1].left, p[1].right))
    {
        return Err(fail("Duplicate Playdate kerning pair"));
    }
    for p in pairs {
        if !cps.contains(&p.left) || !cps.contains(&p.right) {
            return Err(fail("Playdate kerning refers to an unexported glyph"));
        }
        let adjustment = whole(p.adjustment_26_6)?;
        if !(-128..=127).contains(&adjustment) {
            return Err(fail("Playdate pair adjustments must be -128..127 px"));
        }
        if adjustment != 0 {
            writeln!(out, "U+{:04X}U+{:04X}\t{adjustment}", p.left, p.right).unwrap();
        }
    }
    Ok(out.into_bytes())
}

fn whole(value: i32) -> Result<i64, Error> {
    if value % 64 != 0 {
        return Err(fail("Playdate requires finalized whole-pixel metrics"));
    }
    Ok(i64::from(value / 64))
}

// RFC 4648 section 4; PNG bytes use the standard padded Base64 alphabet.
fn base64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut result = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let bits = (u32::from(chunk[0]) << 16)
            | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8)
            | u32::from(*chunk.get(2).unwrap_or(&0));
        result.push(ALPHABET[(bits >> 18) as usize] as char);
        result.push(ALPHABET[((bits >> 12) & 63) as usize] as char);
        result.push(if chunk.len() > 1 {
            ALPHABET[((bits >> 6) & 63) as usize] as char
        } else {
            '='
        });
        result.push(if chunk.len() > 2 {
            ALPHABET[(bits & 63) as usize] as char
        } else {
            '='
        });
    }
    result
}

#[cfg(test)]
mod tests {
    #[test]
    fn rfc4648_vectors() {
        for (input, expected) in [
            ("", ""),
            ("f", "Zg=="),
            ("fo", "Zm8="),
            ("foo", "Zm9v"),
            ("foob", "Zm9vYg=="),
        ] {
            assert_eq!(super::base64(input.as_bytes()), expected);
        }
    }
}
