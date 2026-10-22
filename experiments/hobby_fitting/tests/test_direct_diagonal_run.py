"""Wiring tests for the direct-diagonal harness (synthetic fake core only).

The stub core below exercises argument plumbing, policy forwarding and
fatal-parity handling. It is not a model and proves nothing about fitting.
"""

import json
import os
import sys
import tempfile
import types
import unittest

from experiments.hobby_fitting import direct_diagonal_run as run

FAKE_ADAPTER = """#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if args == ["candidate"]:
    sys.exit(2)
with open(args[args.index("--record") + 1]) as handle:
    record = json.load(handle)
if args[0] == "parity":
    print(json.dumps({"match": True, "policy": record["raster_policy"]}))
elif args[0] == "candidate":
    print(json.dumps({"left": record["left"], "top": record["top"],
                      "width": record["width"], "height": record["height"],
                      "pixels": record["pixels"], "coverage": record["coverage"]}))
else:
    sys.exit(2)
"""

FAIL_ADAPTER = """#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if args == ["candidate"]:
    sys.exit(2)
print(json.dumps({"match": False}))
"""


def shifted(commands, dx):
    out = []
    for cmd in commands:
        cmd = dict(cmd)
        if "x" in cmd:
            cmd["x"] = cmd["x"] + dx
        out.append(cmd)
    return out


BASE_COMMANDS = [
    {"op": "move_to", "x": 0.0, "y": 0.0},
    {"op": "line_to", "x": 2.0, "y": 0.0},
    {"op": "line_to", "x": 2.0, "y": 2.0},
    {"op": "close"},
]


def record(codepoint, fitted, engine="auto", native_axes=None, policy="free_type_mono"):
    rec = {
        "codepoint": codepoint,
        "glyph_id": codepoint,
        "source_commands": shifted(BASE_COMMANDS, -1.0),
        "fitted_commands": fitted,
        "pixels": [1, 0, 0, 1],
        "coverage": [255, 0, 0, 255],
        "left": 0,
        "top": 0,
        "width": 2,
        "height": 2,
        "advance_26_6": 128,
        "hinted_advance_width": 2.0,
        "hinted_lsb": 0.0,
        "hinted_has_overlaps": False,
        "side_bearing_deltas_26_6": [0, 0],
        "raster_policy": policy,
        "mono_raster": {"tag": engine},
        "selected_engine": engine,
    }
    if native_axes is not None:
        rec["selective_fitting"] = {"native_axes": native_axes}
    return rec


def captures_doc():
    # Auto and selective baselines deliberately differ in commands,
    # ownership and policy so a crossed baseline fails the assertions.
    auto = [record(107, BASE_COMMANDS, engine="auto",
                   policy="free_type_mono_terminals"),
            record(108, BASE_COMMANDS, engine="auto",
                   policy="free_type_mono_terminals")]
    sel = [record(107, shifted(BASE_COMMANDS, 5.0), engine="auto_x_native_y",
                  native_axes=[False, True], policy="free_type_mono"),
           record(108, shifted(BASE_COMMANDS, 5.0), engine="auto_x_native_y",
                  native_axes=[False, True], policy="free_type_mono")]
    src = [dict(record(107, BASE_COMMANDS), pixels=[0, 1, 1, 0]),
           dict(record(108, BASE_COMMANDS), pixels=[0, 1, 1, 0])]
    return [{
        "family": "Test", "size": 16, "axes": {"wght": 400.0},
        "source": {"source_sha256": "ab" * 32, "records": src},
        "modes": {"auto_default": {"records": auto},
                  "selective_default": {"records": sel}},
    }]


def fake_core_module(calls, checker_aware=False):
    module = types.ModuleType("experiments.hobby_fitting.direct_diagonal")

    def build_reference(records, size_px):
        calls.append(("reference", [r["fitted_commands"] for r in records], size_px))
        return {"n": len(records)}

    if checker_aware:
        def fit_glyph(source, fitted, size_px, reference, native_axes=(False, False),
                      grid=False, topology_checker=None):
            calls.append(("fit", grid, tuple(native_axes), fitted,
                          topology_checker is not None))
            return {
                "candidate_commands": fitted, "applied": True,
                "reason": "fake-applied",
                "widths": {"w": 1.0}, "fixed": [], "movement": 0.0, "bound": 0.5,
                "validity": {"exact_topology": None},
            }
    else:
        def fit_glyph(source, fitted, size_px, reference, native_axes=(False, False),
                      grid=False):
            calls.append(("fit", grid, tuple(native_axes), fitted))
            return {
                "candidate_commands": fitted, "applied": grid,
                "reason": "fake-grid" if grid else "fake-width",
                "widths": {"w": 1.0}, "fixed": [], "movement": 0.0, "bound": 0.5,
                "validity": True,
            }

    module.build_reference = build_reference
    module.fit_glyph = fit_glyph
    return module


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = os.path.join(self.tmp.name, "adapter.py")
        with open(self.adapter, "w") as handle:
            handle.write(FAKE_ADAPTER)
        os.chmod(self.adapter, 0o755)
        self.captures = os.path.join(self.tmp.name, "captures.json")
        with open(self.captures, "w") as handle:
            json.dump(captures_doc(), handle)
        self.out = os.path.join(self.tmp.name, "out")
        self.fake_name = "experiments.hobby_fitting.direct_diagonal"
        self.saved = sys.modules.pop(self.fake_name, None)
        self.addCleanup(self.restore_core)

    def restore_core(self):
        sys.modules.pop(self.fake_name, None)
        if self.saved is not None:
            sys.modules[self.fake_name] = self.saved

    def base_args(self, extra=()):
        return ["--captures", self.captures, "--out", self.out,
                "--adapter", self.adapter] + list(extra)

    def load_case(self, summary, hint, codepoint=107):
        entry = [c for c in summary["cases"]
                 if c["hint_mode"] == hint and c["codepoint"] == codepoint][0]
        with open(os.path.join(self.out, entry["file"])) as handle:
            return json.load(handle)

    def test_default_off_imports_no_solver(self):
        before = set(sys.modules)
        summary = run.main(self.base_args())
        self.assertFalse(summary["enabled"])
        new = set(sys.modules) - before
        self.assertNotIn("numpy", new)
        self.assertNotIn(self.fake_name, new)

    def test_both_hint_modes_separate(self):
        summary = run.main(self.base_args())
        self.assertEqual(len(summary["cases"]), 4)
        hints = sorted(c["hint_mode"] for c in summary["cases"])
        self.assertEqual(hints, ["auto_default"] * 2 + ["selective_default"] * 2)
        self.assertEqual(summary["counts"]["upstream"]["rendered"], 4)

    def test_no_baseline_crossing(self):
        calls = []
        sys.modules[self.fake_name] = fake_core_module(calls)
        summary = run.main(self.base_args(["--enable-direct-diagonals"]))
        # References are per hint mode, built from that mode's own records.
        refs = [c for c in calls if c[0] == "reference"]
        self.assertEqual(len(refs), 2)
        by_fitted = {tuple(r[0][0]["x"] for r in [ref[1]]) for ref in refs}
        self.assertEqual(by_fitted, {(0.0,), (5.0,)})
        # Fits receive the mode's own fitted commands and ownership.
        fits = [c for c in calls if c[0] == "fit"]
        auto_fits = [c for c in fits if c[3][0]["x"] == 0.0]
        sel_fits = [c for c in fits if c[3][0]["x"] == 5.0]
        self.assertEqual(len(auto_fits), len(sel_fits))
        self.assertTrue(all(c[2] == (False, False) for c in auto_fits))
        self.assertTrue(all(c[2] == (False, True) for c in sel_fits))
        # Selective candidate pixels follow the selective policy/commands.
        case = self.load_case(summary, "selective_default")
        self.assertEqual(
            case["arms"]["upstream"]["pixels"], [1, 0, 0, 1])
        self.assertEqual(case["native_axes"], [False, True])

    def test_mode_selection(self):
        calls = []
        sys.modules[self.fake_name] = fake_core_module(calls)
        summary = run.main(self.base_args(
            ["--enable-direct-diagonals", "--mode", "width_only"]))
        self.assertEqual(summary["mode"], "width_only")
        grids = [c for c in calls if c[0] == "fit" and c[1]]
        self.assertEqual(grids, [])

    def test_unknown_engine_reserves_both(self):
        self.assertEqual(run.ownership({"selected_engine": "other"}),
                         ((True, True), "unknown-reserve-both"))
        self.assertEqual(run.ownership({"selected_engine": "auto"}),
                         ((False, False), "selected-engine"))
        self.assertEqual(
            run.ownership({"selective_fitting": {"native_axes": [True, False]}}),
            ((True, False), "selective-native-axes"))

    def test_html_pixel_contract(self):
        summary = run.main(self.base_args())
        with open(os.path.join(self.out, "index.html")) as handle:
            index = handle.read()
        self.assertIn("arm.pixels", index)
        self.assertIn("auto_default", index)
        for entry in summary["cases"]:
            with open(os.path.join(self.out, entry["file"])) as handle:
                case = json.load(handle)
            for name in ("upstream", "width_only", "grid"):
                arm = case["arms"][name]
                if arm is None:
                    continue
                frame = arm.get("frame", {})
                if "pixels" in arm:
                    self.assertEqual(
                        len(arm["pixels"]), frame["width"] * frame["height"])

    def test_exact_joins_requires_enabled(self):
        with self.assertRaises(SystemExit):
            run.main(self.base_args(["--exact-joins"]))

    def test_exact_joins_missing_binary_fails(self):
        saved = os.environ.pop("HOBBY_EXACT_TOPOLOGY_BINARY", None)

        def restore():
            if saved is None:
                os.environ.pop("HOBBY_EXACT_TOPOLOGY_BINARY", None)
            else:
                os.environ["HOBBY_EXACT_TOPOLOGY_BINARY"] = saved

        self.addCleanup(restore)
        calls = []
        sys.modules[self.fake_name] = fake_core_module(calls, checker_aware=True)
        with self.assertRaises(SystemExit) as ctx:
            run.main(self.base_args([
                "--enable-direct-diagonals", "--exact-joins",
                "--topology-binary", "/nonexistent/topology"]))
        self.assertIn("topology binary", str(ctx.exception))

    def test_exact_joins_forwards_checker(self):
        binary = os.path.join(self.tmp.name, "topology")
        with open(binary, "w") as handle:
            handle.write("#!/bin/sh\nexit 0\n")
        os.chmod(binary, 0o755)
        import hashlib

        calls = []
        sys.modules[self.fake_name] = fake_core_module(calls, checker_aware=True)
        summary = run.main(self.base_args([
            "--enable-direct-diagonals", "--exact-joins",
            "--topology-binary", binary, "--mode", "width_only"]))
        fits = [c for c in calls if c[0] == "fit"]
        self.assertTrue(fits)
        self.assertTrue(all(c[4] for c in fits))
        self.assertEqual(summary["topology_mode"], "exact_arrangement")
        self.assertEqual(summary["topology_binary"], binary)
        with open(binary, "rb") as handle:
            self.assertEqual(summary["topology_binary_sha256"],
                             hashlib.sha256(handle.read()).hexdigest())
        self.assertEqual(summary["cgal_version"], "6.1.1")
        self.assertTrue(summary["capture_sha256"])
        case = self.load_case(summary, "selective_default")
        self.assertEqual(case["arms"]["width_only"]["checker"], "exact_arrangement")

    def test_default_mode_is_strict_signature(self):
        summary = run.main(self.base_args())
        self.assertEqual(summary["topology_mode"], "strict_signature")
        self.assertIsNone(summary["topology_binary"])
        self.assertIsNone(summary["topology_binary_sha256"])

    def test_fatal_parity(self):
        with open(self.adapter, "w") as handle:
            handle.write(FAIL_ADAPTER)
        with self.assertRaises(SystemExit):
            run.main(self.base_args())


if __name__ == "__main__":
    unittest.main()
