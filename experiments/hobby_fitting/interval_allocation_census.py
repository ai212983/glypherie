"""Count allocations in curve-search dominance queries in a diagnostic-only copy."""
import json
import os
import shutil
import subprocess
from certificate_census import ROOT, replace_once, requests

OUT = ROOT / 'out/diagnostics/interval-diagnostics-optimization'
LABEL = os.environ.get('CENSUS_LABEL', 'before')

OBSERVER = r'''use std::alloc::{GlobalAlloc,Layout,System};
use std::sync::atomic::{AtomicBool,AtomicU64,Ordering::Relaxed};
use serde_json::{json,Value};
struct Alloc;
#[global_allocator] static ALLOC:Alloc=Alloc;
static ACTIVE:AtomicBool=AtomicBool::new(false);
static CONTACT:AtomicBool=AtomicBool::new(false);
static CALLS:AtomicU64=AtomicU64::new(0);
static ALLOCS:AtomicU64=AtomicU64::new(0);
static REALLOCS:AtomicU64=AtomicU64::new(0);
static BYTES:AtomicU64=AtomicU64::new(0);
static CONTACT_ALLOCS:AtomicU64=AtomicU64::new(0);
static SPANS:AtomicU64=AtomicU64::new(0);
unsafe impl GlobalAlloc for Alloc{
 unsafe fn alloc(&self,l:Layout)->*mut u8{let p=System.alloc(l);if ACTIVE.load(Relaxed){ALLOCS.fetch_add(1,Relaxed);BYTES.fetch_add(l.size() as u64,Relaxed);if CONTACT.load(Relaxed){CONTACT_ALLOCS.fetch_add(1,Relaxed);}}p}
 unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{let p=System.alloc_zeroed(l);if ACTIVE.load(Relaxed){ALLOCS.fetch_add(1,Relaxed);BYTES.fetch_add(l.size() as u64,Relaxed);if CONTACT.load(Relaxed){CONTACT_ALLOCS.fetch_add(1,Relaxed);}}p}
 unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{let p=System.realloc(p,l,n);if ACTIVE.load(Relaxed){REALLOCS.fetch_add(1,Relaxed);BYTES.fetch_add(n as u64,Relaxed);}p}
 unsafe fn dealloc(&self,p:*mut u8,l:Layout){System.dealloc(p,l)}
}
pub struct Query;
impl Query{pub fn new()->Self{assert!(!ACTIVE.swap(true,Relaxed));CALLS.fetch_add(1,Relaxed);Self}pub fn finish(self,spans:usize){SPANS.fetch_add(spans as u64,Relaxed);}}
impl Drop for Query{fn drop(&mut self){ACTIVE.store(false,Relaxed);}}
pub struct Contact;
pub fn contact()->Contact{CONTACT.store(true,Relaxed);Contact}
impl Drop for Contact{fn drop(&mut self){CONTACT.store(false,Relaxed);}}
pub fn take()->Value{json!({"queries":CALLS.swap(0,Relaxed),"allocations":ALLOCS.swap(0,Relaxed),"reallocations":REALLOCS.swap(0,Relaxed),"requested_bytes":BYTES.swap(0,Relaxed),"contact_allocations":CONTACT_ALLOCS.swap(0,Relaxed),"materialized_spans":SPANS.swap(0,Relaxed)})}
'''


def prepare():
    dst = OUT / f'instrumented-{LABEL}'
    assert not dst.exists(), 'Preserve frozen instrumentation; select a new CENSUS_LABEL.'
    shutil.copytree(ROOT / 'crates/generator/src', dst / 'src')
    for name in ['Cargo.toml', 'Cargo.lock', 'build.rs']:
        shutil.copyfile(ROOT / 'crates/generator' / name, dst / name)
    (dst / 'vendor').symlink_to(ROOT / 'crates/generator/vendor', target_is_directory=True)
    lib = dst / 'src/lib.rs'
    lib.write_text(lib.read_text() + '\npub mod allocation_observer;\n')
    (dst / 'src/allocation_observer.rs').write_text(OBSERVER)
    p = dst / 'src/diagonal_fitting/curve_model.rs'
    search = 'competitors.search_for(' in p.read_text()
    method = 'search_for' if search else 'dominance_for'
    anchor = f'                    let dom = competitors.{method}(&setup, ea, eb, Some(&loops));'
    spans = '0' if search else 'dom.spans.len()'
    replace_once(p, anchor, '                    let tracker = crate::allocation_observer::Query::new();\n' + anchor + f'\n                    tracker.finish({spans});')
    p = dst / 'src/diagonal_fitting/intervals.rs'
    replace_once(p, '    let no = |stage:', '    let _allocation_contact = crate::allocation_observer::contact();\n    let no = |stage:')
    harness = OUT / f'allocation-harness-{LABEL}'
    (harness / 'src').mkdir(parents=True)
    (harness / 'Cargo.toml').write_text(f'''[package]
name="allocation-census"
version="0.0.0"
edition="2021"
[dependencies]
font_generator={{path="../instrumented-{LABEL}"}}
serde_json="1"
''')
    shutil.copyfile(ROOT / 'crates/generator/Cargo.lock', harness / 'Cargo.lock')
    (harness / 'src/main.rs').write_text('''use std::io::{self,BufRead};
fn main(){for line in io::stdin().lock().lines(){
let row:serde_json::Value=serde_json::from_str(&line.unwrap()).unwrap();
let bytes=std::fs::read(row["font"].as_str().unwrap()).unwrap();
let request=serde_json::from_value(row["request"].clone()).unwrap();
let pipeline=serde_json::from_value(row["pipeline"].clone()).unwrap();
let report=font_generator::candidate::render_with_pipeline(&bytes,&request,pipeline).unwrap();
println!("{}",serde_json::json!({"cell":row["cell"],"glyphs":report.records.len(),"counts":font_generator::allocation_observer::take()}));
}}''')
    with (OUT / f'allocation-build-{LABEL}.log').open('w') as log:
        subprocess.run(['cargo', 'build', '--release', '--offline', '--manifest-path', str(harness / 'Cargo.toml')],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    rows = list(requests())
    (OUT / 'allocation-requests.json').write_text(json.dumps(rows, indent=2))
    with (OUT / f'allocations-{LABEL}.jsonl').open('w') as log:
        subprocess.run([str(harness / 'target/release/allocation-census')],
                       input=''.join(json.dumps(row) + '\n' for row in rows),
                       text=True, stdout=log, check=True)
    data = [json.loads(line) for line in (OUT / f'allocations-{LABEL}.jsonl').read_text().splitlines()]
    totals = {key: sum(row['counts'][key] for row in data) for key in data[0]['counts']}
    (OUT / f'allocation-summary-{LABEL}.json').write_text(json.dumps({'cells': len(data), 'totals': totals}, indent=2))
    print(json.dumps({'label': LABEL, 'cells': len(data), 'totals': totals}))


if __name__ == '__main__':
    prepare()
