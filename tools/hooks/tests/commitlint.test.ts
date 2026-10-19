import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const scopes: string[] = JSON.parse(readFileSync(new URL("../../../commit-scopes.json", import.meta.url), "utf8"));

function lint(message: string) {
  const result = spawnSync(process.execPath, ["node_modules/@commitlint/cli/cli.js"], {
    cwd: root,
    input: `${message}\n`,
    encoding: "utf8",
  });
  if (result.error) throw result.error;
  return result;
}

test("allowed scopes and optional scopes pass", () => {
  for (const scope of scopes) {
    const result = lint(`test(${scope}): validate commit messages`);
    assert.equal(result.status, 0, result.stdout + result.stderr);
  }
  assert.equal(lint("ci: add commit checks").status, 0);
});

test("breaking changes and generated Git messages pass", () => {
  for (const message of [
    "feat(generator)!: change the output format",
    "feat(generator): change the output format\n\nBREAKING CHANGE: consumers must use the new format.",
    "Merge branch 'main'",
    "fixup! feat(generator): change the output format",
    'Revert "change the output format"',
  ]) {
    const result = lint(message);
    assert.equal(result.status, 0, result.stdout + result.stderr);
  }
});

test("unknown scopes, invalid types, malformed messages and long headers fail", () => {
  const cases: Array<[string, string]> = [
    ["feat(unknown): add a feature", "scope-enum"],
    ["unknown(generator): add a feature", "type-enum"],
    ["add a feature", "type-empty"],
    ["fix(generator):", "subject-empty"],
    [`feat(generator): ${"a".repeat(100)}`, "header-max-length"],
  ];
  for (const [message, rule] of cases) {
    const result = lint(message);
    assert.notEqual(result.status, 0);
    assert.ok(result.stdout.includes(rule), result.stdout + result.stderr);
  }
});
