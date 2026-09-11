"""Render calibrated glyph artifacts into labelled native panel pages.

Consumes generator pixels and metrics directly. Paths in output manifests are
relative to the manifest; only explicitly listed cases enter a session.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PANELS = {"inkplate": (600, 600), "waveshare": (400, 300)}


def pack(image, panel, bits):
    """Pack luminance into the board's existing specimen frame contract."""
    width, height = image.size
    px = image.convert("L").tobytes()
    if bits == 1:
        stride = (width + 7) // 8
        payload = bytearray(stride * height)
        for y in range(height):
            for x in range(width):
                if px[y * width + x] < 128:
                    shift = x % 8 if panel == "inkplate" else 7 - x % 8
                    payload[y * stride + x // 8] |= 1 << shift
    elif panel == "inkplate" and bits == 3:
        if width % 2:
            raise ValueError("Gray4 requires even width")
        levels = [round(v * 7 / 255) * 2 for v in px]
        payload = bytes((a << 4) | b for a, b in zip(levels[::2], levels[1::2]))
    else:
        raise ValueError(f"unsupported panel output: {panel}/{bits}")
    if panel == "inkplate":
        return (b"MDFR" + bytes([1, int(bits == 3)])
                + width.to_bytes(2, "little") + height.to_bytes(2, "little")
                + bytes(6) + payload)
    return bytes(payload)


def text_image(generated, text):
    glyphs = {g["codepoint"]: g for g in generated["glyphs"]}
    pairs = {(p["left"], p["right"]): p["adjustment_26_6"]
             for p in generated["kerning"]}
    placed, pen = [], 0
    for index, char in enumerate(text):
        glyph = glyphs[ord(char)]
        x = math.floor(pen / 64 + 0.5) + glyph["left"]
        placed.append((x, glyph))
        pen += glyph["advance_26_6"]
        if index + 1 < len(text):
            pen += pairs.get((ord(char), ord(text[index + 1])), 0)
    left = min([0] + [x for x, _ in placed])
    right = max([math.ceil(pen / 64)] + [x + g["width"] for x, g in placed])
    top = min([0] + [g["top"] for _, g in placed])
    bottom = max([0] + [g["top"] + g["height"] for _, g in placed])
    result = Image.new("L", (max(1, right - left), max(1, bottom - top)), 255)
    maximum = (1 << generated["config"]["output_bits"]) - 1
    for x, glyph in placed:
        for y in range(glyph["height"]):
            for dx in range(glyph["width"]):
                ink = glyph["pixels"][y * glyph["width"] + dx]
                target = (x - left + dx, glyph["top"] - top + y)
                result.putpixel(target, min(result.getpixel(target), 255 - round(ink * 255 / maximum)))
    return result


def page(case, generated):
    width, height = PANELS[case["panel"]]
    size = generated["config"]["size_px"]
    if case["role"] == "ambient_primary":
        lines = ["23°C"]
    elif case["role"] == "ambient_secondary":
        lines = ["08hmn", "23°C 45%"]
    else:
        lines = ["Il1 O0 8B bhmnp", "23°C 45% / 12:34"]
    sample = "\n".join(lines)
    line_images = [text_image(generated, line) for line in lines]
    sample_image = Image.new("L", (max(im.width for im in line_images),
                                  sum(im.height for im in line_images) + 10 * (len(lines) - 1)), 255)
    line_y = 0
    for bitmap in line_images:
        sample_image.paste(bitmap, (0, line_y))
        line_y += bitmap.height + 10
    label_height = 30
    available = (width - 24, height // 2 - label_height - 12)
    if sample_image.width > available[0] or sample_image.height > available[1]:
        raise ValueError(f"{case['id']}: sample exceeds canvas: {sample_image.size} > {available}")
    result = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(result)
    font = ImageFont.load_default()
    for inverse in (False, True):
        y = height // 2 if inverse else 0
        background, foreground = (0, 255) if inverse else (255, 0)
        draw.rectangle((0, y, width - 1, y + height // 2 - 1), fill=background)
        label = f"{case['id']} | {'inverse' if inverse else 'normal'}"
        # Wrap labels to preserve exact case IDs on the physical page.
        lines, line = [], ""
        for char in label:
            if draw.textlength(line + char, font=font) > width - 16:
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
        if len(lines) > 2:
            raise ValueError(f"case label too long: {case['id']}")
        for index, line in enumerate(lines):
            draw.text((8, y + 3 + index * 12), line, font=font, fill=foreground)
        bitmap = sample_image.point(lambda v: 255 - v) if inverse else sample_image
        result.paste(bitmap, (12, y + label_height))
    maximum = (1 << generated["config"]["output_bits"]) - 1
    result = result.point(lambda v: round(round(v * maximum / 255) * 255 / maximum))
    return result, sample


def render(manifest_path, output, selected=()):
    manifest = json.loads(manifest_path.read_text())
    cases = manifest["cases"]
    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate case IDs")
    if set(selected) - set(ids):
        raise ValueError("unknown selected case IDs")
    cases = [c for c in cases if not selected or c["id"] in selected]
    output.mkdir(parents=True, exist_ok=True)
    pages = []
    for case in cases:
        identifier = case["id"]
        if not identifier or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in identifier):
            raise ValueError("case ID must be a safe filename")
        artifact = manifest_path.parent / case["artifact"]
        generated = json.loads(artifact.read_text())["generated"]
        if generated["config"] != case["settings"]:
            raise ValueError(f"{identifier}: artifact settings differ from manifest")
        image, sample = page(case, generated)
        image.save(output / f"{identifier}.pgm")
        image.save(output / f"{identifier}.png")
        frame = pack(image, case["panel"], generated["config"]["output_bits"])
        (output / f"{identifier}.bin").write_bytes(frame)
        pages.append({"id": identifier, "font": case["font"], "panel": case["panel"],
                      "settings": case["settings"], "sample": sample,
                      "width": image.width, "height": image.height,
                      "png": f"{identifier}.png", "frame": f"{identifier}.bin",
                      "frame_sha256": hashlib.sha256(frame).hexdigest(),
                      "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()})
    result = {"schema_version": 1, "calibration_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "pages": pages}
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def install_session(manifest_path, module_path, panel, selected):
    """Install an explicit <=8-page session as a genuine Rust data module."""
    import shutil
    manifest = json.loads(manifest_path.read_text())
    entries = {p["id"]: p for p in manifest["pages"]}
    if not 1 <= len(selected) <= 8 or len(set(selected)) != len(selected):
        raise ValueError("session needs 1 to 8 unique case IDs")
    pages = [entries[key] for key in selected]
    if any(p["panel"] != panel for p in pages):
        raise ValueError("session panel mismatch")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["// Generated by tools/font_probe/render_specimens.py; selected session only."]
    if panel == "waveshare":
        lines.append("pub const SPECIMENS: &[(&str, &[u8; 15000])] = &[")
        for page in pages:
            name = page["id"] + ".bin"
            shutil.copyfile(manifest_path.parent / page["frame"], module_path.parent / name)
            lines.append(f'    ("{page["id"]}", include_bytes!("{name}")),')
    else:
        lines.append("pub const SLIDES: &[(&str, &str)] = &[")
        for page in pages:
            # FAT short names are content-derived, excluding stale prior sessions.
            name = page["frame_sha256"][:8].upper() + ".BIN"
            shutil.copyfile(manifest_path.parent / page["frame"], module_path.parent / name)
            lines.append(f'    ("{page["id"]}", "/assets/spec/{name}"),')
    lines.append("];\n")
    module_path.write_text("\n".join(lines))
    (module_path.parent / "session.json").write_text(json.dumps({"panel": panel, "pages": pages}, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--case", action="append", default=[], help="case ID; repeat to select a session")
    parser.add_argument("--install-module", type=Path, help="write selected session Rust module beside frame files")
    parser.add_argument("--panel", choices=PANELS)
    args = parser.parse_args()
    result = render(args.manifest, args.output, args.case)
    if args.install_module:
        if not args.panel or not args.case:
            parser.error("--install-module requires --panel and explicit --case selection")
        install_session(args.output / "manifest.json", args.install_module, args.panel, args.case)
    print(f"Rendered {len(result['pages'])} native pages; manifest: {args.output / 'manifest.json'}")


if __name__ == "__main__":
    main()
