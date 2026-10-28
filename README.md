# Glypherie

## Development

Prerequisites: Node.js (>= 22.18) with npm, Rust with rustfmt, and [Git LFS](https://git-lfs.com/). The recommended Node
version is pinned in [.node-version](.node-version).

### Commands

From the repository root:

```sh
npm ci --ignore-scripts
git lfs install --local
npm run hooks:install
```

Quality checks:

```sh
npm run fmt:check
npm run spell:check
cargo fmt --manifest-path tools/generator/Cargo.toml --check
npm test
```

`just` recipes remain as optional convenience wrappers; they are not required.

### Documentation

- [Generator](tools/generator/README.md)
- [Web preview](tools/web/README.md)
- [WASM renderer](tools/wasm/README.md)
- [Experiments](experiments/AGENTS.md)
- [Font assets](fonts/README.md)
- [Evaluation](docs/evaluation.md)
- [Development revisions](docs/revisions/README.md)
- [Agent instructions](AGENTS.md)
- [Research papers](docs/references/papers/)
