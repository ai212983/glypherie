#!/usr/bin/env python3
"""Extract the local reference papers with page provenance and review patches."""

import argparse
import hashlib
import importlib.metadata
import json
import logging
import copy
import re
import unicodedata
from pathlib import Path

import pymupdf
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.stage_model_specs import VlmEngineType
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument, FormulaItem, ImageRef, ImageRefMode


ROOT = Path(__file__).resolve().parents[2]
PAPERS = ROOT / "docs/references/papers"
CATALOG = {
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


def converter(enrich):
    options = PdfPipelineOptions()
    options.do_ocr = False  # These PDFs have native text; raster-only content is reviewed separately.
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
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def extract(stem, cache, reuse, get_converter, patches, enrich):
    paper_dir = PAPERS / CATALOG[stem]["folder"]
    pdf_path = paper_dir / "paper.pdf"
    sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    cached = cache / f"{stem}-{'enriched' if enrich else 'native'}-{sha}.json"
    if reuse and cached.exists():
        print(f"Reusing {cached.name}", flush=True)
        doc = DoclingDocument.load_from_json(cached)
    else:
        print(f"Converting {pdf_path.name}", flush=True)
        result = get_converter().convert(pdf_path)
        if result.status.value != "success":
            raise RuntimeError(f"Conversion status: {result.status}; errors: {result.errors}")
        doc = result.document
        doc.save_as_json(cached)

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
        image.save(asset_dir / filename)
        picture.image = ImageRef(mimetype="image/png", dpi=144, size=picture.image.size, uri=asset_rel / filename)
        figures.append({
            "file": str(asset_rel / filename),
            "pdf_page": picture.prov[0].page_no,
            "caption": picture.caption_text(doc),
            "bbox": picture.prov[0].bbox.model_dump(mode="json"),
        })

    paper_patches = patches.get(stem, {})
    page_text = {}
    reviewed = []
    # Docling supplies structure and reading order, while PyMuPDF decodes legacy
    # font glyphs more accurately here. Recover each prose region separately so
    # paragraphs spanning pages do not get duplicated by page-filtered exports.
    recovered = {}
    with pymupdf.open(pdf_path) as pdf:
        for item in doc.texts:
            if item.label.value in {"formula", "code"}:
                continue
            by_page = {}
            for prov in item.prov:
                source_page = pdf[prov.page_no - 1]
                box = prov.bbox.to_top_left_origin(source_page.rect.height)
                rect = pymupdf.Rect(box.l - .5, box.t - .5, box.r + .5, box.b + .5)
                text = unicodedata.normalize("NFKC", source_page.get_textbox(rect))
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

    for page in sorted(doc.pages):
        page_doc = copy.deepcopy(doc)
        for item in page_doc.texts:
            if item.self_ref in recovered and page in recovered[item.self_ref]:
                item.text = recovered[item.self_ref][page]
                # Docling's page filter tests the first provenance entry. A
                # paragraph spanning pages must expose the current page first.
                item.prov = [prov for prov in item.prov if prov.page_no == page]
        md = page_doc.export_to_markdown(page_no=page, image_mode=ImageRefMode.REFERENCED)
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

    settings = CATALOG[stem]
    header = (
        "---\n"
        "source_pdf: paper.pdf\n"
        f"source_url: {settings['source']}\n"
        f"source_sha256: {sha}\n"
        f"pdf_pages: {len(doc.pages)}\n"
        f"converter: docling {importlib.metadata.version('docling')}\n"
        "math_format: latex\n"
        "review_status: targeted corrections; not a fully proofread transcription\n"
        "---\n\n"
        "Source: [original PDF](paper.pdf). "
        "Page markers identify the PDF page and the original printed page. "
        "See [review guidance](../README.md#accuracy-and-review) for review scope and limitations.\n\n"
    )
    body = []
    for page, md in page_text.items():
        printed = settings["first_printed_page"] + page - 1
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
        "versions": {name: importlib.metadata.version(name) for name in
                     ["docling", "docling-core", "docling-ibm-models", "docling-parse", "torch", "pymupdf"]},
        "pipeline": {"ocr": False, "formula_enrichment": enrich, "code_enrichment": enrich,
                     "code_formula_model": "docling-project/CodeFormulaV2" if enrich else None, "device": "cpu",
                     "dtype": "float32", "image_dpi": 144,
                     "prose_decoder": "PyMuPDF using Docling bounding boxes"},
        "model_revisions": {
            name: (Path.home() / ".cache/huggingface/hub" / ("models--" + name.replace("/", "--"))
                   / "refs" / ref).read_text().strip()
            for name, ref in [("docling-project/docling-layout-heron", "main"),
                              ("docling-project/docling-models", "v2.3.0")]
                            + ([("docling-project/CodeFormulaV2", "main")] if enrich else [])
        },
        "detected_item_counts": counts, "figures": figures, "reviewed_corrections": reviewed,
        "review_notes": paper_patches.get("review_notes", []),
    }
    (paper_dir / "extraction.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {output.name}: {len(doc.pages)} pages, {len(figures)} images, {counts}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("papers", nargs="*", metavar="PAPER", help="Catalog keys (default: all registered papers)")
    parser.add_argument("--reuse", action="store_true", help="Reuse cached Docling documents before applying review patches")
    parser.add_argument("--enrich", action="store_true", help="Run additional neural code/formula recognition (slow on CPU)")
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/font-generator-docling/documents")
    args = parser.parse_args()
    unknown = set(args.papers) - set(CATALOG)
    if unknown:
        parser.error(f"Unknown paper stems: {', '.join(sorted(unknown))}")
    args.cache.mkdir(parents=True, exist_ok=True)
    patch_file = Path(__file__).with_name("review.json")
    patches = json.loads(patch_file.read_text()) if patch_file.exists() else {}
    active = None

    def get_converter():
        nonlocal active
        if active is None:
            active = converter(args.enrich)
        return active

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for stem in args.papers or CATALOG:
        extract(stem, args.cache, args.reuse, get_converter, patches, args.enrich)


if __name__ == "__main__":
    main()
