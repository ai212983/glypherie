"""Measure existing crossing/joint prerequisites in a diagnostic-only generator copy."""
import json
import pathlib
import shutil
import subprocess

from certificate_census import ROOT, replace_once, requests

OUT = ROOT / "out/diagnostics/stage-eligibility-optimization"


def prepare():
    dst = OUT / "instrumented"
    assert not dst.exists(), "Preserve an existing census and its saved executable."
    shutil.copytree(ROOT / "tools/generator/src", dst / "src")
    for name in ["Cargo.toml", "Cargo.lock", "build.rs"]:
        shutil.copyfile(ROOT / "tools/generator" / name, dst / name)
    (dst / "vendor").symlink_to(ROOT / "tools/generator/vendor", target_is_directory=True)
    lib = dst / "src/lib.rs"
    lib.write_text(lib.read_text() + "\npub mod stage_observer;\n")
    (dst / "src/stage_observer.rs").write_text(OBSERVER)
    for stage in ["crossing", "joint"]:
        p = dst / f"src/diagonal_fitting/{stage}.rs"
        upstream = "upstream" if stage == "crossing" else "original_upstream"
        raw_arg = "raw, " if stage == "crossing" else ""
        text = p.read_text()
        implementation = "fn fit_impl<const SELECTING: bool>(\n" in text
        start = text.index("fn fit_impl<const SELECTING: bool>(\n" if implementation else "pub fn fit(\n")
        end = text.index(" {\n", start) + 2
        signature = text[start:end]
        called = "observed_impl::<SELECTING>" if implementation else "observed_fit"
        original = signature.replace("fn fit_impl", "fn observed_impl") if implementation else signature.replace("pub fn fit(", "fn observed_fit(")
        wrapper = signature + f'''
    crate::stage_observer::begin("{stage}");
    let result = {called}({raw_arg}source, {upstream}, size_px, reference, native_axes);
    crate::stage_observer::finish(&result);
    result
}}
''' + original
        p.write_text(text[:start] + wrapper + text[end:])
        if stage == "crossing":
            anchor = "    let (portions, curve_boxes, loops, flats) = geometry::split_visible(raw, true);"
            predicate = '''    let tick = std::time::Instant::now();
    let gate = if !raw_supported { "unsupported-raw" }
        else if !raw.contours.iter().flatten().any(|s| matches!(s, GeomSegment::Quad { .. })) { "no-quadratics" }
        else if chord_loops(raw).as_ref().and_then(|loops| waist_from_slabs(loops)).is_none() { "no-waist" }
        else { "eligible" };
    crate::stage_observer::heavy(gate, tick.elapsed().as_nanos() as u64);
'''
            suffix = "    let skipped_json = || -> Vec<serde_json::Value> {"
            vector = "    let mut prepared: Vec<geometry::PreppedPair> = Vec::new();"
        else:
            anchor = "    let (portions, curve_boxes, loops, flats) = geometry::split_visible(&parsed, true);"
            predicate = '''    let tick = std::time::Instant::now();
    let gate = match axis_interval(source) {
        None => "no-axis",
        Some(locus) if locus.cmax - locus.cmin > EPS_PARITY => "axis-range",
        Some(_) if waist_from_slabs(&parsed).is_none() => "no-waist",
        Some(_) => "eligible",
    };
    crate::stage_observer::heavy(gate, tick.elapsed().as_nanos() as u64);
'''
            suffix = "    let skipped_json: Vec<serde_json::Value> = skipped"
            vector = "    let mut prepped: Vec<super::PreppedInfo> = Vec::new();"
        replace_once(p, anchor, predicate + anchor)
        replace_once(p, anchor, anchor.replace("geometry::split_visible(", 'crate::stage_observer::timed("visibility", || geometry::split_visible(').replace(");", "));"))
        recognize = "    let (pairs, mut skipped) = geometry::recognize(&portions, &loops, true);"
        replace_once(p, recognize, '    let (pairs, mut skipped) = crate::stage_observer::timed("recognition", || geometry::recognize(&portions, &loops, true));')
        replace_once(p, vector, '    let prepare_tick = std::time::Instant::now();\n' + vector)
        text = p.read_text()
        location = text.index(suffix, text.index(vector))
        p.write_text(text[:location] + '    crate::stage_observer::component("preparation", prepare_tick.elapsed().as_nanos() as u64);\n' + text[location:])
    harness = OUT / "harness"
    (harness / "src").mkdir(parents=True)
    (harness / "Cargo.toml").write_text('''[package]
name="stage-census"
version="0.0.0"
edition="2021"
[dependencies]
font_generator={path="../instrumented"}
serde_json="1"
''')
    shutil.copyfile(ROOT / "tools/generator/Cargo.lock", harness / "Cargo.lock")
    (harness / "src/main.rs").write_text('''use std::io::{self,BufRead};
fn main(){for line in io::stdin().lock().lines(){
let row:serde_json::Value=serde_json::from_str(&line.unwrap()).unwrap();
let bytes=std::fs::read(row["font"].as_str().unwrap()).unwrap();
let request=serde_json::from_value(row["request"].clone()).unwrap();
let pipeline=serde_json::from_value(row["pipeline"].clone()).unwrap();
let tick=std::time::Instant::now();
let report=font_generator::candidate::render_with_pipeline(&bytes,&request,pipeline).unwrap();
let elapsed_ns=tick.elapsed().as_nanos() as u64;
println!("{}",serde_json::json!({"cell":row["cell"],"glyphs":report.records.len(),"render_ns":elapsed_ns,"stages":font_generator::stage_observer::take()}));
}}''')
    with (OUT / "census-build.log").open("w") as log:
        subprocess.run(["cargo", "build", "--release", "--offline", "--manifest-path", str(harness / "Cargo.toml")],
                       stdout=log, stderr=subprocess.STDOUT, check=True)


OBSERVER = r'''use std::{cell::RefCell,collections::BTreeMap,time::Instant};
use serde_json::{Value,json};
struct Work { stage:String, start:Instant, heavy:Option<Instant>, gate:String, predicate_ns:u64, components:BTreeMap<String,u64> }
thread_local! { static STACK:RefCell<Vec<Work>>=const{RefCell::new(Vec::new())}; static ROWS:RefCell<Vec<Value>>=const{RefCell::new(Vec::new())}; }
pub fn begin(stage:&str){STACK.with(|s|s.borrow_mut().push(Work{stage:stage.into(),start:Instant::now(),heavy:None,gate:"initial-validation".into(),predicate_ns:0,components:BTreeMap::new()}));}
pub fn heavy(gate:&str,ns:u64){STACK.with(|s|{let mut s=s.borrow_mut();let w=s.last_mut().unwrap();w.gate=gate.into();w.predicate_ns=ns;w.heavy=Some(Instant::now());});}
pub fn component(name:&str,ns:u64){STACK.with(|s|{*s.borrow_mut().last_mut().unwrap().components.entry(name.into()).or_default()+=ns;});}
pub fn timed<T>(name:&str,f:impl FnOnce()->T)->T{let tick=Instant::now();let result=f();component(name,tick.elapsed().as_nanos() as u64);result}
pub fn finish(result:&Result<crate::diagonal_fitting::FitResult,crate::Error>){STACK.with(|s|{let w=s.borrow_mut().pop().unwrap();let row=json!({"stage":w.stage,"gate":w.gate,"predicate_ns":w.predicate_ns,"total_ns":w.start.elapsed().as_nanos() as u64,"body_ns":w.heavy.map(|i|i.elapsed().as_nanos() as u64).unwrap_or(0),"components":w.components,"applied":result.as_ref().map(|r|r.applied).unwrap_or(false),"reason":result.as_ref().map(|r|r.reason.clone()).unwrap_or_else(|e|e.to_string())});if w.gate!="eligible"&&w.gate!="initial-validation"{assert!(!result.as_ref().unwrap().applied,"prerequisite rejected an applicable stage");}ROWS.with(|r|r.borrow_mut().push(row));});}
pub fn take()->Value{ROWS.with(|r|json!(std::mem::take(&mut *r.borrow_mut())))}
'''


def main():
    if not (OUT / "instrumented").exists():
        prepare()
    rows = list(requests())
    for family in ["Roboto", "SourceSans3"]:
        template = next(r for r in rows if r["cell"] == [family, 16, 400, "font_hints_auto", "free_type_mono"])
        for name, text in [("pangram", "Pack my box with five dozen liquor jugs."), ("stress", "s x X 2 A y W")]:
            row = json.loads(json.dumps(template))
            row["cell"] = [family, name]
            row["request"]["settings"]["characters"] = text
            rows.append(row)
    (OUT / "requests.json").write_text(json.dumps(rows, indent=2) + "\n")
    with (OUT / "census.jsonl").open("w") as log:
        subprocess.run([str(OUT / "harness/target/release/stage-census")],
                       input="".join(json.dumps(r) + "\n" for r in rows), text=True, stdout=log, check=True)
    print(json.dumps({"cells": len(rows), "status": "complete"}))


if __name__ == "__main__":
    main()
