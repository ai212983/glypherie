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
  parseProvidedFnt,
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

function fnt(rows, headers = {}) {
  const {
    width = "8",
    height = "12",
    tracking = "0",
    datalen = "3",
    data = "ABC",
  } = headers;
  const lines = [];
  if (width !== null) lines.push(`width=${width}`);
  if (height !== null) lines.push(`height=${height}`);
  if (tracking !== null) lines.push(`tracking=${tracking}`);
  if (datalen !== null) lines.push(`datalen=${datalen}`);
  if (data !== null) lines.push(`data=${data}`);
  return [...lines, ...rows].join("\n");
}

function throwsMessage(text, displayPath) {
  try {
    parseProvidedFnt(text, displayPath);
  } catch (error) {
    return error.message;
  }
  throw new Error("expected parseProvidedFnt to throw");
}

describe("parseProvidedFnt", () => {
  it("parses minimal accepted header and glyph rows and normalizes CRLF and CR", () => {
    const expected = { width: 8, height: 12, characters: "A" };
    const lf = fnt(["U+0041\t5"]);
    assert.deepEqual(parseProvidedFnt(lf, "test.fnt"), expected);
    assert.deepEqual(
      parseProvidedFnt(lf.split("\n").join("\r\n"), "test.fnt"),
      expected,
    );
    assert.deepEqual(
      parseProvidedFnt(lf.split("\n").join("\r"), "test.fnt"),
      expected,
    );
  });

  it("prefixes every failure with the display path", () => {
    assert.equal(
      throwsMessage("width=8\n", "provided-1-foo.fnt"),
      "provided-1-foo.fnt: not a Playdate source font (missing datalen/data)",
    );
  });

  it("accepts dimensions 1 and 255 but rejects 0, 256, float, NaN and missing", () => {
    for (const field of ["width", "height"]) {
      const missing =
        field === "width" ? "missing width 1..255" : "missing height 1..255";
      for (const value of ["1", "255"]) {
        const parsed = parseProvidedFnt(
          fnt(["U+0041\t5"], { [field]: value }),
          "test.fnt",
        );
        assert.equal(parsed[field], Number(value));
      }
      for (const value of ["0", "256", "1.5", "abc", null]) {
        assert.equal(
          throwsMessage(fnt(["U+0041\t5"], { [field]: value }), "test.fnt"),
          `test.fnt: not a Playdate source font (${missing})`,
        );
      }
    }
  });

  it("reports datalen/data first, then width before height before tracking", () => {
    assert.equal(
      throwsMessage(
        fnt(["U+0041\t5"], {
          width: "0",
          height: "0",
          tracking: "x",
          datalen: null,
          data: null,
        }),
        "test.fnt",
      ),
      "test.fnt: not a Playdate source font (missing datalen/data)",
    );
    assert.equal(
      throwsMessage(
        fnt(["U+0041\t5"], { width: "0", height: "0", tracking: "x" }),
        "test.fnt",
      ),
      "test.fnt: not a Playdate source font (missing width 1..255)",
    );
    assert.equal(
      throwsMessage(fnt(["U+0041\t5"], { height: "0", tracking: "x" }), "test.fnt"),
      "test.fnt: not a Playdate source font (missing height 1..255)",
    );
    assert.equal(
      throwsMessage(fnt(["U+0041\t5"], { tracking: "x" }), "test.fnt"),
      "test.fnt: not a Playdate source font (missing integer tracking)",
    );
    assert.equal(
      throwsMessage(fnt(["U+0041\t5"], { datalen: null }), "test.fnt"),
      "test.fnt: not a Playdate source font (missing datalen/data)",
    );
    assert.equal(
      throwsMessage(fnt(["U+0041\t5"], { data: null }), "test.fnt"),
      "test.fnt: not a Playdate source font (missing datalen/data)",
    );
    assert.equal(
      throwsMessage(fnt(["U+D800\t1"], { width: "0" }), "test.fnt"),
      "test.fnt: not a Playdate source font (missing width 1..255)",
    );
    assert.equal(
      throwsMessage(fnt(["U+D800\t1"], { tracking: "x" }), "test.fnt"),
      "test.fnt: not a Playdate source font (missing integer tracking)",
    );
  });

  it("accepts negative, zero and leading-zero tracking but rejects other shapes", () => {
    for (const tracking of ["-3", "0", "007", "42"]) {
      assert.deepEqual(
        parseProvidedFnt(fnt(["U+0041\t5"], { tracking }), "test.fnt"),
        { width: 8, height: 12, characters: "A" },
      );
    }
    for (const tracking of [null, "+1", "1.0", " 1", "1 ", "12px"]) {
      assert.equal(
        throwsMessage(fnt(["U+0041\t5"], { tracking }), "test.fnt"),
        "test.fnt: not a Playdate source font (missing integer tracking)",
      );
    }
  });

  it("keeps glyph rows and skips pair and malformed rows", () => {
    assert.deepEqual(
      parseProvidedFnt(
        fnt(["U+0041U+0056\t-2", "U+0041U+0056\t2", "U+004a\t7", "U+0041\t5"]),
        "test.fnt",
      ),
      { width: 8, height: 12, characters: "AJ" },
    );
    assert.equal(
      throwsMessage(
        fnt(["U+41\t5", "U+004G\t5", "U+0041 5", "U+0041\t", "U+0041\t-5", "garbage"]),
        "test.fnt",
      ),
      "test.fnt: not a Playdate source font (no glyph entries)",
    );
    assert.equal(
      throwsMessage(fnt(["U+0041U+0056\t-2"]), "test.fnt"),
      "test.fnt: not a Playdate source font (no glyph entries)",
    );
  });

  it("dedupes glyphs and sorts codepoints numerically", () => {
    assert.deepEqual(
      parseProvidedFnt(
        fnt(["U+00E9\t2", "U+10000\t4", "U+0042\t3", "U+0041\t5", "U+0041\t9"]),
        "test.fnt",
      ),
      {
        width: 8,
        height: 12,
        characters: `ABé${String.fromCodePoint(0x10000)}`,
      },
    );
  });

  it("allows D7FF and E000 but rejects the surrogate range", () => {
    assert.deepEqual(
      parseProvidedFnt(fnt(["U+D7FF\t1", "U+E000\t2"]), "test.fnt"),
      {
        width: 8,
        height: 12,
        characters: `${String.fromCodePoint(0xd7ff)}${String.fromCodePoint(0xe000)}`,
      },
    );
    assert.equal(
      throwsMessage(fnt(["U+D800\t1"]), "test.fnt"),
      "test.fnt: not a Playdate source font (U+D800 is a surrogate, not a scalar value)",
    );
    assert.equal(
      throwsMessage(fnt(["U+DFFF\t1"]), "test.fnt"),
      "test.fnt: not a Playdate source font (U+DFFF is a surrogate, not a scalar value)",
    );
  });

  it("accepts U+10FFFF but rejects codepoints above it", () => {
    assert.deepEqual(parseProvidedFnt(fnt(["U+10FFFF\t1"]), "test.fnt"), {
      width: 8,
      height: 12,
      characters: String.fromCodePoint(0x10ffff),
    });
    assert.equal(
      throwsMessage(fnt(["U+110000\t1"]), "test.fnt"),
      "test.fnt: not a Playdate source font (U+110000 exceeds U+10FFFF)",
    );
  });

  it("keeps current header coercions with first duplicate winning", () => {
    assert.equal(
      parseProvidedFnt(fnt(["U+0041\t5"], { width: "0x10" }), "test.fnt").width,
      16,
    );
    assert.equal(
      parseProvidedFnt(fnt(["U+0041\t5"], { width: "1e1" }), "test.fnt").width,
      10,
    );
    assert.equal(
      parseProvidedFnt(fnt(["U+0041\t5"], { width: " 8" }), "test.fnt").width,
      8,
    );
    assert.deepEqual(
      parseProvidedFnt(`${fnt(["U+0041\t5"])}\nwidth=0`, "test.fnt"),
      { width: 8, height: 12, characters: "A" },
    );
  });

  it("accepts present-but-empty datalen/data and ignores data bytes and huge advances", () => {
    assert.deepEqual(
      parseProvidedFnt(fnt(["U+0041\t5"], { datalen: "", data: "" }), "test.fnt"),
      { width: 8, height: 12, characters: "A" },
    );
    assert.deepEqual(
      parseProvidedFnt(
        fnt(["U+0041\t5"], { datalen: "999", data: "!!!" }),
        "test.fnt",
      ),
      { width: 8, height: 12, characters: "A" },
    );
    assert.deepEqual(
      parseProvidedFnt(fnt(["U+0041\t99999999999999999999"]), "test.fnt"),
      { width: 8, height: 12, characters: "A" },
    );
  });
});
