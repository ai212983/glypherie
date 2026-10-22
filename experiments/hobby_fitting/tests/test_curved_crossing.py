"""Tests for the bounded joint curved-crossing fit.

Hobby section 3.5 supplies approximate-reflection correspondence on the
crossing region; Hersch sections 5-6 supply grid-compatible symmetry
phase. The four-arm incidence classifier below keeps that sourced
correspondence on true crossings: forks and hooks abstain instead of
receiving a crossing placement. Per-arm relative widths follow Hobby
(17) preserving source contrast rather than forcing a mirror.
"""
# cspell:words oncurve offcurve cand rebits fontTools instancer ctrls onmap offmap

from functools import lru_cache
import math
import struct
import unittest
from pathlib import Path

from experiments.hobby_fitting import curved_crossing as cc
from experiments.hobby_fitting import curved_width as cw
from experiments.hobby_fitting import shape_balance_review as checks
from experiments.hobby_fitting import smooth_curve_fit
from experiments.hobby_fitting.real_outline import parse_commands
from experiments.hobby_fitting.tests.test_smooth_curve_geometry import (
    TOPOLOGY_BINARY_REASON,
    topology_binary_present,
)

ROOT = Path(__file__).resolve().parents[3]
FONT_PATH = ROOT / "fonts/SourceSans3.ttf"
CAP_PATH = (ROOT / "out/diagnostics/direct-diagonal/text-review"
            / "ascii-captures/SourceSans3-400-16.json")
REF_PATH = (ROOT / "out/diagnostics/direct-diagonal/coverage-review"
            / "cells/SourceSans3_16.0_400_selective_default.json")

FAMILY_KWARGS = dict(size_px=16, native_axes=(False, False))

CLOSED_REASONS = frozenset({
    "malformed-native-axes", "native-X-owned", "invalid-geometry-scale",
    "no-correspondence", "malformed-commands", "non-26.6-input",
    "no-reference-anchors", "no-attached-diagonals",
    "uncertified-substitution", "no-waist", "parity-ambiguous",
    "unsupported-crossing-class", "no-symmetry-matches",
    "phase-unconstrained", "no-free-controls", "weld-mismatch",
    "degenerate-joint", "source-degenerate-curvature",
    "fixed-constraints-incompatible", "movement-budget-empty",
    "no-curve-constraints", "constraints-incompatible",
    "rounded-movement-budget", "rounded-hard-constraint",
    "joint-continuity", "clearance-failed",
    "clearance-station-disk-curve", "clearance-station-disk-line",
    "clearance-moved-fixed-hull", "clearance-moved-moved-hull",
    "clearance-swept-fixed-curve", "clearance-swept-moved-curve",
    "curve-degenerate-leg", "curve-degenerate-curvature",
    "curve-curvature-sign", "curve-tangent-reversed",
    "y-changed", "cap-changed", "topology", "topology-captured",
    "checker-rejected", "checker-exception", "unsupported-topology",
    "no-movement",
})


def _f32(value):
    return struct.unpack(">f", struct.pack(">f", value))[0]


def _rebits(commands):
    for cmd in commands:
        for key in ("x", "y", "x1", "y1", "x2", "y2"):
            if key in cmd:
                cmd[key + "_bits"] = struct.unpack(
                    ">I", struct.pack(">f", cmd[key]))[0]
    return commands


@lru_cache(maxsize=None)
def load_case(char):
    import json
    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib.instancer import instantiateVariableFont
    except ImportError:
        raise unittest.SkipTest(
            "missing optional fontTools dependency "
            "(run with uv run --with fonttools==4.53.1 -- "
            "python -m unittest ...)")
    from experiments.hobby_fitting.curved_crossing_review import raw_commands

    missing = [str(p) for p in (FONT_PATH, CAP_PATH, REF_PATH)
               if not p.exists()]
    if missing:
        raise unittest.SkipTest(
            "missing optional prerequisites %s (CAP_PATH/REF_PATH are "
            "git-ignored corpora; regenerate CAP_PATH with "
            "experiments/hobby_fitting/text_review.py and REF_PATH with "
            "experiments/hobby_fitting/coverage_review.py)"
            % ", ".join(missing))
    if not topology_binary_present():
        raise unittest.SkipTest(TOPOLOGY_BINARY_REASON)
    cap = json.loads(CAP_PATH.read_text())[0]
    record = [r for r in cap["modes"]["selective_default"]["records"]
              if r["codepoint"] == ord(char)][0]
    reference = json.loads(REF_PATH.read_text())["reference"]
    with TTFont(FONT_PATH) as font:
        instance = instantiateVariableFont(font, cap['axes'], inplace=False)
        raw = raw_commands(instance, record['glyph_id'], 16)
        instance.close()
    assert reference.get("anchors"), "reference anchors"
    return (raw, record["source_commands"], record["fitted_commands"],
            reference)


def fit_default(raw, captured, upstream, reference, **kwargs):
    args = dict(FAMILY_KWARGS)
    args.update(kwargs)
    return cc.fit(raw, captured, upstream, args["size_px"], reference,
                  args["native_axes"],
                  topology_checker=kwargs.get("topology_checker"))


def primitives(commands):
    parsed = parse_commands(commands)
    assert len(parsed["contours"]) == 1
    points = parsed["oncurve"] + parsed["offcurve"]
    count = len(parsed["oncurve"])
    prims = []
    for seg in parsed["contours"][0]:
        if seg[0] == "line":
            a, b = tuple(points[seg[1]]), tuple(points[seg[2]])
            if a == b:
                continue
            prims.append(("line", None, a, b))
        elif seg[0] == "quad":
            prims.append(("quad", tuple(points[count + seg[1]]),
                          tuple(points[seg[2]]), tuple(points[seg[3]])))
        else:
            raise AssertionError("unsupported segment")
    return prims


def emit_cycle(start, prims):
    out = [{"op": "move_to", "x": start[0], "y": start[1]}]
    drawn = prims[:-1] if prims[-1][0] == 'line' else prims
    for kind, ctrl, _, end in drawn:
        if kind == "line":
            out.append({"op": "line_to", "x": end[0], "y": end[1]})
        else:
            out.append({"op": "quad_to", "x1": ctrl[0], "y1": ctrl[1],
                        "x": end[0], "y": end[1]})
    out.append({"op": "close"})
    return _rebits(out)


def rotate_commands(commands, shift):
    prims = primitives(commands)
    shift %= len(prims)
    cycled = prims[shift:] + prims[:shift]
    return emit_cycle(cycled[0][2], cycled)


def reverse_commands(commands):
    prims = primitives(commands)
    flipped = [(kind, ctrl, end, start)
               for kind, ctrl, start, end in reversed(prims)]
    return emit_cycle(flipped[0][2], flipped)


def assert_same_geometry(test, original, transformed):
    def signature(commands):
        return sorted((kind, ctrl, *sorted((start, end)))
                      for kind, ctrl, start, end in primitives(commands))
    test.assertEqual(signature(original), signature(transformed))


def shift_commands(commands, dx, dy, transform):
    out = []
    for cmd in commands:
        item = dict(cmd)
        for key in ("x", "x1", "x2"):
            if key in item:
                item[key] = transform(item[key], dx)
        for key in ("y", "y1", "y2"):
            if key in item:
                item[key] = transform(item[key], dy)
        out.append(item)
    return _rebits(out)


class CurvedCrossingTest(unittest.TestCase):

    def test_x16_applies_with_valid_delivery(self):
        raw, captured, upstream, reference = load_case("x")
        result = fit_default(raw, captured, upstream, reference)
        self.assertTrue(result["applied"], result["reason"])
        self.assertEqual(result["reason"], "applied-curved-crossing")
        candidate = result["candidate_commands"]
        self.assertTrue(checks.same_skeleton(upstream, candidate))
        for cmd in candidate:
            self.assertTrue(checks.valid_command(cmd), cmd)
        self.assertTrue(checks.respects_pins(upstream, candidate,
                                             (False, True)))
        self.assertTrue(all(c["y"] == u["y"]
                            for c, u in zip(candidate, upstream)
                            if "y" in c))
        movement = max((math.dist(
            tuple(a), tuple(b)) for a, b in zip(
                parse_commands(upstream)["oncurve"]
                + parse_commands(upstream)["offcurve"],
                parse_commands(candidate)["oncurve"]
                + parse_commands(candidate)["offcurve"])), default=0.0)
        self.assertAlmostEqual(movement, result["movement"], delta=1e-12)
        self.assertTrue(math.isfinite(result["radius"]))
        self.assertGreater(result["radius"], 0)
        self.assertLessEqual(movement, result["radius"])
        parsed = parse_commands(raw)
        cand = parse_commands(candidate)
        points = parsed["oncurve"] + parsed["offcurve"]
        new = cand["oncurve"] + cand["offcurve"]
        for curve in cw.curves_of(parsed):
            ok, why = cw._quad_interval_ok(
                [tuple(points[i]) for i in curve["idx"]],
                [tuple(new[i]) for i in curve["idx"]])
            self.assertTrue(ok, (curve["idx"], why))
        old = parse_commands(upstream)
        old_points = old['oncurve'] + old['offcurve']
        for duplicate, canonical in smooth_curve_fit._weld_map(old, old_points).items():
            self.assertEqual(tuple(new[duplicate]), tuple(new[canonical]))

    def test_x16_preserves_source_contrast_without_mirror(self):
        raw, captured, upstream, reference = load_case("x")
        result = fit_default(raw, captured, upstream, reference)
        self.assertTrue(result["applied"], result["reason"])
        arms = result["arms"]
        self.assertEqual(set(arms), {"rising", "falling"})
        src = {arm: arms[arm]["source"] for arm in arms}
        cand = {arm: arms[arm]["candidate"] for arm in arms}
        src_diff = src["rising"] - src["falling"]
        cand_diff = cand["rising"] - cand["falling"]
        self.assertNotEqual(src_diff, 0.0)
        self.assertEqual(math.copysign(1.0, cand_diff),
                         math.copysign(1.0, src_diff))
        src_ratio = src["rising"] / src["falling"]
        cand_ratio = cand["rising"] / cand["falling"]
        self.assertLess(abs(cand_ratio - src_ratio), abs(1.0 - src_ratio))
        self.assertGreater(abs(cand_diff), 0.0)

    def test_x16_phase_report_is_finite(self):
        raw, captured, upstream, reference = load_case("x")
        result = fit_default(raw, captured, upstream, reference)
        self.assertTrue(result["applied"], result["reason"])
        diag = result["diagnostics"]
        self.assertTrue(math.isfinite(diag["parity_target"]))
        self.assertTrue(math.isfinite(diag["phase_mid_cand"]))
        self.assertTrue(math.isfinite(diag["phase_residual"]))
        self.assertEqual(diag["matches"], 4)

    def test_x16_quantized_capture_keeps_raw_curvature(self):
        raw, captured, upstream, reference = load_case("x")
        result = fit_default(raw, captured, upstream, reference)
        self.assertTrue(result["applied"], result["reason"])
        zeros = result["diagnostics"]["quantized_zero_curves"]
        self.assertTrue(len(zeros) > 0, zeros)
        raw_parsed = parse_commands(raw)
        cap_parsed = parse_commands(captured)
        raw_points = raw_parsed["oncurve"] + raw_parsed["offcurve"]
        cap_points = cap_parsed["oncurve"] + cap_parsed["offcurve"]
        by_control = {}
        for curve in cw.curves_of(raw_parsed):
            by_control[curve["idx"][1]] = curve["idx"]
        for index in zeros:
            self.assertIn(index, by_control)
            idx = by_control[index]
            raw_ctrls = [raw_points[i] for i in idx]
            cap_ctrls = [cap_points[i] for i in idx]
            raw_cross = ((raw_ctrls[1][0] - raw_ctrls[0][0])
                         * (raw_ctrls[2][1] - raw_ctrls[1][1])
                         - (raw_ctrls[1][1] - raw_ctrls[0][1])
                         * (raw_ctrls[2][0] - raw_ctrls[1][0]))
            cap_cross = ((cap_ctrls[1][0] - cap_ctrls[0][0])
                         * (cap_ctrls[2][1] - cap_ctrls[1][1])
                         - (cap_ctrls[1][1] - cap_ctrls[0][1])
                         * (cap_ctrls[2][0] - cap_ctrls[1][0]))
            self.assertNotEqual(raw_cross, 0.0)
            self.assertEqual(cap_cross, 0.0)

    def test_X16_applies(self):
        raw, captured, upstream, reference = load_case("X")
        result = fit_default(raw, captured, upstream, reference)
        self.assertTrue(result["applied"], result["reason"])
        candidate = result["candidate_commands"]
        self.assertTrue(checks.same_skeleton(upstream, candidate))
        self.assertTrue(checks.respects_pins(upstream, candidate,
                                             (False, True)))
        self.assertLessEqual(result["movement"], result["radius"])

    def test_y_hook_abstains_without_identity_branch(self):
        raw, captured, upstream, reference = load_case("y")
        result = fit_default(raw, captured, upstream, reference)
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "unsupported-crossing-class")
        self.assertIs(result["candidate_commands"], upstream)
        waist = result["waist"]
        self.assertEqual(result["arms_below"], [])
        self.assertEqual(sorted(result["arms_above"]), ["falling", "rising"])
        self.assertLess(waist["level"], 0.0)

    def test_native_x_owned_abstains_exact(self):
        raw, captured, upstream, reference = load_case("x")
        result = fit_default(raw, captured, upstream, reference,
                             native_axes=(True, False))
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "native-X-owned")
        self.assertIs(result["candidate_commands"], upstream)

    def test_native_y_owned_still_applies(self):
        raw, captured, upstream, reference = load_case("x")
        result = fit_default(raw, captured, upstream, reference,
                             native_axes=(False, True))
        self.assertTrue(result["applied"], result["reason"])
        self.assertTrue(checks.respects_pins(result["candidate_commands"],
                                             upstream, (False, True)))

    def test_malformed_inputs_abstain_exact(self):
        raw, captured, upstream, reference = load_case("x")
        bad_axes = fit_default(raw, captured, upstream, reference,
                               native_axes=(1, 0))
        self.assertEqual(bad_axes["reason"], "malformed-native-axes")
        self.assertIs(bad_axes["candidate_commands"], upstream)
        bad_size = cc.fit(raw, captured, upstream, float("nan"),
                          reference, (False, False))
        self.assertEqual(bad_size["reason"], "invalid-geometry-scale")
        broken = [dict(c) for c in upstream]
        del broken[3]
        no_corr = fit_default(raw, captured, broken, reference)
        self.assertEqual(no_corr["reason"], "no-correspondence")
        self.assertIs(no_corr["candidate_commands"], broken)
        off_grid = [dict(c) for c in upstream]
        off_grid[0] = dict(off_grid[0], x=off_grid[0]["x"] + 0.001)
        non_grid = fit_default(raw, captured, off_grid, reference)
        self.assertEqual(non_grid["reason"], "non-26.6-input")
        no_ref = fit_default(raw, captured, upstream, {})
        self.assertEqual(no_ref["reason"], "no-reference-anchors")

    def test_collinear_raw_curve_abstains(self):
        commands = [
            {"op": "move_to", "x": 0.0, "y": 0.0},
            {"op": "quad_to", "x1": 1.0, "y1": 0.0, "x": 2.0, "y": 0.0},
            {"op": "line_to", "x": 2.0, "y": 1.0},
            {"op": "close"},
        ]
        grid = _rebits([{**c} for c in commands])
        _, _, _, reference = load_case("x")
        result = fit_default(commands, grid, grid, reference)
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "source-degenerate-curvature")
        self.assertTrue(len(result["raw_crosses"]) > 0)

    def test_callback_reject_and_exception_abstain_exact(self):
        raw, captured, upstream, reference = load_case("x")
        reject = fit_default(
            raw, captured, upstream, reference,
            topology_checker=lambda s, u, c: {"ok": False,
                                              "verdict": {"reason": "no"}})
        self.assertEqual(reject["reason"], "checker-rejected")
        self.assertIs(reject["candidate_commands"], upstream)

        def fail(source, fitted, candidate):
            raise RuntimeError("boom")

        exc = fit_default(raw, captured, upstream, reference,
                          topology_checker=fail)
        self.assertEqual(exc["reason"], "checker-exception")
        self.assertIs(exc["candidate_commands"], upstream)

    def test_callback_ok_applies_through_gate(self):
        import functools
        raw, captured, upstream, reference = load_case("x")
        gate = functools.partial(cw._substitution_gate)
        result = fit_default(raw, captured, upstream, reference,
                             topology_checker=lambda s, u, c: gate(s, u, c))
        self.assertTrue(result["applied"], result["reason"])

    def test_integer_translation_applies_translated(self):
        raw, captured, upstream, reference = load_case("x")
        base = fit_default(raw, captured, upstream, reference)
        self.assertTrue(base["applied"], base["reason"])
        moved = shift_commands(
            base["candidate_commands"], 3, -2,
            lambda v, d: struct.unpack(
                ">f", struct.pack(">f", v + d))[0])
        raw2 = shift_commands(raw, 3, -2, lambda v, d: v + d)
        cap2 = shift_commands(captured, 3, -2, lambda v, d: v + d)
        up2 = shift_commands(upstream, 3, -2, lambda v, d: v + d)
        result = fit_default(raw2, cap2, up2, reference)
        self.assertTrue(result["applied"], result["reason"])
        self.assertEqual(moved, result["candidate_commands"])

    def test_reflection_preserves_widths(self):
        raw, captured, upstream, reference = load_case("x")
        base = fit_default(raw, captured, upstream, reference)
        self.assertTrue(base["applied"], base["reason"])
        neg = []
        for cmds in (raw, captured, upstream):
            out = []
            for cmd in cmds:
                item = dict(cmd)
                for key in ("x", "x1", "x2"):
                    if key in item:
                        item[key] = -item[key]
                out.append(item)
            neg.append(_rebits(out))
        result = fit_default(neg[0], neg[1], neg[2], reference)
        self.assertTrue(result["applied"], result["reason"])
        expected = sorted(p["candidate_width"] for p in base["pairs"])
        got = sorted(p["candidate_width"] for p in result["pairs"])
        self.assertEqual(len(expected), len(got))
        for want, have in zip(expected, got):
            self.assertAlmostEqual(want, have, delta=1e-9)

    def test_rotation_preserves_fitted_geometry(self):
        raw, captured, upstream, reference = load_case("x")
        baseline = fit_default(raw, captured, upstream, reference)
        for shift in (3, 5):
            with self.subTest(shift=shift):
                raw2 = rotate_commands(raw, shift)
                cap2 = rotate_commands(captured, shift)
                up2 = rotate_commands(upstream, shift)
                assert_same_geometry(self, raw, raw2)
                assert_same_geometry(self, captured, cap2)
                assert_same_geometry(self, upstream, up2)
                result = fit_default(raw2, cap2, up2, reference)
                self.assertTrue(result['applied'], result['reason'])
                candidate = result['candidate_commands']
                self.assertTrue(checks.same_skeleton(up2, candidate))
                self.assertTrue(all(checks.valid_command(cmd) for cmd in candidate))
                assert_same_geometry(self, baseline['candidate_commands'], candidate)

    def test_reversal_preserves_fitted_geometry(self):
        raw, captured, upstream, reference = load_case("x")
        raw2 = reverse_commands(raw)
        cap2 = reverse_commands(captured)
        up2 = reverse_commands(upstream)
        assert_same_geometry(self, raw, raw2)
        assert_same_geometry(self, captured, cap2)
        assert_same_geometry(self, upstream, up2)
        result = fit_default(raw2, cap2, up2, reference)
        self.assertTrue(result['applied'], result['reason'])
        candidate = result['candidate_commands']
        self.assertTrue(checks.same_skeleton(up2, candidate))
        self.assertTrue(all(checks.valid_command(cmd) for cmd in candidate))
        baseline = fit_default(raw, captured, upstream, reference)
        assert_same_geometry(self, baseline['candidate_commands'], candidate)

    def test_command_index_maps_quad_controls(self):
        commands = [
            {"op": "move_to", "x": 0.0, "y": 0.0},
            {"op": "quad_to", "x1": 1.0, "y1": 1.0, "x": 2.0, "y": 0.0},
            {"op": "line_to", "x": 2.0, "y": 2.0},
            {"op": "close"},
        ]
        parsed = parse_commands(commands)
        onmap, offmap = cc._command_index(commands, parsed)
        self.assertEqual(onmap[0], (0, "x"))
        self.assertEqual(onmap[1], (1, "x"))
        self.assertEqual(offmap[0], (1, "x1"))
        self.assertEqual(onmap[2], (2, "x"))
        with self.assertRaises(ValueError):
            cc._command_index(commands + [{"op": "curve_to", "x1": 0.0,
                                           "y1": 0.0, "x2": 1.0,
                                           "y2": 1.0, "x": 2.0,
                                           "y": 2.0}], parsed)

    def test_certified_depth_accepts_raw_f64(self):
        raw, _, _, _ = load_case("x")
        depth, cert = cc._certified_depth(raw)
        self.assertEqual(depth, 0)
        self.assertTrue(cert.get("ok"), cert)


if __name__ == "__main__":
    unittest.main()
