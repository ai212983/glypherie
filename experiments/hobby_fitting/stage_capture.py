"""Capture and compare complete native reports for fitting performance experiments."""
import concurrent.futures
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(os.environ.get("CAPTURE_OUTPUT_DIR", ROOT / "out/diagnostics/stage-eligibility-optimization"))


def build(label):
    binary = OUT / f"capture-{label}"
    assert not binary.exists(), "Preserve the frozen capture executable."
    harness = OUT / "capture-harness"
    (harness / "src").mkdir(parents=True, exist_ok=True)
    (harness / "Cargo.toml").write_text('''[package]
name="stage-capture"
version="0.0.0"
edition="2021"
[dependencies]
font_generator={path=GENERATOR_PATH}
serde_json={version="1",features=["float_roundtrip"]}
'''.replace("GENERATOR_PATH", json.dumps(str(ROOT / "crates/generator"))))
    locked = (harness / "Cargo.lock").exists()
    if not locked:
        shutil.copyfile(ROOT / "crates/generator/Cargo.lock", harness / "Cargo.lock")
    (harness / "src/main.rs").write_text('''use std::io::{self,BufRead};
fn main(){for line in io::stdin().lock().lines(){
let row:serde_json::Value=serde_json::from_str(&line.unwrap()).unwrap();
let bytes=std::fs::read(row["font"].as_str().unwrap()).unwrap();
let request=serde_json::from_value(row["request"].clone()).unwrap();
let pipeline=serde_json::from_value(row["pipeline"].clone()).unwrap();
let result=font_generator::candidate::render_with_pipeline(&bytes,&request,pipeline);
let report=match result{Ok(r)=>serde_json::json!({"ok":r}),Err(e)=>serde_json::json!({"error":e.to_string()})};
println!("{}",serde_json::json!({"cell":row["cell"],"output":report}));
}}''')
    with (OUT / f"capture-build-{label}.log").open("w") as log:
        subprocess.run(["cargo", "build", "--release", "--offline", *(["--locked"] if locked else []),
                        "--manifest-path", str(harness / "Cargo.toml"), "--target-dir", str(ROOT / "crates/generator/target")],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    shutil.copyfile(ROOT / "crates/generator/target/release/stage-capture", binary)
    binary.chmod(0o755)


def requests():
    for family in ["Roboto", "SourceSans3"]:
        for weight in [300, 400, 700]:
            for size in [12, 14, 16, 18, 20, 24]:
                for fitting, extension in [("font_hints_auto", "font-hints-auto-01"), ("upstream_mono", "mono-width-01")]:
                    for raster in ["free_type_mono", "free_type_mono_terminals"]:
                        for diagonal in [False, True]:
                            axes = {"wght": weight, **({"wdth": 100} if family == "Roboto" else {})}
                            yield {"cell": [family, weight, size, fitting, raster, diagonal],
                                   "font": str(ROOT / f"fonts/{family}.ttf"),
                                   "request": {"profile": "mono_1bit", "extensions": extension,
                                               "settings": {"size_px": size, "axes": axes,
                                                            "characters": "".join(chr(i) for i in range(32, 127)),
                                                            "mono_raster": {"dropout": "smart", "include_stubs": True, "font_instructions": True}}},
                                   "pipeline": {"fitting": fitting, "rasterization": raster, "diagonal_fitting": diagonal}}


def capture(label):
    rows = list(requests())
    (OUT / "capture-requests.json").write_text(json.dumps(rows, indent=2))

    def shard(i):
        with (OUT / f"captures-{label}-{i}.jsonl").open("w") as log:
            subprocess.run([str(OUT / f"capture-{label}")],
                           input="".join(json.dumps(r) + "\n" for r in rows[i::6]),
                           text=True, stdout=log, check=True)
        print(json.dumps({"label": label, "shard": i, "cases": len(rows[i::6])}), flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(shard, range(6)))


def compare():
    mismatches = []
    cases = glyphs = 0
    for shard in range(6):
        before = [json.loads(s) for s in (OUT / f"captures-before-{shard}.jsonl").read_text().splitlines()]
        after = [json.loads(s) for s in (OUT / f"captures-after-{shard}.jsonl").read_text().splitlines()]
        assert len(before) == len(after)
        for x, y in zip(before, after, strict=True):
            assert x["cell"] == y["cell"]
            assert "ok" in x["output"] and "ok" in y["output"], x["cell"]
            cases += 1
            glyphs += len(y["output"]["ok"]["records"])
            if json.dumps(x, sort_keys=True) != json.dumps(y, sort_keys=True):
                mismatches.append({"cell": x["cell"], "before": x, "after": y})
    summary = {"cases": cases, "glyphs": glyphs, "full_capture_mismatches": len(mismatches)}
    (OUT / "capture-comparison.json").write_text(json.dumps(summary, indent=2))
    (OUT / "capture-mismatches.json").write_text(json.dumps(mismatches, indent=2))
    print(json.dumps(summary))
    return bool(mismatches)


if __name__ == "__main__":
    if sys.argv[1] in ["build-before", "build-after"]:
        build(sys.argv[1].removeprefix("build-"))
        raise SystemExit(0)
    if sys.argv[1] == "compare":
        raise SystemExit(compare())
    assert sys.argv[1] in ["before", "after"]
    capture(sys.argv[1])
