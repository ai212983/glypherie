"""Focused tests for audit_native_font_coverage (small fixtures, mocks)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import audit_native_font_coverage as A

TRI = [[0, 0], [500, 0], [250, 500]]


def _graph(points, extra=()):
    cons = []
    cid = 0

    def add(kind, p, n, sources=(), value=None, **kw):
        nonlocal cid
        cons.append({"kind": kind, "point": p, "normal": list(n),
                     "sources": list(sources),
                     "value": float(value) if value is not None else 0.0,
                     "id": cid, **kw})
        cid += 1

    pts = np.asarray(points, float)
    for p in range(len(pts)):
        add("Abs", p, [1, 0], value=float(pts[p][0]), round=False)
        add("Abs", p, [0, 1], value=float(pts[p][1]), round=False)
    cons.extend(extra)
    return {"constraints": cons, "order": list(range(len(pts))),
            "rejected": [],
            "baseline_execution": {
                "native_points_px": (pts * 14 / 1000).tolist()}}


def _fixture_font(path, chars="AB"):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    b = FontBuilder(1000, isTTF=True)
    order = [".notdef"] + list(chars)
    b.setupGlyphOrder(order)
    b.setupCharacterMap({ord(c): c for c in chars})
    glyphs = {}
    for c in chars:
        pen = TTGlyphPen(None)
        pen.moveTo(tuple(TRI[0]))
        for p in TRI[1:]:
            pen.lineTo(tuple(p))
        pen.closePath()
        glyphs[c] = pen.glyph()
    glyphs[".notdef"] = TTGlyphPen(None).glyph()
    b.setupGlyf(glyphs)
    b.setupHorizontalMetrics({c: (600, 0) for c in order})
    b.setupHorizontalHeader(ascent=800, descent=-200)
    b.setupNameTable({"familyName": "T", "styleName": "R",
                      "uniqueFontIdentifier": "T",
                      "fullName": "T R", "psName": "T-R"})
    b.setupOS2(sTypoAscender=800, sTypoDescender=-200,
               usWinAscent=800, usWinDescent=200)
    b.setupPost()
    b.setupMaxp()
    b.save(path)


def _fresh_output(testcase):
    # Pipeline requires output under tools/font_probe/out; use a unique
    # tempdir there (never a fixed name) and create out/ if missing.
    base = A.HERE / "out"
    base.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(dir=base, prefix="native-audit-test-"))
    testcase.addCleanup(shutil.rmtree, out, True)
    return out


class ParamTests(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(A._classify_param(5), "integer")
        self.assertEqual(A._classify_param(5.5), "fractional")
        self.assertEqual(A._classify_param(40000), "out-of-signed16")
        self.assertEqual(A._classify_param(float("nan")), "non-finite")
        self.assertEqual(A._classify_param("x"), "non-numeric")

    def test_inventory_origins(self):
        g = _graph(TRI)
        g["constraints"][0].update(feature="seg-1", metric=True,
                                   metric_role="baseline")
        g["constraints"][1].update(default=True, default_reason="cycle")
        inv = A._inventory(g, TRI)
        self.assertEqual(sum(inv["kinds"].values()), len(g["constraints"]))
        self.assertEqual(inv["origins"]["metric:True"], 1)
        self.assertEqual(inv["origins"]["default:True"], 1)
        self.assertEqual(inv["origins"]["feature:True"], 1)

    def test_enrich_detail(self):
        g = _graph(TRI)
        inv = A._inventory(g, TRI)
        d = A._enrich({"point": 0, "constraint_id": 0, "reason": "r"},
                      inv["_by_id"], TRI)
        self.assertEqual(d["kind"], "Abs")
        self.assertEqual(d["value"], 0.0)
        self.assertIn("expected_projection", d)
        self.assertIn("origin", d)

    def test_stable_reason_buckets_numeric_dots(self):
        r1 = "singular or too-small native dot (ideal 0.01234 < 1/16)"
        r2 = "encoded normalized dot 0.05678 < 1/16 (F2.14 quantization)"
        r3 = "point normals are not independent (determinant 1e-09)"
        self.assertEqual(A._stable_reason(r1), A.NEAR_PERPENDICULAR)
        self.assertEqual(A._stable_reason(r2), A.NEAR_PERPENDICULAR)
        self.assertEqual(A._stable_reason(r3), A.NEAR_PERPENDICULAR)
        self.assertEqual(A._stable_reason("Abs value must equal original projection"),
                         "Abs value must equal original projection")

    def test_check_shapes_rejects_mismatch(self):
        with self.assertRaises(ValueError):
            A._check_shapes([[1, 2]], [[1, 2], [3, 4]], "case")
        A._check_shapes([[1, 2]], [[1.0, 2.0]], "case")


class GateTests(unittest.TestCase):
    def test_malformed(self):
        with self.assertRaises(ValueError):
            A._validate(["nope"], [14])
        with self.assertRaises(ValueError):
            A._validate(["roboto"], [0])
        with self.assertRaises(ValueError):
            A._validate([], [14])

    def test_fresh_output_gate(self):
        out = _fresh_output(self) / "run"
        out.mkdir()
        (out / "old.txt").write_text("x")
        with self.assertRaises(ValueError):
            A.run(out, families=["roboto"], sizes=[14])

    def test_cli_nonzero_when_incomplete(self):
        with mock.patch.object(A, "run",
                               return_value={"audit_complete": False}):
            with self.assertRaises(SystemExit):
                A.main(["--output", "somewhere",
                        "--families", "roboto", "--sizes", "14"])


class NativeFixtureTests(unittest.TestCase):
    def test_accepted_preserves_contours(self):
        from shamir_native_translation import compile_native
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            base = tmp / "base.ttf"
            _fixture_font(base, "A")
            pts = np.asarray(TRI, float)
            asm, meta = compile_native(_graph(TRI), pts)
            out = tmp / "cases" / "n.ttf"
            out.parent.mkdir()
            A._build_native_font(base, out, "A", asm, list(meta.get("cvt", [])))
            raw, px = A._run_ft_strict(out, "A", 14)
            self.assertEqual(len(raw), len(TRI))
            self.assertTrue(all(np.isfinite(v) for p in px for v in p))

    def test_fractional_pdist_rejected(self):
        from shamir_native_translation import UnsupportedNativeTranslation
        import shamir_native_translation as N
        pts = np.asarray(TRI, float)
        bad = {"kind": "PDist", "point": 0, "normal": [1, 0],
               "sources": [1], "value": 3.5, "id": 999,
               "feature": "seg-9"}
        g = _graph(TRI, extra=[bad])
        # replace one Abs on point 0 with the fractional PDist (keep 2/point)
        g["constraints"] = [c for c in g["constraints"]
                            if not (c["point"] == 0 and c["id"] == 0)]
        g["order"] = [1, 0, 2]
        with self.assertRaises(UnsupportedNativeTranslation) as ctx:
            N.compile_native(g, pts)
        reasons = [d["reason"] for d in ctx.exception.diagnostics]
        self.assertTrue(any("integer" in r for r in reasons))


class DirectTests(unittest.TestCase):
    def _build_all_direct(self, static, target, chars, **kw):
        _fixture_font(target, "AB")
        return {"records": {"A": {"graph": _graph(TRI)},
                            "B": {"graph": _graph(TRI)}}}

    def test_direct_run_records_lowering_and_domain(self):
        # Opt-in direct audit on small fixtures: integer Abs/Abs pairs
        # lower direct, the declared domain holds post-execution, and the
        # report carries the lowering evidence.
        out = _fresh_output(self)
        target = out / "run"
        with mock.patch.object(A, "CHARS", "AB"), mock.patch.object(
                A, "build_font", side_effect=self._build_all_direct):
            rep = A.run(target, families=["roboto"], sizes=[14],
                        allow_direct=True)
        self.assertTrue(rep["config"]["allow_direct"])
        self.assertTrue(rep["audit_complete"], rep["failures"])
        self.assertEqual(rep["direct"]["cases"], 2)
        self.assertEqual(rep["direct"]["points"], 6)
        self.assertEqual(rep["direct"]["domain_exceeded"], 0)
        self.assertEqual(rep["direct"]["skip_reasons"], {})
        by_char = {c["char"]: c for b in rep["builds"]
                   if isinstance(b, dict) and "cases" in b
                   for c in b["cases"]}
        self.assertEqual(by_char["A"]["lowering"], [0, 1, 2])
        self.assertEqual(by_char["B"]["lowering"], [0, 1, 2])
        self.assertFalse(by_char["A"]["domain_exceeded"])

    def test_direct_domain_helper_and_reason_bucket(self):
        d = A._direct_domain_for_case(
            [[100.0, -200.0]], {"constraints": [{"value": 200}]}, 1000, 14)
        self.assertEqual(d, (180 + 512, 45876))
        self.assertEqual(
            A._stable_reason(
                "non-integer font-unit scalar 1.5 (exact CVT contract)"),
            "non-integer scalar (exact CVT contract)")


class RunTests(unittest.TestCase):
    def _run_small(self, build_side_effect):
        out = _fresh_output(self)
        target = out / "run"
        with mock.patch.object(A, "CHARS", "AB"), mock.patch.object(
                A, "build_font", side_effect=build_side_effect):
            return A.run(target, families=["roboto"], sizes=[14]), target

    def _build_mixed(self, static, target, chars, **kw):
        _fixture_font(target, "AB")
        pts = np.asarray(TRI, float)
        bad = {"kind": "PDist", "point": 0, "normal": [1, 0],
               "sources": [1], "value": 3.5, "id": 999,
               "feature": "seg-9"}
        gb = _graph(TRI, extra=[bad])
        gb["constraints"] = [c for c in gb["constraints"]
                             if not (c["point"] == 0 and c["id"] == 0)]
        gb["order"] = [1, 0, 2]
        return {"records": {"A": {"graph": _graph(TRI)},
                            "B": {"graph": gb}}}

    def test_mixed_supported_unsupported(self):
        rep, out = self._run_small(self._build_mixed)
        self.assertEqual(rep["counts"]["total"], 2)
        self.assertEqual(rep["counts"]["supported"], 1)
        self.assertEqual(rep["counts"]["unsupported"], 1)
        self.assertEqual(rep["counts"]["unexpected"], 0)
        self.assertEqual(rep["counts"]["executed"], 1)
        self.assertTrue(rep["audit_complete"])
        n_reasons = len(rep["reason_relations"])
        self.assertGreaterEqual(n_reasons, 1)
        # distinct relation count >= glyph-case count per reason
        for r, n in rep["reason_cases"].items():
            self.assertGreaterEqual(rep["reason_relations"][r], n)
        # P-kind parameter classes are tracked separately from all values
        self.assertIn("PDist", rep["parameter_classes_by_kind"])
        self.assertGreaterEqual(
            sum(rep["parameter_classes_total"].values()), 1)
        # unsupported glyph has NO fallback native result
        report = json.loads(
            (out / "native-font-coverage-report.json").read_text())
        by_char = {c["char"]: c for b in rep["builds"]
                   if isinstance(b, dict) and "cases" in b
                   for c in b["cases"]}
        self.assertIn("A", by_char)
        self.assertIsNotNone(by_char["A"]["native"])
        self.assertIsNone(by_char["B"]["native"])
        self.assertTrue(by_char["B"]["diagnostics"])
        self.assertEqual(by_char["B"]["result"], "unsupported")
        self.assertFalse(by_char["B"]["compiler_supported"])
        self.assertEqual(report["counts"]["unsupported"], 1)
        # disjoint per-family and per-build tallies
        fam = rep["family_counts"]["roboto"]
        self.assertEqual(
            fam["supported"] + fam["unsupported"] + fam["unexpected"],
            fam["total"])
        build = rep["builds"][0]
        self.assertEqual(build["total"], 2)
        self.assertEqual(build["supported"], 1)
        self.assertEqual(build["unsupported"], 1)
        self.assertEqual(build["unexpected"], 0)
        self.assertEqual(build["executed"], 1)
        # successful-case coordinate summary present
        self.assertEqual(
            rep["native_match"]["exact"]
            + rep["native_match"]["different"], 1)

    def test_build_failure_persisted(self):
        def boom(*a, **k):
            raise RuntimeError("injected build failure")
        out = _fresh_output(self)
        target = out / "run"
        with mock.patch.object(A, "CHARS", "AB"), mock.patch.object(
                A, "build_font", side_effect=boom):
            rep = A.run(target, families=["roboto"], sizes=[14])
        self.assertEqual(rep["counts"]["total"], 2)
        self.assertEqual(rep["counts"]["unexpected"], 2)
        self.assertEqual(rep["counts"]["supported"], 0)
        self.assertEqual(rep["counts"]["unsupported"], 0)
        self.assertFalse(rep["audit_complete"])
        self.assertTrue(rep["failures"])
        fam = rep["family_counts"]["roboto"]
        self.assertEqual(fam["total"], 2)
        self.assertEqual(fam["unexpected"], 2)
        build = rep["builds"][0]
        self.assertTrue(build["build_error"])
        self.assertEqual(build["unexpected"], 2)
        self.assertEqual(build["total"], 2)

    def test_execution_failure_unexpected_keeps_inventory(self):
        with mock.patch.object(
                A, "_run_ft_strict",
                side_effect=RuntimeError("injected execution failure")):
            rep, _ = self._run_small(self._build_mixed)
        self.assertEqual(rep["counts"]["supported"], 0)
        self.assertEqual(rep["counts"]["unsupported"], 1)
        self.assertEqual(rep["counts"]["unexpected"], 1)
        self.assertEqual(rep["counts"]["executed"], 0)
        self.assertFalse(rep["audit_complete"])
        by_char = {c["char"]: c for b in rep["builds"]
                   if isinstance(b, dict) and "cases" in b
                   for c in b["cases"]}
        # accepted-then-failed case keeps inventory, diagnostics slot,
        # compiler verdict, and stage while categorized unexpected
        failed = by_char["A"]
        self.assertEqual(failed["result"], "unexpected")
        self.assertTrue(failed["compiler_supported"])
        self.assertEqual(failed["stage"], "execution")
        self.assertIsNotNone(failed["relations"])
        self.assertIsNone(failed["native"])
        fam = rep["family_counts"]["roboto"]
        self.assertEqual(fam["unexpected"], 1)
        self.assertEqual(fam["total"], 2)


def _blank_fixture_font(path, char="B", advance=600, lsb=50):
    """Real fixture: blank glyph (no contours) with nonzero advance and lsb."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    b = FontBuilder(1000, isTTF=True)
    order = [".notdef", char]
    b.setupGlyphOrder(order)
    b.setupCharacterMap({ord(char): char})
    glyphs = {char: TTGlyphPen(None).glyph(),
              ".notdef": TTGlyphPen(None).glyph()}
    b.setupGlyf(glyphs)
    b.setupHorizontalMetrics({c: (advance if c == char else 600,
                                 lsb if c == char else 0) for c in order})
    b.setupHorizontalHeader(ascent=800, descent=-200)
    b.setupNameTable({"familyName": "T", "styleName": "R",
                      "uniqueFontIdentifier": "T",
                      "fullName": "T R", "psName": "T-R"})
    b.setupOS2(sTypoAscender=800, sTypoDescender=-200,
               usWinAscent=800, usWinDescent=200)
    b.setupPost()
    b.setupMaxp()
    b.save(path)


def _empty_graph():
    return {"constraints": [], "order": [],
            "rejected": [],
            "baseline_execution": {"native_points_px": []}}


class EmptyOutlineTests(unittest.TestCase):
    def test_blank_glyph_nonzero_spacing_survives_strict_ft(self):
        from shamir_native_translation import compile_native
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            base = tmp / "base.ttf"
            _blank_fixture_font(base, "B", advance=600, lsb=50)
            asm, meta = compile_native(_empty_graph(), [])
            self.assertEqual(asm, [])
            self.assertEqual(list(meta.get("cvt", [])), [])
            self.assertEqual(list(meta.get("operations", [])), [])
            self.assertTrue(meta.get("empty_outline"))
            out = tmp / "cases" / "n.ttf"
            out.parent.mkdir()
            orig = A._build_native_font(
                base, out, "B", asm, list(meta.get("cvt", [])))
            # Serialization preserves the blank outline and hmtx spacing.
            self.assertEqual(orig["coords"], [])
            self.assertEqual(orig["end_pts"], [])
            self.assertEqual(list(orig["advance"]), [600, 50])
            self.assertNotEqual(orig["advance"][0], 0)
            self.assertNotEqual(orig["advance"][1], 0)
            raw, px = A._run_ft_strict(out, "B", 14)
            self.assertEqual(raw, [])
            self.assertEqual(px, [])
            evidence = A._verify_empty_noop(out, base, "B", 14, orig,
                                            "blank-case")
            self.assertTrue(evidence["bitmap"]["all_zero"])
            self.assertEqual(evidence["advance_native"],
                             evidence["advance_baseline"])
            self.assertNotEqual(evidence["advance_native"][0], 0)
            self.assertEqual(evidence["hmtx"], [600, 50])

    def test_check_shapes_empty_acceptance(self):
        got, exp = A._check_shapes([], [], "case")
        self.assertEqual(got.shape, (0, 2))
        self.assertEqual(exp.shape, (0, 2))
        # Zero-point diagnostic equality: no differences, zero delta.
        exp_raw = np.rint(exp * 64).astype(np.int64)
        diff = int((np.rint(got).astype(np.int64)
                    != exp_raw).any(axis=1).sum())
        self.assertEqual(diff, 0)
        # Malformed arrays stay rejected.
        for bad in (np.zeros((0, 3)), np.zeros((2, 0)), None,
                    [[0, 0], [1]]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                A._check_shapes(bad, [], "case")
            with self.assertRaises(ValueError, msg=repr(bad)):
                A._check_shapes([], bad, "case")


if __name__ == "__main__":
    unittest.main()
