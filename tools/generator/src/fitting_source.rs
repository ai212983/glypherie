//! Source feature geometry in font units, scaled once in f64.
//!
//! Hobby section 6 maps source features to fitted controls. Drawing in font
//! units avoids the FreeType scaled 26.6 path before feature recognition.
//! The HarfBuzz path holds floating-point variation deltas without the
//! FreeType unscaled integer rounding (`Fixed::to_i32` on gvar deltas in
//! `skrifa::outline::glyf`); the pen keeps continuous coordinates and the
//! single f64 scale below preserves them.

use crate::{fail, probe::FittedPen, Config, Error};
use skrifa::{
    instance::Size,
    outline::{pen::PathStyle, DrawSettings},
    FontRef, MetadataProvider,
};

pub use crate::diagonal_fitting::geometry::{Parsed as SourceOutline, Segment as SourceSegment};

pub fn draw(data: &[u8], config: &Config, glyph_id: u32) -> Result<SourceOutline, Error> {
    let font = FontRef::new(data).map_err(|e| fail(format!("source font: {e}")))?;
    for (tag, value) in &config.axes {
        if tag.len() != 4 || !tag.is_ascii() {
            return Err(fail("source axis tags must contain four ASCII bytes"));
        }
        let axis = font
            .axes()
            .iter()
            .find(|a| a.tag().to_string() == *tag)
            .ok_or_else(|| fail(format!("unsupported source axis {tag}")))?;
        if !value.is_finite() || *value < axis.min_value() || *value > axis.max_value() {
            return Err(fail(format!("source axis {tag} exceeds its font bounds")));
        }
    }
    let location = font
        .axes()
        .location(config.axes.iter().map(|(t, v)| (t.as_str(), *v)));
    let units = font.metrics(Size::unscaled(), &location).units_per_em;
    if units == 0 || !config.size_px.is_finite() || config.size_px <= 0.0 {
        return Err(fail(
            "source geometry requires positive size and units per em",
        ));
    }
    let outlines = font.outline_glyphs();
    let glyph = outlines
        .get(skrifa::GlyphId::new(glyph_id))
        .ok_or_else(|| fail("missing source glyph"))?;
    let mut pen = FittedPen::default();
    glyph
        .draw(
            DrawSettings::unhinted(Size::unscaled(), &location)
                .with_path_style(PathStyle::HarfBuzz),
            &mut pen,
        )
        .map_err(|e| fail(format!("source outline: {e}")))?;
    let mut parsed = crate::diagonal_fitting::geometry::parse_commands(pen.commands())
        .map_err(|()| fail("malformed source outline"))?;
    for point in parsed.oncurve.iter_mut().chain(parsed.offcurve.iter_mut()) {
        for coordinate in point {
            *coordinate = *coordinate * f64::from(config.size_px) / f64::from(units);
        }
    }
    Ok(parsed)
}
