use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, env, fs, path::Path, process::ExitCode};

fn topology(record: &Value) -> Result<[usize; 2], String> {
    let width = record["width"].as_u64().ok_or("missing width")? as usize;
    let height = record["height"].as_u64().ok_or("missing height")? as usize;
    let pixels = record["pixels"].as_array().ok_or("missing pixels")?;
    if width.checked_mul(height) != Some(pixels.len()) || pixels.len() > 4_194_304 {
        return Err("invalid bitmap allocation".into());
    }
    let ink: Vec<_> = pixels
        .iter()
        .map(|p| p.as_u64().map(|p| p != 0).ok_or("invalid pixel"))
        .collect::<Result<_, _>>()?;
    let mut visited = vec![false; pixels.len()];
    let mut counts = [0, 0];
    for start in 0..pixels.len() {
        if visited[start] {
            continue;
        }
        let color = ink[start];
        let mut queue = vec![start];
        visited[start] = true;
        let mut next = 0;
        let mut boundary = false;
        while next < queue.len() {
            let p = queue[next];
            next += 1;
            let x = p % width;
            let y = p / width;
            boundary |= x == 0 || y == 0 || x + 1 == width || y + 1 == height;
            for dy in -1..=1isize {
                for dx in -1..=1isize {
                    if (dx == 0 && dy == 0) || (!color && dx != 0 && dy != 0) {
                        continue;
                    }
                    let xx = x as isize + dx;
                    let yy = y as isize + dy;
                    if xx < 0 || yy < 0 || xx >= width as isize || yy >= height as isize {
                        continue;
                    }
                    let p = yy as usize * width + xx as usize;
                    if !visited[p] && ink[p] == color {
                        visited[p] = true;
                        queue.push(p);
                    }
                }
            }
        }
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
        let original = refs[&key(case)];
        let a = &original["report"];
        let b = &case["report"];
        if !a.is_object() || !b.is_object() {
            return Err("capture has an unsuccessful outcome".into());
        }
        for field in [
            "source_sha256",
            "axes",
            "profile",
            "size_px",
            "target",
            "hinting_requested",
        ] {
            if a[field].is_null() || a[field] != b[field] {
                return Err(format!("capture {field} differs"));
            }
        }
        let ar = a["records"].as_array().ok_or("missing reference records")?;
        let br = b["records"].as_array().ok_or("missing proposed records")?;
        if ar.len() != br.len() {
            return Err("record counts differ".into());
        }
        let mut changed_outlines = 0;
        let mut changed_bitmaps = 0;
        let mut pair_counts = [0u64; 3];
        let mut topology_differences = Vec::new();
        let mut changes = Vec::new();
        for (r, s) in ar.iter().zip(br) {
            for field in [
                "codepoint",
                "glyph_id",
                "output_bits",
                "mono_threshold",
                "gray_gamma",
            ] {
                if r[field].is_null() || r[field] != s[field] {
                    return Err(format!("record {field} differs"));
                }
            }
            if let Some(counts) = s["diagonal_pairs"].as_array() {
                if counts.len() != 3 {
                    return Err("invalid diagonal pair counts".into());
                }
                for (i, count) in counts.iter().enumerate() {
                    pair_counts[i] += count.as_u64().ok_or("invalid pair count")?;
                }
            }
            let outline = r["fitted_commands"] != s["fitted_commands"];
            let bitmap = ["pixels", "left", "top", "width", "height"]
                .iter()
                .any(|k| r[k] != s[k]);
            changed_outlines += usize::from(outline);
            changed_bitmaps += usize::from(bitmap);
            if outline || bitmap {
                let glyph =
                    char::from_u32(s["codepoint"].as_u64().ok_or("invalid codepoint")? as u32)
                        .ok_or("invalid scalar")?
                        .to_string();
                let mut change = json!({"glyph":glyph,"codepoint":s["codepoint"],"outline_changed":outline,"bitmap_changed":bitmap});
                if s["output_bits"] == 1 {
                    let before = topology(r)?;
                    let after = topology(s)?;
                    change["reference_topology"] = json!(before);
                    change["proposal_topology"] = json!(after);
                    if before != after {
                        topology_differences.push(change.clone());
                    }
                }
                changes.push(change);
            }
        }
        reports.push(json!({"family_id":case["family_id"],"size_px":case["size_px"],"profile":case["profile"],
            "record_count":br.len(),"diagonal_pairs":pair_counts,"changed_outlines":changed_outlines,"changed_bitmaps":changed_bitmaps,
            "metrics_changed":a["metrics"]!=b["metrics"],"advances_changed":ar.iter().zip(br).any(|(r,s)|r["advance_26_6"]!=s["advance_26_6"]),
            "topology_differences":topology_differences,"changes":changes}));
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
