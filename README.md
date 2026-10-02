# font_generator

Tools for font research and glyph generation.

Font binaries, reference PDFs, and figure PNGs are stored with [Git LFS](https://git-lfs.com/). Install Git LFS before
cloning, then run `git lfs install --local` and `git lfs pull` in an existing clone to configure filters and retrieve
assets. LFS installs its upload hook alongside the Lefthook commit checks. Generated builds and previews remain ignored.

## Getting started

Install [mise](https://mise.jdx.dev/getting-started.html), then run from the repository root:

```sh
mise install
mise exec -- just
```

Tool versions are pinned in [mise.toml](mise.toml). `just` lists the available commands.

Markdown wraps at 120 characters. Use `just fmt` to format Markdown and JSON or `just fmt-check` to check formatting.
Use `just spell-check` to check documentation spelling; project vocabulary lives in [cspell.json](cspell.json).

## Commit checks

Run `mise exec -- just hooks-setup` after cloning to install the locked commit tooling and activate
[Lefthook](https://lefthook.dev/) hooks. Rust formatting requires a Rust toolchain with rustfmt.

Before a commit, hooks check Markdown/JSON formatting and documentation spelling for relevant staged files, plus Rust
formatting when generator Rust files change. Hooks check files in the working tree and never format or stage fixes. Use
`just fmt` or `cargo fmt --manifest-path tools/generator/Cargo.toml` to fix formatting, then stage your changes again.
Imported paper transcripts and upstream reference sources are excluded from documentation spelling checks.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `type(scope):
description`. The scope is optional; when supplied, it must appear in [commit-scopes.json](commit-scopes.json). Types
are `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, `perf`, `style`, `chore`, and `revert`. Headers are
limited to 100 characters. Breaking changes use `!` and/or a `BREAKING CHANGE:` footer. Standard generated merge,
revert, and fixup messages use commitlint's default exemptions.

```text
refactor(fonts): move font assets to the repository root
test(generator): remove redundant font fixtures
ci: add formatting and commit-message checks
```

Use `just commit-check path/to/message.txt` to validate a message, `just commit-check-range BASE HEAD` to validate new
commits, or `just hooks-test` to test hook behavior. CI runs formatting, spelling, Rust and web tests, and checks commit
messages introduced by a push or pull request. The first push to a new branch checks its tip; subsequent pushes check
the new commit range. Existing history is not revalidated.

## Browse

- [Glyph generation](tools/generator/)
- [Web preview](tools/web/)
- [Font assets](fonts/)
- [Documentation](docs/)
- [Development revisions](docs/revisions/)
- [Evaluation rules and Rust evaluator](docs/evaluation.md)
- [Agent working rules](AGENTS.md)
- [Research papers](docs/references/papers/)
