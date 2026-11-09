"""Evaluate six source-master spacing standards without bitmap integration.

Hersch et al. 1995 pp. 86–87, Figure 21, grounds nn/HH, oo/OO and no/HO
vertical-border standards. This experiment uses the existing provisional exact
source-element classifier; its rounded-plateau limitations are preserved.
Reusing no/HO in the reverse curve/stem direction is a declared experimental
adaptation, not author-code parity. Unsupported cases keep source placement.

Both reference and candidate gaps use exact source support coordinates and full
source metrics. Generic filtered-wall fallback is measured separately, using
source geometry for BOTH reference and candidate. No text calibrates a target;
there is no rounding, tracking, clearance or Solver mode in this tool.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

import hu_hersch as hu
import filtered_walls as walls
from calibration import pair_basis
from estimator import _segments


POLICIES = ['retained_delivered_reference_windows', 'source_reference_bounds']
STANDARDS = {'lowercase': {'stem_stem': 'nn', 'curve_curve': 'oo', 'mixed': 'no'}, 'uppercase': {'stem_stem': 'HH', 'curve_curve': 'OO', 'mixed': 'HO'}}
EXPECTED = {'stem_stem': ('stem', 'stem'), 'curve_curve': ('curve', 'curve'), 'mixed': ('stem', 'curve')}
REPORTED = ['ip', 'pe', 'ly', 'yn', 'nx', 'tu', 'uf', 'ft', 'fr', 'ro', 'og', 'gs', 'oe', 'kh', 'rn', 'xn', 'co', 'ff', 'cc', 'zz', 'jo', 'yd', 'le', 'pi', 'te', 'tp', 'OE', 'OR', 'bd', 'ct', 'ab', 'du', 're', '01', '12', 'nn', 'oo', 'no', 'on', 'HH', 'OO', 'HO', 'OH']


def avg(values):
    values = list(values)
    return math.fsum(values) / len(values) if values else None


def distribution(values):
    values = sorted(values)
    if not values:
        return dict(count=0)
    return dict(
        count=len(values),
        mean_px=avg(values),
        min_px=values[0],
        max_px=values[-1],
        median_px=statistics.median(values),
        mean_abs_px=avg((abs(v) for v in values)),
        negative=sum((v < -1e-10 for v in values)),
        zero=sum((abs(v) <= 1e-10 for v in values)),
        positive=sum((v > 1e-10 for v in values)),
        p05_px=values[math.floor(0.05 * (len(values) - 1))],
        p95_px=values[math.floor(0.95 * (len(values) - 1))],
    )


def transformed(commands, scale=1, dx=0, dy=0):
    return [dict(
        op=c['op'],
        **{k: c[k] * scale + (dx if k.startswith('x') else dy) for k in c if k != 'op'},
    ) for c in commands]


def reversed_contours(commands):
    groups = []
    current = []
    for command in commands:
        if command['op'] == 'move_to' and current:
            groups.append(current)
            current = []
        current.append(command)
    if current:
        groups.append(current)
    result = []
    for group in groups:
        segments = _segments(group)
        if not segments:
            continue
        rev = [tuple(reversed(s)) for s in reversed(segments)]
        result.append(dict(op='move_to', x=rev[0][0][0], y=rev[0][0][1]))
        for points in rev:
            endpoint = points[-1]
            command = dict(op={2: 'line_to', 3: 'quad_to', 4: 'curve_to'}[len(points)], x=endpoint[0], y=endpoint[1])
            if len(points) > 2:
                command.update(x1=points[1][0], y1=points[1][1])
            if len(points) > 3:
                command.update(x2=points[2][0], y2=points[2][1])
            result.append(command)
        result.append(dict(op='close'))
    return result


def analytic_checks():
    rectangle = [dict(
        op='move_to',
        x=0,
        y=0,
    ), dict(op='line_to', x=3, y=0), dict(op='line_to', x=3, y=4), dict(op='line_to', x=0, y=4), dict(op='close')]
    oval = [dict(
        op='move_to',
        x=0,
        y=2,
    ), dict(
        op='quad_to',
        x1=0,
        y1=4,
        x=2,
        y=4,
    ), dict(
        op='quad_to',
        x1=4,
        y1=4,
        x=4,
        y=2,
    ), dict(op='quad_to', x1=4, y1=0, x=2, y=0), dict(op='quad_to', x1=0, y1=0, x=0, y=2), dict(op='close')]
    records = []
    for name, commands, kind in [('rectangle', rectangle, 'stem'), ('oval', oval, 'curve')]:
        for side in ['left', 'right']:
            baseline = hu.classify_face(commands, 1, (0, 4), side)
            assert baseline['kind'] == kind
            for scale, dx, dy in [(1, 0, 0), (0.5, 7, -3), (2, -5, 4), (3, 6, -7)]:
                transformed_commands = transformed(commands, scale, dx, dy)
                window = (dy, dy + 4 * scale)
                for reverse in [False, True]:
                    candidate = reversed_contours(transformed_commands) if reverse else transformed_commands
                    result = hu.classify_face(candidate, 1, window, side)
                    expected = baseline['source_support_x_px'] * scale + dx
                    assert result['kind'] == kind and result['source_support_x_px'] == expected, (name, side, scale, reverse, result)
                    records.append(dict(
                        shape=name,
                        side=side,
                        scale=scale,
                        translation_px=[dx, dy],
                        reversed=reverse,
                        classification=result,
                    ))
    return dict(status='passed', cases=len(records), records=records)


class Experiment:
    """Compare internally consistent source-only classified and generic solves.

    The window policy changes only body-window derivation. It never selects a
    target using observed corpus shifts. Diagnostics expose every abstention.
    """

    def __init__(self, capture, policy):
        if policy not in POLICIES:
            raise ValueError('unsupported source experiment window policy')
        self.capture = capture
        self.policy = policy
        self.glyphs = {g['codepoint']: g for g in capture['glyphs']}
        self.scale = capture['size_px'] / capture['units_per_em']
        self.kerns = {(p['left'], p['right']): p['adjustment_px'] for p in capture['source_pairs']}
        self.windows = {}
        self.faces = {}
        self.refs = {}
        self.filtered = {}
        self.generic_targets = {}
        self.pair_cache = {}
        for basis, char in [('lowercase', 'n'), ('uppercase', 'H')]:
            g = self.glyphs.get(ord(char))
            window = None
            if g:
                if policy == 'retained_delivered_reference_windows':
                    rows = walls._bitmap_rows(g['bitmap'])
                    if rows:
                        window = (-max(rows) - 1.0, -min(rows) * 1.0)
                else:
                    bounds = walls.source_bounds(g['source_commands'], self.scale)
                    if bounds and bounds.maxy > bounds.miny:
                        window = (bounds.miny, bounds.maxy)
            self.windows[basis] = window
        for cp, g in self.glyphs.items():
            basis = self.glyph_basis(cp)
            for side in ['left', 'right']:
                window = self.windows.get(basis)
                if basis is None:
                    result = dict(
                        kind='generic',
                        reason='unsupported_same_case_letter',
                        source_support_x_px=None,
                        source_support_y_px=None,
                    )
                elif window is None:
                    result = dict(
                        kind='generic',
                        reason='missing_reference_window',
                        source_support_x_px=None,
                        source_support_y_px=None,
                    )
                else:
                    result = hu.classify_face(g['source_commands'], self.scale, window, side)
                self.faces[cp, side] = result
        for basis, standards in STANDARDS.items():
            for kind, text in standards.items():
                self.refs[basis, kind] = self.reference(basis, kind, text)
            anchor = ord('n' if basis == 'lowercase' else 'H')
            if anchor in self.glyphs and self.windows[basis]:
                p = self.profile(anchor, basis)
                if p.bounds is not None:
                    self.generic_targets[basis] = self.step(anchor, anchor) + hu.pair_offset(p, p)

    @staticmethod
    def glyph_basis(cp):
        return {'Ll': 'lowercase', 'Lu': 'uppercase'}.get(unicodedata.category(chr(cp))) if unicodedata.name(chr(cp), '').startswith('LATIN ') else None

    def step(self, a, b):
        return self.glyphs[a]['source_advance_px'] + self.kerns.get((a, b), 0.0)

    def profile(self, cp, basis):
        key = (cp, basis)
        if key not in self.filtered:
            self.filtered[key] = hu.source_depth_profile(self.glyphs[cp]['source_commands'], self.scale, self.windows[basis], hu.Settings(hu.PUBLISHED_RELATIVE_DEPTH, hu.PUBLISHED_VISUAL_DEPTH_FACTOR, 64))
        return self.filtered[key]

    def reference(self, basis, kind, text):
        a, b = map(ord, text)
        result = dict(
            reference_pair=text,
            basis=basis,
            class_key=kind,
            expected_facing=list(EXPECTED[kind]),
            status='unavailable',
            reason=None,
        )
        if a not in self.glyphs or b not in self.glyphs:
            return dict(result, reason='missing_reference_glyph')
        if self.windows[basis] is None:
            return dict(result, reason='missing_reference_window')
        faces = [self.faces[a, 'right'], self.faces[b, 'left']]
        result.update(facing=faces, source_step_px=self.step(a, b), measurement_window_px=self.windows[basis])
        if tuple((f['kind'] for f in faces)) != EXPECTED[kind]:
            return dict(result, reason='unsupported_reference_facing_elements')
        offset = faces[1]['source_support_x_px'] - faces[0]['source_support_x_px']
        target = self.step(a, b) + offset
        if target <= 0:
            return dict(result, reason='nonpositive_reference_gap', source_border_gap_px=target)
        reconstructed = target - offset
        result.update(status='available', reason=None, source_border_offset_px=offset, source_border_gap_px=target, reconstructed_step_px=reconstructed, reconstruction_error_px=reconstructed - self.step(a, b))
        assert math.isclose(reconstructed, self.step(a, b), abs_tol=1e-12)
        return result

    def pair(self, a, b):
        if (a, b) in self.pair_cache:
            return self.pair_cache[a, b]
        basis = pair_basis(a, b)
        step = self.step(a, b)
        faces = [self.faces[a, 'right'], self.faces[b, 'left']]
        result = dict(
            pair=chr(a) + chr(b),
            left=a,
            right=b,
            basis=basis,
            source_advance_px=self.glyphs[a]['source_advance_px'],
            source_pair_adjustment_px=self.kerns.get((a, b), 0.0),
            source_step_px=step,
            source_facing=faces,
            status='abstained',
            reason=None,
            class_key=None,
            reference_pair=None,
            source_border_offset_px=None,
            source_border_gap_px=None,
            target_border_gap_px=None,
            required_step_px=step,
            origin_shift_px=0.0,
            reverse_mixed_adaptation=False,
            generic_source_only_shared_step_px=step,
            generic_source_only_shared_shift_px=0.0,
            generic_source_only_status='abstained',
            generic_source_only_reason='unsupported_same_case_pair',
        )
        if basis not in ['lowercase', 'uppercase']:
            result['reason'] = 'unsupported_same_case_pair'
        elif self.windows[basis] is None:
            result['reason'] = 'missing_reference_window'
            result['generic_source_only_reason'] = 'missing_reference_window'
        else:
            pa, pb = (self.profile(a, basis), self.profile(b, basis))
            if pa.bounds is not None and pb.bounds is not None and walls.shared_ink_rows(pa, pb) and (basis in self.generic_targets):
                generic = self.generic_targets[basis] - hu.pair_offset(pa, pb)
                result.update(generic_source_only_shared_step_px=generic, generic_source_only_shared_shift_px=generic - step, generic_source_only_status='solved', generic_source_only_reason=None)
            else:
                result['generic_source_only_reason'] = 'empty_geometry' if pa.bounds is None or pb.bounds is None else 'no_shared_ink_rows' if not walls.shared_ink_rows(pa, pb) else 'generic_reference_unavailable'
            kinds = tuple((f['kind'] for f in faces))
            if any((k not in ['stem', 'curve'] for k in kinds)):
                result['reason'] = 'unsupported_or_ambiguous_facing_element'
            else:
                kind = 'stem_stem' if kinds == ('stem', 'stem') else 'curve_curve' if kinds == ('curve', 'curve') else 'mixed'
                reference = self.refs[basis, kind]
                offset = faces[1]['source_support_x_px'] - faces[0]['source_support_x_px']
                result.update(class_key=kind, reference_pair=reference['reference_pair'], source_border_offset_px=offset, source_border_gap_px=step + offset, reverse_mixed_adaptation=kinds == ('curve', 'stem'))
                if reference['status'] != 'available':
                    result.update(reason='reference_unavailable', reference_failure=reference['reason'])
                else:
                    target = reference['source_border_gap_px']
                    required = target - offset
                    result.update(status='solved', reason=None, target_border_gap_px=target, required_step_px=required, origin_shift_px=required - step)
        result['paper_like_composition_status'] = 'six_standard_solved' if result['status'] == 'solved' else 'generic_fallback_solved' if result['generic_source_only_status'] == 'solved' else 'source_preserved_abstention'
        result['paper_like_composition_shift_px'] = result['origin_shift_px'] if result['status'] == 'solved' else result['generic_source_only_shared_shift_px']
        result['paper_like_composition_step_px'] = step + result['paper_like_composition_shift_px']
        self.pair_cache[a, b] = result
        return result

    def summarize(self, domain):
        records = [self.pair(*pair) for pair in domain]
        eligible = [r for r in records if r['basis'] in ['lowercase', 'uppercase']]
        supported = [r for r in records if r['status'] == 'solved']
        return dict(
            occurrences=len(records),
            eligible_same_case_occurrences=len(eligible),
            supported_occurrences=len(supported),
            supported_distinct_pairs=len({r['pair'] for r in supported}),
            eligible_coverage=len(supported) / len(eligible) if eligible else None,
            statuses=dict(Counter((r['status'] for r in records))),
            reasons=dict(Counter((r['reason'] or 'solved' for r in records))),
            supported_classes=dict(Counter((r['class_key'] for r in supported))),
            reverse_mixed_occurrences=sum((r['reverse_mixed_adaptation'] for r in supported)),
            source_only_origin_shift=dict(
                overall=distribution((r['origin_shift_px'] for r in records)),
                eligible_same_case=distribution((r['origin_shift_px'] for r in eligible)),
                supported_only=distribution((r['origin_shift_px'] for r in supported)),
            ),
            paper_like_composition_shift=dict(
                overall=distribution((r['paper_like_composition_shift_px'] for r in records)),
                eligible_same_case=distribution((r['paper_like_composition_shift_px'] for r in eligible)),
                six_standard_supported_only=distribution((r['paper_like_composition_shift_px'] for r in supported)),
            ),
            composition_statuses=dict(Counter((r['paper_like_composition_status'] for r in records))),
            generic_nn_reset_source_only_shift=dict(
                overall=distribution((r['generic_source_only_shared_shift_px'] for r in records)),
                eligible_same_case=distribution((r['generic_source_only_shared_shift_px'] for r in eligible)),
                six_standard_supported_only=distribution((r['generic_source_only_shared_shift_px'] for r in supported)),
            ),
            unique_pairs=[dict(
                pair=pair,
                count=count,
            ) for pair, count in Counter((r['pair'] for r in records)).items()],
        )

CORPUS_IDS = ("lynx-lowercase", "lynx-uppercase", "aaron-abraham")



def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()



def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")



def load_presets(path):
    """Load the declared assessment texts without using them for calibration."""
    records = json.loads(Path(path).read_text())
    if not isinstance(records, list):
        raise ValueError("presets must be a JSON list")
    presets = {}
    for record in records:
        if (not isinstance(record, dict) or not isinstance(record.get("id"), str)
                or not isinstance(record.get("text"), str)):
            raise ValueError("preset entries require string id and text")
        if record["id"] in presets:
            raise ValueError("preset ids must be distinct")
        presets[record["id"]] = record["text"]
    missing = set(CORPUS_IDS) - presets.keys()
    if missing:
        raise ValueError("missing assessment presets: " + ", ".join(sorted(missing)))
    return presets



def validate_capture(capture):
    """Reject malformed identities/metrics before producing diagnostic outputs."""
    if capture.get("schema_version") != "contextual-spacing-capture-v1":
        raise ValueError("expected contextual-spacing-capture-v1")
    for key in ("size_px", "units_per_em"):
        value = capture[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be finite and positive")
    glyphs = {}
    for glyph in capture["glyphs"]:
        cp = glyph["codepoint"]
        if type(cp) is not int or not 0 <= cp <= 0x10FFFF or 0xD800 <= cp <= 0xDFFF or cp in glyphs:
            raise ValueError("capture codepoints must be valid and distinct")
        advance = glyph["source_advance_px"]
        if isinstance(advance, bool) or not isinstance(advance, (int, float)) or not math.isfinite(advance):
            raise ValueError("source advances must be finite")
        glyphs[cp] = glyph
    if not glyphs:
        raise ValueError("capture repertoire must not be empty")
    pairs = set()
    for pair in capture["source_pairs"]:
        key = (pair["left"], pair["right"])
        if key in pairs or any(cp not in glyphs for cp in key):
            raise ValueError("source pairs must be distinct and inside the repertoire")
        adjustment = pair["adjustment_px"]
        if isinstance(adjustment, bool) or not isinstance(adjustment, (int, float)) or not math.isfinite(adjustment):
            raise ValueError("source pair adjustments must be finite")
        pairs.add(key)



def evaluate_capture(capture, capture_path, label, presets):
    """Retain both window policies and every tested source relationship."""
    validate_capture(capture)
    font = dict(font=label, axes=capture.get("axes", {}),
                capture_path=str(capture_path), capture_sha256=sha256(capture_path),
                source_metric_quantization=capture.get("source_metric_quantization"), policies={})
    for policy in POLICIES:
        model = Experiment(capture, policy)
        corpora = {}
        for name in CORPUS_IDS:
            text = presets[name]
            available = lambda pair: all(ord(char) in model.glyphs for char in pair)
            corpora[name] = model.summarize(tuple(map(ord, pair)) for pair in zip(text, text[1:]) if available(pair))
            corpora[name]["missing_capture_pairs"] = dict(Counter(
                "".join(pair) for pair in zip(text, text[1:]) if not available(pair)))
        alphabet = [ord(char) for char in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" if ord(char) in model.glyphs]
        corpora["source-alphabet-52x52"] = model.summarize((a, b) for a in alphabet for b in alphabet)
        classifications = [dict(codepoint=cp, character=chr(cp), basis=model.glyph_basis(cp), side=side, **face)
                           for (cp, side), face in sorted(model.faces.items())]
        reversals = []
        for cp, glyph in model.glyphs.items():
            basis = model.glyph_basis(cp)
            if basis is None or model.windows[basis] is None:
                continue
            for side in ("left", "right"):
                original = model.faces[(cp, side)]
                reverse = hu.classify_face(reversed_contours(glyph["source_commands"]), model.scale,
                                           model.windows[basis], side)
                if original != reverse:
                    reversals.append(dict(codepoint=cp, character=chr(cp), side=side,
                                          original=original, reversed=reverse))
        font["policies"][policy] = dict(
            windows=model.windows, references=list(model.refs.values()),
            generic_nn_filtered_source_targets=model.generic_targets,
            classifications=classifications, classifier_reverse_contour_differences=reversals,
            corpora=corpora, reported_pairs=[model.pair(*map(ord, pair)) for pair in REPORTED
                                          if all(ord(char) in model.glyphs for char in pair)],
            pair_records=list(model.pair_cache.values()))
    return font



def summarize_font(font):
    fields = ("occurrences", "eligible_same_case_occurrences", "supported_occurrences", "eligible_coverage",
              "source_only_origin_shift", "generic_nn_reset_source_only_shift", "paper_like_composition_shift",
              "composition_statuses", "reasons")
    return dict(font=font["font"], policies={policy: dict(
        windows=data["windows"],
        reference_statuses={record["reference_pair"]: record["status"] for record in data["references"]},
        reference_gaps={record["reference_pair"]: record.get("source_border_gap_px") for record in data["references"]},
        reverse_contour_differences=len(data["classifier_reverse_contour_differences"]),
        corpora={name: {key: record[key] for key in fields} for name, record in data["corpora"].items()})
        for policy, data in font["policies"].items()})



def run_probe(output_directory, capture_paths, presets_path):
    """Publish complete JSON in a new directory; never replace prior evidence."""
    output = Path(output_directory)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output directory already exists: {output}")
    paths = [Path(path) for path in capture_paths]
    if not paths:
        raise ValueError("provide at least one source capture")
    presets = load_presets(presets_path)
    labels = [path.parent.name if path.stem == "capture" else path.stem for path in paths]
    reserved = {"summary", "identities"}
    label_keys = [unicodedata.normalize("NFC", label).casefold() for label in labels]
    if (any(not label or len(label.encode("utf-8")) > 200 or key in reserved
            for label, key in zip(labels, label_keys))
            or len(set(label_keys)) != len(label_keys)
            or len({path.resolve() for path in paths}) != len(paths)):
        raise ValueError("capture output labels must be nonempty, bounded, distinct and not reserved")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"capture not found: {path}")
    checks = analytic_checks()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    reservation = False
    try:
        fonts = []
        for label, path in zip(labels, paths):
            font = evaluate_capture(json.loads(path.read_text()), path, label, presets)
            write_json(stage / f"{label}.json", font)
            fonts.append(summarize_font(font))
        helper_paths = [Path(__file__), Path(hu.__file__), Path(walls.__file__),
                        Path(__file__).with_name("estimator.py"), Path(__file__).with_name("calibration.py")]
        source_hashes = {path.name: sha256(path) for path in helper_paths}
        summary = dict(schema="source-stem-curve-experiment-v1", status="completed_source_only",
                       policy="six standards; exact source support x; full source metrics; unordered mixed-reference adaptation explicitly flagged; no rounding or clearance; unsupported positions unchanged",
                       analytic_checks=checks, source_hashes=source_hashes, fonts=fonts)
        write_json(stage / "summary.json", summary)
        identities = dict(tool_and_helpers={str(path.resolve()): sha256(path) for path in helper_paths},
                          captures={str(path.resolve()): sha256(path) for path in paths},
                          presets=dict(path=str(Path(presets_path).resolve()), sha256=sha256(presets_path)),
                          outputs={path.name: sha256(path) for path in stage.glob("*.json")})
        write_json(stage / "identities.json", identities)
        output.mkdir()
        reservation = True
        os.replace(stage, output)
        reservation = False
        return summary
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if reservation:
            output.rmdir()



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("captures", metavar="CAPTURE", type=Path, nargs="+")
    parser.add_argument("--presets", type=Path, default=Path(__file__).with_name("presets.json"),
                        help="preset JSON containing lynx-lowercase, lynx-uppercase and aaron-abraham")
    args = parser.parse_args(argv)
    try:
        summary = run_probe(args.output_directory, args.captures, args.presets)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(dict(status=summary["status"], captures=len(summary["fonts"]),
                          output_directory=str(args.output_directory))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
