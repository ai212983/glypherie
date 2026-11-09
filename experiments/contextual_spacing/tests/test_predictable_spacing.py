# cspell:words roboto yinyangfit
"""Focused tests for the predictable spacing-control prototype.

Covers catalogue mapping, Source-exact whole-text identity from independent
capture arithmetic, strength-1 endpoint parity against direct solver calls,
per-pair monotonic movement in each endpoint's own direction, independent
monotone tracking with spaces excluded, glyph invariance, apply-once layout
and frozen-grid plateau records. Optical quality is out of scope here.
"""
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REPO = Path(__file__).resolve().parents[3]

import predictable_spacing as ps
from solver import Controls, Solver

CATALOGUE = json.loads(
    (REPO / "apps/web/scripts/landing-samples/main-page.json").read_text())
CAPTURES = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3"
            / "captures")
SITE = (REPO / "out/diagnostics/contextual-spacing/predictable-spacing"
        / "site")
PINNED = "roboto-16"


def pixel_round(value):
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def raw_mono_capture(path):
    capture = json.loads(Path(path).read_text())
    advances = {g["codepoint"]: g["finalized_advance_px"]
                for g in capture["glyphs"]}
    kern = {(p["left"], p["right"]): p["adjustment_px"]
            for p in capture.get("metric_pairs_on", [])}
    return advances, kern


def raw_gray_capture(path):
    capture = json.loads(Path(path).read_text())
    font = capture["font"]
    advances = {g["codepoint"]: g["advance_26_6"] / 64.0
                for g in font["glyphs"]}
    kern = {(p["left"], p["right"]): p["adjustment_26_6"] / 64.0
            for p in (font.get("kerning") or [])}
    return advances, kern


def raw_origins_mono(advances, kern, line):
    cps = [ord(c) for c in line]
    origins, pen = [0], 0
    for left, right in zip(cps, cps[1:]):
        pen += advances[left] + kern.get((left, right), 0)
        origins.append(pixel_round(pen))
    return origins


def raw_origins_gray(advances, kern, line):
    cps = [ord(c) for c in line]
    origins, pen = [0], 0.0
    for left, right in zip(cps, cps[1:]):
        pen += advances[left] + kern.get((left, right), 0)
        origins.append(pixel_round(pen))
    return origins


def site_boot():
    return json.loads((SITE / "boot.json").read_text())


class CatalogueTest(unittest.TestCase):
    def test_thirteen_cases_in_root_order(self):
        self.assertEqual(
            [c["id"] for c in CATALOGUE],
            ["roboto-8", "roboto-12", "roboto-16", "roboto-20",
             "roboto-italic-8", "roboto-italic-12",
             "roboto-italic-16", "roboto-italic-20",
             "literata-8", "literata-12", "literata-16",
             "literata-20", "rouge-script-20"])

    def test_boot_follows_catalogue(self):
        boot = site_boot()
        self.assertEqual(boot["model"], ps.MODEL)
        self.assertEqual(boot["spacing_model"], ps.SPACING_MODEL)
        self.assertEqual([c["id"] for c in boot["cases"]],
                         [c["id"] for c in CATALOGUE])
        self.assertEqual(boot["controls"]["default"],
                         {"optical": 0.0, "letter": 0})


class SourceIdentityTest(unittest.TestCase):
    def test_all_cases_source_exact_from_raw_captures(self):
        boot = site_boot()
        checked = 0
        for case in boot["cases"]:
            mono_adv, mono_kern = raw_mono_capture(
                CAPTURES / f"{case['id']}-mono.json")
            gray_adv, gray_kern = raw_gray_capture(
                CAPTURES / f"{case['id']}-gray.json")
            for line, mono_got, gray_got in zip(
                    case["profiles"]["mono"]["lines"],
                    case["profiles"]["mono"]["captured"],
                    case["profiles"]["gray"]["captured"]):
                self.assertEqual(
                    mono_got, raw_origins_mono(mono_adv, mono_kern, line),
                    f"{case['id']} mono source identity")
                self.assertEqual(
                    gray_got, raw_origins_gray(gray_adv, gray_kern, line),
                    f"{case['id']} gray source identity")
                checked += 1
        self.assertGreaterEqual(checked, 13)


class EndpointParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        capture = json.loads((CAPTURES / f"{PINNED}-mono.json").read_text())
        cls.solver = Solver(capture)
        boot = site_boot()
        case = next(c for c in boot["cases"] if c["id"] == PINNED)
        table = json.loads(
            (SITE / "data" / f"ps-{PINNED}-mono.js").read_text().split(
                "window.PS_TABLES[", 1)[1].split("] = ", 1)[1].rsplit(";", 1)[0])
        cls.pairs = table["pairs"]

    def test_strength_endpoints_match_direct_solver(self):
        for name, rec in self.pairs.items():
            direct = self.solver.pair(
                ord(name[0]), ord(name[1]),
                Controls(spacing_model=ps.SPACING_MODEL, optical=1.0))
            advance = self.solver.glyphs[ord(name[0])]["finalized_advance_px"]
            self.assertEqual(rec["advance"], advance, name)
            self.assertEqual(rec["metric"],
                             advance + direct["metric_adjustment_px"], name)
            self.assertEqual(rec["optical_adjustment"],
                             direct["optical_adjustment_px"], name)
            self.assertEqual(rec["minimum"],
                             direct["clearance_min_step_px"], name)
            self.assertEqual(rec["reason"], direct["reason"], name)

    def test_compose_matches_direct_solver_at_mid_strengths(self):
        names = sorted(self.pairs)[:40]
        for strength in (0.13, 0.5, 0.77):
            for name in names:
                direct = self.solver.pair(
                    ord(name[0]), ord(name[1]),
                    Controls(spacing_model=ps.SPACING_MODEL,
                             optical=strength))
                self.assertEqual(
                    ps.compose_step(self.pairs[name], strength),
                    self.solver.glyphs[ord(name[0])]["finalized_advance_px"]
                    + direct["automatic_adjustment_px"], f"{name}@{strength}")

    def test_zero_strength_is_exact_bypass(self):
        zero = Controls(spacing_model=ps.SPACING_MODEL, optical=0.0)
        for name, rec in self.pairs.items():
            direct = self.solver.pair(ord(name[0]), ord(name[1]), zero)
            self.assertEqual(direct["reason"], "optical_disabled", name)
            self.assertEqual(
                direct["automatic_adjustment_px"],
                direct["metric_adjustment_px"], name)
            self.assertEqual(ps.compose_step(rec, 0), rec["metric"], name)

    def test_monotone_in_endpoint_direction(self):
        strengths = [i / 100 for i in range(101)]
        for name, rec in self.pairs.items():
            steps = [ps.compose_step(rec, s) for s in strengths]
            direction = (rec["advance"] + (rec["optical_adjustment"] or rec["metric_adjustment"])
                         + 0.0) - rec["metric"]
            if rec["optical_adjustment"] is None:
                self.assertTrue(all(s == rec["metric"] for s in steps), name)
                continue
            if direction >= 0:
                self.assertTrue(
                    all(b >= a for a, b in zip(steps, steps[1:])), name)
                self.assertGreaterEqual(steps[-1], steps[0], name)
            else:
                self.assertTrue(
                    all(b <= a for a, b in zip(steps, steps[1:])), name)
                self.assertLessEqual(steps[-1], steps[0], name)

    def test_frozen_grid_matches_compose(self):
        table = json.loads(
            (SITE / "data" / f"ps-{PINNED}-mono.js").read_text().split(
                "window.PS_TABLES[", 1)[1].split("] = ", 1)[1].rsplit(";", 1)[0])
        for name, rec in self.pairs.items():
            expected = [ps.compose_step(rec, s) for s in ps.STRENGTH_GRID]
            self.assertEqual(table["grid"]["steps"][name], expected, name)


if __name__ == "__main__":
    unittest.main()
