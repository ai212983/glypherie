use crate::{fail, fixed, Config, Error, Glyph, KerningPair};
use harfrust::{Feature, FontRef, ShapeOptions, ShaperData, ShaperInstance, Tag, UnicodeBuffer};
use unicode_general_category::{get_general_category, GeneralCategory};
use unicode_script::{Script, UnicodeScript};

pub(crate) fn validate_request(ch: char) -> Result<(), Error> {
    if get_general_category(ch) == GeneralCategory::Unassigned {
        Ok(())
    } else {
        validate_character(ch)
    }
}

pub(crate) fn validate_character(ch: char) -> Result<(), Error> {
    let mark = matches!(
        get_general_category(ch),
        GeneralCategory::NonspacingMark
            | GeneralCategory::SpacingMark
            | GeneralCategory::EnclosingMark
            | GeneralCategory::Format
            | GeneralCategory::Control
    );
    if mark
        || !matches!(
            ch.script(),
            Script::Latin | Script::Greek | Script::Cyrillic | Script::Common
        )
    {
        return Err(fail(format!("U+{:04X} requires unsupported text-run shaping; repertoire supports Latin, Greek, Cyrillic and common symbols",ch as u32)));
    }
    Ok(())
}

pub(crate) fn extract(
    data: &[u8],
    config: &Config,
    glyphs: &[Glyph],
) -> Result<Vec<KerningPair>, Error> {
    let font = FontRef::from_index(data, 0).map_err(|e| fail(format!("shaper font: {e}")))?;
    let instance =
        ShaperInstance::from_variations(&font, config.axes.iter().map(|(t, v)| (t.as_str(), *v)));
    let shaping = ShaperData::new(&font);
    let shaper = shaping.shaper(&font).instance(Some(&instance)).build();
    let scale = config.size_px / shaper.units_per_em() as f32;
    let features = [
        Feature::new(Tag::new(b"liga"), 0, ..),
        Feature::new(Tag::new(b"clig"), 0, ..),
        Feature::new(Tag::new(b"calt"), 0, ..),
        Feature::new(Tag::new(b"kern"), u32::from(config.kerning), ..),
    ];
    let shape = |text: &str, expected: &[u32]| -> Result<Vec<i32>, Error> {
        let mut buffer = UnicodeBuffer::new();
        buffer.push_str(text);
        buffer.guess_segment_properties();
        let out = shaper.shape(buffer, ShapeOptions::new().features(&features));
        if out
            .glyph_infos()
            .iter()
            .map(|g| g.glyph_id)
            .ne(expected.iter().copied())
            || out
                .glyph_positions()
                .iter()
                .any(|p| p.x_offset != 0 || p.y_offset != 0 || p.y_advance != 0)
        {
            return Err(fail(format!("text {text:?} requires substitutions or positioning beyond scalar glyphs and pair kerning")));
        }
        Ok(out.glyph_positions().iter().map(|p| p.x_advance).collect())
    };
    let mut singles = Vec::with_capacity(glyphs.len());
    for glyph in glyphs {
        let ch = char::from_u32(glyph.codepoint).unwrap();
        singles.push(shape(&ch.to_string(), &[glyph.glyph_id])?[0]);
    }
    let mut pairs = Vec::new();
    for (i, left) in glyphs.iter().enumerate() {
        for (j, right) in glyphs.iter().enumerate() {
            let text: String = [
                char::from_u32(left.codepoint).unwrap(),
                char::from_u32(right.codepoint).unwrap(),
            ]
            .into_iter()
            .collect();
            let advances = shape(&text, &[left.glyph_id, right.glyph_id])?;
            if advances[1] != singles[j] {
                return Err(fail(format!(
                    "pair {text:?} changes the right advance; requires text-run positioning"
                )));
            }
            let adjustment = fixed(
                (advances[0] - singles[i]) as f32 * scale,
                config.metric_rounding,
            );
            if adjustment != 0 {
                pairs.push(KerningPair {
                    left: left.codepoint,
                    right: right.codepoint,
                    adjustment_26_6: adjustment,
                });
            }
        }
    }
    Ok(pairs)
}
