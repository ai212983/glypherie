const scopes = require("./commit-scopes.json");

module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "header-max-length": [2, "always", 100],
    "scope-enum": [2, "always", scopes],
  },
};
