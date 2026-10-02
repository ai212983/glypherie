// Per-family interactive specimens rendered with the WASM font renderer and
// real source font bytes. Each family section is independent; the published
// PNG assessment cards are untouched. Sections stay hidden until their font
// and renderer load, and degrade to a concise message when unavailable.
const TEXT_DEFAULT = "Pack my box with five dozen liquor jugs.";
const MAX_TEXT_LENGTH = 200;
const CANVAS_WIDTH = 720;
const INK = [36, 40, 43, 255];
const PAPER = [255, 255, 255, 255];

// Exact request shape for tools/wasm RenderSpec (deny_unknown_fields:
// text, width, height, size_px, axes, hinting, output_bits, mono_threshold,
// gray_gamma, missing_glyphs, kerning, metric_rounding, wrap, align,
// foreground, background, palette?). Height scales with size so wrapped lines
// fit; both bounds stay within the renderer's 1..=4096 canvas contract.
export function toRenderSpec({ text, sizePx, axes, profile, render }) {
  return {
    text,
    width: CANVAS_WIDTH,
    height: Math.min(512, Math.max(48, Math.ceil(sizePx * 3))),
    size_px: sizePx,
    axes: { ...axes },
    hinting: "auto",
    output_bits: profile === "gray_3bit" ? 3 : 1,
    mono_threshold: render?.mono_threshold ?? 128,
    gray_gamma: render?.gray_gamma ?? 1.0,
    missing_glyphs: "error",
    kerning: true,
    metric_rounding: "subpixel",
    wrap: "word",
    align: "left",
    foreground: [...INK],
    background: [...PAPER],
  };
}

function readSectionConfig(section) {
  const data = section.dataset;
  const axes = JSON.parse(data.axes ?? "[]");
  const defaultAxes = JSON.parse(data.defaultAxes ?? "{}");
  const render = JSON.parse(data.render ?? "{}");
  const size = Number(data.defaultSize);
  if (!data.fontUrl || !Number.isFinite(size) || typeof defaultAxes !== "object") throw new Error("Invalid interactive configuration.");
  return {
    fontUrl: data.fontUrl,
    defaultSize: Math.min(512, Math.max(1, size)),
    defaultAxes,
    axes: Array.isArray(axes) ? axes : [],
    render,
    sampleText: (data.sampleText || TEXT_DEFAULT).slice(0, MAX_TEXT_LENGTH),
  };
}

function status(section, message) {
  const node = section.querySelector("[data-status]");
  if (!node) return;
  node.hidden = !message;
  if (message) node.textContent = message;
}

function setEnabled(section, enabled) {
  for (const control of section.querySelectorAll("fieldset, input, button")) {
    if (control.tagName === "INPUT" && control.type === "hidden") continue;
    control.disabled = !enabled;
  }
}

// One shared initialized wasm-bindgen module (default init() before use).
let wasmModulePromise = null;
function wasmModule(wasmUrl) {
  wasmModulePromise ??= (async () => {
    const wasm = await import(wasmUrl);
    await wasm.default();
    if (typeof wasm.Font !== "function") throw new Error("Font export is missing.");
    return wasm;
  })();
  return wasmModulePromise;
}

async function loadFont(wasmUrl, fontUrl) {
  const [wasm, response] = await Promise.all([
    wasmModule(wasmUrl),
    fetch(fontUrl, { credentials: "same-origin" }),
  ]);
  if (!response.ok) throw new Error(`Font fetch failed: ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (!bytes.length) throw new Error("Empty font response.");
  const font = new wasm.Font(bytes);
  return {
    renderData: (spec) => {
      const result = font.render(spec);
      try {
        const width = result.width();
        const height = result.height();
        const copy = result.pixels();
        return { width, height, pixels: new Uint8ClampedArray(copy.buffer, copy.byteOffset, copy.length) };
      } finally {
        result.free();
      }
    },
    dispose: () => font.free(),
  };
}

function paint(canvas, data, zoom) {
  if (!Number.isInteger(data?.width) || !Number.isInteger(data?.height)
    || data.width <= 0 || data.height <= 0) {
    throw new Error("Invalid render dimensions.");
  }
  if (data.pixels.length !== data.width * data.height * 4) throw new Error("Invalid render pixels.");
  canvas.width = data.width;
  canvas.height = data.height;
  const context = canvas.getContext("2d", { alpha: false });
  context.imageSmoothingEnabled = false;
  context.putImageData(new ImageData(data.pixels, data.width, data.height), 0, 0);
  canvas.style.width = `${data.width * zoom}px`;
  canvas.style.height = `${data.height * zoom}px`;
  canvas.dataset.rendered = "true";
}

function currentProfile() {
  return document.querySelector('input[name="output-profile"]:checked')?.value ?? "mono_1bit";
}

function currentZoom() {
  const slider = document.querySelector("#zoom");
  return [1, 2, 3, 4][Number(slider?.value)] ?? 1;
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
  return {
    text: (section.querySelector("[data-text]")?.value ?? config.sampleText).slice(0, MAX_TEXT_LENGTH),
    sizePx: Number.isFinite(size) ? Math.min(512, Math.max(1, size)) : config.defaultSize,
    axes,
  };
}

async function initFamily(section) {
  const canvas = section.querySelector("canvas");
  if (section.dataset.available !== "true") {
    section.hidden = false;
    canvas.hidden = true;
    setEnabled(section, false);
    status(section, "Interactive preview is unavailable for this font.");
    return;
  }
  let config;
  try {
    config = readSectionConfig(section);
  } catch {
    return;
  }
  const state = { config, generation: 0, font: null, failed: false, lastWidth: 0, lastHeight: 0, lastSpec: null };
  // Published defaults may differ from the font's native defaults (for
  // example, optical size follows the initial specimen size).
  for (const input of section.querySelectorAll("[data-axis]")) {
    const value = config.defaultAxes[input.dataset.axis];
    if (Number.isFinite(value)) input.value = String(value);
  }
  section.hidden = false;

  const ensureFont = async () => {
    if (!state.font && !state.failed) {
      try {
        const base = new URL(import.meta.url);
        const wasmUrl = new URL("./wasm/font_wasm.js", base).href;
        const fontUrl = new URL(config.fontUrl, document.baseURI).href;
        state.font = await loadFont(wasmUrl, fontUrl);
      } catch {
        state.failed = true;
        setEnabled(section, false);
        status(section, "Interactive preview is unavailable for this font.");
      }
    }
    return state.font;
  };

  const renderNow = async () => {
    const font = await ensureFont();
    if (!font) return;
    const controls = readControls(section, config);
    const spec = toRenderSpec({ ...controls, profile: currentProfile(), render: config.render });
    // Coalesce repeat requests (input+change and blur-change pairs fire for
    // one edit); only a changed request reaches the renderer.
    const key = JSON.stringify(spec);
    if (key === state.lastSpec) return;
    const token = ++state.generation;
    let data;
    try {
      data = font.renderData(spec);
    } catch {
      if (token === state.generation) status(section, "Interactive render failed.");
      return;
    }
    if (token !== state.generation) return;
    try {
      paint(canvas, data, currentZoom());
      state.lastWidth = data.width;
      state.lastHeight = data.height;
      state.lastSpec = key;
      status(section, "");
    } catch {
      if (token === state.generation) status(section, "Interactive render failed.");
    }
  };
  const applyZoom = () => {
    if (state.lastWidth > 0) {
      canvas.style.width = `${state.lastWidth * currentZoom()}px`;
      canvas.style.height = `${state.lastHeight * currentZoom()}px`;
    }
  };

  section.querySelector("[data-reset]")?.addEventListener("click", () => {
    section.querySelector("[data-size]").value = String(config.defaultSize);
    for (const input of section.querySelectorAll("[data-axis]")) {
      input.value = String(config.defaultAxes[input.dataset.axis] ?? input.value);
    }
    section.querySelector("[data-text]").value = config.sampleText;
    void renderNow();
  });
  let debounce = 0;
  for (const input of section.querySelectorAll("[data-size], [data-axis], [data-text]")) {
    input.addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => void renderNow(), input.hasAttribute("data-text") ? 150 : 0);
    });
    input.addEventListener("change", () => void renderNow());
  }
  document.querySelector("#output-mode")?.addEventListener("change", () => void renderNow());
  document.querySelector("#zoom")?.addEventListener("input", applyZoom);

  setEnabled(section, false);
  if (await ensureFont()) setEnabled(section, true);
  else return;
  // A persisted page (BFCache restore) keeps its renderer; only a real
  // unload destroys it, and the next render recreates it on demand.
  window.addEventListener("pagehide", (event) => {
    if (event.persisted || !state.font) return;
    state.font.dispose();
    state.font = null;
  });
  await renderNow();
}

if (typeof document !== "undefined") {
  for (const section of document.querySelectorAll("[data-interactive-family]")) {
    void initFamily(section);
  }
}
