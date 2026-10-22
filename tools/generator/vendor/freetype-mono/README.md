# FreeType monochrome scanner

Built by the generator's `candidate` feature. Requires a host C compiler; WASM builds require Clang
with the `wasm32-unknown-unknown` target and `llvm-ar` on PATH (or Cargo `CC`/`AR` target overrides).
No system FreeType installation is used. Source and adaptation policy: [PATCH.md](PATCH.md).
