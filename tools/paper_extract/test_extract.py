"""Regression checks for OCR provenance and rejection of broken native decoding."""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from docling_core.types.doc import BoundingBox, CoordOrigin, ProvenanceItem, TextItem, ListItem, DocItemLabel
import extract
from extract import ocr_fragments, review_status, validate_text


class ExtractionTests(unittest.TestCase):
    def test_merged_ocr_paragraph_retains_only_each_pages_characters(self):
        item = TextItem(
            self_ref="#/texts/0", label=DocItemLabel.TEXT,
            text="End of first page. Start of second page.", orig="End of first page. Start of second page.",
            prov=[ProvenanceItem(page_no=page, charspan=span,
                                 bbox=BoundingBox(l=0, t=1, r=1, b=0, coord_origin=CoordOrigin.BOTTOMLEFT))
                  for page, span in [(1, (0, 18)), (2, (19, 40))]],
        )
        self.assertEqual(ocr_fragments(item), {1: "End of first page.", 2: "Start of second page."})
        item.prov[1].charspan = (17, 40)
        with self.assertRaisesRegex(ValueError, "Invalid OCR character span"):
            ocr_fragments(item)
        item.prov[1].charspan = (20, 40)
        with self.assertRaisesRegex(ValueError, "Unassigned OCR characters"):
            ocr_fragments(item)

    def test_same_page_ocr_slices_preserve_original_spacing(self):
        item = TextItem(
            self_ref="#/texts/0", label=DocItemLabel.TEXT, text="outline", orig="outline",
            prov=[ProvenanceItem(page_no=1, charspan=span,
                                 bbox=BoundingBox(l=0, t=1, r=1, b=0, coord_origin=CoordOrigin.BOTTOMLEFT))
                  for span in [(0, 3), (3, 7)]],
        )
        self.assertEqual(ocr_fragments(item), {1: "outline"})

    def test_no_claim_of_review_without_applied_corrections(self):
        self.assertEqual(review_status([]), "unreviewed machine extraction")
        self.assertIn("not a fully proofread transcription", review_status([{"pdf_page": 1}]))

    def test_list_marker_spans_index_original_ocr_text(self):
        item = ListItem(self_ref="#/texts/7", label=DocItemLabel.LIST_ITEM,
                        text="Introduction", orig="1. Introduction", marker="1.", enumerated=True,
                        prov=[ProvenanceItem(page_no=2, charspan=(0, 15),
                              bbox=BoundingBox(l=90, t=636, r=174, b=629, coord_origin=CoordOrigin.BOTTOMLEFT))])
        self.assertEqual(ocr_fragments(item), {2: "Introduction"})

    def test_invalid_native_decoding_is_rejected(self):
        for text in ("The width is \x01 pixels", "The \ufffd symbol"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "PDF page 2"):
                validate_text({1: "Readable abstract", 2: text})

    def test_page_markers_and_images_do_not_establish_searchable_coverage(self):
        with self.assertRaisesRegex(ValueError, "No searchable text"):
            validate_text({1: "<!-- PDF page 1 -->\n\n![Image](figures/figure-01.png)"})

    def test_failed_conversion_leaves_accepted_artifacts_intact(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(extract, "PAPERS", Path(tmp)):
            folder = Path(tmp) / extract.CATALOG["hobby-1993-automatically-tuned-bitmaps"]["folder"]
            folder.mkdir()
            (folder / "paper.md").write_text("accepted")
            with patch.object(extract, "extract_into", side_effect=ValueError("bad decoding")):
                with self.assertRaisesRegex(ValueError, "bad decoding"):
                    extract.extract("hobby-1993-automatically-tuned-bitmaps", Path(tmp), True, None, {}, False)
            self.assertEqual((folder / "paper.md").read_text(), "accepted")

    def test_successful_publication_replaces_stale_figures(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(extract, "PAPERS", Path(tmp)):
            folder = Path(tmp) / extract.CATALOG["hobby-1993-automatically-tuned-bitmaps"]["folder"]
            (folder / "figures").mkdir(parents=True)
            (folder / "figures/obsolete.png").write_bytes(b"old")
            def write_outputs(*args):
                staging = args[-1]
                (staging / "figures").mkdir()
                (staging / "figures/current.png").write_bytes(b"current")
                (staging / "paper.md").write_text("new text")
                (staging / "extraction.json").write_text("{}")
            with patch.object(extract, "extract_into", side_effect=write_outputs):
                extract.extract("hobby-1993-automatically-tuned-bitmaps", Path(tmp), True, None, {}, False)
            self.assertEqual([p.name for p in (folder / "figures").iterdir()], ["current.png"])

    def test_failed_installation_restores_the_previous_bundle(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(extract, "PAPERS", Path(tmp)):
            folder = Path(tmp) / extract.CATALOG["hobby-1993-automatically-tuned-bitmaps"]["folder"]
            (folder / "figures").mkdir(parents=True)
            (folder / "figures/old.png").write_bytes(b"old")
            (folder / "paper.md").write_text("accepted")
            (folder / "extraction.json").write_text('{"accepted": true}')
            def write_outputs(*args):
                staging = args[-1]
                (staging / "figures").mkdir()
                (staging / "figures/new.png").write_bytes(b"new")
                (staging / "paper.md").write_text("new text")
                (staging / "extraction.json").write_text("{}")
            original_replace = Path.replace
            def fail_second_install(source, target):
                if source.name == "paper.md" and source.parent.name.startswith("paper-extract-"):
                    raise OSError("installation failed")
                return original_replace(source, target)
            with patch.object(extract, "extract_into", side_effect=write_outputs), patch.object(Path, "replace", fail_second_install):
                with self.assertRaisesRegex(OSError, "installation failed"):
                    extract.extract("hobby-1993-automatically-tuned-bitmaps", Path(tmp), True, None, {}, False)
            self.assertEqual((folder / "paper.md").read_text(), "accepted")
            self.assertEqual((folder / "extraction.json").read_text(), '{"accepted": true}')
            self.assertEqual([p.name for p in (folder / "figures").iterdir()], ["old.png"])


if __name__ == "__main__":
    unittest.main()
