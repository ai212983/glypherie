use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, env, fs, path::Path, process::ExitCode};

#[derive(Debug)]
struct ValidatedBitmap {
    width: usize,
    height: usize,
    ink: Vec<bool>,
}

fn validate_bitmap(record: &Value) -> Result<ValidatedBitmap, String> {
    let width = record["width"].as_u64().ok_or("missing width")? as usize;
    let height = record["height"].as_u64().ok_or("missing height")? as usize;
    let pixels = record["pixels"].as_array().ok_or("missing pixels")?;
    if width.checked_mul(height) != Some(pixels.len()) || pixels.len() > 4_194_304 {
        return Err("invalid bitmap allocation".into());
    }
    let ink = pixels
        .iter()
        .map(|p| p.as_u64().map(|p| p != 0).ok_or("invalid pixel"))
        .collect::<Result<_, _>>()?;
    Ok(ValidatedBitmap { width, height, ink })
}

const INK_OFFSETS: [(isize, isize); 8] = [
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
];

const WHITE_OFFSETS: [(isize, isize); 4] = [(0, -1), (-1, 0), (1, 0), (0, 1)];

fn neighbors(
    index: usize,
    width: usize,
    height: usize,
    eight: bool,
) -> impl Iterator<Item = usize> {
    let x = index % width;
    let y = index / width;
    let offsets: &[(isize, isize)] = if eight { &INK_OFFSETS } else { &WHITE_OFFSETS };
    offsets.iter().filter_map(move |(dx, dy)| {
        let xx = x as isize + dx;
        let yy = y as isize + dy;
        if xx < 0 || yy < 0 || xx >= width as isize || yy >= height as isize {
            None
        } else {
            Some(yy as usize * width + xx as usize)
        }
    })
}

fn flood_fill(
    bitmap: &ValidatedBitmap,
    start: usize,
    visited: &mut [bool],
    queue: &mut Vec<usize>,
) -> (bool, bool) {
    let color = bitmap.ink[start];
    queue.clear();
    queue.push(start);
    visited[start] = true;
    let mut next = 0;
    let mut boundary = false;
    while next < queue.len() {
        let p = queue[next];
        next += 1;
        let x = p % bitmap.width;
        let y = p / bitmap.width;
        boundary |= x == 0 || y == 0 || x + 1 == bitmap.width || y + 1 == bitmap.height;
        for q in neighbors(p, bitmap.width, bitmap.height, color) {
            if !visited[q] && bitmap.ink[q] == color {
                visited[q] = true;
                queue.push(q);
            }
        }
    }
    (color, boundary)
}

fn topology(record: &Value) -> Result<[usize; 2], String> {
    let bitmap = validate_bitmap(record)?;
    let mut visited = vec![false; bitmap.ink.len()];
    let mut queue = Vec::new();
    let mut counts = [0, 0];
    for start in 0..bitmap.ink.len() {
        if visited[start] {
            continue;
        }
        let (color, boundary) = flood_fill(&bitmap, start, &mut visited, &mut queue);
        if color {
            counts[0] += 1;
        } else if !boundary {
            counts[1] += 1;
        }
    }
    Ok(counts)
}

fn key(case: &Value) -> String {
    json!([
        case["family_id"],
        case["size_px"],
        case["axes"],
        case["profile"]
    ])
    .to_string()
}

fn match_required_fields(a: &Value, b: &Value, fields: &[&str], label: &str) -> Result<(), String> {
    for field in fields {
        if a[field].is_null() || a[field] != b[field] {
            return Err(format!("{label} {field} differs"));
        }
    }
    Ok(())
}

struct CaseTally {
    outlines: usize,
    bitmaps: usize,
    pairs: [u64; 3],
    topology_differences: Vec<Value>,
    changes: Vec<Value>,
}

fn accumulate_pairs(record: &Value, pairs: &mut [u64; 3]) -> Result<(), String> {
    if let Some(counts) = record["diagonal_pairs"].as_array() {
        if counts.len() != 3 {
            return Err("invalid diagonal pair counts".into());
        }
        for (i, count) in counts.iter().enumerate() {
            pairs[i] += count.as_u64().ok_or("invalid pair count")?;
        }
    }
    Ok(())
}

fn describe_change(
    r: &Value,
    s: &Value,
    outline: bool,
    bitmap: bool,
) -> Result<(Value, Option<Value>), String> {
    let glyph = char::from_u32(s["codepoint"].as_u64().ok_or("invalid codepoint")? as u32)
        .ok_or("invalid scalar")?
        .to_string();
    let mut change = json!({"glyph":glyph,"codepoint":s["codepoint"],"outline_changed":outline,"bitmap_changed":bitmap});
    let mut topology_difference = None;
    if s["output_bits"] == 1 {
        let before = topology(r)?;
        let after = topology(s)?;
        change["reference_topology"] = json!(before);
        change["proposal_topology"] = json!(after);
        if before != after {
            topology_difference = Some(change.clone());
        }
    }
    Ok((change, topology_difference))
}

fn compare_records(ar: &[Value], br: &[Value]) -> Result<CaseTally, String> {
    let mut tally = CaseTally {
        outlines: 0,
        bitmaps: 0,
        pairs: [0; 3],
        topology_differences: Vec::new(),
        changes: Vec::new(),
    };
    for (r, s) in ar.iter().zip(br) {
        match_required_fields(
            r,
            s,
            &[
                "codepoint",
                "glyph_id",
                "output_bits",
                "mono_threshold",
                "gray_gamma",
            ],
            "record",
        )?;
        accumulate_pairs(s, &mut tally.pairs)?;
        let outline = r["fitted_commands"] != s["fitted_commands"];
        let bitmap = ["pixels", "left", "top", "width", "height"]
            .iter()
            .any(|k| r[k] != s[k]);
        tally.outlines += usize::from(outline);
        tally.bitmaps += usize::from(bitmap);
        if outline || bitmap {
            let (change, topology_difference) = describe_change(r, s, outline, bitmap)?;
            if let Some(difference) = topology_difference {
                tally.topology_differences.push(difference);
            }
            tally.changes.push(change);
        }
    }
    Ok(tally)
}

fn compare_case(original: &Value, case: &Value) -> Result<Value, String> {
    let a = &original["report"];
    let b = &case["report"];
    if !a.is_object() || !b.is_object() {
        return Err("capture has an unsuccessful outcome".into());
    }
    match_required_fields(
        a,
        b,
        &[
            "source_sha256",
            "axes",
            "profile",
            "size_px",
            "target",
            "hinting_requested",
        ],
        "capture",
    )?;
    let ar = a["records"].as_array().ok_or("missing reference records")?;
    let br = b["records"].as_array().ok_or("missing proposed records")?;
    if ar.len() != br.len() {
        return Err("record counts differ".into());
    }
    let tally = compare_records(ar, br)?;
    Ok(
        json!({"family_id":case["family_id"],"size_px":case["size_px"],"profile":case["profile"],
        "record_count":br.len(),"diagonal_pairs":tally.pairs,"changed_outlines":tally.outlines,"changed_bitmaps":tally.bitmaps,
        "metrics_changed":a["metrics"]!=b["metrics"],"advances_changed":ar.iter().zip(br).any(|(r,s)|r["advance_26_6"]!=s["advance_26_6"]),
        "topology_differences":tally.topology_differences,"changes":tally.changes}),
    )
}

fn compare(reference: &Value, proposal: &Value) -> Result<Value, String> {
    if reference["characters"] != proposal["characters"]
        || reference["profiles"] != proposal["profiles"]
    {
        return Err("repertoire/profile policies differ".into());
    }
    let cases = reference["cases"]
        .as_array()
        .ok_or("missing reference cases")?;
    let proposed = proposal["cases"]
        .as_array()
        .ok_or("missing proposed cases")?;
    let refs: BTreeMap<_, _> = cases.iter().map(|c| (key(c), c)).collect();
    let candidates: BTreeMap<_, _> = proposed.iter().map(|c| (key(c), c)).collect();
    if refs.len() != cases.len()
        || candidates.len() != proposed.len()
        || !refs.keys().eq(candidates.keys())
    {
        return Err("case selections differ or contain duplicates".into());
    }
    let mut reports = Vec::new();
    for case in proposed {
        reports.push(compare_case(refs[&key(case)], case)?);
    }
    Ok(
        json!({"schema_version":"specimen-diff-v1","reference_variant":reference["variant"],"proposal_variant":proposal["variant"],
        "topology_policy":"1-bit witnesses: 8-connected ink components, 4-connected enclosed white regions; differences require source/visual review",
        "cases":reports}),
    )
}

fn run() -> Result<(), String> {
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() != 3 {
        return Err("usage: font_specimen_diff REFERENCE_CANONICAL.json PROPOSAL_CANONICAL.json OUTPUT.json".into());
    }
    let output = Path::new(&args[2]);
    for input in &args[..2] {
        if output.exists()
            && fs::canonicalize(output).map_err(|e| e.to_string())?
                == fs::canonicalize(input).map_err(|e| e.to_string())?
        {
            return Err("output must differ from inputs".into());
        }
    }
    let read = |path: &Path| -> Result<(Value, String), String> {
        let bytes = fs::read(path).map_err(|e| e.to_string())?;
        let value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
        Ok((value, format!("{:x}", Sha256::digest(bytes))))
    };
    let (reference, reference_hash) = read(Path::new(&args[0]))?;
    let (proposal, proposal_hash) = read(Path::new(&args[1]))?;
    let mut report = compare(&reference, &proposal)?;
    report["reference_generation_sha256"] = json!(reference_hash);
    report["proposal_generation_sha256"] = json!(proposal_hash);
    let bytes = serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?;
    fs::write(output, bytes).map_err(|e| e.to_string())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("font_specimen_diff: {e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
#[path = "font_specimen_diff/comparison_tests.rs"]
mod comparison_tests;

#[cfg(test)]
#[path = "font_specimen_diff/topology_tests.rs"]
mod topology_tests;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn topology_uses_complementary_connectivity() {
        assert_eq!(
            topology(&json!({"width":2,"height":2,"pixels":[1,0,0,1]})).unwrap(),
            [1, 0]
        );
        assert_eq!(
            topology(&json!({"width":3,"height":3,"pixels":[1,1,1,1,0,1,1,1,1]})).unwrap(),
            [1, 1]
        );
        assert_eq!(
            topology(&json!({"width":3,"height":1,"pixels":[1,0,1]})).unwrap(),
            [2, 0]
        );
    }
    #[test]
    fn mismatched_inputs_fail_before_comparison() {
        assert!(compare(
            &json!({"characters":"A","profiles":[]}),
            &json!({"characters":"B","profiles":[]})
        )
        .is_err());
    }
}
