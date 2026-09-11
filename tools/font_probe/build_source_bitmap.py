"""Consolidated source-to-bitmap pipeline (font-legibility plan phase 1).

One executable entry point from original source fonts and configuration
through preparation, feature extraction, fitting, scan conversion and
bitmap/metric export. This replaces the saved-checkpoint chain that
``build_cumulative_recovery.py`` continues via ``cumulative_inputs.py``:

geometric candidate -> cumulative prepare/reflect -> component symmetry
-> round symmetry ->+- curved-width links --+-> stem-relative terminals
                    +-> source junctions ---+   (newest wins per glyph)
-> whole curved-stroke recovery -> export.

The curved-width and source-junction experiments are parallel branches
from the round-level rendering: neither reads the other's output, and
downstream selection prefers the newer branch per glyph with explicit
newest-wins merges. A recorded change is never silently replaced.

Stage order, inputs, ownership and failure behavior are explicit below;
each stage calls the same approved fitting entry point the frozen
comparison script used, with the same admission conditions. Held and
unsupported cases stay visible; a recorded change is never silently
replaced by an older rendering.

Frozen output artifacts are never production inputs here. The runtime
generator may read only original source fonts, job configuration, Python
sources and files it wrote itself into its fresh output directory or its
temporary work directory; every data read passes through ``use_input``,
which enforces that boundary and records provenance. Frozen specimens
remain test references (see ``test_build_source_bitmap.py``).

Geometry helpers accept coordinates, outlines, scales and equation
records only: no character, font-family or size exception tables.
Per-glyph selection lives in ``run`` (the adapter), as before.

Regenerate the approved specimen from the repository root::

    OPENBLAS_NUM_THREADS=1 PYTHONPATH=tools/font_probe \\
        tools/font_probe/.venv/bin/python tools/font_probe/build_source_bitmap.py

The output directory ``tools/font_probe/out/source-bitmap-v1/`` must be
empty (or absent). It contains per-face specimens (HTML with native and
enlarged PNGs under ``img/``), per-face ``*-bitmap.json`` bitmap/metric
exports from the exact final render, ``report.json`` with repo-relative
input provenance and tool versions, and combined ``*-candidate.ttf``
fonts. Unsupported cases are excluded from exported Unicode maps and
listed explicitly.

The native adapter contract is unchanged: ``compile_baseline`` emits
direct SCFS coordinates for one requested ppem per face/size; other
sizes receive no adapter hints.
"""

from array import array
from collections import Counter
from copy import deepcopy
from pathlib import Path
import html
import json
import shutil
import tempfile

import freetype as ft
import numpy as np
from fontTools import subset
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.ttProgram import Program

from audit_terminal_coverage import coords
from build_geometric_candidate import REPERTOIRE, geometry as geometric_data
from check_shamir_baseline import digest
from compare_diagonal_widths import metrics
from compare_paper_prototypes import render, pixels
from compare_shamir_pipeline import CHARS, SIZES, instance
from cross_section_widths import export_graph, system
from cumulative_hinter import prepare, reflect, finalize, validate_geometry
from curved_width_links import fit as curved_width_fit, detect as curved_detect
from repeated_component_symmetry import fit as component_fit
from repeated_rings import contours
from round_component_fit import fit as round_fit
from stem_relative_terminals import fit as terminal_fit
from geometric_candidate import correct, finish
from outline_relationships import reversed_edges
from shamir_baseline_solver import compile_baseline, evaluate_baseline
from shamir_boundary import normalize_boundaries
from shamir_geometry import from_font
from shamir_model import build_font
from shamir_reorientation import Unsupported
from shamir_representative_search import representative_override
from shamir_segment_fit import prepared_glyph
import source_bitmap_output as output_mod
 
HERE = Path(__file__).resolve().parent
FACES = ('roboto', 'literata', 'source-sans-3')
OUTPUT_NAME = 'source-bitmap-v1'
STAGE_ORDER = (
    'source-instantiation',
    'baseline-model',
    'geometric-candidate',
    'cumulative-fit',
    'component-symmetry',
    'round-symmetry',
    'curved-width-links',
    'source-junctions',
    'stem-relative-terminals',
    'curved-stroke-recovery',
    'export',
)


class ForbiddenInput(ValueError):
    """A historical output checkpoint was requested as a generation input."""


def _export_row_status(char, live, row, fitted, reference_ink, source,
                       advance, audit, actual, ink, exported_advance):
    """Verify one exported case against its expected record; stamp the row.

    Returns the ink delta. The upstream audit recorded is looked up from
    ``live`` by this row's own character: reusing a loop variable left
    over from the expected-record pass would stamp every row with the
    last character's owners/order, so the lookup stays per-character.
    """
    if np.max(abs(actual - fitted)) > 1 / 128 + 1e-9:
        raise ValueError(f'export native drift: {char!r}')
    if exported_advance != advance:
        raise ValueError(f'export advance drift: {char!r}')
    if metrics(ink, actual, source)['white_counters'] != \
            metrics(reference_ink, actual, source)['white_counters']:
        raise ValueError(f'export counter drift: {char!r}')
    delta = len(ink ^ reference_ink)
    row.update(status='changed' if delta else 'retained', changed_pixels=delta,
               native_verified=True, audit=audit,
               upstream_audit=deepcopy(live[char]['audit']))
    return delta


class Pipeline:
    """Fresh-output generator; all data reads pass through ``use_input``."""

    def __init__(self, output):
        self.output = Path(output)
        if self.output.resolve().is_relative_to((HERE / 'out').resolve()) is False:
            raise ValueError('output must live under tools/font_probe/out')
        self.work = Path(tempfile.mkdtemp(prefix='source-bitmap-'))
        self.inputs = {}
        self._resolved = {}
        self.provenance = dict(stages=list(STAGE_ORDER))

    def close(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def use_input(self, path):
        """Record a generation input; refuse historical output checkpoints.

        Only repo-relative display paths and content hashes enter the
        serialized provenance. Resolved local paths stay in memory for
        change verification and never reach the report, so the report
        describes reusable inputs instead of this machine's layout.
        """
        path = Path(path)
        resolved = path.resolve()
        out_root = (HERE / 'out').resolve()
        own = self.output.resolve()
        if resolved.is_relative_to(out_root) and not resolved.is_relative_to(own) \
                and resolved != own:
            raise ForbiddenInput(f'historical output is not a generation input: {path}')
        display = output_mod.repo_relative(resolved)
        self.inputs[display] = digest(path)
        self._resolved[display] = resolved
        return path

    def verify_inputs_unchanged(self):
        for display, sha in self.inputs.items():
            if display.endswith('.py'):
                continue
            if digest(self._resolved[display]) != sha:
                raise ValueError(f'input changed during generation: {display}')

    def note_sources(self):
        for name in HERE.glob('*.py'):
            rel = output_mod.repo_relative(name)
            if rel not in self.inputs:
                self.inputs[rel] = digest(name)
                self._resolved[rel] = name.resolve()

    def verify_sources(self):
        for name in HERE.glob('*.py'):
            rel = output_mod.repo_relative(name)
            if rel in self.inputs and digest(name) != self.inputs[rel]:
                raise ValueError(f'source changed during generation: {rel}')

    # -- stage 0: source fonts and configuration ---------------------------

    def job_axes(self, name, size):
        job_path = HERE.parent / 'font_generator' / 'examples' / f'{name}.json'
        job = json.loads(self.use_input(job_path).read_text())
        source = (job_path.parent / job['font']).resolve()
        self.use_input(source)
        if digest(source) != job['provenance']['expected_sha256']:
            raise ValueError(f'font checksum mismatch: {source}')
        axes = dict(job['settings']['axes'])
        axes['wght'] = 400
        if 'opsz' in axes:
            axes['opsz'] = min(72, max(7, size))
        return source, axes, job

    def instantiate(self, key, name, size):
        """Variable-font instantiation from source fonts (no saved statics)."""
        source, axes, _ = self.job_axes(name, size)
        target = self.work / f'{key}-source.ttf'
        instance(source, target, axes)
        self.provenance.setdefault('instantiation', {})[key] = dict(
            font=name, size=size, axes=axes,
            source=output_mod.repo_relative(source),
            source_sha256=self.inputs[output_mod.repo_relative(source)],
            static_sha256=digest(target))
        return target

    # -- stage 1: preparation, feature extraction, fitting -----------------

    def baseline(self, key, size, static_path):
        """Regenerate constraint records from the instantiated source.

        Mirrors the representative-comparison construction: baseline
        profile at the requested ppem with the bounded coordinated
        representative search. Returns (experiment_font, records).
        """
        target = self.work / f'{key}-experiment.ttf'
        with representative_override(256) as audits:
            model = build_font(static_path, target, CHARS, profile='baseline', ppem=size)
        self.provenance.setdefault('representative_search', {})[key] = dict(
            budget=256, evaluations=sum(a['evaluations'] for a in audits),
            exhausted=sum(a['budget_exhausted'] for a in audits))
        return target, model['records']

    # -- shared compile/scan-conversion helpers ----------------------------

    @staticmethod
    def install(base_path, target_path, jobs):
        """Compile fitted coordinates to native SCFS programs (batched).

        Mirrors ``compare_diagonal_widths.build`` per glyph: each
        ``(char, size, em, outline, fitted)`` job compiles
        ``export_graph`` coordinates for one requested ppem and replaces
        that glyph's program. Glyph programs are independent, so one
        saved font carries every changed glyph of the stage.
        """
        natives = {}
        with TTFont(str(base_path)) as font:
            em = font['head'].unitsPerEm
            for char, size, outline, fitted in jobs:
                name = font.getBestCmap()[ord(char)]
                original = font['glyf'][name].getCoordinates(font['glyf'])
                if not np.array_equal(np.asarray(original[0]), np.asarray(outline[0])) \
                        or list(original[1]) != list(outline[1]):
                    raise ValueError(f'outline changed during generation: {char!r}')
                graph = export_graph(fitted, size / em)
                meta = evaluate_baseline(graph, outline[0], size, em)[1]
                assembly, _ = compile_baseline(graph, outline[0], size, em)
                font['glyf'][name].program = Program()
                font['glyf'][name].program.fromAssembly(assembly)
                natives[char] = (np.asarray(meta['native_points_px']),
                                 original, font['hmtx'][name])
            font['maxp'].maxStackElements = max(font['maxp'].maxStackElements, 16)
            font.save(target_path)
        face = ft.Face(str(target_path))
        checked = {}
        with TTFont(str(target_path)) as font:
            for char, size, outline, fitted in jobs:
                actual = coords(face, char, size)
                if np.max(abs(actual - natives[char][0])) > 1e-8:
                    raise ValueError(f'native prediction mismatch: {char!r}')
                if np.max(abs(actual - np.asarray(fitted))) > 1 / 128 + 1e-9:
                    raise ValueError(f'native coordinate mismatch: {char!r}')
                recovered = font['glyf'][font.getBestCmap()[ord(char)]].getCoordinates(font['glyf'])
                if not all(list(a) == list(b) for a, b in zip(natives[char][1], recovered)):
                    raise ValueError(f'outline not preserved: {char!r}')
                checked[char] = actual
        return checked

    def stage_font(self, key, stage, base_path, jobs):
        """Compile one stage's changed glyphs; return (font_path, natives)."""
        if not jobs:
            return base_path, {}
        target = self.work / f'{key}-{stage}.ttf'
        return target, self.install(base_path, target, jobs)

    # -- stage 2: uniform geometric candidate ------------------------------

    def geometric(self, key, size, experiment_path, records):
        """Run the fixed correction sequence for every available record.

        Mirrors ``build_geometric_candidate.run``: identity-free
        ``correct``/``finish`` on the regenerated constraint records.
        Returns (candidate_font, outcomes) where outcomes maps char to
        dict(status, expected, result); only verified glyphs continue.
        """
        outcomes = {}
        with TTFont(str(experiment_path)) as font:
            cmap = font.getBestCmap()
            em = font['head'].unitsPerEm
            if 'cvt ' not in font:
                font['cvt '] = newTable('cvt ')
                font['cvt '].values = array('h')
            built = []
            for code in REPERTOIRE:
                char = chr(code)
                if code not in cmap or char not in records:
                    outcomes[char] = dict(status='unsupported',
                                          reason='missing outline or constraint record')
                    continue
                points, ends, flags = font['glyf'][cmap[code]].getCoordinates(font['glyf'])
                data = geometric_data(records[char], points, ends, flags, size, em)
                try:
                    result = correct(data)
                    assembly, cvts, expected = finish(result, data, len(font['cvt '].values))
                except np.linalg.LinAlgError as exc:
                    outcomes[char] = dict(status='failed',
                                          reason=f'numerical diagnostic failure: {exc}')
                    continue
                except (ValueError, Unsupported) as exc:
                    outcomes[char] = dict(status='unsupported', reason=str(exc))
                    continue
                font['cvt '].values.extend(cvts)
                glyph = font['glyf'][cmap[code]]
                glyph.program = Program()
                glyph.program.fromAssembly(assembly)
                built.append((char, result, expected,
                              tuple(map(tuple, points)), tuple(ends), tuple(flags)))
                outcomes[char] = dict(status='verified', expected=expected, result=result,
                                      outline=(tuple(map(tuple, points)), tuple(ends), tuple(flags)))
            keep = {ord(char) for char, _, _, _, _, _ in built}
            for tag in ('GSUB', 'morx', 'mort'):
                if tag in font:
                    del font[tag]
            options = subset.Options()
            options.recalc_max_context = False
            sub = subset.Subsetter(options=options)
            sub.populate(unicodes=keep)
            sub.subset(font)
            for table in font['cmap'].tables:
                if hasattr(table, 'cmap'):
                    table.cmap = {code: name for code, name in table.cmap.items() if code in keep}
            font['maxp'].maxSizeOfInstructions = max(
                (len(font['glyf'][n].program.getBytecode()) if hasattr(font['glyf'][n], 'program') else 0)
                for n in font.getGlyphOrder())
            font['maxp'].maxStackElements = max(font['maxp'].maxStackElements, 16)
            target = self.work / f'{key}-candidate.ttf'
            font.save(target)
        with TTFont(str(target)) as exported:
            assert set(exported.getBestCmap()) == keep
            assert not any(tag in exported for tag in ('GSUB', 'morx', 'mort'))
        # Native-coordinate check per exported candidate (mirrors the adapter).
        face = ft.Face(str(target))
        for char, result, expected, _, _, _ in built:
            error = float(np.max(abs(coords(face, char, size) - expected)))
            if error > 1 / 64 + 1e-7:
                raise AssertionError((key, char, error))
            outcomes[char]['native_error_px'] = error
        return target, outcomes

    # -- stage 3: cumulative prepare/reflect --------------------------------

    def cumulative(self, key, size, candidate_path, experiment_path, records, outcomes):
        """Stage-owned joint fit with explicit reflection (v6 equivalent).

        Mirrors ``compare_cumulative_hinter.run`` per glyph: geometric
        rebuild agreement, coordinated support and joint fit via
        ``prepare``, then experimental reflection via ``reflect``.
        Exceptions are explicit rejections that later stages must carry
        as upstream rejections, never silent fallbacks.
        """
        cases = {}
        with TTFont(str(experiment_path)) as font:
            em = font['head'].unitsPerEm
            outlines = {}
            for char, outcome in outcomes.items():
                if outcome['status'] != 'verified':
                    continue
                glyph = font['glyf'][font.getBestCmap()[ord(char)]]
                outlines[char] = glyph.getCoordinates(font['glyf'])
        jobs, currents = [], {}
        base_face = ft.Face(str(candidate_path))
        for char, outcome in outcomes.items():
            if outcome['status'] != 'verified':
                continue
            row = dict(key=key, char=char)
            cases[char] = row
            try:
                points, ends, flags = outlines[char]
                data = geometric_data(records[char], points, ends, flags, size, em)
                base, current, audit = prepare(data, records[char])
                baseline_q = coords(base_face, char, size)
                if np.max(abs(baseline_q - base)) >= 1 / 64 + 1e-7:
                    raise AssertionError('geometric rebuild differs from candidate')
                if np.max(abs(current - baseline_q)) < 1e-9:
                    middle_ink = pixels(render(base_face, char, size, hinted=True))
                    final, reflection = reflect(data, records[char], current, audit, middle_ink)
                    currents[char] = (current, final, audit, reflection, baseline_q)
                else:
                    jobs.append((char, size, outlines[char], current))
                    currents[char] = (current, None, audit, None, baseline_q)
                row['audit'] = audit
            except (ValueError, AssertionError, np.linalg.LinAlgError, ft.FT_Exception) as exc:
                row.update(status='rejected', reason=str(exc))
        current_font, natives = self.stage_font(key, 'cumulative-current', candidate_path, jobs)
        # Reflection runs on fitted floats; its output compiles like any stage.
        after_jobs, rows = [], {}
        for char, (current, final, audit, reflection, baseline_q) in currents.items():
            row = cases[char]
            try:
                if final is None:
                    ink = pixels(render(ft.Face(str(current_font)), char, size, hinted=True))
                    data_points, data_ends, data_flags = outlines[char]
                    data = geometric_data(records[char], data_points, data_ends, data_flags, size, em)
                    final, reflection = reflect(data, records[char], current, audit, ink)
                    if np.array_equal(final, current):
                        row.update(status=audit['status'], audit=audit, reflection=reflection)
                        rows[char] = (current, audit)
                        continue
                after_jobs.append((char, size, outlines[char], final))
                rows[char] = (final, audit)
                row.update(status=audit['status'], audit=audit, reflection=reflection)
            except (ValueError, AssertionError, np.linalg.LinAlgError, ft.FT_Exception) as exc:
                row.update(status='rejected', reason=str(exc))
                rows.pop(char, None)
        after_font, after_natives = self.stage_font(key, 'cumulative-after', current_font, after_jobs)
        resolved = {}
        for char, (final, audit) in rows.items():
            resolved[char] = after_natives.get(char, natives.get(char))
            if resolved[char] is None:
                resolved[char] = coords(ft.Face(str(after_font)), char, size)
        return after_font, cases, resolved, rows

    # -- stages 4-8: symmetry, width, junction and terminal fits -----------

    def read_stage_inputs(self, font_path, chars, size, outlines):
        """Native coordinates, bitmaps and outlines from a stage font."""
        face = ft.Face(str(font_path))
        seen = {}
        with TTFont(str(font_path)) as font:
            em = font['head'].unitsPerEm
            for char in chars:
                points, ends, flags = font['glyf'][font.getBestCmap()[ord(char)]].getCoordinates(
                    font['glyf'])
                expected = outlines[char]
                if not np.array_equal(np.asarray(points), np.asarray(expected[0])) \
                        or list(ends) != list(expected[1]) or list(flags) != list(expected[2]):
                    raise ValueError(f'source outline changed between stages: {char!r}')
                seen[char] = (points, ends, flags,
                              render(face, char, size, hinted=True),
                              coords(face, char, size),
                              font['hmtx'][font.getBestCmap()[ord(char)]])
        return em, seen

    def symmetry_stages(self, key, size, prev_font, records, static_path, live, case_rows):
        """Component then round symmetry (v2/v4 equivalents), in order."""
        for stage, kind in (('component-symmetry', 'component'), ('round-symmetry', 'round')):
            em, seen = self.read_stage_inputs(
                prev_font, sorted(live), size, {c: live[c]['outline'] for c in live})
            before_ink = {char: pixels(seen[char][3]) for char in live}
            jobs = []
            for char in sorted(live):
                row = case_rows[char]
                if row.get('status') == 'rejected':
                    row['stages'][stage] = 'upstream-rejected'
                    continue
                points, ends, flags, before, q, _ = seen[char]
                ownership = live[char]['audit']['ownership']
                face = ft.Face(str(prev_font))

                def raster(candidate, ids, factor, _face=face, _char=char, _size=size):
                    isolated = np.zeros_like(np.asarray(candidate, float))
                    isolated[ids] = np.asarray(candidate, float)[ids] * factor
                    return pixels(render(_face, _char, _size * factor,
                                         points=isolated, hinted=False))

                try:
                    if kind == 'component':
                        after, audit = component_fit(
                            points, q, ends, flags, em, size / em,
                            pixels(before), ownership, raster=raster)
                    else:
                        after, audit = round_fit(
                            points, q, flags, ends, em, size, records[char], ownership, raster)
                    row['components'] = audit
                    if not audit:
                        row['stages'][stage] = 'no-match'
                        continue
                    validate_geometry(np.asarray(points) * size / em, after,
                                      'component coordination')
                    if reversed_edges(np.asarray(points) * size / em, after, ends, flags):
                        raise ValueError('cardinal edge inversion')
                    if np.array_equal(q, after):
                        row['stages'][stage] = 'unchanged'
                        continue
                    jobs.append((char, size, (points, ends, flags), after))
                    row['stages'][stage] = 'pending-compile'
                except (ValueError, AssertionError) as exc:
                    row['stages'][stage] = 'held'
                    row.setdefault('holds', {})[stage] = str(exc)
            prev_font, _ = self.stage_font(key, stage, prev_font, jobs)
            after_face = ft.Face(str(prev_font))
            for char in sorted(live):
                row = case_rows[char]
                if row['stages'].get(stage) == 'pending-compile':
                    delta = len(before_ink[char] ^ pixels(render(after_face, char, size, hinted=True)))
                    row['stages'][stage] = 'changed' if delta else 'unchanged'
                    row['changed_pixels_' + stage] = delta
        return prev_font

    def overlay(self, key, size, stage, base_path, overlays):
        """Newest-wins per-glyph merge for diamond branches.

        ``overlays`` is oldest-to-newest ``(font_path, produced_chars)``.
        A recorded change is never silently replaced: every produced
        glyph carries its compiled program forward, and anything else
        keeps the older rendering explicitly.
        """
        target = self.work / f'{key}-{stage}.ttf'
        programs = {}
        for font_path, produced in overlays:
            with TTFont(str(font_path)) as font:
                for char in produced:
                    glyph = font['glyf'][font.getBestCmap()[ord(char)]]
                    programs[char] = deepcopy(glyph.program)
        with TTFont(str(base_path)) as font:
            for char, program in programs.items():
                name = font.getBestCmap()[ord(char)]
                font['glyf'][name].program = deepcopy(program)
            font['maxp'].maxStackElements = max(font['maxp'].maxStackElements, 16)
            font.save(target)
        check = ft.Face(str(target))
        for font_path, produced in overlays:
            face = ft.Face(str(font_path))
            for char in produced:
                newest = None
                for later_path, later_produced in overlays:
                    if char in later_produced:
                        newest = later_path
                if newest == font_path and np.max(
                        abs(coords(check, char, size) - coords(face, char, size))) > 1e-9:
                    raise ValueError(f'merge changed native coordinates: {char!r}')
        return target

    def branch_stage(self, key, size, base_font, records, static_path, live, case_rows,
                     stage, junctions):
        """One diamond branch from the round-level font (v2/v1 equivalent).

        Both the curved-width and source-junction experiments read the
        round-level rendering, never each other's output. Returns
        (branch_font, produced) where produced holds every glyph whose
        compiled program this branch verified (changed or not).
        """
        em, seen = self.read_stage_inputs(
            base_font, sorted(live), size, {c: live[c]['outline'] for c in live})
        before_ink = {char: pixels(seen[char][3]) for char in live}
        jobs, produced = [], set()
        for char in sorted(live):
            row = case_rows[char]
            if row.get('status') == 'rejected':
                row['stages'][stage] = 'upstream-rejected'
                continue
            points, ends, flags, before, q, _ = seen[char]
            try:
                if junctions:
                    with TTFont(str(static_path)) as source:
                        normalize_boundaries(source, [char])
                        model = from_font(source, char, baseline=True)
                    model.update(scale=size / em, source_junctions=True)
                    if not any(f['new'] for f in curved_detect(model)):
                        row['stages'][stage] = 'no-match'
                        continue
                else:
                    with TTFont(str(base_font)) as current:
                        model = from_font(current, char, baseline=True)
                    model['scale'] = size / em
                cs = contours(np.asarray(points), flags, ends)
                outer = sum(not any(j != i and b['poly'].contains(a['poly'])
                                    for j, b in enumerate(cs)) for i, a in enumerate(cs))
                if outer != 1:
                    row['stages'][stage] = 'deferred-disconnected'
                    continue
                prepared, _, _ = prepared_glyph(model)
                if not np.array_equal(prepared.coordinates, points) \
                        or list(prepared.endPtsOfContours) != list(ends):
                    raise ValueError('prepared point mapping differs')
                after, audit = curved_width_fit(
                    model, q, live[char]['audit']['ownership'], reconstruct_curves=True)
                row['width_audit_' + stage] = audit
                if not audit['new_pairs']:
                    row['stages'][stage] = 'no-match'
                    continue
                if not audit['links']:
                    row['stages'][stage] = 'already-consistent'
                    continue
                validate_geometry(np.asarray(points) * size / em, after, 'curved width links')
                if reversed_edges(np.asarray(points) * size / em, after, ends, flags):
                    raise ValueError('cardinal edge inversion')
                matrix, _ = system(records[char]['graph'], len(points), size / em)
                ids = [i for i, c in enumerate(records[char]['graph']['constraints'])
                       if c.get('metric') or c['kind'].startswith('P')]
                residual = float(np.max(abs(matrix[ids] @ (after - q).ravel()))) if ids else 0.
                if residual > 1 / 64 + 1e-9:
                    raise ValueError('protected metric/parameter changes')
                candidate = self.install(base_font, self.work / f'{key}-{stage}-{ord(char):04x}.ttf',
                                         [(char, size, (points, ends, flags), after)])
                native = candidate[char]
                check_before = pixels(before)
                check_after = pixels(render(ft.Face(str(
                    self.work / f'{key}-{stage}-{ord(char):04x}.ttf')), char, size, hinted=True))
                if metrics(check_before, q, np.asarray(points) * size / em)['white_counters'] != \
                        metrics(check_after, native, np.asarray(points) * size / em)['white_counters']:
                    raise ValueError('counter topology changes')
                jobs.append((char, size, (points, ends, flags), after))
                row['stages'][stage] = 'pending-compile'
            except (ValueError, AssertionError) as exc:
                row['stages'][stage] = 'held'
                row.setdefault('holds', {})[stage] = str(exc)
        branch_font, _ = self.stage_font(key, stage, base_font, jobs)
        after_face = ft.Face(str(branch_font))
        for char in sorted(live):
            row = case_rows[char]
            if row['stages'].get(stage) == 'pending-compile':
                delta = len(before_ink[char] ^ pixels(render(after_face, char, size, hinted=True)))
                row['stages'][stage] = 'changed' if delta else 'unchanged'
                row['changed_pixels_' + stage] = delta
                produced.add(char)
        return branch_font, produced

    def terminal_stage(self, key, size, prev_font, records, static_path, live, case_rows):
        """Stem-relative terminal placement (v1 equivalent)."""
        stage = 'stem-relative-terminals'
        em, seen = self.read_stage_inputs(
            prev_font, sorted(live), size, {c: live[c]['outline'] for c in live})
        before_ink = {char: pixels(seen[char][3]) for char in live}
        jobs = []
        for char in sorted(live):
            row = case_rows[char]
            if row.get('status') == 'rejected':
                row['stages'][stage] = 'upstream-rejected'
                continue
            points, ends, flags, before, q, advance = seen[char]
            try:
                with TTFont(str(static_path)) as source:
                    normalize_boundaries(source, [char])
                    model = from_font(source, char, baseline=True)
                model['scale'] = size / model['em']
                prepared, _, _ = prepared_glyph(model)
                if not np.array_equal(prepared.coordinates, points) \
                        or list(prepared.endPtsOfContours) != list(ends):
                    raise ValueError('point mapping differs')
                after, audit = terminal_fit(model, q, live[char]['audit']['ownership'])
                row['terminals'] = audit
                if not audit:
                    row['stages'][stage] = 'no-change'
                    continue
                validate_geometry(np.asarray(points) * model['scale'], after,
                                  'stem-relative terminal')
                if reversed_edges(np.asarray(points) * model['scale'], after, ends, flags):
                    raise ValueError('cardinal edge inversion')
                record = records[char]
                matrix, _ = system(record['graph'], len(points), model['scale'])
                tips = {a['tip'] for a in audit}
                graph_cs = record['graph']['constraints']
                released = [i for i, c in enumerate(graph_cs)
                            if c.get('metric') and abs(c['normal'][0]) == 1
                            and tips.intersection([c['point'], *c.get('sources', [])])]
                if not released:
                    raise ValueError('no outline dimension constraint identified')
                protected = [i for i, c in enumerate(graph_cs)
                             if (c.get('metric') or c['kind'].startswith('P')) and i not in released]
                residual = float(np.max(abs(matrix[protected] @ (after - q).ravel()))) \
                    if protected else 0.
                if residual > 1 / 64 + 1e-9:
                    raise ValueError('other protected relationship changes')
                native_map = self.install(prev_font, self.work / f'{key}-{stage}-{ord(char):04x}.ttf',
                                          [(char, size, (points, ends, flags), after)])
                native = native_map[char]
                if metrics(pixels(render(ft.Face(str(
                        self.work / f'{key}-{stage}-{ord(char):04x}.ttf')), char, size, hinted=True)),
                           native, np.asarray(points) * model['scale'])['white_counters'] != \
                        metrics(pixels(before), q, np.asarray(points) * model['scale'])['white_counters']:
                    raise ValueError('counter topology changes')
                with TTFont(str(self.work / f'{key}-{stage}-{ord(char):04x}.ttf')) as check:
                    if check['hmtx'][check.getBestCmap()[ord(char)]] != advance:
                        raise ValueError('advance changed')
                jobs.append((char, size, (points, ends, flags), after))
                row['stages'][stage] = 'pending-compile'
            except (ValueError, AssertionError) as exc:
                row['stages'][stage] = 'held'
                row.setdefault('holds', {})[stage] = str(exc)
        stem_font, _ = self.stage_font(key, stage, prev_font, jobs)
        after_face = ft.Face(str(stem_font))
        produced = set()
        for char in sorted(live):
            row = case_rows[char]
            if row['stages'].get(stage) == 'pending-compile':
                delta = len(before_ink[char] ^ pixels(render(after_face, char, size, hinted=True)))
                row['stages'][stage] = 'changed' if delta else 'unchanged'
                row['changed_pixels_' + stage] = delta
                produced.add(char)
        return stem_font, produced

    # -- stage 9: approved recovery and export ------------------------------

    def export(self, key, size, candidate_path, prev_font, live, case_rows):
        """Apply the approved whole curved-stroke pass and export the face.

        Mirrors ``build_cumulative_recovery.run`` per glyph: ``finalize``
        runs once on the pre-recovery cumulative coordinates with the
        cumulative audit's order and ownership, then the result compiles
        to native SCFS programs for the single requested ppem.
        """
        rows, failures, expected, sections, changes = [], [], {}, [], []
        with TTFont(str(candidate_path)) as combined:
            cmap = combined.getBestCmap()
            included = set()
            for char in sorted(set(list(live) + [r['char'] for r in case_rows.values()
                                                 if r.get('status') == 'rejected'])):
                row = case_rows[char]
                rows.append(row)
                if row.get('status') == 'rejected':
                    row.update(status='upstream-rejected')
                    failures.append(row)
                    continue
                info = live[char]
                face = ft.Face(str(prev_font))
                current = coords(face, char, size)
                before = render(face, char, size, hinted=True)
                with TTFont(str(prev_font)) as source:
                    name = source.getBestCmap()[ord(char)]
                    glyph = source['glyf'][name]
                    p, e, t = glyph.getCoordinates(source['glyf'])
                    em = source['head'].unitsPerEm
                    assert em == combined['head'].unitsPerEm
                    fitted, audit = finalize(p, e, t, current, size / em, info['audit'])
                    if glyph.isComposite():
                        raise ValueError(f'composite export requires explicit component mapping: {char!r}')
                    assembly, _ = compile_baseline(export_graph(fitted, size / em), p, size, em)
                    compiled = deepcopy(glyph)
                    compiled.program = Program()
                    compiled.program.fromAssembly(assembly)
                    combined['glyf'][cmap[ord(char)]] = compiled
                    combined['hmtx'][cmap[ord(char)]] = source['hmtx'][name]
                    included.add(ord(char))
                    expected[char] = (fitted, pixels(before), np.asarray(p) * size / em,
                                      source['hmtx'][name], audit)
            for table in combined['cmap'].tables:
                if table.isUnicode():
                    table.cmap = {c: n for c, n in table.cmap.items() if c in included}
            combined['maxp'].maxStackElements = max(combined['maxp'].maxStackElements, 16)
            target = self.output / f'{key}-candidate.ttf'
            combined.save(target)
        face = ft.Face(str(target))
        records = {}
        with TTFont(str(target)) as exported:
            assert set(exported.getBestCmap()) == included
            for char in sorted(expected):
                row = case_rows[char]
                fitted, reference_ink, source, advance, audit = expected[char]
                actual = coords(face, char, size)
                after = render(face, char, size, hinted=True)
                ink = pixels(after)
                delta = _export_row_status(
                    char, live, row, fitted, reference_ink, source,
                    advance, audit, actual, ink,
                    exported['hmtx'][exported.getBestCmap()[ord(char)]])
                record = output_mod.glyph_record(char, size, after, actual, advance)
                records[char] = record
                native_name, large_name = output_mod.write_specimens(
                    self.output, key, char, after)
                panel = output_mod.panel_html(
                    key, char, row['status'], delta, record, native_name, large_name)
                sections.append(panel)
                if delta:
                    changes.append(panel)
        output_mod.write_face_json(self.output, key, size, records)
        return rows, failures, sections, changes

    # -- driver --------------------------------------------------------------

    def run_key(self, name, size):
        """All executable stages for one face/size, oldest to newest."""
        key = f'{name}-{size}'
        static_path = self.instantiate(key, name, size)
        experiment_path, records = self.baseline(key, size, static_path)
        candidate_path, outcomes = self.geometric(key, size, experiment_path, records)
        live, case_rows = {}, {}
        for char, outcome in outcomes.items():
            if outcome['status'] != 'verified':
                continue
            points, ends, flags = outcome['outline']
            live[char] = dict(outline=(np.asarray(points, float),
                                       list(ends), list(flags)))
        prev_font, cum_cases, _, cum_rows = self.cumulative(
            key, size, candidate_path, experiment_path, records, outcomes)
        with TTFont(str(experiment_path)) as font:
            advances = {ch: font['hmtx'][font.getBestCmap()[ord(ch)]] for ch in live}
        for char, cum_row in cum_cases.items():
            row = dict(key=key, char=char, stages={})
            case_rows[char] = row
            if cum_row.get('status') == 'rejected':
                row.update(status='rejected', reason=cum_row.get('reason'),
                           stages={'cumulative-fit': 'rejected'})
                live.pop(char, None)
                continue
            row.update(status=cum_row.get('status'), reflection=cum_row.get('reflection'),
                       stages={'cumulative-fit': cum_row.get('status')})
            live[char]['audit'] = cum_row['audit']
            live[char]['advance'] = advances[char]
        for char, row in case_rows.items():
            if row.get('status') == 'rejected':
                for stage in STAGE_ORDER[4:10]:
                    row['stages'][stage] = 'upstream-rejected'
        round_font = self.symmetry_stages(key, size, prev_font, records, static_path,
                                            live, case_rows)
        # Diamond branches: curved-width and source-junction experiments
        # both read the round-level rendering, never each other's output.
        curved_font, curved_produced = self.branch_stage(
            key, size, round_font, records, static_path, live, case_rows,
            'curved-width-links', False)
        junction_font, junction_produced = self.branch_stage(
            key, size, round_font, records, static_path, live, case_rows,
            'source-junctions', True)
        stem_input = self.overlay(key, size, 'stem-input', round_font, [
            (curved_font, curved_produced), (junction_font, junction_produced)])
        for char, row in case_rows.items():
            if row.get('status') == 'rejected':
                continue
            if char in junction_produced:
                row['stem_input_stage'] = 'source-junctions'
            elif char in curved_produced:
                row['stem_input_stage'] = 'curved-width-links'
            else:
                row['stem_input_stage'] = 'round-symmetry'
        stem_font, stem_produced = self.terminal_stage(
            key, size, stem_input, records, static_path, live, case_rows)
        recovery_input = self.overlay(key, size, 'recovery-input', stem_input, [
            (stem_font, stem_produced)])
        for char, row in case_rows.items():
            if row.get('status') == 'rejected':
                continue
            if char in stem_produced:
                row['recovery_input_stage'] = 'stem-relative-terminals'
            else:
                row['recovery_input_stage'] = row['stem_input_stage']
        return self.export(key, size, candidate_path, recovery_input, live, case_rows)

    def run(self):
        self.output.mkdir(parents=True, exist_ok=True)
        if any(self.output.iterdir()):
            raise ValueError('output must be empty')
        (self.output / 'img').mkdir(exist_ok=True)
        self.note_sources()
        rows, pages, changes, failures = [], [], [], []
        try:
            for name in FACES:
                for size in SIZES:
                    tag = face_key(name, size)
                    key_rows, key_failures, sections, key_changes = self.run_key(name, size)
                    rows.extend(key_rows)
                    failures.extend(key_failures)
                    (self.output / f'{tag}.html').write_text(header() + ''.join(sections))
                    pages.append(f'<li><a href="{tag}.html">{tag}</a></li>')
                    changes.extend(key_changes)
                    print(tag, dict(Counter(r['status'] for r in key_rows)), flush=True)
        finally:
            self.close()
        self.verify_inputs_unchanged()
        self.verify_sources()
        counts = dict(Counter(r['status'] for r in rows))
        self.provenance['environment'] = output_mod.environment()
        self.provenance['exports'] = {
            'fonts': sorted(f'{face_key(n, s)}-candidate.ttf' for n in FACES for s in SIZES),
            'bitmaps': sorted(f'{face_key(n, s)}-bitmap.json' for n in FACES for s in SIZES),
            'specimens': 'img/',
        }
        (self.output / 'report.json').write_text(json.dumps(dict(
            summary=counts, cases=rows, inputs=self.inputs,
            provenance=self.provenance), indent=2, default=_json_default) + '\n')
        (self.output / 'index.html').write_text(
            header() + '<p>Admitted glyphs regenerate from source fonts and configuration. '
            'Unresolved cases are excluded from font character maps.</p><ul>' + ''.join(pages) + '</ul>')
        (self.output / 'changes.html').write_text(header() + ''.join(changes))
        (self.output / 'diagnostics.html').write_text(
            header() + '<pre>' + html.escape(json.dumps(failures, indent=2,
                                                        default=_json_default)) + '</pre>')
        print(counts)
        return counts


def face_key(name, size):
    return f'{name}-{size}'


def header():
    return ('<meta charset="utf-8"><style>body{font:16px sans-serif;margin:24px}img{max-width:100%}'
            '</style><h1>Source-to-bitmap specimen</h1><p><a href="index.html">Full specimen</a> · '
            '<a href="changes.html">Approved changes</a> · '
            '<a href="diagnostics.html">Unresolved cases</a></p>')


def _json_default(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return str(value)


def main(output=None):
    pipeline = Pipeline(output or HERE / 'out' / OUTPUT_NAME)
    return pipeline.run()


if __name__ == '__main__':
    main()
