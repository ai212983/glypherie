#![cfg(feature = "candidate")]
//! Executed scan state and component markers follow FreeType 2.15 TT_Hint_Glyph.
//! Geometry equality checks isolate metadata export from the fitting model.
use font_generator::{
    candidate,
    probe::FittedCommand,
    reference::{reference, ReferenceReport, ReferenceRequest},
    Config, Hinting, MonoRasterSettings,
};
use skrifa::{FontRef, MetadataProvider};
use std::{collections::BTreeMap, path::Path};

fn source() -> Vec<u8> {
    std::fs::read(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fonts/SourceSans3.ttf"))
        .unwrap()
}

fn programs(
    prep: &[u8],
    glyph_programs: &[(char, Vec<u8>)],
    composite: Option<Vec<u8>>,
) -> Vec<u8> {
    let data = source();
    let font = FontRef::new(&data).unwrap();
    let table = |tag| {
        font.table_data(skrifa::Tag::new(tag))
            .unwrap()
            .as_bytes()
            .to_vec()
    };
    let mut head = table(b"head");
    let mut maxp = table(b"maxp");
    let glyf = table(b"glyf");
    let loca = table(b"loca");
    let count = u16::from_be_bytes(maxp[4..6].try_into().unwrap()) as usize;
    let long = i16::from_be_bytes(head[50..52].try_into().unwrap()) == 1;
    let offsets: Vec<_> = (0..=count)
        .map(|i| {
            if long {
                u32::from_be_bytes(loca[i * 4..i * 4 + 4].try_into().unwrap()) as usize
            } else {
                u16::from_be_bytes(loca[i * 2..i * 2 + 2].try_into().unwrap()) as usize * 2
            }
        })
        .collect();
    let mut replacements = BTreeMap::new();
    for (ch, program) in glyph_programs {
        let gid = font.charmap().map(*ch).unwrap().to_u32() as usize;
        let raw = &glyf[offsets[gid]..offsets[gid + 1]];
        let contours = i16::from_be_bytes(raw[..2].try_into().unwrap());
        assert!(contours > 0);
        let at = 10 + contours as usize * 2;
        let old = u16::from_be_bytes(raw[at..at + 2].try_into().unwrap()) as usize;
        let mut patched = raw[..at].to_vec();
        patched.extend_from_slice(&(program.len() as u16).to_be_bytes());
        patched.extend_from_slice(program);
        patched.extend_from_slice(&raw[at + 2 + old..]);
        replacements.insert(gid, patched);
    }
    if let Some(program) = composite {
        let gid = font.charmap().map('é').unwrap().to_u32() as usize;
        let mut raw = vec![0xff, 0xff, 0, 0, 0, 0, 8, 0, 8, 0];
        for (i, ch) in ['A', 'B'].iter().enumerate() {
            let flags: u16 = if i == 0 {
                0x23
            } else if program.is_empty() {
                3
            } else {
                0x103
            };
            raw.extend_from_slice(&flags.to_be_bytes());
            raw.extend_from_slice(
                &(font.charmap().map(*ch).unwrap().to_u32() as u16).to_be_bytes(),
            );
            raw.extend_from_slice(&(if i == 0 { 0_i16 } else { 600_i16 }).to_be_bytes());
            raw.extend_from_slice(&0_i16.to_be_bytes());
        }
        if !program.is_empty() {
            raw.extend_from_slice(&(program.len() as u16).to_be_bytes());
            raw.extend_from_slice(&program);
        }
        replacements.insert(gid, raw);
    }
    let mut new_glyf = Vec::new();
    let mut new_loca = Vec::new();
    for i in 0..count {
        new_loca.extend_from_slice(&(new_glyf.len() as u32).to_be_bytes());
        new_glyf.extend_from_slice(
            replacements
                .get(&i)
                .map(Vec::as_slice)
                .unwrap_or(&glyf[offsets[i]..offsets[i + 1]]),
        );
        if new_glyf.len() % 2 != 0 {
            new_glyf.push(0);
        }
    }
    new_loca.extend_from_slice(&(new_glyf.len() as u32).to_be_bytes());
    head[50..52].copy_from_slice(&1_i16.to_be_bytes());
    maxp[24..26].copy_from_slice(&1024_u16.to_be_bytes());
    maxp[26..28].copy_from_slice(&256_u16.to_be_bytes());
    maxp[28..30].copy_from_slice(&8_u16.to_be_bytes());
    maxp[30..32].copy_from_slice(&8_u16.to_be_bytes());
    let overrides = [
        (b"glyf", new_glyf),
        (b"loca", new_loca),
        (b"head", head),
        (b"maxp", maxp),
        (b"prep", prep.to_vec()),
    ];
    let mut builder = write_fonts::FontBuilder::new();
    for record in font.table_directory().table_records() {
        let tag = record.tag();
        if tag == skrifa::Tag::new(b"fpgm") {
            continue;
        }
        if let Some((_, bytes)) = overrides
            .iter()
            .find(|(raw, _)| tag == skrifa::Tag::new(raw))
        {
            builder.add_raw(tag, bytes.clone());
        } else {
            builder.add_raw(tag, font.table_data(tag).unwrap().as_bytes());
        }
    }
    builder.build()
}

fn prep(control: u16, mode: u16) -> Vec<u8> {
    let mut result = vec![0xb8];
    result.extend_from_slice(&control.to_be_bytes());
    result.push(0x85);
    result.extend_from_slice(&push_unsigned(mode));
    result.push(0x8d);
    result
}

fn mode_program(mode: u16) -> Vec<u8> {
    let mut result = push_unsigned(mode);
    result.push(0x8d);
    result
}

fn push_unsigned(value: u16) -> Vec<u8> {
    if value <= i16::MAX as u16 {
        let mut result = vec![0xb8];
        result.extend_from_slice(&value.to_be_bytes());
        result
    } else {
        // PUSHW sign-extends; ADD builds a positive 16-bit operand instead.
        let mut result = vec![0xb9, 0x7f, 0xff, 0x7f, 0xff, 0x60, 0xb8];
        result.extend_from_slice(&((i32::from(value) - 65534) as i16).to_be_bytes());
        result.push(0x60);
        result
    }
}

fn request(chars: &str, size: f32, follow: bool) -> ReferenceRequest {
    ReferenceRequest {
        profile: "mono_1bit".into(),
        extensions: "font-hints-01".into(),
        settings: Config {
            size_px: size,
            characters: chars.into(),
            hinting: Hinting::AutoFallback,
            mono_raster: MonoRasterSettings {
                font_instructions: follow,
                ..Default::default()
            },
            ..Default::default()
        },
    }
}

fn assert_same_geometry(manual: &ReferenceReport, following: &ReferenceReport) {
    assert_eq!(manual.records.len(), following.records.len());
    for (a, b) in manual.records.iter().zip(&following.records) {
        assert_eq!(
            a.fitted_commands, b.fitted_commands,
            "U+{:04X}",
            a.codepoint
        );
        assert_eq!(
            (a.left, a.top, a.width, a.height, a.advance_26_6),
            (b.left, b.top, b.width, b.height, b.advance_26_6)
        );
        assert_eq!(a.hinted_lsb, b.hinted_lsb);
        assert_eq!(a.hinted_advance_width, b.hinted_advance_width);
        assert!(a.font_scan.is_none());
    }
}

#[test]
fn selective_hints_reserve_zero_moves_reads_and_failed_programs() {
    // TrueType's executed projection/freedom vectors, not movement size or
    // final touched flags, determine whether an axis is safe to replace.
    for (program, axes, selected) in [
        (
            vec![0x00, 0xb0, 0, 0x2e, 0x30, 0x31],
            [false, true],
            "auto_x_native_y",
        ),
        (
            vec![0x01, 0xb0, 0, 0x2e, 0x30, 0x31],
            [true, false],
            "native_x_auto_y",
        ),
        (
            vec![0x01, 0xb0, 0, 0x46, 0x21, 0x00, 0xb0, 0, 0x2e],
            [true, true],
            "interpreter",
        ),
        (vec![0x83], [true, true], "interpreter"),
    ] {
        let data = programs(&[], &[('A', program)], None);
        let native = candidate::render(&data, &request("AB", 16., true)).unwrap();
        let mut req = request("AB", 16., true);
        req.extensions = "font-hints-auto-01".into();
        let hybrid = candidate::render(&data, &req).unwrap();
        assert_eq!(
            native.records[0].font_scan.as_ref().unwrap().hinting_axes,
            axes
        );
        assert_eq!(hybrid.records[0].selected_engine, selected);
        if axes == [true, true] {
            assert_eq!(
                hybrid.records[0].fitted_commands,
                native.records[0].fitted_commands
            );
            assert_eq!(hybrid.records[0].pixels, native.records[0].pixels);
        }
        // A program on A does not stop automatic fitting of program-free B.
        assert_eq!(hybrid.records[1].selected_engine, "auto_with_native_scan");
    }
}

#[test]
fn selective_hints_respect_explicit_disable_and_composite_dependencies() {
    for (prep_program, glyph_program, composite) in [
        (vec![0xb1, 1, 1, 0x8e], vec![0x00, 0xb0, 0, 0x2e], None),
        (
            vec![],
            vec![0x00, 0xb0, 0, 0x2e],
            Some(vec![0x00, 0xb0, 0, 0x2e]),
        ),
    ] {
        let data = programs(&prep_program, &[('A', glyph_program)], composite.clone());
        let chars = if composite.is_some() { "é" } else { "A" };
        let native = candidate::render(&data, &request(chars, 16., true)).unwrap();
        let mut req = request(chars, 16., true);
        req.extensions = "font-hints-auto-01".into();
        let hybrid = candidate::render(&data, &req).unwrap();
        assert_eq!(hybrid.records[0].selected_engine, "interpreter");
        assert_eq!(
            hybrid.records[0].fitted_commands,
            native.records[0].fitted_commands
        );
        assert_eq!(hybrid.records[0].pixels, native.records[0].pixels);
    }
}

#[test]
fn prep_threshold_modes_and_glyph_isolation_preserve_registry_geometry() {
    for mode in [0, 1, 2, 3, 4, 5, 6, 7, 8, 65535] {
        let data = programs(&prep(0x110, mode), &[('A', vec![0xb0, 0, 0x21])], None);
        for size in [14., 20.] {
            let manual = candidate::render(&data, &request("AB", size, false)).unwrap();
            let following = candidate::render(&data, &request("AB", size, true)).unwrap();
            assert_same_geometry(&manual, &following);
            for record in &following.records {
                let state = record.font_scan.as_ref().unwrap();
                assert_eq!(state.enabled, size <= 16.);
                assert_eq!(state.scan_type, mode);
                assert_eq!(
                    state.contour_modes.len(),
                    record
                        .fitted_commands
                        .iter()
                        .filter(|x| matches!(x, FittedCommand::MoveTo(..)))
                        .count()
                );
                assert_eq!(
                    state.contour_modes[0],
                    if record.codepoint == 'A' as u32 {
                        Some((mode & 7) as u8)
                    } else {
                        None
                    }
                );
            }
            let repeated = candidate::render(&data, &request("AB", size, true)).unwrap();
            for (a, b) in following.records.iter().zip(&repeated.records) {
                assert_eq!(a.font_scan, b.font_scan);
                assert_eq!(a.pixels, b.pixels);
            }
        }
        if let Ok(dir) = std::env::var("FONT_SCAN_FIXTURE_DIR") {
            std::fs::create_dir_all(&dir).unwrap();
            std::fs::write(Path::new(&dir).join(format!("mode-{mode}.ttf")), data).unwrap();
        }
    }
}

#[test]
fn component_markers_survive_composite_programs() {
    for composite_program in [vec![], mode_program(1)] {
        let data = programs(
            &prep(0x1ff, 5),
            &[('A', mode_program(4)), ('B', mode_program(0))],
            Some(composite_program.clone()),
        );
        let manual = candidate::render(&data, &request("ABé", 16., false)).unwrap();
        let following = candidate::render(&data, &request("ABé", 16., true)).unwrap();
        assert_same_geometry(&manual, &following);
        let a = following
            .records
            .iter()
            .find(|r| r.codepoint == 'A' as u32)
            .unwrap()
            .font_scan
            .as_ref()
            .unwrap();
        let b = following
            .records
            .iter()
            .find(|r| r.codepoint == 'B' as u32)
            .unwrap()
            .font_scan
            .as_ref()
            .unwrap();
        let composite = following
            .records
            .iter()
            .find(|r| r.codepoint == 'é' as u32)
            .unwrap()
            .font_scan
            .as_ref()
            .unwrap();
        assert_eq!(a.contour_modes[0], Some(4));
        assert_eq!(b.contour_modes[0], Some(0));
        let mut expected = a.contour_modes.clone();
        expected.extend_from_slice(&b.contour_modes);
        assert_eq!(composite.contour_modes, expected);
        assert_eq!(
            composite.scan_type,
            if composite_program.is_empty() { 0 } else { 1 }
        );
        if let Ok(dir) = std::env::var("FONT_SCAN_FIXTURE_DIR") {
            std::fs::create_dir_all(&dir).unwrap();
            std::fs::write(
                Path::new(&dir).join(format!("composite-{}.ttf", !composite_program.is_empty())),
                data,
            )
            .unwrap();
        }
    }
}

#[test]
fn automatic_and_cff_use_manual_fallback_without_font_state() {
    for data in [source(), include_bytes!("fixtures/static-cff.otf").to_vec()] {
        let a = candidate::render(&data, &request("A", 16., false)).unwrap();
        let b = candidate::render(&data, &request("A", 16., true)).unwrap();
        assert_same_geometry(&a, &b);
        assert!(b.records[0].font_scan.is_none());
        assert_eq!(a.records[0].pixels, b.records[0].pixels);
    }
}

#[test]
fn corpus_font_mode_keeps_registry_outlines_and_reference_independent() {
    for family in [
        "Roboto",
        "Roboto-Italic",
        "RobotoFlex",
        "Literata",
        "SourceSans3",
    ] {
        let data = std::fs::read(
            Path::new(env!("CARGO_MANIFEST_DIR")).join(format!("../../fonts/{family}.ttf")),
        )
        .unwrap();
        for size in [12., 14., 16., 20.] {
            let mut req = request("Axckwemniu0O8é", size, false);
            let a = candidate::render(&data, &req).unwrap();
            req.settings.mono_raster.font_instructions = true;
            let b = candidate::render(&data, &req).unwrap();
            assert_same_geometry(&a, &b);
            req.extensions = "none".into();
            req.settings.hinting = Hinting::Interpreter;
            assert!(reference(&data, &req).is_err());
        }
    }
}

#[test]
fn evaluation_reconstructs_font_modes_and_rejects_corrupted_state() {
    let data = programs(&prep(0x1ff, 4), &[('A', mode_program(1))], None);
    let req = request("AB", 16., true);
    let captured = candidate::render(&data, &req).unwrap();
    let mut independent = req;
    independent.extensions = "none".into();
    independent.settings.mono_raster = MonoRasterSettings::default();
    independent.settings.hinting = Hinting::Interpreter;
    let upstream = reference(&data, &independent).unwrap();
    independent.settings.hinting = Hinting::None;
    let source = reference(&data, &independent).unwrap();
    let evaluation = font_generator::evaluation::evaluate(&source, &upstream, &captured);
    assert!(
        evaluation.hard_invariants_pass,
        "{:?}",
        evaluation.hard_failures
    );
    let mut corrupt = captured.clone();
    corrupt.records[0].font_scan.as_mut().unwrap().contour_modes[0] = Some(8);
    assert!(
        !font_generator::evaluation::evaluate(&source, &upstream, &corrupt).hard_invariants_pass
    );
    let mut corrupt = captured;
    corrupt.records[0].font_scan.as_mut().unwrap().source_sha256 = "unrecognized".into();
    assert!(
        !font_generator::evaluation::evaluate(&source, &upstream, &corrupt).hard_invariants_pass
    );
}
