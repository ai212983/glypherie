"""Capture source-ordered curve searches and replay certified-bound ordering."""
import json
import shutil
import subprocess

from certificate_census import ROOT, replace_once, requests

OUT = ROOT / "out/diagnostics/curve-ordering-optimization"


def prepare():
    dst = OUT / "instrumented"
    assert not dst.exists(), "Preserve the saved census and executable."
    shutil.copytree(ROOT / "tools/generator/src", dst / "src")
    for name in ["Cargo.toml", "Cargo.lock", "build.rs"]:
        shutil.copyfile(ROOT / "tools/generator" / name, dst / name)
    (dst / "vendor").symlink_to(ROOT / "tools/generator/vendor", target_is_directory=True)
    lib = dst / "src/lib.rs"
    lib.write_text(lib.read_text() + "\npub mod ordering_observer;\n")
    (dst / "src/ordering_observer.rs").write_text(OBSERVER)
    p = dst / "src/diagonal_fitting/curve_model.rs"
    anchor = "            let mut best: Option<(f64, f64, usize, usize, f64, intervals::PairSetup)> = None;"
    replace_once(p, anchor, '            let mut observed = crate::ordering_observer::Group::new(depth, i, j);\n' + anchor)
    anchor = "                    // A returned interval cannot exceed this pair's"
    replace_once(p, anchor, '                    observed.candidate(ea, eb, setup.span_upper_bound());\n' + anchor)
    anchor = "                    let dom = competitors.dominance_for(&setup, ea, eb, Some(&loops));"
    replace_once(p, anchor, '                    let tick = std::time::Instant::now();\n' + anchor + '\n                    observed.result(&dom, tick.elapsed().as_nanos() as u64);')
    anchor = "            let Some((lo, hi, ea, eb, arc, setup)) = best else {"
    replace_once(p, anchor, '            observed.finish(best.as_ref().map(|(lo,hi,ea,eb,..)| (*lo,*hi,*ea,*eb)));\n' + anchor)
    harness = OUT / "harness"
    (harness / "src").mkdir(parents=True)
    (harness / "Cargo.toml").write_text('''[package]
name="ordering-census"
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
println!("{}",serde_json::json!({"cell":row["cell"],"glyphs":report.records.len(),"groups":font_generator::ordering_observer::take()}));
}}''')
    with (OUT / "census-build.log").open("w") as log:
        subprocess.run(["cargo", "build", "--release", "--offline", "--manifest-path", str(harness / "Cargo.toml")],
                       stdout=log, stderr=subprocess.STDOUT, check=True)


OBSERVER = r'''use std::{cell::RefCell,cmp::Ordering,time::Instant};
use serde_json::{Value,json};
use crate::diagonal_fitting::intervals::Dominance;
thread_local!{static ROWS:RefCell<Vec<Value>>=const{RefCell::new(Vec::new())};}
struct Candidate{ea:usize,eb:usize,bound:Option<f64>,span:Option<Option<(f64,f64)>>,ns:u64}
pub struct Group{depth:usize,i:usize,j:usize,items:Vec<Candidate>}
impl Group{
pub fn new(depth:usize,i:usize,j:usize)->Self{Self{depth,i,j,items:Vec::new()}}
pub fn candidate(&mut self,ea:usize,eb:usize,bound:Option<f64>){self.items.push(Candidate{ea,eb,bound,span:None,ns:0});}
pub fn result(&mut self,dom:&Dominance,ns:u64){let c=self.items.last_mut().unwrap();c.ns=ns;c.span=Some(if dom.status!="ok"{None}else{dom.intervals.iter().max_by(|a,b|(a.hi-a.lo).partial_cmp(&(b.hi-b.lo)).unwrap_or(Ordering::Equal)).map(|s|(s.lo,s.hi))});}
pub fn finish(self,expected:Option<(f64,f64,usize,usize)>){
 let tick=Instant::now();let mut order:Vec<usize>=(0..self.items.len()).collect();
 order.sort_unstable_by(|&a,&b|match(self.items[a].bound,self.items[b].bound){(None,None)=>a.cmp(&b),(None,Some(_))=>Ordering::Less,(Some(_),None)=>Ordering::Greater,(Some(x),Some(y))=>y.total_cmp(&x).then(a.cmp(&b))});
 let ordering_ns=tick.elapsed().as_nanos() as u64;
 let nonfinite=self.items.iter().any(|c|matches!(c.span,Some(Some((lo,hi))) if !(hi-lo).is_finite()));
 if nonfinite{order=(0..self.items.len()).collect();}
 let mut winner:Option<usize>=None;let mut queried=vec![false;self.items.len()];
 for &idx in &order{let c=&self.items[idx];
  if winner.is_some_and(|w|{let Some(Some((lo,hi)))=self.items[w].span else{unreachable!()};c.bound.is_some_and(|b|b<hi-lo)}){continue;}
  let outcome=c.span.expect("reordering queried a candidate pruned in the original search");queried[idx]=true;
  if let Some((lo,hi))=outcome{let replace=winner.map_or(true,|w|{let Some(Some((wl,wh)))=self.items[w].span else{unreachable!()};hi-lo>wh-wl || (!nonfinite && hi-lo==wh-wl && idx<w)});if replace{winner=Some(idx);}}
 }
 let actual=winner.map(|idx|{let c=&self.items[idx];let Some(Some((lo,hi)))=c.span else{unreachable!()};(lo.to_bits(),hi.to_bits(),c.ea,c.eb)});
 let expected=expected.map(|(lo,hi,ea,eb)|(lo.to_bits(),hi.to_bits(),ea,eb));assert_eq!(actual,expected,"winner changed");
 let before=self.items.iter().filter(|c|c.span.is_some()).count();let after=queried.iter().filter(|b|**b).count();
 let body_ns:u64=self.items.iter().map(|c|c.ns).sum();let avoided_ns:u64=self.items.iter().enumerate().filter(|(i,_)|!queried[*i]).map(|(_,c)|c.ns).sum();
 let entries:Vec<Value>=self.items.iter().enumerate().map(|(idx,c)|json!({"index":idx,"ea":c.ea,"eb":c.eb,"bound_bits":c.bound.map(f64::to_bits),"queried_before":c.span.is_some(),"queried_after":queried[idx],"span_bits":c.span.flatten().map(|(lo,hi)|[lo.to_bits(),hi.to_bits()]),"ns":c.ns})).collect();
 ROWS.with(|rows|rows.borrow_mut().push(json!({"depth":self.depth,"curve_pair":[self.i,self.j],"candidates":self.items.len(),"queries_before":before,"queries_after":after,"body_ns":body_ns,"avoided_ns":avoided_ns,"ordering_ns":ordering_ns,"nonfinite_fallback":nonfinite,"winner":actual,"entries":entries})));
}}
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
    (OUT / "requests.json").write_text(json.dumps(rows, indent=2))
    with (OUT / "census.jsonl").open("w") as log:
        subprocess.run([str(OUT / "harness/target/release/ordering-census")],
                       input="".join(json.dumps(r) + "\n" for r in rows), text=True, stdout=log, check=True)
    print(json.dumps({"cells": len(rows), "status": "complete"}))


if __name__ == "__main__":
    main()
