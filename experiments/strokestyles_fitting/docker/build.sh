#!/bin/sh
# Reproducible setup/build launcher for the StrokeStyles extraction image.
# Usage:
#   sh build.sh --check-only            verify existing vendor checkouts
#   sh build.sh <out-dir>               clone pins, assemble context, print build command
#   sh build.sh <out-dir> --build       ... and run the docker build
# Never run a build while another build owns the shared context.
set -eu

MODE="--build"
OUT=""
for arg in "$@"; do
    case "$arg" in
        --check-only) MODE="--check-only" ;;
        --build) MODE="--build" ;;
        --print-only) MODE="--print-only" ;;
        *) OUT="$arg" ;;
    esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"

pins() {
    grep -E '^[a-z]+ = ' "$HERE/PINS" | sed 's/.*"\(.*\) @ \([0-9a-f]*\)".*/\1 \2/'
}

check_tree() {
    root="$1"
    ok=1
    while read -r url sha; do
        [ -n "$url" ] || continue
        case "$url" in
            *scikit-geometry*) name="skgeom" ;;
            *) name="$(basename "$url")" ;;
        esac
        dir="$root/$name"
        if [ ! -d "$dir/.git" ]; then
            echo "missing: $dir"
            ok=0
            continue
        fi
        got="$(git -C "$dir" rev-parse HEAD)"
        if [ "$got" != "$sha" ]; then
            echo "PIN MISMATCH $name: got $got want $sha"
            ok=0
        else
            echo "pinned ok: $name $sha"
        fi
    done <<EOF
$(pins)
EOF
    return $((1 - ok))
}

if [ "$MODE" = "--check-only" ]; then
    check_tree "${OUT:-$HERE/../../../out/diagnostics/strokestyles-fitting/vendor}"
    exit $?
fi

if [ -z "$OUT" ]; then
    echo "usage: sh build.sh [--check-only] <out-dir> [--print-only|--build]" >&2
    exit 1
fi

mkdir -p "$OUT/vendor"
while read -r url sha; do
    [ -n "$url" ] || continue
    case "$url" in
        *scikit-geometry*) name="skgeom" ;;
        *) name="$(basename "$url")" ;;
    esac
    if [ ! -d "$OUT/vendor/$name/.git" ]; then
        git clone -q "$url" "$OUT/vendor/$name"
    fi
    git -C "$OUT/vendor/$name" fetch -q origin || true
    git -C "$OUT/vendor/$name" checkout -q "$sha"
done <<EOF
$(pins)
EOF

check_tree "$OUT/vendor"

rm -rf "$OUT/docker"
mkdir -p "$OUT/docker"
cp "$HERE/Dockerfile" "$HERE/requirements.txt" "$HERE/runtime-requirements.txt" "$OUT/docker/"
cp -r "$HERE/patches" "$OUT/docker/patches"
cp "$HERE/../runner/run_extract.py" "$OUT/docker/run_extract.py"

(cd "$OUT" && sha256sum docker/Dockerfile docker/requirements.txt \
    docker/runtime-requirements.txt \
    docker/patches/*.patch docker/run_extract.py | tee docker/SOURCES.sha256)

echo "build metadata written to $OUT/docker/SOURCES.sha256"
# shellcheck disable=SC2016
echo "run: cd $OUT && docker build -f docker/Dockerfile -t strokestyles-proto ."
if [ "$MODE" = "--build" ]; then
    cd "$OUT" && docker build -f docker/Dockerfile -t strokestyles-proto .
fi
