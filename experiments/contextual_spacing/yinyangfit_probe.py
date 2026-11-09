"""Probe a pinned YinYangFit scoring path without inventing a missing cost.

Execute the original method bodies in isolation, bypassing font/GPU imports.
This establishes their behavior, not full-engine or notebook reproduction.
"""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
from types import SimpleNamespace

import numpy as np


REVISION = "609d17e8a6446ec4413a1b02a0768b8214d73333"


def probe(reference):
    reference = Path(reference)
    revision = subprocess.check_output(["git", "-C", str(reference), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("unexpected YinYangFit revision")
    paths = ["engine/__init__.py", "engine/filter_bank.py", "engine/radial_filter.py", "engine/kernels.cl",
             "YinYangFit.ipynb", "LICENSE", "docs/source/algorithms.markdown"]
    identities = {}
    for path in paths:
        raw = (reference/path).read_bytes()
        committed = subprocess.check_output(["git", "-C", str(reference), "show", f"{REVISION}:{path}"])
        if raw != committed:
            raise ValueError("modified reference input: " + path)
        identities[path] = hashlib.sha256(raw).hexdigest()
    parsed = ast.parse((reference/"engine/__init__.py").read_text())
    engine = next(node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == "Engine")
    names = {"render_penalty_fields", "get_best_distances_and_full_penalty_fields", "prepare_params"}
    methods = [node for node in engine.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(methods) != len(names):
        raise ValueError("reference method inventory changed")
    isolated = ast.fix_missing_locations(ast.Module(
        body=[ast.ClassDef(name="Engine", bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[]))
    namespace = dict(np=np, io=io, tqdm=lambda values: values)
    exec(compile(isolated, str(reference/"engine/__init__.py"), "exec"), namespace)
    instance = namespace["Engine"]()
    instance.n_scales, instance.n_orientations = 2, 2
    instance.box_height, instance.box_width = 4, 5
    instance.f = SimpleNamespace(minimum_ink_distance=lambda _a, _b: 0)
    records = []
    for pair in ("HH", "nn", "rd", "os"):
        distances = np.array([0, 1, 2, 3, 4], dtype=np.int32)
        field = instance.render_penalty_fields(*pair, {}, distances)
        records.append(dict(pair=pair, distances=distances.tolist(), shape=list(field.shape),
                            all_zero=bool(np.all(field == 0)),
                            totals=np.sum(field, axis=(0, 1, 2, 3)).tolist()))
    # Exercise the unchanged high-level selection method as well. No font or
    # glyph data is read by the constant penalty implementation.
    binary = instance.get_best_distances_and_full_penalty_fields(dict(sampleText="rd"))
    best = int(np.frombuffer(binary[8:12], dtype=np.int32)[0])
    notebook = json.loads((reference/"YinYangFit.ipynb").read_text())
    cells = [dict(index=i, source="".join(cell["source"])) for i, cell in enumerate(notebook["cells"])
             if cell["cell_type"] == "code"]
    return dict(status="probe_completed", feasibility="incomplete_reference" if all(r["all_zero"] for r in records)
                else "requires_further_reproduction", revision=revision,
                repository="https://github.com/skosch/YinYangFit", source_sha256=identities,
                environment=dict(python=platform.python_version(), numpy=np.__version__),
                execution="unchanged AST-extracted method bodies; imports and Engine.__init__ bypassed",
                method_lines={node.name: node.lineno for node in methods}, penalty_probes=records,
                high_level_selected_distance=best, high_level_search_start=-1,
                notebook_code_cells=len(cells), notebook_last_code_cell=cells[-1],
                limits=["No full-engine or notebook reproduction", "No fitted parameters or accepted pair score",
                        "No binary-capture adaptation, spacing predictions or optical acceptance"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference")
    parser.add_argument("output")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise ValueError("probe output must be new")
    result = probe(args.reference)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(dict(feasibility=result["feasibility"], penalty_probes=result["penalty_probes"],
                          high_level_selected_distance=result["high_level_selected_distance"])))
