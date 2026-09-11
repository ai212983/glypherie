"""Create labelled, native-scale contact sheets from a specimen manifest."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def contact(manifest_path, output):
    manifest = json.loads(manifest_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    files = []
    # Batches keep every sheet manageable and consume only current manifest pages.
    for panel in sorted({p["panel"] for p in manifest["pages"]}):
        pages = [p for p in manifest["pages"] if p["panel"] == panel]
        for offset in range(0, len(pages), 6):
            batch = pages[offset:offset + 6]
            width, height = batch[0]["width"], batch[0]["height"]
            sheet = Image.new("RGB", (2 * (width + 16) + 16,
                                      ((len(batch) + 1) // 2) * (height + 48) + 16), "#eeeeee")
            draw = ImageDraw.Draw(sheet)
            for index, entry in enumerate(batch):
                image = Image.open(manifest_path.parent / entry["png"]).convert("RGB")
                if image.size != (width, height):
                    raise ValueError(f"dimension mismatch: {entry['id']}")
                x, y = 16 + index % 2 * (width + 16), 16 + index // 2 * (height + 48)
                draw.text((x, y), entry["id"], font=ImageFont.load_default(), fill="black")
                sheet.paste(image, (x, y + 24))
            name = f"CONTACT_{panel}_{offset // 6 + 1:02}.png"
            sheet.save(output / name)
            files.append(name)
    (output / "contacts.json").write_text(json.dumps({"files": files}, indent=2) + "\n")
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print("Wrote", len(contact(args.manifest, args.output)), "contact sheets")
