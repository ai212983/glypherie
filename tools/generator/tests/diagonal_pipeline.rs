#![cfg(feature = "candidate")]
//! Opt-in reviewed shape fitting: default-off serde, validation,
//! disabled identity, reference-config invariance and export/surface checks.
use font_generator::{
    candidate,
    evaluation::evaluate,
    mono,
    reference::{reference, RasterPolicy, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    surface::{self, HAlign, TextRenderRequest, WrapMode},
    Config, Hinting, MissingGlyphs, MonoDropoutMode, MonoRasterSettings,
};

fn font() -> Vec<u8> {
    std::fs::read(format!(
        "{}/../../fonts/Roboto.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap()
}

fn load(name: &str) -> Vec<u8> {
    std::fs::read(format!("{}/../../fonts/{name}", env!("CARGO_MANIFEST_DIR"))).unwrap()
}

fn capture_request(
    fitting: StemFittingStrategy,
    characters: &str,
    mono_raster: MonoRasterSettings,
) -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: StemFittingStrategy::extension(Some(fitting)).into(),
        settings: Config {
            characters: characters.into(),
            size_px: 16.0,
            output_bits: 1,
            hinting: fitting.hinting(),
            mono_raster,
            ..Config::default()
        },
    }
}

fn pipeline(
    fitting: StemFittingStrategy,
    rasterization: Rasterization,
    diagonal: bool,
) -> RenderPipeline {
    RenderPipeline {
        fitting,
        rasterization,
        diagonal_fitting: diagonal,
    }
}

#[test]
fn diagonal_defaults_off_and_keeps_old_json() {
    assert!(!RenderPipeline::default().diagonal_fitting);
    let legacy: RenderPipeline =
        serde_json::from_str(r#"{"fitting":"upstream_mono","rasterization":"free_type_mono"}"#)
            .unwrap();
    assert!(!legacy.diagonal_fitting);
    let serialized = serde_json::to_string(&RenderPipeline::default()).unwrap();
    assert!(!serialized.contains("diagonal"));
    let on = pipeline(
        StemFittingStrategy::UpstreamMono,
        Rasterization::FreeTypeMono,
        true,
    );
    let round: RenderPipeline = serde_json::from_str(&serde_json::to_string(&on).unwrap()).unwrap();
    assert!(round.diagonal_fitting);
}

#[test]
fn local_curve_fitting_reaches_roboto_flex_without_changing_metrics_or_native_y() {
    let data = load("RobotoFlex.ttf");
    let fitting = StemFittingStrategy::FontHintsAuto;
    let request = capture_request(
        fitting,
        "s",
        MonoRasterSettings {
            font_instructions: true,
            include_stubs: true,
            ..Default::default()
        },
    );
    let make = |on| {
        candidate::render_with_pipeline(
            &data,
            &request,
            pipeline(fitting, Rasterization::FreeTypeMonoTerminals, on),
        )
        .unwrap()
    };
    let off = make(false);
    let on = make(true);
    let (old, new) = (&off.records[0], &on.records[0]);
    assert_eq!(old.glyph_id, new.glyph_id);
    assert_eq!(old.advance_26_6, new.advance_26_6);
    assert_eq!(old.hinted_advance_width, new.hinted_advance_width);
    assert_eq!(old.selected_engine, new.selected_engine);
    assert_eq!(old.font_scan, new.font_scan);
    let capture = new
        .diagonal_fitting
        .as_ref()
        .expect("interior curve is supported");
    assert_eq!(capture.reason, "curve:fitted");
    assert_eq!(capture.upstream_commands, old.fitted_commands);
    assert_ne!(old.fitted_commands, new.fitted_commands);
    assert_ne!(
        old.pixels, new.pixels,
        "check final delivery as well as outline activity"
    );
    for (a, b) in old.fitted_commands.iter().zip(&new.fitted_commands) {
        let ys = |c: &font_generator::probe::FittedCommand| match c {
            font_generator::probe::FittedCommand::MoveTo(_, y)
            | font_generator::probe::FittedCommand::LineTo(_, y) => vec![y.to_bits()],
            font_generator::probe::FittedCommand::QuadTo(_, y1, _, y) => {
                vec![y1.to_bits(), y.to_bits()]
            }
            font_generator::probe::FittedCommand::CurveTo(_, y1, _, y2, _, y) => {
                vec![y1.to_bits(), y2.to_bits(), y.to_bits()]
            }
            font_generator::probe::FittedCommand::Close => vec![],
        };
        assert_eq!(ys(a), ys(b));
    }
}

#[test]
fn diagonal_sequence_preserves_local_reference_heights_in_roboto_flex_k() {
    let data = load("RobotoFlex.ttf");
    let fitting = StemFittingStrategy::FontHintsAuto;
    let request = capture_request(
        fitting,
        "k",
        MonoRasterSettings {
            font_instructions: true,
            include_stubs: true,
            ..Default::default()
        },
    );
    let render = |enabled| {
        candidate::render_with_pipeline(
            &data,
            &request,
            pipeline(fitting, Rasterization::FreeTypeMonoTerminals, enabled),
        )
        .unwrap()
    };
    let off = render(false);
    let on = render(true);
    let (up, got) = (&off.records[0], &on.records[0]);
    assert_eq!(up.advance_26_6, got.advance_26_6);
    assert_eq!(up.hinted_advance_width, got.hinted_advance_width);
    let capture = got
        .diagonal_fitting
        .as_ref()
        .expect("width correction stays active");
    assert_eq!(capture.reason, "terminal:fitted");
    let raw = font_generator::fitting_source::draw(&data, &request.settings, up.glyph_id).unwrap();
    let oncurve = |cmds: &[font_generator::probe::FittedCommand]| {
        cmds.iter()
            .filter_map(|c| {
                use font_generator::probe::FittedCommand::*;
                match *c {
                    MoveTo(_, y)
                    | LineTo(_, y)
                    | QuadTo(_, _, _, y)
                    | CurveTo(_, _, _, _, _, y) => Some(y),
                    Close => None,
                }
            })
            .collect::<Vec<_>>()
    };
    let up_y = oncurve(&up.fitted_commands);
    let got_y = oncurve(&got.fitted_commands);
    let mut held = 0;
    for segment in raw.contours.iter().flatten() {
        if segment.is_line() {
            let (a, b) = segment.endpoints();
            if raw.oncurve[a][0] != raw.oncurve[b][0]
                && raw.oncurve[a][1] == raw.oncurve[b][1]
                && up_y[a] == up_y[b]
            {
                for v in [a, b] {
                    assert_eq!(got_y[v].to_bits(), up_y[v].to_bits());
                }
                held += 1;
            }
        }
    }
    assert!(
        held >= 4,
        "baseline, ascender, and local arm reference edges are present"
    );
}

#[test]
fn diagonal_validates_only_supported_stages() {
    let mono = || Config {
        size_px: 16.0,
        output_bits: 1,
        hinting: Hinting::Auto,
        ..Config::default()
    };
    for fitting in [
        StemFittingStrategy::FontHintsAuto,
        StemFittingStrategy::UpstreamMono,
    ] {
        for rasterization in [
            Rasterization::FreeTypeMono,
            Rasterization::FreeTypeMonoTerminals,
        ] {
            pipeline(fitting, rasterization, true)
                .validate(&mono())
                .unwrap();
        }
    }
    // Unsupported strategies fail explicitly, independent of native hints.
    for fitting in [
        StemFittingStrategy::FontHintsFirst,
        StemFittingStrategy::SourceRelative,
    ] {
        assert!(pipeline(fitting, Rasterization::FreeTypeMono, true)
            .validate(&mono())
            .is_err());
    }
    assert!(pipeline(
        StemFittingStrategy::UpstreamMono,
        Rasterization::Coverage,
        true
    )
    .validate(&mono())
    .is_err());
    let gray = Config {
        output_bits: 3,
        ..mono()
    };
    assert!(pipeline(
        StemFittingStrategy::UpstreamMono,
        Rasterization::FreeTypeMono,
        true
    )
    .validate(&gray)
    .is_err());
    // Disabled pipelines keep every established combination valid.
    pipeline(
        StemFittingStrategy::UpstreamMono,
        Rasterization::Coverage,
        false,
    )
    .validate(&gray)
    .unwrap();
}

#[test]
fn disabled_pipeline_is_identity_with_rasterization() {
    let data = font();
    for fitting in [
        StemFittingStrategy::FontHintsAuto,
        StemFittingStrategy::UpstreamMono,
    ] {
        for rasterization in [
            Rasterization::FreeTypeMono,
            Rasterization::FreeTypeMonoTerminals,
        ] {
            let request = ReferenceRequest {
                profile: "mono_1bit".into(),
                extensions: StemFittingStrategy::extension(Some(fitting)).into(),
                settings: Config {
                    characters: "AVkxzv".into(),
                    size_px: 16.0,
                    output_bits: 1,
                    hinting: fitting.hinting(),
                    ..Config::default()
                },
            };
            let direct =
                candidate::render_with_rasterization(&data, &request, rasterization).unwrap();
            let routed = candidate::render_with_pipeline(
                &data,
                &request,
                pipeline(fitting, rasterization, false),
            )
            .unwrap();
            assert_eq!(direct.records.len(), routed.records.len());
            for (a, b) in direct.records.iter().zip(&routed.records) {
                assert_eq!(a.codepoint, b.codepoint);
                assert_eq!(a.fitted_commands, b.fitted_commands);
                assert_eq!(a.pixels, b.pixels);
                assert_eq!(a.coverage, b.coverage);
                assert!(b.diagonal_fitting.is_none());
            }
        }
    }
}

#[test]
fn enabled_opt_in_preserves_reference_config_and_metrics() {
    let data = font();
    for fitting in [
        StemFittingStrategy::FontHintsAuto,
        StemFittingStrategy::UpstreamMono,
    ] {
        let request = ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: StemFittingStrategy::extension(Some(fitting)).into(),
            settings: Config {
                characters: "AVkxyWzv".into(),
                size_px: 16.0,
                output_bits: 1,
                hinting: fitting.hinting(),
                ..Config::default()
            },
        };
        let off = candidate::render_with_pipeline(
            &data,
            &request,
            pipeline(fitting, Rasterization::FreeTypeMono, false),
        )
        .unwrap();
        let on = candidate::render_with_pipeline(
            &data,
            &request,
            pipeline(fitting, Rasterization::FreeTypeMono, true),
        )
        .unwrap();
        // Reference config invariance: same font, size, axes and profile.
        assert_eq!(on.source_sha256, off.source_sha256);
        assert_eq!(on.size_px, off.size_px);
        assert_eq!(on.axes, off.axes);
        assert_eq!(on.profile, off.profile);
        assert_eq!(on.records.len(), off.records.len());
        let mut applied = 0;
        for (a, b) in off.records.iter().zip(&on.records) {
            assert_eq!(a.codepoint, b.codepoint);
            assert_eq!(a.glyph_id, b.glyph_id);
            // Native text-layout advances remain upstream.
            assert_eq!(a.advance_26_6, b.advance_26_6);
            assert_eq!(a.hinted_advance_width, b.hinted_advance_width);
            assert_eq!(a.hinted_lsb, b.hinted_lsb);
            assert_eq!(a.selected_engine, b.selected_engine);
            // Earlier width/selective captures stay valid against the
            // pre-diagonal outline; they legitimately coexist here.
            if let Some(diagonal) = &b.diagonal_fitting {
                applied += 1;
                assert!(!diagonal.upstream_commands.is_empty());
                assert!(!diagonal.reason.is_empty());
                assert_eq!(diagonal.size_px, 16.0);
                assert!(b.source_commands.is_some());
                let stored: font_generator::diagonal_fitting::Reference =
                    serde_json::from_value(diagonal.reference.clone()).unwrap();
                assert!(!stored.anchors.is_empty());
            } else {
                assert_eq!(a.fitted_commands, b.fitted_commands);
                assert_eq!(a.pixels, b.pixels);
            }
        }
        if applied > 0 {
            assert!(on.implementation.contains(":diagonal-shape-04"));
        }
    }
}

#[test]
fn export_and_surface_share_pipeline_metrics() {
    let data = font();
    let config = Config {
        characters: "AVkxzvW".into(),
        size_px: 16.0,
        output_bits: 1,
        hinting: Hinting::Auto,
        ..Config::default()
    };
    let off = candidate::generate_monochrome_font_with_pipeline(
        &data,
        &config,
        pipeline(
            StemFittingStrategy::UpstreamMono,
            Rasterization::FreeTypeMono,
            false,
        ),
        0.0,
    )
    .unwrap();
    let on = candidate::generate_monochrome_font_with_pipeline(
        &data,
        &config,
        pipeline(
            StemFittingStrategy::UpstreamMono,
            Rasterization::FreeTypeMono,
            true,
        ),
        0.0,
    )
    .unwrap();
    assert_eq!(off.glyphs.len(), on.glyphs.len());
    for (a, b) in off.glyphs.iter().zip(&on.glyphs) {
        assert_eq!(a.codepoint, b.codepoint);
        assert_eq!(a.advance_26_6, b.advance_26_6);
    }
    let text = TextRenderRequest {
        config: Config {
            size_px: 16.0,
            output_bits: 1,
            hinting: Hinting::Auto,
            ..Config::default()
        },
        text: "AV kxzv".into(),
        width: 200,
        height: 60,
        wrap: WrapMode::Word,
        align: HAlign::Left,
        foreground: [0, 0, 0, 255],
        background: [255, 255, 255, 255],
        palette: None,
    };
    let off_surface = surface::render_text_with_pipeline(
        &data,
        &text,
        pipeline(
            StemFittingStrategy::UpstreamMono,
            Rasterization::FreeTypeMono,
            false,
        ),
    )
    .unwrap();
    let on_surface = surface::render_text_with_pipeline(
        &data,
        &text,
        pipeline(
            StemFittingStrategy::UpstreamMono,
            Rasterization::FreeTypeMono,
            true,
        ),
    )
    .unwrap();
    assert_eq!(off_surface.lines, on_surface.lines);
}

#[test]
fn pipeline_rejects_extension_mismatch_before_capture() {
    let data = font();
    let mut request = capture_request(
        StemFittingStrategy::FontHintsFirst,
        "AV",
        MonoRasterSettings::default(),
    );
    request.settings.hinting = Hinting::AutoFallback;
    for diagonal in [false, true] {
        assert!(
            candidate::render_with_pipeline(
                &data,
                &request,
                pipeline(
                    StemFittingStrategy::UpstreamMono,
                    Rasterization::FreeTypeMono,
                    diagonal
                ),
            )
            .is_err(),
            "fitting/extensions mismatch must fail, diagonal={diagonal}"
        );
    }
}

#[test]
fn applied_records_keep_their_own_scan_policy() {
    let terminal_scan = MonoRasterSettings {
        dropout: MonoDropoutMode::Smart,
        include_stubs: true,
        font_instructions: true,
    };
    for name in ["Roboto.ttf", "Literata.ttf"] {
        let data = load(name);
        for fitting in [
            StemFittingStrategy::FontHintsAuto,
            StemFittingStrategy::UpstreamMono,
        ] {
            for (rasterization, scan) in [
                (Rasterization::FreeTypeMono, MonoRasterSettings::default()),
                (Rasterization::FreeTypeMonoTerminals, terminal_scan),
            ] {
                let request = capture_request(fitting, "AVyWkzxv", scan);
                let report = candidate::render_with_pipeline(
                    &data,
                    &request,
                    pipeline(fitting, rasterization, true),
                )
                .unwrap();
                for record in &report.records {
                    let Some(diagonal) = &record.diagonal_fitting else {
                        continue;
                    };
                    let expected_axes = record
                        .selective_fitting
                        .as_ref()
                        .map(|capture| capture.native_axes)
                        .unwrap_or(if record.selected_engine == "auto" {
                            [false, false]
                        } else {
                            [true, true]
                        });
                    assert_eq!(
                        diagonal.native_axes, expected_axes,
                        "{name} U+{:04X}",
                        record.codepoint
                    );
                    match record.raster_policy {
                        // Selective-native records keep FreeTypeMono with
                        // their executed scan state, never the requested
                        // terminal rasterization.
                        RasterPolicy::FreeTypeMono => {
                            let again = mono::rasterize_with_scan_state(
                                &record.fitted_commands,
                                &request.settings,
                                record.font_scan.as_ref(),
                            )
                            .unwrap();
                            assert_eq!(
                                (again.left, again.top, again.width, again.height),
                                (record.left, record.top, record.width, record.height),
                                "{name} U+{:04X}",
                                record.codepoint
                            );
                            assert_eq!(again.pixels, record.pixels);
                            assert_eq!(again.coverage, record.coverage);
                        }
                        RasterPolicy::FreeTypeMonoTerminals => {
                            assert!(record.source_commands.is_some());
                        }
                        policy => panic!(
                            "diagonal applied on unexpected policy {policy:?} for {name} U+{:04X}",
                            record.codepoint
                        ),
                    }
                }
            }
        }
    }
}

#[test]
fn evaluator_replays_diagonal_records() {
    let data = font();
    for fitting in [
        StemFittingStrategy::FontHintsAuto,
        StemFittingStrategy::UpstreamMono,
    ] {
        for scan in [
            MonoRasterSettings::default(),
            MonoRasterSettings {
                dropout: MonoDropoutMode::Smart,
                include_stubs: true,
                font_instructions: true,
            },
        ] {
            let request = capture_request(fitting, "AVyWkzxv", scan);
            let mut unhinted = request.settings.clone();
            unhinted.hinting = Hinting::None;
            unhinted.mono_raster = MonoRasterSettings::default();
            let source = reference(
                &data,
                &ReferenceRequest {
                    profile: "mono_1bit".into(),
                    extensions: "none".into(),
                    settings: unhinted,
                },
            )
            .unwrap();
            // Independent upstream needs explicit hinting and default scan
            // settings; Roboto resolves wholly automatic, so forced Auto
            // matches the fallback draw.
            let upstream = reference(
                &data,
                &ReferenceRequest {
                    profile: "mono_1bit".into(),
                    extensions: "none".into(),
                    settings: Config {
                        hinting: Hinting::Auto,
                        mono_raster: MonoRasterSettings::default(),
                        ..request.settings.clone()
                    },
                },
            )
            .unwrap();
            let rasterization = if scan == MonoRasterSettings::default() {
                Rasterization::FreeTypeMono
            } else {
                Rasterization::FreeTypeMonoTerminals
            };
            let candidate = candidate::render_with_pipeline(
                &data,
                &request,
                pipeline(fitting, rasterization, true),
            )
            .unwrap();
            assert!(
                candidate
                    .records
                    .iter()
                    .any(|record| record.diagonal_fitting.is_some()),
                "expected applied diagonal records for {fitting:?}"
            );
            let evaluation = evaluate(&source, &upstream, &candidate);
            assert!(
                evaluation.hard_invariants_pass,
                "{fitting:?} {scan:?}: {:?}",
                evaluation.hard_failures
            );
        }
    }
}

fn be16(bytes: &[u8], at: usize) -> u16 {
    u16::from_be_bytes([bytes[at], bytes[at + 1]])
}

fn be32(bytes: &[u8], at: usize) -> u32 {
    u32::from_be_bytes([bytes[at], bytes[at + 1], bytes[at + 2], bytes[at + 3]])
}

fn put16(bytes: &mut [u8], at: usize, value: u16) {
    bytes[at..at + 2].copy_from_slice(&value.to_be_bytes());
}

fn put32(bytes: &mut [u8], at: usize, value: u32) {
    bytes[at..at + 4].copy_from_slice(&value.to_be_bytes());
}

// Copy of `data` with one cmap format-4 codepoint unmapped, splitting its
// delta segment and rebuilding the sfnt directory with fixed checksums.
// Only delta-mapped donor segments are supported; anything else panics.
fn unmap_codepoint(data: &[u8], codepoint: u32) -> Vec<u8> {
    assert!(codepoint <= 0xFFFF);
    let target = codepoint as u16;
    let tables = be16(data, 4) as usize;
    let mut list: Vec<([u8; 4], Vec<u8>)> = Vec::with_capacity(tables);
    let mut cmap_index = None;
    for i in 0..tables {
        let at = 12 + i * 16;
        let tag = [data[at], data[at + 1], data[at + 2], data[at + 3]];
        let offset = be32(data, at + 8) as usize;
        let length = be32(data, at + 12) as usize;
        if &tag == b"cmap" {
            cmap_index = Some(list.len());
        }
        list.push((tag, data[offset..offset + length].to_vec()));
    }
    let ci = cmap_index.expect("cmap table present");
    // Patch every format-4 subtable mapping the codepoint.
    let mut cmap = list[ci].1.clone();
    let nsubs = be16(&cmap, 2) as usize;
    let mut patched = false;
    for i in 0..nsubs {
        let record = 4 + i * 8;
        let sub = be32(&cmap, record + 4) as usize;
        if be16(&cmap, sub) != 4 {
            continue;
        }
        let old_len = be16(&cmap, sub + 2) as usize;
        let segs = (be16(&cmap, sub + 6) / 2) as usize;
        let mut starts = Vec::with_capacity(segs);
        let mut ends = Vec::with_capacity(segs);
        let mut deltas = Vec::with_capacity(segs);
        let mut ranges = Vec::with_capacity(segs);
        for s in 0..segs {
            ends.push(be16(&cmap, sub + 14 + 2 * s));
            starts.push(be16(&cmap, sub + 16 + 2 * segs + 2 * s));
            deltas.push(be16(&cmap, sub + 16 + 4 * segs + 2 * s));
            ranges.push(be16(&cmap, sub + 16 + 6 * segs + 2 * s));
        }
        let glyph_data = cmap[sub + 16 + 8 * segs..sub + old_len].to_vec();
        let Some(pos) = (0..segs).find(|&s| starts[s] <= target && target <= ends[s]) else {
            continue;
        };
        assert_eq!(ranges[pos], 0, "donor segment must be delta-mapped");
        patched = true;
        // Split out the target, keeping delta mapping for the remainder.
        let mut parts: Vec<(u16, u16)> = Vec::new();
        if starts[pos] < target {
            parts.push((starts[pos], target - 1));
        }
        if target < ends[pos] {
            parts.push((target + 1, ends[pos]));
        }
        let net = parts.len() as i32 - 1;
        let mut nstarts: Vec<u16> = Vec::with_capacity(segs + 2);
        let mut nends: Vec<u16> = Vec::with_capacity(segs + 2);
        let mut ndeltas: Vec<u16> = Vec::with_capacity(segs + 2);
        let mut nranges: Vec<u16> = Vec::with_capacity(segs + 2);
        for s in 0..segs {
            if s == pos {
                for &(lo, hi) in &parts {
                    nstarts.push(lo);
                    nends.push(hi);
                    ndeltas.push(deltas[s]);
                    nranges.push(0);
                }
            } else {
                // Later range offsets are unchanged: their address and the
                // glyph data shift together. Earlier ones gain the net array
                // growth since only the data moves.
                let shift = if (s as i32) < pos as i32 { 8 * net } else { 0 };
                nstarts.push(starts[s]);
                nends.push(ends[s]);
                ndeltas.push(deltas[s]);
                nranges.push((ranges[s] as i32 + shift) as u16);
            }
        }
        let nsegs = nstarts.len();
        let mut power = 1;
        while power * 2 <= nsegs {
            power *= 2;
        }
        let mut rebuilt = vec![0u8; 16 + 8 * nsegs + glyph_data.len()];
        put16(&mut rebuilt, 0, 4);
        put16(&mut rebuilt, 4, be16(&cmap, sub + 4));
        put16(&mut rebuilt, 6, (2 * nsegs) as u16);
        put16(&mut rebuilt, 8, (2 * power) as u16);
        put16(&mut rebuilt, 10, power.trailing_zeros() as u16);
        put16(&mut rebuilt, 12, (2 * nsegs - 2 * power) as u16);
        for (k, v) in nends.iter().enumerate() {
            put16(&mut rebuilt, 14 + 2 * k, *v);
        }
        put16(&mut rebuilt, 14 + 2 * nsegs, 0);
        for (k, v) in nstarts.iter().enumerate() {
            put16(&mut rebuilt, 16 + 2 * nsegs + 2 * k, *v);
        }
        for (k, v) in ndeltas.iter().enumerate() {
            put16(&mut rebuilt, 16 + 4 * nsegs + 2 * k, *v);
        }
        for (k, v) in nranges.iter().enumerate() {
            put16(&mut rebuilt, 16 + 6 * nsegs + 2 * k, *v);
        }
        rebuilt[16 + 8 * nsegs..].copy_from_slice(&glyph_data);
        let rebuilt_len = rebuilt.len() as u16;
        put16(&mut rebuilt, 2, rebuilt_len);
        // Splice the subtable, shifting later subtables within cmap.
        let delta = rebuilt.len() as i64 - old_len as i64;
        let mut patched_cmap = Vec::with_capacity(cmap.len() + delta as usize);
        patched_cmap.extend_from_slice(&cmap[..sub]);
        patched_cmap.extend_from_slice(&rebuilt);
        patched_cmap.extend_from_slice(&cmap[sub + old_len..]);
        for j in 0..nsubs {
            let at = 4 + j * 8 + 4;
            let off = be32(&cmap, at) as usize;
            if off > sub {
                put32(&mut patched_cmap, at, (off as i64 + delta) as u32);
            }
        }
        cmap = patched_cmap;
    }
    assert!(patched, "donor codepoint must be mapped");
    list[ci].1 = cmap;
    // Rebuild the sfnt with fresh offsets and checksums.
    let mut blobs: Vec<([u8; 4], Vec<u8>, u32)> = Vec::with_capacity(list.len());
    for (tag, bytes) in &list {
        let mut stored = bytes.clone();
        if tag == b"head" {
            stored[8..12].copy_from_slice(&[0, 0, 0, 0]);
        }
        let mut sum = 0u32;
        for chunk in stored.chunks(4) {
            let mut word = [0u8; 4];
            word[..chunk.len()].copy_from_slice(chunk);
            sum = sum.wrapping_add(u32::from_be_bytes(word));
        }
        blobs.push((*tag, stored, sum));
    }
    let head = blobs
        .iter()
        .position(|(tag, _, _)| tag == b"head")
        .expect("head table present");
    let mut cursor = 12 + 16 * blobs.len();
    let mut offsets = vec![0usize; blobs.len()];
    for (i, (_, stored, _)) in blobs.iter().enumerate() {
        offsets[i] = cursor;
        cursor += (stored.len() + 3) & !3;
    }
    let mut out = vec![0u8; cursor];
    out[..12].copy_from_slice(&data[..12]);
    for (i, (tag, stored, sum)) in blobs.iter().enumerate() {
        let at = 12 + i * 16;
        out[at..at + 4].copy_from_slice(tag);
        put32(&mut out, at + 4, *sum);
        put32(&mut out, at + 8, offsets[i] as u32);
        put32(&mut out, at + 12, stored.len() as u32);
        out[offsets[i]..offsets[i] + stored.len()].copy_from_slice(stored);
    }
    let mut total = 0u32;
    for chunk in out.chunks(4) {
        let mut word = [0u8; 4];
        word[..chunk.len()].copy_from_slice(chunk);
        total = total.wrapping_add(u32::from_be_bytes(word));
    }
    put32(
        &mut out,
        offsets[head] + 8,
        0xB1B0AFBAu32.wrapping_sub(total),
    );
    out
}

#[test]
fn missing_donor_keeps_upstream_without_new_failure() {
    // Unmap donor `W` (U+0057): the fifteen-donor reference cannot build,
    // so the opt-in run must retain upstream output without failing.
    let patched = unmap_codepoint(&font(), 'W' as u32);
    for fitting in [
        StemFittingStrategy::FontHintsAuto,
        StemFittingStrategy::UpstreamMono,
    ] {
        let mut settings =
            capture_request(fitting, "AVkxz", MonoRasterSettings::default()).settings;
        settings.missing_glyphs = MissingGlyphs::Skip;
        let request = ReferenceRequest {
            profile: "mono_1bit".into(),
            extensions: StemFittingStrategy::extension(Some(fitting)).into(),
            settings,
        };
        let off = candidate::render_with_pipeline(
            &patched,
            &request,
            pipeline(fitting, Rasterization::FreeTypeMono, false),
        )
        .unwrap();
        let on = candidate::render_with_pipeline(
            &patched,
            &request,
            pipeline(fitting, Rasterization::FreeTypeMono, true),
        )
        .unwrap();
        assert!(on
            .records
            .iter()
            .all(|record| record.diagonal_fitting.is_none()));
        assert!(!on.implementation.contains(":diagonal-shape-04"));
        assert_eq!(off.records.len(), on.records.len());
        for (a, b) in off.records.iter().zip(&on.records) {
            assert_eq!(a.fitted_commands, b.fitted_commands);
            assert_eq!(a.pixels, b.pixels);
        }
    }
}
