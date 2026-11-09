"""Prepare pinned original-domain inputs for the historical YinYangFit notebook.

This is a disclosed dependency compatibility port, not recovery of the author's
exact environment. Rendering and pair metrics remain the pinned tensorfont code.
"""

import argparse
import ast
import hashlib
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import platform
import re
import sys
import types
import urllib.request

import freetype
import numpy as np
import uharfbuzz


ROOT = Path(__file__).resolve().parents[2]
LOCK = Path(__file__).with_name("reference") / "yinyangfit-recovery" / "inputs.lock.json"
REQUIREMENTS = Path(__file__).with_name("requirements-yinyangfit.txt")
CHARACTERS = "abcdefghijklmnopqrstuvwxyz"
DELTAS = [-3, -1, 0, 1, 5]
SCHEMA = "yinyangfit-original-inputs-v1"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def sources(cache):
    """Fetch only immutable, size/hash-checked reference inputs; reuse exact cache bytes."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    lock = json.loads(LOCK.read_text())
    for name, item in lock["files"].items():
        path = cache / name
        if not path.exists():
            with urllib.request.urlopen(item["url"], timeout=45) as response:
                data = response.read(item["bytes"] + 1)
            if len(data) != item["bytes"] or sha256(data) != item["sha256"]:
                raise ValueError("reference download identity mismatch: " + name)
            path.write_bytes(data)
        data = path.read_bytes()
        if len(data) != item["bytes"] or sha256(data) != item["sha256"]:
            raise ValueError("modified reference cache: " + name)
    return cache, lock


def tensorfont(cache):
    """Execute checked source privately; never patch the upstream checkout or global NumPy."""
    name = "_yinyang_tensorfont_ca40a"
    if name in sys.modules:
        raise ValueError("private tensorfont recovery package already loaded")
    module = types.ModuleType(name)
    module.__path__ = [str(cache)]
    module.__file__ = str(cache / "tensorfont-__init__.py")
    sys.modules[name] = module
    spec = importlib.util.spec_from_file_location(name + ".interpshape", cache / "tensorfont-interpshape.py")
    child = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = child
    spec.loader.exec_module(child)
    source = (cache / "tensorfont-__init__.py").read_text()
    edits = []
    for old, new, explanation in [
        ("from skimage.util import pad", "from numpy import pad",
         "scikit-image removed its NumPy pad alias; retain identical constant-padding arguments"),
        ("from tensorfont.interpshape import interp_shape", "from " + name + ".interpshape import interp_shape",
         "load pinned dependency in a private namespace; no geometry change"),
    ]:
        if source.count(old) != 1:
            raise ValueError("unexpected compatibility patch site: " + old)
        source = source.replace(old, new)
        edits.append(dict(old=old, new=new, count=1, reason=explanation))
    source, count = re.subn(r"\bnp\.float\b", "float", source)
    if count != 1:
        raise ValueError("unexpected np.float alias inventory")
    edits.append(dict(old="np.float", new="float", count=count,
                      reason="NumPy removed its alias of the built-in float type; conversion remains float64"))
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module, edits, sha256(source.encode())


def pair_translator(cache, font, widths):
    notebook = json.loads((cache / "YinYangFit.ipynb").read_text())
    tree = ast.parse("".join(notebook["cells"][10]["source"]))
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == "get_pair_translations"]
    if len(definitions) != 1:
        raise ValueError("unexpected original translation definition")
    isolated = ast.fix_missing_locations(ast.Module(body=definitions, type_ignores=[]))
    namespace = dict(np=np, f=font, glyph_ink_widths=widths)
    exec(compile(isolated, "YinYangFit.ipynb:cell10", "exec"), namespace)
    return namespace["get_pair_translations"], sha256(ast.dump(isolated, include_attributes=False).encode())


def clipping(image, shift):
    if shift < 0:
        lost = image[:, :min(-shift, image.shape[1])]
    elif shift > 0:
        lost = image[:, max(0, image.shape[1] - shift):]
    else:
        lost = np.empty((0,), dtype=image.dtype)
    return dict(nonzero_samples=int(np.count_nonzero(lost)), coverage_sum=float(lost.sum(dtype=np.float64)))


def environment():
    packages = {dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()}
    return dict(python=platform.python_version(), executable=sys.executable, platform=platform.platform(),
                architecture=platform.machine(), packages=dict(sorted(packages.items())),
                freetype_version=list(freetype.version()), harfbuzz_version=uharfbuzz.version_string(),
                requirements_sha256=sha256(REQUIREMENTS.read_bytes()))


def prepare(cache, output):
    output = Path(output)
    if output.exists():
        raise ValueError("input output directory must be new")
    cache, lock = sources(cache)
    module, edits, compatibility_hash = tensorfont(cache)
    font = module.Font(str(cache / "CrimsonRoman.otf"), 34)
    height, width = int(font.full_height_px), 161
    if height != 80:
        raise ValueError(f"candidate font/dependency gives height {height}, historical retained shape is 80; stop")
    images, glyphs, widths = [], [], {}
    for ch in CHARACTERS:
        glyph = font.glyph(ch)
        image = np.asarray(glyph.as_matrix(normalize=True).with_padding_to_constant_box_width(width), dtype=np.float32)
        if image.shape != (height, width) or not np.isfinite(image).all() or image.min() < 0 or image.max() > 1:
            raise ValueError("invalid original-domain rendered image: " + ch)
        if not np.any(image):
            raise ValueError("empty original-domain glyph: " + ch)
        widths[ch] = glyph.ink_width
        rows, columns = np.nonzero(image)
        original_top = font.ascender_px - glyph.tsb
        source_ink_vertical_clipped = glyph.tsb < 0 or glyph.tsb + glyph.ink_height > height
        if source_ink_vertical_clipped:
            raise ValueError("source glyph ink is clipped vertically: " + ch)
        images.append(image)
        glyphs.append(dict(character=ch, codepoint=ord(ch), glyph_id=font.ttFont.getGlyphID(ch),
                           ink_width=int(glyph.ink_width), ink_height=int(glyph.ink_height),
                           advance_px=float(glyph.width), lsb_px=float(glyph.lsb), rsb_px=float(glyph.rsb),
                           tsb_px=float(glyph.tsb), bitmap_top_px=float(original_top),
                           padding_left=int(np.ceil((width - glyph.ink_width) / 2)),
                           padding_right=int(np.floor((width - glyph.ink_width) / 2)),
                           occupied_bounds=[int(columns.min()), int(rows.min()), int(columns.max()) + 1, int(rows.max()) + 1],
                           image_sha256=sha256(image.tobytes()), source_ink_vertical_clipped=False))
    translate, translation_hash = pair_translator(cache, font, widths)
    pairs, left_all, right_all = [], [], []
    glyph_by_character = {g["character"]: g for g in glyphs}
    for a in CHARACTERS:
        for b in CHARACTERS:
            kern = float(font.pair_kerning(a, b))
            designed_gap = float(font.pair_distance(a, b))
            minimum = float(font.minimum_ink_distance(a, b))
            if not all(math.isfinite(v) for v in [kern, designed_gap, minimum]):
                raise ValueError("nonfinite original metric")
            left, right = translate(a, b, DELTAS)
            if left.shape != (5,) or right.shape != (5,) or len(set((right - left).tolist())) != 5:
                raise ValueError("invalid/collapsed original candidate translations")
            ga, gb = glyph_by_character[a], glyph_by_character[b]
            candidates = []
            for delta, tl, tr in zip(DELTAS, left.tolist(), right.tolist()):
                lost_left = clipping(images[ord(a) - 97], tl)
                lost_right = clipping(images[ord(b) - 97], tr)
                ink_origin_step = gb["padding_left"] + tr - ga["padding_left"] - tl
                font_origin_step = ink_origin_step + ga["lsb_px"] - gb["lsb_px"]
                candidates.append(dict(delta_px=delta, translation_left_px=tl, translation_right_px=tr,
                                       ink_origin_step_px=ink_origin_step, font_origin_step_px=font_origin_step,
                                       bounding_box_gap_px=ink_origin_step - widths[a],
                                       clipping_left=lost_left, clipping_right=lost_right))
            if any(c[side]["nonzero_samples"] for c in candidates for side in ["clipping_left", "clipping_right"]):
                raise ValueError("candidate translation clips glyph ink: " + a + b)
            metric_step = ga["advance_px"] + kern
            pairs.append(dict(pair=a + b, left=ord(a), right=ord(b), pair_distance_px=designed_gap,
                              minimum_ink_distance_px=minimum, kerning_px=kern,
                              label_center_px=int(designed_gap + minimum), label_index=2,
                              metric_origin_step_px=metric_step,
                              center_origin_step_difference_px=candidates[2]["font_origin_step_px"] - metric_step,
                              candidates=candidates))
            left_all.append(left)
            right_all.append(right)
    output.mkdir(parents=True)
    arrays = dict(glyph_images=np.stack(images), glyph_ink_widths=np.array([widths[c] for c in CHARACTERS], dtype=np.int32),
                  translations_left=np.stack(left_all).astype(np.int32), translations_right=np.stack(right_all).astype(np.int32),
                  codepoints=np.array(list(map(ord, CHARACTERS)), dtype=np.uint32),
                  pair_codepoints=np.array([(ord(a), ord(b)) for a in CHARACTERS for b in CHARACTERS], dtype=np.uint32),
                  sample_distance_deltas=np.array(DELTAS, dtype=np.int32), labels=np.full(676, 2, dtype=np.int64))
    np.savez(output / "inputs.npz", **arrays)
    manifest = dict(schema_version=SCHEMA, status="complete", model_domain="original normalized grayscale, not delivered bitmaps",
                    source_lock=lock, source_lock_sha256=sha256(LOCK.read_bytes()),
                    adapter_sha256=sha256(Path(__file__).read_bytes()),
                    inputs_npz_sha256=sha256((output / "inputs.npz").read_bytes()),
                    array_identities={name: dict(dtype=str(value.dtype), shape=list(value.shape), sha256=sha256(value.tobytes()))
                                      for name, value in arrays.items()},
                    compatibility=dict(environment_is_historical=False, edits=edits, private_source_sha256=compatibility_hash),
                    environment=environment(), font=dict(requested_x_height_px=34, selected_ppem=font.face.size.y_ppem,
                        scale_factor=font.scale_factor, units_per_em=font.face.units_per_EM,
                        original_x_height_at_em_px=34 / font.scale_factor, ascender_px=font.ascender_px,
                        descender_px=font.descender_px, full_height_px=height, width_px=width,
                        has_freetype_kerning=bool(font.face.has_kerning),
                        baseline_coordinate_y_down_px=font.ascender_px, grayscale_normalization="coverage/255 then float32"),
                    glyphs=glyphs, pairs=pairs, sample_distance_deltas=DELTAS, label_index=2,
                    translation_function_ast_sha256=translation_hash,
                    clipping=dict(source_ink=False, candidate_ink=False),
                    limits=["Candidate immutable font/dependency provenance, not recovered original execution bytes",
                            "Labels imitate source design; no optical or small-bitmap acceptance",
                            "Original centering and integer translation rounding retained, including metric-step differences"])
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sources-cache", type=Path,
                        default=ROOT / "out/diagnostics/contextual-spacing/yinyangfit/recovery-sources")
    args = parser.parse_args()
    result = prepare(args.sources_cache, args.output)
    print(json.dumps(dict(status=result["status"], shape=result["array_identities"]["glyph_images"]["shape"],
                          pairs=len(result["pairs"]), inputs_npz_sha256=result["inputs_npz_sha256"])))
