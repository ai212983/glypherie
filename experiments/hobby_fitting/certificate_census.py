"""Build a diagnostic-only generator copy and count exact certificate duplicates per fit."""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "out/diagnostics/certificate-reuse-optimization"


def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (path, old)
    path.write_text(text.replace(old, new, 1))


def prepare():
    dst = OUT / "instrumented"
    assert not dst.exists(), "Preserve an existing census; use its saved harness to rerun."
    dst.mkdir()
    shutil.copytree(ROOT / "tools/generator/src", dst / "src")
    for name in ["Cargo.toml", "Cargo.lock", "build.rs"]:
        shutil.copyfile(ROOT / "tools/generator" / name, dst / name)
    (dst / "vendor").symlink_to(ROOT / "tools/generator/vendor", target_is_directory=True)
    lib = dst / "src/lib.rs"
    lib.write_text(lib.read_text() + "\npub mod certificate_observer;\n")
    p = dst / "src/diagonal_fitting/approved.rs"
    replace_once(p, "    // The reviewed sequence replaces earlier deliveries", "    let _frame = crate::certificate_observer::frame();\n    // The reviewed sequence replaces earlier deliveries")
    for name, function in [("crossing", "fit"), ("attached", "fit_with_analysis"), ("mod", "fit_with_analysis"),
                           ("curve_model", "fit_horizontal"), ("joint", "fit"), ("terminal", "fit_terminal")]:
        p = dst / f"src/diagonal_fitting/{name}.rs"
        text = p.read_text()
        match = re.search(r"\bfn " + function + r"\([^{}]+?\)\s*->[^{}]+?\{", text, re.S)
        assert match, (name, function)
        text = text[:match.end()] + f'\n    let _stage = crate::certificate_observer::stage("{name}");' + text[match.end():]
        p.write_text(text)
    p = dst / "src/diagonal_fitting/curves.rs"
    for name in ["Prim", "Contour"]:
        replace_once(p, ("enum " if name == "Prim" else "struct ") + name + " {",
                     "#[derive(Debug)]\n" + ("enum " if name == "Prim" else "struct ") + name + " {")
    replace_once(p, "fn certify(contours: &[Contour], depth: usize) -> Report {", """fn certify(contours: &[Contour], depth: usize) -> Report {
    let key = crate::certificate_observer::key(format!("{depth}|{contours:?}").as_bytes());
    let tick = std::time::Instant::now();
    let result = certify_observed_body(contours, depth);
    let ns = tick.elapsed().as_nanos() as u64;
    crate::certificate_observer::record("certify", key, serde_json::json!([result.ok,result.reason,result.at,result.with]), ns);
    result
}
fn certify_observed_body(contours: &[Contour], depth: usize) -> Report {""")
    p = dst / "src/diagonal_fitting/topology.rs"
    replace_once(p, "pub fn signature(loops: &[Vec<[f64; 2]>]) -> Option<Value> {", """pub fn signature(loops: &[Vec<[f64; 2]>]) -> Option<Value> {
    let mut bits = Vec::new();
    for contour in loops {
        bits.extend_from_slice(&(contour.len() as u64).to_le_bytes());
        for p in contour { for v in p { bits.extend_from_slice(&v.to_bits().to_le_bytes()); } }
    }
    let key = crate::certificate_observer::key(&bits);
    let tick = std::time::Instant::now();
    let result = signature_observed_body(loops);
    let ns = tick.elapsed().as_nanos() as u64;
    crate::certificate_observer::record("signature", key, serde_json::json!(result), ns);
    result
}
fn signature_observed_body(loops: &[Vec<[f64; 2]>]) -> Option<Value> {""")
    (dst / "src/certificate_observer.rs").write_text(OBSERVER)
    harness = OUT / "harness"
    (harness / "src").mkdir(parents=True)
    (harness / "Cargo.toml").write_text('''[package]
name="certificate-census"
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
let report=font_generator::candidate::render_with_pipeline(&bytes,&request,pipeline).unwrap();
println!("{}",serde_json::json!({"cell":row["cell"],"glyphs":report.records.len(),"measurement":font_generator::certificate_observer::take()}));
}}''')
    with (OUT / "census-build.log").open("w") as log:
        subprocess.run(["cargo", "build", "--release", "--offline", "--manifest-path", str(harness / "Cargo.toml")],
                       stdout=log, stderr=subprocess.STDOUT, check=True)


OBSERVER = r'''use std::{cell::RefCell,collections::BTreeMap};
use sha2::{Digest,Sha256};
use serde_json::{Value,json};
#[derive(Default)] struct Frame { stage:String, entries:BTreeMap<(String,String),Entry> }
struct Entry { calls:u64, total_ns:u64, duplicate_ns:u64, value:Value, stages:BTreeMap<String,u64> }
#[derive(Default)] struct State { current:Option<Frame>, rows:Vec<Value> }
thread_local! { static STATE:RefCell<State>=RefCell::new(State::default()); }
pub struct FrameGuard(Option<Frame>);
pub fn frame()->FrameGuard { STATE.with(|s|FrameGuard(s.borrow_mut().current.replace(Frame::default()))) }
impl Drop for FrameGuard { fn drop(&mut self){STATE.with(|s|{let mut s=s.borrow_mut();let f=s.current.take().unwrap();
let rows:Vec<Value>=f.entries.into_iter().map(|((kind,key),e)|json!({"kind":kind,"key":key,"calls":e.calls,"total_ns":e.total_ns,"duplicate_ns":e.duplicate_ns,"value":e.value,"stages":e.stages})).collect();
s.rows.push(json!({"entries":rows}));s.current=self.0.take();});} }
pub struct StageGuard(Option<String>);
pub fn stage(name:&str)->StageGuard { STATE.with(|s|{let mut s=s.borrow_mut();StageGuard(s.current.as_mut().map(|f|std::mem::replace(&mut f.stage,name.into())))}) }
impl Drop for StageGuard {fn drop(&mut self){if let Some(old)=self.0.take(){STATE.with(|s|{if let Some(f)=s.borrow_mut().current.as_mut(){f.stage=old;}});}}}
pub fn key(bytes:&[u8])->String {format!("{:x}",Sha256::digest(bytes))}
pub fn record(kind:&str,key:String,value:Value,ns:u64){STATE.with(|s|{let mut s=s.borrow_mut();if let Some(f)=s.current.as_mut(){
let e=f.entries.entry((kind.into(),key)).or_insert_with(||Entry{calls:0,total_ns:0,duplicate_ns:0,value:value.clone(),stages:BTreeMap::new()});
assert_eq!(e.value,value,"same certificate input returned a different result");if e.calls>0{e.duplicate_ns+=ns;}e.calls+=1;e.total_ns+=ns;*e.stages.entry(f.stage.clone()).or_default()+=1;
}})}
pub fn take()->Value {STATE.with(|s|json!(std::mem::take(&mut s.borrow_mut().rows)))}
'''


def requests():
    for family in ["Roboto", "SourceSans3"]:
        for size in [12, 16, 24]:
            for weight in [300, 400, 700]:
                for fitting, extension in [("font_hints_auto", "font-hints-auto-01"), ("upstream_mono", "mono-width-01")]:
                    for raster in ["free_type_mono", "free_type_mono_terminals"]:
                        axes = {"wght": weight, **({"wdth": 100} if family == "Roboto" else {})}
                        yield {"cell": [family, size, weight, fitting, raster], "font": str(ROOT / f"fonts/{family}.ttf"),
                               "request": {"profile": "mono_1bit", "extensions": extension,
                                           "settings": {"characters": "".join(chr(i) for i in range(32, 127)), "size_px": size, "axes": axes}},
                               "pipeline": {"fitting": fitting, "rasterization": raster, "diagonal_fitting": True}}


if __name__ == "__main__":
    if not (OUT / "instrumented").exists():
        prepare()
    rows = list(requests())
    (OUT / "requests.json").write_text(json.dumps(rows, indent=2) + "\n")
    with (OUT / "census.jsonl").open("w") as log:
        subprocess.run([str(OUT / "harness/target/release/certificate-census")],
                       input="".join(json.dumps(r) + "\n" for r in rows), text=True, stdout=log, check=True)
    print(json.dumps({"cells": len(rows), "status": "complete"}))
