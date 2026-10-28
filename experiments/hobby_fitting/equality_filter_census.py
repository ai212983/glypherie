"""Replay captured normalized dominance queries with diagnostic equality-call counters."""
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/diagnostics/equality-filter-optimization'

OBSERVER = r'''use serde_json::{json,Value};
use std::cell::RefCell;
thread_local!{static ROWS:RefCell<Vec<Value>>=const{RefCell::new(Vec::new())};}
#[derive(Default)] struct Calls { point:u64,line:u64,no_root:u64,bernstein:u64,root:u64,uncertain:u64,ns:u64,no_root_ns:u64 }
pub struct Query{cells:usize,done:bool,items:Vec<Calls>}
impl Query{
 pub fn new(n:usize)->Self{Self{cells:0,done:false,items:(0..n).map(|_|Calls::default()).collect()}}
 pub fn cells(&mut self,n:usize){self.cells=n;}
 pub fn record(&mut self,i:usize,line:bool,ns:u64,bernstein:bool,roots:usize,uncertain:bool){
  let c=&mut self.items[i];if line{c.line+=1}else{c.point+=1};c.ns+=ns;
  if uncertain{c.uncertain+=1;}else if roots==0{c.no_root+=1;c.no_root_ns+=ns;if bernstein{c.bernstein+=1;}}else{c.root+=1;}
 }
 pub fn done(&mut self){self.done=true;}
}
impl Drop for Query{fn drop(&mut self){ROWS.with(|r|r.borrow_mut().push(json!({"cells":self.cells,"complete":self.done,"competitors":self.items.iter().map(|c|json!({"point":c.point,"line":c.line,"no_root":c.no_root,"bernstein":c.bernstein,"root":c.root,"uncertain":c.uncertain,"ns":c.ns,"no_root_ns":c.no_root_ns})).collect::<Vec<_>>()})));}}
pub fn take()->Vec<Value>{ROWS.with(|r|std::mem::take(&mut *r.borrow_mut()))}
'''

ADAPTER = r'''
pub fn replay(v:&serde_json::Value)->Dominance{
 let setup:PairSetup=serde_json::from_value(v["setup"].clone()).unwrap();
 let others:Vec<Border>=serde_json::from_value(v["others"].clone()).unwrap();
 let loops:Option<Vec<Vec<Point>>>=serde_json::from_value(v["loops"].clone()).unwrap();
 let on:Vec<NormOther>=others.iter().map(|b|NormOther{seg:b.seg,tag:&b.tag}).collect();
 dominance_core(&setup,&on,loops.as_deref())
}
fn observer_bernstein(a:f64,b:f64,c:f64)->bool{
 let scale=a.abs().max(b.abs()).max(c.abs());if scale<=EPS{return false;}
 let middle=c+b/2.0;let end=fsum3(c,b,a);
 let lower=next_after(next_after(c.min(middle).min(end),f64::NEG_INFINITY),f64::NEG_INFINITY);
 let upper=next_after(next_after(c.max(middle).max(end),f64::INFINITY),f64::INFINITY);
 lower>EPS*scale || upper< -EPS*scale
}
'''


def prepare():
    queries = pathlib.Path(sys.argv[1]).resolve()
    dst = OUT / 'census'
    (dst / 'src').mkdir(parents=True, exist_ok=False)
    (dst / 'Cargo.toml').write_text('''[package]
name="equality-census"
version="0.0.0"
edition="2021"
[dependencies]
serde={version="1",features=["derive"]}
serde_json={version="1",features=["float_roundtrip"]}
''')
    shutil.copyfile(ROOT / 'crates/generator/Cargo.lock', dst / 'Cargo.lock')
    original = (OUT / 'before/intervals.rs').read_text()
    original = original.replace('#[derive(Clone, Debug)]\npub(super) struct PairSetup',
                                '#[derive(Clone, Debug, Serialize, Deserialize)]\npub(super) struct PairSetup')
    (dst / 'src/frozen.rs').write_text(original + ADAPTER)
    text = original
    def replace(old, new):
        nonlocal text
        assert text.count(old) == 1, old
        text = text.replace(old, new, 1)
    replace('fn dominance_core(setup: &PairSetup, on: &[NormOther], ln: Option<&[Vec<Point>]>) -> Dominance {',
            'fn dominance_core(setup: &PairSetup, on: &[NormOther], ln: Option<&[Vec<Point>]>) -> Dominance {\n    let mut observed = crate::observer::Query::new(on.len());')
    replace('    for (l, r) in cuts.clone() {', '    observed.cells(cuts.len());\n    for (l, r) in cuts.clone() {')
    replace('        for branch in &branches {', '        for (index, branch) in branches.iter().enumerate() {')
    replace('            let mut qs = Vec::with_capacity(3);', '            let tick = std::time::Instant::now();\n            let mut qs = Vec::with_capacity(3);')
    replace('            let (roots, uncertain) = quad_roots(qa, qb, qc);',
            '            let (roots, uncertain) = quad_roots(qa, qb, qc);\n            let ns = tick.elapsed().as_nanos() as u64;\n            observed.record(index, matches!(branch, Branch::Ln {..}), ns, observer_bernstein(qa,qb,qc), roots.len(), uncertain);')
    replace('    splits.extend(extra);', '    observed.done();\n    splits.extend(extra);')
    (dst / 'src/observed.rs').write_text(text + ADAPTER)
    (dst / 'src/observer.rs').write_text(OBSERVER)
    (dst / 'src/main.rs').write_text(r'''#![allow(dead_code)]
#[path=NUMERIC] mod numeric;
mod frozen;mod observed;mod observer;
fn bits(v:serde_json::Value)->serde_json::Value{match v{
 serde_json::Value::Number(n)=>serde_json::json!({"bits":n.as_f64().unwrap().to_bits()}),
 serde_json::Value::Array(a)=>serde_json::Value::Array(a.into_iter().map(bits).collect()),
 serde_json::Value::Object(m)=>serde_json::Value::Object(m.into_iter().map(|(k,v)|(k,bits(v))).collect()),v=>v}}
fn main(){let rows:serde_json::Value=serde_json::from_str(&std::fs::read_to_string(std::env::args().nth(1).unwrap()).unwrap()).unwrap();
for row in rows.as_array().unwrap(){let mut count=0;for q in row["queries"].as_array().unwrap(){
 let a=frozen::replay(q);let b=observed::replay(q);assert_eq!(bits(serde_json::to_value(a).unwrap()),bits(serde_json::to_value(b).unwrap()));count+=1;
}println!("{}",serde_json::json!({"cell":row["cell"],"queries":count,"full_mismatches":0,"observed":observer::take()}));}}
'''.replace('NUMERIC', json.dumps(str(ROOT / 'crates/generator/src/diagonal_fitting/numeric.rs'))))
    with (OUT / 'census-build.log').open('w') as log:
        subprocess.run(['cargo', 'build', '--release', '--offline', '--manifest-path', str(dst / 'Cargo.toml')],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    with (OUT / 'census.jsonl').open('w') as log:
        subprocess.run([str(dst / 'target/release/equality-census'), str(queries)], stdout=log, check=True)
    data = [json.loads(line) for line in (OUT / 'census.jsonl').read_text().splitlines()]
    totals = dict(queries=0, complete_queries=0, calls=0, no_root=0, bernstein=0, root=0, uncertain=0,
                  point=0, line=0, ns=0, no_root_ns=0, all_clear_competitor_calls=0, all_clear_competitor_ns=0)
    for row in data:
        totals['queries'] += row['queries']
        for q in row['observed']:
            totals['complete_queries'] += q['complete']
            for c in q['competitors']:
                calls = c['point'] + c['line']
                totals['calls'] += calls
                for key in ['no_root', 'bernstein', 'root', 'uncertain', 'point', 'line', 'ns', 'no_root_ns']:
                    totals[key] += c[key]
                if q['complete'] and c['no_root'] == calls:
                    totals['all_clear_competitor_calls'] += calls
                    totals['all_clear_competitor_ns'] += c['ns']
    (OUT / 'census-summary.json').write_text(json.dumps(totals, indent=2))
    print(json.dumps(totals))


if __name__ == '__main__':
    prepare()
