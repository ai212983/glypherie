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

# Build the WASM font renderer via tools/wasm/build.sh (owned separately; never
# installs toolchains). The browser app stages the source package into a
# hashed Vite asset; inputs are documented in the [WASM interface](tools/wasm/README.md).
wasm-build:
    tools/wasm/build.sh web

# Build the candidate-enabled preview WASM renderer. Uses the opt-in `preview`
# cargo feature, which enables the generator's `candidate` feature; the output
# (tools/wasm/pkg-web-preview/) stays separate from the production artifact
# (tools/wasm/pkg-web/, built by `wasm-build` with default features).
wasm-build-preview:
    tools/wasm/build.sh web preview

# Build the browser app into out/web/.
web:
    mise -C tools/web exec -- npm run build

# Serve the browser app with live reload, without generating specimens.
dev $web_port="8903":
    mise -C tools/web exec -- npm run dev -- --port="$web_port"

# Serve the current browser app; `preview` keeps the review-workflow name.
alias preview := dev

# Generate and publish the configured specimen packages.
specimens $config_path="tools/generator/specimens.json" $output_dir="out/specimens":
    cargo run --locked --manifest-path tools/generator/Cargo.toml --bin font_specimens -- "$config_path" "$output_dir"

# Check web browser types without emitting files.
web-typecheck:
    mise -C tools/web exec -- npm run typecheck

# Run the web tests with the pinned runtime.
web-test:
    mise -C tools/web exec -- npm test

# Serve isolated web components with live reload.
web-storybook:
    mise -C tools/web exec -- npm run storybook

# Build the component explorer into out/storybook/.
web-storybook-build:
    mise -C tools/web exec -- npm run build-storybook

# Export aligned glyph images and pixel differences from published renders.
comparisons $config_path="tools/generator/comparisons.json" $specimen_dir="out/specimens":
    cargo run --locked --manifest-path tools/generator/Cargo.toml --bin font_comparison -- "$config_path" "$specimen_dir"
