"""Native-font graph coverage audit (investigation, not a conformance claim).

Pipeline uses ONLY original source/config IO: instantiate each family/size,
call build_font(profile="baseline", ppem=size) directly with no
representative override or later fitting. The baseline TTF holds ORIGINAL
prepared glyf coordinates pre-interpreter; original points/contours come
from glyph.getCoordinates(font["glyf"]). For every graph, compile_native is
called unmodified; rejections persist as structured diagnostics. Accepted
graphs execute their actual native program in a fresh baseline-font copy
under strict FreeType flags; exact coordinate match/difference against the
baseline graph baseline_execution.native_points_px is diagnostic only.
Numerical support + execution is not visual or paper conformance.
"""

import argparse
import json
import platform
import shutil
import tempfile
from array import array
from collections import Counter
from pathlib import Path

import fontTools
import freetype as ft
import numpy as np

from build_source_bitmap import FACES, SIZES, Pipeline, _json_default
from check_shamir_baseline import digest
from compare_shamir_pipeline import CHARS
from shamir_model import build_font
from shamir_native_translation import UnsupportedNativeTranslation, compile_native

HERE = Path(__file__).resolve().parent
READINESS = "native-font coverage investigation; support rejection is expected diagnostic"
FT_FLAGS = (ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_NO_AUTOHINT
            | ft.FT_LOAD_TARGET_MONO | ft.FT_LOAD_PEDANTIC)
P_KINDS = ("PAbs", "PDist", "PRatio")

# Stable aggregation bucket for every near-perpendicular / small-native-dot
# rejection. The compiler emits one distinct reason string per numeric dot
# value; those must not become one aggregate key each. The original complete
# reason string is always preserved verbatim in each diagnostic entry.
NEAR_PERPENDICULAR = "near-perpendicular/small-dot rejection"


def _stable_reason(reason):
    text = str(reason)
    if ("native dot" in text
            or "normalized dot" in text
            or "not independent (determinant" in text
            or "degenerate freedom vector" in text):
        return NEAR_PERPENDICULAR
    return text


def _sanitize(value, secrets):
    ordered = sorted(secrets, key=len, reverse=True)
    if isinstance(value, str):
        for secret in ordered:
            if secret:
                value = value.replace(secret, "<path>")
        return value
    if isinstance(value, dict):
        return {k: _sanitize(v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v, secrets) for v in value]
    return value


def _secrets(pipeline, output):
    parts = {str(HERE), str(Path(output).resolve()), str(Path.home())}
    work = getattr(pipeline, "work", None)
    if work is not None:
        parts.add(str(work))
    try:
        parts.add(str(Path.cwd()))
    except OSError:
        pass
    return {p for p in parts if p}


def _validate(families, sizes):
    families, sizes = tuple(families), tuple(sizes)
    if not families or not sizes:
        raise ValueError("families and sizes must both be non-empty")
    if len(set(families)) != len(families):
        raise ValueError("duplicate families rejected")
    if len(set(sizes)) != len(sizes):
        raise ValueError("duplicate sizes rejected")
    unknown = [f for f in families if f not in FACES]
    if unknown:
        raise ValueError(f"unknown families rejected: {unknown}")
    for size in sizes:
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError(f"invalid size rejected: {size!r}")
    return families, sizes


def _classify_param(value):
    """Exact integer / fractional / out-of-signed16 / non-finite classes."""
    try:
        import math as _m

        f = float(value)
    except (TypeError, ValueError):
        return "non-numeric"
    if not _m.isfinite(f):
        return "non-finite"
    if f.is_integer():
        return "integer" if -32768 <= int(f) <= 32767 else "out-of-signed16"
    return "fractional"


def _origin(constraint):
    return {
        "feature": constraint.get("feature"),
        "default": bool(constraint.get("default", False)),
        "default_reason": constraint.get("default_reason"),
        "metric": bool(constraint.get("metric", False)),
        "metric_role": constraint.get("metric_role"),
    }


def _expected_projection(constraint, points):
    try:
        pts = np.asarray(points, dtype=float)
        n = np.asarray(constraint.get("normal"), dtype=float).reshape(2)
        p = int(constraint.get("point"))
        kind = constraint.get("kind")
        if kind in ("Abs", "PAbs"):
            return float(pts[p] @ n)
        if kind in ("Dist", "PDist"):
            return float((pts[p] - pts[int(constraint["sources"][0])]) @ n)
        if kind in ("Ratio", "PRatio"):
            a, b = (int(s) for s in constraint["sources"][:2])
            pa, pb, pp = float(pts[a] @ n), float(pts[b] @ n), float(pts[p] @ n)
            return (pp - pa) / (pb - pa) if pb != pa else None
    except (TypeError, ValueError, IndexError, KeyError):
        pass
    return None


def _inventory(graph, points):
    """Census of the SELECTED constraints as audited (no compile trigger)."""
    kinds, p_counts, origins = Counter(), Counter(), Counter()
    params = []
    by_id = {}
    for c in graph.get("constraints", []):
        by_id[c.get("id")] = c
        kind = c.get("kind")
        kinds[str(kind)] += 1
        if kind in P_KINDS:
            p_counts[str(kind)] += 1
        org = _origin(c)
        origins["feature:%s" % (org["feature"] is not None)] += 1
        origins["default:%s" % org["default"]] += 1
        origins["metric:%s" % org["metric"]] += 1
        params.append({
            "id": c.get("id"), "kind": kind,
            "value": c.get("value"),
            "value_class": _classify_param(c.get("value")),
            "sources": list(c.get("sources", [])),
            "feature": org["feature"],
            "default": org["default_reason"] or False,
            "metric": org["metric_role"] or False,
        })
    return {"kinds": dict(kinds), "p_kinds": dict(p_counts),
            "origins": dict(origins), "params": params, "_by_id": by_id}


def _enrich(diag, by_id, points):
    entry = dict(diag)
    cid = diag.get("constraint_id")
    c = by_id.get(cid)
    if isinstance(c, dict):
        entry["kind"] = c.get("kind")
        entry["normal"] = list(c.get("normal")) if c.get("normal") is not None else None
        entry["value"] = c.get("value")
        entry["value_class"] = _classify_param(c.get("value"))
        entry["sources"] = list(c.get("sources", []))
        entry["origin"] = _origin(c)
        entry["expected_projection"] = _expected_projection(c, points)
    return entry


def _build_native_font(baseline_path, out_path, char, assembly, cvt_vals):
    """Fresh baseline copy with target program/CVT replaced; subset to char."""
    from fontTools import subset
    from fontTools.ttLib import TTFont, newTable
    from fontTools.ttLib.tables.ttProgram import Program

    tmp = Path(tempfile.mkdtemp(prefix="native-case-"))
    try:
        work = tmp / "work.ttf"
        shutil.copy2(baseline_path, work)
        with TTFont(str(work)) as font:
            name = font.getBestCmap()[ord(char)]
            glyf, hmtx = font["glyf"], font["hmtx"]
            coords, end_pts, flags = glyf[name].getCoordinates(glyf)
            orig = {"coords": [list(map(int, p)) for p in coords],
                    "end_pts": list(end_pts),
                    "oncurve": [int(f & 1) for f in flags],
                    "advance": list(hmtx[name])}
            prog = Program()
            prog.fromAssembly(assembly)
            glyf[name].program = prog
            cvt = newTable("cvt ")
            cvt.values = array("h", [int(v) for v in cvt_vals])
            font["cvt "] = cvt
            font["maxp"].maxStackElements = max(
                int(font["maxp"].maxStackElements), 8)
            font["maxp"].maxSizeOfInstructions = max(
                len(font["glyf"][n].program.getBytecode())
                if hasattr(font["glyf"][n], "program") else 0
                for n in font.getGlyphOrder())
            if "fpgm" not in font:
                font["fpgm"] = newTable("fpgm")
                font["fpgm"].program = Program()
            if "prep" not in font:
                font["prep"] = newTable("prep")
                font["prep"].program = Program()
            keep = {ord(char)}
            opts = subset.Options()
            sub = subset.Subsetter(options=opts)
            sub.populate(unicodes=keep)
            sub.subset(font)
            font.save(out_path)
        with TTFont(str(out_path)) as check:
            name2 = check.getBestCmap()[ord(char)]
            c2, e2, f2 = check["glyf"][name2].getCoordinates(check["glyf"])
            assert [list(map(int, p)) for p in c2] == orig["coords"]
            assert [int(f & 1) for f in f2] == orig["oncurve"]
            assert list(e2) == orig["end_pts"]
            assert list(check["hmtx"][name2]) == orig["advance"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return orig


def _run_ft_strict(path, char, size):
    face = ft.Face(str(path))
    face.set_pixel_sizes(0, size)
    face.load_char(char, FT_FLAGS)
    raw = np.asarray(face.glyph.outline.points, dtype=np.int64)
    return raw.tolist(), (raw / 64.0).tolist()


def _as_nx2_strict(values, case_id, label):
    """Normalize genuinely-empty [] to shape (0, 2); reject malformed arrays."""
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        raise ValueError(f"{case_id}: {label} points are not numeric Nx2")
    if arr.ndim == 1 and arr.shape == (0,):
        arr = arr.reshape(0, 2)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"{case_id}: {label} points are not Nx2")
    return arr


def _check_shapes(raw, expected_px, case_id):
    """Require equal native-vs-expected coordinate shapes before comparison."""
    exp = _as_nx2_strict(expected_px, case_id, "expected")
    got = _as_nx2_strict(raw, case_id, "native")
    if got.shape[0] != exp.shape[0]:
        raise ValueError(
            f"{case_id}: native/expected point-count mismatch "
            f"({got.shape[0]} vs {exp.shape[0]})")
    return got, exp


FT_RENDER_FLAGS = FT_FLAGS | ft.FT_LOAD_MONOCHROME


def _ft_advance(path, char, size):
    face = ft.Face(str(path))
    face.set_pixel_sizes(0, size)
    face.load_char(char, FT_FLAGS)
    return (int(face.glyph.advance.x), int(face.glyph.advance.y),
            int(face.glyph.metrics.horiAdvance),
            int(face.glyph.metrics.horiBearingX))


def _ft_bitmap_is_empty(path, char, size):
    face = ft.Face(str(path))
    face.set_pixel_sizes(0, size)
    face.load_char(char, FT_RENDER_FLAGS | ft.FT_LOAD_RENDER)
    buf = bytes(face.glyph.bitmap.buffer)
    return ({"rows": int(face.glyph.bitmap.rows),
             "width": int(face.glyph.bitmap.width),
             "pitch": int(face.glyph.bitmap.pitch),
             "all_zero": all(b == 0 for b in buf),
             "n_bytes": len(buf)})


def _verify_empty_noop(native_path, baseline_path, char, size, orig, case_id):
    """Verify a blank glyph: empty bitmap, unchanged advance/lsb.

    Compares the native build against the baseline under strict FreeType;
    the native/baseline advance comparison is exact (same rasterizer and
    flags, so grid rounding applies identically to both). hmtx
    outline/contour/advance equality is already asserted by
    _build_native_font; the recorded advance/lsb come from there.
    """
    evidence = {"bitmap": _ft_bitmap_is_empty(native_path, char, size),
                "bitmap_baseline": _ft_bitmap_is_empty(
                    baseline_path, char, size),
                "advance_native": _ft_advance(native_path, char, size),
                "advance_baseline": _ft_advance(baseline_path, char, size),
                "hmtx": list(orig["advance"])}
    empty_bitmap = (evidence["bitmap"]["all_zero"]
                    and evidence["bitmap_baseline"]["all_zero"])
    if not empty_bitmap:
        raise ValueError(f"{case_id}: empty outline bitmap is not blank")
    # Grid rounding may apply to the FT advance, so the check is
    # native-vs-baseline (identical flags), not font-unit scalar math.
    if evidence["advance_native"] != evidence["advance_baseline"]:
        raise ValueError(
            f"{case_id}: empty outline FT advance changed "
            f"({evidence['advance_native']} vs "
            f"{evidence['advance_baseline']})")
    return evidence


def _empty_tally():
    return {"total": 0, "supported": 0, "unsupported": 0,
            "unexpected": 0, "executed": 0,
            "empty_outlines": 0, "empty_verified": 0}


def _record(tally, result):
    tally["total"] += 1
    if result == "supported":
        tally["supported"] += 1
        tally["executed"] += 1
    elif result == "unsupported":
        tally["unsupported"] += 1
    else:
        tally["unexpected"] += 1


def run(output, families=FACES, sizes=SIZES):
    families, sizes = _validate(families, sizes)
    output = Path(output)
    expected = len(families) * len(sizes) * len(CHARS)
    pipeline = Pipeline(output)
    pipeline.provenance = {"stages": ["source-instantiation", "baseline-model",
                                      "native-coverage"]}
    secrets = _secrets(pipeline, output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        pipeline.close()
        raise ValueError("use an empty output directory to preserve frozen evidence")
    cases_dir = output / "cases"
    cases_dir.mkdir()
    builds, failures = [], []
    reason_relations, reason_cases = Counter(), Counter()
    graph_reason_cases = Counter()
    # Value classes over ALL selected-constraint values (diagnostic context).
    relation_value_classes = Counter()
    # Actual parameter classes: P-kind (PAbs/PDist/PRatio) values only, so
    # fractional Ratio/Dist are never mixed with CVT parameter values.
    parameter_classes_by_kind = {k: Counter() for k in P_KINDS}
    parameter_classes_total = Counter()
    kind_totals = Counter()
    counts = {"expected": expected, **_empty_tally()}
    family_counts = {}
    native_match = {"exact": 0, "different": 0, "max_delta_px": 0.0}
    try:
        pipeline.note_sources()
        for family in families:
            for size in sizes:
                key = f"{family}-{size}"
                print(f"[{key}] build", flush=True)
                target = output / f"{key}-baseline.ttf"
                build_path = output / f"{key}-build.json"
                fam = family_counts.setdefault(family, _empty_tally())
                build_tally = _empty_tally()
                static_path, build = None, None
                try:
                    static_path = pipeline.instantiate(key, family, size)
                    build = build_font(static_path, target, CHARS,
                                       profile="baseline", ppem=size)
                    build_path.write_text(json.dumps(
                        _sanitize(build, secrets), indent=2,
                        default=_json_default) + "\n")
                except Exception as exc:  # noqa: BLE001 - persist all chars
                    failures.append(_sanitize(
                        {"stage": "build", "font": family, "size": size,
                         "error": f"{type(exc).__name__}: {exc}"}, secrets))
                    summaries = []
                    for char in CHARS:
                        counts["total"] += 1
                        counts["unexpected"] += 1
                        fam["total"] += 1
                        fam["unexpected"] += 1
                        build_tally["total"] += 1
                        build_tally["unexpected"] += 1
                        summaries.append(
                            {"char": char, "code": f"U+{ord(char):04X}",
                             "result": "unexpected", "supported": False,
                             "compiler_supported": None, "stage": "build",
                             "relations": None, "diagnostics": [],
                             "graph_diagnostics": [], "native": None,
                             "error": "build failed; case not attempted"})
                    builds.append({"font": family, "size": size, "key": key,
                                   "build_error": True, **build_tally,
                                   "cases": summaries})
                    print(f"[{key}] build FAILED", flush=True)
                    continue
                from fontTools.ttLib import TTFont

                n_ok = n_no = n_bad = 0
                summaries = []
                for char in CHARS:
                    code = f"U+{ord(char):04X}"
                    case_id = f"{key}-{code}"
                    case = {"char": char, "code": code,
                            "result": "unexpected", "supported": False,
                            "compiler_supported": None, "stage": None,
                            "relations": None, "diagnostics": [],
                            "graph_diagnostics": [], "native": None,
                            "error": None}
                    try:
                        with TTFont(str(target)) as font:
                            gname = font.getBestCmap()[ord(char)]
                            coords, _, _ = font["glyf"][gname].getCoordinates(
                                font["glyf"])
                            points = np.asarray(coords, dtype=float)
                        graph = build["records"][char]["graph"]
                        inv = _inventory(graph, points)
                        by_id = inv.pop("_by_id")
                        for prm in inv["params"]:
                            relation_value_classes[prm["value_class"]] += 1
                            if prm["kind"] in P_KINDS:
                                parameter_classes_by_kind[prm["kind"]][
                                    prm["value_class"]] += 1
                                parameter_classes_total[prm["value_class"]] += 1
                        kind_totals.update(inv["kinds"])
                        case["relations"] = inv
                        try:
                            assembly, meta = compile_native(graph, points)
                        except UnsupportedNativeTranslation as rej:
                            # Spaces stay unsupported: audited as rejected,
                            # never reinterpreted or given a fallback.
                            enriched = [_enrich(d, by_id, points)
                                        for d in rej.diagnostics]
                            # Graph-level diagnostics carry no constraint_id
                            # and are not rejected relations.
                            case["diagnostics"] = [
                                d for d in enriched
                                if d.get("constraint_id") is not None]
                            case["graph_diagnostics"] = [
                                d for d in enriched
                                if d.get("constraint_id") is None]
                            for d in case["diagnostics"]:
                                reason_relations[_stable_reason(
                                    d.get("reason"))] += 1
                            for r in {_stable_reason(d.get("reason"))
                                      for d in case["diagnostics"]}:
                                reason_cases[r] += 1
                            for r in {_stable_reason(d.get("reason"))
                                      for d in case["graph_diagnostics"]}:
                                graph_reason_cases[r] += 1
                            case["result"] = "unsupported"
                            case["compiler_supported"] = False
                            case["stage"] = "compile"
                            n_no += 1
                        else:
                            case["compiler_supported"] = True
                            native_path = cases_dir / f"{case_id}.ttf"
                            meta_path = cases_dir / f"{case_id}.json"
                            orig = _build_native_font(
                                target, native_path, char, assembly,
                                list(meta.get("cvt", [])))
                            raw, px = _run_ft_strict(native_path, char, size)
                            expected_px = graph.get(
                                "baseline_execution", {}).get(
                                "native_points_px")
                            if expected_px is None:
                                raise ValueError(
                                    "baseline_execution.native_points_px missing")
                            got, exp = _check_shapes(raw, expected_px, case_id)
                            exp_raw = np.rint(exp * 64).astype(np.int64)
                            diff = int((np.rint(got).astype(np.int64)
                                        != exp_raw).any(axis=1).sum())
                            # Delta is purely diagnostic, never acceptance.
                            delta = float(np.abs(
                                np.asarray(px, float) - np.asarray(
                                    expected_px, float)).max()) if px else 0.0
                            empty_evidence = None
                            is_empty = bool(got.shape[0] == 0)
                            if is_empty:
                                # Blank glyph: verify empty bitmap and
                                # unchanged advance/lsb; record verified
                                # no-op metadata distinctly from ordinary
                                # native instruction execution.
                                if not bool(meta.get("empty_outline")):
                                    raise ValueError(
                                        f"{case_id}: zero-point case without "
                                        "empty-outline no-op metadata")
                                if list(assembly) != [] or list(
                                        meta.get("cvt", [])) != [] or list(
                                        meta.get("operations", [])) != []:
                                    raise ValueError(
                                        f"{case_id}: empty outline must have "
                                        "empty assembly/cvt/operations")
                                empty_evidence = _verify_empty_noop(
                                    native_path, target, char, size,
                                    orig, case_id)
                            meta_path.write_text(json.dumps({
                                "assembly": assembly, "metadata": meta,
                                "original": orig,
                                "ft_raw_26_6": raw, "ft_px": px,
                                "expected_px": expected_px,
                                "exact_match": diff == 0,
                                "n_different": diff,
                                "max_delta_px": delta,
                                "empty_outline": is_empty,
                                "empty_evidence": empty_evidence}, indent=2,
                                default=_json_default) + "\n")
                            case["native"] = {
                                "font": f"cases/{native_path.name}",
                                "metadata": f"cases/{meta_path.name}",
                                "sha256": digest(native_path),
                                "meta_sha256": digest(meta_path),
                                "exact_match": diff == 0,
                                "n_different": diff,
                                "max_delta_px": delta,
                                "n_points": len(raw),
                                "empty_outline": is_empty,
                                "empty_verified": is_empty,
                                "empty_noop_status": meta.get("status")
                                if is_empty else None,
                                "empty_evidence": empty_evidence}
                            case["result"] = "supported"
                            case["supported"] = True
                            case["stage"] = "executed"
                            if diff == 0:
                                native_match["exact"] += 1
                            else:
                                native_match["different"] += 1
                            native_match["max_delta_px"] = max(
                                native_match["max_delta_px"], delta)
                            n_ok += 1
                    except Exception as exc:  # noqa: BLE001 - unexpected
                        # Preserve audited evidence: inventory, diagnostics,
                        # and compiler verdict gathered before the failure.
                        if case.get("error") is None:
                            case["error"] = f"{type(exc).__name__}: {exc}"
                        case["result"] = "unexpected"
                        if case.get("stage") in (None, "executed"):
                            case["stage"] = "execution" if case.get(
                                "compiler_supported") else "case"
                        n_bad += 1
                        failures.append(_sanitize(
                            {"stage": case["stage"], "font": family,
                             "size": size, "char": char,
                             "compiler_supported": case.get(
                                 "compiler_supported"),
                             "error": case["error"]}, secrets))
                    _record(counts, case["result"])
                    _record(fam, case["result"])
                    _record(build_tally, case["result"])
                    if bool((case.get("native") or {}).get("empty_verified")):
                        counts["empty_outlines"] += 1
                        counts["empty_verified"] += 1
                        fam["empty_outlines"] += 1
                        fam["empty_verified"] += 1
                        build_tally["empty_outlines"] += 1
                        build_tally["empty_verified"] += 1
                    summaries.append({
                        "char": char, "code": code,
                        "result": case["result"],
                        "supported": case["supported"],
                        "compiler_supported": case["compiler_supported"],
                        "stage": case["stage"],
                        "relations": case.get("relations"),
                        "diagnostics": case.get("diagnostics", []),
                        "graph_diagnostics": case.get(
                            "graph_diagnostics", []),
                        "native": case.get("native"),
                        "error": case.get("error")})
                builds.append({"font": family, "size": size, "key": key,
                               "output": target.name,
                               "build_json": build_path.name,
                               "input_sha256": digest(static_path),
                               "output_sha256": digest(target),
                               "build_json_sha256": digest(build_path),
                               **build_tally,
                               "cases": summaries})
                print(f"[{key}] supported={n_ok} unsupported={n_no} "
                      f"unexpected={n_bad}", flush=True)
        try:
            pipeline.verify_inputs_unchanged()
            pipeline.verify_sources()
        except Exception as exc:  # noqa: BLE001
            failures.append(_sanitize(
                {"stage": "verify", "error": f"{type(exc).__name__}: {exc}"},
                secrets))
    except Exception as exc:  # noqa: BLE001 - setup failure persists
        failures.append(_sanitize(
            {"stage": "setup", "error": f"{type(exc).__name__}: {exc}"},
            secrets))
    finally:
        try:
            pipeline.close()
        except Exception as exc:  # noqa: BLE001
            failures.append({"stage": "cleanup",
                             "error": f"{type(exc).__name__}: {exc}"})
        inputs = dict(pipeline.inputs)
    audit_complete = (counts["total"] == expected and counts["unexpected"] == 0
                      and not any(f.get("stage") in ("setup", "verify", "build",
                                                     "cleanup") for f in failures))
    report = _sanitize({
        "config": {"profile": "baseline", "families": list(families),
                   "sizes": list(sizes), "chars": len(CHARS)},
        "inputs": inputs, "provenance": dict(pipeline.provenance),
        "counts": counts, "family_counts": family_counts,
        "builds": builds,
        "reason_relations": dict(reason_relations),
        "reason_cases": dict(reason_cases),
        "graph_reason_cases": dict(graph_reason_cases),
        "relation_value_classes": dict(relation_value_classes),
        "parameter_classes_by_kind": {k: dict(v) for k, v in
                                      parameter_classes_by_kind.items()},
        "parameter_classes_total": dict(parameter_classes_total),
        "relation_kinds": dict(kind_totals),
        "native_match": native_match,
        "failures": failures,
        "versions": {"python": platform.python_version(),
                     "freetype": list(ft.version()),
                     "fonttools": fontTools.__version__,
                     "numpy": np.__version__},
        "audit_complete": bool(audit_complete),
        "readiness": READINESS}, secrets)
    (output / "native-font-coverage-report.json").write_text(
        json.dumps(report, indent=2, default=_json_default) + "\n")
    print(json.dumps({"audit_complete": report["audit_complete"],
                      "counts": counts,
                      "native_match": native_match,
                      "top_reasons": dict(reason_cases.most_common(8)),
                      "parameter_classes_total": dict(
                          parameter_classes_total)}, indent=2))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--families", nargs="+", default=list(FACES))
    parser.add_argument("--sizes", nargs="+", type=int, default=list(SIZES))
    args = parser.parse_args(argv)
    result = run(args.output, families=args.families, sizes=args.sizes)
    if not result["audit_complete"]:
        raise SystemExit("native-font coverage audit incomplete; see report")


if __name__ == "__main__":
    main()
