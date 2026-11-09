#!/usr/bin/env bash
# Reproducible browser/node build for the experimental YinYang oriented
# engine. No maintained crate depends on this; the reviewed page is
# untouched. Uses only the preinstalled toolchain (no global installs):
# `wasm32-unknown-unknown` std (already installed) and `wasm-bindgen`
# 0.2.129 (must match the crate's pinned `wasm-bindgen` dependency).
#
# Usage: build-wasm.sh [web|nodejs]   (defaults to web)
#
# Each target writes an isolated package directory (`pkg-web/`, `pkg-node/`)
# holding the JS glue plus the `.wasm` bytes. Offline `file://` pages must
# NOT fetch the `.wasm` URL: the worker instantiates from inlined bytes via
# `initSync({ module: bytes })` (see smoke/inline_check.mjs).
set -euo pipefail

LEAF="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-web}"
case "$TARGET" in
  web|nodejs) ;;
  *) echo "usage: $0 [web|nodejs]" >&2; exit 2 ;;
esac

if ! rustup target list --installed 2>/dev/null | grep -q '^wasm32-unknown-unknown$'; then
  echo "missing Rust target wasm32-unknown-unknown (rustup target add wasm32-unknown-unknown)" >&2
  exit 2
fi
if ! command -v wasm-bindgen >/dev/null 2>&1; then
  echo "missing wasm-bindgen CLI (must match the pinned crate version)" >&2
  exit 2
fi

OUT="$LEAF/pkg-$TARGET"
rm -rf "$OUT" "$LEAF/target/wasm"
mkdir -p "$OUT"
cargo build --locked --manifest-path "$LEAF/Cargo.toml" \
  --target wasm32-unknown-unknown --release \
  --features wasm --lib
wasm-bindgen --target "$TARGET" --out-dir "$OUT" \
  "$LEAF/target/wasm32-unknown-unknown/release/yinyang_oriented_engine.wasm"
ls "$OUT"
