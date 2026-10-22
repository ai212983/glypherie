import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  buildRepertoire,
  defaultPairEntry,
  defaultRepertoire,
  loadPhrases,
  phrasesLua,
} from "./build.mjs";

describe("loadPhrases", () => {
  it("preserves argument order across text and file inputs", async () => {
    const dir = mkdtempSync(join(tmpdir(), "pd-"));
    const file = join(dir, "one.fnt.txt");
    writeFileSync(file, "file phrase");
    const phrases = await loadPhrases([
      { kind: "text", value: "first" },
      { kind: "file", value: file },
      { kind: "text", value: "third" },
    ]);
    assert.deepEqual(phrases, ["first", "file phrase", "third"]);
  });

  it("normalizes newlines and folds tabs to spaces", async () => {
    const phrases = await loadPhrases([{ kind: "text", value: "a\tb\r\nc\rd" }]);
    assert.deepEqual(phrases, ["a b\nc\nd"]);
  });

  it("rejects empty, blank, control-char and oversized phrases", async () => {
    await assert.rejects(loadPhrases([{ kind: "text", value: "   " }]), /whitespace-only/);
    await assert.rejects(loadPhrases([{ kind: "text", value: "a\x07b" }]), /control character/);
    await assert.rejects(
      loadPhrases([{ kind: "text", value: "x".repeat(4097) }]),
      /exceeds 4096/,
    );
    await assert.rejects(
      loadPhrases(Array.from({ length: 17 }, (_, i) => ({ kind: "text", value: `p${i}` }))),
      /at most 16/,
    );
  });

  it("rejects malformed UTF-8 files", async () => {
    const dir = mkdtempSync(join(tmpdir(), "pd-"));
    const file = join(dir, "bad.txt");
    writeFileSync(file, Buffer.from([0xff, 0xfe]));
    await assert.rejects(loadPhrases([{ kind: "file", value: file }]), /malformed UTF-8/);
  });

  it("rejects C1 controls like Rust char::is_control", async () => {
    const nel = String.fromCharCode(0x85);
    const apc = String.fromCharCode(0x9f);
    await assert.rejects(loadPhrases([{ kind: "text", value: `a${nel}b` }]), /control character/);
    await assert.rejects(loadPhrases([{ kind: "text", value: apc }]), /control character/);
  });
});

describe("buildRepertoire", () => {
  it("adds phrase scalars deduplicated in codepoint order without LF", () => {
    const repertoire = buildRepertoire(["héllo\nJ"]);
    for (const ch of ["h", "é", "l", "o", "J"]) {
      assert.ok(repertoire.includes(ch), `repertoire keeps ${ch}`);
    }
    assert.ok(!repertoire.includes("\n"));
    const points = [...repertoire].map((ch) => ch.codePointAt(0));
    assert.deepEqual(points, [...points].sort((a, b) => a - b));
    assert.equal(new Set(points).size, points.length);
    assert.ok(points.includes(0x4a) && points.includes(0xe9));
  });

  it("rejects scalars above the Playdate range", () => {
    assert.throws(() => buildRepertoire(["\u{40000}"]), /exceeds the Playdate range/);
  });

  it("stages manifest coverage equal to the exported repertoire", () => {
    const repertoire = defaultRepertoire(["café"]);
    const entry = defaultPairEntry("Roboto", 16, repertoire);
    assert.equal(entry.characters, repertoire);
    assert.ok(entry.characters.includes("é"));
    assert.equal(entry.font, "fonts/roboto-16-kern");
    assert.equal(entry.unkerned, "fonts/roboto-16-plain");
  });

  it("caps the default repertoire at 1024 distinct scalars", () => {
    // Printable ASCII contributes 95 scalars.
    const extra = (n) => Array.from({ length: n }, (_, i) => String.fromCharCode(0x400 + i)).join("");
    assert.equal([...defaultRepertoire([extra(929)])].length, 1024);
    assert.throws(() => defaultRepertoire([extra(930)]), /1024/);
  });
});

describe("phrasesLua", () => {
  it("quotes unicode safely and ends empty without entries", () => {
    const lua = phrasesLua(["a\"b\\c", "é\n"]);
    assert.ok(!lua.includes("\\u"));
    assert.ok(lua.includes('"a\\"b\\\\c"'));
    assert.ok(phrasesLua([]).includes("return {\n}"));
  });
});
