"""Regression tests for the oriented-engine v3 sample-gallery page.

Covers the canonical root catalogue mapping (all 13 cases, order, axes,
font bytes, sample texts), both delivered profiles per case, the documented
Literata repertoire limitation, the oriented table contract (entry keys
shared with the page choice mirror), the TIE-v2 choice rule (global
minimum, then lowest step index), numeric guardrails, and a single-case
builder run into a temporary directory (model identity, table shape,
shipped table contract).
"""
import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "apps/web/scripts/landing-samples"))
import yinyangfit_interactive_v3 as v3
import generate as landing_generate

CATALOGUE = json.loads(
    (REPO / "apps/web/scripts/landing-samples/main-page.json").read_text())
CAPTURES = (REPO / "out/diagnostics/contextual-spacing/yinyangfit-interactive-v3"
            / "captures")
ASCII = "".join(chr(c) for c in range(32, 127))

ENTRY_KEYS = {"ok", "inter", "raw", "fsh", "rfsh", "both", "abst", "why",
              "fa", "co"}


class CatalogueCoverageTest(unittest.TestCase):
    def test_thirteen_cases_in_root_order(self):
        self.assertEqual(len(CATALOGUE), 13)
        self.assertEqual([c["id"] for c in CATALOGUE],
                         ["roboto-8", "roboto-12", "roboto-16", "roboto-20",
                          "roboto-italic-8", "roboto-italic-12",
                          "roboto-italic-16", "roboto-italic-20",
                          "literata-8", "literata-12", "literata-16",
                          "literata-20", "rouge-script-20"])

    def test_axes_follow_root_policy(self):
        for entry in CATALOGUE:
            if entry["family_id"] in ("roboto", "roboto-italic"):
                self.assertEqual(entry["axes"], {"wdth": 100, "wght": 400})
                self.assertEqual(entry["size_px"],
                                 int(entry["id"].rsplit("-", 1)[1]))
            elif entry["family_id"] == "literata":
                size = int(entry["id"].rsplit("-", 1)[1])
                self.assertEqual(entry["axes"], {"opsz": size, "wght": 400})
            elif entry["family_id"] == "rouge-script":
                self.assertEqual(entry["axes"], {})
                self.assertTrue(entry["font_url"].startswith("https://"))
                self.assertRegex(entry["font_sha256"], r"^[0-9a-f]{64}$")

    def test_sample_texts_canonical(self):
        DEFAULT_TEXT = landing_generate.DEFAULT_TEXT
        for entry in CATALOGUE:
            text = entry.get("text") or DEFAULT_TEXT
            self.assertTrue(text.strip())
            for ch in text:
                self.assertIn(ch, ASCII + "\n")
            if entry["id"] == "rouge-script-20":
                self.assertEqual(text, entry["text"])
                self.assertNotIn("Minimum effort", text)
            else:
                self.assertNotIn("text", entry)
                self.assertIn("Minimum effort", text)

    def test_pinned_rouge_bytes_unchanged(self):
        entry = next(c for c in CATALOGUE if c["id"] == "rouge-script-20")
        font = (REPO / "apps/web/scripts/landing-samples"
                / entry["font"]).resolve()
        self.assertTrue(font.is_file())
        self.assertEqual(hashlib.sha256(font.read_bytes()).hexdigest(),
                         entry["font_sha256"])

    def test_all_captures_exist_and_load(self):
        for entry in CATALOGUE:
            for profile in ("mono", "gray"):
                path = CAPTURES / f"{entry['id']}-{profile}.json"
                self.assertTrue(path.is_file(), f"missing {path.name}")
                dataset = v3.load_case_dataset(entry["id"], profile, CAPTURES)
                self.assertEqual(dataset["profile"], profile)
                self.assertGreater(len(dataset["cells"]), 90)

    def test_repertoire_covers_every_sample_text(self):
        from generate import DEFAULT_TEXT
        for entry in CATALOGUE:
            text = entry.get("text") or DEFAULT_TEXT
            for profile in ("mono", "gray"):
                dataset = v3.load_case_dataset(entry["id"], profile, CAPTURES)
                repertoire = set(dataset["cells"])
                for ch in text:
                    if ch != "\n":
                        self.assertIn(ord(ch), repertoire,
                                      f"{entry['id']} {profile} U+{ord(ch):04X}")

    def test_literata_backtick_limitation_documented(self):
        """Literata cannot represent the backtick scalarly, so its captures
        omit U+0060; no sample text needs it."""
        self.assertNotIn("`", landing_generate.DEFAULT_TEXT)
        for size in (8, 12, 16, 20):
            for profile in ("mono", "gray"):
                dataset = v3.load_case_dataset(f"literata-{size}", profile,
                                               CAPTURES)
                self.assertNotIn(96, set(dataset["cells"]))
        for case_id in ("roboto-16", "roboto-italic-16", "rouge-script-20"):
            dataset = v3.load_case_dataset(case_id, "mono", CAPTURES)
            self.assertIn(96, set(dataset["cells"]))


class OrientedTableContractTest(unittest.TestCase):
    """Shipped table records share the page entry contract exactly.

    The browser choice mirror reads ``entry.inter``/``entry.ok``; a table
    record with any other key shape breaks choice derivation. This pins
    the contract the page depends on.
    """

    @classmethod
    def setUpClass(cls):
        cls.dataset = v3.load_case_dataset("roboto-8", "mono", CAPTURES)
        cls.store = v3.GlyphFields(cls.dataset)

    def test_pair_curves_carry_entry_keys(self):
        table = v3.score_pair_curves(self.store, ord("o"), ord("g"))
        self.assertEqual(set(table["geo"]), ENTRY_KEYS)
        search = table["search"]
        self.assertEqual(search["policy"], v3.SEARCH_POLICY)
        self.assertTrue(search["exhaustive"])
        self.assertIsNone(search["domain_reason"])
        self.assertEqual(table["steps"],
                         list(range(search["lo"], search["hi"] + 1)))
        self.assertGreater(len(table["steps"]), 5)
        self.assertIn(table["metric"], table["steps"])
        for i, ok in enumerate(table["geo"]["ok"]):
            if ok:
                self.assertIsInstance(table["geo"]["inter"][i], float)
                self.assertGreaterEqual(table["geo"]["inter"][i], 0.0)
                self.assertLessEqual(table["geo"]["inter"][i], 128.0)
                self.assertIsNone(table["geo"]["why"][i])
            else:
                self.assertIsNone(table["geo"]["inter"][i])
                self.assertEqual(table["geo"]["why"][i],
                                 "occupied_cell_overlap")

    def test_overlap_steps_invalid_never_chosen(self):
        # 'og' at roboto-8 mono overlaps at tight steps; invalid steps
        # carry no G2 and any C* choice lands on a supported step or the
        # metric fallback.
        table = v3.score_pair_curves(self.store, ord("o"), ord("g"))
        self.assertIn(False, table["geo"]["ok"])
        for cstar in (0, 4, 16, 128):
            chosen, detail = v3.derive_choice(table, float(cstar))
            idx = table["steps"].index(chosen)
            supported = (table["geo"]["ok"][idx]
                         and not table["geo"]["abst"][idx])
            self.assertTrue(supported or
                            (detail["fallback"]
                             and chosen == table["metric"]))

    def test_tie_rule_lowest_step_index(self):
        # TIE-v2: global minimum, then lowest step index (never
        # metric-nearest). A symmetric tie around the metric picks low.
        table = {"metric": 10, "steps": [8, 9, 10, 11, 12],
                 "geo": {"ok": [True] * 5, "abst": [False] * 5,
                         "inter": [6.0, 5.0, 5.0, 5.0, 7.0]}}
        chosen, detail = v3.derive_choice(table, 5.0)
        self.assertEqual(chosen, 9)
        self.assertFalse(detail["fallback"])
        # Minimizing set within tol of m* only; far steps excluded.
        table["geo"]["inter"] = [5.0, 9.0, 9.0, 9.0, 9.0]
        self.assertEqual(v3.derive_choice(table, 0.0)[0], 8)

    def test_tie_tolerance_scales_with_minimum(self):
        # The engine tolerance is 1e-9*max(1, m*): near-ties at large G2
        # stay inside the minimizing set.
        table = {"metric": 10, "steps": [8, 9, 10, 11, 12],
                 "geo": {"ok": [True] * 5, "abst": [False] * 5,
                         "inter": [100.0, 100.0 + 5e-8, 120.0, 120.0, 120.0]}}
        self.assertEqual(v3.derive_choice(table, 0.0)[0], 8)

    def test_all_invalid_falls_back_to_metric(self):
        table = {"metric": 10, "steps": [8, 9, 10, 11, 12],
                 "geo": {"ok": [False] * 5, "abst": [False] * 5,
                         "inter": [None] * 5,
                         "why": ["occupied_cell_overlap"] * 5}}
        chosen, detail = v3.derive_choice(table, 4.0)
        self.assertEqual(chosen, 10)
        self.assertTrue(detail["fallback"])
        self.assertEqual(detail["reason"], "occupied_cell_overlap")

    def test_abstain_steps_never_win_even_at_target_zero(self):
        # Supported-but-flagged steps lose to real signal at target 0, and
        # an all-abstain curve retains Source instead of winning with 0.
        table = {"metric": 10, "steps": [8, 9, 10],
                 "geo": {"ok": [True] * 3, "abst": [True, False, True],
                         "inter": [0.0, 3.0, 0.0],
                         "why": [None] * 3}}
        chosen, detail = v3.derive_choice(table, 0.0)
        self.assertEqual(chosen, 9)
        self.assertFalse(detail["fallback"])
        table["geo"]["abst"] = [True] * 3
        chosen, detail = v3.derive_choice(table, 0.0)
        self.assertEqual(chosen, 10)
        self.assertTrue(detail["fallback"])
        self.assertEqual(detail["reason"], "no_shared_support")

    def test_target_outside_names_closest(self):
        table = {"metric": 10, "steps": [8, 9, 10],
                 "geo": {"ok": [True] * 3, "abst": [False] * 3,
                         "inter": [6.0, 7.0, 8.0],
                         "why": [None] * 3}}
        chosen, detail = v3.derive_choice(table, 128.0)
        self.assertEqual(chosen, 10)
        self.assertTrue(detail["target_outside"])
        chosen, detail = v3.derive_choice(table, 7.0)
        self.assertFalse(detail["target_outside"])

class SearchDomainTest(unittest.TestCase):
    """Geometry-derived ordered-letter domains (search-v1).

    The lower bound keeps left-to-right order from delivered ink extents
    (never advance boxes); the upper bound ends where padded field
    lattices stop overlapping. The all-pairs check runs over one dataset
    here; the full-corpus sweep runs in the implementation evidence.
    """

    @classmethod
    def setUpClass(cls):
        cls.dataset = v3.load_case_dataset("roboto-16", "mono", CAPTURES)

    def test_lower_bound_uses_ink_not_advance(self):
        # Hand-computed from the capture cells: lo is the left ink minimum
        # minus the right ink maximum at step zero, floored, intersected
        # with strictly forward pen order (step >= 1).
        left, right = ord("A"), ord("V")
        bounds, reason = v3.search_domain(self.dataset, left, right, 24)
        self.assertIsNone(reason)
        lo, hi = bounds
        cells = self.dataset["cells"]
        ink_min = min(math.trunc(cells[left]["left"]) + col
                      for row in range(cells[left]["height"])
                      for col in range(cells[left]["width"])
                      if cells[left]["cover"][row * cells[left]["width"] + col] > 0.0)
        ink_max = max(math.trunc(cells[right]["left"]) + col
                      for row in range(cells[right]["height"])
                      for col in range(cells[right]["width"])
                      if cells[right]["cover"][row * cells[right]["width"] + col] > 0.0)
        self.assertEqual(lo, max(math.floor(ink_min - ink_max), 1))
        self.assertGreater(hi, lo)

    def test_forward_pen_order_for_every_pair(self):
        # LTR layout admissibility: no domain admits a backward or equal
        # origin move, whatever the italic bearings.
        cells = self.dataset["cells"]
        checked = 0
        for left in cells:
            for right in cells:
                if left == 32 or right == 32:
                    continue
                bounds, _ = v3.search_domain(self.dataset, left, right, 24)
                self.assertIsNotNone(bounds)
                self.assertGreaterEqual(bounds[0], 1)
                self.assertGreaterEqual(bounds[1], bounds[0])
                checked += 1
        self.assertGreater(checked, 8000)

    def test_metric_inside_domain_for_every_pair(self):
        import yinyangfit_interactive as yy
        cells = self.dataset["cells"]
        checked = 0
        for left in cells:
            for right in cells:
                if left == 32 or right == 32:
                    continue
                bounds, _ = v3.search_domain(self.dataset, left, right, 24)
                self.assertIsNotNone(bounds)
                metric = yy.metric_step(self.dataset, left, right)
                self.assertLessEqual(bounds[0], metric)
                self.assertGreaterEqual(bounds[1], metric)
                checked += 1
        self.assertGreater(checked, 8000)

    def test_fractional_field_origins_match_the_scorer(self):
        dataset = {"cells": {
            65: {"width": 2, "height": 2, "left": 0.5, "top": 0.5,
                 "cover": [1.0, 0.0, 0.0, 0.0]},
            66: {"width": 2, "height": 2, "left": -1.5, "top": -1.5,
                 "cover": [1.0, 0.0, 0.0, 0.0]}}}
        bounds, reason = v3.search_domain(dataset, 65, 66, 24)
        self.assertIsNone(reason)
        expected_hi = math.trunc(0.5 - 24) + 50 - 1 - math.trunc(-1.5 - 24)
        self.assertEqual(bounds, (1, expected_hi))

    def test_synthetic_blank_and_disjoint_yield_no_domain(self):
        dataset = {"cells": {
            65: {"width": 2, "height": 2, "left": 0.0, "top": 0.0,
                 "cover": [1.0, 0.0, 0.0, 0.0]},
            66: {"width": 2, "height": 2, "left": 5.0, "top": 0.0,
                 "cover": [0.0, 0.0, 0.0, 0.0]},
            67: {"width": 2, "height": 2, "left": 5.0, "top": 200.0,
                 "cover": [1.0, 0.0, 0.0, 0.0]},
            68: {"width": 2, "height": 2, "left": 200.0, "top": 0.0,
                 "cover": [0.0, 1.0, 0.0, 0.0]}}}
        bounds, reason = v3.search_domain(dataset, 65, 66, 24)
        self.assertIsNone(bounds)
        self.assertEqual(reason, "blank_glyph_no_ink")
        bounds, reason = v3.search_domain(dataset, 65, 67, 24)
        self.assertIsNone(bounds)
        self.assertEqual(reason, "row_bands_disjoint")
        # X-disjoint padded lattices: support ends before the pen can
        # advance, so there is no forward step either.
        bounds, reason = v3.search_domain(dataset, 65, 68, 24)
        self.assertIsNone(bounds)
        self.assertEqual(reason, "no_forward_step")


class LinePitchTest(unittest.TestCase):
    """Stacked-line leading is display-only: one general 1.25em rule
    rounded up, shared by every view; scorer gaps stay per-line."""

    def test_pitch_is_ceil_quarter_em(self):
        for size in (8, 12, 16, 20):
            dataset = v3.load_case_dataset(f"roboto-{size}", "mono", CAPTURES)
            store = v3.GlyphFields(dataset)
            tables = {name: v3.score_pair_curves(store, ord(name[0]),
                                                ord(name[1]))
                      for name in ("AV", "To")}
            pitch, experiment, captured = v3.line_layouts(
                dataset, tables, "AV\nTo", 4.0)
            self.assertEqual(pitch, math.ceil(1.25 * size))
            self.assertEqual(len(experiment), 2)
            self.assertEqual(len(captured), 2)


CLASSL_ENTRY_KEYS = {"ok", "gl", "both", "abst", "why", "areason",
                         "weak", "skip", "short", "bound", "fa", "co"}


class BuiltSiteTest(unittest.TestCase):
    """A single-case builder run carries the Class-L model identity and
    the page entry contract end to end."""

    def test_single_case_build_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            import subprocess
            proc = subprocess.run(
                [sys.executable,
                 str(Path(__file__).resolve().parents[1]
                     / "yinyangfit_interactive_v3.py"),
                 str(out), "--only", "roboto-8"],
                capture_output=True, text=True, cwd=str(REPO))
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
            boot = json.loads((out / "boot.json").read_text())
            self.assertEqual(boot["model"], "yinyangfit-oriented-engine-v1")
            self.assertEqual(boot["score_model"],
                             "yinyangfit-local-energy-v2")
            self.assertEqual(boot["settings_version"],
                             "v3-settings-2026-11-05-classl")
            self.assertEqual(boot["default_setting"],
                             {"target": 8.0, "reach": 12, "falloff": 2.0})
            self.assertEqual(boot["fast_geometry"],
                             {"reach": 12.0, "falloff": 2.0})
            self.assertEqual(len(boot["cases"]), 1)
            import re
            raw = (out / "data" / "roboto-8-mono.js").read_text()
            table = json.loads(re.search(
                r"window\.YY_TABLES\[.*?\] = (\{.*\});\s*$", raw, re.S
            ).group(1))
            self.assertEqual(table["score_model"],
                             "yinyangfit-local-energy-v2")
            self.assertEqual(set(table["pairs"]["og"]["geo"]),
                             CLASSL_ENTRY_KEYS)
            spot = table["spot"]
            self.assertEqual(spot["default_target"], 8.0)
            for name, choices in spot["pinned"].items():
                self.assertEqual(len(choices), len(spot["target_grid"]))
                for target, chosen in zip(spot["target_grid"], choices):
                    short = {k: table["pairs"][name][k] for k in
                             ("metric", "steps", "search", "geo")}
                    self.assertEqual(
                        chosen,
                        v3.derive_choice_classl(
                            short, float(target))[0])


class FontSourceGuardTest(unittest.TestCase):
    """The builder must reject a selected font the capture was not made from.

    build_case records both the selected font hash and each capture's
    recorded source hash; accepting a mismatch bakes silent drift into the
    next regeneration, so the comparison has to happen after loading the
    capture but before building any geometry.
    """
    @classmethod
    def setUpClass(cls):
        cls.cases_parent = REPO / "apps/web/scripts/landing-samples"

    def test_mismatched_selected_font_rejected(self):
        """In-memory roboto-16 entry pointed at the existing literata file."""
        literata = next(c for c in CATALOGUE if c["id"] == "literata-16")
        literata_font = (self.cases_parent / literata["font"]).resolve()
        self.assertTrue(literata_font.is_file())
        original = next(c for c in CATALOGUE if c["id"] == "roboto-16")
        entry = dict(original)
        entry["font"] = str(literata_font)
        with self.assertRaises(ValueError) as ctx:
            v3.build_case(entry, CAPTURES, self.cases_parent)
        self.assertIn("roboto-16", str(ctx.exception))
        # Originals untouched: catalogue, captures and font files unmodified.
        self.assertEqual(next(
            c for c in CATALOGUE if c["id"] == "roboto-16"), original)
        self.assertIn("source_sha256", json.loads(
            (CAPTURES / "roboto-16-mono.json").read_text()))
        self.assertIn("source_sha256", json.loads(
            (CAPTURES / "roboto-16-gray.json").read_text())["font"])

    def test_missing_capture_source_identity_rejected(self):
        """A capture stripped of its recorded source hash cannot build."""
        import shutil
        tmp = Path(tempfile.mkdtemp(
            dir=REPO / "out/diagnostics/contextual-spacing"
            / "yinyang-full-window/review-fixes",
            prefix="fixtures-captures-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        for profile in ("mono", "gray"):
            src = CAPTURES / f"roboto-8-{profile}.json"
            capture = json.loads(src.read_text())
            if profile == "mono":
                self.assertIn("source_sha256", capture)
                del capture["source_sha256"]
            else:
                self.assertIn("source_sha256", capture["font"])
                del capture["font"]["source_sha256"]
            (tmp / src.name).write_text(json.dumps(capture))
        entry = next(c for c in CATALOGUE if c["id"] == "roboto-8")
        with self.assertRaises(ValueError) as ctx:
            v3.build_case(entry, tmp, self.cases_parent)
        self.assertIn("roboto-8", str(ctx.exception))


class SourceCatalogueTest(unittest.TestCase):
    """The frozen source catalogue is pinned, reproducible, and complete.

    The builder reads generated pages for nothing; every catalogue field
    derives from captures plus the root catalogue plus fonts. Regenerating
    must reproduce the frozen bytes exactly, or the pin is meaningless.
    """

    @classmethod
    def setUpClass(cls):
        cls.cases_parent = REPO / "apps/web/scripts/landing-samples"
        cls.frozen = v3.SOURCE_SITE / "catalogue.json"

    def test_pin_matches_frozen_file(self):
        text = self.frozen.read_text()
        self.assertEqual(v3.sha_bytes(text.encode()),
                         v3.SOURCE_CATALOGUE_SHA)
        source = json.loads(text)
        self.assertEqual(source.get("format"), v3.SOURCE_FORMAT)
        self.assertEqual(len(source["cases"]), 13)

    def test_regeneration_byte_identical(self):
        entries = json.loads(
            (self.cases_parent / "main-page.json").read_text())
        fresh = v3.build_source_catalogue(entries, CAPTURES,
                                          self.cases_parent)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "catalogue.json"
            out.write_text(v3.dump_source_catalogue(fresh))
            self.assertEqual(out.read_bytes(), self.frozen.read_bytes())

    def test_source_covers_all_cases_and_profiles(self):
        source = json.loads(self.frozen.read_text())
        self.assertEqual([c["id"] for c in source["cases"]],
                         [c["id"] for c in CATALOGUE])
        for case in source["cases"]:
            self.assertEqual(case["line_pitch"],
                             math.ceil(1.25 * case["size_px"]))
            for profile in ("mono", "gray"):
                prof = case["profiles"][profile]
                self.assertTrue(prof["glyphs"], f"{case['id']} {profile}")
                self.assertTrue(prof["lines"])
                self.assertTrue(prof["captured"])
                self.assertTrue(prof["advances"])
                self.assertTrue(prof["space_metrics"])
                self.assertTrue((REPO / prof["capture"]).is_file())
                self.assertRegex(prof["capture_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(prof["source_sha256"], r"^[0-9a-f]{64}$")


class SourceGuardTest(unittest.TestCase):
    """Stale or tampered source inputs are refused before any geometry.

    A G2-era curve without a Class-L identity, a catalogue with drifted
    capture bytes, a missing font, or a source-hash mismatch must all
    fail closed; only exact model/params/capture/domain identities build.
    """

    @classmethod
    def setUpClass(cls):
        cls.cases_parent = REPO / "apps/web/scripts/landing-samples"
        cls.source = json.loads(
            (v3.SOURCE_SITE / "catalogue.json").read_text())
        cls.fontmap = {e["id"]: e.get("font") for e in CATALOGUE}

    def _case(self, case_id):
        return json.loads(json.dumps(next(
            c for c in self.source["cases"] if c["id"] == case_id)))

    def test_stale_g2_curve_identity_rejected(self):
        real = json.loads(
            (v3.CURVES / "roboto-8-mono.json").read_text())
        stale = dict(real)
        del stale["engine_version"]
        wrong_model = dict(real)
        wrong_model["engine_version"] = dict(
            real["engine_version"], score_model="yinyangfit-g2-oracle")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_curves = Path(tmp) / "curves"
            tmp_curves.mkdir()
            work = Path(tmp) / "work"
            work.mkdir()
            for name, curve in (("stale", stale),
                                ("wrong-model", wrong_model)):
                (tmp_curves / "roboto-8-mono.json").write_text(
                    json.dumps(curve))
                saved, v3.CURVES = v3.CURVES, tmp_curves
                try:
                    with self.assertRaises(ValueError, msg=name) as ctx:
                        v3.build_dataset_tables(
                            self.source,
                            v3.SOURCE_SITE / "catalogue.json",
                            "roboto-8-mono", "roboto-8", "mono", work)
                finally:
                    v3.CURVES = saved
                self.assertIn("drift", str(ctx.exception))

    def test_missing_curve_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            saved, v3.CURVES = v3.CURVES, Path(tmp)
            try:
                with self.assertRaises(ValueError) as ctx:
                    v3.build_dataset_tables(
                        self.source,
                        v3.SOURCE_SITE / "catalogue.json",
                        "roboto-8-mono", "roboto-8", "mono", work)
            finally:
                v3.CURVES = saved
            self.assertIn("missing curve", str(ctx.exception))

    def test_capture_content_drift_rejected(self):
        case = self._case("roboto-16")
        case["profiles"]["mono"]["capture_sha256"] = "0" * 64
        with self.assertRaises(ValueError) as ctx:
            v3.verify_case_fonts(
                case, self.fontmap["roboto-16"], self.cases_parent)
        self.assertIn("capture content", str(ctx.exception))

    def test_mismatched_capture_source_rejected(self):
        case = self._case("roboto-16")
        case["profiles"]["mono"]["source_sha256"] = "0" * 64
        with self.assertRaises(ValueError) as ctx:
            v3.verify_case_fonts(
                case, self.fontmap["roboto-16"], self.cases_parent)
        self.assertIn("capture source", str(ctx.exception))

    def test_missing_font_rejected(self):
        case = self._case("roboto-16")
        case["font_file"] = "NoSuchFont-000.ttf"
        with self.assertRaises(ValueError) as ctx:
            v3.verify_case_fonts(case, None, self.cases_parent)
        self.assertIn("missing font", str(ctx.exception))


class RebundleTest(unittest.TestCase):
    """`--rebundle` re-embeds owner sources without touching boot/tables.

    Deterministic across runs, boot payload byte-stable, foreign boot
    identities refused. Covers display-only page updates that must not
    trigger a full table rebuild.
    """

    def _run(self, main_dir, *extra):
        import subprocess
        return subprocess.run(
            [sys.executable,
             str(Path(__file__).resolve().parents[1]
                 / "yinyangfit_interactive_v3.py"),
             *extra, "--rebundle", str(main_dir)],
            capture_output=True, text=True, cwd=str(REPO))

    def test_rebundle_deterministic_and_boot_stable(self):
        import shutil
        live = (REPO / "out/diagnostics/contextual-spacing"
                / "yinyangfit-interactive-v3/site-reviewed")
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "main"
            site.mkdir()
            for name in ("boot.json", "manifest.json"):
                shutil.copyfile(live / name, site / name)
            boot_before = (site / "boot.json").read_bytes()
            pages = []
            for _ in ("first", "second", "third"):
                proc = self._run(site)
                self.assertEqual(proc.returncode, 0,
                                 proc.stderr[-2000:])
                pages.append((site / "index.html").read_bytes())
            self.assertEqual(pages[1], pages[0])
            self.assertEqual(pages[2], pages[0])
            first = pages[0]
            text = first.decode()
            payload = json.loads(text.split(
                '<script type="application/json" id="yy-boot">\n'
            )[1].split("\n</script>")[0])
            self.assertEqual(
                payload, json.loads((site / "boot.json").read_text()))
            self.assertEqual((site / "boot.json").read_bytes(), boot_before)
            manifest = json.loads((site / "manifest.json").read_text())
            self.assertEqual(manifest["page_bytes"], len(first))

    def test_rebundle_refuses_foreign_boot(self):
        live = (REPO / "out/diagnostics/contextual-spacing"
                / "yinyangfit-interactive-v3/site-reviewed")
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "main"
            site.mkdir()
            boot = json.loads((live / "boot.json").read_text())
            boot["score_model"] = "foreign-model"
            (site / "boot.json").write_text(json.dumps(boot))
            (site / "manifest.json").write_text(
                (live / "manifest.json").read_text())
            proc = self._run(site)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse((site / "index.html").exists())


class SourceSiteRebuildTest(unittest.TestCase):
    """The builder ignores generated pages and reproduces its outputs.

    A source-site copy carrying mutated page decoys still builds (no
    page-checksum gating), two builds from the same valid catalogue are
    identical, and the tables match the existing consolidated leaf.
    """

    def _records(self, path):
        import re
        raw = path.read_text()
        table = json.loads(re.search(
            r"window\.YY_TABLES\[.*?\] = (\{.*\});\s*$", raw, re.S
        ).group(1))
        table.pop("seconds", None)
        return table

    def test_build_twice_with_changed_page_decoy(self):
        import shutil
        import subprocess
        leaf = (REPO / "out/diagnostics/contextual-spacing"
                / "yinyang-normalization-repair"
                / "page-staging-consolidated")
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "source-site"
            site.mkdir()
            shutil.copyfile(v3.SOURCE_SITE / "catalogue.json",
                            site / "catalogue.json")
            (site / "index.html").write_text(
                "<html>mutated generated page decoy</html>")
            (site / "boot.json").write_text('{"mutated": true}')
            outs = []
            for i in ("a", "b"):
                out = Path(tmp) / f"site-{i}"
                proc = subprocess.run(
                    [sys.executable,
                     str(Path(__file__).resolve().parents[1]
                         / "yinyangfit_interactive_v3.py"),
                     str(out), "--only", "roboto-8",
                     "--source-site", str(site)],
                    capture_output=True, text=True, cwd=str(REPO))
                self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
                outs.append(out)
            for name in ("boot.json", "index.html", "manifest.json",
                         "PROVENANCE.md"):
                self.assertEqual((outs[0] / name).read_bytes(),
                                 (outs[1] / name).read_bytes(),
                                 f"{name} reproduces")
            for data in ("roboto-8-mono.js", "roboto-8-gray.js"):
                self.assertEqual(
                    self._records(outs[0] / "data" / data),
                    self._records(outs[1] / "data" / data),
                    f"{data} reproduces")
                if leaf.exists():
                    self.assertEqual(
                        self._records(outs[0] / "data" / data),
                        self._records(leaf / "data" / data),
                        f"{data} matches consolidated leaf")


if __name__ == "__main__":
    unittest.main()
