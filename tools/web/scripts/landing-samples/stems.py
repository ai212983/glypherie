"""Source-axis calibration and native-pixel measurements for sample generation.

Hersch 1993, sections 5-6 describes reference stem widths and grid fitting:
https://lspwww.epfl.ch/publications/typography/frsa.pdf
fontTools supplies variation-aware outlines and exact Bezier intersections:
https://fonttools.readthedocs.io/en/latest/pens/basePen.html

Project adaptation: use the maximum horizontal body width in H, I and l as a
family-wide design-weight reference. Three upper-body sections exclude cap/base
serifs and H's crossbar. Solve only the font's global weight axis, never pixels,
individual glyphs, thresholds or rasterizer rules. This targets principal stems,
not every diagonal, join, serif or curved stroke. Native checks are measurements,
not an optical assessment.
"""
from collections import Counter
import io
import statistics

from fontTools.misc.bezierTools import solveCubic, solveQuadratic
from fontTools.pens.basePen import BasePen
from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

REFERENCES = 'HIl'
BODY_SECTIONS = (2 / 3, 3 / 4, 5 / 6)


class HorizontalIntersections(BasePen):
    def __init__(self, glyph_set, y):
        super().__init__(glyph_set)
        self.y, self.xs, self.start = y, [], None

    def _moveTo(self, point):
        self.start = point

    def _lineTo(self, point):
        a = self._getCurrentPoint()
        if a[1] != point[1] and min(a[1], point[1]) <= self.y <= max(a[1], point[1]):
            self.xs.append(a[0] + (point[0] - a[0]) * (self.y - a[1]) / (point[1] - a[1]))

    def _qCurveToOne(self, b, c):
        a = self._getCurrentPoint()
        for t in solveQuadratic(a[1] - 2 * b[1] + c[1], 2 * (b[1] - a[1]), a[1] - self.y):
            if 0 <= t <= 1:
                self.xs.append((1 - t)**2 * a[0] + 2 * (1 - t) * t * b[0] + t**2 * c[0])

    def _curveToOne(self, b, c, d):
        a = self._getCurrentPoint()
        for t in solveCubic(-a[1] + 3 * b[1] - 3 * c[1] + d[1], 3 * a[1] - 6 * b[1] + 3 * c[1], -3 * a[1] + 3 * b[1], a[1] - self.y):
            if 0 <= t <= 1:
                self.xs.append((1 - t)**3 * a[0] + 3 * (1 - t)**2 * t * b[0] + 3 * (1 - t) * t**2 * c[0] + t**3 * d[0])

    def _closePath(self):
        self._lineTo(self.start)


def source_widths(font, axes, size):
    glyph_set = font.getGlyphSet(location=axes)
    cap = font['OS/2'].sCapHeight
    scale = size / font['head'].unitsPerEm
    widths = []
    for character in REFERENCES:
        for fraction in BODY_SECTIONS:
            pen = HorizontalIntersections(glyph_set, cap * fraction)
            glyph = glyph_set[font.getBestCmap()[ord(character)]]
            glyph.draw(pen)
            xs = sorted(set(pen.xs))
            spans = []
            # TrueType uses nonzero winding, including overlapping contours.
            # https://learn.microsoft.com/en-us/typography/opentype/spec/ttch01#the-scan-converter
            for left, right in zip(xs, xs[1:]):
                inside = PointInsidePen(glyph_set, ((left + right) / 2, cap * fraction), evenOdd=False)
                glyph.draw(inside)
                if inside.getResult():
                    if spans and spans[-1][1] == left:
                        spans[-1] = (spans[-1][0], right)
                    else:
                        spans.append((left, right))
            if not spans:
                raise ValueError(f'Cannot measure source stem sections for {character}')
            widths.extend((right - left) * scale for left, right in spans)
    return widths


def calibrate(source, axes, size, target):
    with TTFont(source) as font:
        available = {a.axisTag: a for a in font['fvar'].axes} if 'fvar' in font else {}
        if 'wght' not in available or 'wght' in axes:
            raise ValueError('Stem calibration requires a variable weight axis without an explicit wght coordinate')
        if set(axes) - available.keys():
            raise ValueError('Unknown source axis in stem calibration')
        resolved = {tag: axes.get(tag, a.defaultValue) for tag, a in available.items()}
        for tag, value in resolved.items():
            if not available[tag].minValue <= value <= available[tag].maxValue:
                raise ValueError(f'Axis {tag} is outside the font range')
        weight = available['wght']
        low, high = weight.minValue, weight.maxValue
        low_width = max(source_widths(font, {**resolved, 'wght': low}, size))
        high_width = max(source_widths(font, {**resolved, 'wght': high}, size))
        if not low_width <= target <= high_width:
            raise ValueError(f'{source.name} cannot reach {target}px reference stems at {size}px within its weight axis')
        for _ in range(24):
            middle = (low + high) / 2
            if max(source_widths(font, {**resolved, 'wght': middle}, size)) < target:
                low = middle
            else:
                high = middle
        # Round down to stay within the stem-width bound.
        import math
        resolved['wght'] = math.floor(low * 100) / 100
        def realized_widths(location):
            # Measure serialized outlines: saving rounds TrueType coordinates.
            instance = instantiateVariableFont(font, location, inplace=False)
            try:
                serialized = io.BytesIO()
                instance.save(serialized)
                serialized.seek(0)
                with TTFont(serialized) as static:
                    return source_widths(static, {}, size)
            finally:
                instance.close()
        widths = realized_widths(resolved)
        if max(widths) > target:
            low, high = weight.minValue, resolved['wght']
            if max(realized_widths({**resolved, 'wght': low})) > target:
                raise ValueError('Static source coordinates cannot meet the requested stem bound')
            for _ in range(18):
                middle = (low + high) / 2
                if max(realized_widths({**resolved, 'wght': middle})) <= target:
                    low = middle
                else:
                    high = middle
            resolved['wght'] = math.floor(low * 100) / 100
            widths = realized_widths(resolved)
        evidence = {'target_px': target, 'reference_characters': REFERENCES, 'body_sections': BODY_SECTIONS, 'source_horizontal_widths_px': widths, 'maximum_source_width_px': max(widths), 'median_source_width_px': statistics.median(widths), 'cap_height_px': font['OS/2'].sCapHeight * size / font['head'].unitsPerEm, 'method': 'One family-wide weight coordinate bounding reference source body widths by the target; no bitmap feedback.'}
        return resolved, evidence


def native_widths(glyphs, calibration):
    """Count native horizontal ink runs in the fitted cap-height body band."""
    report = {}
    h_image, _, _, h_top = glyphs['H']
    h_box = h_image.getbbox()
    if not h_box:
        raise ValueError('No native cap-height reference')
    cap = h_box[3] - h_box[1]
    baseline = h_top + h_box[3]
    rows = [y for y in range(int(cap) + 1) if min(BODY_SECTIONS) * cap <= y + 0.5 <= max(BODY_SECTIONS) * cap]
    for ch in REFERENCES:
        image, _, _, top = glyphs[ch]
        widths, missing = [], []
        for y in rows:
            bitmap_y = baseline - y - 1 - top
            if not 0 <= bitmap_y < image.height:
                missing.append(y)
                continue
            run = 0
            row_widths = []
            for x in range(image.width + 1):
                if x < image.width and image.getpixel((x, bitmap_y)):
                    run += 1
                elif run:
                    row_widths.append(run)
                    run = 0
            if not row_widths:
                missing.append(y)
            widths.extend(row_widths)
        report[ch] = {'native_cap_height_px': cap, 'body_rows_above_ink_baseline': rows, 'run_width_counts_px': dict(sorted(Counter(widths).items())), 'rows_without_ink': missing}
    return report
