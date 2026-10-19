//! Approved baseline (001.01/001.02) diagonal-model geometric guards,
//! preserved from the former candidate iteration tests when the working
//! candidate moved to the vertical-only policy. These tests now guard
//! their actual owner: the vendored baseline snapshot accessed through
//! `baseline::{capture, render}`. The baseline declares linear advances,
//! so advance assertions use source linear identity throughout. The
//! superseded candidate compact-dot ownership test is intentionally not
//! ported; compact marks are not part of the baseline contract tested
//! here. Mechanical/geometric guards only; no optical acceptance.
use font_generator::{
    baseline::{capture, render, EXTENSIONS_DIAGONAL_01},
    reference::{
        reference, ReferenceRecord, ReferenceRequest, PROFILE_GRAY_3BIT, PROFILE_MONO_1BIT,
    },
    Config, Hinting,
};
use serde_json::Value;
use std::{fs, path::Path};

fn font(name: &str) -> Vec<u8> {
    fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../fonts")
            .join(name),
    )
    .unwrap()
}

fn request(name: &str, size: f32, profile: &str) -> ReferenceRequest {
    let mut config = Config {
        size_px: size,
        characters: (33u8..=126).map(char::from).chain(['°']).collect(),
        hinting: Hinting::Auto,
        output_bits: if profile == PROFILE_MONO_1BIT { 1 } else { 3 },
        ..Config::default()
    };
    config.axes.insert("wght".into(), 400.0);
    if name == "Roboto.ttf" {
        config.axes.insert("wdth".into(), 100.0);
    }
    if name == "Literata.ttf" {
        config.axes.insert("opsz".into(), size);
    }
    ReferenceRequest {
        profile: profile.into(),
        extensions: "none".into(),
        settings: config,
    }
}

fn ink_components(record: &ReferenceRecord) -> usize {
    let width = record.width as usize;
    let height = record.height as usize;
    let mut visited = vec![false; record.pixels.len()];
    let mut count = 0;
    for start in 0..record.pixels.len() {
        if visited[start] || record.pixels[start] == 0 {
            continue;
        }
        count += 1;
        let mut queue = vec![start];
        visited[start] = true;
        let mut next = 0;
        while next < queue.len() {
            let p = queue[next];
            next += 1;
            for dy in -1..=1isize {
                for dx in -1..=1isize {
                    let x = (p % width) as isize + dx;
                    let y = (p / width) as isize + dy;
                    if x < 0 || y < 0 || x >= width as isize || y >= height as isize {
                        continue;
                    }
                    let neighbor = y as usize * width + x as usize;
                    if !visited[neighbor] && record.pixels[neighbor] != 0 {
                        visited[neighbor] = true;
                        queue.push(neighbor);
                    }
                }
            }
        }
    }
    count
}

fn assert_connected_letter_preserved(a: &ReferenceRecord, b: &ReferenceRecord, context: &str) {
    if char::from_u32(b.codepoint).unwrap().is_ascii_alphabetic() && ink_components(b) == 1 {
        assert_eq!(ink_components(a), 1, "{context} U+{:04X}", a.codepoint);
    }
}

// The approved baseline declares the linear advance policy: its reported
// advance is the source linear advance at every record, while its fitted
// outlines and dropout raster carry the diagonal model.
fn assert_baseline_advance(record: &ReferenceRecord, linear_26_6: i32) {
    assert_eq!(record.advance_26_6, linear_26_6);
}

// The approved model changes X-width fitting even when no diagonal pair applies.
// Y fitting and contour structure remain unchanged on these axial witnesses.
fn assert_axial_structure_and_y_preserved(a: &ReferenceRecord, b: &ReferenceRecord) {
    let y_commands = |r: &ReferenceRecord| {
        let mut commands = serde_json::to_value(&r.fitted_commands).unwrap();
        for command in commands.as_array_mut().unwrap() {
            for key in ["x", "x_bits", "x1", "x1_bits", "x2", "x2_bits"] {
                command.as_object_mut().unwrap().remove(key);
            }
        }
        commands
    };
    assert_eq!(y_commands(a), y_commands(b));
    assert_baseline_advance(a, b.advance_26_6);
    assert_eq!(ink_components(a), 1);
}

#[test]
fn reported_roboto_14_x_and_16_nwxyz_fit_all_pairs_and_stay_connected() {
    let bytes = font("Roboto.ttf");
    for (size, glyphs) in [(14.0, "X"), (16.0, "NWXYZ")] {
        for ch in glyphs.chars() {
            let mut req = request("Roboto.ttf", size, PROFILE_MONO_1BIT);
            req.settings.characters = ch.to_string();
            let upstream = reference(&bytes, &req).unwrap();
            req.extensions = EXTENSIONS_DIAGONAL_01.into();
            let fitted = render(&bytes, &req).unwrap();
            let a = &fitted.records[0];
            let b = &upstream.records[0];
            let [detected, applied, unapplied] = a.diagonal_pairs.unwrap();
            assert!(detected > 0);
            assert_eq!(detected, applied);
            assert_eq!(unapplied, 0);
            // Pixel population is a diagnostic, not a quality objective. The
            // geometric width/contrast and original-correction witnesses below
            // provide fitting evidence independently of a preferred ink count.
            assert_baseline_advance(a, b.advance_26_6);
            assert_eq!(ink_components(a), 1, "Roboto {size} {ch}");
        }
    }
}

#[test]
fn disabled_capture_delegates_exactly_to_independent_reference() {
    // Full serialized equality, provenance included: the disabled route
    // is the current registry reference, not the legacy fork.
    let assert_exact = |bytes: &[u8], req: &ReferenceRequest, context: &str| {
        let expected = reference(bytes, req).unwrap();
        let disabled = capture(bytes, req, false).unwrap();
        assert!(!disabled.fork, "{context}");
        assert_eq!(
            disabled.implementation, expected.implementation,
            "{context}"
        );
        assert_eq!(
            disabled.skrifa_version, expected.skrifa_version,
            "{context}"
        );
        assert_eq!(
            disabled.skrifa_registry_checksum, expected.skrifa_registry_checksum,
            "{context}"
        );
        assert_eq!(
            serde_json::to_value(&disabled).unwrap(),
            serde_json::to_value(&expected).unwrap(),
            "{context}"
        );
    };
    let bytes = font("Roboto.ttf");
    for profile in [PROFILE_MONO_1BIT, PROFILE_GRAY_3BIT] {
        for mode in [Hinting::Auto, Hinting::None, Hinting::Interpreter] {
            let mut req = request("Roboto.ttf", 14.0, profile);
            req.settings.characters = "AVa09".into();
            req.settings.hinting = mode;
            assert_exact(&bytes, &req, &format!("Roboto {profile} {mode:?}"));
        }
    }
    for (name, bytes) in [
        (
            "static-cff",
            include_bytes!("fixtures/static-cff.otf").as_slice(),
        ),
        (
            "variable-cff2",
            include_bytes!("fixtures/variable-cff2.otf").as_slice(),
        ),
    ] {
        for profile in [PROFILE_MONO_1BIT, PROFILE_GRAY_3BIT] {
            for mode in [Hinting::Auto, Hinting::None, Hinting::Interpreter] {
                let req = ReferenceRequest {
                    profile: profile.into(),
                    extensions: "none".into(),
                    settings: Config {
                        size_px: 14.0,
                        characters: "A".into(),
                        hinting: mode,
                        output_bits: if profile == PROFILE_MONO_1BIT { 1 } else { 3 },
                        ..Config::default()
                    },
                };
                assert_exact(bytes, &req, &format!("{name} {profile} {mode:?}"));
            }
        }
    }
}

#[test]
fn disabled_capture_rejects_non_none_and_routes_reference_errors() {
    let bytes = font("Roboto.ttf");
    for extensions in [EXTENSIONS_DIAGONAL_01, "diagonal-02", ""] {
        let mut req = request("Roboto.ttf", 14.0, PROFILE_MONO_1BIT);
        req.settings.characters = "A".into();
        req.extensions = extensions.into();
        let error = capture(&bytes, &req, false).unwrap_err();
        assert!(
            error.to_string().contains("disabled fork capture"),
            "{extensions}: {error}"
        );
    }
    // Invalid reference requests fail through the reference itself, with
    // its exact error, once the none extension is accepted.
    let invalid = |req: &ReferenceRequest| {
        let delegated = capture(&bytes, req, false).unwrap_err().to_string();
        let direct = reference(&bytes, req).unwrap_err().to_string();
        assert_eq!(delegated, direct);
    };
    let mut req = request("Roboto.ttf", 14.0, PROFILE_MONO_1BIT);
    req.settings.characters = "A".into();
    req.settings.hinting = Hinting::AutoFallback;
    invalid(&req);
    let mut req = request("Roboto.ttf", 14.0, PROFILE_MONO_1BIT);
    req.settings.characters = "A".into();
    req.profile = "unknown".into();
    invalid(&req);
    let mut req = request("Roboto.ttf", 14.0, PROFILE_GRAY_3BIT);
    req.settings.characters = "A".into();
    req.settings.output_bits = 1;
    invalid(&req);
}

#[test]
fn experimental_corpus_is_deterministic_preserves_line_metrics_and_grayscale() {
    for name in ["Roboto.ttf", "Literata.ttf", "SourceSans3.ttf"] {
        let bytes = font(name);
        for size in [14.0, 16.0, 18.0, 20.0] {
            for profile in [PROFILE_MONO_1BIT, PROFILE_GRAY_3BIT] {
                let mut req = request(name, size, profile);
                let upstream = reference(&bytes, &req).unwrap();
                req.extensions = EXTENSIONS_DIAGONAL_01.into();
                let fitted = render(&bytes, &req).unwrap();
                req.settings.characters = req.settings.characters.chars().rev().collect();
                let repeated = render(&bytes, &req).unwrap();
                assert_eq!(
                    serde_json::to_value(&fitted).unwrap(),
                    serde_json::to_value(&repeated).unwrap()
                );
                assert_eq!(fitted.metrics, upstream.metrics);
                assert_eq!(fitted.records.len(), 95);
                for (a, b) in fitted.records.iter().zip(&upstream.records) {
                    assert_baseline_advance(a, b.advance_26_6);
                    assert_eq!(a.coverage.len(), (a.width * a.height) as usize);
                    assert!(a.pixels.iter().all(|p| *p < (1 << a.output_bits)));
                    if profile == PROFILE_GRAY_3BIT {
                        assert_eq!(
                            serde_json::to_value(a).unwrap(),
                            serde_json::to_value(b).unwrap()
                        );
                    } else {
                        let [detected, applied, conflicting] = a.diagonal_pairs.unwrap();
                        assert_eq!(detected, applied + conflicting);
                        assert_connected_letter_preserved(a, b, &format!("{name} {size}"));
                    }
                }
            }
        }
    }
}

#[test]
fn reported_case_has_real_constraints_and_straight_controls_preserve_y_and_layout() {
    let bytes = font("Roboto.ttf");
    let mut req = request("Roboto.ttf", 14.0, PROFILE_MONO_1BIT);
    let upstream = reference(&bytes, &req).unwrap();
    req.extensions = EXTENSIONS_DIAGONAL_01.into();
    let fitted = render(&bytes, &req).unwrap();
    for (a, b) in fitted.records.iter().zip(&upstream.records) {
        if "HIn".contains(char::from_u32(a.codepoint).unwrap()) {
            assert_eq!(a.diagonal_pairs, Some([0, 0, 0]));
            assert_axial_structure_and_y_preserved(a, b);
        }
        if "AVvwxyz".contains(char::from_u32(a.codepoint).unwrap()) {
            eprintln!(
                "{}: {:?}, pixels {} -> {}",
                char::from_u32(a.codepoint).unwrap(),
                a.diagonal_pairs,
                b.pixels.iter().filter(|p| **p != 0).count(),
                a.pixels.iter().filter(|p| **p != 0).count()
            );
        }
    }
    let a = fitted.records.iter().find(|r| r.codepoint == 65).unwrap();
    assert_eq!(a.diagonal_pairs.unwrap(), [2, 2, 0]);
    for ch in "AVvwxyz".chars() {
        let a = fitted
            .records
            .iter()
            .find(|r| r.codepoint == ch as u32)
            .unwrap();
        let b = upstream
            .records
            .iter()
            .find(|r| r.codepoint == ch as u32)
            .unwrap();
        let counts = a.diagonal_pairs.unwrap();
        assert!(counts[0] > 0);
        assert_eq!(counts[0], counts[1]);
        assert_eq!(counts[2], 0);
        assert_ne!(a.fitted_commands, b.fitted_commands);
    }
}

#[test]
fn rejects_unsupported_extension_and_active_nonmono_controls() {
    let bytes = font("Roboto.ttf");
    let mut req = request("Roboto.ttf", 14.0, PROFILE_MONO_1BIT);
    assert!(render(&bytes, &req).is_err());
    req.extensions = "diagonal-02".into();
    assert!(render(&bytes, &req).is_err());
    assert!(capture(&bytes, &req, true).is_err());
    req.extensions = EXTENSIONS_DIAGONAL_01.into();
    for mode in [Hinting::Interpreter, Hinting::None, Hinting::AutoFallback] {
        req.settings.hinting = mode;
        assert!(render(&bytes, &req).is_err());
        req.profile = PROFILE_GRAY_3BIT.into();
        req.settings.output_bits = 3;
        assert!(render(&bytes, &req).is_err());
        req.profile = PROFILE_MONO_1BIT.into();
        req.settings.output_bits = 1;
    }
}

#[test]
fn non_held_active_sweep_preserves_metrics_advances_and_join_observations() {
    let mut join_regressions = Vec::new();
    for name in ["Roboto.ttf", "Literata.ttf", "SourceSans3.ttf"] {
        let bytes = font(name);
        let sizes: Vec<_> = if name == "SourceSans3.ttf" {
            vec![13.0, 14.0, 16.0, 18.0, 20.0]
        } else {
            (13..=21).map(|size| size as f32).collect()
        };
        let mut requests: Vec<_> = sizes
            .into_iter()
            .map(|size| request(name, size, PROFILE_MONO_1BIT))
            .collect();
        for size in [16.0, 20.0] {
            for weight in [300.0, 500.0] {
                let mut req = request(name, size, PROFILE_MONO_1BIT);
                req.settings.axes.insert("wght".into(), weight);
                requests.push(req);
            }
        }
        if name == "Literata.ttf" {
            for optical_size in [12.0, 24.0] {
                let mut req = request(name, 16.0, PROFILE_MONO_1BIT);
                req.settings.axes.insert("opsz".into(), optical_size);
                requests.push(req);
            }
        }
        for mut req in requests {
            let upstream = reference(&bytes, &req).unwrap();
            req.extensions = EXTENSIONS_DIAGONAL_01.into();
            let fitted = render(&bytes, &req).unwrap();
            assert_eq!(fitted.metrics, upstream.metrics);
            assert!(fitted.missing_codepoints.is_empty());
            assert_eq!(fitted.records.len(), 95);
            for (a, b) in fitted.records.iter().zip(&upstream.records) {
                assert_baseline_advance(a, b.advance_26_6);
                assert!(a.pixels.iter().all(|p| *p <= 1));
                if char::from_u32(a.codepoint).unwrap().is_ascii_alphabetic()
                    && ink_components(b) == 1
                    && ink_components(a) > 1
                {
                    join_regressions.push(serde_json::json!({
                        "font": name, "size_px": req.settings.size_px, "axes": req.settings.axes,
                        "glyph": char::from_u32(a.codepoint).unwrap(), "components": ink_components(a)
                    }));
                }
            }
        }
    }
    eprintln!(
        "Non-held join regressions: {}",
        serde_json::to_string(&join_regressions).unwrap()
    );
}

#[test]
fn postscript_fixtures_preserve_active_metrics_and_advances() {
    for bytes in [
        include_bytes!("fixtures/static-cff.otf").as_slice(),
        include_bytes!("fixtures/variable-cff2.otf").as_slice(),
    ] {
        let settings = |profile: &str| Config {
            size_px: 14.0,
            characters: "A".into(),
            hinting: Hinting::Auto,
            output_bits: if profile == PROFILE_MONO_1BIT { 1 } else { 3 },
            ..Config::default()
        };
        // Active Mono runs the legacy fork on PostScript outlines.
        let upstream = reference(
            bytes,
            &ReferenceRequest {
                profile: PROFILE_MONO_1BIT.into(),
                extensions: "none".into(),
                settings: settings(PROFILE_MONO_1BIT),
            },
        )
        .unwrap();
        let fitted = render(
            bytes,
            &ReferenceRequest {
                profile: PROFILE_MONO_1BIT.into(),
                extensions: EXTENSIONS_DIAGONAL_01.into(),
                settings: settings(PROFILE_MONO_1BIT),
            },
        )
        .unwrap();
        assert!(fitted.fork);
        assert_eq!(fitted.metrics, upstream.metrics);
        assert_eq!(fitted.records.len(), 1);
        assert_eq!(fitted.records[0].codepoint, u32::from('A'));
        assert_baseline_advance(&fitted.records[0], upstream.records[0].advance_26_6);
        assert!(fitted.records[0].diagonal_pairs.is_some());
        assert!(fitted.records[0].pixels.iter().all(|p| *p <= 1));
        assert_eq!(
            fitted.records[0].coverage.len(),
            (fitted.records[0].width * fitted.records[0].height) as usize
        );
        // Active Gray keeps its upstream delegation under legacy metadata.
        let upstream_gray = reference(
            bytes,
            &ReferenceRequest {
                profile: PROFILE_GRAY_3BIT.into(),
                extensions: "none".into(),
                settings: settings(PROFILE_GRAY_3BIT),
            },
        )
        .unwrap();
        let gray = render(
            bytes,
            &ReferenceRequest {
                profile: PROFILE_GRAY_3BIT.into(),
                extensions: EXTENSIONS_DIAGONAL_01.into(),
                settings: settings(PROFILE_GRAY_3BIT),
            },
        )
        .unwrap();
        assert_eq!(gray.extensions, EXTENSIONS_DIAGONAL_01);
        assert_eq!(gray.metrics, upstream_gray.metrics);
        assert_eq!(
            serde_json::to_value(&gray.records).unwrap(),
            serde_json::to_value(&upstream_gray.records).unwrap()
        );
    }
}

#[test]
fn baseline_single_glyph_records_match_full_ordinary_repertoires() {
    for name in ["Roboto.ttf", "Literata.ttf", "SourceSans3.ttf"] {
        let bytes = font(name);
        for size in [14.0, 16.0, 18.0, 20.0] {
            let mut req = request(name, size, PROFILE_MONO_1BIT);
            req.extensions = EXTENSIONS_DIAGONAL_01.into();
            let full = render(&bytes, &req).unwrap();
            for record in full.records {
                req.settings.characters = char::from_u32(record.codepoint).unwrap().to_string();
                let single = render(&bytes, &req).unwrap();
                assert_eq!(single.records.len(), 1);
                assert_eq!(
                    serde_json::to_value(record).unwrap(),
                    serde_json::to_value(&single.records[0]).unwrap(),
                    "{name} {size}"
                );
            }
        }
    }
}

// These are immutable captures from earlier work within the accepted 001.01.
// They preserve regression evidence without exposing a second renderer iteration.
fn before_width_tweak(name: &str, size: f32, characters: &str) -> Vec<Value> {
    let snapshot: Value =
        serde_json::from_str(include_str!("fixtures/diagonal-before-width-tweak.json")).unwrap();
    let family = if name == "Roboto.ttf" {
        "roboto"
    } else {
        "literata"
    };
    let case = snapshot["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["family"] == family && case["size_px"].as_f64() == Some(size as f64))
        .unwrap();
    let records: Vec<_> = case["records"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|record| {
            characters
                .contains(char::from_u32(record["codepoint"].as_u64().unwrap() as u32).unwrap())
        })
        .cloned()
        .collect();
    assert_eq!(records.len(), characters.chars().count());
    records
}

#[test]
fn stem_relative_widths_restore_reported_strokes_and_preserve_design_contracts() {
    let normal_width = |r: &Value, left: usize, right: usize| {
        let border = |index: usize| {
            let xy = |i: usize| {
                let command = &r["fitted_commands"][i];
                (
                    command["x"].as_f64().unwrap(),
                    command["y"].as_f64().unwrap(),
                )
            };
            let (x0, y0) = xy(index - 1);
            let (x1, y1) = xy(index);
            let slope = (x1 - x0) / (y1 - y0);
            (slope, x0 - slope * y0, y0.min(y1), y0.max(y1))
        };
        let a = border(left);
        let b = border(right);
        let y = (a.2.max(b.2) + a.3.min(b.3)) * 0.5;
        let slope = (a.0 + b.0) * 0.5;
        ((a.0 * y + a.1) - (b.0 * y + b.1)).abs() / (1.0 + slope * slope).sqrt()
    };
    // Reported witnesses verify actual border geometry, rather than using total
    // ink as a substitute for stroke thickness. Point indices are diagnostic only.
    for (name, size, ch, left, right) in [
        ("Roboto.ttf", 18.0, 'v', 1, 3),
        ("Roboto.ttf", 18.0, 'w', 1, 4),
        ("Literata.ttf", 16.0, 'z', 2, 11),
    ] {
        let bytes = font(name);
        let mut req = request(name, size, PROFILE_MONO_1BIT);
        req.settings.characters = ch.to_string();
        req.extensions = EXTENSIONS_DIAGONAL_01.into();
        let old = before_width_tweak(name, size, &ch.to_string());
        let new = render(&bytes, &req).unwrap();
        // Fractional shared fitting replaces the former integer-width increase.
        // Compare to independent unhinted source thickness, with the inherited
        // quarter-pixel axial rounding bound and endpoint quantization margin.
        req.settings.hinting = Hinting::None;
        req.extensions = "none".into();
        let source = reference(&bytes, &req).unwrap();
        let source_width = normal_width(
            &serde_json::to_value(&source.records[0]).unwrap(),
            left,
            right,
        );
        let commands = serde_json::to_value(&new.records[0].fitted_commands).unwrap();
        let slope = (commands[left]["x"].as_f64().unwrap()
            - commands[left - 1]["x"].as_f64().unwrap())
            / (commands[left]["y"].as_f64().unwrap() - commands[left - 1]["y"].as_f64().unwrap());
        let normal_scale = (1.0 + slope * slope).sqrt();
        let rounding_bound = (0.25 * slope.abs().max(1.0)
            + ((1.0 + slope.abs()).ceil() + 1.0) / 64.0)
            / normal_scale;
        let fitted_width =
            normal_width(&serde_json::to_value(&new.records[0]).unwrap(), left, right);
        assert!(
            (fitted_width - source_width).abs() <= rounding_bound,
            "{name} {size} {ch}: {source_width} -> {fitted_width}"
        );
        assert_eq!(ink_components(&new.records[0]), 1);
        assert_eq!(
            serde_json::to_value(new.records[0].diagonal_pairs).unwrap(),
            old[0]["diagonal_pairs"]
        );
    }
    let bytes = font("Roboto.ttf");
    for (size, chars) in [(14.0, "AVvwxyzX"), (16.0, "NWXYZ")] {
        let mut req = request("Roboto.ttf", size, PROFILE_MONO_1BIT);
        req.settings.characters = chars.into();
        req.extensions = EXTENSIONS_DIAGONAL_01.into();
        let old = before_width_tweak("Roboto.ttf", size, chars);
        let new = render(&bytes, &req).unwrap();
        // Acceptance of an earlier rendering does not freeze its pixels or
        // outline. Retain the correction's coverage, connectivity and layout
        // contracts while allowing the general model to evolve.
        for (previous, current) in old.iter().zip(&new.records) {
            assert_eq!(previous["codepoint"], current.codepoint);
            assert_baseline_advance(current, previous["advance_26_6"].as_i64().unwrap() as i32);
            assert_eq!(ink_components(current), 1);
            assert!(current.diagonal_pairs.unwrap()[1] > 0);
            let operations: Vec<_> = previous["fitted_commands"]
                .as_array()
                .unwrap()
                .iter()
                .map(|command| command["op"].as_str().unwrap())
                .collect();
            let commands = serde_json::to_value(&current.fitted_commands).unwrap();
            let current_operations: Vec<_> = commands
                .as_array()
                .unwrap()
                .iter()
                .map(|command| command["op"].as_str().unwrap())
                .collect();
            assert_eq!(operations, current_operations);
        }
    }
    let bytes = font("Literata.ttf");
    let mut req = request("Literata.ttf", 18.0, PROFILE_MONO_1BIT);
    req.settings.characters = "vyz".into();
    let upstream = reference(&bytes, &req).unwrap();
    req.extensions = EXTENSIONS_DIAGONAL_01.into();
    let old = before_width_tweak("Literata.ttf", 18.0, "vyz");
    let new = render(&bytes, &req).unwrap();
    for ((a, b), c) in new.records.iter().zip(old).zip(upstream.records) {
        if a.codepoint == 'z' as u32 {
            assert!(a.diagonal_pairs.unwrap()[1] > 0);
            assert_eq!(ink_components(a), 1);
            assert_baseline_advance(a, c.advance_26_6);
        } else {
            // Earlier 001.01 captures retain evidence of the unresolved curve
            // freeze. The terminal-curve correction now fits these strokes;
            // keeping their historical pixels unchanged is no longer a goal.
            assert_eq!(b["diagonal_pairs"], serde_json::json!([2, 0, 2]));
            assert_eq!(a.diagonal_pairs, Some([2, 2, 0]));
            assert_eq!(ink_components(a), 1);
            assert_baseline_advance(a, c.advance_26_6);
        }
    }
}

#[test]
fn reported_literata_y_has_parallel_borders_contrast_and_protected_curve_junctions() {
    let bytes = font("Literata.ttf");
    for size in [14.0, 16.0, 18.0, 20.0] {
        let mut req = request("Literata.ttf", size, PROFILE_MONO_1BIT);
        req.settings.characters = "y".into();
        let baseline = reference(&bytes, &req).unwrap();
        req.extensions = EXTENSIONS_DIAGONAL_01.into();
        let fitted = render(&bytes, &req).unwrap();
        let record = &fitted.records[0];
        assert_eq!(record.diagonal_pairs, Some([2, 2, 0]));
        assert_eq!(ink_components(record), 1);
        assert_baseline_advance(record, baseline.records[0].advance_26_6);
        assert_ne!(record.fitted_commands, baseline.records[0].fitted_commands);
        let commands = serde_json::to_value(&record.fitted_commands).unwrap();
        // Command indices are diagnostic witnesses, never production selectors.
        let border = |i: usize| {
            let a = &commands[i - 1];
            let b = &commands[i];
            assert_eq!(b["op"], "line_to");
            let slope = (b["x"].as_f64().unwrap() - a["x"].as_f64().unwrap())
                / (b["y"].as_f64().unwrap() - a["y"].as_f64().unwrap());
            (
                slope,
                a["x"].as_f64().unwrap() - slope * a["y"].as_f64().unwrap(),
            )
        };
        let mut widths = Vec::new();
        for (left, right) in [(13, 23), (25, 35)] {
            let a = border(left);
            let b = border(right);
            assert!((a.0 - b.0).abs() < 0.01, "Literata {size} y border slopes");
            let slope = (a.0 + b.0) * 0.5;
            widths.push((a.1 - b.1).abs() / (1.0 + slope * slope).sqrt());
        }
        // At 14 px both strokes hit the existing one-pixel axial minimum. At
        // larger sizes, the source thick/thin distinction must remain visible in
        // outline geometry rather than being inferred from total ink counts.
        if size >= 16.0 {
            assert!(widths[0] > widths[1] + 0.5, "Literata {size} y contrast");
        }
    }
    for size in [14.0, 19.0] {
        let mut req = request("Literata.ttf", size, PROFILE_MONO_1BIT);
        req.settings.characters = "k".into();
        let baseline = reference(&bytes, &req).unwrap();
        req.extensions = EXTENSIONS_DIAGONAL_01.into();
        let fitted = render(&bytes, &req).unwrap();
        // Continuous curve junctions remain protected. They cannot acquire the
        // terminal dependency that broke these joins in the unrestricted trial.
        assert_eq!(fitted.records[0].diagonal_pairs, Some([2, 0, 2]));
        assert_axial_structure_and_y_preserved(&fitted.records[0], &baseline.records[0]);
        // The unsupported curved junction contour keeps its shape: the changed
        // upright width carries it by one X translation, without a diagonal solve.
        let actual = serde_json::to_value(&fitted.records[0].fitted_commands).unwrap();
        let expected = serde_json::to_value(&baseline.records[0].fitted_commands).unwrap();
        let translation = actual[0]["x"].as_f64().unwrap() - expected[0]["x"].as_f64().unwrap();
        for (a, b) in actual
            .as_array()
            .unwrap()
            .iter()
            .zip(expected.as_array().unwrap())
        {
            if a["op"] == "close" {
                break;
            }
            for key in ["x", "x1", "x2"] {
                if let (Some(x), Some(y)) = (a[key].as_f64(), b[key].as_f64()) {
                    assert_eq!(x - y, translation, "Literata {size} k protected junction");
                }
            }
        }
    }
}

#[test]
fn stem_relative_sweep_is_deterministic_preserves_line_metrics_gray_and_introduces_no_additional_join_failures(
) {
    let snapshot: Value =
        serde_json::from_str(include_str!("fixtures/diagonal-before-width-tweak.json")).unwrap();
    for name in ["Roboto.ttf", "Literata.ttf", "SourceSans3.ttf"] {
        let bytes = font(name);
        let mut requests: Vec<_> = (14..=20)
            .filter(|s| name != "SourceSans3.ttf" || [14, 16, 18, 20].contains(s))
            .map(|s| request(name, s as f32, PROFILE_MONO_1BIT))
            .collect();
        for size in [16.0, 20.0] {
            for weight in [300.0, 500.0] {
                let mut req = request(name, size, PROFILE_MONO_1BIT);
                req.settings.axes.insert("wght".into(), weight);
                requests.push(req);
            }
        }
        if name == "Literata.ttf" {
            for opsz in [12.0, 24.0] {
                let mut req = request(name, 16.0, PROFILE_MONO_1BIT);
                req.settings.axes.insert("opsz".into(), opsz);
                requests.push(req);
            }
        }
        for mut req in requests {
            let upstream = reference(&bytes, &req).unwrap();
            req.extensions = EXTENSIONS_DIAGONAL_01.into();
            let new = render(&bytes, &req).unwrap();
            req.settings.characters = req.settings.characters.chars().rev().collect();
            let repeat = render(&bytes, &req).unwrap();
            assert_eq!(
                serde_json::to_value(&new).unwrap(),
                serde_json::to_value(repeat).unwrap()
            );
            assert_eq!(new.metrics, upstream.metrics);
            for (a, c) in new.records.iter().zip(&upstream.records) {
                assert_baseline_advance(a, c.advance_26_6);
                assert!(a.pixels.iter().all(|p| *p <= 1));
                if char::from_u32(a.codepoint).unwrap().is_ascii_alphabetic() {
                    // Known failures are historical diagnostic evidence, never production exceptions.
                    let known = snapshot["known_join_failures"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .find(|failure| {
                            failure["font"] == name
                                && failure["size_px"].as_f64() == Some(req.settings.size_px as f64)
                                && failure["axes"]
                                    == serde_json::to_value(&req.settings.axes).unwrap()
                                && failure["glyph"]
                                    == char::from_u32(a.codepoint).unwrap().to_string()
                        });
                    let before = known
                        .map(|failure| failure["components"].as_u64().unwrap() as usize)
                        .unwrap_or(0);
                    assert!(
                        ink_components(a) <= before.max(ink_components(c)),
                        "{name} {} {:?} U+{:04X}",
                        req.settings.size_px,
                        req.settings.axes,
                        a.codepoint
                    );
                }
            }
        }
        for size in [14.0, 16.0, 18.0, 20.0] {
            let mut req = request(name, size, PROFILE_GRAY_3BIT);
            let upstream = reference(&bytes, &req).unwrap();
            req.extensions = EXTENSIONS_DIAGONAL_01.into();
            let new = render(&bytes, &req).unwrap();
            assert_eq!(
                serde_json::to_value(upstream.records).unwrap(),
                serde_json::to_value(new.records).unwrap()
            );
            assert_eq!(new.metrics, upstream.metrics);
        }
    }
}

#[test]
fn reported_literata_q_and_x_fit_general_features_preserving_extrema_and_contrast() {
    let bytes = font("Literata.ttf");
    for size in [14.0, 16.0, 18.0, 20.0] {
        let mut req = request("Literata.ttf", size, PROFILE_MONO_1BIT);
        req.settings.characters = "Qx".into();
        let baseline = reference(&bytes, &req).unwrap();
        req.extensions = EXTENSIONS_DIAGONAL_01.into();
        let fitted = render(&bytes, &req).unwrap();
        for (a, b) in fitted.records.iter().zip(&baseline.records) {
            assert_baseline_advance(a, b.advance_26_6);
            assert_eq!(ink_components(a), 1);
            assert_eq!(
                a.fitted_commands
                    .iter()
                    .map(|c| std::mem::discriminant(c))
                    .collect::<Vec<_>>(),
                b.fitted_commands
                    .iter()
                    .map(|c| std::mem::discriminant(c))
                    .collect::<Vec<_>>()
            );
        }
        let q = &fitted.records[0];
        let count = if size == 20.0 { 2 } else { 3 };
        assert_eq!(q.diagonal_pairs, Some([count, count, 0]));
        let extremes = |r: &ReferenceRecord| {
            let c = serde_json::to_value(&r.fitted_commands).unwrap();
            let ys: Vec<_> = c
                .as_array()
                .unwrap()
                .iter()
                .filter_map(|c| c["y"].as_f64())
                .collect();
            (
                ys.iter().copied().fold(f64::INFINITY, f64::min),
                ys.iter().copied().fold(f64::NEG_INFINITY, f64::max),
            )
        };
        assert_eq!(
            extremes(q),
            extremes(&baseline.records[0]),
            "Literata {size} Q global extrema"
        );
        let x = &fitted.records[1];
        assert_eq!(x.diagonal_pairs, Some([4, 4, 0]));
        let commands = serde_json::to_value(&x.fitted_commands).unwrap();
        let border = |i: usize| {
            let a = &commands[i - 1];
            let b = &commands[i];
            assert_eq!(b["op"], "line_to");
            let slope = (b["x"].as_f64().unwrap() - a["x"].as_f64().unwrap())
                / (b["y"].as_f64().unwrap() - a["y"].as_f64().unwrap());
            (
                slope,
                a["x"].as_f64().unwrap() - slope * a["y"].as_f64().unwrap(),
                a["y"].as_f64().unwrap(),
                b["y"].as_f64().unwrap(),
            )
        };
        let mut widths = Vec::new();
        // Command positions identify witnesses only, never production selectors.
        for (left, right) in [(6, 42), (7, 17), (18, 29), (30, 41)] {
            let a = border(left);
            let b = border(right);
            assert!(
                (a.0 - b.0).abs() < 0.025,
                "Literata {size} x parallel borders"
            );
            let low = a.2.min(a.3).max(b.2.min(b.3));
            let high = a.2.max(a.3).min(b.2.max(b.3));
            let y = (low + high) * 0.5;
            let slope = (a.0 + b.0) * 0.5;
            widths.push(((a.0 - b.0) * y + a.1 - b.1).abs() / (1.0 + slope * slope).sqrt());
        }
        assert!(
            (widths[1] + widths[3]) * 0.5 > (widths[0] + widths[2]) * 0.5 + 0.2,
            "Literata {size} x source thick/thin contrast"
        );
    }
}

#[test]
fn reported_source_sans_inner_diagonals_preserve_caps_layout_and_connectivity() {
    let bytes = font("SourceSans3.ttf");
    let mut req = request("SourceSans3.ttf", 16.0, PROFILE_MONO_1BIT);
    req.settings.characters = "wxy".into();
    let baseline = reference(&bytes, &req).unwrap();
    req.extensions = EXTENSIONS_DIAGONAL_01.into();
    let fitted = render(&bytes, &req).unwrap();
    for (actual, reference) in fitted.records.iter().zip(&baseline.records) {
        assert_baseline_advance(actual, reference.advance_26_6);
        assert_eq!(ink_components(actual), 1);
        assert!(actual.diagonal_pairs.unwrap()[1] > 0);
    }
    let w = &fitted.records[0];
    // The earlier straight-only plan supported two outer pairs. This witness
    // requires actual additional inner coverage, not a preferred ink population.
    assert!(w.diagonal_pairs.unwrap()[1] > 2);
    let commands = serde_json::to_value(&w.fitted_commands).unwrap();
    let previous = serde_json::to_value(&baseline.records[0].fitted_commands).unwrap();
    for (left, right) in [(9, 10), (23, 24)] {
        let a = &commands[left];
        let b = &commands[right];
        assert_eq!(a["y"], b["y"]);
        assert_eq!(a["y"], previous[left]["y"]);
        let old = previous[right]["x"].as_f64().unwrap() - previous[left]["x"].as_f64().unwrap();
        let new = b["x"].as_f64().unwrap() - a["x"].as_f64().unwrap();
        assert!(new * old.signum() >= 0.0, "Source Sans 3 w cap order");
    }
}

#[test]
fn unsupported_two_control_bow_terminal_preserves_reference_join() {
    // A source pair without interior controls can change local width only by
    // moving its shared cap. It lacks this curved-width model's supported shape
    // role; keep the pair unsupported and its join intact under axial refitting.
    let bytes = font("Literata.ttf");
    let mut req = request("Literata.ttf", 17.0, PROFILE_MONO_1BIT);
    req.settings.characters = "c".into();
    let upstream = reference(&bytes, &req).unwrap();
    req.extensions = EXTENSIONS_DIAGONAL_01.into();
    let fitted = render(&bytes, &req).unwrap();
    assert_eq!(fitted.records[0].diagonal_pairs, Some([0, 0, 0]));
    assert_axial_structure_and_y_preserved(&fitted.records[0], &upstream.records[0]);
}

#[test]
fn mono_straight_stem_uses_fractional_shared_width_across_weight_boundary() {
    use skrifa_baseline::{
        outline::{
            autohint::{GlyphStyles, Scale, UnscaledStyleMetrics},
            Target,
        },
        FontRef, MetadataProvider,
    };
    let bytes = font("Roboto.ttf");
    let face = FontRef::new(&bytes).unwrap();
    let outlines = face.outline_glyphs();
    let styles = GlyphStyles::new(&outlines);
    let style = styles
        .get(face.charmap().map('H').unwrap())
        .unwrap()
        .style_class()
        .unwrap();
    let mut widths = Vec::new();
    for weight in [459.0, 460.0] {
        let mut req = request("Roboto.ttf", 14.0, PROFILE_MONO_1BIT);
        req.settings.characters = "H".into();
        req.settings.axes.insert("wght".into(), weight);
        let loc = face.axes().location([("wght", weight), ("wdth", 100.0)]);
        let metrics = UnscaledStyleMetrics::new(&face, loc.coords(), style);
        let scaled = metrics.scale(Scale::new(
            14.0,
            face.metrics(skrifa_baseline::instance::Size::unscaled(), &loc)
                .units_per_em as i32,
            face.attributes().style,
            Target::Mono,
            style.script.group,
        ));
        let standard = scaled.horizontal_metrics().widths()[0].scaled as f64 / 64.0;
        let upstream = reference(&bytes, &req).unwrap();
        req.extensions = EXTENSIONS_DIAGONAL_01.into();
        let fitted = render(&bytes, &req).unwrap();
        let actual = &fitted.records[0];
        assert_eq!(actual.diagonal_pairs, Some([0, 0, 0]));
        assert_axial_structure_and_y_preserved(actual, &upstream.records[0]);
        let commands = serde_json::to_value(&actual.fitted_commands).unwrap();
        // The first upright's opposing borders are geometric witnesses, never
        // production selectors. Its width follows the independently scaled class.
        let width = commands[5]["x"].as_f64().unwrap() - commands[7]["x"].as_f64().unwrap();
        assert_eq!(width, standard);
        widths.push(width);
    }
    // A standard moving one 26.6 unit cannot trigger the former full-pixel fit.
    assert_eq!(widths[1] - widths[0], 1.0 / 64.0);
}
