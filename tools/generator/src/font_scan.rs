//! Candidate-only access to executed TrueType scan state. The separate pinned
//! Skrifa snapshot adds metadata without changing fitting; registry Skrifa stays
//! independent for manual rendering, reference captures and Gray.
use crate::{fail, probe::FittedPen, reference::FontScanState, Config, Error};
use skrifa_scan::{
    instance::Size,
    outline::{DrawSettings, Engine, HintingInstance, HintingOptions, Target},
    FontRef, MetadataProvider,
};

pub const SOURCE_SHA256: &str = env!("SKRIFA_SCAN_SHA256");

pub(crate) struct FontScanFitter<'a> {
    font: FontRef<'a>,
    hinting: HintingInstance,
}

impl<'a> FontScanFitter<'a> {
    pub(crate) fn is_enabled(&self) -> bool {
        self.hinting.is_enabled()
    }
    pub(crate) fn new(data: &'a [u8], config: &Config) -> Result<Option<Self>, Error> {
        let font = FontRef::new(data).map_err(|e| fail(format!("scan font: {e}")))?;
        if font.table_data(skrifa_scan::Tag::new(b"glyf")).is_none()
            || font.table_data(skrifa_scan::Tag::new(b"VARC")).is_some()
        {
            return Ok(None);
        }
        let location = font.axes().location(
            config
                .axes
                .iter()
                .map(|(tag, value)| (tag.as_str(), *value)),
        );
        let hinting = HintingInstance::new(
            &font.outline_glyphs(),
            Size::new(config.size_px),
            &location,
            HintingOptions {
                engine: Engine::Interpreter,
                target: Target::Mono,
            },
        )
        .map_err(|e| fail(format!("scan hinting setup: {e}")))?;
        Ok(Some(Self { font, hinting }))
    }

    pub(crate) fn draw(
        &self,
        glyph_id: u32,
        pen: &mut FittedPen,
    ) -> Result<(skrifa::outline::AdjustedMetrics, Option<FontScanState>), Error> {
        let glyph = self
            .font
            .outline_glyphs()
            .get(skrifa_scan::GlyphId::new(glyph_id))
            .ok_or_else(|| fail(format!("missing scan outline {glyph_id}")))?;
        let metrics = glyph
            .draw(DrawSettings::hinted(&self.hinting, false), pen)
            .map_err(|e| fail(format!("scan outline {glyph_id}: {e}")))?;
        let scan = metrics.scan_conversion.map(|scan| FontScanState {
            source_sha256: SOURCE_SHA256.into(),
            enabled: scan.control.enabled,
            scan_type: scan.control.scan_type,
            contour_modes: scan.contour_modes,
            hinting_axes: scan.hinting_axes,
        });
        Ok((
            skrifa::outline::AdjustedMetrics {
                has_overlaps: metrics.has_overlaps,
                lsb: metrics.lsb,
                advance_width: metrics.advance_width,
            },
            scan,
        ))
    }
}
