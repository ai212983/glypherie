use crate::{
    fail, fixed,
    probe::{lock_sha256, lock_version},
    reference::{ReferenceReport, ReferenceRequest},
    specimen_config::{self, RenderCase, RendererRole, VariantKind},
    Config, Error, MetricRounding,
};
use harfrust::{
    Feature, FontRef as ShapingFont, ShapeOptions, ShaperData, ShaperInstance, Tag, UnicodeBuffer,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use skrifa::{instance::Size, FontRef, MetadataProvider};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{Cursor, Write},
    path::{Path, PathBuf},
};

const PADDING: i32 = 8;
const MAX_IMAGE_PIXELS: usize = 16 * 1024 * 1024;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ActivePointer {
    pub schema_version: String,
    pub variant_id: String,
    pub manifest: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema_version: String,
    pub variant: PackageVariant,
    pub profiles: Vec<DisplayProfile>,
    pub families: Vec<FamilyManifest>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DisplayProfile {
    pub id: String,
    pub output_bits: u8,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PackageVariant {
    pub id: String,
    pub kind: VariantKind,
    pub version: Option<String>,
    pub generation_sha256: String,
    pub composition_sha256: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub renderer: Option<RendererRole>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FamilyManifest {
    pub id: String,
    pub name: String,
    pub source_sha256: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub metadata: Option<crate::metadata::FontMetadata>,
    pub sizes: Vec<SizeGroup>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SizeGroup {
    pub size_px: f32,
    pub axes: BTreeMap<String, f32>,
    pub thumbnail: Thumbnail,
    pub items: Vec<Item>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Thumbnail {
    pub width_px: u32,
    pub height_px: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Item {
    pub id: String,
    pub profile: String,
    pub label: String,
    pub text: String,
    pub outcome: Outcome,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub image: Option<Image>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Rendered,
    Failed,
    Unsupported,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Image {
    pub path: String,
    pub sha256: String,
}

#[derive(Debug)]
pub struct Publication {
    pub active: ActivePointer,
    pub packages: Vec<String>,
    pub case_count: usize,
    pub image_count: usize,
    pub failure_count: usize,
}

#[derive(Clone, Debug, Serialize)]
struct Space {
    glyph_id: u32,
    advance_26_6: i32,
}

#[derive(Serialize)]
struct CapturedCase {
    family_id: String,
    size_px: f32,
    axes: BTreeMap<String, f32>,
    profile: String,
    provenance: specimen_config::Provenance,
    space: Option<Space>,
    report: Option<ReferenceReport>,
    reason: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
struct PlacedGlyph {
    codepoint: u32,
    glyph_id: u32,
    x_26_6: i64,
    y_26_6: i64,
    x_px: i32,
    y_px: i32,
    advance_26_6: i32,
}

#[derive(Clone, Debug, Serialize)]
struct Layout {
    glyphs: Vec<PlacedGlyph>,
    bounds: [i32; 4],
    line_height_px: i32,
}

struct Captured {
    case: RenderCase,
    capture: CapturedCase,
    layouts: Vec<Result<Layout, String>>,
}

struct CapturedFonts {
    cases: Vec<Captured>,
    metadata: BTreeMap<String, crate::metadata::FontMetadata>,
}

struct BuiltPackage {
    logical_variant: String,
    manifest: Manifest,
    assets: BTreeMap<String, Vec<u8>>,
    generation: Vec<u8>,
    composition: Vec<u8>,
}

fn io<T>(result: std::io::Result<T>) -> Result<T, Error> {
    result.map_err(|e| fail(e.to_string()))
}
pub(crate) fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub(crate) fn json<T: Serialize>(value: &T) -> Result<Vec<u8>, Error> {
    let mut bytes = serde_json::to_vec(value).map_err(|e| fail(e.to_string()))?;
    bytes.push(b'\n');
    Ok(bytes)
}

fn coordinate(value: i64) -> Result<i32, Error> {
    i32::try_from(value).map_err(|_| fail("layout coordinate exceeds supported range"))
}

fn renderer_identity(role: RendererRole) -> String {
    let mut digest = Sha256::new();
    for source in [
        include_str!("lib.rs"),
        include_str!("reference.rs"),
        include_str!("renderer.rs"),
        include_str!("probe.rs"),
        include_str!("raster.rs"),
        include_str!("spacing.rs"),
    ] {
        digest.update((source.len() as u64).to_le_bytes());
        digest.update(source.as_bytes());
    }
    let (adapter, source) = match role {
        RendererRole::Reference => ("", ""),
        RendererRole::Baseline => (include_str!("baseline.rs"), env!("SKRIFA_BASELINE_SHA256")),
        RendererRole::Candidate => (
            include_str!("candidate.rs"),
            env!("SKRIFA_CANDIDATE_SHA256"),
        ),
    };
    digest.update(adapter.as_bytes());
    digest.update(source.as_bytes());
    if role != RendererRole::Reference {
        digest.update(include_str!("fitting.rs").as_bytes());
    }
    format!("{digest:x}", digest = digest.finalize())
}

fn effective_axes(data: &[u8], case: &RenderCase) -> Result<BTreeMap<String, f32>, Error> {
    let font = FontRef::new(data)
        .map_err(|e| fail(format!("invalid font for {}: {e}", case.family_id)))?;
    let mut axes = BTreeMap::new();
    for axis in font.axes().iter() {
        let tag = axis.tag().to_string();
        let value = case.axes.get(&tag).copied().unwrap_or(axis.default_value());
        if value < axis.min_value() || value > axis.max_value() {
            return Err(fail(format!(
                "axis {tag} out of range for {}",
                case.family_id
            )));
        }
        axes.insert(tag, value);
    }
    if let Some(tag) = case.axes.keys().find(|tag| !axes.contains_key(*tag)) {
        return Err(fail(format!(
            "unsupported axis {tag} for {}",
            case.family_id
        )));
    }
    Ok(axes)
}

fn guard_reserved(checksum: &str, case: &RenderCase) -> Result<(), Error> {
    let reserved = match checksum {
        "042fe2cc0b933e328410d7acbd0aa6a1873dca5aef81875f4bc214b08825c7b9" => {
            [22.0, 23.0].contains(&case.size_px)
                || (case.axes.get("wght") == Some(&400.0)
                    && [15.0, 17.0, 19.0, 21.0].contains(&case.size_px))
        }
        "d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134"
        | "b41138c9373112f32abb589cc22e8674b06ed4048b0c513be922bdd26f274440" => {
            [22.0, 23.0].contains(&case.size_px)
        }
        _ => false,
    };
    if reserved {
        return Err(fail(format!("{} at {} px is a reserved evaluation slice; use the separately authorized evaluation workflow", case.family_id, case.size_px)));
    }
    Ok(())
}

fn space(data: &[u8], case: &RenderCase) -> Result<Option<Space>, Error> {
    let font = FontRef::new(data).map_err(|e| fail(e.to_string()))?;
    let Some(gid) = font.charmap().map(' ').filter(|g| g.to_u32() != 0) else {
        return Ok(None);
    };
    let location = font
        .axes()
        .location(case.axes.iter().map(|(tag, value)| (tag.as_str(), *value)));
    let advance = font
        .glyph_metrics(Size::new(case.size_px), &location)
        .advance_width(gid)
        .ok_or_else(|| fail("missing source space advance"))?;
    Ok(Some(Space {
        glyph_id: gid.to_u32(),
        advance_26_6: fixed(advance, MetricRounding::Subpixel),
    }))
}

fn layout(
    data: &[u8],
    report: &ReferenceReport,
    space: Option<&Space>,
    text: &str,
) -> Result<Layout, Error> {
    let font = ShapingFont::from_index(data, 0).map_err(|e| fail(format!("shaper font: {e}")))?;
    let instance = ShaperInstance::from_variations(
        &font,
        report
            .axes
            .iter()
            .map(|(tag, value)| (tag.as_str(), *value)),
    );
    let shaping = ShaperData::new(&font);
    let shaper = shaping.shaper(&font).instance(Some(&instance)).build();
    let scale = report.size_px / shaper.units_per_em() as f32;
    let features = [
        Feature::new(Tag::new(b"liga"), 0, ..),
        Feature::new(Tag::new(b"clig"), 0, ..),
        Feature::new(Tag::new(b"calt"), 0, ..),
        Feature::new(Tag::new(b"kern"), 1, ..),
    ];
    let records: BTreeMap<_, _> = report
        .records
        .iter()
        .map(|record| (record.codepoint, record))
        .collect();
    let metrics = &report.metrics;
    let line_height = coordinate(
        ((i64::from(metrics.ascent_26_6) - i64::from(metrics.descent_26_6)
            + i64::from(metrics.line_gap_26_6)
            + 63)
            / 64)
            .max(1),
    )?;
    let mut glyphs = Vec::new();
    let mut bounds = [0, 0, 0, 0];
    let mut singles = BTreeMap::new();
    for (line_index, line) in text.split('\n').enumerate() {
        let chars: Vec<_> = line.chars().collect();
        let nominal: Vec<_> = chars
            .iter()
            .map(|ch| {
                if *ch == ' ' {
                    space
                        .map(|s| s.glyph_id)
                        .ok_or_else(|| fail("missing source space glyph"))
                } else {
                    records
                        .get(&(*ch as u32))
                        .map(|r| r.glyph_id)
                        .ok_or_else(|| fail(format!("missing sample glyph U+{:04X}", *ch as u32)))
                }
            })
            .collect::<Result<_, _>>()?;
        let mut buffer = UnicodeBuffer::new();
        buffer.push_str(line);
        buffer.guess_segment_properties();
        let shaped = shaper.shape(buffer, ShapeOptions::new().features(&features));
        if shaped
            .glyph_infos()
            .iter()
            .map(|info| info.glyph_id)
            .ne(nominal.iter().copied())
            || shaped
                .glyph_positions()
                .iter()
                .any(|pos| pos.x_offset != 0 || pos.y_offset != 0 || pos.y_advance != 0)
        {
            return Err(fail(
                "sample requires unsupported substitutions or offset positioning",
            ));
        }
        let baseline = coordinate(line_index as i64 * i64::from(line_height))?;
        bounds[1] = bounds[1].min(coordinate(
            i64::from(baseline) - (i64::from(metrics.ascent_26_6) + 63).div_euclid(64),
        )?);
        bounds[3] = bounds[3].max(coordinate(
            i64::from(baseline) - i64::from(metrics.descent_26_6).div_euclid(64),
        )?);
        let mut pen = 0_i64;
        for ((ch, gid), position) in chars.iter().zip(&nominal).zip(shaped.glyph_positions()) {
            let single = if let Some(advance) = singles.get(ch) {
                *advance
            } else {
                let mut buffer = UnicodeBuffer::new();
                buffer.push_str(&ch.to_string());
                buffer.guess_segment_properties();
                let result = shaper.shape(buffer, ShapeOptions::new().features(&features));
                if result.glyph_infos().len() != 1 || result.glyph_infos()[0].glyph_id != *gid {
                    return Err(fail("sample scalar requires unsupported substitution"));
                }
                let advance = result.glyph_positions()[0].x_advance;
                singles.insert(*ch, advance);
                advance
            };
            let linear = if *ch == ' ' {
                space.unwrap().advance_26_6
            } else {
                records[&(*ch as u32)].advance_26_6
            };
            let adjustment = fixed(
                (i64::from(position.x_advance) - i64::from(single)) as f32 * scale,
                MetricRounding::Subpixel,
            );
            let advance = linear
                .checked_add(adjustment)
                .ok_or_else(|| fail("layout advance overflow"))?;
            let x = i32::try_from((pen + 32).div_euclid(64))
                .map_err(|_| fail("layout position overflow"))?;
            if *ch != ' ' {
                let record = records[&(*ch as u32)];
                bounds[0] = bounds[0].min(coordinate(i64::from(x) + i64::from(record.left))?);
                bounds[1] = bounds[1].min(coordinate(i64::from(baseline) + i64::from(record.top))?);
                bounds[2] = bounds[2].max(coordinate(
                    i64::from(x) + i64::from(record.left) + i64::from(record.width),
                )?);
                bounds[3] = bounds[3].max(coordinate(
                    i64::from(baseline) + i64::from(record.top) + i64::from(record.height),
                )?);
            }
            glyphs.push(PlacedGlyph {
                codepoint: *ch as u32,
                glyph_id: *gid,
                x_26_6: pen,
                y_26_6: i64::from(baseline) * 64,
                x_px: x,
                y_px: baseline,
                advance_26_6: advance,
            });
            pen += i64::from(advance);
            bounds[2] = bounds[2].max(
                i32::try_from((pen + 63).div_euclid(64))
                    .map_err(|_| fail("layout extent overflow"))?,
            );
        }
    }
    Ok(Layout {
        glyphs,
        bounds,
        line_height_px: line_height,
    })
}

fn encode_png(pixels: &[u8], thumbnail: &Thumbnail) -> Result<Vec<u8>, Error> {
    let mut bytes = Vec::new();
    let mut encoder = png::Encoder::new(&mut bytes, thumbnail.width_px, thumbnail.height_px);
    encoder.set_color(png::ColorType::Grayscale);
    encoder.set_depth(png::BitDepth::Eight);
    let mut writer = encoder
        .write_header()
        .map_err(|e| fail(format!("PNG header: {e}")))?;
    writer
        .write_image_data(pixels)
        .map_err(|e| fail(format!("PNG encoding: {e}")))?;
    writer
        .finish()
        .map_err(|e| fail(format!("PNG finish: {e}")))?;
    Ok(bytes)
}

fn compose(
    report: &ReferenceReport,
    layout: &Layout,
    bounds: [i32; 4],
    thumbnail: &Thumbnail,
) -> Result<Vec<u8>, Error> {
    let count = (thumbnail.width_px as usize)
        .checked_mul(thumbnail.height_px as usize)
        .filter(|n| *n <= MAX_IMAGE_PIXELS)
        .ok_or_else(|| fail("specimen canvas exceeds allocation limit"))?;
    let mut ink = vec![0_u8; count];
    let levels = (1_u16 << report.records[0].output_bits) - 1;
    let records: BTreeMap<_, _> = report
        .records
        .iter()
        .map(|record| (record.codepoint, record))
        .collect();
    for glyph in &layout.glyphs {
        if glyph.codepoint == 32 {
            continue;
        }
        let record = records[&glyph.codepoint];
        for y in 0..record.height {
            for x in 0..record.width {
                let px = i64::from(glyph.x_px) + i64::from(record.left) + i64::from(x)
                    - i64::from(bounds[0])
                    + i64::from(PADDING);
                let py = i64::from(glyph.y_px) + i64::from(record.top) + i64::from(y)
                    - i64::from(bounds[1])
                    + i64::from(PADDING);
                if px < 0
                    || py < 0
                    || px >= i64::from(thumbnail.width_px)
                    || py >= i64::from(thumbnail.height_px)
                {
                    return Err(fail("specimen bounds would clip generated pixels"));
                }
                let destination = py as usize * thumbnail.width_px as usize + px as usize;
                ink[destination] = ink[destination]
                    .max(record.pixels[y as usize * record.width as usize + x as usize]);
            }
        }
    }
    let pixels: Vec<_> = ink
        .into_iter()
        .map(|q| 255 - ((u16::from(q) * 255 + levels / 2) / levels) as u8)
        .collect();
    encode_png(&pixels, thumbnail)
}

fn capture(loaded: &specimen_config::LoadedSpecimens) -> Result<CapturedFonts, Error> {
    let mut fonts = BTreeMap::new();
    let mut metadata = BTreeMap::new();
    for family in &loaded.config.families {
        let path = loaded
            .cases
            .iter()
            .find(|case| case.family_id == family.id)
            .unwrap()
            .font
            .clone();
        let bytes = io(fs::read(path))?;
        if hash(&bytes) != family.provenance.expected_sha256 {
            return Err(fail(format!("font checksum mismatch for {}", family.id)));
        }
        metadata.insert(family.id.clone(), crate::metadata::extract(&bytes)?);
        fonts.insert(family.id.as_str(), bytes);
    }
    let mut cases = loaded.cases.clone();
    for case in &mut cases {
        case.axes = effective_axes(&fonts[case.family_id.as_str()], case)?;
        guard_reserved(&hash(&fonts[case.family_id.as_str()]), case)?;
    }
    let mut captured = Vec::new();
    for case in cases {
        let data = &fonts[case.family_id.as_str()];
        let variant = loaded
            .config
            .variants
            .iter()
            .find(|v| v.id == case.variant)
            .unwrap();
        let profile = loaded
            .config
            .profiles
            .iter()
            .find(|p| p.id == case.profile)
            .unwrap();
        let family = loaded
            .config
            .families
            .iter()
            .find(|f| f.id == case.family_id)
            .unwrap();
        let space = space(data, &case)?;
        let settings = Config {
            size_px: case.size_px,
            axes: case.axes.clone(),
            hinting: variant.hinting,
            output_bits: profile.output_bits,
            mono_threshold: profile.mono_threshold,
            gray_gamma: profile.gray_gamma,
            characters: loaded.config.characters.clone(),
            ..Config::default()
        };
        let request = ReferenceRequest {
            profile: case.profile.clone(),
            extensions: variant.extensions.clone(),
            settings,
        };
        let result = crate::renderer::render(data, &request, variant.renderer());
        let (report, reason) = match result {
            Ok(report) => (Some(report), None),
            Err(error) => (None, Some(error.to_string())),
        };
        let layouts = loaded
            .config
            .samples
            .iter()
            .map(|sample| match &report {
                Some(report) => {
                    layout(data, report, space.as_ref(), &sample.text).map_err(|e| e.to_string())
                }
                None => Err(reason.clone().unwrap()),
            })
            .collect();
        let capture = CapturedCase {
            family_id: case.family_id.clone(),
            size_px: case.size_px,
            axes: case.axes.clone(),
            profile: case.profile.clone(),
            provenance: family.provenance.clone(),
            space,
            report,
            reason,
        };
        captured.push(Captured {
            case,
            capture,
            layouts,
        });
    }
    Ok(CapturedFonts {
        cases: captured,
        metadata,
    })
}

fn build_packages(
    loaded: &specimen_config::LoadedSpecimens,
    captures: &[Captured],
    metadata: &BTreeMap<String, crate::metadata::FontMetadata>,
) -> Result<Vec<BuiltPackage>, Error> {
    let mut packages = Vec::new();
    for variant in &loaded.config.variants {
        let selected: Vec<_> = captures
            .iter()
            .filter(|capture| capture.case.variant == variant.id)
            .collect();
        if selected.is_empty() {
            continue;
        }
        let profiles: Vec<_> = loaded
            .config
            .profiles
            .iter()
            .filter(|p| selected.iter().any(|c| c.case.profile == p.id))
            .cloned()
            .collect();
        let generation = json(&serde_json::json!({
            "schema_version": "specimen-render-v1", "generator_version": env!("CARGO_PKG_VERSION"),
            "implementation_sha256": renderer_identity(variant.renderer()), "dependency_lock_sha256": lock_sha256(),
            "variant": variant, "profiles": profiles, "characters": loaded.config.characters,
            "cases": selected.iter().map(|c| &c.capture).collect::<Vec<_>>()
        }))?;
        let generation_sha256 = hash(&generation);
        let mut families = Vec::new();
        let mut assets = BTreeMap::new();
        let mut compositions = Vec::new();
        for family in &loaded.config.families {
            let selected: Vec<_> = selected
                .iter()
                .copied()
                .filter(|capture| capture.case.family_id == family.id)
                .collect();
            if selected.is_empty() {
                continue;
            }
            let mut sizes: Vec<f32> = selected
                .iter()
                .map(|capture| capture.case.size_px)
                .collect();
            sizes.sort_by(f32::total_cmp);
            sizes.dedup();
            let mut groups = Vec::new();
            for size in sizes {
                let group: Vec<_> = selected
                    .iter()
                    .copied()
                    .filter(|capture| capture.case.size_px == size)
                    .collect();
                let mut bounds = [0_i32; 4];
                for capture in &group {
                    for layout in capture.layouts.iter().flatten() {
                        bounds[0] = bounds[0].min(layout.bounds[0]);
                        bounds[1] = bounds[1].min(layout.bounds[1]);
                        bounds[2] = bounds[2].max(layout.bounds[2]);
                        bounds[3] = bounds[3].max(layout.bounds[3]);
                    }
                }
                let width = i64::from(bounds[2]) - i64::from(bounds[0]) + i64::from(PADDING) * 2;
                let height = i64::from(bounds[3]) - i64::from(bounds[1]) + i64::from(PADDING) * 2;
                if width
                    .checked_mul(height)
                    .is_none_or(|pixels| pixels > MAX_IMAGE_PIXELS as i64)
                {
                    return Err(fail("specimen canvas exceeds allocation limit"));
                }
                let thumbnail = Thumbnail {
                    width_px: width as u32,
                    height_px: height as u32,
                };
                let mut items = Vec::new();
                for capture in &group {
                    for (sample, layout) in loaded.config.samples.iter().zip(&capture.layouts) {
                        let (outcome, image, reason) = match layout {
                            Ok(layout) => {
                                let bytes = compose(
                                    capture.capture.report.as_ref().unwrap(),
                                    layout,
                                    bounds,
                                    &thumbnail,
                                )?;
                                let sha256 = hash(&bytes);
                                let name = format!("{sha256}.png");
                                assets.insert(name.clone(), bytes);
                                (
                                    Outcome::Rendered,
                                    Some(Image {
                                        path: format!("assets/{name}"),
                                        sha256,
                                    }),
                                    None,
                                )
                            }
                            Err(reason) => (
                                if reason.contains("unsupported") {
                                    Outcome::Unsupported
                                } else {
                                    Outcome::Failed
                                },
                                None,
                                Some(reason.clone()),
                            ),
                        };
                        items.push(Item {
                            id: format!(
                                "{}-{}-{}-{}",
                                family.id, size, capture.case.profile, sample.id
                            ),
                            profile: capture.case.profile.clone(),
                            label: sample.label.clone(),
                            text: sample.text.clone(),
                            outcome,
                            image,
                            reason,
                        });
                        compositions.push(serde_json::json!({ "family_id": family.id, "size_px": size, "profile": capture.case.profile, "sample": sample,
                        "layout": layout.as_ref().ok(), "reason": layout.as_ref().err(), "group_bounds": bounds, "thumbnail": thumbnail }));
                    }
                }
                groups.push(SizeGroup {
                    size_px: size,
                    axes: group[0].case.axes.clone(),
                    thumbnail,
                    items,
                });
            }
            families.push(FamilyManifest {
                id: family.id.clone(),
                name: family.name.clone(),
                source_sha256: family.provenance.expected_sha256.clone(),
                metadata: Some(metadata[&family.id].clone()),
                sizes: groups,
            });
        }
        let composition = json(&serde_json::json!({
            "schema_version": "specimen-composition-v1", "generation_sha256": generation_sha256,
            "implementation_sha256": hash(include_bytes!("specimens.rs")), "harfrust_version": lock_version("harfrust"),
            "layout_policy": "canonical-linear-26.6-plus-harfrust-run-adjustments",
            "features": {"kern": true, "liga": false, "clig": false, "calt": false},
            "origin_rounding": "nearest-pixel-half-toward-positive", "overlap": "maximum-ink", "padding_px": PADDING,
            "palette": "255-round(level*255/(2^output_bits-1))", "items": compositions
        }))?;
        let mut manifest = Manifest {
            schema_version: "web-specimens-v1".into(),
            variant: PackageVariant {
                id: String::new(),
                kind: variant.kind,
                renderer: variant.renderer,
                version: variant.version.clone(),
                generation_sha256,
                composition_sha256: hash(&composition),
            },
            profiles: profiles
                .iter()
                .map(|profile| DisplayProfile {
                    id: profile.id.clone(),
                    output_bits: profile.output_bits,
                })
                .collect(),
            families,
        };
        manifest.variant.id = format!("{}-{}", variant.id, hash(&json(&manifest)?));
        packages.push(BuiltPackage {
            logical_variant: variant.id.clone(),
            manifest,
            assets,
            generation,
            composition,
        });
    }
    Ok(packages)
}

pub(crate) fn regular(path: &Path) -> Result<(), Error> {
    let metadata = io(fs::symlink_metadata(path))?;
    if !metadata.file_type().is_file() {
        return Err(fail(format!("expected a regular file: {}", path.display())));
    }
    Ok(())
}

pub(crate) fn directory(path: &Path) -> Result<(), Error> {
    if !path.exists() {
        io(fs::create_dir_all(path))?;
    }
    require_directory(path)
}

pub(crate) fn require_directory(path: &Path) -> Result<(), Error> {
    if !io(fs::symlink_metadata(path))?.file_type().is_dir() {
        return Err(fail(format!("expected a directory: {}", path.display())));
    }
    Ok(())
}

pub(crate) fn immutable_file(path: &Path, bytes: &[u8]) -> Result<(), Error> {
    if path.exists() || path.is_symlink() {
        regular(path)?;
        if io(fs::read(path))? != bytes {
            return Err(fail(format!(
                "immutable artifact differs: {}",
                path.display()
            )));
        }
        return Ok(());
    }
    let mut temp = io(tempfile::NamedTempFile::new_in(path.parent().unwrap()))?;
    io(temp.write_all(bytes))?;
    io(temp.as_file().sync_all())?;
    temp.persist_noclobber(path)
        .map_err(|e| fail(e.to_string()))?;
    Ok(())
}

pub fn validate_package(path: &Path, manifest: &Manifest) -> Result<(), Error> {
    require_directory(path)?;
    regular(&path.join("manifest.json"))?;
    let bytes = io(fs::read(path.join("manifest.json")))?;
    if bytes != json(manifest)? {
        return Err(fail("published manifest differs from expected package"));
    }
    if manifest.schema_version != "web-specimens-v1" || manifest.families.is_empty() {
        return Err(fail("invalid specimen manifest"));
    }
    let valid_hash = |value: &str| {
        value.len() == 64
            && value
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    };
    if !valid_hash(&manifest.variant.generation_sha256)
        || !valid_hash(&manifest.variant.composition_sha256)
        || manifest.profiles.is_empty()
    {
        return Err(fail("invalid specimen identities or profiles"));
    }
    let mut profile_ids = BTreeSet::new();
    for profile in &manifest.profiles {
        if !profile_ids.insert(&profile.id)
            || !matches!(
                (profile.id.as_str(), profile.output_bits),
                ("mono_1bit", 1) | ("gray_3bit", 3)
            )
        {
            return Err(fail("invalid or duplicate specimen profile"));
        }
    }
    let profiles: BTreeMap<_, _> = manifest
        .profiles
        .iter()
        .map(|p| (p.id.as_str(), p.output_bits))
        .collect();
    let mut ids = BTreeSet::new();
    let mut family_ids = BTreeSet::new();
    for family in &manifest.families {
        if !family_ids.insert(&family.id)
            || family.sizes.is_empty()
            || !valid_hash(&family.source_sha256)
        {
            return Err(fail("invalid or duplicate specimen family"));
        }
        let mut sizes = BTreeSet::new();
        for group in &family.sizes {
            if !group.size_px.is_finite()
                || !(1.0..=512.0).contains(&group.size_px)
                || !sizes.insert(group.size_px.to_bits())
                || group.thumbnail.width_px == 0
                || group.thumbnail.height_px == 0
                || group.items.is_empty()
                || group
                    .axes
                    .iter()
                    .any(|(tag, value)| tag.len() != 4 || !tag.is_ascii() || !value.is_finite())
            {
                return Err(fail("invalid or duplicate specimen size group"));
            }
            for item in &group.items {
                if !ids.insert(&item.id) {
                    return Err(fail("duplicate specimen item ID"));
                }
                let bits = *profiles
                    .get(item.profile.as_str())
                    .ok_or_else(|| fail("unknown item profile"))?;
                match item.outcome {
                    Outcome::Rendered => {
                        let image = item
                            .image
                            .as_ref()
                            .ok_or_else(|| fail("rendered item missing image"))?;
                        if image.sha256.len() != 64
                            || !image
                                .sha256
                                .bytes()
                                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
                            || image.path != format!("assets/{}.png", image.sha256)
                            || item.reason.is_some()
                        {
                            return Err(fail("invalid specimen image reference"));
                        }
                        require_directory(&path.join("assets"))?;
                        let file = path.join(&image.path);
                        regular(&file)?;
                        let bytes = io(fs::read(&file))?;
                        if hash(&bytes) != image.sha256 {
                            return Err(fail("specimen PNG checksum mismatch"));
                        }
                        let mut reader = png::Decoder::new(Cursor::new(bytes))
                            .read_info()
                            .map_err(|e| fail(e.to_string()))?;
                        let count = reader
                            .output_buffer_size()
                            .filter(|n| *n <= MAX_IMAGE_PIXELS)
                            .ok_or_else(|| fail("PNG allocation exceeds limit"))?;
                        let mut pixels = vec![0; count];
                        let info = reader
                            .next_frame(&mut pixels)
                            .map_err(|e| fail(e.to_string()))?;
                        if info.width != group.thumbnail.width_px
                            || info.height != group.thumbnail.height_px
                            || info.color_type != png::ColorType::Grayscale
                            || info.bit_depth != png::BitDepth::Eight
                        {
                            return Err(fail("PNG dimensions or format mismatch"));
                        }
                        let levels = (1_u16 << bits) - 1;
                        let palette: BTreeSet<u8> = (0..=levels)
                            .map(|q| 255 - ((q * 255 + levels / 2) / levels) as u8)
                            .collect();
                        if pixels[..info.buffer_size()]
                            .iter()
                            .any(|p| !palette.contains(p))
                        {
                            return Err(fail("PNG contains unexpected display levels"));
                        }
                    }
                    Outcome::Failed | Outcome::Unsupported => {
                        if item.image.is_some()
                            || item.reason.as_ref().is_none_or(|r| r.trim().is_empty())
                        {
                            return Err(fail("invalid failed/unsupported item"));
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

struct PublishLock(PathBuf);
impl Drop for PublishLock {
    fn drop(&mut self) {
        let _ = fs::remove_dir(&self.0);
    }
}

pub fn publish(config_path: &Path, output: &Path) -> Result<Publication, Error> {
    let loaded = specimen_config::load(config_path)?;
    let latest = loaded.config.latest_variant()?;
    let pointer_path = output.join("active.json");
    if pointer_path.exists() {
        regular(&pointer_path)?;
        let destination = io(fs::canonicalize(&pointer_path))?;
        for input in std::iter::once(config_path.to_path_buf())
            .chain(loaded.cases.iter().map(|case| case.font.clone()))
        {
            if io(fs::canonicalize(input))? == destination {
                return Err(fail(
                    "active pointer must differ from config and font inputs",
                ));
            }
        }
    }
    let captures = capture(&loaded)?;
    let packages = build_packages(&loaded, &captures.cases, &captures.metadata)?;
    directory(output)?;
    let output = io(fs::canonicalize(output))?;
    let lock_path = output.join(".publishing");
    io(fs::create_dir(&lock_path))
        .map_err(|_| fail("specimen publication is locked; another publisher may be running"))?;
    let _lock = PublishLock(lock_path);
    let canonical_dir = output.join("canonical");
    directory(&canonical_dir)?;
    let mut active = None;
    for package in &packages {
        immutable_file(
            &canonical_dir.join(format!(
                "{}.json",
                package.manifest.variant.generation_sha256
            )),
            &package.generation,
        )?;
        immutable_file(
            &canonical_dir.join(format!(
                "{}.json",
                package.manifest.variant.composition_sha256
            )),
            &package.composition,
        )?;
        let destination = output.join(&package.manifest.variant.id);
        if destination.exists() || destination.is_symlink() {
            validate_package(&destination, &package.manifest)?;
        } else {
            let staging = io(tempfile::Builder::new()
                .prefix(".staging-")
                .tempdir_in(&output))?;
            let assets_dir = staging.path().join("assets");
            directory(&assets_dir)?;
            for (name, bytes) in &package.assets {
                immutable_file(&assets_dir.join(name), bytes)?;
            }
            immutable_file(
                &staging.path().join("manifest.json"),
                &json(&package.manifest)?,
            )?;
            validate_package(staging.path(), &package.manifest)?;
            io(io(fs::File::open(&assets_dir))?.sync_all())?;
            io(io(fs::File::open(staging.path()))?.sync_all())?;
            io(fs::rename(staging.path(), &destination))?;
            io(fs::File::open(&output))?
                .sync_all()
                .map_err(|e| fail(e.to_string()))?;
        }
        if package.logical_variant == latest {
            active = Some(ActivePointer {
                schema_version: "web-active-v1".into(),
                variant_id: package.manifest.variant.id.clone(),
                manifest: format!("{}/manifest.json", package.manifest.variant.id),
            });
        }
    }
    let active = active.ok_or_else(|| fail("active package missing"))?;
    io(io(fs::File::open(&canonical_dir))?.sync_all())?;
    let published: BTreeMap<_, _> = packages
        .iter()
        .map(|p| (&p.logical_variant, &p.manifest.variant.id))
        .collect();
    atomic_file(
        &output.join("published.json"),
        &json(&serde_json::json!({
            "schema_version": "specimen-publication-v1", "variants": published
        }))?,
    )?;
    atomic_file(&output.join("active.json"), &json(&active)?)?;
    io(fs::File::open(&output))?
        .sync_all()
        .map_err(|e| fail(e.to_string()))?;
    let items = packages
        .iter()
        .flat_map(|p| &p.manifest.families)
        .flat_map(|f| &f.sizes)
        .flat_map(|g| &g.items);
    let (image_count, failure_count) = items.fold((0, 0), |(images, failures), item| {
        if item.outcome == Outcome::Rendered {
            (images + 1, failures)
        } else {
            (images, failures + 1)
        }
    });
    Ok(Publication {
        active,
        packages: packages
            .iter()
            .map(|p| p.manifest.variant.id.clone())
            .collect(),
        case_count: captures.cases.len(),
        image_count,
        failure_count,
    })
}

pub(crate) fn atomic_file(path: &Path, bytes: &[u8]) -> Result<(), Error> {
    if path.exists() || path.is_symlink() {
        regular(path)?;
        if io(fs::read(path))? == bytes {
            return Ok(());
        }
    }
    let mut temp = io(tempfile::NamedTempFile::new_in(path.parent().unwrap()))?;
    io(temp.write_all(bytes))?;
    io(temp.as_file().sync_all())?;
    temp.persist(path).map_err(|e| fail(e.to_string()))?;
    Ok(())
}
