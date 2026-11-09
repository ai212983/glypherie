"""Fit TypeFacet density through parameters, with origins solved in pixels.

Original profile/intrusion code is invoked in pinned Python 2. This adapter's
integer search and density-constrained calibration are project experiments:
docs/designs/text-layout/contextual-spacing-and-healing.md
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import itertools
import json
import math
from pathlib import Path
import subprocess
import time

from density_probe import BitmapOracle
from filtered_walls import clearance_min_step_no_overlap
from solver import Solver, bitmap_commands
from typefacet_probe import HERE, IMAGE, REVISION, rectangle, sha, run_job
from typefacet_density_review import DOMAIN, CAPTURE_SHA


POLICY = "typefacet-constrained-integer-v1"
FAMILIES = dict(endpoint=("tt", "rf"), body=("nn",), intrusion=("oo",))
HELD_OUT = ("gs", "hi", "rd", "ri", "ca", "os", "bd", "du", "ff", "cc", "zz", "al", "nx", "en", "op", "se",
            "ip", "pe", "ig", "oe", "kh", "rn", "xn", "co", "jo", "yd", "le", "pi", "te", "tp", "ct", "ab")
MAX_DISTANCE = (.04, .06, .08, .10, .12, .14, .16, .18, .20)
INTRUSION = (0., .025, .05, .075, .10, .15, .20)
REFINEMENT = ((.005, .0125), (.0025, .00625))
DENSITY_TOLERANCE = 1/64


def params(normal, intrusion):
    return dict(min_distance_ems=0., max_distance_ems=normal, intrusion_tolerance_ems=intrusion,
                max_x_extrema_overlap_ems=.1, precision_ems=.005)


def parameter_key(record):
    p = record["parameters"]
    return p["max_distance_ems"], p["intrusion_tolerance_ems"]


def reference_error(steps, targets, omit=None):
    families = [sum((steps[p]-targets[p])**2 for p in pairs)/len(pairs)
                for name, pairs in FAMILIES.items() if name != omit]
    return math.sqrt(math.fsum(families)/len(families))


def select(records, omit=None):
    feasible = [r for r in records if abs(r["density_error_px"]) <= DENSITY_TOLERANCE]
    if feasible:
        return min(feasible, key=lambda r: (r["reference_errors"][str(omit)], abs(r["density_error_px"]),
                   r["parameters"]["intrusion_tolerance_ems"], parameter_key(r))), True
    return min(records, key=lambda r: (abs(r["density_error_px"]), r["reference_errors"][str(omit)], parameter_key(r))), False


def batch(root, reference, name, request, settings, cold=False):
    candidates = [dict(id="%.8f:%.8f" % (m, t), parameters=params(m, t)) for m, t in settings]
    path = root/(name+".json")
    path.write_text(json.dumps(dict(request, candidates=candidates, cold_cache=cold), allow_nan=False))
    envpath = ":".join(["/adapters"]+["/reference/"+p for p in ["python/src-main", "dependencies/RoboFab/Lib",
        "dependencies/FontTools/Lib", "dependencies/pystache", "dependencies/PyYAML/lib", "dependencies/svgwrite"]])
    command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp",
        "-v", str(reference)+":/reference:ro", "-v", str(HERE/"reference")+":/adapters:ro", "-v", str(root)+":/work:rw",
        "-e", "PYTHONPATH="+envpath, IMAGE, "python", "-B", "/adapters/typefacet_integer.py", "/work/"+path.name, "/work/"+name]
    start = time.monotonic()
    with (root/(name+".log")).open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, text=True, timeout=900)
    produced = root/name/"integer.json"
    if result.returncode or not produced.is_file():
        raise RuntimeError("integer batch failed: "+str(root/(name+".log")))
    print(name, len(settings), "settings", round(time.monotonic()-start, 2), "s", flush=True)
    return json.loads(produced.read_text())["candidates"]


def stage(root, reference, name, request, settings):
    groups = [(m, sorted(p for p in settings if p[0] == m)) for m in sorted({p[0] for p in settings})]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(batch, root, reference, name+"-"+str(i), request, values) for i, (_m, values) in enumerate(groups)]
        return [record for future in futures for record in future.result()]


def summarize(records, source_mean, targets, oracle):
    for record in records:
        steps = {p["pair"]: p["step_px"] for p in record["pairs"]}
        if set(steps) != {chr(a)+chr(b) for a, b in DOMAIN}:
            raise ValueError("incomplete fixed domain")
        for pair in record["pairs"]:
            tests = pair["tested"]
            if [p["step"] for p in tests] != list(range(pair["first"], pair["last"]+1)):
                raise ValueError("incomplete integer enumeration")
            accepted = [p["step"] for p in tests if p["accepted"]]
            if not accepted or pair["step_px"] != min(accepted):
                raise ValueError("selected step is not the smallest admissible integer")
            for test in tests:
                if test["accepted"] != all(test[k] for k in ("minimum_ok", "extrema_ok", "full", "ascender")):
                    raise ValueError("predicate combination differs")
            a, b = map(ord, pair["pair"])
            contact = oracle.contacts(a, b, pair["step_px"])
            if not contact["overlap_free"] or not contact["same_row_wall_order"]:
                raise ValueError("emitted placement violates pixel geometry")
        record.update(mean_emitted_px=math.fsum(steps.values())/len(DOMAIN),
                      density_error_px=math.fsum(steps.values())/len(DOMAIN)-source_mean,
                      reference_errors={str(omit): reference_error(steps, targets, omit) for omit in (None, *FAMILIES)})


def refinement_settings(records, steps):
    best, _ = select(records)
    anchors = [best]
    for sign in (-1, 1):
        side = [r for r in records if r["density_error_px"]*sign >= 0]
        if side:
            anchors.append(min(side, key=lambda r: (abs(r["density_error_px"]),r["reference_errors"]["None"])))
    values = {tuple(round(v, 8) for v in p) for r in anchors
              for p in itertools.product(*(tuple(v+i*s for i in (-1,0,1)) for v, s in zip(parameter_key(r), steps)))
              if MAX_DISTANCE[0] <= p[0] <= MAX_DISTANCE[-1] and INTRUSION[0] <= p[1] <= INTRUSION[-1]}
    return sorted(values-{parameter_key(r) for r in records})


def fixture_request():
    # Odd half-FU contact: a 62.5 FU rectangle is exactly one 16px-grid cell.
    glyphs = [dict(name=c, codepoint=ord(c), advance=125, commands=rectangle(*box)) for c, box in
              [("a",(0,0,62.5,125)), ("b",(0,0,62.5,125)), ("c",(0,0,125,125)), ("d",(0,250,125,125))]]
    return dict(units_per_em=1000,size_px=16,ascender=800,descender=-200,glyphs=glyphs,
                pairs=[list("ab"),list("cd")],bitmap_minimums=dict(ab=1,cd=None))


def verify_selected(root, reference, request, best):
    run_job((root,reference,"original-full",dict(request,parameters=best["parameters"])))
    envpath = ":".join(["/adapters"]+["/reference/"+p for p in ["python/src-main", "dependencies/RoboFab/Lib",
        "dependencies/FontTools/Lib", "dependencies/pystache", "dependencies/PyYAML/lib", "dependencies/svgwrite"]])
    command = ["docker","run","--rm","--network","none","--read-only","--tmpfs","/tmp",
        "-v",str(reference)+":/reference:ro","-v",str(HERE/"reference")+":/adapters:ro","-v",str(root)+":/work:rw",
        "-e","PYTHONPATH="+envpath,IMAGE,"python","-B","/adapters/typefacet_integer_verify.py",
        "/work/selected-cold.json","/work/original-full/capture.json","/work/summary.json",
        "/work/original-predicate-verification.json"]
    with (root/"verification.log").open("w") as log:
        result = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,text=True,timeout=180)
    if result.returncode or not (root/"original-predicate-verification.json").is_file():
        raise RuntimeError("original predicate verification failed; see verification.log")


def run(output, reference, capture_path):
    root, reference, capture_path = [Path(p).resolve() for p in (output, reference, capture_path)]
    if root.exists():
        raise ValueError("output must be new")
    if (subprocess.check_output(["git","-C",str(reference),"rev-parse","HEAD"],text=True).strip() != REVISION
            or subprocess.check_output(["git","-C",str(reference),"status","--porcelain"],text=True)):
        raise ValueError("original reference must be clean and pinned")
    raw = capture_path.read_bytes()
    if sha(raw) != CAPTURE_SHA:
        raise ValueError("this experiment requires the frozen capture")
    capture = json.loads(raw)
    solver = Solver(capture)
    oracle = BitmapOracle(solver.glyphs)
    source = {chr(a)+chr(b): solver.glyphs[a]["source_advance_px"]+solver.source_pairs.get((a,b),0) for a,b in DOMAIN}
    mean = math.fsum(source.values())/len(DOMAIN)
    refs = {p for pairs in FAMILIES.values() for p in pairs}
    assert not refs & set(HELD_OUT)
    targets = {p: source[p] for p in refs}
    request_path = HERE.parents[1]/"out/diagnostics/contextual-spacing/typefacet-calibration/fit-03/full-cells.json"
    request_raw = request_path.read_bytes()
    request = json.loads(request_raw)
    for glyph in request["glyphs"]:
        g = solver.glyphs[glyph["codepoint"]]
        scale = capture["units_per_em"]/capture["size_px"]
        if (glyph["commands"] != bitmap_commands(g["bitmap"],scale)
                or glyph["advance"] != g["source_advance_px"]*scale):
            raise ValueError("original request differs from retained bitmaps or metrics")
    request = {k:v for k,v in request.items() if k not in ("candidates", "cold_cache", "parameters")}
    request.update(size_px=capture["size_px"], pairs=[[chr(a),chr(b)] for a,b in DOMAIN],
        bitmap_minimums={chr(a)+chr(b):clearance_min_step_no_overlap(solver.glyphs[a]["bitmap"],solver.glyphs[b]["bitmap"]) for a,b in DOMAIN})
    root.mkdir(parents=True)
    protocol = dict(policy=POLICY,revision=REVISION,image=IMAGE,capture_sha256=sha(raw),capture_path=str(capture_path),
        fixed_parameters=dict(min_distance_ems=0.,max_x_extrema_overlap_ems=.1,precision_ems=.005,tracking=0.),
        grid=dict(normal=MAX_DISTANCE,intrusion=INTRUSION),refinement=REFINEMENT,families=FAMILIES,held_out=HELD_OUT,
        targets_px=targets,source_mean_px=mean,density_tolerance_px=DENSITY_TOLERANCE,
        objective="reference RMS within emitted-density band; closest-density diagnostic if none feasible",
        domain="complete ASCII lowercase Cartesian product",quantization="integer pixels, no intermediate FU rounding or post-solve shift",
        input_request_sha256=sha(request_raw),host_sha256=sha(Path(__file__).read_bytes()),
        adapter_sha256=sha((HERE/"reference/typefacet_integer.py").read_bytes()),
        verifier_sha256=sha((HERE/"reference/typefacet_integer_verify.py").read_bytes()))
    (root/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    (root/"start-status.txt").write_text(subprocess.check_output(["git","status","--short"],text=True))
    fixture = batch(root,reference,"analytic-fixture",fixture_request(),[(0.,0.)])[0]
    if {p["pair"]:p["step_px"] for p in fixture["pairs"]} != dict(ab=1,cd=2):
        raise ValueError("analytic contact or no-shared-profile fallback failed")
    records = stage(root,reference,"coarse",request,list(itertools.product(MAX_DISTANCE,INTRUSION)))
    summarize(records,mean,targets,oracle)
    for i, increments in enumerate(REFINEMENT):
        settings = refinement_settings(records,increments)
        if settings:
            more = stage(root,reference,"refine-"+str(i),request,settings)
            summarize(more,mean,targets,oracle)
            records += more
    best, feasible = select(records)
    near = [r for r in records if abs(r["density_error_px"]) <= DENSITY_TOLERANCE
            and r["reference_errors"]["None"] <= best["reference_errors"]["None"]+DENSITY_TOLERANCE] if feasible else []
    steps = {p["pair"]:p["step_px"] for p in best["pairs"]}
    alt = [dict(parameters=r["parameters"],density_error_px=r["density_error_px"],rmse_px=r["reference_errors"]["None"],
                changed_pairs=sum(p["step_px"] != steps[p["pair"]] for p in r["pairs"])) for r in near]
    cold = batch(root,reference,"selected-cold",request,[parameter_key(best)],cold=True)[0]
    if cold["pairs"] != best["pairs"]:
        raise ValueError("cold original-code replay differs")
    summary = dict(schema="typefacet-integer-fit-v1",status="density_feasible" if feasible else "no_density_feasible_setting",
        protocol=protocol,selected=best,settings_evaluated=len(records),density_feasible_settings=sum(abs(r["density_error_px"])<=DENSITY_TOLERANCE for r in records),
        alternatives=alt,cold_replay_identical=True,analytic_contact_passed=True,postsolve_correction_px=0,
        omitted_family={name:dict(parameters=select(records,name)[0]["parameters"],feasible=select(records,name)[1]) for name in FAMILIES})
    (root/"all-settings.json").write_text(json.dumps(records,allow_nan=False)+"\n")
    (root/"summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False)+"\n")
    verify_selected(root,reference,request,best)
    print(json.dumps(dict(status=summary["status"],parameters=best["parameters"],mean_px=best["mean_emitted_px"],
                         density_error_px=best["density_error_px"],reference_rmse_px=best["reference_errors"]["None"],settings=len(records),
                         near_fits=len(near),max_near_disagreement=max((a["changed_pairs"] for a in alt),default=0)),indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output")
    p.add_argument("--reference",default="out/diagnostics/contextual-spacing/yinyang-alternatives/typefacet")
    p.add_argument("--capture",default="out/diagnostics/contextual-spacing/preset-preview/captures/Literata-reading/capture.json")
    args = p.parse_args()
    run(args.output,args.reference,args.capture)
