"""Small precise '+' complete-edge diagnostic. Read-only; no production edits."""
from pathlib import Path
import functools, json, tempfile
import numpy as np
import freetype as ft
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "complete-edge-audit-v3"
import build_source_bitmap as gen
import cumulative_hinter as cum_mod
from build_geometric_candidate import geometry as geometric_data
from geometric_candidate import correct, finish
from shamir_reorientation import prototype
from shamir_parent_anchor import experiment as parent_experiment
from audit_terminal_coverage import coords
from compare_paper_prototypes import render, pixels

FROZEN = HERE / "out" / "source-bitmap-constraints-v2"


def js(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.integer, np.floating)):
        return o.item()
    if isinstance(o, set):
        return sorted(o, key=repr)
    if isinstance(o, dict):
        return {str(k): js(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [js(v) for v in o]
    return o


def snap(arr):
    return np.asarray(arr, float).tolist() if arr is not None else None


def stage_vals(stages, idx, axis):
    return {name: float(np.asarray(v)[idx, axis]) for name, v in stages.items()}


def main():
    if any(OUT.iterdir()) if OUT.exists() else False:
        raise ValueError("output must be empty")
    OUT.mkdir(parents=True, exist_ok=True)
    pipe = gen.Pipeline(str(OUT / "gen"))
    try:
        pipe.note_sources()
        faces = {}
        for size in (16, 20):
            key = f"source-sans-3-{size}"
            static = pipe.instantiate(key, "source-sans-3", size)
            exp, records = pipe.baseline(key, size, static)  # CHARS incl.; globalstats unchanged
            rec = records["+"]
            with TTFont(str(exp)) as font:
                em = font["head"].unitsPerEm
                p, e, t = font["glyf"][font.getBestCmap()[ord("+")]].getCoordinates(font["glyf"])
            p = np.asarray(p, float)
            scale = size / em
            source_px = (p * scale).tolist()
            true_base = snap(coords(ft.Face(str(exp)), "+", size))
            data = geometric_data(rec, p.tolist(), list(e), list(t), size, em)
            result = correct(data)
            _, _, base = finish(result, data, 0)
            geom_q = (np.round(np.asarray(base) * 64) / 64).tolist()
            oriented = prototype(rec)
            model_px = oriented["graph"]["baseline_execution"]["model_points_px"]
            par = parent_experiment(oriented, p, size, em, False)
            model_pts = par["graph"]["baseline_execution"]["model_points_px"]
            # scoped wrappers: numeric stages of actual prepare invocation
            calls = {}
            origs = {}
            def wrap(name, tag, snap0):
                orig = getattr(cum_mod, name)
                origs[name] = orig
                @functools.wraps(orig)
                def w(*a, **k):
                    r = orig(*a, **k)
                    ent = {"args_shapes": [js(getattr(x, "shape", None)) for x in a]}
                    if tag == "fit":
                        ent["upstream"] = js(k.get("upstream"))
                    try:
                        ent["r0"] = snap(r[0]) if snap0 and r is not None else None
                        ent["ret"] = js(r)
                    except Exception as exc:
                        ent["error"] = str(exc)
                    calls.setdefault(tag, []).append(ent)
                    return r
                setattr(cum_mod, name, w)
            wrap("recover_order", "recover_order", True)
            wrap("shared_fit", "shared_fit", True)
            wrap("fit", "fit", True)
            try:
                b2, current, audit = cum_mod.prepare(data, rec)
            finally:
                for n, o in origs.items():
                    setattr(cum_mod, n, o)
            audit_js = js(audit)
            joint_in = calls.get("fit", [{}])[0].get("upstream")
            # PREPARE current: actual native/raster
            with tempfile.TemporaryDirectory(prefix="edge-prepare-") as td:
                pre_font = str(Path(td) / "pre.ttf")
                pre_native = gen.Pipeline.install(exp, pre_font, [("+", size, (p.tolist(), list(e), list(t)), np.asarray(current).tolist())])
                ink = js(pixels(render(ft.Face(pre_font), "+", size, hinted=True)))
                original_fit = cum_mod.fit
                reflection_calls = []
                def reflection_fit(*args, **kwargs):
                    value, details = original_fit(*args, **kwargs)
                    reflection_calls.append(js(details))
                    return value, details
                cum_mod.fit = reflection_fit
                try:
                    final, reflection = cum_mod.reflect(data, rec, np.asarray(current), audit, pixels(render(ft.Face(pre_font), "+", size, hinted=True)))
                finally:
                    cum_mod.fit = original_fit
                after_font = str(Path(td) / "after.ttf")
                nat = gen.Pipeline.install(exp, after_font, [("+", size, (p.tolist(), list(e), list(t)), np.asarray(final).tolist())])
                actual_native = snap(nat["+"])
                final_render = render(ft.Face(after_font), "+", size, hinted=True)
                with TTFont(after_font) as font:
                    hmtx = list(font["hmtx"][font.getBestCmap()[ord("+")]])
            reflection_js = js(reflection)
            # parity vs frozen FINAL file (read-only; inspect schema first)
            fpath = FROZEN / f"source-sans-3-{size}-bitmap.json"
            fd = json.loads(fpath.read_text())
            assert set(fd) >= {"key", "size", "glyphs"}, f"frozen schema changed: {sorted(fd)}"
            fz = fd["glyphs"]["+"]
            parity = {"file": f"source-bitmap-constraints-v2/source-sans-3-{size}-bitmap.json",
                      "native_match": bool(np.allclose(actual_native, fz["native_points_px"], atol=1e-9)),
                      "pixels_match": pixels(final_render) == pixels(fz),
                      "hmtx_match": bool(list(hmtx) == list(fz["advance_hmtx"])),
                      "native_maxdiff": float(np.max(abs(np.asarray(actual_native) - np.asarray(fz["native_points_px"])))),
                      "reflected_maxdiff_vs_native": float(np.max(abs(np.asarray(final) - np.asarray(actual_native))))}
            # grouping: source-equal coords, values at each stage, first split
            stages = {"source": np.asarray(source_px), "true_baseline": np.asarray(true_base),
                      "graph_model": np.asarray(model_px), "parent_model": np.asarray(model_pts),
                      "geometric": np.asarray(geom_q), "prepare_current": np.asarray(current),
                      "reflected": np.asarray(final), "native": np.asarray(actual_native)}
            groups = []
            for axis in (0, 1):
                by_val = {}
                for i, v in enumerate(np.asarray(source_px)[:, axis].tolist()):
                    by_val.setdefault(round(float(v), 9), []).append(i)
                for sval, members in by_val.items():
                    if len(members) < 2:
                        continue
                    per = {n: [float(np.asarray(a)[i, axis]) for i in members] for n, a in stages.items()}
                    first = None
                    for n in ("true_baseline", "graph_model", "parent_model", "geometric", "prepare_current", "reflected", "native"):
                        v = per[n]
                        if max(v) - min(v) > 1 / 64 + 1e-9:
                            first = n
                            break
                    groups.append({"axis": axis, "source_value": sval, "members": members,
                                   "values": per, "spreads": {n: float(max(v) - min(v)) for n, v in per.items()},
                                   "first_split": first})
            joint = audit_js.get("joint") if isinstance(audit_js, dict) else None
            faces[str(size)] = {
                "em": em, "scale": scale, "source_px": source_px, "true_baseline": true_base,
                "geometric_q": geom_q, "graph_model_points_px": snap(model_px), "parent_model_points_px": snap(model_pts),
                "reflection_calls": reflection_calls,
                "prepare_calls": calls, "joint_upstream_kwarg": joint_in, "audit": audit_js,
                "prepare_ink": ink, "reflected_numeric": snap(final), "reflected_native": actual_native,
                "hmtx": hmtx, "parity": parity, "groups": groups,
                "graph_constraints": js(rec.get("graph", {}).get("constraints")),
                "attachment_resolution": js(rec.get("attachment_resolution")),
                "protected_ids": js((joint or {}).get("protected_ids")),
                "released_equations": js((joint or {}).get("released_equations")),
                "stage_maxspread": {n: float(max((g["spreads"][n] for g in groups), default=0.0)) for n in stages},
            }
        # assertions
        for size, f in faces.items():
            rn, rv = np.asarray(f["reflected_native"], float), np.asarray(f["reflected_numeric"], float)
            assert np.all(np.isfinite(rv)) and np.all(np.isfinite(rn))
            assert float(np.max(abs(rv - rn))) <= 1 / 64 + 1e-9, size
        pipe.verify_inputs_unchanged()
        pipe.verify_sources()
        report = {"faces": faces, "sources": dict(pipe.inputs)}
        (OUT / "report.json").write_text(json.dumps(js(report), indent=1))
        lines = ["# Complete-edge audit v3", ""]
        for size, f in faces.items():
            lines.append(f"## size {size}: reflected-vs-native {f['parity']['reflected_maxdiff_vs_native']:.4f}px; parity native={f['parity']['native_match']} pixels={f['parity']['pixels_match']} hmtx={f['parity']['hmtx_match']} (native_maxdiff {f['parity']['native_maxdiff']:.4f})")
            lines.append(f"named-stage maxspread: {json.dumps({k: round(v, 4) for k, v in f['stage_maxspread'].items()})}")
            lines.append("| axis | source | members | first_split | max spread stage |")
            for g in f["groups"]:
                st, mx = max(g["spreads"].items(), key=lambda kv: kv[1])
                lines.append(f"| {g['axis']} | {g['source_value']} | {g['members']} | {g['first_split']} | {st} {mx:.4f} |")
            jr = (f["audit"] or {}).get("joint") or {}
            details = f['reflection_calls'][-1] if f['reflection_calls'] else {}
            released = [c['id'] for c in details.get('released_equations', []) if c.get('feature', '').startswith('align-')]
            lines.append(f"reflection released align IDs: {released}")
            lines.append("")
        (OUT / "trace.md").write_text("\n".join(lines))
        print(json.dumps({s: {"parity": f["parity"], "firsts": [(g["axis"], g["source_value"], g["members"], g["first_split"]) for g in f["groups"]]} for s, f in faces.items()}, indent=1))
    finally:
        pipe.close()


if __name__ == "__main__":
    main()
