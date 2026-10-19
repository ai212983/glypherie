import { readFileSync } from "node:fs";
import type { UserConfig } from "@commitlint/types";

// Read scopes with fs: commitlint loads this file through its own TS loader,
// so JSON import attributes are avoided.
const scopes: string[] = JSON.parse(
  readFileSync(new URL("./commit-scopes.json", import.meta.url), "utf8"),
);

const config: UserConfig = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "header-max-length": [2, "always", 100],
    "scope-enum": [2, "always", scopes],
  },
};

export default config;
