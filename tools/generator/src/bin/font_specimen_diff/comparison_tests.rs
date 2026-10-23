use super::*;

fn report(records: Vec<Value>) -> Value {
    json!({
        "source_sha256": "abc",
        "axes": {},
        "profile": "mono_1bit",
        "size_px": 16,
        "target": "t",
        "hinting_requested": false,
        "metrics": {"a": 1},
        "records": records,
    })
}

fn record(codepoint: i64) -> Value {
    json!({
        "codepoint": codepoint,
        "glyph_id": 1,
        "output_bits": 1,
        "mono_threshold": 128,
        "gray_gamma": 1.0,
        "fitted_commands": [],
        "pixels": [0],
        "left": 0,
        "top": 0,
        "width": 1,
        "height": 1,
        "advance_26_6": 64,
    })
}

fn case(report: Value) -> Value {
    json!({
        "family_id": "f",
        "size_px": 16,
        "axes": {},
        "profile": "mono_1bit",
        "report": report,
    })
}

fn sized_case(size: u64, report: Value) -> Value {
    json!({
        "family_id": "f",
        "size_px": size,
        "axes": {},
        "profile": "mono_1bit",
        "report": report,
    })
}

fn doc(variant: &str, cases: Vec<Value>) -> Value {
    json!({
        "characters": "ABC",
        "profiles": ["mono_1bit"],
        "variant": variant,
        "cases": cases,
    })
}

fn single() -> (Value, Value) {
    let reference = doc("ref", vec![case(report(vec![record(65)]))]);
    let proposal = doc("prop", vec![case(report(vec![record(65)]))]);
    (reference, proposal)
}

#[test]
fn repertoire_policies_differ() {
    let (reference, mut proposal) = single();
    proposal["characters"] = json!("ABD");
    assert_eq!(
        compare(&reference, &proposal).unwrap_err(),
        "repertoire/profile policies differ"
    );
    let (_, mut proposal) = single();
    proposal["profiles"] = json!(["gray_3bit"]);
    assert_eq!(
        compare(&reference, &proposal).unwrap_err(),
        "repertoire/profile policies differ"
    );
}

#[test]
fn missing_cases_arrays() {
    let (mut reference, proposal) = single();
    reference.as_object_mut().unwrap().remove("cases");
    assert_eq!(
        compare(&reference, &proposal).unwrap_err(),
        "missing reference cases"
    );
    let (reference, mut proposal) = single();
    proposal.as_object_mut().unwrap().remove("cases");
    assert_eq!(
        compare(&reference, &proposal).unwrap_err(),
        "missing proposed cases"
    );
}

#[test]
fn selection_mismatch_and_duplicates() {
    let (reference, _) = single();
    let other = doc("prop", vec![sized_case(24, report(vec![record(65)]))]);
    assert_eq!(
        compare(&reference, &other).unwrap_err(),
        "case selections differ or contain duplicates"
    );
    let dup = doc(
        "prop",
        vec![
            case(report(vec![record(65)])),
            case(report(vec![record(66)])),
        ],
    );
    assert_eq!(
        compare(&reference, &dup).unwrap_err(),
        "case selections differ or contain duplicates"
    );
}

#[test]
fn unsuccessful_capture() {
    let (reference, _) = single();
    let mut bad = case(report(vec![record(65)]));
    bad["report"] = json!("boom");
    assert_eq!(
        compare(&reference, &doc("prop", vec![bad])).unwrap_err(),
        "capture has an unsuccessful outcome"
    );
}

#[test]
fn capture_field_differs_and_null() {
    let (reference, _) = single();
    let mut rep = report(vec![record(65)]);
    rep["size_px"] = json!(18);
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(rep)])).unwrap_err(),
        "capture size_px differs"
    );
    let mut rep = report(vec![record(65)]);
    rep.as_object_mut().unwrap().remove("target");
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(rep)])).unwrap_err(),
        "capture target differs"
    );
}

#[test]
fn records_missing_and_counts() {
    let (reference, _) = single();
    let mut rep = report(vec![record(65)]);
    rep.as_object_mut().unwrap().remove("records");
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(rep.clone())])).unwrap_err(),
        "missing proposed records"
    );
    let mut ref_case = case(report(vec![record(65)]));
    ref_case["report"]
        .as_object_mut()
        .unwrap()
        .remove("records");
    assert_eq!(
        compare(&doc("ref", vec![ref_case]), &doc("prop", vec![case(rep)]),).unwrap_err(),
        "missing reference records"
    );
    let (reference, _) = single();
    let two = report(vec![record(65), record(66)]);
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(two)])).unwrap_err(),
        "record counts differ"
    );
}

#[test]
fn record_field_differs_and_null() {
    let (reference, _) = single();
    let mut rec = record(65);
    rec["glyph_id"] = json!(2);
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(report(vec![rec]))])).unwrap_err(),
        "record glyph_id differs"
    );
    let mut rec = record(65);
    rec.as_object_mut().unwrap().remove("output_bits");
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(report(vec![rec]))])).unwrap_err(),
        "record output_bits differs"
    );
}

#[test]
fn invalid_pair_counts() {
    let (reference, _) = single();
    let mut rec = record(65);
    rec["diagonal_pairs"] = json!([1, 2]);
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(report(vec![rec]))])).unwrap_err(),
        "invalid diagonal pair counts"
    );
    let mut rec = record(65);
    rec["diagonal_pairs"] = json!(["x", 1, 2]);
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(report(vec![rec]))])).unwrap_err(),
        "invalid pair count"
    );
}

#[test]
fn invalid_codepoint_and_scalar_abort_on_change() {
    let ref_rec = record(-1);
    let mut rec = record(-1);
    rec["fitted_commands"] = json!([1]);
    let reference = doc("ref", vec![case(report(vec![ref_rec]))]);
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(report(vec![rec]))])).unwrap_err(),
        "invalid codepoint"
    );
    let mut rec = record(65);
    rec["codepoint"] = json!(55296);
    rec["fitted_commands"] = json!([1]);
    let mut ref_rec = record(65);
    ref_rec["codepoint"] = json!(55296);
    let reference = doc("ref", vec![case(report(vec![ref_rec]))]);
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(report(vec![rec]))])).unwrap_err(),
        "invalid scalar"
    );
}

#[test]
fn corrupt_changed_bitmap_aborts_unchanged_ignored() {
    let (reference, _) = single();
    let mut rec = record(65);
    rec["fitted_commands"] = json!([1]);
    rec["width"] = json!(2);
    rec["height"] = json!(2);
    assert_eq!(
        compare(&reference, &doc("prop", vec![case(report(vec![rec]))])).unwrap_err(),
        "invalid bitmap allocation"
    );
    let mut bad = record(65);
    bad["width"] = json!(2);
    bad["height"] = json!(2);
    let reference = doc("ref", vec![case(report(vec![bad.clone()]))]);
    let proposal = doc("prop", vec![case(report(vec![bad]))]);
    assert!(compare(&reference, &proposal).is_ok());
}

#[test]
fn identical_docs_report_empty_changes() {
    let (reference, proposal) = single();
    let out = compare(&reference, &proposal).unwrap();
    assert_eq!(out["schema_version"], json!("specimen-diff-v1"));
    assert_eq!(out["reference_variant"], json!("ref"));
    assert_eq!(out["proposal_variant"], json!("prop"));
    let case_out = &out["cases"][0];
    assert_eq!(case_out["record_count"], json!(1));
    assert_eq!(case_out["diagonal_pairs"], json!([0, 0, 0]));
    assert_eq!(case_out["changed_outlines"], json!(0));
    assert_eq!(case_out["changed_bitmaps"], json!(0));
    assert_eq!(case_out["metrics_changed"], json!(false));
    assert_eq!(case_out["advances_changed"], json!(false));
    assert_eq!(case_out["topology_differences"], json!([]));
    assert_eq!(case_out["changes"], json!([]));
}

#[test]
fn changed_outline_bitmap_reports_topology() {
    let (reference, _) = single();
    let mut rec = record(65);
    rec["fitted_commands"] = json!([1]);
    rec["pixels"] = json!([1]);
    let out = compare(&reference, &doc("prop", vec![case(report(vec![rec]))])).unwrap();
    let case_out = &out["cases"][0];
    assert_eq!(case_out["changed_outlines"], json!(1));
    assert_eq!(case_out["changed_bitmaps"], json!(1));
    assert_eq!(case_out["changes"][0]["glyph"], json!("A"));
    assert_eq!(case_out["changes"][0]["outline_changed"], json!(true));
    assert_eq!(case_out["changes"][0]["bitmap_changed"], json!(true));
    assert_eq!(case_out["changes"][0]["reference_topology"], json!([0, 0]));
    assert_eq!(case_out["changes"][0]["proposal_topology"], json!([1, 0]));
    assert_eq!(
        case_out["topology_differences"].as_array().unwrap().len(),
        1
    );
}

#[test]
fn gray_record_skips_topology() {
    let (mut reference, _) = single();
    let mut rec = record(65);
    rec["output_bits"] = json!(3);
    rec["fitted_commands"] = json!([1]);
    rec["pixels"] = json!([7]);
    reference["cases"][0]["report"]["records"] = json!([{
        "codepoint": 65, "glyph_id": 1, "output_bits": 3, "mono_threshold": 128,
        "gray_gamma": 1.0, "fitted_commands": [], "pixels": [0],
        "left": 0, "top": 0, "width": 1, "height": 1, "advance_26_6": 64,
    }]);
    let out = compare(&reference, &doc("prop", vec![case(report(vec![rec]))])).unwrap();
    let change = &out["cases"][0]["changes"][0];
    assert!(change.get("reference_topology").is_none());
    assert!(change.get("proposal_topology").is_none());
    assert_eq!(out["cases"][0]["topology_differences"], json!([]));
}

#[test]
fn aggregation_pairs_metrics_advances_and_order() {
    let mk = |pairs: Value, advance: u64, metrics: u64| {
        let mut a = record(65);
        a["diagonal_pairs"] = pairs;
        a["advance_26_6"] = json!(advance);
        let mut rep = report(vec![a]);
        rep["metrics"] = json!({"a": metrics});
        rep
    };
    let reference = doc(
        "ref",
        vec![
            sized_case(16, mk(json!([0, 0, 0]), 64, 1)),
            sized_case(24, mk(json!([0, 0, 0]), 64, 1)),
        ],
    );
    let mut b16 = record(65);
    b16["diagonal_pairs"] = json!([1, 2, 3]);
    let mut rep16 = report(vec![b16]);
    rep16["metrics"] = json!({"a": 2});
    let mut b24 = record(65);
    b24["diagonal_pairs"] = json!([4, 5, 6]);
    b24["advance_26_6"] = json!(65);
    let proposal = doc(
        "prop",
        vec![sized_case(24, report(vec![b24])), sized_case(16, rep16)],
    );
    let out = compare(&reference, &proposal).unwrap();
    assert_eq!(out["cases"][0]["size_px"], json!(24));
    assert_eq!(out["cases"][1]["size_px"], json!(16));
    assert_eq!(out["cases"][0]["diagonal_pairs"], json!([4, 5, 6]));
    assert_eq!(out["cases"][1]["diagonal_pairs"], json!([1, 2, 3]));
    assert_eq!(out["cases"][0]["advances_changed"], json!(true));
    assert_eq!(out["cases"][1]["advances_changed"], json!(false));
    assert_eq!(out["cases"][1]["metrics_changed"], json!(true));
    assert_eq!(out["cases"][0]["metrics_changed"], json!(false));
}
