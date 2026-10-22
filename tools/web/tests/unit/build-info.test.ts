import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createBuildInfo } from "../../scripts/build-info.ts";

test("build identity distinguishes committed, staged, untracked and deleted inputs", (t) => {
  const root = mkdtempSync(path.join(os.tmpdir(), "glypherie-build-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const git = (...args: string[]): string => execFileSync("git", args, { cwd: root, encoding: "utf8" });
  git("init", "-q");
  mkdirSync(path.join(root, "tools/web"), { recursive: true });
  const file = path.join(root, "tools/web/source.ts");
  writeFileSync(file, "original");
  git("add", ".");
  git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "initial");
  const now = new Date("2026-01-02T03:04:05.000Z");
  const info = (): ReturnType<typeof createBuildInfo> => createBuildInfo(root, "0.1.0", false, now);
  assert.equal(info().version, "0.1.0");
  assert.equal(info().build, "260102-0304");
  assert.equal(info().builtAt, now.toISOString());
  assert.equal(info().localFingerprint, null);
  assert.equal(createBuildInfo(root, "0.1.0", true, now).version, "0.1.0-dev");
  writeFileSync(file, "modified");
  const changed = info();
  assert.equal(changed.version, "0.1.0-dev");
  assert.ok(changed.localFingerprint);
  git("add", ".");
  assert.equal(info().localFingerprint, changed.localFingerprint, "staging preserves content identity");
  writeFileSync(path.join(root, "tools/web/new.ts"), "untracked");
  assert.notEqual(info().localFingerprint, changed.localFingerprint);
  const withUntracked = info().localFingerprint;
  writeFileSync(path.join(root, "tools/web/new.ts"), "another local edit");
  assert.notEqual(info().localFingerprint, withUntracked, "same-minute builds distinguish local edits");
  rmSync(file);
  assert.ok(info().localFingerprint, "deleted inputs retain local status");
});

test("source archives report development with unavailable Git provenance", (t) => {
  const root = mkdtempSync(path.join(os.tmpdir(), "glypherie-archive-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const info = createBuildInfo(root, "0.1.0", false);
  assert.equal(info.version, "0.1.0-dev");
  assert.equal(info.commit, null);
});
