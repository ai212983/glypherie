// Per-family interactive specimens rendered with the WASM font renderer and
// real source font bytes. Each family section is independent; the published
// PNG assessment cards are untouched. Sections stay hidden until their font
// and renderer load, and degrade to a concise message when unavailable.
const TEXT_DEFAULT = "Pack my box with five dozen liquor jugs.";
const MAX_TEXT_LENGTH = 8192;
const INK = [36, 40, 43, 255];
const PAPER = [255, 255, 255, 255];

// Exact request shape for tools/wasm RenderSpec (deny_unknown_fields:
// text, width, height, size_px, axes, hinting, output_bits, mono_threshold,
// gray_gamma, missing_glyphs, kerning, metric_rounding, wrap, align,
// foreground, background, palette?, renderer?). Width/height are the logical
// request bounds: width derives from the viewport (see logicalBounds) while
// height is a first-pass estimate corrected from the result layout below.
// `role` is the stable preview role ("baseline", "reference", "candidate");
// it defaults to the approved baseline and never changes any other control,
// so compared roles share font, size, axes and text exactly.
export function toRenderSpec({ text, sizePx, axes, profile, render, width, height, role }) {
  return {
    text,
    width: Math.min(4096, Math.max(1, Math.ceil(width))),
    height: Math.min(4096, Math.max(1, Math.ceil(height))),
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
    render: (spec) => font.render(spec),
    dispose: () => font.free(),
  };
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

function createController(section) {
  const canvas = section.querySelector("canvas");
  if (section.dataset.available !== "true") {
    return {
      section, renderNow: async () => {}, schedule: () => {},
      disposeFont: () => {},
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
  const state = { generation: 0, font: null, loading: null, failed: false, lastSpec: null, raf: 0, display: { w: 0, h: 0 } };
  // Published defaults may differ from the font's native defaults (for
  // example, optical size follows the initial specimen size).
  for (const input of section.querySelectorAll("[data-axis]")) {
    const value = config.defaultAxes[input.dataset.axis];
    if (Number.isFinite(value)) input.value = String(value);
  }

  // Syncs the display canvas width to the measured viewport; height is
  // driven by the laid-out content at paint time. Keeps prior bounds when
  // the section is hidden (zero size). Returns false for empty.
  const measure = () => {
    const w = viewport.clientWidth;
    if (w > 0 && canvas.width !== w) {
      canvas.width = w;
      canvas.style.width = `${w}px`;
    }
    state.display = { w: canvas.width };
    return state.display.w > 0;
  };

  // Serialized font load: concurrent triggers share one in-flight promise
  // instead of constructing parallel Font instances.
  const ensureFont = () => {
    if (state.font) return Promise.resolve(state.font);
    if (!state.failed && !state.loading) {
      state.loading = (async () => {
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
    if (section.hidden || !measure()) return;
    const font = await ensureFont();
    if (!font || section.hidden) return;
    const zoom = currentZoom();
    const controls = readControls(section, config);
    const width = logicalBounds(state.display.w, zoom);
    const cap = nativeCap(width);
    const spec = toRenderSpec({
      ...controls, profile: currentProfile(), render: config.render,
      width, height: estimateHeight(controls.text, controls.sizePx, cap),
      role: currentRole(),
    });
    // Coalesce repeat requests (input+change and blur-change pairs fire for
    // one edit); only a changed request reaches the renderer. Display width
    // and zoom join the key so a backing-size change repaints even when the
    // shrunken logical request is unchanged (reassigning canvas dimensions
    // clears its pixels).
    const key = JSON.stringify({ displayW: state.display.w, zoom, spec });
    if (key === state.lastSpec) return;
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
      paint(canvas, native, data, zoom, shown);
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
  section.querySelector("[data-reset]")?.addEventListener("click", () => {
    section.querySelector("[data-size]").value = String(config.defaultSize);
    for (const input of section.querySelectorAll("[data-axis]")) {
      input.value = String(config.defaultAxes[input.dataset.axis] ?? input.value);
    }
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
  let debounce = 0;
  for (const input of section.querySelectorAll("[data-size], [data-axis], [data-text]")) {
    input.addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => { syncPreset(); void renderNow(); }, input.hasAttribute("data-text") ? 150 : 0);
    });
    input.addEventListener("change", () => { syncPreset(); void renderNow(); });
  }

  const boot = async () => {
    setEnabled(section, false);
    if (await ensureFont()) setEnabled(section, true);
    else return false;
    syncPreset();
    await renderNow();
    return true;
  };
  return {
    section, renderNow, schedule,
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
  // Profile, version role, and zoom are global: only the visible family renders.
  document.querySelector("#output-mode")?.addEventListener("change", () => controllers.get(activeId)?.renderNow());
  document.querySelector("#renderer-role")?.addEventListener("change", () => controllers.get(activeId)?.renderNow());
  document.querySelector("#zoom")?.addEventListener("input", () => controllers.get(activeId)?.schedule());
  // A viewport resize remeasures the display width and re-renders.
  new ResizeObserver(() => controllers.get(activeId)?.schedule()).observe(document.body);
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
