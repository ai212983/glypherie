#!/usr/bin/env node
// Playdate Font Lab staging: export fonts with the maintained generator,
// stage tools/playdate/Source plus fonts/fonts.lua, and compile FontLab.pdx.
// Source-font format: https://sdk.play.date/Inside%20Playdate.html#_fonts
import { execFile } from "node:child_process";
import {
  cp,
  mkdir,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);
const SOURCE_DIR = path.join(REPO_ROOT, "tools", "playdate", "Source");
const OUT_DIR = path.join(REPO_ROOT, "out", "playdate-font-lab");
const STAGED_DIR = path.join(OUT_DIR, "Source");
const STAGED_FONTS_DIR = path.join(STAGED_DIR, "fonts");
const REQUESTS_DIR = path.join(OUT_DIR, "requests");
const PDX_PATH = path.join(OUT_DIR, "FontLab.pdx");

// Printable ASCII repertoire shared by every exported font.
const ASCII = Array.from({ length: 0x7e - 0x20 + 1 }, (_, i) =>
  String.fromCharCode(0x20 + i),
).join("");

// Default repository exports: [font file, display stem] at 16 and 24 px with
// kerned/plain partners. Kerning on/off only flips `config.kerning`; tracking
// stays neutral so advances are never baked twice.
const DEFAULT_FONTS = [
  { file: path.join(REPO_ROOT, "fonts", "Roboto.ttf"), stem: "Roboto" },
  { file: path.join(REPO_ROOT, "fonts", "SourceSans3.ttf"), stem: "SourceSans3" },
];
const DEFAULT_SIZES_PX = [16, 24];

function usage() {
  return `Usage: node tools/playdate/build.mjs [--sdk PATH] [--font PATH ...] [--text TEXT ...] [--text-file PATH ...] [--run]

Stages Playdate Font Lab and compiles out/playdate-font-lab/FontLab.pdx.

  --sdk PATH    Playdate SDK root (or set PLAYDATE_SDK_PATH).
                Falls back to ~/Developer/PlaydateSDK.
  --font PATH   Stage an existing Playdate .fnt (e.g. a browser download)
                instead of exporting. Repeatable; skips the Rust exporter.
  --text TEXT   Custom phrase to inspect. Repeatable.
  --text-file PATH  UTF-8 file whose whole content becomes one phrase. Repeatable.
                --text and --text-file combine in argument order.
  --run         Open the compiled .pdx in the SDK Simulator after building.
  --help, -h    Print this usage.

Without --font, exports Roboto and Source Sans 3 at 16/24 px via
cargo run --bin font_playdate (candidate + native-io features), writing one
kerned/plain partner pair per font and size. Request JSON is kept under
out/playdate-font-lab/requests/. Sources are copied from
tools/playdate/Source; generated fonts.lua, phrases.lua and fonts/ are build
output. Custom phrases are always staged in Source/phrases.lua (empty when
none); default exports add phrase scalars to the printable-ASCII repertoire,
while imported --font coverage is unchanged.`;
}

function parseArgs(argv) {
  const options = { sdk: null, fonts: [], texts: [], run: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--sdk") {
      const value = argv[++i];
      if (!value) throw new Error("--sdk requires a PATH");
      options.sdk = value;
    } else if (arg === "--font") {
      const value = argv[++i];
      if (!value) throw new Error("--font requires a PATH");
      options.fonts.push(value);
    } else if (arg === "--text") {
      const value = argv[++i];
      if (value === undefined) throw new Error("--text requires TEXT");
      options.texts.push({ kind: "text", value });
    } else if (arg === "--text-file") {
      const value = argv[++i];
      if (value === undefined) throw new Error("--text-file requires PATH");
      options.texts.push({ kind: "file", value });
    } else if (arg === "--run") {
      options.run = true;
    } else if (arg === "--help" || arg === "-h") {
      console.log(usage());
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${arg}\n\n${usage()}`);
    }
  }
  return options;
}

function runProcess(file, args) {
  return new Promise((resolve, reject) => {
    execFile(file, args, { encoding: "utf8" }, (error, stdout, stderr) => {
      if (error) {
        error.message += `\n--- stdout ---\n${stdout}\n--- stderr ---\n${stderr}`;
        reject(error);
      } else {
        resolve({ stdout, stderr });
      }
    });
  });
}

export const MAX_PHRASES = 16;
export const MAX_PHRASE_SCALARS = 4096;

// Default-export repertoire: printable ASCII plus custom phrase scalars,
// deduplicated in codepoint order. LF is layout, not a glyph.
export function buildRepertoire(phrases) {
  const scalars = new Set([...ASCII]);
  for (const phrase of phrases) {
    for (const ch of phrase) {
      const codepoint = ch.codePointAt(0);
      if (codepoint === 0x0a) continue;
      if (codepoint > 0x3ffff) {
        throw new Error(
          `U+${codepoint.toString(16).toUpperCase()} exceeds the Playdate range U+0020..U+3FFFF`,
        );
      }
      scalars.add(ch);
    }
  }
  return [...scalars]
    .sort((a, b) => a.codePointAt(0) - b.codePointAt(0))
    .join("");
}

// Native-export repertoire: phrase scalars plus the distinct-scalar limit the
// Playdate format enforces. Imported fonts keep their own coverage, so only
// generated exports go through this limit.
export function defaultRepertoire(phrases) {
  const repertoire = buildRepertoire(phrases);
  const count = [...repertoire].length;
  if (count > 1024) {
    throw new Error(
      `default export repertoire has ${count} distinct scalars, exceeding the 1024 Playdate limit`,
    );
  }
  return repertoire;
}

// Phrases preserve argument order. Tabs fold to spaces (no Playdate tab stop);
// every other C0/C1 control except LF fails, matching Rust char::is_control.
// Fatal UTF-8 decoding rejects malformed file bytes instead of substituting
// replacement characters.
export async function loadPhrases(specs) {
  if (specs.length > MAX_PHRASES) {
    throw new Error(`at most ${MAX_PHRASES} phrases`);
  }
  const phrases = [];
  for (const spec of specs) {
    const label = spec.kind === "file" ? spec.value : "--text";
    let value;
    if (spec.kind === "file") {
      let bytes;
      try {
        bytes = await readFile(spec.value);
      } catch (error) {
        throw new Error(`cannot read ${spec.value}: ${error.message}`);
      }
      try {
        value = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      } catch {
        throw new Error(`cannot read ${spec.value}: malformed UTF-8`);
      }
    } else {
      value = spec.value;
    }
    value = value.replace(/\r\n?/g, "\n").replace(/\t/g, " ");
    if (value.trim().length === 0) {
      throw new Error(`${label}: phrase is empty or whitespace-only`);
    }
    if (
      /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(value)
    ) {
      throw new Error(`${label}: phrase contains an unpaired surrogate`);
    }
    if (
      /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\x80-\x9F]/.test(value)
    ) {
      throw new Error(`${label}: phrase contains a control character other than LF`);
    }
    if ([...value].length > MAX_PHRASE_SCALARS) {
      throw new Error(`${label}: phrase exceeds ${MAX_PHRASE_SCALARS} Unicode scalars`);
    }
    phrases.push(value);
  }
  return phrases;
}

function exportRequest({ sizePx, kerning, characters }) {
  return {
    config: {
      size_px: sizePx,
      axes: {},
      hinting: "auto_fallback",
      output_bits: 1,
      mono_threshold: 128,
      gray_gamma: 1.0,
      characters,
      missing_glyphs: "error",
      kerning,
      metric_rounding: "subpixel",
      mono_raster: {
        dropout: "smart",
        include_stubs: true,
        font_instructions: true,
      },
    },
    // Current web preview pipeline.
    pipeline: {
      fitting: "font_hints_first",
      rasterization: "free_type_mono_terminals",
    },
    letter_spacing_px: 0,
  };
}

// Minimal Playdate source-font header check: enough to reject other `.fnt`
// dialects (BMFont/XML) before deriving coverage from glyph entries.
export function parseProvidedFnt(text, displayPath) {
  const fail = (why) => {
    throw new Error(`${displayPath}: not a Playdate source font (${why})`);
  };
  // Source files may use CRLF; normalize before line-anchored matching.
  const normalized = text.replace(/\r\n?/g, "\n");
  const get = (key) => normalized.match(new RegExp(`^${key}=(.*)$`, "m"))?.[1];
  const width = Number(get("width"));
  const height = Number(get("height"));
  const data = get("data");
  if (get("datalen") == null || data == null) fail("missing datalen/data");
  if (!Number.isInteger(width) || width < 1 || width > 255) {
    fail("missing width 1..255");
  }
  if (!Number.isInteger(height) || height < 1 || height > 255) {
    fail("missing height 1..255");
  }
  if (get("tracking") == null || !/^-?\d+$/.test(get("tracking"))) {
    fail("missing integer tracking");
  }
  const codepoints = [];
  for (const line of normalized.split("\n")) {
    // Glyph rows carry one scalar; pair rows carry two and are skipped here.
    const glyph = line.match(/^U\+([0-9A-Fa-f]{4,6})\t(\d+)$/);
    if (!glyph) continue;
    const codepoint = parseInt(glyph[1], 16);
    if (codepoint >= 0xd800 && codepoint <= 0xdfff) {
      fail(`${glyph[0].split("\t")[0].toUpperCase()} is a surrogate, not a scalar value`);
    }
    if (codepoint > 0x10ffff) {
      fail(`${glyph[0].split("\t")[0].toUpperCase()} exceeds U+10FFFF`);
    }
    codepoints.push(codepoint);
  }
  if (codepoints.length === 0) fail("no glyph entries");
  const characters = [...new Set(codepoints)]
    .sort((a, b) => a - b)
    .map((cp) => String.fromCodePoint(cp))
    .join("");
  return { width, height, characters };
}

// Lua has no \u escapes, so quote UTF-8 bytes with short escapes plus
// zero-padded decimal escapes (padding keeps adjacent escapes unambiguous).
export function luaQuote(value) {
  const bytes = Buffer.from(value, "utf8");
  let out = '"';
  for (const byte of bytes) {
    if (byte === 0x5c) out += "\\\\";
    else if (byte === 0x22) out += '\\"';
    else if (byte === 0x0a) out += "\\n";
    else if (byte === 0x0d) out += "\\r";
    else if (byte === 0x09) out += "\\t";
    else if (byte >= 0x20 && byte <= 0x7e) out += String.fromCharCode(byte);
    else out += `\\${String(byte).padStart(3, "0")}`;
  }
  return `${out}"`;
}

function slugStem(name) {
  // Stable ASCII fallback for non-ASCII-only basenames; the per-entry staged
  // prefix keeps such entries unique.
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "font"
  );
}

export function fontsLua(entries) {
  const lines = [
    "-- Generated by tools/playdate/build.mjs; do not edit.",
    "return {",
  ];
  for (const entry of entries) {
    const fields = [
      `label=${luaQuote(entry.label)}`,
      `font=${luaQuote(entry.font)}`,
    ];
    if (entry.unkerned) fields.push(`unkerned=${luaQuote(entry.unkerned)}`);
    fields.push(`characters=${luaQuote(entry.characters)}`);
    if (entry.sizePx != null) fields.push(`size_px=${entry.sizePx}`);
    lines.push(`  { ${fields.join(", ")} },`);
  }
  lines.push("}");
  return `${lines.join("\n")}\n`;
}

// Custom inspection phrases; exact schema agreed with the app. Always staged,
// empty when no phrases are given so app defaults apply.
export function phrasesLua(phrases) {
  const lines = [
    "-- Generated by tools/playdate/build.mjs; do not edit.",
    "return {",
  ];
  for (const phrase of phrases) {
    lines.push(`  ${luaQuote(phrase)},`);
  }
  lines.push("}");
  return `${lines.join("\n")}\n`;
}

async function hasPdc(root) {
  try {
    await stat(path.join(root, "bin", "pdc"));
    return true;
  } catch {
    return false;
  }
}

export async function resolveSdk(explicit) {
  // An explicit --sdk overrides every fallback and must be usable.
  if (explicit) {
    if (await hasPdc(explicit)) return explicit;
    throw new Error(`invalid --sdk ${explicit}: no bin/pdc inside the SDK root`);
  }
  // A set PLAYDATE_SDK_PATH is authoritative too; never fall past it silently.
  const fromEnv = process.env.PLAYDATE_SDK_PATH;
  if (fromEnv) {
    if (await hasPdc(fromEnv)) return fromEnv;
    throw new Error(
      `invalid PLAYDATE_SDK_PATH ${fromEnv}: no bin/pdc inside the SDK root`,
    );
  }
  const fallback = path.join(os.homedir(), "Developer", "PlaydateSDK");
  if (await hasPdc(fallback)) return fallback;
  throw new Error(
    "Playdate SDK not found: pass --sdk PATH or set PLAYDATE_SDK_PATH to the SDK root containing bin/pdc",
  );
}

async function stageSources() {
  try {
    await stat(path.join(SOURCE_DIR, "main.lua"));
  } catch {
    throw new Error("missing tools/playdate/Source/main.lua");
  }
  await mkdir(STAGED_DIR, { recursive: true });
  await cp(SOURCE_DIR, STAGED_DIR, { recursive: true });
}

// Entry shell for one default font/size pair. Manifest coverage is the
// exported repertoire itself, so the app gate never rejects a present glyph.
export function defaultPairEntry(stem, sizePx, repertoire) {
  const slug = slugStem(stem);
  const base = `${slug}-${sizePx}`;
  return {
    label: `${stem} ${sizePx} px`,
    font: `fonts/${base}-kern`,
    unkerned: `fonts/${base}-plain`,
    characters: repertoire,
    sizePx,
  };
}

async function exportDefaultFonts(repertoire) {
  const entries = [];
  await mkdir(REQUESTS_DIR, { recursive: true });
  for (const { file, stem } of DEFAULT_FONTS) {
    const slug = slugStem(stem);
    for (const sizePx of DEFAULT_SIZES_PX) {
      for (const kerning of [true, false]) {
        const name = `${slug}-${sizePx}-${kerning ? "kern" : "plain"}`;
        const requestPath = path.join(REQUESTS_DIR, `${name}.json`);
        const outputPath = path.join(STAGED_FONTS_DIR, `${name}.fnt`);
        await writeFile(
          requestPath,
          `${JSON.stringify(exportRequest({ sizePx, kerning, characters: repertoire }), null, 2)}\n`,
        );
        try {
          await runProcess("cargo", [
            "run",
            "--locked",
            "--manifest-path",
            path.join(REPO_ROOT, "tools", "generator", "Cargo.toml"),
            "--bin",
            "font_playdate",
            "--",
            file,
            requestPath,
            outputPath,
          ]);
        } catch (error) {
          // Never leave a partial font for a later stage to pick up.
          await rm(outputPath, { force: true });
          throw new Error(`export failed for ${stem} ${sizePx}px: ${error.message}`);
        }
      }
      entries.push(defaultPairEntry(stem, sizePx, repertoire));
    }
  }
  return entries;
}

// Read and validate every custom font before the caller cleans staged output,
// so a --font inside the previous staging tree cannot delete its own input.
export async function loadProvidedFonts(fontPaths) {
  const loaded = [];
  for (let i = 0; i < fontPaths.length; i++) {
    const fontPath = fontPaths[i];
    const resolved = path.isAbsolute(fontPath)
      ? fontPath
      : path.resolve(process.cwd(), fontPath);
    const text = await readFile(resolved, "utf8").catch((error) => {
      throw new Error(`cannot read ${fontPath}: ${error.message}`);
    });
    const parsed = parseProvidedFnt(text, fontPath);
    const original = path.basename(resolved, path.extname(resolved));
    // Unique per-entry prefix: same basenames must never overwrite each other.
    const stagedName = `provided-${i + 1}-${slugStem(original)}`;
    // Playdate .fnt files carry no point size; only a filename size hint is
    // reported, otherwise the entry leaves size_px unset.
    const sizePx = original.match(/-(\d+)(?:px)?$/i)?.[1];
    loaded.push({
      label: original,
      stagedName,
      bytes: text,
      characters: parsed.characters,
      sizePx: sizePx == null ? null : Number(sizePx),
    });
  }
  return loaded;
}

async function compilePdx(sdkRoot) {
  const pdc = path.join(sdkRoot, "bin", "pdc");
  await rm(PDX_PATH, { recursive: true, force: true });
  try {
    await runProcess(pdc, ["-sdkpath", sdkRoot, STAGED_DIR, PDX_PATH]);
  } catch (error) {
    throw new Error(`pdc failed: ${error.message}`);
  }
}

async function launchSimulator(sdkRoot) {
  const bin = path.join(sdkRoot, "bin");
  if (process.platform === "darwin") {
    const app = path.join(bin, "Playdate Simulator.app");
    await stat(app).catch(() => {
      throw new Error(`Simulator not found at ${app}`);
    });
    await runProcess("open", ["-a", app, PDX_PATH]);
    return;
  }
  const candidates =
    process.platform === "win32"
      ? ["PlaydateSimulator.exe"]
      : ["PlaydateSimulator", "playdatesimulator"];
  for (const name of candidates) {
    try {
      await stat(path.join(bin, name));
      const { spawn } = await import("node:child_process");
      spawn(path.join(bin, name), [PDX_PATH], { stdio: "inherit" });
      return;
    } catch {
      // Try the next candidate.
    }
  }
  throw new Error(
    `no Simulator executable in ${bin} for ${process.platform}; open ${PDX_PATH} manually`,
  );
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const sdkRoot = await resolveSdk(options.sdk);
  // Validate all custom inputs before touching staged output.
  const phrases = await loadPhrases(options.texts);
  const provided =
    options.fonts.length > 0 ? await loadProvidedFonts(options.fonts) : null;
  const repertoire = provided ? null : defaultRepertoire(phrases);
  await stageSources();
  // Fresh fonts every run: a failed export must never fall back to stale output.
  await rm(STAGED_FONTS_DIR, { recursive: true, force: true });
  await mkdir(STAGED_FONTS_DIR, { recursive: true });
  let entries;
  if (provided) {
    entries = [];
    for (const font of provided) {
      await writeFile(
        path.join(STAGED_FONTS_DIR, `${font.stagedName}.fnt`),
        font.bytes,
      );
      entries.push({
        label: font.label,
        font: `fonts/${font.stagedName}`,
        characters: font.characters,
        sizePx: font.sizePx,
      });
    }
  } else {
    entries = await exportDefaultFonts(repertoire);
  }
  await writeFile(path.join(STAGED_DIR, "fonts.lua"), fontsLua(entries));
  await writeFile(path.join(STAGED_DIR, "phrases.lua"), phrasesLua(phrases));
  await compilePdx(sdkRoot);
  console.log(`Built ${PDX_PATH} with ${entries.length} font entr${entries.length === 1 ? "y" : "ies"}`);
  if (options.run) await launchSimulator(sdkRoot);
}

const invokedAsMain =
  process.argv[1] != null &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedAsMain) {
  main().catch((error) => {
    console.error(`tools/playdate/build.mjs: ${error.message}`);
    process.exitCode = 1;
  });
}
