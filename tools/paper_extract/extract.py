#!/usr/bin/env python3
"""Extract the local reference papers with page provenance and review patches."""

import argparse
import hashlib
import importlib.metadata
import json
import logging
import copy
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import pymupdf
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import OcrMode, PdfPipelineOptions, TesseractCliOcrOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.datamodel.stage_model_specs import VlmEngineType
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument, FormulaItem, ImageRef, ImageRefMode


ROOT = Path(__file__).resolve().parents[2]
PAPERS = ROOT / "docs/references/papers"
CATALOG = {
    "kelley-1998-display-reflectance": {
        "folder": "1998-kelley",
        "first_printed_page": 27,
        "ocr": True,
        "source": "https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=24685",
    },
    "darling-ferwerda-2012-reflective-surfaces": {
        "folder": "2012-darling-ferwerda",
        "first_printed_page": 135,
        "page_labels": {i: "unnumbered author manuscript" for i in range(1, 8)},
        "ocr": True,
        "source": "https://jamesferwerda.com/wp-content/uploads/2015/06/r19_darling12_cic.pdf",
    },
    "herle-2024-reflective-displays": {
        "folder": "2024-herle",
        "first_printed_page": 1,
        "page_labels": {i: f"020901-{i}" for i in range(1, 35)},
        "source": "https://infoscience.epfl.ch/server/api/core/bitstreams/bbef8e44-17de-4b0e-aa0b-649fe35f51b5/content",
    },
    "hobby-1993-automatically-tuned-bitmaps": {
        "folder": "1993-hobby",
        "first_printed_page": 0,
        "ocr": True,
        "enrich": True,
        "page_batch_size": 6,
        "page_labels": {1: "unnumbered abstract"},
        "source": "https://telecom.wiki/download/attachments/819301/CSTR%20148.pdf",
    },
    "hersch-1993-font-rasterization-survey": {
        "folder": "1993-hersch",
        "first_printed_page": 78,
        "source": "https://lspwww.epfl.ch/publications/typography/frsa.pdf",
    },
    "shamir-2003-constraint-based-hinting": {
        "folder": "2003-shamir",
        "first_printed_page": 131,
        "source": "https://dl.acm.org/doi/10.1145/636886.636887",
    },
    "turner-lemberg-2003-grid-fitting": {
        "folder": "2003-turner-lemberg",
        "first_printed_page": 430,
        "source": "https://www.tug.org/TUGboat/tb24-3/lemberg.pdf",
    },
    "gallager-2006-quantization": {
        "folder": "2006-gallager-quantization",
        "first_printed_page": 63,
        "source": "https://ocw.mit.edu/courses/6-450-principles-of-digital-communications-i-fall-2006/926689aaa62a0315473fa9b982de1b07_book_3.pdf",
    },
}


def converter(enrich, ocr=False):
    options = PdfPipelineOptions()
    options.do_ocr = ocr
    if ocr:
        # Use Docling's full-page OCR recipe for PDFs with unusable native font
        # encodings: https://docling-project.github.io/docling/_generated/examples/full_page_ocr/
        options.ocr_options = TesseractCliOcrOptions(mode=OcrMode.FULL_PAGE, lang=["eng"], scale=4)
    options.do_formula_enrichment = enrich
    options.do_code_enrichment = enrich
    options.generate_page_images = True
    options.generate_picture_images = True
    options.images_scale = 2.0
    options.accelerator_options = AcceleratorOptions(num_threads=4, device="cpu")
    # This machine has no native BF16 instructions. FP32 avoids emulated BF16 inference.
    options.code_formula_options.model_spec.engine_overrides[
        VlmEngineType.TRANSFORMERS
    ].extra_config["torch_dtype"] = "float32"
    kwargs = {"backend": PyPdfiumDocumentBackend} if ocr else {}
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options, **kwargs)})


def ocr_fragments(item):
    """Split merged OCR paragraphs by their character provenance, not PDF text."""
    # Docling's provenance indexes orig, while list-item text omits its marker.
    source = item.orig
    fragments = {}
    cursor = 0
    previous_page = None
    for prov in sorted(item.prov, key=lambda prov: prov.charspan):
        start, end = prov.charspan
        if not cursor <= start <= end <= len(source):
            raise ValueError(f"Invalid OCR character span: {item.self_ref}")
        gap = source[cursor:start]
        if gap.strip():
            raise ValueError(f"Unassigned OCR characters: {item.self_ref}")
        separator = gap if prov.page_no == previous_page else ""
        fragments.setdefault(prov.page_no, []).append(separator + source[start:end])
        cursor, previous_page = end, prov.page_no
    if source[cursor:].strip():
        raise ValueError(f"Unassigned OCR characters: {item.self_ref}")
    if len(fragments) == 1:
        return {next(iter(fragments)): item.text}
    result = {page: "".join(parts) for page, parts in fragments.items()}
    if item.text != source:
        prefix = getattr(item, "marker", "") + " "
        if not prefix.strip() or not source.startswith(prefix) or source[len(prefix):] != item.text:
            raise ValueError(f"Changed OCR text needs a page split review: {item.self_ref}")
        first_page = next(iter(result))
        result[first_page] = result[first_page].removeprefix(prefix)
    return result


def review_status(reviewed):
    return ("targeted corrections; not a fully proofread transcription" if reviewed
            else "unreviewed machine extraction")


def save_checkpoint(doc, path):
    partial = path.with_name(path.stem + ".partial.json")
    doc.save_as_json(partial)
    partial.replace(path)


def validate_text(page_text):
    """Reject known decoding failures before publishing a transcription."""
    for page, text in page_text.items():
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]", text):
            raise ValueError(f"Invalid decoded characters on PDF page {page}; review the decoder or use --ocr")
        # A page represented only by an image is not searchable paper text.
        prose = re.sub(r"!\[[^\]]*\]\([^)]*\)|<!--.*?-->", "", text, flags=re.S)
        if not re.search(r"\w", prose):
            raise ValueError(f"No searchable text on PDF page {page}; review page coverage")


def extract(stem, cache, reuse, get_converter, patches, enrich, ocr=False):
    paper_dir = PAPERS / CATALOG[stem]["folder"]
    # A conversion or review failure must not overwrite the accepted copy.
    with tempfile.TemporaryDirectory(prefix="paper-extract-", dir=paper_dir.parent) as staging:
        output_dir = Path(staging)
        extract_into(stem, cache, reuse, get_converter, patches, enrich, ocr, output_dir)
        installed, backups = [], []
        try:
            for filename in ("figures", "paper.md", "extraction.json"):
                target = paper_dir / filename
                if target.exists():
                    backup = output_dir / ("previous-" + filename)
                    target.replace(backup)
                    backups.append((backup, target))
                (output_dir / filename).replace(target)
                installed.append(target)
        except BaseException:
            for target in reversed(installed):
                target.replace(output_dir / target.name)
            for backup, target in reversed(backups):
                backup.replace(target)
            raise


def extract_into(stem, cache, reuse, get_converter, patches, enrich, ocr, paper_dir):
    pdf_path = PAPERS / CATALOG[stem]["folder"] / "paper.pdf"
    sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    mode = ("ocr-" if ocr else "") + ("enriched" if enrich else "native")
    batch_size = CATALOG[stem].get("page_batch_size")
    cache_mode = mode + (f"-batch{batch_size}" if batch_size else "")
    paper_patches = patches.get(stem, {})
    if paper_patches and paper_patches.get("mode", "native") != mode:
        raise ValueError(f"Review patches for {stem} require mode {paper_patches.get('mode', 'native')}, not {mode}")
    cached = cache / f"{stem}-{cache_mode}-{sha}.json"
    if reuse and cached.exists():
        print(f"Reusing {cached.name}", flush=True)
        doc = DoclingDocument.load_from_json(cached)
    else:
        print(f"Converting {pdf_path.name}", flush=True)
        if batch_size:
            with pymupdf.open(pdf_path) as pdf:
                page_count = len(pdf)
            parts = []
            for start in range(1, page_count + 1, batch_size):
                end = min(start + batch_size - 1, page_count)
                checkpoint = cached.with_name(cached.stem + f"-pages{start}-{end}.json")
                if reuse and checkpoint.exists():
                    part = DoclingDocument.load_from_json(checkpoint)
                else:
                    print(f"Converting PDF pages {start}–{end}", flush=True)
                    result = get_converter(ocr, enrich).convert(pdf_path, page_range=(start, end))
                    if result.status.value != "success":
                        raise RuntimeError(f"Conversion status: {result.status}; errors: {result.errors}")
                    part = result.document
                if sorted(part.pages) != list(range(start, end + 1)):
                    raise RuntimeError(f"Incomplete page batch: {start}–{end}")
                if not (reuse and checkpoint.exists()):
                    save_checkpoint(part, checkpoint)
                parts.append(part)
            doc = DoclingDocument.concatenate(parts)
        else:
            result = get_converter(ocr, enrich).convert(pdf_path)
            if result.status.value != "success":
                raise RuntimeError(f"Conversion status: {result.status}; errors: {result.errors}")
            doc = result.document
        save_checkpoint(doc, cached)

    with pymupdf.open(pdf_path) as pdf:
        if sorted(doc.pages) != list(range(1, len(pdf) + 1)):
            raise RuntimeError(f"Incomplete page coverage: {pdf_path.name}")

    asset_rel = Path("figures")
    asset_dir = paper_dir / asset_rel
    asset_dir.mkdir(parents=True, exist_ok=True)
    figures = []
    for i, picture in enumerate(doc.pictures, 1):
        filename = f"figure-{i:02}.png"
        image = picture.get_image(doc)
        if image is None:
            raise RuntimeError(f"Missing image: {picture.self_ref}")
        if not paper_patches.get("figure_regions"):
            image.save(asset_dir / filename)
        picture.image = ImageRef(mimetype="image/png", dpi=144, size=picture.image.size, uri=asset_rel / filename)
        if not paper_patches.get("figure_regions"):
            figures.append({
                "file": str(asset_rel / filename),
                "pdf_page": picture.prov[0].page_no,
                "caption": picture.caption_text(doc),
                "bbox": picture.prov[0].bbox.model_dump(mode="json"),
            })

    page_text = {}
    reviewed = []
    # Docling supplies structure and reading order, while PyMuPDF decodes legacy
    # font glyphs more accurately here. Recover each prose region separately so
    # paragraphs spanning pages do not get duplicated by page-filtered exports.
    recovered = {}
    with pymupdf.open(pdf_path) as pdf:
        text_pages = {}
        for item in doc.texts:
            if item.label.value in {"formula", "code"}:
                continue
            if ocr:
                recovered[item.self_ref] = ocr_fragments(item)
                continue
            by_page = {}
            for prov in item.prov:
                # Reuse the native TextPage rather than decoding every Type 3
                # font again for each region (Page.get_textbox's textpage API).
                if prov.page_no not in text_pages:
                    source_page = pdf[prov.page_no - 1]
                    text_pages[prov.page_no] = (source_page, source_page.get_textpage())
                source_page, text_page = text_pages[prov.page_no]
                box = prov.bbox.to_top_left_origin(source_page.rect.height)
                rect = pymupdf.Rect(box.l - .5, box.t - .5, box.r + .5, box.b + .5)
                text = unicodedata.normalize("NFKC", source_page.get_textbox(rect, textpage=text_page))
                if text.strip():
                    by_page.setdefault(prov.page_no, []).append(text.strip())
            page_fragments = {}
            for page, parts in by_page.items():
                # Preserve physical breaks until both columns' fragments have
                # been joined, including words split at a region boundary.
                text = "\n".join(parts)
                text = re.sub(r"(?<=\w)-\n(?=[a-z])", "", text)
                # Join identifiers split at a physical line break, e.g. ah_\nset_uv.
                text = re.sub(r"(?<=_)\n(?=[a-zA-Z])", "", text)
                text = " ".join(text.split())
                text = text.replace("B ́ezier", "Bézier").replace("B´ezier", "Bézier")
                text = text.replace("B ́etrisey", "Bétrisey").replace("B´etrisey", "Bétrisey")
                text = text.replace("F\uf769\uf767.", "Fig.")
                if item.label.value == "list_item":
                    text = re.sub(r"^[•″]\s*", "", text)
                    if item.marker and text.startswith(item.marker + " "):
                        text = text[len(item.marker):].lstrip()
                page_fragments[page] = text
            recovered[item.self_ref] = page_fragments

    for change in paper_patches.get("items", []):
        item = doc.texts[int(change["ref"].rsplit("/", 1)[1])]
        if len({prov.page_no for prov in item.prov}) > 1:
            raise ValueError(f"Item patch spans pages; use page replacements: {stem}, {change['ref']}")
        if item.orig != change["before"]:
            raise ValueError(f"Item patch mismatch: {stem}, {change['ref']}")
        item.text = change["after"]
        if change.get("kind") == "formula":
            data = item.model_dump()
            data["label"] = "formula"
            item = FormulaItem.model_validate({k: v for k, v in data.items() if k in FormulaItem.model_fields})
            doc.texts[int(change["ref"].rsplit("/", 1)[1])] = item
        recovered.pop(item.self_ref, None)
        reviewed.append({"pdf_page": item.prov[0].page_no, "note": change["note"]})

    for change in paper_patches.get("reorders", []):
        refs = set(change["refs"])
        nodes = [node for node in doc.body.children if node.cref in refs]
        if {node.cref for node in nodes} != refs:
            raise ValueError(f"Reorder references missing: {stem}")
        remaining = [node for node in doc.body.children if node.cref not in refs]
        target = next(i for i, node in enumerate(remaining) if node.cref == change["before_ref"])
        doc.body.children = remaining[:target] + nodes + remaining[target:]
        reviewed.append({"pdf_page": change["page"], "note": change["note"]})

    # Reviewed source regions replace a failed figure detector. Remove only OCR
    # items wholly contained in those illustrations; preserve surrounding prose,
    # captions and explicitly retained algorithm transcriptions.
    omitted_illustration_items = []
    for region in paper_patches.get("figure_regions", []):
        if region.get("keep_text", False):
            continue
        bounds = pymupdf.Rect(region["bbox"])
        omitted = []
        for item in doc.texts:
            if item.prov and all(
                prov.page_no == region["page"] and bounds.contains(pymupdf.Rect(
                    prov.bbox.to_top_left_origin(doc.pages[prov.page_no].size.height).as_tuple()))
                for prov in item.prov
            ):
                item.text = ""
                recovered.pop(item.self_ref, None)
                omitted.append(item.self_ref)
        omitted_illustration_items.append({"figure": region["anchor"], "pdf_page": region["page"],
                                           "item_refs": omitted})

    for page in sorted(doc.pages):
        page_doc = copy.deepcopy(doc)
        for item in page_doc.texts:
            if item.self_ref in recovered and page in recovered[item.self_ref]:
                item.text = recovered[item.self_ref][page]
                # Docling's page filter tests the first provenance entry. A
                # paragraph spanning pages must expose the current page first.
                item.prov = [prov for prov in item.prov if prov.page_no == page]
        md = page_doc.export_to_markdown(page_no=page, image_mode=ImageRefMode.REFERENCED)
        if paper_patches.get("figure_regions"):
            md = re.sub(r"!\[[^\]]*\]\(figures/figure-\d+\.png\)", "", md)
            if "figures/figure-" in md:
                raise ValueError(f"Unremoved detector image reference: {stem}, page {page}")
            md = re.sub(r"(?m)^#{1,6}\s+(Figure \d+:)", r"\1", md)
        if stem.startswith("shamir"):
            md = re.sub(r"(?m)^(?:#{1,6}\s+|-\s+)?(?:\d+ • A\. Shamir|Constraint-Based Approach for Automatic Hinting of Digital Typefaces • \d+)\s*$", "", md)
            md = re.sub(r"ACM Transactions on Graphics, Vol\. 22, No\. 2, April 2003(?:, Pages 131–151)?\.", "", md)
            md = re.sub(r"(?m)^(?:-\s+)?(\d+\.\d+)\s+([A-Z][^\n]+)$", r"### \1 \2", md)
            md = re.sub(r"(?m)^(?:-\s+)?([1-6])\.\s+([A-Z][A-Z ]+)$", r"## \1. \2", md)
        if stem.startswith("hersch"):
            md = re.sub(r"(?m)^- ((?:1|10|11|12) (?:Introduction|Remaining problems|Conclusions|Acknowlegments))$", r"## \1", md)
        if page == 1:
            md = re.sub(r"^## ", "# ", md, count=1)
        for change in paper_patches.get("replacements", []):
            if change["page"] != page:
                continue
            before = change["before"]
            if md.count(before) != 1:
                raise ValueError(f"Patch must match once: {stem}, page {page}, {before!r}")
            md = md.replace(before, change["after"], 1)
            reviewed.append({"pdf_page": page, "note": change["note"]})
        if stem.startswith("turner"):
            md = re.sub(r"```\n(.*?)\n```", r"```c\n\1\n```", md, flags=re.S)
        page_text[page] = md

    with pymupdf.open(pdf_path) as pdf:
        for region in paper_patches.get("figure_regions", []):
            page = region["page"]
            bounds = pymupdf.Rect(region["bbox"])
            if bounds.is_empty or not pdf[page - 1].rect.contains(bounds):
                raise ValueError(f"Figure region outside page: {stem}, {region['file']}")
            anchor = region["anchor"]
            if page_text[page].count(anchor) != 1:
                raise ValueError(f"Figure anchor must match once: {stem}, page {page}, {anchor!r}")
            pdf[page - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=bounds).save(asset_dir / region["file"])
            md = f"![{anchor.rstrip(':')}](figures/{region['file']})"
            if region.get("transcription"):
                md += "\n\n" + region["transcription"]
            page_text[page] = page_text[page].replace(anchor, md + "\n\n" + anchor, 1)
            caption = re.search(re.escape(anchor) + r".*?(?=\n\n|\Z)", page_text[page], flags=re.S).group()
            figures.append({"file": str(asset_rel / region["file"]), "pdf_page": page,
                            "caption": caption, "bbox": {"l": bounds.x0, "t": bounds.y0,
                                "r": bounds.x1, "b": bounds.y1, "coord_origin": "TOPLEFT"}})
            reviewed.append({"pdf_page": page, "note": region["note"]})
        for supplement in paper_patches.get("supplements", []):
            page = supplement["page"]
            filename = supplement["file"]
            rect = pymupdf.Rect(supplement["bbox"])
            pdf[page - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=rect).save(asset_dir / filename)
            if "insert_after" in supplement:
                anchor = supplement["insert_after"]
                if page_text[page].count(anchor) != 1:
                    raise ValueError(f"Supplement anchor must match once: {stem}, page {page}")
                page_text[page] = page_text[page].replace(anchor, anchor + "\n\n" + supplement["markdown"], 1)
            else:
                page_text[page] += "\n\n" + supplement["markdown"]
            figures.append({"file": str(asset_rel / filename), "pdf_page": page,
                            "caption": supplement["note"], "bbox": supplement["bbox"]})
            reviewed.append({"pdf_page": page, "note": supplement["note"]})

    # Reviewed crop bounds override incomplete figure regions from the layout model.
    with pymupdf.open(pdf_path) as pdf:
        for crop in paper_patches.get("figure_crops", []):
            matches = [figure for figure in figures if figure["file"] == crop["file"]]
            if len(matches) != 1 or matches[0]["pdf_page"] != crop["page"]:
                raise ValueError(f"Figure crop must match once: {stem}, {crop['file']}")
            rect = pymupdf.Rect(crop["bbox"])
            page = pdf[crop["page"] - 1]
            if rect.is_empty or not page.rect.contains(rect):
                raise ValueError(f"Figure crop outside page: {stem}, {crop['file']}")
            page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=rect).save(paper_dir / crop["file"])
            matches[0]["bbox"] = {
                "l": rect.x0, "t": rect.y0, "r": rect.x1, "b": rect.y1, "coord_origin": "TOPLEFT"
            }
            reviewed.append({"pdf_page": crop["page"], "note": crop["note"]})

    validate_text(page_text)
    settings = CATALOG[stem]
    status = review_status(reviewed)
    header = (
        "---\n"
        "source_pdf: paper.pdf\n"
        f"source_url: {settings['source']}\n"
        f"source_sha256: {sha}\n"
        f"pdf_pages: {len(doc.pages)}\n"
        f"converter: docling {importlib.metadata.version('docling')}\n"
        "math_format: latex\n"
        f"review_status: {status}\n"
        "---\n\n"
        "Source: [original PDF](paper.pdf). "
        "Page markers identify the PDF page and the original printed page. "
        "See [review guidance](../README.md#accuracy-and-review) for review scope and limitations.\n\n"
    )
    body = []
    for page, md in page_text.items():
        printed = settings.get("page_labels", {}).get(page, settings["first_printed_page"] + page - 1)
        body.append(f"<!-- PDF page {page}; printed page {printed} -->\n\n{md.strip()}")
    output = paper_dir / "paper.md"
    output.write_text(header + "\n\n".join(body) + "\n")

    counts = {}
    for item, _ in doc.iterate_items():
        label = item.label.value
        counts[label] = counts.get(label, 0) + 1
    manifest = {
        "source_pdf": pdf_path.name, "source_url": settings["source"], "source_sha256": sha,
        "pdf_pages": len(doc.pages), "first_printed_page": settings["first_printed_page"],
        "page_labels": settings.get("page_labels", {}),
        "versions": {name: importlib.metadata.version(name) for name in
                     ["docling", "docling-core", "docling-ibm-models", "docling-parse", "torch", "pymupdf"]},
        "pipeline": {"mode": mode, "ocr": ocr, "formula_enrichment": enrich, "code_enrichment": enrich,
                     "page_batch_size": batch_size,
                     "code_formula_model": "docling-project/CodeFormulaV2" if enrich else None, "device": "cpu",
                     "dtype": "float32", "image_dpi": 144,
                     "prose_decoder": "Tesseract full-page OCR" if ocr else "PyMuPDF using Docling bounding boxes",
                     **({"ocr_language": ["eng"], "ocr_dpi": 288,
                         "tesseract_version": subprocess.check_output(["tesseract", "--version"], text=True).splitlines()[0]}
                        if ocr else {})},
        "model_revisions": {
            name: (Path.home() / ".cache/huggingface/hub" / ("models--" + name.replace("/", "--"))
                   / "refs" / ref).read_text().strip()
            for name, ref in [("docling-project/docling-layout-heron", "main"),
                              ("docling-project/docling-models", "v2.3.0")]
                            + ([("docling-project/CodeFormulaV2", "main")] if enrich else [])
        },
        "detected_item_counts": counts, "figures": figures, "reviewed_corrections": reviewed,
        "review_status": status,
        "omitted_illustration_items": omitted_illustration_items,
        "review_notes": paper_patches.get("review_notes", []),
    }
    (paper_dir / "extraction.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {output.name}: {len(doc.pages)} pages, {len(figures)} images, {counts}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("papers", nargs="*", metavar="PAPER", help="Catalog keys (default: all registered papers)")
    parser.add_argument("--reuse", action="store_true", help="Reuse cached Docling documents before applying review patches")
    parser.add_argument("--enrich", action="store_true", help="Run additional neural code/formula recognition (slow on CPU)")
    parser.add_argument("--ocr", action="store_true", help="Use full-page Tesseract OCR instead of native PDF text")
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/font-generator-docling/documents")
    args = parser.parse_args()
    unknown = set(args.papers) - set(CATALOG)
    if unknown:
        parser.error(f"Unknown paper stems: {', '.join(sorted(unknown))}")
    args.cache.mkdir(parents=True, exist_ok=True)
    patch_file = Path(__file__).with_name("review.json")
    patches = json.loads(patch_file.read_text()) if patch_file.exists() else {}
    active = {}

    def get_converter(ocr, enrich):
        key = (ocr, enrich)
        if key not in active:
            active[key] = converter(enrich, ocr)
        return active[key]

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for stem in args.papers or CATALOG:
        extract(stem, args.cache, args.reuse, get_converter, patches,
                args.enrich or CATALOG[stem].get("enrich", False),
                args.ocr or CATALOG[stem].get("ocr", False))


if __name__ == "__main__":
    main()
