import { readFileSync } from "node:fs";
import { execFileSync, spawnSync } from "node:child_process";

const eventPath = process.env.GITHUB_EVENT_PATH;
if (!eventPath) throw new Error("GITHUB_EVENT_PATH is not set");

// Read event data as JSON instead of interpolating it into shell commands.
const event = JSON.parse(readFileSync(eventPath, "utf8"));
let range: string[] = [];
let message: string | undefined;
if (process.env.GITHUB_EVENT_NAME === "pull_request") {
  const base = execFileSync("git", ["merge-base", event.pull_request.base.sha, event.pull_request.head.sha], {
    encoding: "utf8",
  }).trim();
  range = ["--from", base, "--to", event.pull_request.head.sha];
} else if (process.env.GITHUB_EVENT_NAME === "push") {
  if (!event.before || /^0+$/.test(event.before)) {
    // A new branch has no previous tip. Check its tip without relinting old history.
    console.log("First push to this branch: checking the tip commit only.");
    message = execFileSync("git", ["show", "--no-patch", "--format=%B", event.after], { encoding: "utf8" });
  } else {
    const beforeExists = spawnSync("git", ["cat-file", "-e", `${event.before}^{commit}`], { stdio: "ignore" });
    if (beforeExists.status !== 0) execFileSync("git", ["fetch", "origin", event.before], { stdio: "inherit" });
    range = ["--from", event.before, "--to", event.after];
  }
} else {
  throw new Error(`Unsupported event: ${process.env.GITHUB_EVENT_NAME}`);
}

const result = spawnSync(process.execPath, ["node_modules/@commitlint/cli/cli.js", ...range, "--verbose"], {
  input: message,
  stdio: ["pipe", "inherit", "inherit"],
});
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
