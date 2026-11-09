"""Reference-family TypeFacet calibration; no held-out or text-driven fitting.

The manual tunes four parameter roles using four reference families. Automatic
family-balanced least squares is our hypothesis, not an upstream fitter:
https://charlesmchen.github.io/typefacet/topics/autokern/typefacet-autokern-manual.html
Runs original Python 2 methods, followed by independent full-UFO reproduction.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
import math
from pathlib import Path
import subprocess
import time

from density_probe import BitmapOracle
from filtered_walls import clearance_min_step_no_overlap
from solver import Controls, Solver, bitmap_commands, pixel_round
from typefacet_probe import HERE, IMAGE, PARAMETERS, REVISION, outline_identity, run_job, scaled, sha


FAMILIES = dict(endpoint=("TT", "tt", "fT", "rf"), body=("NN", "nn"),
                intrusion=("AA", "OO", "oo"), overhang=("VA", "Ta", "LT"))
REFERENCES = tuple(pair for family in FAMILIES.values() for pair in family)
HELD_OUT = ("rd", "ri", "ca", "os", "bd", "du", "ff", "cc", "zz", "al", "nx", "en", "op", "se",
            "ip", "pe", "ig", "oe", "kh", "rn", "xn", "co", "jo", "yd", "le", "pi", "te", "tp", "ct", "ab")
KEYS = ("min_distance_ems", "max_distance_ems", "intrusion_tolerance_ems", "max_x_extrema_overlap_ems")
GRID = ((0., .02, .04, .06, .08), (.04, .08, .12, .16, .20, .24, .28, .32),
        (0., .025, .05, .10, .15, .20), (0., .05, .10, .15, .20))
BOUNDS = tuple((min(axis), max(axis)) for axis in GRID)
REFINEMENT = ((.01, .02, .0125, .025), (.005, .01, .00625, .0125))
PRECISION = .005
NEAR_RMSE_PX = 1/64  # One quantum of the retained source metric capture, not an optical tolerance.


def key(parameters):
    return tuple(parameters[name] for name in KEYS)


def parameters(values):
    return dict(zip(KEYS, values), precision_ems=PRECISION)


def loss(advances, targets, omit=None):
    """Equal family weight, independent of the number of examples in a family."""
    terms = [math.fsum((advances[pair]-targets[pair])**2 for pair in pairs)/len(pairs)
             for family, pairs in FAMILIES.items() if family != omit]
    return math.fsum(terms)/len(terms)


def ranked(records, targets, omit=None):
    # Manual: intrusion should be no larger than needed. Remaining ties use a
    # fixed parameter ordering; neither observed pixels nor held-outs break ties.
    return sorted(records, key=lambda r: (loss(r["steps_px"], targets, omit),
                  r["parameters"]["intrusion_tolerance_ems"], key(r["parameters"])))


def neighbors(anchors, steps):
    return sorted({tuple(round(v, 8) for v in values) for anchor in anchors
                   for values in itertools.product(*(tuple(anchor[i]+d*steps[i] for d in (-1, 0, 1)) for i in range(4)))
                   if all(lo-1e-10 <= v <= hi+1e-10 for v, (lo, hi) in zip(values, BOUNDS))
                   and values[0] <= values[1]})


def make_request(capture, geometry):
    letters = sorted(set("abcdefghijklmnopqrstuvwxyz"+"".join(REFERENCES)))
    lookup = {g["codepoint"]: g for g in capture["glyphs"]}
    scale = capture["units_per_em"]/capture["size_px"]
    glyphs = []
    for char in letters:
        glyph = lookup[ord(char)]
        glyphs.append(dict(name=char, codepoint=ord(char), advance=glyph["source_advance_px"]*scale,
                           commands=glyph["source_commands"] if geometry == "source" else bitmap_commands(glyph["bitmap"], scale)))
    return dict(units_per_em=capture["units_per_em"], ascender=capture["metrics"]["ascent_26_6"]/64*scale,
                descender=capture["metrics"]["descent_26_6"]/64*scale, glyphs=glyphs,
                pairs=[list(pair) for pair in REFERENCES], parameters=PARAMETERS)


def batch(root, reference, name, request, candidates, share=True):
    request = dict(request, candidates=candidates, disable_cache_sharing=not share)
    (root/(name+".json")).write_text(json.dumps(request, allow_nan=False))
    envpath = ":".join(["/adapters"]+["/reference/"+p for p in ["python/src-main", "dependencies/RoboFab/Lib",
        "dependencies/FontTools/Lib", "dependencies/pystache", "dependencies/PyYAML/lib", "dependencies/svgwrite"]])
    command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp",
        "-v", str(reference)+":/reference:ro", "-v", str(HERE/"reference")+":/adapters:ro",
        "-v", str(root)+":/work:rw", "-e", "PYTHONPATH="+envpath, IMAGE, "python", "-B",
        "/adapters/typefacet_batch.py", "/work/"+name+".json", "/work/"+name]
    started = time.monotonic()
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=900)
    (root/(name+".log")).write_text(result.stdout)
    path = root/name/"batch.json"
    if result.returncode or not path.is_file() or "BATCH_COMPLETE" not in result.stdout:
        raise RuntimeError("batch failed: "+str(root/(name+".log")))
    records = json.loads(path.read_text())["candidates"]
    factor = 16/request["units_per_em"]
    for record in records:
        record["steps_px"] = {pair: value*factor for pair, value in record["advances"].items()}
    print(name, len(records), "complete", round(time.monotonic()-started, 2), "s", flush=True)
    return records


def candidate_list(values):
    return [dict(id=str(i), parameters=parameters(v)) for i, v in enumerate(values)]


def near_extremes(result):
    """Choose sensitivity probes by parameters alone, never output pixels."""
    return [("near-"+name+"-"+str(sign), min(result["near"],
             key=lambda r: (sign*r["parameters"][name], key(r["parameters"]))))
            for name in KEYS for sign in (-1, 1)]


def fit(root, reference, geometry, request, targets):
    coarse = [values for values in itertools.product(*GRID) if values[0] <= values[1]]
    seen = set(coarse)
    records = batch(root, reference, geometry+"-coarse", request, candidate_list(coarse))
    for i, steps in enumerate(REFINEMENT):
        anchors = [key(ranked(records, targets, omit)[0]["parameters"]) for omit in (None, *FAMILIES)]
        new = [v for v in neighbors(anchors, steps) if v not in seen]
        if new:
            records += batch(root, reference, geometry+"-refine-"+str(i), request, candidate_list(new))
            seen.update(new)
    ordered = ranked(records, targets)
    best = ordered[0]
    best_rmse = math.sqrt(loss(best["steps_px"], targets))
    near = [r for r in ordered if math.sqrt(loss(r["steps_px"], targets)) <= best_rmse+NEAR_RMSE_PX]
    omitted = {family: ranked(records, targets, family)[0] for family in FAMILIES}
    result = dict(best=best, rmse_px=best_rmse, near=near, omit_family=omitted,
                  evaluated=len(records), boundary_keys=[k for k, (lo, hi) in zip(KEYS, BOUNDS) if best["parameters"][k] in (lo, hi)],
                  targets_px=targets)
    (root/(geometry+"-fit.json")).write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    return result


def emitted(solver, oracle, pair, ideal):
    a, b = map(ord, pair)
    advance = solver.glyphs[a]["finalized_advance_px"]
    rounded = advance+pixel_round(ideal-advance)
    minimum = clearance_min_step_no_overlap(solver.glyphs[a]["bitmap"], solver.glyphs[b]["bitmap"])
    step = max(rounded, minimum) if minimum is not None else rounded
    contacts = oracle.contacts(a, b, step)
    if not contacts["overlap_free"] or not contacts["same_row_wall_order"]:
        raise ValueError("overlap or wall inversion: "+pair)
    return dict(ideal_px=ideal, step_px=step, minimum_px=minimum, contacts=contacts)


def evaluate(root, reference, capture, request, fits):
    solver, lookup = Solver(capture), {}
    oracle = BitmapOracle(solver.glyphs)
    all_pairs = sorted(set(a+b for a in "abcdefghijklmnopqrstuvwxyz" for b in "abcdefghijklmnopqrstuvwxyz")|set(REFERENCES))
    all_request = dict(request, pairs=[list(pair) for pair in all_pairs])
    candidates = {}
    for arm, result in fits.items():
        for role, record in [("best", result["best"]), *[("omit-"+k, r) for k, r in result["omit_family"].items()],
                             *near_extremes(result)]:
            values = key(record["parameters"])
            if values not in candidates:
                candidates[values] = dict(id=str(len(candidates)), parameters=record["parameters"])
            lookup[arm+":"+role] = candidates[values]["id"]
    results = batch(root, reference, "cell-predictions", all_request, list(candidates.values()))
    predictions = {r["id"]: r for r in results}
    # Matched full original process()/UFO path, independently of the batch cache.
    jobs = []
    for arm, fit_result in fits.items():
        req = dict(all_request, parameters=fit_result["best"]["parameters"])
        jobs.append(("full-"+arm, req))
    with ThreadPoolExecutor(max_workers=2) as pool:
        full = dict(pool.map(run_job, [(root, reference, name, req) for name, req in jobs]))
    for arm in fits:
        name = "full-"+arm
        assert outline_identity(root/name/"input.ufo") == outline_identity(root/name/"output.ufo")
        values = {r["left"]+r["right"]: r["selected_advance"] for r in full[name]["pairs"]}
        if values != predictions[lookup[arm+":best"]]["advances"]:
            raise ValueError("batch disagrees with full UFO process: "+arm)
    pairs, alternative_counts = [], {arm: [] for arm in fits}
    baseline = {pair: solver.pair(*map(ord, pair), Controls(spacing_model="hu_fitted_full_density_conserved_touch",
                     preserve_tabular_spacing=False))["resolved_step_px"] for pair in all_pairs}
    for record in results:
        record["emitted"] = {pair: emitted(solver, oracle, pair, ideal) for pair, ideal in record["steps_px"].items()}
    for arm in fits:
        best = predictions[lookup[arm+":best"]]
        for label, candidate_id in lookup.items():
            if not label.startswith(arm+":") or label.endswith(":best"):
                continue
            other = predictions[candidate_id]
            lower = [p for p in all_pairs if p.islower()]
            alternative_counts[arm].append(dict(role=label.split(":", 1)[1], candidate_id=candidate_id,
                changed_lowercase=sum(best["emitted"][p]["step_px"] != other["emitted"][p]["step_px"] for p in lower),
                max_continuous_delta_px=max(abs(best["steps_px"][p]-other["steps_px"][p]) for p in lower)))
    for pair in all_pairs:
        a, b = map(ord, pair)
        pairs.append(dict(pair=pair, held_out=pair in HELD_OUT, control_px=baseline[pair],
            source_px=solver.glyphs[a]["source_advance_px"]+solver.source_pairs.get((a,b), 0.),
            arms={arm: predictions[lookup[arm+":best"]]["emitted"][pair] for arm in fits}))
    return dict(pairs=pairs, alternatives=alternative_counts, predictions=results, lookup=lookup, full_ufo_parity=True)


def reuse_fit(previous, geometry, targets):
    """Re-score all retained candidates before reusing a completed search."""
    result = json.loads((previous/(geometry+"-fit.json")).read_text())
    records, identities = [], {}
    for suffix in ("-coarse", "-refine-0", "-refine-1"):
        path = previous/(geometry+suffix)/"batch.json"
        raw = path.read_bytes()
        identities[str(path)] = sha(raw)
        for record in json.loads(raw)["candidates"]:
            record["steps_px"] = {p: v*.016 for p, v in record["advances"].items()}
            records.append(record)
    if result["targets_px"] != targets or result["best"] != ranked(records, targets)[0]:
        raise ValueError("reused fit disagrees with current reference objective")
    for family, selected in result["omit_family"].items():
        if selected != ranked(records, targets, family)[0]:
            raise ValueError("reused omitted-family fit disagrees")
    best_rmse = math.sqrt(loss(result["best"]["steps_px"], targets))
    near = [r for r in ranked(records, targets) if math.sqrt(loss(r["steps_px"], targets)) <= best_rmse+NEAR_RMSE_PX]
    if result["near"] != near:
        raise ValueError("reused near-optimal set disagrees")
    identities[str(previous/(geometry+"-fit.json"))] = sha((previous/(geometry+"-fit.json")).read_bytes())
    return result, identities


def run(reference, output, capture_path, reuse=None):
    reference, root, capture_path = map(lambda p: Path(p).resolve(), (reference, output, capture_path))
    if root.exists():
        raise ValueError("output must be new")
    if subprocess.check_output(["git", "-C", str(reference), "rev-parse", "HEAD"], text=True).strip() != REVISION or subprocess.check_output(
            ["git", "-C", str(reference), "status", "--porcelain"], text=True):
        raise ValueError("reference must be clean and pinned")
    assert not set(REFERENCES)&set(HELD_OUT)
    raw = capture_path.read_bytes()
    capture = json.loads(raw)
    if sha(raw) != "ffcc3b3b4fcadfa6e5eb2814704e82d74eb7ce888209baeb45d0886aa93e8967":
        raise ValueError("calibration requires the frozen capture")
    root.mkdir(parents=True)
    (root/"start-status.txt").write_text(subprocess.check_output(["git", "status", "--short"], text=True))
    (root/"image.json").write_text(subprocess.check_output(["docker", "image", "inspect", IMAGE], text=True))
    protocol = dict(families=FAMILIES, held_out=HELD_OUT, grid=GRID, keys=KEYS, refinement=REFINEMENT,
                    near_rmse_px=NEAR_RMSE_PX, precision=PRECISION, parameters_fixed="zero tracking, no category overrides",
                    objective="equal-family mean squared continuous origin-step residual; no text/held-out/rounding terms",
                    targets=dict(cells="finalized advance + full maintained metric pair", source="source advance + full source pair"),
                    revision=REVISION, image=IMAGE, capture_sha256=sha(raw),
                    host_sha256=sha(Path(__file__).read_bytes()), batch_sha256=sha((HERE/"reference/typefacet_batch.py").read_bytes()),
                    ufo_driver_sha256=sha((HERE/"reference/typefacet_capture.py").read_bytes()))
    if reuse:
        reuse = Path(reuse).resolve()
        previous = json.loads((reuse/"protocol.json").read_text())
        if any(json.dumps(previous[k], sort_keys=True) != json.dumps(v, sort_keys=True)
               for k, v in protocol.items() if k != "host_sha256"):
            raise ValueError("reused search protocol differs")
        protocol["reused_search_protocol"] = dict(path=str(reuse/"protocol.json"), sha256=sha((reuse/"protocol.json").read_bytes()))
    protocol["prediction_selection"] = "best, omitted-family fits and per-parameter extrema of near-optimal set; not exhaustive near-set predictions"
    (root/"protocol.json").write_text(json.dumps(protocol, indent=2)+"\n")
    solver = Solver(capture)
    requests = {geometry: make_request(capture, geometry) for geometry in ("source", "cells")}
    targets = {geometry: {pair: (solver.glyphs[ord(pair[0])]["source_advance_px"]+solver.source_pairs.get(tuple(map(ord,pair)),0.)
                       if geometry == "source" else solver.glyphs[ord(pair[0])]["finalized_advance_px"]+solver.metric_on.get(tuple(map(ord,pair)),0.))
                       for pair in REFERENCES} for geometry in requests}
    if reuse:
        fits, identities = {}, {}
        for geometry in requests:
            fits[geometry], files = reuse_fit(reuse, geometry, targets[geometry])
            identities.update(files)
            (root/(geometry+"-fit.json")).write_text(json.dumps(fits[geometry], indent=2)+"\n")
        (root/"reused-search-files.json").write_text(json.dumps(identities, indent=2)+"\n")
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {geometry: pool.submit(fit, root, reference, geometry, req, targets[geometry]) for geometry, req in requests.items()}
            fits = {geometry: future.result() for geometry, future in futures.items()}
    # No held-out pair measurements have participated in any optimization above.
    evaluated = evaluate(root, reference, capture, requests["cells"], fits)
    sensitivity = {}
    for geometry, fit_result in fits.items():
        best = dict(id="best", parameters=fit_result["best"]["parameters"])
        double = batch(root, reference, geometry+"-double", scaled(requests[geometry], 2), [best])[0]
        fine = batch(root, reference, geometry+"-fine", requests[geometry],
                     [dict(best, parameters=dict(best["parameters"], precision_ems=PRECISION/2))])[0]
        cold = batch(root, reference, geometry+"-cold", requests[geometry], [best], share=False)[0]
        if cold["advances"] != fit_result["best"]["advances"]:
            raise ValueError("cache sharing changed best reference outputs")
        sensitivity[geometry] = dict(doubled_steps_px=double["steps_px"], finer_steps_px=fine["steps_px"], cold_cache_identical=True)
    summary = dict(status="calibrated_diagnostic_optical_assessment_pending", protocol=protocol, fits=fits,
                   sensitivity=sensitivity, evaluation=evaluated)
    (root/"summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    print(json.dumps({name: dict(parameters=r["best"]["parameters"], rmse_px=r["rmse_px"], evaluated=r["evaluated"],
                               near_optima=len(r["near"]), boundaries=r["boundary_keys"]) for name, r in fits.items()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--reference", default="out/diagnostics/contextual-spacing/yinyang-alternatives/typefacet")
    parser.add_argument("--capture", default="out/diagnostics/contextual-spacing/preset-preview/captures/Literata-reading/capture.json")
    parser.add_argument("--reuse-fits", help="Re-score compatible retained reference searches instead of repeating them")
    args = parser.parse_args()
    run(args.reference, args.output, args.capture, args.reuse_fits)
