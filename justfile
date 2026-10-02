default:
    @just --list

# Install commit tooling and activate the Git hooks in this clone.
hooks-setup:
    git lfs install --local
    mise install --locked dprint just lefthook node npm:cspell
    mise exec -- npm ci --ignore-scripts
    mise exec -- lefthook install

# Check a commit message file, defaulting to the most recent message.
commit-check message_file=".git/COMMIT_EDITMSG":
    mise exec -- node node_modules/@commitlint/cli/cli.js --edit "{{message_file}}"

# Validate a range of new commits.
commit-check-range from to="HEAD":
    mise exec -- node node_modules/@commitlint/cli/cli.js --from "{{from}}" --to "{{to}}" --verbose

# Test the hook and commit-message validation behavior.
hooks-test:
    mise exec -- npm test

# Check Rust formatting without changing files.
rust-fmt-check:
    cargo fmt --manifest-path tools/generator/Cargo.toml --check

# Install the pinned formatter and spell checker using mise.
docs-setup:
    mise install --locked dprint node npm:cspell
    mise exec -- dprint resolved-config > /dev/null

# Format Markdown prose, tables, and JSON files.
fmt:
    mise exec -- dprint fmt

# Check Markdown and JSON formatting without changing files.
fmt-check:
    mise exec -- dprint check

# Check spelling in the project documentation.
spell-check:
    mise exec -- cspell --no-progress --gitignore

# Install the pinned web runtime and locked web dependencies.
web-setup:
    mise -C tools/web install --locked node
    mise -C tools/web exec -- npm ci --ignore-scripts

# Build the WASM font renderer and stage its web artifacts into out/web/assets/wasm/.
# Runs tools/wasm/build.sh (owned separately; never installs toolchains) and
# copies the web-target outputs. Set FONT_WASM_WEB_DIR to override the build
# output directory. Fails loudly when the toolchain or outputs are missing;
# the preview page stays disabled until this succeeds.
wasm-build out_dir="out/web":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ ! -x tools/wasm/build.sh ]; then
      echo "wasm-build: tools/wasm/build.sh is missing or not executable." >&2
      exit 1
    fi
    tools/wasm/build.sh web
    wasm_dir="${FONT_WASM_WEB_DIR:-tools/wasm/pkg-web}"
    mkdir -p "{{out_dir}}/assets/wasm"
    for artifact in font_wasm.js font_wasm_bg.wasm; do
      source="$wasm_dir/$artifact"
      if [ ! -f "$source" ]; then
        echo "wasm-build: expected output $source was not produced." >&2
        exit 1
      fi
      cp "$source" "{{out_dir}}/assets/wasm/$artifact"
    done

# Build the static website into out/web/.
web:
    mise -C tools/web exec -- npm run build

# Build, watch, and serve the website with live reload.
preview $web_port="8903" config_path="tools/generator/specimens.json" comparison_config="tools/generator/comparisons.json": (specimens config_path) (comparisons comparison_config) (wasm-build)
    mise -C tools/web exec -- npm run dev -- --port="$web_port"

# Generate and publish the configured specimen packages.
specimens $config_path="tools/generator/specimens.json" $output_dir="out/specimens":
    cargo run --locked --manifest-path tools/generator/Cargo.toml --bin font_specimens -- "$config_path" "$output_dir"

# Generate specimens and build the static website.
preview-build config_path="tools/generator/specimens.json" comparison_config="tools/generator/comparisons.json": (specimens config_path) (comparisons comparison_config) (wasm-build) web

# Rebuild the website when its sources change.
web-watch:
    mise -C tools/web exec -- npm run watch

# Run the web tests with the pinned runtime.
web-test:
    mise -C tools/web exec -- npm test

# Export aligned glyph images and pixel differences from published renders.
comparisons $config_path="tools/generator/comparisons.json" $specimen_dir="out/specimens":
    cargo run --locked --manifest-path tools/generator/Cargo.toml --bin font_comparison -- "$config_path" "$specimen_dir"
