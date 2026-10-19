#!/usr/bin/env bash
# Reproducible browser/node build for the font_wasm crate.
#
# Usage: tools/wasm/build.sh [web|bundler|nodejs] [features]   (defaults: web, no features)
#
# Runs `cargo build --locked --target wasm32-unknown-unknown --release`, then
# `wasm-bindgen` over the produced .wasm into tools/wasm/pkg-<target>/
# (isolated per target, so a Node build never overwrites the web artifact
# the preview serves).
#
# The optional features argument (e.g. `preview` for the candidate-enabled
# interactive preview) is forwarded as `cargo build --features`. A feature
# build writes to a separate tools/wasm/pkg-<target>-<features>/ directory so
# the production artifact (default features) is never overwritten by, or
# confused with, the preview artifact.
#
# Final contract for the host/preview: one target per invocation; artifacts
# are tools/wasm/pkg-web/, tools/wasm/pkg-nodejs/, tools/wasm/pkg-bundler/
# (plus `-<features>` suffixed variants) each holding font_wasm.js +
# font_wasm_bg.wasm (+ .d.ts). The preview session copies or points at the
# web artifact; this script never touches tools/web or the justfile.
#
# This script never installs toolchains. Target detection checks for an
# INSTALLED wasm std (rustc --print target-list only lists known targets):
# a preinstalled wasm32-unknown-unknown std is preferred; when it is absent
# but system library sources exist, the documented RUSTC_BOOTSTRAP=1
# -Z build-std=std,panic_abort fallback is used. Otherwise it prints the
# host-owned hint and stops.
set -euo pipefail

TARGET="${1:-web}"
FEATURES="${2:-}"
case "$TARGET" in
  web|bundler|nodejs) ;;
  *) echo "usage: $0 [web|bundler|nodejs] [features]" >&2; exit 2 ;;
esac
if [[ "$FEATURES" == *[!a-zA-Z0-9+,_-]* ]]; then
  echo "usage: features must match [a-zA-Z0-9+,_-]+" >&2; exit 2
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "$FEATURES" ]; then
  SLUG="$(echo "$FEATURES" | tr ',' '-' | tr -cd 'a-zA-Z0-9_-')"
  OUT="$HERE/pkg-$TARGET-$SLUG"
  FEATURE_ARGS=(--features "$FEATURES")
else
  OUT="$HERE/pkg-$TARGET"
  FEATURE_ARGS=()
fi
# Both the preinstalled-std and the build-std fallback emit here.
WASM="$HERE/target/wasm32-unknown-unknown/release/font_wasm.wasm"
WASM_BINDGEN_BIN="${WASM_BINDGEN:-$(command -v wasm-bindgen || true)}"

if ! rustc --print target-list 2>/dev/null | grep -q '^wasm32-unknown-unknown$'; then
  echo "rustc does not know target wasm32-unknown-unknown." >&2
  echo "hint (host-owned): rustup target add wasm32-unknown-unknown" >&2
  exit 1
fi
if [ -z "$WASM_BINDGEN_BIN" ]; then
  echo "missing wasm-bindgen CLI (set WASM_BINDGEN to override)." >&2
  echo "hint (host-owned): cargo install wasm-bindgen-cli --locked --version <crate wasm-bindgen>" >&2
  exit 1
fi

SYSROOT="$(rustc --print sysroot)"
STDLIB="$SYSROOT/lib/rustlib/wasm32-unknown-unknown"
HAVE_STD=0
if ls "$STDLIB"/lib/libstd-*.rlib >/dev/null 2>&1; then
  HAVE_STD=1
fi

cd "$HERE"
if [ "$HAVE_STD" -eq 1 ]; then
  cargo build --locked --target wasm32-unknown-unknown --release "${FEATURE_ARGS[@]}"
else
  # No installed wasm std: fall back to building std from the system library
  # sources into the same target dir. Never installs anything.
  if [ ! -d "$SYSROOT/lib/rustlib/src/rust/library" ] && [ ! -d "/usr/lib/rustlib/src/rust/library" ]; then
    echo "no preinstalled wasm32 std and no system library sources found." >&2
    echo "hint (host-owned): rustup target add wasm32-unknown-unknown" >&2
    exit 1
  fi
  echo "no preinstalled wasm32 std; building std from system sources" >&2
  RUSTC_BOOTSTRAP=1 cargo build --locked -Z build-std=std,panic_abort \
    --target wasm32-unknown-unknown --release "${FEATURE_ARGS[@]}"
fi

mkdir -p "$OUT"
"$WASM_BINDGEN_BIN" --target "$TARGET" --out-dir "$OUT" "$WASM"
if [ "$TARGET" = "nodejs" ]; then
  # wasm-bindgen --target nodejs emits CommonJS, but the repo root is
  # type=module: the isolated output dir carries its own marker so Node
  # loads the generated .js as CJS without touching root settings.
  printf '{"type":"commonjs"}\n' > "$OUT/package.json"
fi
echo "wrote $OUT (target $TARGET)"
