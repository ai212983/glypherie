# Optical spacing diagnostics

Owning question and decision boundary:
[spacing investigation and proposal](../../docs/revisions/001/03-spacing-kerning.md#pair-spacing-and-kerning).

## Setup

Use the pinned Python dependencies in [the landing capture environment](../../apps/web/README.md#front-page-samples).
Build the shared native capture adapter:

```sh
cargo build --locked --offline --manifest-path experiments/strokestyles_fitting/native/Cargo.toml \
  --example spacing_capture --target-dir crates/generator/target
```

## Commands

The adapter accepts JSON lines containing `font`, generator `settings` and `pipeline`:

```sh
crates/generator/target/debug/examples/spacing_capture < JOBS.jsonl > CAPTURES.jsonl
python experiments/optical_spacing/assess.py --captures CAPTURES.jsonl --out OUTPUT_DIRECTORY
```

Add `--landing-root RUN_DIRECTORY` to verify each current diagonal-enabled capture against its matching published
Playdate export. Serve the generated `index.html` through the web development server's diagnostic-file route documented
in the [web README](../../apps/web/README.md#commands).

Run the diagnostic verification checks in the same Python environment:

```sh
python -m unittest discover -s experiments/optical_spacing -p 'test_*.py'
```
