"""Symmetry placement prototype; geometric relationships only."""

import json
import math
import struct
import unittest
from pathlib import Path

import experiments.hobby_fitting.symmetry_placement as sp

ROOT = Path(__file__).resolve().parents[3]
X_CELL = (ROOT / "out/diagnostics/direct-diagonal/text-review"
          / "ascii-captures/Roboto-400-16.json")

# Simple symmetric hexagon in 64ths, axis 253/64; all values 26.6-exact.
HEX64 = [(29, 0), (477, 0), (400, 300), (400, 544), (106, 544), (106, 300)]
# Tapered simple octagon in halves, axis 3.0 before offset.
OCT = [(1.0, 0.0), (2.0, 2.0), (4.0, 2.0), (5.0, 0.0),
       (4.0, 0.0), (3.5, 1.0), (2.5, 1.0), (2.0, 0.0)]


def _bits(x, y):
    return {"x_bits": struct.unpack("<I", struct.pack("<f", x))[0],
            "y_bits": struct.unpack("<I", struct.pack("<f", y))[0]}


def cmds64(pts64, dx64=0):
    out = [{"op": "move_to", "x": (pts64[0][0] + dx64) / 64.0,
            "y": pts64[0][1] / 64.0}]
    out[0].update(_bits(out[0]["x"], out[0]["y"]))
    for x, y in pts64[1:]:
        cmd = {"op": "line_to", "x": (x + dx64) / 64.0, "y": y / 64.0}
        cmd.update(_bits(cmd["x"], cmd["y"]))
        out.append(cmd)
    return out + [{"op": "close"}]


def cmds(points):
    out = [{"op": "move_to", "x": points[0][0], "y": points[0][1]}]
    out[0].update(_bits(out[0]["x"], out[0]["y"]))
    for x, y in points[1:]:
        cmd = {"op": "line_to", "x": x, "y": y}
        cmd.update(_bits(cmd["x"], cmd["y"]))
        out.append(cmd)
    return out + [{"op": "close"}]


def seg_lengths(commands):
    pts = [(c["x"], c["y"]) for c in commands if c["op"] != "close"]
    return [math.hypot(b[0] - a[0], b[1] - a[1])
            for a, b in zip(pts, pts[1:] + pts[:1])]


class SymmetryPlacementTest(unittest.TestCase):
    def test_exact_mirror_applies_and_preserves_widths(self):
        src = cmds64(HEX64)
        up = cmds64(HEX64)
        res = sp.fit(src, up, 16, native_axes=(False, True))
        self.assertTrue(res["applied"])
        self.assertEqual(res["reason"], "applied")
        got = [(c["x"], c["y"]) for c in res["commands"] if c["op"] != "close"]
        for a, b in zip(seg_lengths(up), seg_lengths(res["commands"])):
            self.assertEqual(a, b)
        ys_old = [c["y"] for c in up if c["op"] != "close"]
        ys_new = [c["y"] for c in res["commands"] if c["op"] != "close"]
        self.assertEqual(ys_old, ys_new)
        for c in res["commands"]:
            if c["op"] == "close":
                continue
            self.assertEqual(c["x_bits"],
                             struct.unpack("<I", struct.pack("<f", c["x"]))[0])
            self.assertEqual(c["y_bits"],
                             struct.unpack("<I", struct.pack("<f", c["y"]))[0])
            self.assertEqual(sp._f32(c["x"]), c["x"])
            self.assertEqual(sp._f32(c["y"]), c["y"])
        axis = res["diagnostics"]["axes"]["x"]
        self.assertLessEqual(abs(axis["shift"]), 0.25)
        self.assertEqual(axis["shift"], 3.0 / 64.0)
        center = ((min(x for x, _ in got) + max(x for x, _ in got)) / 2.0)
        self.assertEqual(center, axis["target"])
        self.assertEqual(res["diagnostics"]["width_delta_max"], 0.0)

    def test_translation_invariance_of_target(self):
        first = sp.fit(cmds64(HEX64), cmds64(HEX64), 16)
        second = sp.fit(cmds64(HEX64, dx64=72), cmds64(HEX64, dx64=72), 16)
        self.assertTrue(first["applied"] and second["applied"])
        self.assertEqual(first["diagnostics"]["axes"]["x"]["target"], 4.0)
        self.assertEqual(second["diagnostics"]["axes"]["x"]["target"], 5.0)
        self.assertEqual(second["diagnostics"]["axes"]["x"]["shift"], -5 / 64)

    def test_nonuniform_but_symmetric_geometry_applies(self):
        pts = [(x + 0.125, y) for x, y in OCT]
        res = sp.fit(cmds(pts), cmds(pts), 16)
        self.assertTrue(res["applied"])
        self.assertEqual(res["diagnostics"]["axes"]["x"]["reason"], "certified")

    def test_already_centered_abstains(self):
        up = cmds(OCT)
        res = sp.fit(cmds(OCT), up, 16)
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "already-centered")
        self.assertEqual(res["commands"], up)

    def test_intentional_asymmetry_abstains_control(self):
        bad = [tuple(p) for p in HEX64]
        bad[2] = (bad[2][0] + 8, bad[2][1])
        up = cmds64(HEX64)
        res = sp.fit(cmds64(bad), up, 16, native_axes=(False, True))
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "no-near-reflection")
        self.assertEqual(res["commands"], up)

    def test_native_x_owned_abstains(self):
        src = cmds64(HEX64)
        up = cmds64(HEX64)
        res = sp.fit(src, up, 16, native_axes=(True, False))
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "native-owned")
        self.assertEqual(res["commands"], up)

    def test_horizontal_axis_uses_y_ownership(self):
        pts = [(y / 64.0, x / 64.0) for x, y in HEX64]
        src, up = cmds(pts), cmds(pts)
        res = sp.fit(src, up, 16, native_axes=(False, False))
        self.assertTrue(res["applied"])
        self.assertEqual(res["diagnostics"]["axes"]["y"]["reason"], "certified")
        self.assertEqual(res["diagnostics"]["axes"]["y"]["shift"], 3.0 / 64.0)
        blocked = sp.fit(src, up, 16, native_axes=(False, True))
        self.assertFalse(blocked["applied"])
        self.assertEqual(blocked["diagnostics"]["axes"]["y"]["reason"],
                         "native-owned")

    def test_encoding_variants_agree(self):
        variants = [cmds64(HEX64), cmds64(HEX64[3:] + HEX64[:3]),
                    cmds64(list(reversed(HEX64)))]
        results = [sp.fit(v, v, 16) for v in variants]
        decisions = [(r["applied"], r["reason"]) for r in results]
        self.assertTrue(all(d == decisions[0] for d in decisions))
        first = sorted((c["x"], c["y"]) for c in results[0]["commands"]
                       if c["op"] != "close")
        for r in results[1:]:
            self.assertEqual(sorted((c["x"], c["y"]) for c in r["commands"]
                                    if c["op"] != "close"), first)
        box_a = [(72, 64), (136, 64), (136, 128), (72, 128)]
        box_b = [(264, 64), (328, 64), (328, 128), (264, 128)]
        multi = cmds64(box_a) + cmds64(box_b)
        multi_rev = cmds64(box_b) + cmds64(box_a)
        both = [sp.fit(multi, multi, 16), sp.fit(multi_rev, multi_rev, 16)]
        self.assertTrue(all(r["applied"] for r in both))
        for r in both:
            self.assertEqual(r["diagnostics"]["axes"]["x"]["shift"], -8 / 64)

    def test_decision_stable_across_sizes(self):
        for size, off in ((12, 2), (16, 0), (24, -3)):
            res = sp.fit(cmds64(HEX64, dx64=off), cmds64(HEX64, dx64=off),
                         size)
            self.assertTrue(res["applied"], size)
            self.assertEqual(res["diagnostics"]["axes"]["x"]["target"], 4.0)

    def test_curves_abstain(self):
        src = [{"op": "move_to", "x": 0.0, "y": 0.0},
               {"op": "curve_to", "x1": 1.0, "y1": 3.0, "x2": 3.0, "y2": 3.0,
                "x": 4.0, "y": 0.0},
               {"op": "line_to", "x": 4.0, "y": 4.0},
               {"op": "line_to", "x": 0.0, "y": 4.0},
               {"op": "close"}]
        res = sp.fit(src, [dict(c) for c in src], 16)
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "curves-unsupported")

    def test_correspondence_mismatch_abstains(self):
        src = cmds64(HEX64)
        extra = {"op": "line_to", "x": 0.0, "y": 0.0}
        extra.update(_bits(0.0, 0.0))
        up = [dict(c) for c in src[:-1]] + [extra, dict(src[-1])]
        res = sp.fit(src, up, 16)
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "no-correspondence")

    def test_empty_outline_abstains(self):
        res = sp.fit([], [], 16)
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "empty-outline")
        self.assertEqual(res["commands"], [])
        up = cmds64(HEX64)
        res2 = sp.fit([], up, 16)
        self.assertEqual(res2["reason"], "empty-outline")
        self.assertEqual(res2["commands"], up)

    def test_malformed_native_axes_abstain(self):
        src = cmds64(HEX64)
        up = cmds64(HEX64)
        for bad_axes in (None, True, (False,), (False, True, False),
                         ("x", False), "xy", [0, 1]):
            res = sp.fit(src, up, 16, native_axes=bad_axes)
            self.assertFalse(res["applied"], bad_axes)
            self.assertEqual(res["reason"], "malformed-native-axes",
                             bad_axes)
            self.assertEqual(res["commands"], up)

    def test_malformed_arm_abstains(self):
        src = cmds64(HEX64)
        res = sp.fit(src, src, 16, arm="widen")
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "malformed-arm")

    def test_strict_grammar_rejects(self):
        up = cmds64(HEX64)
        close_x = [dict(c) for c in up]
        close_x[-1] = {"op": "close", "x": 1.0}
        trailing = [c for c in up if c["op"] != "close"]
        nan_cmd = [dict(c) for c in up]
        nan_cmd[1] = {"op": "line_to", "x": float("nan"), "y": 0.0}
        unknown = [dict(c) for c in up]
        unknown[1] = {"op": "spline_to", "x": 1.0, "y": 1.0}
        for bad in (close_x, trailing, nan_cmd, unknown, "cmds", [{}]):
            res = sp.fit(bad, up, 16)
            self.assertFalse(res["applied"], bad)
            self.assertEqual(res["reason"], "malformed-commands", bad)
            self.assertEqual(res["commands"], up)

    def test_untouched_axis_keeps_signed_zero_bits(self):
        pts = [(x / 64.0, (-0.0 if y == 0 else y / 64.0)) for x, y in HEX64]
        src = cmds(pts)
        res = sp.fit(src, cmds(pts), 16, native_axes=(False, True))
        self.assertTrue(res["applied"])
        for old, new in zip(src, res["commands"]):
            if old["op"] == "close":
                continue
            self.assertEqual(new["y"], old["y"])
            self.assertEqual(new["y_bits"], old["y_bits"])
            if math.copysign(1.0, old["y"]) < 0.0:
                self.assertEqual(new["y_bits"], 0x80000000)

    def test_unrepresentable_shift_abstains(self):
        src = cmds64(HEX64)
        off = [dict(c) for c in src]
        for c in off:
            if c["op"] != "close":
                c["x"] = c["x"] - 0.003125
        res = sp.fit(off, off, 16)
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "unrepresentable-shift")
        self.assertEqual(res["commands"], off)

    def test_self_crossing_abstains(self):
        bow = cmds64([(0, 0), (128, 128), (128, 0), (0, 128)])
        for arm in ("strict-quantum", "phase-range"):
            res = sp.fit(bow, bow, 16, arm=arm)
            self.assertFalse(res["applied"], arm)
            self.assertEqual(res["reason"], "ambiguous-overlap", arm)

    def test_coincident_contours_abstain(self):
        box = cmds64([(64, 64), (128, 64), (128, 128), (64, 128)], dx64=8)
        dbl = box + [dict(c) for c in box]
        res = sp.fit(dbl, dbl, 16)
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "ambiguous-overlap")

    def test_phase_range_applies_exact_synthetic(self):
        src = cmds64(HEX64)
        res = sp.fit(src, src, 16, arm="phase-range")
        self.assertTrue(res["applied"])
        self.assertEqual(res["reason"], "applied-phase-range")
        axis = res["diagnostics"]["axes"]["x"]
        self.assertEqual((axis["cmin"], axis["cmax"]),
                         (253 / 64.0, 253 / 64.0))
        self.assertEqual(axis["target"], 4.0)
        self.assertEqual(axis["shift"], 3.0 / 64.0)
        self.assertEqual(res["diagnostics"]["shift"], [3.0 / 64.0, 0.0])
        self.assertEqual(res["diagnostics"]["width_delta_max"], 0.0)
        self.assertGreater(axis["n_pairs"], 0)

    def test_phase_range_already_centered(self):
        pts = [(x + 3 / 64.0, y) for x, y in
               [(x / 64.0, y / 64.0) for x, y in HEX64]]
        up = cmds(pts)
        res = sp.fit(cmds(pts), up, 16, arm="phase-range")
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "already-centered")
        self.assertEqual(res["commands"], up)

    def test_phase_range_wide_interval_abstains(self):
        raw = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0)]
        res = sp.fit(cmds(raw), cmds(raw), 16, arm="phase-range")
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "phase-cell-uncontained")

    def test_phase_range_respects_native_ownership(self):
        src = cmds64(HEX64)
        res = sp.fit(src, src, 16, native_axes=(True, False),
                     arm="phase-range")
        self.assertFalse(res["applied"])
        self.assertEqual(res["diagnostics"]["axes"]["x"]["reason"],
                         "native-owned")

    def test_phase_range_interval_encoding_invariant(self):
        variants = [cmds64(HEX64), cmds64(HEX64[3:] + HEX64[:3]),
                    cmds64(list(reversed(HEX64)))]
        ivs = [sp.axis_interval(v, "x") for v in variants]
        self.assertTrue(all(iv is not None for iv in ivs))
        for iv in ivs[1:]:
            self.assertEqual((iv["cmin"], iv["cmax"]),
                             (ivs[0]["cmin"], ivs[0]["cmax"]))

    @unittest.skipUnless(X_CELL.exists(), "capture packet absent")
    def test_real_x_control_abstains(self):
        data = json.loads(X_CELL.read_text())
        recs = data[0]["modes"]["selective_default"]["records"]
        rec = next(r for r in recs if r.get("codepoint") == 120)
        res = sp.fit(rec["source_commands"], rec["fitted_commands"], 16,
                     native_axes=(False, True))
        self.assertFalse(res["applied"])
        self.assertEqual(res["reason"], "no-near-reflection")
        self.assertEqual(res["commands"], rec["fitted_commands"])
        score = res["diagnostics"]["axes"]["x"]["score_source"]
        self.assertGreater(score, sp.EPS_REC)
        self.assertLess(score, 4.0 * sp.EPS_REC)

    @unittest.skipUnless(X_CELL.exists(), "capture packet absent")
    def test_real_x_phase_range_places_rigidly(self):
        data = json.loads(X_CELL.read_text())
        recs = data[0]["modes"]["selective_default"]["records"]
        rec = next(r for r in recs if r.get("codepoint") == 120)
        res = sp.fit(rec["source_commands"], rec["fitted_commands"], 16,
                     native_axes=(False, True), arm="phase-range")
        self.assertTrue(res["applied"])
        self.assertEqual(res["reason"], "applied-phase-range")
        axis = res["diagnostics"]["axes"]["x"]
        self.assertEqual((axis["cmin"], axis["cmax"]), (3.9375, 3.96875))
        self.assertEqual(axis["interval_mid"], 3.953125)
        self.assertEqual(axis["target"], 4.0)
        self.assertEqual(axis["shift"], 3.0 / 64.0)
        self.assertEqual(res["diagnostics"]["width_delta_max"], 0.0)
        old = [c["y"] for c in rec["fitted_commands"] if c["op"] != "close"]
        new = [c["y"] for c in res["commands"] if c["op"] != "close"]
        self.assertEqual(old, new)

    @unittest.skipUnless(X_CELL.exists(), "capture packet absent")
    def test_real_overlapping_glyphs_abstain(self):
        data = json.loads(X_CELL.read_text())
        recs = data[0]["modes"]["selective_default"]["records"]
        for cp, arm in ((107, "strict-quantum"), (107, "phase-range"),
                        (65, "phase-range"), (122, "phase-range")):
            rec = next(r for r in recs if r.get("codepoint") == cp)
            res = sp.fit(rec["source_commands"], rec["fitted_commands"], 16,
                         native_axes=(False, True), arm=arm)
            self.assertFalse(res["applied"], (cp, arm))
            self.assertEqual(res["reason"], "ambiguous-overlap", (cp, arm))
            self.assertEqual(res["commands"], rec["fitted_commands"])


if __name__ == "__main__":
    unittest.main()
