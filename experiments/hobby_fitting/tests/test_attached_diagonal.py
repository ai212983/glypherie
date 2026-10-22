"""Geometry tests for the attached-diagonal joint solve.

Hersch 1993 section 6 figure 25 requires coupled borders parallel with
integer axis separation; Hobby 1993 section 6 supplies the shared curve
unknowns; Hersch section 2 requires the shared tangent joints survive.
Every bound below is derived from 26.6 rounding (each moved X errs at
most 1/128), not tuned to a glyph.
"""

import json
import math
import unittest
from pathlib import Path

import numpy as np

from experiments.hobby_fitting import attached_diagonal as ad
from experiments.hobby_fitting import curved_width as cw
from experiments.hobby_fitting import direct_diagonal as dd
from experiments.hobby_fitting import smooth_curve_fit as scf
from experiments.hobby_fitting.real_outline import parse_commands
from experiments.hobby_fitting.tests.test_smooth_curve_geometry import (
    TOPOLOGY_BINARY_REASON,
    topology_binary_present,
)

ROOT = Path(__file__).resolve().parents[3]
CAPTURES = (ROOT / "out/diagnostics/direct-diagonal/text-review"
            / "ascii-captures/Roboto-400-16.json")
CELL = (ROOT / "out/diagnostics/direct-diagonal/coverage-review"
        / "cells/Roboto_16.0_400_selective_default.json")

RQ = 1.0 / 128.0
SIZE = 16


def _load_two():
    case = json.loads(CAPTURES.read_text())[0]
    record = next(r for r in case["modes"]["selective_default"]["records"]
                  if r["codepoint"] == 50)
    cell = json.loads(CELL.read_text())
    return (record["source_commands"], record["fitted_commands"],
            cell["reference"])


def _prepared(source, upstream_oncurve):
    parsed = parse_commands(source)
    portions, _, loops, flats = dd._split_visible(parsed, canonical=True)
    pairs, _ = dd._recognize(portions, loops, ownership="interval")
    borders = dd._visible_borders(portions)
    exact = dd._curve_controls(parsed)
    quad_endpoints = set()
    for contour in parsed["contours"]:
        for seg in contour:
            if seg[0] == "quad":
                quad_endpoints.update((seg[2], seg[3]))
    out = []
    for pair in pairs:
        a, b = pair["a"], pair["b"]
        if (dd._axis_of(a["p0"], a["p1"]) is not None
                or dd._axis_of(b["p0"], b["p1"]) is not None):
            continue
        if not ({a["i0"], a["i1"], b["i0"], b["i1"]} & quad_endpoints):
            continue
        info, why = dd._prepare_pair(pair, borders, loops, loops, flats,
                                     flats, upstream_oncurve, SIZE,
                                     exact_curves=exact)
        if why is not None:
            continue
        yield info


def _point(coords, v):
    return (float(coords[v][0]), float(coords[v][1]))


class AttachedDiagonalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [str(p) for p in (CAPTURES, CELL) if not p.exists()]
        reasons = []
        if missing:
            reasons.append(
                "missing optional captures %s (git-ignored corpora; "
                "regenerate CAPTURES with "
                "experiments/hobby_fitting/text_review.py and CELL with "
                "experiments/hobby_fitting/coverage_review.py)"
                % ", ".join(missing))
        if not topology_binary_present():
            reasons.append(TOPOLOGY_BINARY_REASON)
        if reasons:
            raise unittest.SkipTest("; ".join(reasons))
        cls.source, cls.upstream_cmds, cls.ref = _load_two()
        cls.upstream = parse_commands(cls.upstream_cmds)
        cls.result = ad.fit(cls.source, cls.upstream_cmds, SIZE, cls.ref,
                            native_axes=(False, True))
        cls.cand = parse_commands(cls.result["candidate_commands"])

    def test_both_native_axes_abstains_exactly(self):
        result = ad.fit(self.source, self.upstream_cmds, SIZE, self.ref,
                        native_axes=(True, True))
        self.assertFalse(result["applied"])
        self.assertEqual(result["candidate_commands"], self.upstream_cmds)

    def test_real_two_applies(self):
        self.assertTrue(self.result["applied"], self.result.get("reason"))

    def test_parallel_and_integer_separation(self):
        self.assertTrue(self.result["applied"])
        up = self.upstream["oncurve"]
        cc = self.cand["oncurve"]
        moved = {v for v in range(len(up))
                 if _point(cc, v)[0] != _point(up, v)[0]}
        self.assertTrue(moved)
        checked = 0
        for info in _prepared(self.source, up):
            verts = {info["a"]["i0"], info["a"]["i1"],
                     info["b"]["i0"], info["b"]["i1"]}
            if not verts & moved:
                continue
            gate = dd._grid_target(info, self.ref["anchors"], SIZE)
            self.assertIsNotNone(gate)
            n = info["normal"]
            d = info["direction"]
            dn = math.hypot(d[0], d[1])
            d = (d[0] / dn, d[1] / dn)
            for edge in (info["a"], info["b"]):
                p0 = _point(cc, edge["i0"])
                p1 = _point(cc, edge["i1"])
                cross = (p1[0] - p0[0]) * d[1] - (p1[1] - p0[1]) * d[0]
                self.assertLessEqual(abs(cross), abs(d[1]) / 64.0 + 1e-9)
            ta = edge_t(info["a"], gate["fa"])
            tb = edge_t(info["b"], gate["fb"])
            a_pt = sample(cc, info["a"], ta)
            b_pt = sample(cc, info["b"], tb)
            sep = (n[0] * (b_pt[0] - a_pt[0])
                   + n[1] * (b_pt[1] - a_pt[1]))
            self.assertLessEqual(abs(sep - gate["target"]),
                                 abs(n[0]) / 64.0 + 1e-9)
            checked += 1
        self.assertGreater(checked, 0)

    def test_native_y_and_upright_x_retained(self):
        up = self.upstream["oncurve"]
        cc = self.cand["oncurve"]
        for v in range(len(up)):
            self.assertEqual(_point(cc, v)[1], _point(up, v)[1])
        parsed = parse_commands(self.source)
        for contour in parsed["contours"]:
            for seg in contour:
                if seg[0] != "line":
                    continue
                x0 = parsed["oncurve"][seg[1]][0]
                x1 = parsed["oncurve"][seg[2]][0]
                if x0 == x1 and parsed["oncurve"][seg[1]][1] != \
                        parsed["oncurve"][seg[2]][1]:
                    for v in (seg[1], seg[2]):
                        self.assertEqual(_point(cc, v)[0],
                                         _point(up, v)[0])

    def test_curve_joint_raw_cross(self):
        # The rounded candidate cross is never the raw exact value: with Y
        # frozen the joint cross is linear in the X unknowns, so rounding
        # each moved X by at most 1/128 perturbs the cross by first-order
        # leg terms only (the Y-frozen specialization of
        # scf._quant_cross_bound, whose second-order product vanishes).
        self.assertTrue(self.result["applied"], self.result.get("reason"))
        rows = self.result.get("continuity") or []
        parsed = parse_commands(self.source)
        no = len(parsed["oncurve"])
        base = parsed["oncurve"] + parsed["offcurve"]
        up = self.upstream["oncurve"] + self.upstream["offcurve"]
        cc = self.cand["oncurve"] + self.cand["offcurve"]
        joints = scf._joints(parsed, base, no)
        checked = 0
        for row in rows:
            occs = [o for o in joints.get(int(row["joint"]), [])
                    if o["smooth"] == bool(row["smooth"])
                    and (o["prev"][0] == "quad" or o["seg"][0] == "quad")]
            if not occs:
                continue
            self.assertEqual(len(occs), 1)
            occ = occs[0]
            j = int(row["joint"])
            iv = occ["prev"][1] if occ["prev"][0] == "line" \
                else no + occ["prev"][1]
            ov = occ["seg"][2] if occ["seg"][0] == "line" \
                else no + occ["seg"][1]
            target = float(row["raw_target"])
            self.assertLessEqual(abs(float(row["raw_cross"]) - target),
                                 1e-8 * (1 + abs(target)))
            cross, li, lo = scf._cross_of(np.asarray(cc, float), j,
                                          occ["prev"], occ["seg"], no)
            self.assertAlmostEqual(cross, float(row["cross_cand"]),
                                   delta=1e-12)
            _, old_li, old_lo = scf._cross_of(np.asarray(up, float), j,
                                              occ["prev"], occ["seg"], no)
            mx = tuple(float(cc[v][0]) != float(up[v][0])
                     for v in (iv, j, ov))
            bound = ((RQ if mx[0] else 0.0) + (RQ if mx[1] else 0.0)) * abs(
                old_lo[1]) + ((RQ if mx[1] else 0.0)
                               + (RQ if mx[2] else 0.0)) * abs(old_li[1])
            self.assertLessEqual(abs(cross - target), bound + 1e-9)
            self.assertGreaterEqual(float(row["allowed"]), bound - 1e-12)
            self.assertTrue(bool(np.linalg.norm(li) > 0
                                 and np.linalg.norm(lo) > 0))
            self.assertGreater(float(np.dot(li, old_li)), 0.0)
            self.assertGreater(float(np.dot(lo, old_lo)), 0.0)
            if occ["smooth"]:
                self.assertGreater(float(np.dot(li, lo)), 0.0)
            else:
                # Native fitting may already reverse a tiny source kink.
                # This model retains its upstream cross before rounding;
                # the independent rounding envelope above is authoritative.
                old_cross, _, _ = scf._cross_of(
                    np.asarray(up, float), j, occ["prev"], occ["seg"], no)
                self.assertAlmostEqual(target, old_cross, delta=1e-12)
            if row.get("constrained"):
                checked += 1
        self.assertGreater(checked, 0)

    def test_moved_quad_curvature(self):
        # _quad_interval_ok returns a pair; the source controls carry the
        # curvature intent, so the candidate is certified against source.
        self.assertTrue(self.result["applied"], self.result.get("reason"))
        parsed = parse_commands(self.source)
        no = len(parsed["oncurve"])
        src = parsed["oncurve"] + parsed["offcurve"]
        up = self.upstream["oncurve"] + self.upstream["offcurve"]
        cc = self.cand["oncurve"] + self.cand["offcurve"]
        moved = {v for v in range(len(src)) if tuple(cc[v]) != tuple(up[v])}
        checked = 0
        for contour in parsed["contours"]:
            for seg in contour:
                if seg[0] != "quad":
                    continue
                ctrl = [seg[2], no + seg[1], seg[3]]
                ok, reason = cw._quad_interval_ok(
                    [tuple(src[i]) for i in ctrl],
                    [tuple(cc[i]) for i in ctrl])
                self.assertTrue(ok, reason)
                if set(ctrl) & moved:
                    checked += 1
        self.assertGreater(checked, 0)

    def test_line_only_contour_unchanged(self):
        cmds = [{"op": "move_to", "x": 0.0, "y": 0.0},
                {"op": "line_to", "x": 10.0, "y": 0.0},
                {"op": "line_to", "x": 14.0, "y": -30.0},
                {"op": "line_to", "x": 4.0, "y": -30.0},
                {"op": "close"}]
        result = ad.fit(cmds, [dict(c) for c in cmds], SIZE, self.ref,
                        native_axes=(False, True))
        self.assertFalse(result["applied"])
        self.assertEqual(result["candidate_commands"], cmds)

    def test_y_shifted_two_matches(self):
        dy = 2.0
        shifted = shift_y(self.source, dy)
        shifted_up = shift_y(self.upstream_cmds, dy)
        result = ad.fit(shifted, shifted_up, SIZE, self.ref,
                        native_axes=(False, True))
        self.assertTrue(result["applied"], result.get("reason"))
        cand = parse_commands(result["candidate_commands"])
        up = parse_commands(shifted_up)
        for v in range(len(up["oncurve"])):
            self.assertEqual(float(cand["oncurve"][v][1]),
                             float(up["oncurve"][v][1]))


def edge_t(edge, frac):
    return edge["t0"] + (edge["t1"] - edge["t0"]) * frac


def sample(coords, edge, t):
    p0 = coords[edge["i0"]]
    p1 = coords[edge["i1"]]
    return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)


def shift_y(cmds, dy):
    out = []
    for cmd in cmds:
        cmd = dict(cmd)
        for key in ("y", "y1", "y2"):
            if key in cmd:
                cmd[key] = float(cmd[key]) + dy
                cmd.pop(key + "_bits", None)
        out.append(cmd)
    return out


if __name__ == "__main__":
    unittest.main()
