import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { lstatSync, readFileSync, readlinkSync } from "node:fs";
import path from "node:path";

const inputs = ["tools/web", "tools/wasm", "tools/generator", "fonts", "justfile", ".mise.toml"];

export function createBuildInfo(root: string, version: string, devServer: boolean, now = new Date()) {
  const git = (...args: string[]): string => execFileSync("git", args, {
    cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"],
  }).trim();
  let commit: string | null = null;
  let localFingerprint: string | null = null;
  try {
    commit = git("rev-parse", "HEAD");
    const changed = new Set([
      ...git("diff", "--name-only", "-z", "HEAD", "--", ...inputs).split("\0"),
      ...git("ls-files", "--others", "--exclude-standard", "-z", "--", ...inputs).split("\0"),
    ].filter(Boolean));
    if (changed.size > 0) {
      const hash = createHash("sha256");
      for (const file of [...changed].sort()) {
        hash.update(`${file}\0`);
        const absolute = path.join(root, file);
        try {
          const stat = lstatSync(absolute);
          hash.update(`${stat.mode}\0`);
          hash.update(stat.isSymbolicLink() ? readlinkSync(absolute) : readFileSync(absolute));
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
          hash.update("deleted");
        }
        hash.update("\0");
      }
      localFingerprint = hash.digest("hex").slice(0, 12);
    }
  } catch {
    // Source archives cannot claim a clean, committed build.
    commit = null;
  }
  const local = devServer || localFingerprint !== null || commit === null;
  let renderer: string | null = null;
  try {
    renderer = createHash("sha256").update(readFileSync(path.join(root,
      "tools/web/src/app/renderer/wasm/font_wasm_bg.wasm"))).digest("hex");
  } catch { /* The dev server can run with the renderer unavailable. */ }
  return {
    version: local ? `${version}-dev` : version,
    build: now.toISOString().slice(2, 16).replace(/[-:T]/g, "").replace(/^(\d{6})(\d{4})$/, "$1-$2"),
    builtAt: now.toISOString(), commit, localFingerprint, renderer, devServer,
  };
}
