use crate::{
    fail,
    specimens::{self, DisplayProfile, Image, Manifest},
    Error,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
};

mod attention;

const MAX_PIXELS: usize = 16 * 1024 * 1024;
const PADDING: i64 = 3;
pub const ADDED: [u8; 3] = [0, 96, 255];
pub const REMOVED: [u8; 3] = [224, 32, 32];

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Config {
    schema_version: String,
    id: String,
    #[serde(default)]
    attention: Option<std::path::PathBuf>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Selection {
    id: String,
    previous: Input,
    current: Input,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    variant: String,
    label: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Published {
    schema_version: String,
    variants: BTreeMap<String, String>,
}
#[derive(Deserialize)]
struct Canonical {
    schema_version: String,
    characters: String,
    cases: Vec<Case>,
    #[serde(default)]
    variant: Option<crate::specimen_config::Variant>,
    #[serde(default)]
    profiles: Vec<crate::specimen_config::Profile>,
}
#[derive(Deserialize)]
struct Case {
    family_id: String,
    size_px: f32,
    profile: String,
    axes: BTreeMap<String, f32>,
    report: Option<Report>,
    reason: Option<String>,
}
#[derive(Deserialize)]
struct Report {
    source_sha256: String,
    records: Vec<Bitmap>,
}
#[derive(Deserialize)]
struct Bitmap {
    codepoint: u32,
    left: i32,
    top: i32,
    width: u32,
    height: u32,
    output_bits: u8,
    pixels: Vec<u8>,
    advance_26_6: i32,
}
struct Package {
    manifest: Manifest,
    canonical: Canonical,
}

#[derive(Serialize)]
pub struct Comparison {
    schema_version: &'static str,
    id: String,
    previous: Identity,
    current: Identity,
    profiles: Vec<DisplayProfile>,
    families: Vec<Family>,
    statistics: Vec<Statistics>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    attention: Vec<attention::AttentionCase>,
}
#[derive(Serialize)]
struct Statistics {
    profile: String,
    same_symbols: usize,
    changed_symbols: usize,
    average_changed_pixels: f64,
    median_changed_pixels: f64,
}
#[derive(Default)]
struct Counts {
    same: usize,
    changed_pixels: Vec<usize>,
}
impl Counts {
    fn statistics(mut self, profile: String) -> Statistics {
        self.changed_pixels.sort_unstable();
        let changed = self.changed_pixels.len();
        let (average, median) = if changed == 0 {
            (0.0, 0.0)
        } else {
            let average = self.changed_pixels.iter().sum::<usize>() as f64 / changed as f64;
            let median = (self.changed_pixels[(changed - 1) / 2] + self.changed_pixels[changed / 2])
                as f64
                / 2.0;
            (average, median)
        };
        Statistics {
            profile,
            same_symbols: self.same,
            changed_symbols: changed,
            average_changed_pixels: average,
            median_changed_pixels: median,
        }
    }
}
#[derive(Serialize)]
struct Identity {
    package_id: String,
    label: String,
    generation_sha256: String,
}
#[derive(Serialize)]
struct Family {
    id: String,
    name: String,
    sizes: Vec<Size>,
}
#[derive(Serialize)]
struct Size {
    size_px: f32,
    axes: BTreeMap<String, f32>,
    canvas: Canvas,
    glyphs: Vec<Glyph>,
}
#[derive(Clone, Copy, Serialize)]
struct Canvas {
    width_px: u32,
    height_px: u32,
    origin_x: u32,
    baseline_y: u32,
    padding_px: u32,
}
#[derive(Serialize)]
struct Glyph {
    codepoint: u32,
    character: String,
    profiles: Vec<GlyphProfile>,
}
#[derive(Serialize)]
struct GlyphProfile {
    id: String,
    advance_px: u32,
    previous: Option<Image>,
    current: Option<Image>,
    difference: Option<Image>,
    reason: Option<String>,
}

fn io<T>(value: std::io::Result<T>) -> Result<T, Error> {
    value.map_err(|e| fail(e.to_string()))
}
fn read<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T, Error> {
    specimens::regular(path)?;
    if io(fs::metadata(path))?.len() > 64 * 1024 * 1024 {
        return Err(fail("comparison input exceeds size limit"));
    }
    serde_json::from_slice(&io(fs::read(path))?).map_err(|e| fail(e.to_string()))
}
fn safe_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 193
        && id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}

fn package(root: &Path, id: &str) -> Result<Package, Error> {
    if !safe_id(id) {
        return Err(fail("invalid comparison package ID"));
    }
    specimens::require_directory(root)?;
    specimens::require_directory(&root.join(id))?;
    let manifest: Manifest = read(&root.join(id).join("manifest.json"))?;
    if manifest.variant.id != id {
        return Err(fail("comparison package identity differs"));
    }
    specimens::validate_package(&root.join(id), &manifest)?;
    specimens::require_directory(&root.join("canonical"))?;
    let path = root
        .join("canonical")
        .join(format!("{}.json", manifest.variant.generation_sha256));
    let canonical: Canonical = read(&path)?;
    if specimens::hash(&io(fs::read(path))?) != manifest.variant.generation_sha256
        || canonical.schema_version != "specimen-render-v1"
    {
        return Err(fail("canonical comparison input identity differs"));
    }
    let mut keys = BTreeSet::new();
    for case in &canonical.cases {
        if !case.size_px.is_finite()
            || !(1.0..=512.0).contains(&case.size_px)
            || !keys.insert((&case.family_id, case.size_px.to_bits(), &case.profile))
        {
            return Err(fail("invalid or duplicate canonical comparison case"));
        }
        if let Some(report) = &case.report {
            let family = manifest
                .families
                .iter()
                .find(|f| f.id == case.family_id)
                .ok_or_else(|| fail("canonical comparison family missing"))?;
            if family.source_sha256 != report.source_sha256 {
                return Err(fail("canonical font identity differs"));
            }
            let bits = manifest
                .profiles
                .iter()
                .find(|p| p.id == case.profile)
                .ok_or_else(|| fail("canonical comparison profile missing"))?
                .output_bits;
            let mut seen = BTreeSet::new();
            for bitmap in &report.records {
                if bitmap.output_bits != bits
                    || bitmap.width as u64 * bitmap.height as u64 > MAX_PIXELS as u64
                    || bitmap.pixels.len() as u64 != bitmap.width as u64 * bitmap.height as u64
                    || bitmap.pixels.iter().any(|p| *p >= 1 << bits)
                    || char::from_u32(bitmap.codepoint).is_none()
                    || !seen.insert(bitmap.codepoint)
                {
                    return Err(fail("invalid canonical comparison bitmap"));
                }
            }
        }
    }
    Ok(Package {
        manifest,
        canonical,
    })
}

fn case<'a>(package: &'a Package, family: &str, size: f32, profile: &str) -> Option<&'a Case> {
    package
        .canonical
        .cases
        .iter()
        .find(|c| c.family_id == family && c.size_px == size && c.profile == profile)
}
fn bitmap(case: Option<&Case>, codepoint: u32) -> Option<&Bitmap> {
    case?
        .report
        .as_ref()?
        .records
        .iter()
        .find(|r| r.codepoint == codepoint)
}

fn canvas<'a>(records: impl Iterator<Item = &'a Bitmap>) -> Result<Canvas, Error> {
    let mut bounds = [0_i64; 4];
    for r in records {
        bounds[0] = bounds[0].min(i64::from(r.left));
        bounds[1] = bounds[1].min(i64::from(r.top));
        bounds[2] = bounds[2].max(i64::from(r.left) + i64::from(r.width));
        bounds[3] = bounds[3].max(i64::from(r.top) + i64::from(r.height));
    }
    let width = bounds[2] - bounds[0] + PADDING * 2;
    let height = bounds[3] - bounds[1] + PADDING * 2;
    if width
        .checked_mul(height)
        .is_none_or(|n| n > MAX_PIXELS as i64)
    {
        return Err(fail("comparison canvas exceeds size limit"));
    }
    Ok(Canvas {
        width_px: width as u32,
        height_px: height as u32,
        origin_x: (PADDING - bounds[0]) as u32,
        baseline_y: (PADDING - bounds[1]) as u32,
        padding_px: PADDING as u32,
    })
}

fn aligned(r: &Bitmap, canvas: Canvas) -> Vec<u8> {
    let mut pixels = vec![0; canvas.width_px as usize * canvas.height_px as usize];
    for y in 0..r.height {
        for x in 0..r.width {
            let px = i64::from(canvas.origin_x) + i64::from(r.left) + i64::from(x);
            let py = i64::from(canvas.baseline_y) + i64::from(r.top) + i64::from(y);
            pixels[py as usize * canvas.width_px as usize + px as usize] =
                r.pixels[y as usize * r.width as usize + x as usize];
        }
    }
    pixels
}

fn rgb(level: u8, bits: u8) -> [u8; 3] {
    let levels = (1_u16 << bits) - 1;
    let gray = 255 - ((u16::from(level) * 255 + levels / 2) / levels) as u8;
    [gray; 3]
}

fn difference(previous: &[u8], current: &[u8], bits: u8) -> Vec<u8> {
    previous
        .iter()
        .zip(current)
        .flat_map(|(&old, &new)| {
            if new > old {
                ADDED
            } else if new < old {
                REMOVED
            } else {
                rgb(new, bits)
            }
        })
        .collect()
}
fn encode(pixels: &[u8], canvas: Canvas) -> Result<Vec<u8>, Error> {
    let mut bytes = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut bytes, canvas.width_px, canvas.height_px);
        encoder.set_color(png::ColorType::Rgb);
        encoder.set_depth(png::BitDepth::Eight);
        encoder
            .write_header()
            .map_err(|e| fail(e.to_string()))?
            .write_image_data(pixels)
            .map_err(|e| fail(e.to_string()))?;
    }
    Ok(bytes)
}
fn image(
    pixels: &[u8],
    canvas: Canvas,
    assets: &mut BTreeMap<String, Vec<u8>>,
) -> Result<Image, Error> {
    let bytes = encode(pixels, canvas)?;
    let sha256 = specimens::hash(&bytes);
    let path = format!("assets/{sha256}.png");
    assets.insert(path.clone(), bytes);
    Ok(Image { path, sha256 })
}

fn build(
    selection: &Selection,
    previous: &Package,
    current: &Package,
) -> Result<(Comparison, BTreeMap<String, Vec<u8>>), Error> {
    let mut families = Vec::new();
    let mut assets = BTreeMap::new();
    let mut counts: BTreeMap<_, Counts> = current
        .manifest
        .profiles
        .iter()
        .map(|profile| (profile.id.clone(), Counts::default()))
        .collect();
    for family in &current.manifest.families {
        if previous
            .manifest
            .families
            .iter()
            .any(|f| f.id == family.id && f.source_sha256 != family.source_sha256)
        {
            return Err(fail("comparison font sources differ"));
        }
        let mut sizes = Vec::new();
        for size in &family.sizes {
            let selected: Vec<_> = current
                .manifest
                .profiles
                .iter()
                .filter(|p| size.items.iter().any(|item| item.profile == p.id))
                .collect();
            for profile in &selected {
                for p in [previous, current] {
                    if let Some(c) = case(p, &family.id, size.size_px, &profile.id) {
                        if c.axes != size.axes {
                            return Err(fail("comparison variation coordinates differ"));
                        }
                    }
                }
            }
            let canvas = canvas(selected.iter().flat_map(|profile| {
                [previous, current]
                    .into_iter()
                    .filter_map(|p| case(p, &family.id, size.size_px, &profile.id))
                    .filter_map(|c| c.report.as_ref())
                    .flat_map(|r| &r.records)
            }))?;
            let mut glyphs = Vec::new();
            let mut seen = BTreeSet::new();
            for ch in current
                .canonical
                .characters
                .chars()
                .filter(|ch| seen.insert(*ch))
            {
                let mut profiles = Vec::new();
                for profile in &selected {
                    let old_case = case(previous, &family.id, size.size_px, &profile.id);
                    let new_case = case(current, &family.id, size.size_px, &profile.id);
                    let missing = |side: &str, input: Option<&Case>| {
                        fail(format!(
                        "{side} comparison glyph missing: family {}, size {} px, profile {}, U+{:04X} ({ch:?}): {}",
                        family.id, size.size_px, profile.id, ch as u32,
                        input.and_then(|c| c.reason.as_deref()).unwrap_or("glyph or selected size/profile is missing")
                    ))
                    };
                    let before =
                        bitmap(old_case, ch as u32).ok_or_else(|| missing("Previous", old_case))?;
                    let after =
                        bitmap(new_case, ch as u32).ok_or_else(|| missing("Current", new_case))?;
                    let advance_px =
                        ((i64::from(after.advance_26_6) + 32).div_euclid(64)).max(1) as u32;
                    if before.output_bits != profile.output_bits {
                        return Err(fail("comparison output depths differ"));
                    }
                    let before = aligned(before, canvas);
                    let after = aligned(after, canvas);
                    let counts = counts.get_mut(&profile.id).unwrap();
                    if before == after {
                        counts.same += 1;
                        continue;
                    }
                    counts.changed_pixels.push(
                        before
                            .iter()
                            .zip(&after)
                            .filter(|(old, new)| old != new)
                            .count(),
                    );
                    let old_image = Some(image(
                        &before
                            .iter()
                            .flat_map(|p| rgb(*p, profile.output_bits))
                            .collect::<Vec<_>>(),
                        canvas,
                        &mut assets,
                    )?);
                    let new_image = Some(image(
                        &after
                            .iter()
                            .flat_map(|p| rgb(*p, profile.output_bits))
                            .collect::<Vec<_>>(),
                        canvas,
                        &mut assets,
                    )?);
                    let difference = Some(image(
                        &difference(&before, &after, profile.output_bits),
                        canvas,
                        &mut assets,
                    )?);
                    profiles.push(GlyphProfile {
                        id: profile.id.clone(),
                        advance_px,
                        previous: old_image,
                        current: new_image,
                        difference,
                        reason: None,
                    });
                }
                if !profiles.is_empty() {
                    glyphs.push(Glyph {
                        codepoint: ch as u32,
                        character: ch.to_string(),
                        profiles,
                    });
                }
            }
            sizes.push(Size {
                size_px: size.size_px,
                axes: size.axes.clone(),
                canvas,
                glyphs,
            });
        }
        sizes.sort_by(|a, b| a.size_px.total_cmp(&b.size_px));
        families.push(Family {
            id: family.id.clone(),
            name: family.name.clone(),
            sizes,
        });
    }
    let identity = |p: &Package, input: &Input| Identity {
        package_id: p.manifest.variant.id.clone(),
        label: input.label.clone(),
        generation_sha256: p.manifest.variant.generation_sha256.clone(),
    };
    Ok((
        Comparison {
            schema_version: "web-glyph-comparison-v1",
            id: selection.id.clone(),
            previous: identity(previous, &selection.previous),
            current: identity(current, &selection.current),
            profiles: current.manifest.profiles.clone(),
            families,
            statistics: current
                .manifest
                .profiles
                .iter()
                .map(|profile| {
                    counts
                        .remove(&profile.id)
                        .unwrap()
                        .statistics(profile.id.clone())
                })
                .collect(),
            attention: Vec::new(),
        },
        assets,
    ))
}

pub fn publish(config_path: &Path, root: &Path) -> Result<usize, Error> {
    let config: Config = read(config_path)?;
    if config.schema_version != "comparison-config-v2" {
        return Err(fail("unsupported comparison config"));
    }
    let published: Published = read(&root.join("published.json"))?;
    if published.schema_version != "specimen-publication-v1" {
        return Err(fail("unsupported specimen publication"));
    }
    let mut packages = BTreeMap::new();
    for id in published.variants.values() {
        packages.insert(id.clone(), package(root, id)?);
    }
    let (current, previous) =
        crate::preview_selection::select_roles(packages.iter().map(|(id, package)| {
            (
                id.as_str(),
                package.manifest.variant.version.as_deref(),
                package.manifest.variant.renderer,
            )
        }))?;
    let input = |id: &str| Input {
        variant: id.into(),
        label: packages[id]
            .manifest
            .variant
            .version
            .clone()
            .unwrap_or_else(|| "Reference".into()),
    };
    let selections: Vec<_> = previous
        .into_iter()
        .map(|previous| Selection {
            id: config.id.clone(),
            previous: input(previous),
            current: input(current),
        })
        .collect();
    let output = root.join("comparisons");
    specimens::directory(&output)?;
    let mut ids = BTreeSet::new();
    let mut entries = Vec::new();
    for selection in &selections {
        if selection.id.len() < 2
            || selection.id.len() > 8
            || !selection.id.bytes().all(|b| b.is_ascii_digit())
            || !ids.insert(&selection.id)
        {
            return Err(fail(
                "comparison routes require unique numeric IDs of 2–8 digits",
            ));
        }
        let mut inputs = Vec::new();
        for input in [&selection.previous, &selection.current] {
            if !safe_id(&input.variant) || input.label.trim().is_empty() || input.label.len() > 128
            {
                return Err(fail("invalid comparison input or label"));
            }
            inputs.push(&packages[&input.variant]);
        }
        let (mut manifest, mut assets) = build(selection, inputs[0], inputs[1])?;
        if let Some(path) = &config.attention {
            manifest.attention = attention::build(
                &config_path.parent().unwrap_or(Path::new(".")).join(path),
                selection,
                inputs[0],
                inputs[1],
                &mut assets,
            )?;
        }
        let bytes = specimens::json(&manifest)?;
        let id = format!("{}-{}", selection.id, specimens::hash(&bytes));
        let destination = output.join(&id);
        specimens::directory(&destination)?;
        specimens::directory(&destination.join("assets"))?;
        for (relative, bytes) in assets {
            specimens::immutable_file(&destination.join(relative), &bytes)?;
        }
        specimens::immutable_file(&destination.join("manifest.json"), &bytes)?;
        entries.push(
            serde_json::json!({ "id": selection.id, "manifest": format!("{id}/manifest.json") }),
        );
    }
    specimens::atomic_file(
        &output.join("index.json"),
        &specimens::json(&serde_json::json!({
            "schema_version": "web-comparisons-v1", "comparisons": entries
        }))?,
    )?;
    Ok(entries.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn record(left: i32, top: i32) -> Bitmap {
        Bitmap {
            codepoint: 65,
            left,
            top,
            width: 2,
            height: 1,
            output_bits: 1,
            pixels: vec![1, 1],
            advance_26_6: 128,
        }
    }

    #[test]
    fn shared_canvas_preserves_origin_baseline_and_bearing_changes() {
        let old = record(-2, -3);
        let new = record(-1, -3);
        let area = canvas([&old, &new].into_iter()).unwrap();
        assert_eq!((area.origin_x, area.baseline_y), (5, 6));
        let a = aligned(&old, area);
        let b = aligned(&new, area);
        let pixels = difference(&a, &b, 1);
        let start = (3 * area.width_px as usize + 3) * 3;
        assert_eq!(&pixels[start..start + 3], &REMOVED);
        assert_eq!(&pixels[start + 3..start + 6], &[0, 0, 0]);
        assert_eq!(&pixels[start + 6..start + 9], &ADDED);
        assert_eq!(&pixels[..3], &[255, 255, 255]);
    }

    #[test]
    fn grayscale_changes_are_directional_and_unchanged_shades_survive() {
        let result = difference(&[0, 7, 3, 0, 7], &[7, 0, 3, 0, 7], 3);
        assert_eq!(&result[..3], &ADDED);
        assert_eq!(&result[3..6], &REMOVED);
        assert_eq!(&result[6..9], &[146; 3]);
        assert_eq!(&result[9..12], &[255; 3]);
        assert_eq!(&result[12..15], &[0; 3]);
    }

    #[test]
    fn excessive_common_bounds_are_rejected_before_allocation() {
        let old = record(i32::MIN, 0);
        let new = record(i32::MAX, 0);
        assert!(canvas([&old, &new].into_iter()).is_err());
    }
}
