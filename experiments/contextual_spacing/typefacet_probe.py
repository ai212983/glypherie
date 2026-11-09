"""Bounded TypeFacet reference/UFO reproduction and delivered-cell diagnostic.

Runs the original Python 2 application; it does not port the spacing model.
Author manual parameters are frozen before any held-out measurements.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

from density_probe import BitmapOracle
from solver import Solver, Controls, bitmap_commands, pixel_round


REVISION = "8c6db26d0c599ece16f3704696811275120a4044"
IMAGE = "python@sha256:6c1ffdff499e29ea663e6e67c9b6b9a3b401d554d2c9f061f9a45344e3992363"
PARAMETERS = dict(min_distance_ems=.04, max_distance_ems=.1, intrusion_tolerance_ems=.1,
                  max_x_extrema_overlap_ems=.1, precision_ems=.005)
REFERENCES = ("TT", "tt", "NN", "nn", "OO", "oo", "AA")
HELD_OUT = ("rd", "ri", "ca", "os", "bd", "du", "ff", "cc", "zz")
HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def rectangle(x, y, width, height):
    return [dict(op="move_to", x=x, y=y), dict(op="line_to", x=x+width, y=y),
            dict(op="line_to", x=x+width, y=y+height), dict(op="line_to", x=x, y=y+height), dict(op="close")]


def fixture():
    glyphs = [dict(name=c, codepoint=ord(c), advance=500, commands=rectangle(*r)) for c, r in
              [("a", (0,0,200,500)), ("b", (0,0,200,500)), ("c", (-20,0,200,200)), ("d", (0,400,200,200))]]
    glyphs += [dict(name="e", codepoint=101, advance=500, commands=[dict(op="move_to", x=0,y=0),
                dict(op="quad_to", x1=400,y1=250,x=0,y=500),dict(op="close")]),
               dict(name="f", codepoint=102, advance=500, commands=[dict(op="move_to",x=0,y=0),
                dict(op="curve_to",x1=400,y1=0,x2=400,y2=500,x=0,y=500),dict(op="close")])]
    return dict(units_per_em=1000, ascender=800, descender=-200, glyphs=glyphs,
                pairs=[list(pair) for pair in ("ab","cd","ef","fe")], parameters=PARAMETERS)


def scaled(request, factor):
    result = copy.deepcopy(request)
    for key in ("units_per_em", "ascender", "descender"):
        result[key] *= factor
    for glyph in result["glyphs"]:
        glyph["advance"] *= factor
        for command in glyph["commands"]:
            for key in set(command)-{"op"}:
                command[key] *= factor
    return result


def capture_request(capture, geometry):
    glyphs = {g["codepoint"]:g for g in capture["glyphs"]}
    letters = sorted(set("abcdefghijklmnopqrstuvwxyz"+"".join(REFERENCES)))
    scale = capture["units_per_em"] / capture["size_px"]
    records = []
    for char in letters:
        glyph = glyphs[ord(char)]
        commands = glyph["source_commands"] if geometry == "source" else bitmap_commands(glyph["bitmap"], scale)
        records.append(dict(name=char, codepoint=ord(char), advance=glyph["source_advance_px"]*scale, commands=commands))
    metrics = capture["metrics"]
    pairs = sorted(set((a,b) for a in "abcdefghijklmnopqrstuvwxyz" for b in "abcdefghijklmnopqrstuvwxyz")
                   | {tuple(pair) for pair in REFERENCES})
    return dict(units_per_em=capture["units_per_em"], ascender=metrics["ascent_26_6"]/64*scale,
                descender=metrics["descent_26_6"]/64*scale, glyphs=records, pairs=pairs, parameters=PARAMETERS)


def run_job(item):
    root, reference, name, request = item
    path = root/(name+".json")
    path.write_text(json.dumps(request))
    envpath = ":".join("/reference/"+p for p in ["python/src-main", "dependencies/RoboFab/Lib", "dependencies/FontTools/Lib",
                       "dependencies/pystache", "dependencies/PyYAML/lib", "dependencies/svgwrite"])
    command = ["docker","run","--rm","--network","none","--read-only","--tmpfs","/tmp",
               "-v",str(reference)+":/reference:ro", "-v",str(HERE/"reference/typefacet_capture.py")+":/driver.py:ro",
               "-v",str(root)+":/work:rw","-e","PYTHONPATH="+envpath,IMAGE,"python","-B","/driver.py",
               "/work/"+path.name,"/work/"+name]
    started = time.monotonic()
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    (root/(name+".log")).write_text(result.stdout)
    produced = root/name/"capture.json"
    if result.returncode != 0 or not produced.is_file() or "CAPTURE_COMPLETE" not in result.stdout:
        raise RuntimeError("reference job failed: "+name+"; see "+str(root/(name+".log")))
    print(name, "complete", round(time.monotonic()-started,2), "s", flush=True)
    return name, json.loads(produced.read_text())


def outline_identity(path):
    """Compare actual GLIF outlines/advances; kerning is allowed to change."""
    records = {}
    for file in (path/"glyphs").glob("*.glif"):
        root = ET.parse(file).getroot()
        records[root.attrib["name"]] = (ET.tostring(root.find("outline")), root.find("advance").attrib)
    return records


def run(reference, output, capture_path):
    reference, root, capture_path = map(lambda p:Path(p).resolve(), (reference, output, capture_path))
    if root.exists():
        raise ValueError("experiment output must be new")
    revision = subprocess.check_output(["git","-C",str(reference),"rev-parse","HEAD"],text=True).strip()
    if revision != REVISION or subprocess.check_output(["git","-C",str(reference),"status","--porcelain"],text=True):
        raise ValueError("reference must be unchanged at the pinned revision")
    raw = capture_path.read_bytes()
    capture = json.loads(raw)
    if capture["size_px"] != 16 or capture["axes"].get("wght") != 400 or capture["axes"].get("opsz") != 16:
        raise ValueError("this bounded run requires the frozen Literata 400/16 opsz16 capture")
    root.mkdir(parents=True)
    (root/"start-status.txt").write_text(subprocess.check_output(["git","status","--short"],text=True))
    (root/"image.json").write_text(subprocess.check_output(["docker","image","inspect",IMAGE],text=True))
    base = fixture()
    zero = copy.deepcopy(base)
    zero["parameters"] = dict(PARAMETERS, min_distance_ems=0., max_distance_ems=0., intrusion_tolerance_ems=0.)
    component = copy.deepcopy(base)
    component["glyphs"].append(dict(name="g", codepoint=103, advance=500, commands=[], component="a"))
    component["pairs"] = [["a","g"]]
    source, cells = capture_request(capture,"source"), capture_request(capture,"cells")
    jobs = [(name, request) for name, request in [("fixture",base),("fixture-repeat",base),("fixture-zero",zero),
             ("fixture-components",component),("source",source),("cells",cells),
             ("source-double",scaled(source,2)),("cells-double",scaled(cells,2))]]
    # Independent processes own distinct UFO output trees and cached profiles.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(run_job, [(root,reference,name,request) for name,request in jobs]))
    if results["fixture"] != results["fixture-repeat"]:
        raise ValueError("original reference is not repeatable")
    if results["fixture-zero"]["pairs"][0]["selected_advance"] != 200:
        raise ValueError("zero-distance rectangle contact is not reproduced")
    for name, _ in jobs:
        if outline_identity(root/name/"input.ufo") != outline_identity(root/name/"output.ufo"):
            raise ValueError("source outlines or advances changed: "+name)
    solver = Solver(capture)
    oracle = BitmapOracle(solver.glyphs)
    cp_lookup = {g["name"]:g["codepoint"] for g in cells["glyphs"]}
    records = []
    lookup = {name:{r["left"]+r["right"]:r for r in result["pairs"]} for name,result in results.items()}
    for pair in sorted(lookup["cells"]):
        a,b = (cp_lookup[c] for c in pair)
        control = solver.pair(a,b,Controls(spacing_model="hu_fitted_full_density_conserved_touch",preserve_tabular_spacing=False))
        record = dict(pair=pair, held_out=pair in HELD_OUT, reference=pair in REFERENCES,
                      source_step_px=solver.glyphs[a]["source_advance_px"]+solver.source_pairs.get((a,b),0.),
                      control_step_px=control["resolved_step_px"])
        for name in ("source","cells","source-double","cells-double"):
            value = lookup[name][pair]["selected_advance"]
            ideal = value*capture["size_px"]/results[name]["units_per_em"] if value is not None else None
            exported = lookup[name][pair]["emitted_ufo_advance"]*capture["size_px"]/results[name]["units_per_em"]
            record[name] = dict(selected_advance_units=value, ideal_step_px=ideal, ufo_step_px=exported)
        if record["cells"]["ideal_step_px"] is not None:
            advance = solver.glyphs[a]["finalized_advance_px"]
            # Reuse signed adjustment rounding and the independent no-overlap
            # floor; upstream font-unit rounding stays explicitly upstream.
            from filtered_walls import clearance_min_step_no_overlap
            minimum = clearance_min_step_no_overlap(solver.glyphs[a]["bitmap"], solver.glyphs[b]["bitmap"])
            rounded = advance+pixel_round(record["cells"]["ideal_step_px"]-advance)
            emitted = max(rounded,minimum) if minimum is not None else rounded
            record.update(rounded_step_px=rounded, emitted_step_px=emitted, clearance_min_step_px=minimum,
                          contacts=oracle.contacts(a,b,emitted))
            if not record["contacts"]["overlap_free"] or not record["contacts"]["same_row_wall_order"]:
                raise ValueError("cell placement violates the unchanged feasibility guard")
        records.append(record)
    lower = [r for r in records if all(c.islower() for c in r["pair"])]
    summary = dict(status="reference_reproduced_optical_assessment_pending", revision=revision, image=IMAGE,
        capture_path=str(capture_path), capture_sha256=sha(raw), parameters=PARAMETERS,
        parameter_provenance="author manual final example; NOT calibrated for Literata; no held-out tuning",
        reference_pairs=list(REFERENCES), held_out_pairs=list(HELD_OUT), all_pairs=records,
        reference_repeat_identical=True, outlines_and_advances_preserved=True,
        missing_component_selection=results["fixture-components"]["pairs"][0]["selected_advance"] is None,
        lowercase_pairs=len(lower), mean_lowercase_emitted_drift_px=math.fsum(r["emitted_step_px"]-r["source_step_px"] for r in lower)/len(lower),
        scaling={name:dict(max_ideal_delta_px=max(abs(r[name]["ideal_step_px"]-r[name+"-double"]["ideal_step_px"]) for r in records),
                     changed_rounded_pairs=sum(pixel_round(r[name]["ideal_step_px"])!=pixel_round(r[name+"-double"]["ideal_step_px"]) for r in records))
                 for name in ("source","cells")},
        driver_sha256=sha((HERE/"reference/typefacet_capture.py").read_bytes()),
        probe_sha256=sha(Path(__file__).read_bytes()),
        source_identity="unchanged original source commands in design units; delivered cells scaled by UPM/size",
        scope="Python2 original model and UFO output, one frozen capture; no browser port or adopted calibration")
    (root/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps({key:value for key,value in summary.items() if key!="all_pairs"},indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--reference",default="out/diagnostics/contextual-spacing/yinyang-alternatives/typefacet")
    parser.add_argument("--capture",default="out/diagnostics/contextual-spacing/preset-preview/captures/Literata-reading/capture.json")
    args = parser.parse_args()
    run(args.reference,args.output,args.capture)
