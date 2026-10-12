// Per-family interactive specimens rendered with the WASM font renderer and
// real source font bytes. Each family section is independent; the published
// PNG assessment cards are untouched. Sections stay hidden until their font
// and renderer load, and degrade to a concise message when unavailable.
import {
  backingSize,
  cssSize,
  magnification,
  nativeHeightCap,
  nativeWidthFor,
  snapTranslation,
} from "./display-scaling.js";
const TEXT_DEFAULT = "Pack my box with five dozen liquor jugs.";
const MAX_TEXT_LENGTH = 8192;
const INK = [36, 40, 43, 255];
const PAPER = [255, 255, 255, 255];

// Exact request shape for tools/wasm RenderSpec (deny_unknown_fields:
// text, width, height, size_px, axes, hinting, output_bits, mono_threshold,
// gray_gamma, missing_glyphs, kerning, letter_spacing_px, spacing_model,
// metric_rounding, wrap, align,
// foreground, background, palette?, renderer?). Width/height are the logical
// request bounds: width derives from the viewport (see logicalBounds) while
// height is a first-pass estimate corrected from the result layout below.
// `role` is the stable preview role ("baseline", "reference", "candidate");
// it defaults to the approved baseline and never changes any other control,
// so compared roles share font, size, axes and text exactly.
function normalizedSpacing(value, profile) {
  const number = Number(value);
  const clamped = Number.isFinite(number) ? Math.min(4, Math.max(-2, number)) : 0;
  return profile === "gray_3bit" ? clamped : Math.sign(clamped) * Math.floor(Math.abs(clamped) + 0.5);
}

export function toRenderSpec({ text, sizePx, axes, profile, render, width, height, role, letterSpacingPx, spacingModel, kerning }) {
  return {
    text,
    width: Math.min(4096, Math.max(1, Math.ceil(width))),
    height: Math.min(4096, Math.max(1, Math.ceil(height))),
    size_px: sizePx,
    axes: { ...axes },
    letter_spacing_px: normalizedSpacing(letterSpacingPx, profile),
    spacing_model: profile === "gray_3bit" ? "auto" : spacingModel ?? "auto",
    hinting: "auto",
    output_bits: profile === "gray_3bit" ? 3 : 1,
    mono_threshold: render?.mono_threshold ?? 128,
    gray_gamma: render?.gray_gamma ?? 1.0,
    missing_glyphs: "error",
    kerning: kerning ?? true,
    metric_rounding: "subpixel",
    wrap: "word",
    align: "left",
    foreground: [...INK],
    background: [...PAPER],
    renderer: role ?? "baseline",
  };
}

function readSectionConfig(section) {
  const data = section.dataset;
  const axes = JSON.parse(data.axes ?? "[]");
  const defaultAxes = JSON.parse(data.defaultAxes ?? "{}");
  const render = JSON.parse(data.render ?? "{}");
  const presets = JSON.parse(data.presets ?? "[]");
  const size = Number(data.defaultSize);
  if (!data.fontUrl || !Number.isFinite(size) || typeof defaultAxes !== "object") throw new Error("Invalid interactive configuration.");
  return {
    fontUrl: data.fontUrl,
    defaultSize: Math.min(512, Math.max(1, size)),
    defaultAxes,
    axes: Array.isArray(axes) ? axes : [],
    render,
    presets: Array.isArray(presets) ? presets.filter((preset) => preset && typeof preset.id === "string" && typeof preset.content === "string") : [],
    sampleText: (data.sampleText || TEXT_DEFAULT).slice(0, MAX_TEXT_LENGTH),
  };
}

function presetFor(presets, text) {
  return presets.find((preset) => preset.content === text)?.id ?? "custom";
}

function status(section, message) {
  const node = section.querySelector("[data-status]");
  if (!node) return;
  node.hidden = !message;
  if (message) node.textContent = message;
}

function setEnabled(section, enabled) {
  for (const control of section.querySelectorAll("fieldset, input, textarea, select, button")) {
    if (control.tagName === "INPUT" && control.type === "hidden") continue;
    control.disabled = !enabled;
  }
}

// Global spacing preferences (spacing model + render kerning toggle,
// shared across all fonts). Only whitelisted models and real booleans are
// accepted; absent, invalid or unreadable values fall back to
// auto/enabled. Storage failures are silently ignored so blocked storage
// never breaks the preview.
const SPACING_MODELS = ["auto", "source", "fitted", "projected"];
const SPACING_PREFERENCE_KEY = "font-preview.spacing";
function readSpacingPreference() {
  const fallback = { model: "auto", kerning: true };
  try {
    const parsed = JSON.parse(localStorage.getItem(SPACING_PREFERENCE_KEY) ?? "");
    if (!parsed || typeof parsed !== "object") return fallback;
    return {
      model: SPACING_MODELS.includes(parsed.model) ? parsed.model : "auto",
      kerning: typeof parsed.kerning === "boolean" ? parsed.kerning : true,
    };
  } catch {
    return fallback;
  }
}
function currentSpacingPreference(section) {
  const model = section.querySelector("[data-spacing-model]")?.value;
  const kerning = section.querySelector("[data-kerning]")?.checked;
  return {
    model: SPACING_MODELS.includes(model) ? model : "auto",
    kerning: typeof kerning === "boolean" ? kerning : true,
  };
}
function saveSpacingPreference(pref) {
  try {
    localStorage.setItem(SPACING_PREFERENCE_KEY, JSON.stringify({
      model: SPACING_MODELS.includes(pref?.model) ? pref.model : "auto",
      kerning: typeof pref?.kerning === "boolean" ? pref.kerning : true,
    }));
  } catch { /* blocked storage keeps session-only controls */ }
}
// One global in-memory preference, initialized once from storage on first
// use. Later controllers apply this value instead of re-reading storage,
// so an unreadable store (blocked getter, quota failure) cannot reset
// choices made earlier this session. Lazily initialized to keep bare
// Node imports free of storage access.
let memoryPreference = null;
function getSpacingPreference() {
  memoryPreference ??= readSpacingPreference();
  return memoryPreference;
}
function setSpacingPreference(pref) {
  memoryPreference = {
    model: SPACING_MODELS.includes(pref?.model) ? pref.model : "auto",
    kerning: typeof pref?.kerning === "boolean" ? pref.kerning : true,
  };
  saveSpacingPreference(memoryPreference);
  applySpacingPreference(memoryPreference);
}
// Sync every family's model/kerning controls to the global choice, so
// already-created controllers, hidden families, renderer changes and
// reloads all use it. Programmatic sets fire no events; the originating
// control's own listeners already scheduled its render, and hidden
// families render on activation.
function applySpacingPreference(pref) {
  const valid = {
    model: SPACING_MODELS.includes(pref?.model) ? pref.model : "auto",
    kerning: typeof pref?.kerning === "boolean" ? pref.kerning : true,
  };
  for (const model of document.querySelectorAll("[data-spacing-model]")) model.value = valid.model;
  for (const box of document.querySelectorAll("[data-kerning]")) box.checked = valid.kerning;
  syncSpacingHints();
}

// Short visible hint describing the selected spacing model in every
// family. Static per-model wording (the auto hint names both renderer
// defaults); gray appends its source-spacing notice while the saved
// selection is still explained.
const SPACING_HINTS = {
  auto: "Renderer default: the candidate uses projected-gap placement; baseline and reference use source spacing.",
  source: "Source spacing: original advances, with the font's pair kerning when enabled.",
  fitted: "Fitted metrics: hinted advances with available bearing corrections.",
  projected: "Projected gap: each pair keeps its own rounded source gap between visible ink columns.",
};
const GRAY_SPACING_NOTE = "Gray uses source spacing; this selection is retained for 1-bit mode.";
function syncSpacingHints() {
  if (typeof document === "undefined") return;
  const gray = currentProfile() === "gray_3bit";
  for (const section of document.querySelectorAll("[data-interactive-family]")) {
    const hint = section.querySelector("[data-spacing-hint]");
    if (!hint) continue;
    const base = SPACING_HINTS[section.querySelector("[data-spacing-model]")?.value] ?? SPACING_HINTS.auto;
    hint.textContent = gray ? `${base} ${GRAY_SPACING_NOTE}` : base;
  }
}

// Renderer asset URLs carrying this script's cache-busting query (if any)
// so a stale cached renderer cannot serve a previous WASM build. The JS
// module and its binary share the same version; an unversioned script URL
// keeps both unversioned (tests, degraded preview).
export function versionedWasmUrls(scriptUrl) {
  const base = new URL(scriptUrl, "http://localhost/");
  const query = base.search;
  return {
    wasmUrl: new URL(`./wasm/font_wasm.js${query}`, base).href,
    wasmBinaryUrl: new URL(`./wasm/font_wasm_bg.wasm${query}`, base).href,
  };
}

// One shared initialized wasm-bindgen module (default init() before use).
let wasmModulePromise = null;
function wasmModule(wasmUrl, wasmBinaryUrl) {
  wasmModulePromise ??= (async () => {
    const wasm = await import(wasmUrl);
    await wasm.default({ module_or_path: wasmBinaryUrl });
    if (typeof wasm.Font !== "function") throw new Error("Font export is missing.");
    return wasm;
  })();
  return wasmModulePromise;
}

// Logical render bound for zoom factor z in a display box of the given
// width: the native request shrinks so integer magnification fills it.
export function logicalBounds(display, zoom) {
  return Math.min(4096, Math.max(1, Math.ceil(display / zoom)));
}

function takePixels(result) {
  const width = result.width();
  const height = result.height();
  const copy = result.pixels();
  return { width, height, pixels: new Uint8ClampedArray(copy.buffer, copy.byteOffset, copy.length) };
}

async function loadFont(wasmUrl, wasmBinaryUrl, fontUrl) {
  const [wasm, response] = await Promise.all([
    wasmModule(wasmUrl, wasmBinaryUrl),
    fetch(fontUrl, { credentials: "same-origin" }),
  ]);
  if (!response.ok) throw new Error(`Font fetch failed: ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (!bytes.length) throw new Error("Empty font response.");
  const font = new wasm.Font(bytes);
  return {
    render: (spec) => font.render(spec),
    // Source kerning data only: never affects render requests or bitmaps.
    // A missing renderer API says nothing about the font's kerning.
    // Identify the loaded renderer and give a reload recovery action.
    kerningPairs: (sizePx, axes) => {
      if (typeof font.kerning_pairs !== "function") {
        throw new Error("The loaded renderer does not support kerning inspection. Reload the page to load the current renderer.");
      }
      return font.kerning_pairs(sizePx, axes ?? {});
    },
    dispose: () => font.free(),
  };
}

// Source kerning pairs for the font-details section: printable-ASCII scope,
// signed 26.6 adjustments, pure helpers kept testable without a DOM.
export function kerningCacheKey(sizePx, axes) {
  const entries = Object.entries(axes ?? {})
    .filter(([, value]) => Number.isFinite(value))
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return JSON.stringify({ sizePx, axes: entries });
}

export function formatKerningAdjustment(adjustment266) {
  const px = adjustment266 / 64;
  const text = (px > 0 ? "+" : "") + String(px);
  return `${text} px`;
}

export function pairCodepoints(left, right) {
  const hex = (cp) => `U+${cp.toString(16).toUpperCase().padStart(4, "0")}`;
  return `${hex(left)} ${hex(right)}`;
}

export function filterKerningPairs(pairs, query) {
  const text = (query ?? "").trim();
  if (!text) return pairs;
  const upper = text.toUpperCase();
  return pairs.filter((pair) => {
    const chars = String.fromCodePoint(pair.left, pair.right);
    return chars.includes(text)
      || chars.toUpperCase().includes(upper)
      || pairCodepoints(pair.left, pair.right).includes(upper);
  });
}

// Blits the shown logical rows onto the display canvas at integer zoom with
// smoothing off. Display width follows the viewport; display height fits the
// laid-out content exactly (growing and shrinking with it), capped for
// browser canvas limits. PAPER fills first so no cleared-black padding shows.
function paint(display, native, data, zoom, shown) {
  if (data.pixels.length !== data.width * data.height * 4) throw new Error("Invalid render pixels.");
  if (!Number.isInteger(shown) || shown <= 0 || shown > data.height) throw new Error("Invalid shown height.");
  native.width = data.width;
  native.height = data.height;
  const nctx = native.getContext("2d", { alpha: false });
  nctx.imageSmoothingEnabled = false;
  nctx.putImageData(new ImageData(data.pixels, data.width, data.height), 0, 0);
  const height = Math.min(16384, Math.max(1, shown * zoom));
  if (display.height !== height) {
    display.height = height;
    display.style.height = `${height}px`;
  }
  const dctx = display.getContext("2d", { alpha: false });
  dctx.imageSmoothingEnabled = false;
  dctx.fillStyle = "rgb(255, 255, 255)";
  dctx.fillRect(0, 0, display.width, display.height);
  dctx.drawImage(native, 0, 0, data.width, shown, 0, 0, data.width * zoom, shown * zoom);
  display.dataset.rendered = "true";
}

function currentProfile() {
  return document.querySelector('input[name="output-profile"]:checked')?.value ?? "mono_1bit";
}

// Stable preview role from the Version switch; absent switch (single-role
// publication) keeps the approved baseline default.
function currentRole() {
  return document.querySelector('input[name="renderer-role"]:checked')?.value ?? "baseline";
}

function currentZoom() {
  const slider = document.querySelector("#zoom");
  return [1, 2, 3, 4][Number(slider?.value)] ?? 1;
}

// Optional pixel-accurate display mode (main interactive preview only, off
// by default): integer physical screen pixels per source pixel, with the
// canvas CSS size adjusted to the actually achieved magnification. The font
// request (size, axes, hinting, spacing, kerning) is unchanged; only the
// request bounds and canvas backing/CSS sizes adapt. Normal mode below is
// untouched when the checkbox is absent or unchecked.
function deviceRatio() {
  const ratio = Number(window.devicePixelRatio);
  return Number.isFinite(ratio) && ratio > 0 ? ratio : 1;
}

function isPixelAccurate() {
  return document.querySelector("#pixel-accurate")?.checked === true;
}

// Align both grids: Chromium pixel-snaps the untransformed canvas paint
// rectangle before applying CSS transforms (HTMLCanvasPainter::PaintReplaced
// and HTMLCanvasElement::PaintInternal). A fractional layout origin can
// therefore move the painted image away from getBoundingClientRect(). First
// move the layout box inward to a whole CSS pixel; then snap its transformed
// origin to a whole device pixel. Both corrections are general positioning
// rules, independent of glyphs. Reserve 1 CSS px + 1 device px at the end.
// Source: https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/core/paint/html_canvas_painter.cc
// Clear our offsets before measuring so repeated calls never accumulate.
function alignToDeviceGrid(display) {
  const ratio = deviceRatio();
  display.style.transform = "";
  display.style.left = "";
  display.style.top = "";
  display.style.position = "relative";
  display.style.transformOrigin = "0 0";
  const base = display.getBoundingClientRect();
  display.style.left = `${Math.ceil(base.left) - base.left}px`;
  display.style.top = `${Math.ceil(base.top) - base.top}px`;
  const rect = display.getBoundingClientRect();
  const { dx, dy } = snapTranslation(rect.left, rect.top, ratio);
  display.style.transform = `translate(${dx}px, ${dy}px) scale(${1 / ratio})`;
}

// Paints native source rows into a device-sized backing with exactly M
// integer magnification per source pixel. Keep the layout box at the
// integer backing dimensions, then cancel DPR with a CSS transform. This
// avoids the browser snapping fractional CSS paint extents before scaling;
// the transformed box is backing/DPR, with whole physical pixel blocks.
// PAPER fills first so no cleared-black padding shows.
function paintExact(display, native, data, mag, shown) {
  if (data.pixels.length !== data.width * data.height * 4) throw new Error("Invalid render pixels.");
  if (!Number.isInteger(shown) || shown <= 0 || shown > data.height) throw new Error("Invalid shown height.");
  if (!Number.isInteger(mag) || mag < 1) throw new Error("Invalid magnification.");
  const ratio = deviceRatio();
  native.width = data.width;
  native.height = data.height;
  const nctx = native.getContext("2d", { alpha: false });
  nctx.imageSmoothingEnabled = false;
  nctx.putImageData(new ImageData(data.pixels, data.width, data.height), 0, 0);
  const backing = backingSize(data.width, shown, mag);
  if (display.width !== backing.width) display.width = backing.width;
  if (display.height !== backing.height) display.height = backing.height;
  display.style.width = `${backing.width}px`;
  display.style.height = `${backing.height}px`;
  // Transforms do not alter flow layout. Reserve only the visible height
  // plus the alignment gutter, rather than the larger unscaled box.
  display.parentElement.style.height = `${cssSize(backing.height, ratio) + 1 + 1 / ratio}px`;
  const dctx = display.getContext("2d", { alpha: false });
  dctx.imageSmoothingEnabled = false;
  dctx.fillStyle = "rgb(255, 255, 255)";
  dctx.fillRect(0, 0, display.width, display.height);
  dctx.drawImage(native, 0, 0, data.width, shown, 0, 0, backing.width, backing.height);
  display.dataset.rendered = "true";
  alignToDeviceGrid(display);
}

function readControls(section, config) {
  const size = Number(section.querySelector("[data-size]")?.value);
  const axes = { ...config.defaultAxes };
  for (const input of section.querySelectorAll("[data-axis]")) {
    const value = Number(input.value);
    if (Number.isFinite(value)) axes[input.dataset.axis] = value;
  }
  for (const output of section.querySelectorAll("[data-axis-value]")) {
    output.value = String(axes[output.dataset.axisValue] ?? "");
  }
  // The slider is the source of truth so a half-typed number entry (empty
  // or partial) never resets the request; valid number edits sync to it.
  const rawSpacing = Number(section.querySelector("[data-spacing]")?.value);
  const profile = currentProfile();
  const modelInput = section.querySelector("[data-spacing-model]");
  if (modelInput) modelInput.disabled = profile === "gray_3bit";
  const letterSpacingPx = normalizedSpacing(rawSpacing, profile);
  for (const input of section.querySelectorAll("[data-spacing], [data-spacing-number]")) {
    input.step = profile === "gray_3bit" ? "0.25" : "1";
    // An empty number input remains editable without changing the request.
    if (!input.hasAttribute("data-spacing-number") || input.value.trim() !== "") {
      input.value = String(letterSpacingPx);
    }
  }
  return {
    text: (section.querySelector("[data-text]")?.value ?? config.sampleText).slice(0, MAX_TEXT_LENGTH),
    sizePx: Number.isFinite(size) ? Math.min(512, Math.max(1, size)) : config.defaultSize,
    axes,
    letterSpacingPx,
    spacingModel: modelInput?.value ?? "auto",
    kerning: section.querySelector("[data-kerning]")?.checked ?? true,
  };
}

function createController(section) {
  const canvas = section.querySelector("canvas");
  if (section.dataset.available !== "true") {
    return {
      section, renderNow: async () => {}, schedule: () => {},
      disposeFont: () => {},
      kerningPairs: async () => { throw new Error("Source kerning data is unavailable for this font."); },
      activate: async () => {
        section.hidden = false;
        canvas.hidden = true;
        setEnabled(section, false);
        status(section, "Interactive preview is unavailable for this font.");
      },
    };
  }
  const native = document.createElement("canvas");
  const viewport = section.querySelector(".interactive-viewport");
  let config = null;
  try {
    config = readSectionConfig(section);
  } catch {
    return null;
  }
  const state = { generation: 0, font: null, loading: null, failed: false, lastSpec: null, raf: 0, display: { cssW: 0, backingW: 0 } };
  // Published defaults may differ from the font's native defaults (for
  // example, optical size follows the initial specimen size).
  for (const input of section.querySelectorAll("[data-axis]")) {
    const value = config.defaultAxes[input.dataset.axis];
    if (Number.isFinite(value)) input.value = String(value);
  }
  // Restore the global spacing model and kerning choice before the first
  // render; every family shares it across font switches, renderer roles
  // and reloads. Uses the in-memory value so a storage read failure
  // cannot reset choices made earlier this session.
  applySpacingPreference(getSpacingPreference());

  // Reserve one CSS pixel plus one device pixel at the right/bottom
  // before measurement. This absorbs both inward alignment corrections;
  // the viewport keeps overflow hidden
  // so no scrollbar artifact appears. Must run before measure(): the gutter
  // padding changes the available content width. The class is `is-…` scoped
  // so it never collides with the header checkbox label styling.
  const syncExactChrome = () => {
    const exact = isPixelAccurate();
    section.classList.toggle("is-pixel-accurate", exact);
    if (!exact) viewport.style.height = "";
    // Numeric compare: the CSSOM may re-serialize fractional pixels.
    const gutter = exact ? 1 + 1 / deviceRatio() : 0;
    for (const side of ["paddingRight", "paddingBottom"]) {
      if (Math.abs(parseFloat(viewport.style[side] || "0") - gutter) > 1e-9) {
        viewport.style[side] = gutter ? `${gutter}px` : "";
      }
    }
  };

  // Measures the available CSS content width from the viewport (end gutter
  // already deducted: clientWidth includes the reserved padding). The normal
  // path also syncs the canvas backing to that width; the pixel-accurate
  // path keeps its own device-sized backing at paint time and only records
  // the CSS width here (backing and CSS widths stay separate quantities).
  // Keeps prior bounds when the section is hidden (zero size).
  const measure = () => {
    const w = viewport.clientWidth - (isPixelAccurate() ? 1 + 1 / deviceRatio() : 0);
    if (w <= 0) return false;
    if (!isPixelAccurate() && canvas.width !== w) {
      canvas.width = w;
      canvas.style.width = `${w}px`;
    }
    state.display = { cssW: w, backingW: canvas.width };
    return true;
  };

  // Re-snaps the painted canvas to the physical pixel grid after scroll or
  // layout shifts. Transform-only: never re-renders and never reschedules.
  const realign = () => {
    if (section.hidden || !isPixelAccurate()) return;
    if (canvas.dataset.rendered !== "true" || canvas.width <= 0) return;
    alignToDeviceGrid(canvas);
  };

  // Serialized font load: concurrent triggers share one in-flight promise
  // instead of constructing parallel Font instances.
  const ensureFont = () => {
    if (state.font) return Promise.resolve(state.font);
    if (!state.failed && !state.loading) {
      state.loading = (async () => {
        try {
          const { wasmUrl, wasmBinaryUrl } = versionedWasmUrls(import.meta.url);
          const fontUrl = new URL(config.fontUrl, document.baseURI).href;
          state.font = await loadFont(wasmUrl, wasmBinaryUrl, fontUrl);
        } catch {
          state.failed = true;
          setEnabled(section, false);
          status(section, "Interactive preview is unavailable for this font.");
        }
        state.loading = null;
        return state.font;
      })();
    }
    return state.loading ?? Promise.resolve(null);
  };

  // Native height cap from the renderer contract (1..=4096 each side and
  // 16777216 texels); layout beyond it cannot render and gets a message.
  const nativeCap = (width) => Math.min(4096, Math.max(1, Math.floor(16777216 / Math.max(1, width))));
  // First-pass request height only; the painted height always comes from the
  // renderer layout below, so this bound favors fewer correction passes.
  const estimateHeight = (text, sizePx, cap) =>
    Math.min(cap, Math.max(1, text.split(/\r\n|\r|\n/).length * Math.ceil(sizePx * 2)));
  const layoutHeight = (result) => {
    try {
      const lines = result.layout()?.lines;
      if (Array.isArray(lines)) return lines.reduce((sum, line) => sum + (line.height_px || 0), 0);
    } catch { /* fall through to zero */ }
    return 0;
  };

  const renderNow = async () => {
    if (section.hidden) return;
    // Mode chrome (class + end gutter) lands before measurement so the
    // measured content width already excludes the reserved gutter.
    syncExactChrome();
    if (!measure()) return;
    const font = await ensureFont();
    if (!font || section.hidden) return;
    const zoom = currentZoom();
    const controls = readControls(section, config);
    // Source request (size, axes, spacing, kerning) is identical in both
    // modes; only the bounded width/height change with the layout math.
    const exact = isPixelAccurate();
    const ratio = deviceRatio();
    const mag = exact ? magnification(zoom, ratio) : zoom;
    const width = exact
      ? nativeWidthFor(state.display.cssW, mag, ratio)
      : logicalBounds(state.display.cssW, zoom);
    const cap = exact ? nativeHeightCap(width, mag) : nativeCap(width);
    const spec = toRenderSpec({
      ...controls, profile: currentProfile(), render: config.render,
      width, height: estimateHeight(controls.text, controls.sizePx, cap),
      role: currentRole(),
    });
    // Coalesce repeat requests (input+change and blur-change pairs fire for
    // one edit); only a changed request reaches the renderer. Display width
    // and zoom join the key so a backing-size change repaints even when the
    // shrunken logical request is unchanged (reassigning canvas dimensions
    // clears its pixels). The exact-mode key carries the CSS width
    // separately from the backing width plus ratio/mode/scale, so a DPR or
    // mode change repaints even when the native request is unchanged.
    const key = exact
      ? JSON.stringify({ mode: "exact", cssW: state.display.cssW, dpr: ratio, mag, zoom, spec })
      : JSON.stringify({ mode: "normal", displayW: state.display.cssW, zoom, spec });
    if (key === state.lastSpec) { realign(); return; }
    const token = ++state.generation;
    // The layout covers the full text at this width regardless of the
    // requested height, so at most one taller correction pass is needed.
    let data = null;
    let shown = 0;
    let full = 0;
    try {
      const first = font.render(spec);
      try {
        data = takePixels(first);
        full = layoutHeight(first);
      } finally {
        first.free();
      }
      const need = Math.min(cap, Math.max(1, full));
      if (need > spec.height) {
        const second = font.render({ ...spec, height: need });
        try {
          data = takePixels(second);
        } finally {
          second.free();
        }
      }
      shown = need;
    } catch (error) {
      // A rejected role (for example `candidate` on a baseline-only build)
      // fails visibly under its own name; the previous canvas stays up but
      // is never presented as the requested role.
      if (token === state.generation) {
        const message = String(error?.message ?? error ?? "");
        status(section, /candidate/i.test(message)
          ? "Candidate preview is unavailable in this build."
          : spec.renderer !== "baseline"
            ? `Interactive ${spec.renderer} preview failed.`
            : "Interactive render failed.");
      }
      return;
    }
    if (token !== state.generation) return;
    try {
      if (exact) {
        paintExact(canvas, native, data, mag, shown);
      } else {
        section.classList.remove("is-pixel-accurate");
        // Normal path retains the legacy render contract exactly:
        // CSS-width backing, ceil(CW/zoom) request, shown*zoom height.
        canvas.style.transform = "";
        canvas.style.position = "";
        canvas.style.transformOrigin = "";
        canvas.style.left = "";
        canvas.style.top = "";
        paint(canvas, native, data, zoom, shown);
        // The exact-mode CSS box lingers when backing dimensions coincide
        // (paint only touches the height style on backing change), so the
        // normal CSS box is restored unconditionally from the backing.
        canvas.style.width = `${canvas.width}px`;
        canvas.style.height = `${canvas.height}px`;
      }
      state.lastSpec = key;
      status(section, full > cap ? "Text too long to preview fully." : "");
    } catch {
      if (token === state.generation) status(section, "Interactive render failed.");
    }
  };
  const schedule = () => {
    if (state.raf) return;
    state.raf = requestAnimationFrame(() => { state.raf = 0; void renderNow(); });
  };

  const syncPreset = () => {
    const select = section.querySelector("[data-preset]");
    if (select) select.value = presetFor(config.presets, section.querySelector("[data-text]")?.value ?? "");
  };
  const syncSpacing = (source, target) => {
    if (source.value.trim() === "" || source.validity.badInput) return;
    const value = Number(source.value);
    if (Number.isFinite(value)) {
      target.value = String(normalizedSpacing(value, currentProfile()));
      source.value = target.value;
    }
  };
  section.querySelector("[data-reset]")?.addEventListener("click", () => {
    section.querySelector("[data-size]").value = String(config.defaultSize);
    for (const input of section.querySelectorAll("[data-axis]")) {
      input.value = String(config.defaultAxes[input.dataset.axis] ?? input.value);
    }
    for (const input of section.querySelectorAll("[data-spacing], [data-spacing-number]")) {
      input.value = "0";
    }
    const model = section.querySelector("[data-spacing-model]");
    if (model) model.value = "auto";
    const kerning = section.querySelector("[data-kerning]");
    if (kerning) kerning.checked = true;
    // Reset restores and saves the global model/kerning defaults in every
    // family; size, axes, offset and text stay active-font-only.
    setSpacingPreference({ model: "auto", kerning: true });
    section.querySelector("[data-text]").value = config.sampleText;
    syncPreset();
    void renderNow();
  });
  section.querySelector("[data-preset]")?.addEventListener("change", (event) => {
    const preset = config.presets.find((candidate) => candidate.id === event.target.value);
    if (!preset) return;
    section.querySelector("[data-text]").value = preset.content;
    void renderNow();
  });
  const spacingRange = section.querySelector("[data-spacing]");
  const spacingNumber = section.querySelector("[data-spacing-number]");
  spacingRange?.addEventListener("input", () => { if (spacingNumber) spacingNumber.value = spacingRange.value; });
  spacingNumber?.addEventListener("input", () => { if (spacingRange) syncSpacing(spacingNumber, spacingRange); });
  let debounce = 0;
  for (const input of section.querySelectorAll("[data-size], [data-axis], [data-text], [data-spacing], [data-spacing-number], [data-spacing-model], [data-kerning]")) {
    input.addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => { syncPreset(); void renderNow(); }, input.hasAttribute("data-text") ? 150 : 0);
    });
    input.addEventListener("change", () => { syncPreset(); void renderNow(); });
  }
  // Persist the global spacing model and kerning toggle, syncing every
  // family. Other controls render without saving; gray keeps its own
  // disabled selector while the global Mono selection is retained in the
  // control value and still forwarded as auto.
  for (const input of section.querySelectorAll("[data-spacing-model], [data-kerning]")) {
    input.addEventListener("change", () => setSpacingPreference(currentSpacingPreference(section)));
  }

  const boot = async () => {
    setEnabled(section, false);
    if (await ensureFont()) setEnabled(section, true);
    else return false;
    // The pixel-accurate toggle stays inert until a renderer is ready.
    const exactToggle = document.querySelector("#pixel-accurate");
    if (exactToggle) exactToggle.disabled = false;
    syncPreset();
    await renderNow();
    return true;
  };
  return {
    section, renderNow, schedule, realign,
    // Source kerning data at an explicit size/axes coordinate. Independent
    // of the render kerning toggle, letter spacing, zoom and profile: those
    // never trigger a kerning fetch.
    kerningPairs: async (sizePx, axes) => {
      const font = await ensureFont();
      if (!font) throw new Error("Source kerning data is unavailable for this font.");
      return font.kerningPairs(sizePx, axes);
    },
    disposeFont: () => {
      // A pending load releases its late font when this family is hidden.
      if (state.loading) {
        state.loading.then(() => {
          if (section.hidden && state.font) { state.font.dispose(); state.font = null; }
        });
      } else if (state.font) { state.font.dispose(); state.font = null; }
    },
    activate: async () => {
      section.hidden = false;
      await new Promise((resolve) => requestAnimationFrame(resolve));
      await boot();
    },
  };
}

if (typeof document !== "undefined") {
  const select = document.querySelector("#font-select");
  const controllers = new Map();
  const controllerFor = (id) => {
    let controller = controllers.get(id);
    if (!controller) {
      const section = document.querySelector(`[data-interactive-family="${id}"]`);
      controller = section && createController(section);
      if (controller) controllers.set(id, controller);
    }
    return controller ?? null;
  };
  // Expandable source-kerning section per family (native details/summary,
  // collapsed by default, independent family states). Lazy extraction on
  // expand; refreshes only on size/axes edits (debounced, cached per
  // coordinate) — never on zoom, profile, spacing, text, preset, or the
  // render kerning checkbox, and never through a render request.
  const wireKerningDetails = (details) => {
    const familyId = details.dataset.kerningDetails;
    const list = details.querySelector("[data-kerning-list]");
    const statusNode = details.querySelector("[data-kerning-status]");
    const count = details.querySelector("[data-kerning-count]");
    const filter = details.querySelector("[data-kerning-filter]");
    if (!familyId || !list || !statusNode || !count || !filter) return;
    const cache = new Map();
    let pairs = null;
    let skipped = 0;
    let generation = 0;
    const setStatus = (message) => {
      statusNode.hidden = !message;
      if (message) statusNode.textContent = message;
    };
    const renderList = () => {
      list.replaceChildren();
      if (!pairs) return;
      const visible = filterKerningPairs(pairs, filter.value);
      count.textContent = pairs.length === 1 ? "(1 pair)" : `(${pairs.length} pairs)`;
      const omissions = skipped === 1
        ? "1 pair needs text-run positioning and is not listed."
        : skipped > 1 ? `${skipped} pairs need text-run positioning and are not listed.` : "";
      if (pairs.length === 0) {
        setStatus(`No nonzero pairs in this ASCII subset at this size and axes. ${omissions}`.trim());
        return;
      }
      if (visible.length === 0) {
        setStatus(`No pairs match the current filter. ${omissions}`.trim());
        return;
      }
      setStatus(omissions);
      const fragment = document.createDocumentFragment();
      for (const pair of visible) {
        const item = document.createElement("li");
        const chars = document.createElement("span");
        chars.className = "pair";
        chars.textContent = String.fromCodePoint(pair.left, pair.right).replaceAll(" ", "␠");
        chars.title = pairCodepoints(pair.left, pair.right);
        item.append(
          chars,
          document.createTextNode(formatKerningAdjustment(pair.adjustment_26_6)),
        );
        fragment.append(item);
      }
      list.append(fragment);
    };
    const coords = () => {
      const section = document.querySelector(`[data-interactive-family="${CSS.escape(familyId)}"]`);
      if (!section) return null;
      const rawSize = Number(section.querySelector("[data-size]")?.value);
      const fallback = Number(section.dataset.defaultSize);
      const axes = JSON.parse(section.dataset.defaultAxes || "{}");
      for (const input of section.querySelectorAll("[data-axis]")) {
        const value = Number(input.value);
        if (Number.isFinite(value)) axes[input.dataset.axis] = value;
      }
      return {
        sizePx: Number.isFinite(rawSize)
          ? Math.min(512, Math.max(1, rawSize))
          : (Number.isFinite(fallback) ? Math.min(512, Math.max(1, fallback)) : 16),
        axes,
      };
    };
    const refresh = async () => {
      const token = ++generation;
      const position = coords();
      const key = position && kerningCacheKey(position.sizePx, position.axes);
      if (key && cache.has(key)) {
        ({ pairs, skipped } = cache.get(key));
        renderList();
        return;
      }
      pairs = null;
      skipped = 0;
      count.textContent = "";
      list.replaceChildren();
      setStatus("Loading kerning pairs…");
      try {
        const controller = controllerFor(familyId);
        if (!position || !controller) throw new Error("Source kerning data is unavailable for this font.");
        const data = await controller.kerningPairs(position.sizePx, position.axes);
        if (token !== generation) return;
        // Current API returns `{ pairs, skipped_pairs }`; tolerate a bare
        // array from older or mock modules.
        const table = Array.isArray(data) ? { pairs: data, skipped_pairs: 0 } : data;
        if (!table || !Array.isArray(table.pairs)) throw new Error("Invalid kerning data.");
        pairs = table.pairs;
        skipped = Number(table.skipped_pairs) || 0;
        if (key) {
          if (cache.size >= 16) cache.delete(cache.keys().next().value);
          cache.set(key, { pairs, skipped });
        }
        renderList();
      } catch (error) {
        if (token !== generation) return;
        pairs = null;
        skipped = 0;
        list.replaceChildren();
        const message = String(error?.message ?? error ?? "");
        // A stale loaded renderer names its own reload fix and must never
        // read as the font lacking kerning. Unavailable fonts keep the
        // source-data message; extraction failures keep their error text.
        setStatus(/reload the page/i.test(message)
          ? message
          : /unavailable/i.test(message)
            ? "Source kerning data is unavailable for this font."
            : `Kerning data error: ${message}`);
      }
    };
    let debounce = 0;
    const scheduleRefresh = () => {
      clearTimeout(debounce);
      generation += 1;
      if (details.open) debounce = setTimeout(() => {
        if (details.open) void refresh();
      }, 200);
    };
    details.addEventListener("toggle", () => {
      clearTimeout(debounce);
      if (details.open) void refresh();
      else generation += 1;
    });
    filter.addEventListener("input", renderList);
    // Size/axes edits refresh an open section with debounce; closing the
    // section cancels in-flight work. All other controls are ignored here.
    const section = document.querySelector(`[data-interactive-family="${CSS.escape(familyId)}"]`);
    for (const input of section?.querySelectorAll("[data-size], [data-axis]") ?? []) {
      input.addEventListener("input", scheduleRefresh);
    }
    section?.querySelector("[data-reset]")?.addEventListener("click", scheduleRefresh);
  };
  for (const details of document.querySelectorAll("[data-kerning-details]")) wireKerningDetails(details);
  let activeId = null;
  const activate = async (id) => {
    activeId = id;
    for (const [known, controller] of controllers) {
      if (known !== id) {
        controller.section.hidden = true;
        controller.disposeFont();
      }
    }
    await controllerFor(id)?.activate();
  };
  // Profile, version role, zoom, and the pixel-accurate toggle are global:
  // only the visible family renders.
  document.querySelector("#output-mode")?.addEventListener("change", () => { controllers.get(activeId)?.renderNow(); syncSpacingHints(); });
  document.querySelector("#renderer-role")?.addEventListener("change", () => { controllers.get(activeId)?.renderNow(); syncSpacingHints(); });
  document.querySelector("#zoom")?.addEventListener("input", () => controllers.get(activeId)?.schedule());
  // Toggling pixel-accurate mode repaints with the other layout path; the
  // request itself (size, axes, text, spacing, kerning) is untouched.
  document.querySelector("#pixel-accurate")?.addEventListener("change", () => controllers.get(activeId)?.renderNow());
  // A viewport resize remeasures the display width and re-renders.
  new ResizeObserver(() => controllers.get(activeId)?.schedule()).observe(document.body);
  // A DPR change repaints (new integer magnification) via the shared
  // display-scale event from index.js; scroll/layout shifts only re-snap
  // the painted origin to the physical grid without re-rendering.
  window.addEventListener("display-scale-change", () => controllers.get(activeId)?.renderNow());
  const realignActive = () => controllers.get(activeId)?.realign?.();
  window.addEventListener("scroll", realignActive, { passive: true, capture: true });
  window.addEventListener("resize", realignActive);
  // A persisted page (BFCache restore) keeps its fonts; a real unload
  // releases every cached font.
  window.addEventListener("pagehide", (event) => {
    if (event.persisted) return;
    for (const controller of controllers.values()) controller.disposeFont();
  });
  // A #family-<id> anchor selects that font when it names a section.
  const hashFamily = () => {
    const id = location.hash.match(/^#family-([A-Za-z0-9-]+)$/)?.[1] ?? null;
    return id && document.querySelector(`[data-interactive-family="${id}"]`) ? id : null;
  };
  if (select) {
    select.addEventListener("change", () => void activate(select.value));
    window.addEventListener("hashchange", () => {
      const id = hashFamily();
      if (id && id !== select.value && select.querySelector(`option[value="${id}"]`)) {
        select.value = id;
        select.dispatchEvent(new Event("change"));
      }
    });
    const initial = hashFamily() ?? select.value;
    if (initial !== select.value && select.querySelector(`option[value="${initial}"]`)) select.value = initial;
    select.dispatchEvent(new Event("change"));
  }
}
