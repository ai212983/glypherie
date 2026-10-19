# Glypherie

Tools for font research and glyph generation.

Prerequisites: [mise](https://mise.jdx.dev/) and [Git LFS](https://git-lfs.com/).

## Commands

```sh
mise exec -- just
```

Before tackling a problem, follow the
[research and adaptation workflow](docs/evaluation.md#research-before-implementation).

## Deployment

The browser app publishes to GitHub Pages from `main` through
[.github/workflows/pages.yml](.github/workflows/pages.yml). Enable it once under repository Settings, Pages, with source
GitHub Actions. Pull requests build and test without deploying; pushes to `main` (or a manual run from `main`) upload
`out/web/` and deploy it. Reproduce the build locally with the [web](tools/web/README.md) and
[WASM](tools/wasm/README.md) guides.

## Documentation

- [Generator](tools/generator/README.md)
- [Web preview](tools/web/README.md)
- [WASM renderer](tools/wasm/README.md)
- [Experiments](experiments/AGENTS.md)
- [Font assets](fonts/README.md)
- [Evaluation](docs/evaluation.md)
- [Development revisions](docs/revisions/README.md)
- [Agent instructions](AGENTS.md)
- [Research papers](docs/references/papers/)
