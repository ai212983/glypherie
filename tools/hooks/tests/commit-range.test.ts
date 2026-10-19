import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { copyFileSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../../../", import.meta.url));

test("CI checks new commit ranges and branch tips while allowing old history", (t) => {
  const repo = mkdtempSync(path.join(tmpdir(), "font-generator-commit-range-"));
  t.after(() => rmSync(repo, { recursive: true, force: true }));
  const git = (...args: string[]) => {
    const result = spawnSync("git", args, { cwd: repo, encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr);
    return result.stdout.trim();
  };
  git("init", "--quiet");
  git("config", "user.name", "Hook Test");
  git("config", "user.email", "hooks@example.invalid");
  git("config", "core.hooksPath", "/dev/null");
  for (const file of ["commitlint.config.ts", "commit-scopes.json"]) {
    copyFileSync(path.join(root, file), path.join(repo, file));
  }
  symlinkSync(path.join(root, "node_modules"), path.join(repo, "node_modules"), "dir");
  const commit = (message: string) => {
    git("commit", "--quiet", "--allow-empty", "-m", message);
    return git("rev-parse", "HEAD");
  };
  const historical = commit("historical message without a conventional prefix");
  const valid = commit("ci(hooks): validate new commit ranges");
  const invalid = commit("feat(unknown): add a feature");
  const check = (name: string, event: unknown, expected: number) => {
    const eventPath = path.join(repo, "event.json");
    writeFileSync(eventPath, JSON.stringify(event));
    const result = spawnSync(process.execPath, [path.join(root, "tools/hooks/check-commits.ts")], {
      cwd: repo,
      encoding: "utf8",
      env: { ...process.env, GITHUB_EVENT_NAME: name, GITHUB_EVENT_PATH: eventPath },
    });
    if (expected === 0) assert.equal(result.status, 0, result.stdout + result.stderr);
    else assert.notEqual(result.status, 0, result.stdout + result.stderr);
  };
  check("push", { before: historical, after: valid }, 0);
  check("push", { before: historical, after: invalid }, 1);
  check("pull_request", { pull_request: { base: { sha: historical }, head: { sha: valid } } }, 0);
  check("pull_request", { pull_request: { base: { sha: historical }, head: { sha: invalid } } }, 1);
  check("push", { before: "0".repeat(40), after: valid }, 0);
  check("push", { before: "0".repeat(40), after: historical }, 1);

  // A new branch's merge tip must not relint the old commits from its other parent.
  git("checkout", "--quiet", "-b", "legacy", historical);
  commit("another historical message");
  git("checkout", "--quiet", "-b", "modern", valid);
  git("merge", "--quiet", "--no-ff", "legacy", "-m", "ci(hooks): merge the legacy branch");
  check("push", { before: "0".repeat(40), after: git("rev-parse", "HEAD") }, 0);
});
