"""JSON command adapter to native FontForge; never builds Python envelopes.

CLI: python3 reference/native_capture.py INPUT.json OUTPUT.json
Input: {"em_size":1000,"subdivisions":100,"glyphs":[[FittedCommand,...],...]}
Call capture(glyphs, em_size=1000, subdivisions=100) from parity tests.
Build the required native executable with reference/build-native.py first.
"""

from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / "out/diagnostics/contextual-spacing/reference/fontforge-build/bin/contextual-spacing-native-capture"


def capture(glyphs, em_size=1000, subdivisions=100):
    if type(em_size) is not int or type(subdivisions) is not int:
        raise ValueError("native FontForge em and subdivisions must be integers")
    text = [f"{em_size} {subdivisions} {len(glyphs)}"]
    fields = {
        "move_to": ("M", ("x", "y")),
        "line_to": ("L", ("x", "y")),
        "quad_to": ("Q", ("x1", "y1", "x", "y")),
        "curve_to": ("C", ("x1", "y1", "x2", "y2", "x", "y")),
        "close": ("Z", ()),
    }
    for commands in glyphs:
        text.append(str(len(commands)))
        for command in commands:
            op, keys = fields[command["op"]]
            values = [command[key] for key in keys]
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
                raise ValueError("coordinates must be numbers")
            text.append(" ".join([op, *(repr(value) for value in values)]))
    result = subprocess.run([str(NATIVE)], input="\n".join(text) + "\n",
                            text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: native_capture.py INPUT.json OUTPUT.json")
    request = json.loads(Path(sys.argv[1]).read_text())
    result = capture(request["glyphs"], request.get("em_size", 1000), request.get("subdivisions", 100))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
