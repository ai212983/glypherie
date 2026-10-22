#!/usr/bin/env python3
"""Pinned upstream StrokeStyles extraction runner.

Feeds fontTools-flattened glyph contours to strokestyles.api.extract_strokes
and exports spines (P), width profiles (W/Wv as radii, W_full as 2r),
connectivity and junctions as JSON.

Geometric notes (see docs/strokestyles-fitting.md):
- Upstream resamples internally and returns spines in original font units,
  y-up; this runner maps to pixels by size_px/upm only.
- The upstream TTF loader (common.load_glyph) unions the shape with nonzero
  fill before resampling, so list input is unioned with identical semantics;
  original contours are retained alongside the union actually analyzed.
- Glyph points come from the drawPoints protocol, where off-curve points
  carry segmentType None; consecutive off-curves imply a midpoint on-curve
  and an all-offcurve contour wraps through its end midpoint.
"""

import argparse
import copy
import hashlib
import json
import os
import random
import sys
import time

import numpy as np

RUNNER_VERSION = "extract-runner-v2"
UPSTREAM_REPO = "https://github.com/autograff-devel/strokestyles"
UPSTREAM_COMMIT = "3a74c98df66e9053aabf2a0299bbba188d270153"
SCHEMA_VERSION = "extract-record-v2"


def seed_determinism(seed=0):
    random.seed(seed)
    np.random.seed(seed)


def package_versions():
    """Every package on the extraction import path; a missing one is an error."""
    import matplotlib  # noqa: F401
    import networkx  # noqa: F401
    import PIL  # noqa: F401
    import scipy  # noqa: F401
    import fontTools  # noqa: F401
    import pyclipper  # noqa: F401
    import cv2  # noqa: F401
    import skgeom  # noqa: F401
    import svgpathtools  # noqa: F401
    import svgwrite  # noqa: F401
    from importlib.metadata import version as _dist_version

    return {
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "matplotlib": matplotlib.__version__,
        "networkx": networkx.__version__,
        "pillow": PIL.__version__,
        "fonttools": fontTools.version,
        "pyclipper": pyclipper.__version__,
        "opencv": cv2.__version__,
        "skgeom": getattr(skgeom, "__version__", "unversioned"),
        "svgpathtools": _dist_version("svgpathtools"),
        "svgwrite": _dist_version("svgwrite"),
    }


def native_binding_hash():
    """SHA-256 over the cautograff and skgeom native objects.

    Both bindings are required on the extraction path; a missing object is
    an error, never an empty success hash.
    """
    import glob

    import cautograff
    import skgeom

    roots = {
        "cautograff": os.path.dirname(
            os.path.dirname(os.path.abspath(cautograff.__file__))
        ),
        "skgeom": os.path.dirname(os.path.abspath(skgeom.__file__)),
    }
    digest = hashlib.sha256()
    found = {}
    for name, root in sorted(roots.items()):
        objects = sorted(glob.glob(os.path.join(root, "**", "*.so"), recursive=True))
        if not objects:
            raise FileNotFoundError(
                "no compiled objects for %s under %s" % (name, root)
            )
        for path in objects:
            with open(path, "rb") as handle:
                digest.update(path.encode())
                digest.update(handle.read())
        found[name] = [os.path.relpath(p, root) for p in objects]
    return {"sha256": digest.hexdigest(), "objects": found}


def load_font(path, axes):
    """Load a font, instantiating the complete resolved axis set."""
    from fontTools import ttLib
    from fontTools.varLib import instancer

    with open(path, "rb") as handle:
        raw = handle.read()
    original_sha = hashlib.sha256(raw).hexdigest()
    font = ttLib.TTFont(path, recalcTimestamp=False)
    upm = font["head"].unitsPerEm
    resolved = {}
    if "fvar" in font:
        defaults = {a.axisTag: a.defaultValue for a in font["fvar"].axes}
        resolved = dict(defaults)
        for tag, val in axes.items():
            if tag not in defaults:
                raise ValueError("axis %s not in font" % tag)
            axis = next(a for a in font["fvar"].axes if a.axisTag == tag)
            if not (axis.minValue <= val <= axis.maxValue):
                raise ValueError("axis %s=%s out of range" % (tag, val))
            resolved[tag] = val
        font = instancer.instantiateVariableFont(font, resolved)
        font["head"].modified = 0
        import io

        buf = io.BytesIO()
        font.save(buf)
        data = buf.getvalue()
    elif axes:
        raise ValueError("static font has no axes to instantiate: %r" % (axes,))
    else:
        data = raw
    for tag, val in resolved.items():
        if not (isinstance(val, (int, float)) and np.isfinite(val)):
            raise ValueError("non-finite axis value %s=%r" % (tag, val))
    return data, original_sha, hashlib.sha256(data).hexdigest(), resolved, upm


def collect_glyph_points(font, char):
    """Exact typed points per contour via the drawPoints protocol.

    Off-curve points carry segmentType None; every other point is on-curve.
    Composites are decomposed by the glyph set before points are reported.
    """
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    if ord(char) not in cmap:
        raise ValueError("missing glyph for %r" % char)

    class Collector:
        """Duck-typed point-protocol pen; no base import required."""
        def __init__(self):
            self.contours = []

        def beginPath(self):
            self.contours.append([])

        def endPath(self):
            pass

        def addPoint(self, pt, segmentType=None, smooth=False, name=None, **kwargs):
            self.contours[-1].append((tuple(pt), segmentType))

        def addComponent(self, baseGlyph, transformation):
            raise ValueError("unexpanded component %s" % baseGlyph)

    collector = Collector()
    glyph_set[cmap[ord(char)]].drawPoints(collector)
    return [[(tuple(p), t) for p, t in contour] for contour in collector.contours]


def flatten_contour(typed, flavor, curve_steps=12):
    """Flatten one typed contour, expanding implied on-curves.

    A run of k off-curve points between two on-curves expands to k quadratic
    triples joined at run midpoints (TrueType), or must be exactly one cubic
    triple (CFF). An all-offcurve contour wraps through the midpoint of its
    last and first points. Every triple is subdivided with curve_steps
    intervals; joints, endpoints and the wrap point are exact.
    """
    if flavor not in ("quad", "cubic"):
        raise ValueError("flavor must be quad or cubic")
    if len(typed) < 1:
        raise ValueError("empty contour")
    coords = []
    for p, _ in typed:
        arr = np.array(p, float)
        if arr.shape != (2,) or not np.isfinite(arr).all():
            raise ValueError("non-finite contour coordinate")
        coords.append(arr)
    # Off-curve points carry segmentType None under the drawPoints protocol.
    is_on = [t is not None for _, t in typed]
    n = len(coords)
    if n < 2:
        raise ValueError("degenerate contour")
    if not any(is_on):
        if n < 2:
            raise ValueError("degenerate all-offcurve contour")
        wrap = (coords[-1] + coords[0]) / 2.0
        seq = [wrap] + coords + [wrap]
        return _expand_runs(seq, [True] + [False] * n + [True], flavor, curve_steps)
    start = next(i for i, on in enumerate(is_on) if on)
    seq = [coords[(start + i) % n] for i in range(n)] + [coords[start]]
    flags = [is_on[(start + i) % n] for i in range(n)] + [True]
    return _expand_runs(seq, flags, flavor, curve_steps)


def _expand_runs(seq, is_on, flavor, curve_steps):
    """Expand off-curve runs of the linearized sequence into a polyline."""
    out = [np.array(seq[0], float)]
    i = 0
    n = len(seq) - 1
    while i < n:
        run = []
        j = i + 1
        while j <= n and not is_on[j]:
            run.append(seq[j])
            j += 1
        begin, end = np.array(seq[i], float), np.array(seq[j], float)
        if not run:
            closing = j == n and np.allclose(end, out[0])
            if not np.allclose(begin, end) and not closing:
                out.append(end)
        elif flavor == "cubic":
            if len(run) != 2:
                raise ValueError("CFF run is not one cubic triple")
            out.extend(_subdivide_cubic(begin, run[0], run[1], end, curve_steps)[1:])
        else:
            joints = [begin]
            for m in range(len(run) - 1):
                joints.append((np.array(run[m], float) + np.array(run[m + 1], float)) / 2.0)
            joints.append(end)
            starts = [begin] + joints[1:-1]
            ends = joints[1:]
            for a, c, b in zip(starts, run, ends):
                out.extend(
                    _subdivide_quad(a, np.array(c, float), b, curve_steps)[1:]
                )
        i = j
    return np.array(out, float)


def _subdivide_quad(p0, c, p1, n):
    p0, c, p1 = (np.array(p, float) for p in (p0, c, p1))
    ts = np.linspace(0, 1, n + 1)
    mt = 1 - ts
    return (mt * mt)[:, None] * p0 + (2 * mt * ts)[:, None] * c + (ts * ts)[:, None] * p1


def _subdivide_cubic(p0, c1, c2, p1, n):
    p0, c1, c2, p1 = (np.array(p, float) for p in (p0, c1, c2, p1))
    ts = np.linspace(0, 1, n + 1)
    mt = 1 - ts
    return (
        (mt**3)[:, None] * p0
        + (3 * mt * mt * ts)[:, None] * c1
        + (3 * mt * ts * ts)[:, None] * c2
        + (ts**3)[:, None] * p1
    )


def union_shape(contours):
    """Union closed contours with the upstream TTF loader's exact semantics.

    Mirrors common.load_glyph: a single nonzero-fill self-union, no dilation
    or erosion. Takes and returns Nx2 float arrays (font units, y-up); the
    clipper wrapper converts to its 2xN form at integer scale 10000.
    Exceptions are enabled so a clipper failure aborts loudly instead of
    falling back to the un-unioned shape.
    """
    import autograff.geom.clipper_wrap as clip

    clip.cfg.exceptions = True
    as2xn = [np.array(c, float).T for c in contours]
    united = clip.union(as2xn, as2xn)
    return [np.array(p, float).T for p in united]


def polygon_area(poly):
    """Signed shoelace area of an Nx2 polygon."""
    p = np.array(poly, float)
    return float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]) / 2.0)


def union_report(original, united):
    """Filled-ink check: union area, summed area and overlap fraction."""
    orig_areas = [abs(polygon_area(c)) for c in original]
    union_areas = [abs(polygon_area(c)) for c in united]
    total = float(sum(orig_areas))
    union_total = float(sum(union_areas))
    overlap = 0.0 if total == 0 else max(0.0, 1.0 - union_total / total)
    return {
        "n_contours_original": len(original),
        "n_contours_unioned": len(united),
        "area_original_sum": total,
        "area_unioned_sum": union_total,
        "overlap_fraction": overlap,
        "fill_rule": "nonzero",
        "clipper_scale": 10000,
    }


def to_jsonable(v):
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, dict):
        return {str(k): to_jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [to_jsonable(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return sorted([to_jsonable(x) for x in v], key=repr)
    return v


def export_glyph(Sd, char, upm, shape_size):
    """Export strokes, connectivity and junctions from a decomposition.

    Upstream W/Wv entries are medial radii; W_full reports the full normal
    thickness 2r. Spine coordinates are original font units, y-up.
    """
    import strokestyles.glyph_export as ge

    glyph = ge.create_glyph(Sd, [], char=char)
    strokes = []
    for s in glyph.get("strokes", []):
        # Upstream names and values kept verbatim: Wv/W are medial radii.
        # W_full is the derived full normal thickness 2r.
        record = {
            "P": to_jsonable(s["P"]),
            "Wv": to_jsonable(np.array(s["Wv"], float)),
            "W": to_jsonable(np.array(s["W"], float)),
            "W_full": to_jsonable(2.0 * np.array(s["W"], float)),
            "corner_flags": to_jsonable(s.get("corner_flags", [])),
            "corner_radii": to_jsonable(s.get("corner_radii", [])),
        }
        strokes.append(record)
    junctions = []
    for j in getattr(Sd, "junctions", []) or []:
        entry = {"type": type(j).__name__}
        for attr in (
            "kind",
            "key",
            "forks",
            "branches",
            "links",
            "stroke",
            "terminal",
            "covers",
        ):
            if hasattr(j, attr):
                try:
                    entry[attr] = to_jsonable(getattr(j, attr))
                except Exception as exc:  # noqa: BLE001
                    entry[attr] = "unserializable: %s" % exc
        junctions.append(entry)
    px_per_unit = shape_size / upm
    return {
        "strokes": strokes,
        "connectivity": to_jsonable(glyph.get("connectivity", {})),
        "junctions": junctions,
        "width_convention": "Wv/W are medial radii; W_full is 2r",
        "coordinate_convention": "font units, y-up; pixels = units * %r" % px_per_unit,
    }


REPO_COMMITS = {
    "strokestyles": "3a74c98df66e9053aabf2a0299bbba188d270153",
    "autograff": "9352fcccad9950149fe96eb0d88f40dbb8bf99d9",
    "csfs": "d24f33e3f0bb0508852131c62bf9bcc7c6c2ed5c",
    "cautograff": "4566a3741c0008c4b555f41e8e9ffc9ecd7bc70f",
    "skgeom": "e4a25c0cde054a3a4bd6b21d3ca30db8e7e6a178",
}
PINNED_BASE_DIGEST = (
    "sha256:5be5aaecb962a41567bc8041f1e9e3432cb085b037fe057f9a562630b2e4b370"
)


def runner_digest():
    """SHA-256 of this runner file: analysis code is part of the identity."""
    with open(os.path.abspath(__file__), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def build_identity(font_sha256_original, font_sha256_instantiated, axes_resolved,
                   outline_flavor, shape_size, curve_steps, seed, char,
                   packages, binding, image_id):
    """One canonical identity; every field affecting analysis is in it."""
    return {
        "schema_version": SCHEMA_VERSION,
        "font_sha256_original": font_sha256_original,
        "font_sha256_instantiated": font_sha256_instantiated,
        "axes_resolved": axes_resolved,
        "char": char,
        "outline_flavor": outline_flavor,
        "shape_size": shape_size,
        "curve_steps": curve_steps,
        "seed": seed,
        "extractor_commit": UPSTREAM_COMMIT,
        "repo_commits": REPO_COMMITS,
        "runner_version": RUNNER_VERSION,
        "runner_sha256": runner_digest(),
        "packages": packages,
        "native_binding": binding,
        "pinned_base_digest": PINNED_BASE_DIGEST,
        "image_id": image_id,
    }


def cache_key(identity):
    canonical = json.dumps(identity, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def cache_valid(record, identity):
    """A cache hit must equal the full expected identity, not a subset."""
    try:
        if record.get("schema_version") != SCHEMA_VERSION:
            return False, "schema mismatch"
        stored = record.get("identity")
        if not isinstance(stored, dict):
            return False, "identity absent"
        for field in identity:
            if stored.get(field) != identity[field]:
                return False, "identity drift: %s" % field
        for field in stored:
            if field not in identity:
                return False, "identity drift: unexpected %s" % field
        if not record.get("strokes"):
            return False, "empty strokes"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, "unreadable: %s" % exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--chars", required=True, help="e.g. kyxvz")
    ap.add_argument("--axes", default="",
                    help="TAG=val,TAG=val for variable fonts")
    ap.add_argument("--shape-size", type=float, default=150)
    ap.add_argument("--curve-steps", type=int, default=12)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--image-id", default="not-recorded",
                    help="runtime image digest or id, recorded verbatim")
    ap.add_argument("--probe-only", action="store_true")
    args = ap.parse_args()
    wall0 = time.perf_counter()
    stages = {}

    t0 = time.perf_counter()
    seed_determinism(args.seed)
    import strokestyles.api as api  # noqa: F401

    stages["imports_ms"] = (time.perf_counter() - t0) * 1000.0

    axes = {}
    for item in args.axes.split(","):
        if item.strip():
            tag, val = item.split("=")
            axes[tag.strip()] = float(val)

    t0 = time.perf_counter()
    data, original_sha, instantiated_sha, resolved, upm = load_font(
        args.font, axes
    )
    stages["instantiation_ms"] = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    packages = package_versions()
    binding = native_binding_hash()
    stages["setup_ms"] = (time.perf_counter() - t0) * 1000.0

    from fontTools import ttLib

    probe_font = ttLib.TTFont(args.font, recalcTimestamp=False, lazy=True)
    flavor = "quad" if "glyf" in probe_font else "cubic"
    source_bbox = None
    if "head" in probe_font:
        head = probe_font["head"]
        source_bbox = [head.xMin, head.yMin, head.xMax, head.yMax]

    provenance = {
        "schema_version": SCHEMA_VERSION,
        "extractor": "strokestyles-upstream-%s" % UPSTREAM_COMMIT[:12],
        "upstream_repo": UPSTREAM_REPO,
        "upstream_commit": UPSTREAM_COMMIT,
        "repo_commits": REPO_COMMITS,
        "runner_version": RUNNER_VERSION,
        "runner_sha256": runner_digest(),
        "font_sha256_instantiated": instantiated_sha,
        "font_sha256_original": original_sha,
        "axes_requested": axes,
        "axes_resolved": resolved,
        "outline_flavor": flavor,
        "units_per_em": upm,
        "source_font_bbox": source_bbox,
        "shape_size": args.shape_size,
        "curve_steps": args.curve_steps,
        "union": "nonzero self-union only, no offset "
        "(upstream common.load_glyph semantics)",
        "width_convention": "upstream Wv/W are medial radii; W_full is 2r",
        "seed": args.seed,
        "python_hash_seed": os.environ.get("PYTHONHASHSEED", "unset"),
        "packages": packages,
        "native_binding": binding,
        "pinned_base_digest": PINNED_BASE_DIGEST,
        "image_id": args.image_id,
        "char": "",
    }
    if args.probe_only:
        with open(args.out, "w") as handle:
            json.dump({"provenance": provenance, "probe": "ok"}, handle)
        print("probe ok")
        return 0

    os.makedirs(args.cache_dir, exist_ok=True)
    glyphs = {}
    for char in args.chars:
        provenance["char"] = char
        identity = build_identity(
            original_sha, instantiated_sha, resolved, flavor,
            args.shape_size, args.curve_steps, args.seed, char,
            packages, binding, args.image_id,
        )
        key = cache_key(identity)
        cache_path = os.path.join(args.cache_dir, key + ".json")
        t0 = time.perf_counter()
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as handle:
                    record = json.load(handle)
                ok, reason = cache_valid(record, identity)
            except Exception as exc:  # noqa: BLE001
                ok, reason = False, "unreadable: %s" % exc
            if ok:
                dt = (time.perf_counter() - t0) * 1000.0
                record["timing_ms"]["cache_read_ms"] = dt
                record["cache_key"] = key
                glyphs[char] = record
                print("cache hit %s %s %.1fms" % (char, key[:8], dt))
                continue
            print("cache invalid %s: %s; re-extracting" % (char, reason))
        t0 = time.perf_counter()
        typed_contours = collect_glyph_points(
            _reopen(args.font, resolved), char
        )
        original = [
            flatten_contour(c, flavor, args.curve_steps) for c in typed_contours
        ]
        stages_char_flatten = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        analyzed = union_shape(original)
        stages_char_union = (time.perf_counter() - t0) * 1000.0
        union_info = union_report(original, analyzed)
        t0 = time.perf_counter()
        # Upstream shape convention is a list of 2xN arrays (see
        # ttf.glyph_shape_uniform appending P.T); runner contours are Nx2.
        Sd = api.extract_strokes(
            [np.ascontiguousarray(np.array(c, float).T) for c in analyzed],
            shape_size=args.shape_size,
        )
        dt_extract = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        record = export_glyph(Sd, char, upm, args.shape_size)
        stages_char_export = (time.perf_counter() - t0) * 1000.0
        record["schema_version"] = SCHEMA_VERSION
        record["n_contours_original"] = len(original)
        record["n_points_original"] = sum(len(c) for c in original)
        record["n_contours_analyzed"] = len(analyzed)
        record["n_points_analyzed"] = sum(len(c) for c in analyzed)
        record["original_contours"] = to_jsonable(original)
        record["unioned_contours"] = to_jsonable(analyzed)
        record["union"] = union_info
        record["provenance"] = copy.deepcopy(provenance)
        record["identity"] = identity
        record["timing_ms"] = {
            "flatten_ms": stages_char_flatten,
            "union_ms": stages_char_union,
            "extract_ms": dt_extract,
            "serialize_ms": stages_char_export,
        }
        record["cache_key"] = key
        with open(cache_path, "w") as handle:
            json.dump(record, handle)
        glyphs[char] = record
        print(
            "extracted %s contours=%d->%d points=%d %s %.0fms"
            % (
                char,
                len(original),
                len(analyzed),
                record["n_points_original"],
                key[:8],
                dt_extract,
            )
        )

    stages["wall_ms"] = (time.perf_counter() - wall0) * 1000.0
    with open(args.out, "w") as handle:
        json.dump(
            {"provenance": provenance, "stages_ms": stages, "glyphs": glyphs},
            handle,
        )
    print("stages_ms=%s" % json.dumps(stages))
    return 0


def _reopen(path, resolved):
    from fontTools import ttLib
    from fontTools.varLib import instancer

    font = ttLib.TTFont(path, recalcTimestamp=False)
    if "fvar" in font and resolved:
        font = instancer.instantiateVariableFont(font, resolved)
    return font


if __name__ == "__main__":
    sys.exit(main())
