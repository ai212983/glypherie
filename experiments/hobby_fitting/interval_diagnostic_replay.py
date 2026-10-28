"""Replay normalized interval queries against frozen/full/lightweight implementations."""
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/diagnostics/interval-diagnostics-optimization'


def main():
    queries = pathlib.Path(sys.argv[1]).resolve()
    dst = OUT / 'query-replay'
    (dst / 'src').mkdir(parents=True, exist_ok=False)
    (dst / 'Cargo.toml').write_text('''[package]
name="interval-diagnostic-replay"
version="0.0.0"
edition="2021"
[dependencies]
serde={version="1",features=["derive"]}
serde_json={version="1",features=["float_roundtrip"]}
''')
    shutil.copyfile(ROOT / 'crates/generator/Cargo.lock', dst / 'Cargo.lock')
    adapter = '''
pub fn replay(v:&serde_json::Value, explain:bool)->serde_json::Value {
 let setup:PairSetup=serde_json::from_value(v["setup"].clone()).unwrap();
 let others:Vec<Border>=serde_json::from_value(v["others"].clone()).unwrap();
 let loops:Option<Vec<Vec<Point>>>=serde_json::from_value(v["loops"].clone()).unwrap();
 let on:Vec<NormOther>=others.iter().map(|b|NormOther{seg:b.seg,tag:b.tag.as_str()}).collect();
 BODY
}
'''
    for label, source in [('before', OUT / 'before/intervals.rs'),
                          ('after', pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else OUT / 'candidate-source/intervals.rs')]:
        text = source.read_text()
        anchor = '#[derive(Clone, Debug)]\npub(super) struct PairSetup'
        assert text.count(anchor) == 1
        text = text.replace(anchor, '#[derive(Clone, Debug, Serialize, Deserialize)]\npub(super) struct PairSetup')
        body = ('let _=explain;serde_json::to_value(dominance_core(&setup,&on,loops.as_deref())).unwrap()'
                if label == 'before' else
                'serde_json::to_value(if explain{dominance_core::<true>(&setup,&on,loops.as_deref())}else{dominance_core::<false>(&setup,&on,loops.as_deref())}).unwrap()')
        (dst / f'src/{label}.rs').write_text(text + adapter.replace('BODY', body))
    (dst / 'src/main.rs').write_text('''#![allow(dead_code)]
#[path=NUMERIC] mod numeric;
mod before;mod after;
fn bits(v:serde_json::Value)->serde_json::Value{match v{
 serde_json::Value::Number(n)=>serde_json::json!({"bits":n.as_f64().unwrap().to_bits()}),
 serde_json::Value::Array(a)=>serde_json::Value::Array(a.into_iter().map(bits).collect()),
 serde_json::Value::Object(m)=>serde_json::Value::Object(m.into_iter().map(|(k,v)|(k,bits(v))).collect()),other=>other}}
fn main(){let rows:serde_json::Value=serde_json::from_str(&std::fs::read_to_string(std::env::args().nth(1).unwrap()).unwrap()).unwrap();let mut count=0;
for row in rows.as_array().unwrap(){for q in row["queries"].as_array().unwrap(){
 let full=before::replay(q,true);let got=after::replay(q,true);assert_eq!(bits(full.clone()),bits(got));
 let mut selected=after::replay(q,false);assert!(selected["spans"].as_array().unwrap().is_empty());
 let mut expected=full;expected.as_object_mut().unwrap().remove("spans");selected.as_object_mut().unwrap().remove("spans");assert_eq!(bits(expected),bits(selected));count+=1;
}}println!("{}",serde_json::json!({"queries":count,"full_mismatches":0,"search_mismatches":0}));}
'''.replace('NUMERIC', json.dumps(str(ROOT / 'crates/generator/src/diagonal_fitting/numeric.rs'))))
    with (OUT / 'query-replay-build.log').open('w') as log:
        subprocess.run(['cargo', 'build', '--release', '--offline', '--manifest-path', str(dst / 'Cargo.toml')],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    result = subprocess.check_output([str(dst / 'target/release/interval-diagnostic-replay'), str(queries)], text=True)
    (OUT / 'query-replay-summary.json').write_text(result)
    print(result, end='')


if __name__ == '__main__':
    main()
