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

pub(crate) struct AutoFitter<'a> {
    font: FontRef<'a>,
    hinting: HintingInstance,
}

impl<'a> AutoFitter<'a> {
    pub(crate) fn new(data: &'a [u8], config: &Config) -> Result<Option<Self>, Error> {
        let font = FontRef::new(data).map_err(|e| fail(format!("scan font: {e}")))?;
        if font.table_data(skrifa_scan::Tag::new(b"VARC")).is_some() {
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
                engine: Engine::Auto(None),
                target: Target::Mono,
            },
        )
        .map_err(|e| fail(format!("scan autohint setup: {e}")))?;
        Ok(Some(Self { font, hinting }))
    }

    pub(crate) fn draw(
        &self,
        glyph_id: u32,
        pen: &mut FittedPen,
    ) -> Result<skrifa_scan::outline::AdjustedMetrics, Error> {
        let glyph = self
            .font
            .outline_glyphs()
            .get(skrifa_scan::GlyphId::new(glyph_id))
            .ok_or_else(|| fail(format!("scan auto outline {glyph_id}")))?;
        glyph
            .draw(DrawSettings::hinted(&self.hinting, false), pen)
            .map_err(|e| fail(format!("scan auto outline {glyph_id}: {e}")))
    }
}

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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::probe::FittedPen;
    use std::{collections::BTreeMap, path::Path};

    /// Independent probe residuals for Roboto 16px (wght 400, wdth 100,
    /// automatic Mono): `(codepoint, lsb, rsb)` in 26.6 pixels.
    const ROBOTO16_RESIDUALS: [(u32, i32, i32); 95] = [
        (32, 0, 2),      //
        (33, 23, -23),   // !
        (34, 5, 10),     // "
        (35, -4, 43),    // #
        (36, -9, 3),     // $
        (37, -11, 20),   // %
        (38, -13, 18),   // &
        (39, -12, 7),    // '
        (40, 3, 1),      // (
        (41, -1, -9),    // )
        (42, -6, 9),     // *
        (43, -13, 10),   // +
        (44, 0, 17),     // ,
        (45, -37, 36),   // -
        (46, 8, -19),    // .
        (47, 0, 25),     // /
        (48, 0, 0),      // 0
        (49, 0, 0),      // 1
        (50, 0, 0),      // 2
        (51, 0, 0),      // 3
        (52, 0, 0),      // 4
        (53, 0, 0),      // 5
        (54, 0, 0),      // 6
        (55, 0, 0),      // 7
        (56, 0, 0),      // 8
        (57, 0, 0),      // 9
        (58, 3, -2),     // :
        (59, -9, 17),    // ;
        (60, -28, 20),   // <
        (61, 12, -5),    // =
        (62, 4, -9),     // >
        (63, -26, 24),   // ?
        (64, -6, 13),    // @
        (65, 7, 4),      // A
        (66, 21, 6),     // B
        (67, -4, 1),     // C
        (68, 21, 4),     // D
        (69, 21, -17),   // E
        (70, 21, -1),    // F
        (71, -3, -11),   // G
        (72, 21, -23),   // H
        (73, 28, -27),   // I
        (74, -37, -15),  // J
        (75, 21, -14),   // K
        (76, 21, 13),    // L
        (77, 21, -21),   // M
        (78, 21, -22),   // N
        (79, -4, 4),     // O
        (80, 21, 27),    // P
        (81, -9, 0),     // Q
        (82, 21, 14),    // R
        (83, -23, 24),   // S
        (84, 3, -1),     // T
        (85, 6, -3),     // U
        (86, 0, -12),    // V
        (87, 0, -13),    // W
        (88, 0, -2),     // X
        (89, 3, -4),     // Y
        (90, -20, 23),   // Z
        (91, 10, 22),    // [
        (92, 0, 27),     // \
        (93, -27, -14),  // ]
        (94, 0, 20),     // ^
        (95, -54, 55),   // _
        (96, 0, 3),      // `
        (97, -9, -11),   // a
        (98, 6, 18),     // b
        (99, -17, 29),   // c
        (100, -16, -9),  // d
        (101, -17, 27),  // e
        (102, -12, 23),  // f
        (103, -15, -6),  // g
        (104, 7, -4),    // h
        (105, 14, -14),  // i
        (106, 7, -15),   // j
        (107, 7, 29),    // k
        (108, 14, -14),  // l
        (109, 6, -5),    // m
        (110, 7, -6),    // n
        (111, -18, 19),  // o
        (112, 6, 17),    // p
        (113, -16, -14), // q
        (114, 7, 7),     // r
        (115, 16, 8),    // s
        (116, -24, -11), // t
        (117, 5, -6),    // u
        (118, 0, 16),    // v
        (119, 0, -2),    // w
        (120, 0, 4),     // x
        (121, 0, 27),    // y
        (122, -19, 30),  // z
        (123, 0, 12),    // {
        (124, 24, -23),  // |
        (125, -13, -11), // }
        (126, 2, -1),    // ~
    ];

    fn roboto() -> Vec<u8> {
        std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/Roboto.ttf")).unwrap()
    }

    fn config() -> Config {
        let mut axes = BTreeMap::new();
        axes.insert("wght".into(), 400.0);
        axes.insert("wdth".into(), 100.0);
        Config {
            size_px: 16.0,
            axes,
            hinting: crate::Hinting::Auto,
            ..Config::default()
        }
    }

    fn command_bits(command: &crate::probe::FittedCommand) -> (u8, [u32; 6]) {
        use crate::probe::FittedCommand::*;
        match *command {
            MoveTo(x, y) => (0, [x.to_bits(), y.to_bits(), 0, 0, 0, 0]),
            LineTo(x, y) => (1, [x.to_bits(), y.to_bits(), 0, 0, 0, 0]),
            QuadTo(x1, y1, x, y) => (
                2,
                [x1.to_bits(), y1.to_bits(), x.to_bits(), y.to_bits(), 0, 0],
            ),
            CurveTo(x1, y1, x2, y2, x, y) => (
                3,
                [
                    x1.to_bits(),
                    y1.to_bits(),
                    x2.to_bits(),
                    y2.to_bits(),
                    x.to_bits(),
                    y.to_bits(),
                ],
            ),
            Close => (4, [0, 0, 0, 0, 0, 0]),
        }
    }

    #[test]
    fn snapshot_matches_registry_and_frozen_residuals() {
        let data = roboto();
        let config = config();
        // `FontRef` is the shared read-fonts type in both crates, so
        // plain method calls would resolve through the snapshot's
        // imported provider trait. Fully qualified registry trait
        // calls keep the reference side on registry Skrifa.
        let location = |font: &skrifa::FontRef| {
            skrifa::MetadataProvider::axes(font).location(
                config
                    .axes
                    .iter()
                    .map(|(tag, value)| (tag.as_str(), *value)),
            )
        };
        let registry = skrifa::FontRef::new(&data).unwrap();
        let registry_location = location(&registry);
        let registry_hinting = skrifa::outline::HintingInstance::new(
            &skrifa::MetadataProvider::outline_glyphs(&registry),
            skrifa::instance::Size::new(config.size_px),
            &registry_location,
            skrifa::outline::HintingOptions {
                engine: skrifa::outline::Engine::Auto(None),
                target: skrifa::outline::Target::Mono,
            },
        )
        .unwrap();
        let fitter = AutoFitter::new(&data, &config).unwrap().unwrap();
        let mut seen = 0;
        for (codepoint, want_lsb, want_rsb) in ROBOTO16_RESIDUALS {
            let ch = char::from_u32(codepoint).unwrap();
            let gid = registry.charmap().map(ch).unwrap().to_u32();
            let outline = skrifa::MetadataProvider::outline_glyphs(&registry)
                .get(skrifa::GlyphId::new(gid))
                .unwrap();
            let mut registry_pen = FittedPen::default();
            let registry_metrics = outline
                .draw(
                    skrifa::outline::DrawSettings::hinted(&registry_hinting, false),
                    &mut registry_pen,
                )
                .unwrap();
            let mut scan_pen = FittedPen::default();
            let scan_metrics = fitter.draw(gid, &mut scan_pen).unwrap();
            let scan_bits: Vec<_> = scan_pen.into_commands().iter().map(command_bits).collect();
            let registry_bits: Vec<_> = registry_pen
                .into_commands()
                .iter()
                .map(command_bits)
                .collect();
            assert_eq!(
                scan_bits, registry_bits,
                "commands diverge at U+{codepoint:04X}"
            );
            assert_eq!(scan_metrics.has_overlaps, registry_metrics.has_overlaps);
            assert_eq!(
                scan_metrics.lsb.map(f32::to_bits),
                registry_metrics.lsb.map(f32::to_bits)
            );
            assert_eq!(
                scan_metrics.advance_width.map(f32::to_bits),
                registry_metrics.advance_width.map(f32::to_bits)
            );
            assert_eq!(
                scan_metrics.autohint_deltas_26_6,
                Some([want_lsb, want_rsb]),
                "residuals diverge at U+{codepoint:04X}"
            );
            seen += 1;
        }
        assert_eq!(seen, ROBOTO16_RESIDUALS.len());
        assert_eq!(ROBOTO16_RESIDUALS.len(), 95);
    }
}
