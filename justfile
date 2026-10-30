# Keep quoted sample text and font paths intact when forwarding recipe arguments.
set positional-arguments

default:
    @just --list

# Install commit tooling and activate the Git hooks in this clone.
hooks-setup:
    git lfs install --local
    npm ci --ignore-scripts
    npm run hooks:install

# Check a commit message file, defaulting to the most recent message.
commit-check message_file=".git/COMMIT_EDITMSG":
    node node_modules/@commitlint/cli/cli.js --edit "{{message_file}}"

# Validate a range of new commits.
commit-check-range from to="HEAD":
    node node_modules/@commitlint/cli/cli.js --from "{{from}}" --to "{{to}}" --verbose

# Test the hook and commit-message validation behavior.
hooks-test:
    npm test

# Check Rust formatting without changing files.
rust-fmt-check:
    cargo fmt --manifest-path crates/generator/Cargo.toml --check

# Install the pinned formatter and spell checker.
docs-setup:
    npm ci --ignore-scripts
    npx --no-install dprint resolved-config > /dev/null

# Format Markdown prose, tables, and JSON files.
fmt:
    npm run fmt

# Check Markdown and JSON formatting without changing files.
fmt-check:
    npm run fmt:check

# Check spelling in the project documentation.
spell-check:
    npm run spell:check

# Install locked web dependencies.
web-setup:
    npm --prefix apps/web ci --ignore-scripts

# Build the WASM font renderer via crates/wasm/build.sh (owned separately; never
# installs toolchains). The browser app stages the source package into a
# hashed Vite asset; inputs are documented in the [WASM interface](crates/wasm/README.md).
wasm-build:
    crates/wasm/build.sh web

# Build the candidate-enabled preview WASM renderer. Uses the opt-in `preview`
# cargo feature, which enables the generator's `candidate` feature; the output
# (crates/wasm/pkg-web-preview-simd128/) uses standard SIMD and stays separate
# from the production artifact (crates/wasm/pkg-web/, built by `wasm-build`).
wasm-build-preview:
    WASM_SIMD128=1 crates/wasm/build.sh web preview

# Build the browser app into out/web/.
web:
    npm --prefix apps/web run build

# Serve the browser app with live reload, without generating specimens.
dev $web_port="8903":
    npm --prefix apps/web run dev -- --port="$web_port"

# Serve the current browser app; `preview` keeps the review-workflow name.
alias preview := dev

# Serve the built app separately from the dev server.
web-serve:
    npm --prefix apps/web run preview

# Generate and publish the configured specimen packages.
specimens $config_path="crates/generator/specimens.json" $output_dir="out/specimens":
    cargo run --locked --manifest-path crates/generator/Cargo.toml --bin font_specimens -- "$config_path" "$output_dir"

# Check web browser types without emitting files.
web-typecheck:
    npm --prefix apps/web run typecheck

# Run the web tests.
web-test:
    npm --prefix apps/web run test

# Capture the front-page converters; activate the sample-script environment first.
landing-samples *args:
    python3 apps/web/scripts/landing-samples/generate.py "$@"

# Serve isolated web components with live reload.
web-storybook:
    npm --prefix apps/web run storybook

# Build the component explorer into out/storybook/.
web-storybook-build:
    npm --prefix apps/web run build-storybook

# Export aligned glyph images and pixel differences from published renders.
comparisons $config_path="crates/generator/comparisons.json" $specimen_dir="out/specimens":
    cargo run --locked --manifest-path crates/generator/Cargo.toml --bin font_comparison -- "$config_path" "$specimen_dir"

# Stage Playdate Font Lab and compile out/playdate-font-lab/FontLab.pdx.
playdate-build *args:
    node apps/playdate-fontlab/build.mjs {{args}}

# Build FontLab.pdx and open it in the SDK Simulator.
playdate-run *args:
    node apps/playdate-fontlab/build.mjs --run {{args}}
