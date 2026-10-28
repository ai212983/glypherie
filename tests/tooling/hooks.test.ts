import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../../", import.meta.url));

test("installed hooks reject bad formatting, spelling and messages without staging changes", (t) => {
  const repo = mkdtempSync(path.join(tmpdir(), "font generator hooks-"));
  t.after(() => rmSync(repo, { recursive: true, force: true }));
  const run = (command: string, args: string[], ok = true) => {
    const result = spawnSync(command, args, {
      cwd: repo,
      encoding: "utf8",
    });
    if (result.error) throw result.error;
    if (ok) assert.equal(result.status, 0, result.stdout + result.stderr);
    return result;
  };
  run("git", ["init", "--quiet"]);
  run("git", ["config", "user.name", "Hook Test"]);
  run("git", ["config", "user.email", "hooks@example.invalid"]);
  for (const file of ["lefthook.yml", "package.json", "dprint.json", "cspell.json", "commitlint.config.ts", "commit-scopes.json"]) {
    copyFileSync(path.join(root, file), path.join(repo, file));
  }
  symlinkSync(path.join(root, "node_modules"), path.join(repo, "node_modules"), "junction");
  run(process.execPath, [path.join(root, "node_modules/lefthook/bin/index.js"), "install"]);
  const commit = (message: string) => run("git", ["commit", "--quiet", "-m", message], false);
  const unchangedAfterFailure = (message: string, diagnostic: string) => {
    const index = run("git", ["ls-files", "--stage", "-z"]).stdout;
    const result = commit(message);
    assert.notEqual(result.status, 0, "Invalid commit was accepted");
    assert.ok((result.stdout + result.stderr).includes(diagnostic), result.stdout + result.stderr);
    assert.equal(run("git", ["ls-files", "--stage", "-z"]).stdout, index);
  };

  const json = path.join(repo, "file with spaces.json");
  writeFileSync(json, '{"value":1}\n');
  run("git", ["add", "file with spaces.json"]);
  unchangedAfterFailure("test(hooks): validate hooks", "formatting");
  assert.equal(readFileSync(json, "utf8"), '{"value":1}\n');
  run(process.execPath, [path.join(root, "node_modules/dprint/bin.cjs"), "fmt", "file with spaces.json"]);
  run("git", ["add", "file with spaces.json"]);
  unchangedAfterFailure("a malformed commit", "type-empty");
  unchangedAfterFailure("test(unknown): validate hooks", "scope-enum");
  assert.equal(commit("test(hooks): validate hooks").status, 0);

  writeFileSync(path.join(repo, "README.md"), "# Font generator\n\nA qqqmisspelledword.\n");
  run("git", ["add", "README.md"]);
  unchangedAfterFailure("docs: describe the generator", "Unknown word");
  writeFileSync(path.join(repo, "README.md"), "# Font generator\n\nGenerate font specimens.\n");
  run("git", ["add", "README.md"]);
  assert.equal(commit("docs: describe the generator").status, 0);

  mkdirSync(path.join(repo, "crates/generator/src"), { recursive: true });
  writeFileSync(path.join(repo, "crates/generator/Cargo.toml"), '[package]\nname = "hook-test"\nversion = "0.1.0"\nedition = "2021"\n');
  writeFileSync(path.join(repo, "crates/generator/src/lib.rs"), "pub fn value()->u8{1}\n");
  run("git", ["add", "crates/generator"]);
  unchangedAfterFailure("test(generator): check formatting", "rust-formatting");
  run("cargo", ["fmt", "--manifest-path", "crates/generator/Cargo.toml"]);
  run("git", ["add", "crates/generator"]);
  assert.equal(commit("test(generator): check formatting").status, 0);
});
