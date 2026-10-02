#![cfg(feature = "iteration-01")]

use font_generator::{
    iteration::{capture, render, EXTENSIONS_DIAGONAL_01},
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

#[test]
fn reported_roboto_14_x_and_16_nwxyz_fit_all_pairs_and_stay_connected() {
    let bytes = font("Roboto.ttf");
    for (size, glyphs) in [(14.0, "X"), (16.0, "NWXYZ")] {
        for ch in glyphs.chars() {
            let mut req = request("Roboto.ttf", size, PROFILE_MONO_1BIT);
            req.settings.characters = ch.to_string();
            let upstream = reference(&bytes, &req).unwrap();
            req.extensions = EXTENSIONS_DIAGONAL_01.into();
            let candidate = render(&bytes, &req).unwrap();
            let a = &candidate.records[0];
            let b = &upstream.records[0];
            let [detected, applied, unapplied] = a.diagonal_pairs.unwrap();
            assert!(detected > 0);
            assert_eq!(detected, applied);
            assert_eq!(unapplied, 0);
            // Pixel population is a diagnostic, not a quality objective. The
            // geometric width/contrast and original-correction witnesses below
            // provide fitting evidence independently of a preferred ink count.
            assert_eq!(a.advance_26_6, b.advance_26_6);
            assert_eq!(ink_components(a), 1, "Roboto {size} {ch}");
        }
    }
}

fn without_identity(mut value: Value) -> Value {
    for key in ["implementation", "fork", "dependency_lock_sha256"] {
        value.as_object_mut().unwrap().remove(key);
    }
    value
}

#[test]
fn fork_disabled_matches_independent_upstream_full_corpus_and_modes() {
    for name in ["Roboto.ttf", "Literata.ttf", "SourceSans3.ttf"] {
        let bytes = font(name);
        for size in [14.0, 16.0, 18.0, 20.0] {
            for profile in [PROFILE_MONO_1BIT, PROFILE_GRAY_3BIT] {
                for mode in [Hinting::Auto, Hinting::None, Hinting::Interpreter] {
                    let mut req = request(name, size, profile);
                    req.settings.hinting = mode;
                    let upstream = serde_json::to_value(reference(&bytes, &req).unwrap()).unwrap();
                    let disabled =
                        serde_json::to_value(capture(&bytes, &req, false).unwrap()).unwrap();
                    assert_eq!(
                        without_identity(upstream),
                        without_identity(disabled),
                        "{name} {size} {profile} {mode:?}"
                    );
                }
            }
        }
    }
}

#[test]
fn experimental_corpus_is_deterministic_preserves_layout_and_grayscale() {
    for name in ["Roboto.ttf", "Literata.ttf", "SourceSans3.ttf"] {
        let bytes = font(name);
        for size in [14.0, 16.0, 18.0, 20.0] {
            for profile in [PROFILE_MONO_1BIT, PROFILE_GRAY_3BIT] {
                let mut req = request(name, size, profile);
                let upstream = reference(&bytes, &req).unwrap();
                req.extensions = EXTENSIONS_DIAGONAL_01.into();
                let candidate = render(&bytes, &req).unwrap();
                req.settings.characters = req.settings.characters.chars().rev().collect();
                let repeated = render(&bytes, &req).unwrap();
                assert_eq!(
                    serde_json::to_value(&candidate).unwrap(),
                    serde_json::to_value(&repeated).unwrap()
                );
                assert_eq!(candidate.metrics, upstream.metrics);
                assert_eq!(candidate.records.len(), 95);
                for (a, b) in candidate.records.iter().zip(&upstream.records) {
                    assert_eq!(a.advance_26_6, b.advance_26_6);
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
fn reported_case_has_real_constraints_and_straight_controls_are_unchanged() {
    let bytes = font("Roboto.ttf");
    let mut req = request("Roboto.ttf", 14.0, PROFILE_MONO_1BIT);
    let upstream = reference(&bytes, &req).unwrap();
    req.extensions = EXTENSIONS_DIAGONAL_01.into();
    let candidate = render(&bytes, &req).unwrap();
    for (a, b) in candidate.records.iter().zip(&upstream.records) {
        if "HIn".contains(char::from_u32(a.codepoint).unwrap()) {
            let mut actual = serde_json::to_value(a).unwrap();
            actual.as_object_mut().unwrap().remove("diagonal_pairs");
            assert_eq!(actual, serde_json::to_value(b).unwrap());
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
    let a = candidate
        .records
        .iter()
        .find(|r| r.codepoint == 65)
        .unwrap();
    assert_eq!(a.diagonal_pairs.unwrap(), [2, 2, 0]);
    for ch in "AVvwxyz".chars() {
        let a = candidate
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
fn non_held_validation_and_postscript_formats_preserve_metrics_and_disabled_parity() {
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
            let disabled = capture(&bytes, &req, false).unwrap();
            assert_eq!(
                without_identity(serde_json::to_value(&upstream).unwrap()),
                without_identity(serde_json::to_value(disabled).unwrap())
            );
            req.extensions = EXTENSIONS_DIAGONAL_01.into();
            let candidate = render(&bytes, &req).unwrap();
            assert_eq!(candidate.metrics, upstream.metrics);
            assert!(candidate.missing_codepoints.is_empty());
            assert_eq!(candidate.records.len(), 95);
            for (a, b) in candidate.records.iter().zip(&upstream.records) {
                assert_eq!(a.advance_26_6, b.advance_26_6);
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
    for bytes in [
        include_bytes!("fixtures/static-cff.otf").as_slice(),
        include_bytes!("fixtures/variable-cff2.otf").as_slice(),
    ] {
        for profile in [PROFILE_MONO_1BIT, PROFILE_GRAY_3BIT] {
            let req = ReferenceRequest {
                profile: profile.into(),
                extensions: "none".into(),
                settings: Config {
                    size_px: 14.0,
                    characters: "A".into(),
                    hinting: Hinting::Auto,
                    output_bits: if profile == PROFILE_MONO_1BIT { 1 } else { 3 },
                    ..Config::default()
                },
            };
            assert_eq!(
                without_identity(serde_json::to_value(reference(bytes, &req).unwrap()).unwrap()),
                without_identity(
                    serde_json::to_value(capture(bytes, &req, false).unwrap()).unwrap()
                )
            );
        }
    }
    eprintln!(
        "Non-held join regressions: {}",
        serde_json::to_string(&join_regressions).unwrap()
    );
}

#[test]
fn candidate_single_glyph_records_match_full_ordinary_repertoires() {
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

// These are immutable captures from earlier work within the still-open 001.01.
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
        assert!(
            normal_width(&serde_json::to_value(&new.records[0]).unwrap(), left, right)
                > normal_width(&old[0], left, right) + 0.4,
            "{name} {size} {ch}"
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
            assert_eq!(previous["advance_26_6"], current.advance_26_6);
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
            assert_eq!(a.advance_26_6, c.advance_26_6);
        } else {
            // Earlier 001.01 captures retain evidence of the unresolved curve
            // freeze. The terminal-curve correction now fits these strokes;
            // keeping their historical pixels unchanged is no longer a goal.
            assert_eq!(b["diagonal_pairs"], serde_json::json!([2, 0, 2]));
            assert_eq!(a.diagonal_pairs, Some([2, 2, 0]));
            assert_eq!(ink_components(a), 1);
            assert_eq!(a.advance_26_6, c.advance_26_6);
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
        let candidate = render(&bytes, &req).unwrap();
        let record = &candidate.records[0];
        assert_eq!(record.diagonal_pairs, Some([2, 2, 0]));
        assert_eq!(ink_components(record), 1);
        assert_eq!(record.advance_26_6, baseline.records[0].advance_26_6);
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
        let candidate = render(&bytes, &req).unwrap();
        // Continuous curve junctions remain protected. They cannot acquire the
        // terminal dependency that broke these joins in the unrestricted trial.
        assert_eq!(candidate.records[0].diagonal_pairs, Some([2, 0, 2]));
        assert_eq!(
            candidate.records[0].fitted_commands,
            baseline.records[0].fitted_commands
        );
        assert_eq!(candidate.records[0].pixels, baseline.records[0].pixels);
    }
}

#[test]
fn stem_relative_sweep_is_deterministic_preserves_layout_gray_and_introduces_no_additional_join_failures(
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
                assert_eq!(a.advance_26_6, c.advance_26_6);
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
        let candidate = render(&bytes, &req).unwrap();
        for (a, b) in candidate.records.iter().zip(&baseline.records) {
            assert_eq!(a.advance_26_6, b.advance_26_6);
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
        let q = &candidate.records[0];
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
        let x = &candidate.records[1];
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
    let candidate = render(&bytes, &req).unwrap();
    for (actual, reference) in candidate.records.iter().zip(&baseline.records) {
        assert_eq!(actual.advance_26_6, reference.advance_26_6);
        assert_eq!(ink_components(actual), 1);
        assert!(actual.diagonal_pairs.unwrap()[1] > 0);
    }
    let w = &candidate.records[0];
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
    // role; independent fitting must retain the upstream join instead.
    let bytes = font("Literata.ttf");
    let mut req = request("Literata.ttf", 17.0, PROFILE_MONO_1BIT);
    req.settings.characters = "c".into();
    let upstream = reference(&bytes, &req).unwrap();
    req.extensions = EXTENSIONS_DIAGONAL_01.into();
    let candidate = render(&bytes, &req).unwrap();
    assert_eq!(candidate.records[0].diagonal_pairs, Some([0, 0, 0]));
    assert_eq!(
        candidate.records[0].fitted_commands,
        upstream.records[0].fitted_commands
    );
    assert_eq!(ink_components(&candidate.records[0]), 1);
}
