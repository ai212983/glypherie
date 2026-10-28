//! Source identity and metrics without rendered output.
//!
//! Advances are variation-aware linear metrics from the production
//! Skrifa snapshot (`GlyphMetrics::advance_width`), rounded once with
//! the configured `fixed` rule, exactly as legacy generation computes
//! them. Kerning comes from the HarfRust scalar/pair shaping in
//! `spacing`. No outline is rasterized and no bitmap or coverage is
//! allocated here; fitted rendering remains the caller's one raster.

use crate::{fail, fixed, spacing, Config, Error, FontMetrics, KerningPair};
use skrifa_baseline::{instance::Size, MetadataProvider};
use std::{cell::OnceCell, collections::BTreeSet};

/// Immutable owned font bytes with a lazily computed byte identity.
/// Rendering validates each request; exact completed diagonal fits may be reused.
/// https://doc.rust-lang.org/std/cell/struct.OnceCell.html
pub struct PreparedFont {
    data: Vec<u8>,
    pub(crate) identity: OnceCell<String>,
    #[cfg(feature = "candidate")]
    pub(crate) diagonal_fits: std::cell::RefCell<crate::diagonal_fitting::reuse::FitCache>,
}

impl PreparedFont {
    pub fn new(data: Vec<u8>) -> Self {
        Self {
            data,
            identity: OnceCell::new(),
            #[cfg(feature = "candidate")]
            diagonal_fits: Default::default(),
        }
    }

    pub fn as_bytes(&self) -> &[u8] {
        &self.data
    }
}

/// One repertoire scalar resolved to the glyph actually drawn, with
/// its rounded source advance. Identity/metrics only; no bitmap.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct SourceGlyph {
    pub codepoint: u32,
    pub glyph_id: u32,
    pub advance_26_6: i32,
}

/// Source metrics for a repertoire: global line metrics, per-glyph
/// source advances, missing codepoints and source kerning.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct SourceFont {
    pub source_sha256: String,
    pub metrics: FontMetrics,
    pub glyphs: Vec<SourceGlyph>,
    pub missing_codepoints: Vec<u32>,
    pub kerning: Vec<KerningPair>,
}

struct Identities {
    source_sha256: String,
    metrics: FontMetrics,
    glyphs: Vec<SourceGlyph>,
    missing_codepoints: Vec<u32>,
    resolved: Vec<spacing::ResolvedScalar>,
}

fn prepare_identities(
    session: &crate::reference::CaptureSession<'_>,
    config: &Config,
) -> Result<Identities, Error> {
    let data = session.data;
    crate::validate_config(config)?;
    let font = crate::open_font(data)?;
    crate::validate_axes(&font, &config.axes)?;
    let location = font.axes().location(
        config
            .axes
            .iter()
            .map(|(tag, value)| (tag.as_str(), *value)),
    );
    let size = Size::new(config.size_px);
    let metrics = font.metrics(size, &location);
    if metrics.units_per_em == 0 {
        return Err(fail("font has invalid units per em"));
    }
    let advances = font.glyph_metrics(size, &location);
    let outlines = font.outline_glyphs();
    let mut missing_codepoints = Vec::new();
    let mut present = Vec::new();
    for ch in config.characters.chars().collect::<BTreeSet<_>>() {
        // Same missing policy as generation: unassigned scalars may be
        // skipped, controls/text-run requests stay capability errors.
        spacing::validate_request(ch)?;
        if font.charmap().map(ch).is_none_or(|g| g.to_u32() == 0) {
            if config.missing_glyphs == crate::MissingGlyphs::Error {
                return Err(fail(format!("missing glyph U+{:04X}", ch as u32)));
            }
            missing_codepoints.push(ch as u32);
            continue;
        }
        spacing::validate_character(ch)?;
        present.push(ch);
    }
    let resolved = spacing::resolve_scalars(data, &config.axes, config.kerning, &present)?;
    let mut glyphs = Vec::with_capacity(resolved.len());
    for scalar in &resolved {
        let gid = skrifa_baseline::GlyphId::new(scalar.glyph_id);
        // Existence only: drawing the outline is the fitted renderer's
        // job, so an invalid outline still fails there, not silently here.
        outlines
            .get(gid)
            .ok_or_else(|| fail(format!("missing outline U+{:04X}", scalar.codepoint)))?;
        let advance = advances
            .advance_width(gid)
            .ok_or_else(|| fail(format!("missing advance U+{:04X}", scalar.codepoint)))?;
        glyphs.push(SourceGlyph {
            codepoint: scalar.codepoint,
            glyph_id: scalar.glyph_id,
            advance_26_6: fixed(advance, config.metric_rounding),
        });
    }
    if glyphs.is_empty() {
        return Err(fail("repertoire contains no available glyphs"));
    }
    Ok(Identities {
        source_sha256: session.source_sha256().to_owned(),
        metrics: FontMetrics {
            ascent_26_6: fixed(metrics.ascent, config.metric_rounding),
            descent_26_6: fixed(metrics.descent, config.metric_rounding),
            line_gap_26_6: fixed(metrics.leading, config.metric_rounding),
        },
        glyphs,
        missing_codepoints,
        resolved,
    })
}

/// Validate and resolve a repertoire to source advances, global
/// metrics, missing glyphs and kerning, with no rasterization.
#[cfg(any(feature = "candidate", test))]
pub(crate) fn prepare_source(data: &[u8], config: &Config) -> Result<SourceFont, Error> {
    prepare_source_in_session(&crate::reference::CaptureSession::new(data), config)
}

pub(crate) fn prepare_source_in_session(
    session: &crate::reference::CaptureSession<'_>,
    config: &Config,
) -> Result<SourceFont, Error> {
    let data = session.data;
    let identities = prepare_identities(session, config)?;
    let kerning = spacing::extract(data, config, &identities.resolved)?;
    Ok(SourceFont {
        source_sha256: identities.source_sha256,
        metrics: identities.metrics,
        glyphs: identities.glyphs,
        missing_codepoints: identities.missing_codepoints,
        kerning,
    })
}

/// Test-only logical raster accounting. A logical call rasterizes one
/// glyph's bitmap once; internal oversampling tiles inside a raster
/// are not separate calls. Production builds carry no counters.
#[cfg(test)]
pub(crate) mod raster_counter {
    use std::cell::Cell;

    thread_local! {
        static LOGICAL_RASTERS: Cell<usize> = const { Cell::new(0) };
        static SOURCE_GEOMETRY_DRAWS: Cell<usize> = const { Cell::new(0) };
        static FONT_IDENTITY_HASHES: Cell<usize> = const { Cell::new(0) };
    }

    pub(crate) fn reset() {
        LOGICAL_RASTERS.with(|c| c.set(0));
        SOURCE_GEOMETRY_DRAWS.with(|c| c.set(0));
        FONT_IDENTITY_HASHES.with(|c| c.set(0));
    }

    pub(crate) fn logical_rasters() -> usize {
        LOGICAL_RASTERS.with(|c| c.get())
    }

    pub(crate) fn source_geometry_draws() -> usize {
        SOURCE_GEOMETRY_DRAWS.with(|c| c.get())
    }

    pub(crate) fn record_logical(count: usize) {
        LOGICAL_RASTERS.with(|c| c.set(c.get() + count));
    }

    pub(crate) fn record_source_geometry(count: usize) {
        SOURCE_GEOMETRY_DRAWS.with(|c| c.set(c.get() + count));
    }

    pub(crate) fn font_identity_hashes() -> usize {
        FONT_IDENTITY_HASHES.with(|c| c.get())
    }

    pub(crate) fn record_font_identity_hash() {
        FONT_IDENTITY_HASHES.with(|c| c.set(c.get() + 1));
    }
}

#[cfg(test)]
mod tests {
    use super::{prepare_source, raster_counter};
    use crate::{Config, MissingGlyphs};
    use std::path::Path;

    fn roboto() -> Vec<u8> {
        std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf")).unwrap()
    }

    #[test]
    fn source_preparation_rasterizes_nothing() {
        let data = roboto();
        let config = Config {
            size_px: 14.0,
            characters: "hello world".into(),
            ..Config::default()
        };
        raster_counter::reset();
        let source = prepare_source(&data, &config).unwrap();
        // Unique repertoire of "hello world": space, d, e, h, l, o, r, w.
        assert_eq!(source.glyphs.len(), 8);
        assert!(source
            .glyphs
            .iter()
            .all(|g| g.advance_26_6 != 0 || g.codepoint == b' ' as u32));
        assert_eq!(
            raster_counter::logical_rasters(),
            0,
            "source preparation must not rasterize"
        );
        assert_eq!(raster_counter::source_geometry_draws(), 0);
    }

    #[test]
    fn source_preparation_preserves_missing_policy() {
        let data = roboto();
        let mut config = Config {
            size_px: 14.0,
            characters: "A\u{0378}".into(),
            ..Config::default()
        };
        assert!(prepare_source(&data, &config).is_err());
        config.missing_glyphs = MissingGlyphs::Skip;
        let source = prepare_source(&data, &config).unwrap();
        assert_eq!(source.missing_codepoints, vec![0x0378]);
        assert_eq!(source.glyphs.len(), 1);
    }
}
