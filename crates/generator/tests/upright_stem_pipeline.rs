#![cfg(feature = "candidate")]
//! Real-font regression for the source-shape stage: the reported
//! Literata case through build_reference -> approved -> Mono,
//! asserting source relationships rather than literal pixel counts.
use font_generator::{
    candidate,
    evaluation::evaluate,
    mono,
    probe::FittedCommand,
    reference::{reference, DiagonalFittingCapture, ReferenceRequest},
    renderer::{Rasterization, RenderPipeline},
    stem_fitting::StemFittingStrategy,
    Config, Hinting, MonoRasterSettings,
};
use std::collections::BTreeMap;

fn font() -> Vec<u8> {
    std::fs::read(format!(
        "{}/../../fonts/Literata.ttf",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap()
}

fn request(characters: &str) -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: StemFittingStrategy::extension(Some(StemFittingStrategy::FontHintsAuto)).into(),
        settings: Config {
            characters: characters.into(),
            size_px: 16.0,
            output_bits: 1,
            hinting: StemFittingStrategy::FontHintsAuto.hinting(),
            axes: BTreeMap::from([("wght".to_string(), 400.0), ("opsz".to_string(), 16.0)]),
            mono_raster: MonoRasterSettings {
                font_instructions: true,
                include_stubs: true,
                ..Default::default()
            },
            ..Default::default()
        },
    }
}

fn render(
    data: &[u8],
    characters: &str,
    diagonal: bool,
) -> font_generator::reference::ReferenceReport {
    candidate::render_with_pipeline(
        data,
        &request(characters),
        RenderPipeline {
            fitting: StemFittingStrategy::FontHintsAuto,
            rasterization: Rasterization::FreeTypeMonoTerminals,
            diagonal_fitting: diagonal,
        },
    )
    .unwrap()
}

/// Principal upright pair: the widest vertical-border pair whose Y
/// intervals overlap, measured identically for every glyph. Returns the
/// left x, the width, and the overlap Y-interval locating delivered rows.
fn body_pair(commands: &[FittedCommand]) -> Option<(f64, f64, f64, f64)> {
    let mut pen = (0.0f64, 0.0f64);
    let mut segs: Vec<((f64, f64), (f64, f64))> = Vec::new();
    for cmd in commands {
        match *cmd {
            FittedCommand::MoveTo(x, y) => pen = (x as f64, y as f64),
            FittedCommand::LineTo(x, y) => {
                let next = (x as f64, y as f64);
                segs.push((pen, next));
                pen = next;
            }
            FittedCommand::QuadTo(_, _, x, y) => pen = (x as f64, y as f64),
            FittedCommand::CurveTo(_, _, _, _, x, y) => pen = (x as f64, y as f64),
            FittedCommand::Close => {}
        }
    }
    let vertical: Vec<(f64, f64, f64)> = segs
        .iter()
        .filter(|(a, b)| a.0 == b.0 && (a.1 - b.1).abs() > 2.0)
        .map(|(a, b)| (a.0, a.1.min(b.1), a.1.max(b.1)))
        .collect();
    let mut best: Option<(f64, f64, f64, f64)> = None;
    for l in &vertical {
        for r in &vertical {
            if r.0 > l.0 && l.2.min(r.2) > l.1.max(r.1) {
                let w = r.0 - l.0;
                if best.is_none_or(|b| w > b.1) {
                    best = Some((l.0, w, l.1.max(r.1), l.2.min(r.2)));
                }
            }
        }
    }
    best
}

fn upright_width(commands: &[FittedCommand]) -> Option<f64> {
    body_pair(commands).map(|(_, w, _, _)| w)
}

/// Delivered rows whose full pixel height lies strictly inside a Y
/// interval: boundary rows shared with crossbars or feet are excluded by
/// the frame geometry, never by glyph-specific row numbers. Bitmap rows
/// use the generator's y-down origin convention relative to the baseline.
fn interior_rows(top: i32, height: u32, ylo: f64, yhi: f64) -> Vec<usize> {
    (0..height as usize)
        .filter(|&r| {
            let hi_edge = -f64::from(top + r as i32);
            let lo_edge = hi_edge - 1.0;
            hi_edge < yhi && lo_edge > ylo
        })
        .collect()
}

/// Contiguous ink runs (start column, length) in one delivered row.
fn ink_runs(pixels: &[u8], width: u32, row: usize) -> Vec<(usize, usize)> {
    let mut runs = Vec::new();
    let mut start: Option<usize> = None;
    for c in 0..width as usize {
        let ink = pixels[row * width as usize + c] != 0;
        match (ink, start) {
            (true, None) => start = Some(c),
            (false, Some(s)) => {
                runs.push((s, c - s));
                start = None;
            }
            _ => {}
        }
    }
    if let Some(s) = start {
        runs.push((s, width as usize - s));
    }
    runs
}

fn ys(commands: &[FittedCommand]) -> Vec<u32> {
    commands
        .iter()
        .flat_map(|cmd| match *cmd {
            FittedCommand::MoveTo(_, y) | FittedCommand::LineTo(_, y) => vec![y.to_bits()],
            FittedCommand::QuadTo(_, y1, _, y) => vec![y1.to_bits(), y.to_bits()],
            FittedCommand::CurveTo(_, y1, _, y2, _, y) => {
                vec![y1.to_bits(), y2.to_bits(), y.to_bits()]
            }
            FittedCommand::Close => vec![],
        })
        .collect()
}

#[test]
fn literata_reported_case_reaches_peer_standard_through_real_pipeline() {
    let data = font();
    let on = render(&data, "tifl", true);
    let off = render(&data, "tifl", false);
    fn record<'a>(
        report: &'a font_generator::reference::ReferenceReport,
        ch: char,
    ) -> &'a font_generator::reference::ReferenceRecord {
        report
            .records
            .iter()
            .find(|r| r.codepoint == ch as u32)
            .unwrap()
    }
    // Disabled path: no capture, and the reported discrepancy is present
    // in the upstream relationship (t narrower than its peers).
    for ch in "tifl".chars() {
        assert!(record(&off, ch).diagonal_fitting.is_none());
    }
    let widths_off: Vec<f64> = "tifl"
        .chars()
        .map(|ch| upright_width(&record(&off, ch).fitted_commands).unwrap())
        .collect();
    assert!(
        widths_off[0] < widths_off[1],
        "upstream t narrower: {widths_off:?}"
    );

    // Enabled: t carries the source-shape provenance and reaches exactly
    // the peers' common upright width; the standard comes from the
    // certified donors, and the translated head stays narrower than the
    // body standard within the recorded allowance.
    let t_on = record(&on, 't');
    let capture = t_on.diagonal_fitting.as_ref().expect("t capture");
    assert_eq!(capture.model, "diagonal-shape-06");
    assert!(
        capture.reason.starts_with("source-shape:"),
        "{}",
        capture.reason
    );
    assert!(
        capture.upright_stem.is_none(),
        "new capture under legacy field"
    );
    let shape = capture.source_shape.as_ref().expect("shape provenance");
    assert_eq!(shape["model"], "upright-source-shape-01");
    assert_eq!(shape["kernel"], "coupled-shape-auto-01");
    assert_eq!(shape["standard"], 2.0);
    let (target, width, allowance) = (
        shape["checks"]["station_target"].as_f64().unwrap(),
        shape["checks"]["station_width"].as_f64().unwrap(),
        shape["checks"]["station_allowance"].as_f64().unwrap(),
    );
    assert!(width < shape["standard"].as_f64().unwrap());
    assert!((width - target).abs() <= allowance);
    let widths_on: Vec<f64> = "tifl"
        .chars()
        .map(|ch| upright_width(&record(&on, ch).fitted_commands).unwrap())
        .collect();
    assert!(
        widths_on.iter().all(|&w| w == widths_on[0]),
        "peer-equal bodies: {widths_on:?}"
    );

    // Delivered body span: every interior row of every body (pair
    // Y-interval, actual frame) carries one contiguous ink run of exactly
    // the integer standard. An outline-correct but tie-phased 2px body
    // delivering 3 columns fails here; no glyph row numbers, preferred
    // bitmap, or pixel-count goals are used.
    let expected = shape["standard"].as_f64().unwrap().round() as usize;
    assert!(expected >= 1);
    for ch in "tifl".chars() {
        let rec = record(&on, ch);
        let (_, _, ylo, yhi) = body_pair(&rec.fitted_commands).expect("body pair");
        let rows = interior_rows(rec.top, rec.height, ylo, yhi);
        assert!(!rows.is_empty(), "no interior body rows for {ch}");
        for r in rows {
            let runs = ink_runs(&rec.pixels, rec.width, r);
            assert_eq!(runs.len(), 1, "split body run for {ch} row {r}");
            assert_eq!(runs[0].1, expected, "body span for {ch} row {r}");
        }
    }
    // Disabled path delivers the reported discrepancy: t interior rows
    // carry a single 1-column run while peers carry 2.
    for ch in "tifl".chars() {
        let rec = record(&off, ch);
        let (_, _, ylo, yhi) = body_pair(&rec.fitted_commands).expect("body pair");
        let rows = interior_rows(rec.top, rec.height, ylo, yhi);
        assert!(!rows.is_empty(), "no interior body rows for {ch}");
        for r in rows {
            let runs = ink_runs(&rec.pixels, rec.width, r);
            assert_eq!(runs.len(), 1, "split body run for {ch} row {r}");
            assert_eq!(
                runs[0].1,
                if ch == 't' { 1 } else { 2 },
                "upstream body span for {ch} row {r}"
            );
        }
    }

    // Layout stays upstream-owned for every record; the source-shape
    // stage additionally retains t's fitted Y bits exactly (other glyphs
    // pass through the pre-existing downstream stages, which own their Y).
    for ch in "tifl".chars() {
        let (a, b) = (record(&on, ch), record(&off, ch));
        assert_eq!(a.advance_26_6, b.advance_26_6);
        assert_eq!(a.hinted_advance_width, b.hinted_advance_width);
    }
    assert_eq!(
        ys(&record(&on, 't').fitted_commands),
        ys(&record(&off, 't').fitted_commands)
    );

    // Request text does not choose donors: t alone renders identically.
    let solo = render(&data, "t", true);
    assert_eq!(record(&solo, 't').fitted_commands, t_on.fitted_commands);
}

/// Scanner contract the upright phase gate depends on (Hersch 5-6): a 2px
/// stem off the half-pixel tie delivers one clean 2-column run per
/// interior row; on the tie it does not.
#[test]
fn mono_phase_tie_adds_a_column_to_an_integer_stem() {
    let rect = |x0: f32| {
        vec![
            FittedCommand::MoveTo(x0, 0.0),
            FittedCommand::LineTo(x0 + 2.0, 0.0),
            FittedCommand::LineTo(x0 + 2.0, 8.0),
            FittedCommand::LineTo(x0, 8.0),
            FittedCommand::Close,
        ]
    };
    let config = Config {
        output_bits: 1,
        ..Config::default()
    };
    let clean = mono::rasterize(&rect(1.0), &config).unwrap();
    let rows = interior_rows(clean.top, clean.height, 0.0, 8.0);
    assert!(!rows.is_empty());
    for r in &rows {
        assert_eq!(
            ink_runs(&clean.pixels, clean.width, *r).len(),
            1,
            "split off-tie row {r}"
        );
        assert_eq!(ink_runs(&clean.pixels, clean.width, *r)[0].1, 2);
    }
    let tied = mono::rasterize(&rect(0.5), &config).unwrap();
    let tied_rows = interior_rows(tied.top, tied.height, 0.0, 8.0);
    assert!(!tied_rows.is_empty());
    assert!(
        tied_rows.iter().any(|&r| {
            let runs = ink_runs(&tied.pixels, tied.width, r);
            runs.len() != 1 || runs[0].1 != 2
        }),
        "tie phase unexpectedly delivers the clean stem"
    );
}

fn base_request(characters: &str, hinting: Hinting) -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "none".into(),
        settings: Config {
            characters: characters.into(),
            size_px: 16.0,
            output_bits: 1,
            hinting,
            axes: BTreeMap::from([("wght".to_string(), 400.0), ("opsz".to_string(), 16.0)]),
            ..Default::default()
        },
    }
}

/// Test-only reader for the frozen packet's command encoding: every
/// coordinate travels with its exact f32 bits, and the reader asserts
/// numeric consistency instead of trusting either representation alone.
fn frozen_command(value: &serde_json::Value) -> FittedCommand {
    let op = value["op"].as_str().expect("frozen command op");
    let coordinate = |key: &str| -> f32 {
        let text = value[key].as_f64().expect("frozen coordinate") as f32;
        let bits = value
            .get(format!("{key}_bits"))
            .and_then(|bits| bits.as_u64())
            .expect("frozen bits") as u32;
        assert_eq!(f32::from_bits(bits), text, "float bits mismatch for {key}");
        text
    };
    match op {
        "move_to" => FittedCommand::MoveTo(coordinate("x"), coordinate("y")),
        "line_to" => FittedCommand::LineTo(coordinate("x"), coordinate("y")),
        "quad_to" => FittedCommand::QuadTo(
            coordinate("x1"),
            coordinate("y1"),
            coordinate("x"),
            coordinate("y"),
        ),
        "curve_to" => FittedCommand::CurveTo(
            coordinate("x1"),
            coordinate("y1"),
            coordinate("x2"),
            coordinate("y2"),
            coordinate("x"),
            coordinate("y"),
        ),
        "close" => FittedCommand::Close,
        _ => panic!("unknown frozen command op {op}"),
    }
}

fn frozen_commands(value: &serde_json::Value) -> Vec<FittedCommand> {
    value
        .as_array()
        .expect("frozen command list")
        .iter()
        .map(frozen_command)
        .collect()
}

fn invariants(report: &font_generator::evaluation::Evaluation) -> Vec<String> {
    report
        .hard_failures
        .iter()
        .map(|failure| failure.invariant.clone())
        .collect()
}

/// The genuine `diagonal-shape-06` capture replays through the new
/// sequence with its recorded inputs, and the evaluator accepts it.
#[test]
fn new_shape_capture_replays_through_evaluation() {
    let data = font();
    let candidate = render(&data, "t", true);
    let capture = candidate.records[0]
        .diagonal_fitting
        .as_ref()
        .expect("t capture");
    assert_eq!(capture.model, "diagonal-shape-06");
    let source = reference(&data, &base_request("t", Hinting::None)).unwrap();
    let upstream = reference(&data, &base_request("t", Hinting::Auto)).unwrap();
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
    assert_eq!(invariants(&evaluation), Vec::<String>::new());
}

/// Misaligned `diagonal-shape-06` packets fail before any geometry
/// runs: legacy model with new provenance, missing kernel provenance,
/// legacy-field provenance, and a non-shape reason each flaw.
#[test]
fn misaligned_shape_captures_fail_replay() {
    let data = font();
    let source = reference(&data, &base_request("t", Hinting::None)).unwrap();
    let upstream = reference(&data, &base_request("t", Hinting::Auto)).unwrap();
    for (tamper, expected) in [
        (
            "legacy-model",
            "legacy capture carries new source-shape provenance",
        ),
        (
            "missing-provenance",
            "new source capture without kernel provenance",
        ),
        (
            "legacy-field",
            "new source capture under legacy provenance field",
        ),
        (
            "wrong-reason",
            "new non-shape capture carries shape provenance",
        ),
    ] {
        let mut candidate = render(&data, "t", true);
        let capture = candidate.records[0]
            .diagonal_fitting
            .as_mut()
            .expect("t capture");
        match tamper {
            "legacy-model" => capture.model = "diagonal-shape-05".into(),
            "missing-provenance" => capture.source_shape = None,
            "legacy-field" => capture.upright_stem = Some(serde_json::json!({"standard": 2.0})),
            _ => capture.reason = "curve:fitted".into(),
        }
        let evaluation = evaluate(&source, &upstream, &candidate);
        assert!(
            !evaluation.hard_invariants_pass,
            "tamper {tamper} unexpectedly accepted"
        );
        assert!(
            invariants(&evaluation)
                .iter()
                .any(|failure| failure == expected),
            "tamper {tamper}: {:?}",
            evaluation.hard_failures
        );
    }
}

/// The frozen rejected Literata 16px `t` packet replays under the
/// historical `diagonal-shape-05` sequence. Genuine current renders supply
/// the source, upstream and layout identity; the frozen record supplies
/// only its own commands, capture, delivered pixels and bounds. The public
/// evaluator must accept the old bad output exactly, while the current
/// route delivers different commands for the same inputs.
#[test]
fn frozen_rejected_05_packet_replays_under_historical_sequence() {
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/frozen-upright-05-t16.json"))
            .expect("frozen 05 fixture");
    assert_eq!(
        fixture["packet_sha256"],
        "989803ccf29d288e89d6bbefb79813315f9ca13c7f858ec2725f1dcf7af1a76b"
    );
    assert_eq!(
        fixture["source_sha256"],
        "b41138c9373112f32abb589cc22e8674b06ed4048b0c513be922bdd26f274440"
    );
    assert_eq!(fixture["size_px"], 16.0);
    let data = font();
    let mut candidate = render(&data, "t", true);
    let fresh_commands = candidate.records[0].fitted_commands.clone();
    let source = reference(&data, &base_request("t", Hinting::None)).unwrap();
    let upstream = reference(&data, &base_request("t", Hinting::Auto)).unwrap();
    let plain = render(&data, "t", false);
    assert_eq!(
        source.source_sha256,
        fixture["source_sha256"].as_str().unwrap()
    );
    assert_eq!(
        candidate.records[0].glyph_id,
        fixture["glyph_id"].as_u64().unwrap() as u32
    );
    // Frozen inputs are exactly reproducible today: the old source outline
    // matches the genuine current source render and the old upstream
    // outline matches the genuine current diagonal-off pipeline render,
    // so nothing is fabricated from the fitted output.
    let frozen_fitted = frozen_commands(&fixture["fitted_commands"]);
    let frozen_source = frozen_commands(&fixture["source_commands"]);
    let frozen_capture = &fixture["diagonal_fitting"];
    let frozen_upstream = frozen_commands(&frozen_capture["upstream_commands"]);
    assert_eq!(frozen_source, source.records[0].fitted_commands);
    assert_eq!(frozen_upstream, plain.records[0].fitted_commands);
    assert_eq!(
        upstream.records[0].advance_26_6,
        fixture["advance_26_6"].as_i64().unwrap() as i32
    );
    assert_eq!(frozen_capture["model"], "diagonal-shape-05");
    let axes = frozen_capture["native_axes"].as_array().unwrap();
    let native_axes = [axes[0].as_bool().unwrap(), axes[1].as_bool().unwrap()];
    assert_eq!(native_axes, [false, false]);
    // The candidate keeps its genuine layout siblings and takes only the
    // frozen record's own geometry, capture, delivered pixels and bounds.
    let record = &mut candidate.records[0];
    record.fitted_commands = frozen_fitted.clone();
    record.source_commands = Some(frozen_source);
    record.diagonal_fitting = Some(DiagonalFittingCapture {
        model: frozen_capture["model"].as_str().unwrap().into(),
        raw_source: Some(frozen_capture["raw_source"].clone()),
        upstream_commands: frozen_upstream,
        native_axes,
        reason: frozen_capture["reason"].as_str().unwrap().into(),
        size_px: frozen_capture["size_px"].as_f64().unwrap(),
        reference: frozen_capture["reference"].clone(),
        upright_stem: Some(frozen_capture["upright_stem"].clone()),
        source_shape: None,
    });
    record.pixels = serde_json::from_value(fixture["pixels"].clone()).unwrap();
    record.coverage = serde_json::from_value(fixture["coverage"].clone()).unwrap();
    record.coverage_sha256 = fixture["coverage_sha256"].as_str().unwrap().into();
    record.left = fixture["left"].as_i64().unwrap() as i32;
    record.top = fixture["top"].as_i64().unwrap() as i32;
    record.width = fixture["width"].as_u64().unwrap() as u32;
    record.height = fixture["height"].as_u64().unwrap() as u32;
    record.advance_26_6 = fixture["advance_26_6"].as_i64().unwrap() as i32;
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
    // The historical sequence reproduces the old bad commands exactly,
    // while the current route delivers different commands underneath.
    let replayed = &candidate.records[0];
    let capture = replayed.diagonal_fitting.as_ref().expect("frozen capture");
    assert_eq!(capture.model, "diagonal-shape-05");
    assert!(capture.reason.starts_with("upright:"), "{}", capture.reason);
    assert_eq!(replayed.fitted_commands, frozen_fitted);
    assert_ne!(frozen_fitted, fresh_commands);
}

/// First scalar in a wider render carrying a genuine new-sequence non-shape
/// capture. Request text never chooses donors, so the solo render below
/// reproduces the same record.
fn nonshape_text(data: &[u8]) -> String {
    let wide = render(data, "filmnt", true);
    let codepoint = wide
        .records
        .iter()
        .find(|record| {
            record.diagonal_fitting.as_ref().is_some_and(|capture| {
                capture.model == "diagonal-shape-06" && !capture.reason.starts_with("source-shape:")
            })
        })
        .expect("new-sequence non-shape capture")
        .codepoint;
    char::from_u32(codepoint).expect("scalar").to_string()
}

/// A genuine new-sequence non-shape capture replays through the current
/// dispatcher with no shape provenance: model 06, a pre-coupled reason,
/// and both provenance fields absent. Geometry, pixel and layout checks
/// still run unchanged through the public evaluator.
#[test]
fn new_nonshape_capture_replays_without_shape_provenance() {
    let data = font();
    let text = nonshape_text(&data);
    let candidate = render(&data, &text, true);
    let record = &candidate.records[0];
    let capture = record.diagonal_fitting.as_ref().expect("solo capture");
    assert_eq!(capture.model, "diagonal-shape-06");
    assert!(
        !capture.reason.starts_with("source-shape:"),
        "{}",
        capture.reason
    );
    assert_eq!(capture.source_shape, None);
    assert_eq!(capture.upright_stem, None);
    let source = reference(&data, &base_request(&text, Hinting::None)).unwrap();
    let upstream = reference(&data, &base_request(&text, Hinting::Auto)).unwrap();
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
}

/// A non-shape 06 capture carrying shape provenance flaws before any
/// geometry runs.
#[test]
fn malformed_nonshape_capture_with_shape_provenance_flaws() {
    let data = font();
    let text = nonshape_text(&data);
    let mut candidate = render(&data, &text, true);
    candidate.records[0]
        .diagonal_fitting
        .as_mut()
        .expect("solo capture")
        .source_shape = Some(serde_json::json!({
        "model": "upright-source-shape-01",
        "kernel": "coupled-shape-auto-01",
    }));
    let source = reference(&data, &base_request(&text, Hinting::None)).unwrap();
    let upstream = reference(&data, &base_request(&text, Hinting::Auto)).unwrap();
    let evaluation = evaluate(&source, &upstream, &candidate);
    assert!(
        !evaluation.hard_invariants_pass,
        "malformed non-shape unexpectedly accepted"
    );
    assert!(
        invariants(&evaluation)
            .iter()
            .any(|failure| failure == "new non-shape capture carries shape provenance"),
        "{:?}",
        evaluation.hard_failures
    );
}
