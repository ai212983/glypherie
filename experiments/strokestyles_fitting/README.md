# StrokeStyles fitting experiment

Isolated prototype for StrokeStyles-assisted diagonal fitting. Owning design:
[docs/strokestyles-fitting.md](../../docs/strokestyles-fitting.md).

## Setup

Build the pinned image from a fresh checkout (all pins in `docker/PINS`; the script verifies each clone, assembles the
context and records `docker/SOURCES.sha256`):

```sh
sh experiments/strokestyles_fitting/docker/build.sh out/diagnostics/strokestyles-fitting/build --build
```

Assemble and verify a context without building:

```sh
sh experiments/strokestyles_fitting/docker/build.sh out/diagnostics/strokestyles-fitting/build --print-only
```

Verify pins against existing checkouts:

```sh
sh experiments/strokestyles_fitting/docker/build.sh --check-only out/diagnostics/strokestyles-fitting/vendor
```

Pinned host-side test dependencies (Python 3.10, NumPy 1.26.4, fontTools 4.53.1):

```sh
uv run --python 3.10 --with numpy==1.26.4 --with fonttools==4.53.1 python -m unittest discover \
  -s experiments/strokestyles_fitting/tests -p 'test_*.py'
```

Build the capture adapter:

```sh
cargo build --manifest-path experiments/strokestyles_fitting/native/Cargo.toml
```

## Run extraction

All runs mount the experiment runner read-only so the executed code is
`experiments/strokestyles_fitting/runner/run_extract.py`. Create the output directories first and use absolute bind
mounts:

```sh
mkdir -p out/diagnostics/strokestyles-fitting/cache out/diagnostics/strokestyles-fitting/extraction
docker run --rm \
  -v "$PWD/fonts:/fonts:ro" \
  -v "$PWD/out/diagnostics/strokestyles-fitting/cache:/cache" \
  -v "$PWD/out/diagnostics/strokestyles-fitting/extraction:/out" \
  -v "$PWD/experiments/strokestyles_fitting/runner/run_extract.py:/opt/run_extract.py:ro" \
  -e PYTHONHASHSEED=0 \
  strokestyles-proto \
  --font /fonts/Roboto.ttf --chars lIitfnhkyxzvAVW \
  --axes wght=400,wdth=100 \
  --image-id "$(docker inspect --format='{{.Id}}' strokestyles-proto)" \
  --cache-dir /cache --out /out/roboto-wght400-wdth100.json
```

Capture a fresh native case (adapter CLI; mode word first):

```sh
cargo run --manifest-path experiments/strokestyles_fitting/native/Cargo.toml -- capture \
  --font fonts/Roboto.ttf --size 16 --axes '{"wght":400,"wdth":100}' \
  --chars lIitfnhkyxzvAVW --out out/diagnostics/strokestyles-fitting/captures.json
```

## Run fitting

Fitting is off by default; enable it explicitly per run. The analysis directory holds only extract-record JSONs,
separate from the extraction cache and the run summary:

```sh
uv run --python 3.10 --with numpy==1.26.4 --with fonttools==4.53.1 \
  python experiments/strokestyles_fitting/fit.py \
  --captures out/diagnostics/strokestyles-fitting/captures.json \
  --analysis-dir out/diagnostics/strokestyles-fitting/extraction \
  --enable-strokestyles \
  --out out/diagnostics/strokestyles-fitting/fitting
```

Without `--enable-strokestyles` the run stays on the baseline path.

Render a fit candidate on the record's own policy (frame, pixels, coverage):

```sh
python3 - <<'PY'
import json
from pathlib import Path
root = Path("out/diagnostics/strokestyles-fitting")
record = next(r for r in json.loads((root / "captures.json").read_text())[0]
              ["modes"]["selective_default"]["records"] if r["codepoint"] == ord("k"))
fit = json.loads(next((root / "fitting/selective_default").glob("U+006B_*.json")).read_text())
dest = root / "raster-inputs"
dest.mkdir(exist_ok=True)
(dest / "record.json").write_text(json.dumps(record))
(dest / "candidate.json").write_text(json.dumps(fit["candidate_commands"]))
PY
cargo run --manifest-path experiments/strokestyles_fitting/native/Cargo.toml -- parity \
  --record out/diagnostics/strokestyles-fitting/raster-inputs/record.json
cargo run --manifest-path experiments/strokestyles_fitting/native/Cargo.toml -- candidate \
  --record out/diagnostics/strokestyles-fitting/raster-inputs/record.json \
  --commands out/diagnostics/strokestyles-fitting/raster-inputs/candidate.json \
  > out/diagnostics/strokestyles-fitting/raster.json
```

`--record` is one capture record; `--commands` is the fit-produced candidate commands array for that record. The example
uses the single captured default case; use a separate output directory for each capture configuration.

## Configuration

- `runner/run_extract.py`: `--shape-size` (default 150, upstream coordinate), `--curve-steps` (default 12 subdivisions
  per triple), `--seed` (default 0).
- `native/src/capture.rs`: `--font/--chars/--out` required, `--size` (default 16), `--axes` (default empty, JSON
  object).
- Cache keys hash one canonical identity: font bytes (original and instantiated), resolved axes, char, outline flavor,
  shape size, curve sampling, seed, extractor and repo commits, runner version and file hash, full package versions,
  native binding hashes, pinned base digest and runtime image id. A hit must equal the full identity; drift re-extracts.
- Outputs: `out/diagnostics/strokestyles-fitting/` (`extract.json`, `cache/`). Per glyph: strokes (`P` spines and
  upstream `W`/`Wv` radii in font units y-up, plus derived `W_full = 2r`), `connectivity`, `junctions`,
  `original_contours`, `unioned_contours`, union ink check, `identity`, `cache_key` and per-stage timings.
