use crate::{fail, fixed, Config, Error, KerningPair, MetricRounding};
use harfrust::{shape, Buffer, Feature, Font, FontFuncs, ShapeOptions, ShaperFont, Tag};
use skrifa_baseline::MetadataProvider;
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet, HashSet};
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

/// One Unicode scalar resolved to the glyph actually drawn at an exact
/// variation coordinate.
///
/// Source foundation: Required Variation Alternates are coordinate-dependent
/// `GSUB` type 1 (single) substitutions selected through feature variations
/// ([required variation alternates](https://learn.microsoft.com/en-us/typography/opentype/spec/features_pt#tag-rvrn),
/// [GSUB](https://learn.microsoft.com/en-us/typography/opentype/spec/gsub)).
/// The existing HarfRust instance at the exact axes resolves each scalar
/// before outlines are read, so a substituted scalar draws, measures and
/// kerns as its selected glyph. Unicode/codepoint identity is preserved;
/// `glyph_id` records the selected glyph.
pub(crate) struct ResolvedScalar {
    pub codepoint: u32,
    pub glyph_id: u32,
}

/// Observe HarfRust's built-in, unpositioned advances without changing them.
/// The public FontFuncs callback runs after substitution and before positioning:
/// https://docs.rs/harfrust/0.14.0/harfrust/trait.FontFuncs.html
/// Compare within the shaper's own integer domain, avoiding a tolerance between
/// its rounded HVAR/gvar deltas and Skrifa's fractional linear metrics.
#[derive(Default)]
struct ScalarMetrics {
    advances: RefCell<BTreeMap<u32, i32>>,
}

impl FontFuncs for ScalarMetrics {
    fn glyph_h_advance(&self, font: &ShaperFont, glyph: harfrust::GlyphId) -> i32 {
        let advance = font.default_glyph_h_advance(glyph);
        self.advances.borrow_mut().insert(glyph.to_u32(), advance);
        advance
    }
}

/// Shaping features shared by scalar resolution and pair extraction:
/// ligatures and contextual alternates off, pair kerning per configuration.
fn shape_features(kerning: bool) -> [Feature; 4] {
    [
        Feature::new(Tag::new(b"liga"), 0, ..),
        Feature::new(Tag::new(b"clig"), 0, ..),
        Feature::new(Tag::new(b"calt"), 0, ..),
        Feature::new(Tag::new(b"kern"), u32::from(kerning), ..),
    ]
}

/// Resolve each scalar to its coordinate-dependent selected glyph with one
/// reusable shaper at the exact axes.
///
/// Only one-to-one scalar substitutions are accepted: a scalar must shape to
/// exactly one non-`.notdef` glyph with no offsets and no `y_advance`.
/// Anything else (glyph count changes, `.notdef`, offsets or vertical
/// advances) is an explicit shaping error, never a silent fallback.
/// Callers apply their own missing-cmap policy before resolving; a `.notdef`
/// selected glyph for a cmap-present scalar is a shaping error here.
/// Ligatures, contextual alternates and text runs remain unsupported: this
/// resolves isolated scalars only, one `char` at a time.
pub(crate) fn resolve_scalars(
    data: &[u8],
    axes: &BTreeMap<String, f32>,
    kerning: bool,
    chars: &[char],
) -> Result<Vec<ResolvedScalar>, Error> {
    let font = Font::new(data.to_vec(), 0).ok_or_else(|| fail("invalid shaper font"))?;
    let font = font
        .instance_builder()
        .variations(axes.iter().map(|(t, v)| (t.as_str(), *v)))
        .build();
    let features = shape_features(kerning);
    let mut resolved = Vec::with_capacity(chars.len());
    for ch in chars {
        let text = ch.to_string();
        let mut buffer = Buffer::new();
        buffer.push_str(&text);
        buffer.guess_segment_properties();
        let metrics = ScalarMetrics::default();
        let shaper = ShaperFont::new(&font).with_font_funcs(Some(&metrics));
        shape(
            &shaper,
            &mut buffer,
            ShapeOptions::new().features(&features),
        )
        .map_err(|e| fail(format!("shaping failed: {e}")))?;
        if !buffer.allocation_successful() {
            return Err(fail("shaping allocation or operation limit exceeded"));
        }
        let infos = buffer.glyph_infos();
        let positions = buffer.glyph_positions();
        let (info, position) = match (infos, positions) {
            ([info], [position]) => (info, position),
            _ => {
                return Err(fail(format!("text {text:?} requires substitutions or positioning beyond scalar glyphs and pair kerning")));
            }
        };
        if info.glyph_id == 0
            || position.x_offset != 0
            || position.y_offset != 0
            || position.y_advance != 0
            || metrics.advances.borrow().get(&info.glyph_id) != Some(&position.x_advance)
        {
            return Err(fail(format!("text {text:?} requires substitutions or positioning beyond scalar glyphs and pair kerning")));
        }
        resolved.push(ResolvedScalar {
            codepoint: *ch as u32,
            glyph_id: info.glyph_id,
        });
    }
    Ok(resolved)
}

/// Bounded source-font kerning display: horizontal pair adjustments for the
/// printable ASCII subset (U+0020..=U+007E) at one size/axes coordinate.
///
/// Source foundation: the same scalar harfrust shaping path as fitted
/// generation (pair kerning only, ligatures off), evaluated with
/// `kerning = true` and `MetricRounding::Subpixel`. No outlines are drawn and
/// no bitmaps are rasterized. Each scalar is first resolved to its
/// coordinate-dependent selected glyph (see [`resolve_scalars`]); pair
/// shaping then reads each placeholder's codepoint and selected glyph id.
/// Numeric settings reuse
/// `validate_settings` and variation coordinates reuse the shared axis
/// validation; those failures and single-glyph shaping errors stay explicit
/// errors. Codepoints absent from cmap are skipped. Pairs that need more
/// than a scalar left-advance change (further substitutions or text-run
/// positioning) are omitted and reported in `skipped_pairs`, so one
/// contextual pair cannot hide the subset; this display omission changes no
/// layout path. The ASCII scope is explicit: this is not a complete
/// font-table enumeration.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
pub struct AsciiKerning {
    pub pairs: Vec<KerningPair>,
    pub skipped_pairs: u32,
}

pub fn ascii_kerning_pairs(
    data: &[u8],
    size_px: f32,
    axes: &BTreeMap<String, f32>,
) -> Result<AsciiKerning, Error> {
    let config = Config {
        size_px,
        axes: axes.clone(),
        kerning: true,
        metric_rounding: MetricRounding::Subpixel,
        ..Config::default()
    };
    crate::validate_settings(&config)?;
    let font = crate::open_font(data)?;
    crate::validate_axes(&font, &config.axes)?;
    let cmap = font.charmap();
    let mut present = Vec::new();
    for codepoint in 0x20u32..=0x7E {
        let ch = char::from_u32(codepoint).unwrap();
        validate_character(ch)?;
        if cmap.map(ch).is_some_and(|g| g.to_u32() != 0) {
            present.push(ch);
        }
    }
    // Coordinate-dependent single substitutions resolve here, so pair shaping
    // below compares against the glyphs actually drawn at these axes.
    // Single-resolution failures stay explicit errors, like strict generation.
    let resolved = resolve_scalars(data, &config.axes, true, &present)?;
    let (pairs, skipped_pairs) = extract_impl(data, &config, &resolved, false, None)?;
    Ok(AsciiKerning {
        pairs,
        skipped_pairs,
    })
}

pub(crate) fn extract(
    data: &[u8],
    config: &Config,
    identities: &[ResolvedScalar],
) -> Result<Vec<KerningPair>, Error> {
    let (pairs, _) = extract_impl(data, config, identities, true, None)?;
    Ok(pairs)
}

/// Strict isolated-pair extraction for an explicit ordered-pair set.
///
/// Shares [`extract_impl`] with [`extract`] and the ASCII inspection
/// path, so requested pairs are validated with the same strict shape
/// algorithm (isolated pair must keep each scalar's selected glyph and
/// only change the left advance). Unrequested ordered combinations are
/// skipped before shaping or validation; a requested pair with an
/// unsupported substitution or right-advance change remains an error.
#[cfg(any(feature = "native-io", test))]
pub(crate) fn extract_selected(
    data: &[u8],
    config: &Config,
    identities: &[ResolvedScalar],
    requested: &BTreeSet<(u32, u32)>,
) -> Result<Vec<KerningPair>, Error> {
    let (pairs, _) = extract_impl(data, config, identities, true, Some(requested))?;
    Ok(pairs)
}

/// Shared scalar-only shaping body: pair kerning on, ligatures off. Expected
/// glyph ids are the coordinate-selected glyphs from [`resolve_scalars`];
/// singles that no longer match fail here rather than kern against a glyph
/// that is not drawn. Fitted
/// generation (`strict`) keeps the exact previous contract: any pair beyond
/// scalar advances is an error. The ASCII display table (`!strict`) omits
/// such unrepresentable pairs and reports how many, so one contextual pair
/// cannot hide the whole subset; single-glyph failures stay errors in both
/// modes. When `requested` is `Some`, only those ordered pairs are shaped
/// and checked; other combinations are skipped without shaping. Returns
/// the pairs plus the omitted-pair count (zero when strict).
fn extract_impl(
    data: &[u8],
    config: &Config,
    identities: &[ResolvedScalar],
    strict: bool,
    requested: Option<&BTreeSet<(u32, u32)>>,
) -> Result<(Vec<KerningPair>, u32), Error> {
    let font = Font::new(data.to_vec(), 0).ok_or_else(|| fail("invalid shaper font"))?;
    let font = font
        .instance_builder()
        .variations(config.axes.iter().map(|(t, v)| (t.as_str(), *v)))
        .build();
    let shaper = ShaperFont::new(&font);
    let scale = config.size_px / shaper.units_per_em() as f32;
    let features = shape_features(config.kerning);
    let shape = |text: &str, expected: &[u32]| -> Result<Vec<i32>, Error> {
        let mut buffer = Buffer::new();
        buffer.push_str(text);
        buffer.guess_segment_properties();
        shape(
            &shaper,
            &mut buffer,
            ShapeOptions::new().features(&features),
        )
        .map_err(|e| fail(format!("shaping failed: {e}")))?;
        if !buffer.allocation_successful() {
            return Err(fail("shaping allocation or operation limit exceeded"));
        }
        let out = buffer;
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
    // Singles are needed only for identities that participate in a
    // requested pair; unrequested combinations never shape.
    let mut singles: Vec<Option<i32>> = vec![None; identities.len()];
    let needed_codepoints: Option<HashSet<u32>> = requested.map(|filter| {
        let mut needed = HashSet::new();
        for (left, right) in filter {
            needed.insert(*left);
            needed.insert(*right);
        }
        needed
    });
    for (index, identity) in identities.iter().enumerate() {
        let needed = match &needed_codepoints {
            Some(set) => set.contains(&identity.codepoint),
            None => true,
        };
        if !needed {
            continue;
        }
        let ch = char::from_u32(identity.codepoint).unwrap();
        singles[index] = Some(shape(&ch.to_string(), &[identity.glyph_id])?[0]);
    }
    let mut pairs = Vec::new();
    let mut skipped: u32 = 0;
    for (i, left) in identities.iter().enumerate() {
        for (j, right) in identities.iter().enumerate() {
            if let Some(filter) = requested {
                if !filter.contains(&(left.codepoint, right.codepoint)) {
                    continue;
                }
            }
            let text: String = [
                char::from_u32(left.codepoint).unwrap(),
                char::from_u32(right.codepoint).unwrap(),
            ]
            .into_iter()
            .collect();
            let advances = match shape(&text, &[left.glyph_id, right.glyph_id]) {
                Ok(advances) => advances,
                Err(_) if !strict => {
                    skipped += 1;
                    continue;
                }
                Err(error) => return Err(error),
            };
            let single_right = singles[j].expect("requested pair glyph has a single");
            if advances[1] != single_right {
                if !strict {
                    skipped += 1;
                    continue;
                }
                return Err(fail(format!(
                    "pair {text:?} changes the right advance; requires text-run positioning"
                )));
            }
            let single_left = singles[i].expect("requested pair glyph has a single");
            let adjustment = fixed(
                (advances[0] - single_left) as f32 * scale,
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
    Ok((pairs, skipped))
}

#[cfg(test)]
mod tests {
    use super::{extract, extract_selected, resolve_scalars, ResolvedScalar};
    use crate::{Config, MetricRounding};
    use std::collections::{BTreeMap, BTreeSet};

    fn literata() -> Vec<u8> {
        std::fs::read(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../fonts")
                .join("Literata.ttf"),
        )
        .unwrap()
    }

    fn config() -> Config {
        Config {
            size_px: 14.0,
            kerning: true,
            metric_rounding: MetricRounding::Subpixel,
            ..Config::default()
        }
    }

    fn identities(data: &[u8], chars: &[char]) -> Vec<ResolvedScalar> {
        resolve_scalars(data, &BTreeMap::new(), true, chars).unwrap()
    }

    #[test]
    fn selected_extraction_skips_unrequested_unsupported_pairs() {
        let data = literata();
        let cfg = config();
        let repertoire = identities(&data, &['A', '_', '`']);
        // From coverage: the valid ordered pair actually placed is
        // underscore -> grave. Unrequested grave->grave and A->grave
        // must not be shaped or validated.
        let requested = BTreeSet::from([('_' as u32, '`' as u32)]);
        let pairs = extract_selected(&data, &cfg, &repertoire, &requested).unwrap();
        assert!(
            pairs
                .iter()
                .all(|pair| (pair.left, pair.right) != ('`' as u32, '`' as u32)),
            "selected extraction must not invent failures from unrequested pairs"
        );
        // The same repertoire under full-Cartesian extraction still
        // fails, proving the filter is what isolates the requested set.
        assert!(extract(&data, &cfg, &repertoire).is_err());
    }

    #[test]
    fn selected_extraction_still_fails_for_requested_unsupported_pair() {
        let data = literata();
        let cfg = config();
        let repertoire = identities(&data, &['A', '_', '`']);
        let requested = BTreeSet::from([('`' as u32, '`' as u32)]);
        assert!(extract_selected(&data, &cfg, &repertoire, &requested).is_err());
    }

    #[test]
    fn selected_extraction_supports_valid_self_pair() {
        let data = literata();
        let cfg = config();
        let repertoire = identities(&data, &['m']);
        let requested = BTreeSet::from([('m' as u32, 'm' as u32)]);
        let pairs = extract_selected(&data, &cfg, &repertoire, &requested).unwrap();
        // m -> m is the strict isolated pair contract: it shapes as
        // "mm" with the same glyph in both slots; a non-zero kerning
        // value is optional, but the pair must be representable.
        assert!(
            pairs
                .iter()
                .all(|pair| pair.left == 'm' as u32 && pair.right == 'm' as u32),
            "unexpected pairs from m->m extraction: {pairs:?}"
        );
    }
}
