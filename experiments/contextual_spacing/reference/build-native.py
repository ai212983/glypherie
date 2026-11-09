"""Build the pinned native FontForge reference locally; never install it.

Run from any cwd. All upstream sources, logs, and binaries stay in the
repository's out/diagnostics/contextual-spacing/reference directory.
Requires cmake, C/C++ compilers, pkg-config, FreeType, gettext/intl, GLib,
libxml2 and zlib development files. Optional GUI/image/Python features are off.
"""

from pathlib import Path
import hashlib
import json
import subprocess
import tarfile
import urllib.request

REVISION = "c41bdb922285f35defd1e1385adfd13bde1ab32a"
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "out/diagnostics/contextual-spacing/reference"
SOURCE = OUT / f"fontforge-{REVISION}"
BUILD = OUT / "fontforge-build"
DRIVER = Path(__file__).with_name("native_capture.c").resolve()
FP_FLAGS = "-ffp-contract=off -fno-fast-math"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / "fontforge.tar.gz"
    url = f"https://github.com/fontforge/fontforge/archive/{REVISION}.tar.gz"
    if not SOURCE.exists():
        if not archive.exists():
            urllib.request.urlretrieve(url, archive)
        with tarfile.open(archive) as contents:
            contents.extractall(OUT, filter="data")
    # The executable includes the original autowidth2.c verbatim so static
    # aw2_findedges is callable. Only build-system wiring is appended locally.
    cmake_file = SOURCE / "CMakeLists.txt"
    marker = "# contextual-spacing native reference driver"
    content = cmake_file.read_text()
    if marker not in content:
        with cmake_file.open("a") as target:
            target.write(f'\n{marker}\nadd_executable(contextual-spacing-native-capture "{DRIVER}")\n'
                         'target_link_libraries(contextual-spacing-native-capture PRIVATE fontforge)\n')
    configure = ["cmake", "-S", str(SOURCE), "-B", str(BUILD),
                 "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=/opt/homebrew",
                 f"-DCMAKE_C_FLAGS={FP_FLAGS}", f"-DCMAKE_CXX_FLAGS={FP_FLAGS}",
                 "-DBUILD_TESTING=OFF"]
    for option in ["GUI", "PYTHON_SCRIPTING", "PYTHON_EXTENSION", "LIBSPIRO", "DOCS",
                   "LIBGIF", "LIBJPEG", "LIBPNG", "LIBTIFF", "LIBREADLINE", "WOFF2", "HARFBUZZ"]:
        configure.append(f"-DENABLE_{option}=OFF")
    with (OUT / "native-build.log").open("w") as log:
        subprocess.run(configure, check=True, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(["cmake", "--build", str(BUILD), "--target",
                        "contextual-spacing-native-capture", "--parallel", "8"],
                       check=True, stdout=log, stderr=subprocess.STDOUT)
    upstream = SOURCE / "fontforge/autowidth2.c"
    license_end = upstream.read_text().index("#include <fontforge-config.h>")
    (OUT / "autowidth2-LICENSE.txt").write_text(upstream.read_text()[:license_end])
    identity = {
        "revision": REVISION, "archive_url": url,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "autowidth2_sha256": hashlib.sha256(upstream.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(DRIVER.read_bytes()).hexdigest(),
        "source_modifications": "CMake target wiring only; autowidth2.c unchanged",
        "native_functions": ["aw2_findedges", "aw2_bbox_separation"],
        "floating_point_semantics": "separate source arithmetic operations; no fused multiply-add contraction or fast math; this is not default-toolchain binary parity",
        "c_flags": FP_FLAGS,
        "cxx_flags": FP_FLAGS,
        "build_type": "Release",
        "configure_command": configure,
        "compilers": {},
        "license": "upstream autowidth2.c BSD-3-Clause notice retained in autowidth2-LICENSE.txt",
    }
    cache = (BUILD / "CMakeCache.txt").read_text().splitlines()
    for language in ["C", "CXX"]:
        prefix = f"CMAKE_{language}_COMPILER:FILEPATH="
        compiler = next(line[len(prefix):] for line in cache if line.startswith(prefix))
        identity["compilers"][language] = {
            "path": compiler,
            "version": subprocess.run([compiler, "--version"], check=True, text=True,
                                      capture_output=True).stdout.strip(),
        }
    (OUT / "native-build-identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    print(BUILD / "bin/contextual-spacing-native-capture")


if __name__ == "__main__":
    main()
