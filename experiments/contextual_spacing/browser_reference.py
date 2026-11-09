# cspell:words instancer subsetter recalc fvar unicodes
"""Embed original fonts for native browser text, independently of bitmap layout.

FontFace loading follows https://www.w3.org/TR/css-font-loading-3/.
The bounded inline adapter uses fontTools' layout-preserving subsetter; the full
page always embeds the original bytes. Nondefault variation axes remain live.
"""

import base64
import hashlib
import io
from pathlib import Path


def attach_browser_reference(case, capture):
    path = Path(capture["font_path"])
    raw = path.read_bytes()
    identity = hashlib.sha256(raw).hexdigest()
    if identity != case["sourceSha256"] or identity != capture["source_sha256"]:
        raise ValueError("browser reference source font identity mismatch")
    if case["sizePx"] != capture["size_px"] or case["axes"] != capture.get("axes", {}):
        raise ValueError("browser reference size or axes mismatch")
    case["browserReference"] = dict(
        dataUrl="data:font/ttf;base64," + base64.b64encode(raw).decode(),
        sourceSha256=identity, fontSha256=identity, geometry="original_font_bytes",
        shaping="browser_default", axes=case["axes"], sizePx=case["sizePx"])
    license_path = path.with_name(f"OFL-{path.stem}.txt")
    if license_path.is_file():
        case["browserReference"]["licenseText"] = license_path.read_text()


def compact_browser_reference(reference, codepoints):
    """Subset the variable font for the size-bounded offline inline page.

    All features, hint programs, and name/license records are retained. Browser
    parity with the original variable font must be checked at the capture axes.
    https://fonttools.readthedocs.io/en/latest/varLib/instancer.html
    """
    import fontTools
    import brotli
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    if fontTools.__version__ != "4.62.0":
        raise RuntimeError("inline browser font requires fonttools==4.62.0")
    if brotli.__version__ != "1.2.0":
        raise RuntimeError("inline browser font requires Brotli==1.2.0")
    raw = base64.b64decode(reference["dataUrl"].split(",", 1)[1], validate=True)
    if hashlib.sha256(raw).hexdigest() != reference["sourceSha256"]:
        raise ValueError("inline browser font source identity mismatch")
    font = TTFont(io.BytesIO(raw), recalcTimestamp=False)
    axes = {axis.axisTag: reference["axes"].get(axis.axisTag, axis.defaultValue)
            for axis in font["fvar"].axes} if "fvar" in font else {}
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=codepoints)
    subsetter.subset(font)
    # Default-axis pinning leaves the default outlines unchanged. Retain every
    # nondefault axis: fully static instancing rounds interpolated coordinates
    # and was falsified by native-browser pixel comparison at Literata opsz=16.
    defaults = {axis.axisTag: axis.defaultValue for axis in font["fvar"].axes
                if axes[axis.axisTag] == axis.defaultValue} if axes else {}
    if defaults:
        instantiateVariableFont(font, defaults, inplace=True)
    # A unique derivative family also avoids carrying a reserved source family
    # name into the compact resource. Copyright/license name records stay intact.
    family = "Spacing Inline Reference"
    for record in font["name"].names:
        if record.nameID in (1, 3, 4, 6, 16, 17):
            name = "SpacingInlineReference" if record.nameID == 6 else family
            record.string = name.encode(record.getEncoding())
    font.flavor = "woff2"
    output = io.BytesIO()
    font.save(output)
    data = output.getvalue()
    return dict(reference, dataUrl="data:font/woff2;base64," + base64.b64encode(data).decode(),
                fontSha256=hashlib.sha256(data).hexdigest(), geometry="subset_with_nondefault_axes_retained",
                resolvedAxes=axes, pinnedDefaultAxes=defaults,
                fontToolsVersion=fontTools.__version__, brotliVersion=brotli.__version__)
