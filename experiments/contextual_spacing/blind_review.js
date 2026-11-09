/* Masked presentation only: all optical placements come from Python tables. */
(async () => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  try {
    const encoded = $("packed-review").textContent.trim();
    const bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    const data = await new Response(stream).json();
    if (!["masked-wall-review-v1", "masked-spacing-review-v2"].includes(data.schema))
      throw new Error("Unknown comparison format");
    if (data.presentation?.intro) document.querySelector(".intro").textContent = data.presentation.intro;
    if (data.presentation?.moreLabel)
      document.querySelector("#more > summary").textContent = data.presentation.moreLabel;
    let exposed = false;
    for (const font of data.fonts) {
      font.models = Object.fromEntries(
        font.tables.map((table, i) => [String(i), { pairTables: Array(25).fill(table) }]),
      );
    }
    const option = (value, label) => {
      const node = document.createElement("option");
      node.value = value;
      node.textContent = label;
      return node;
    };
    data.fonts.forEach((font, i) => $("font").append(option(String(i), font.label)));
    // One unselected excerpt, rather than a list of cases to rate. Keep every
    // original preset available for optional exploration, with no corpus edits.
    const full = data.presets.find((preset) => preset.id === "lynx-lowercase");
    const shortText = full.text.match(/^(?:\S+\s+){59}\S+/)?.[0] || full.text;
    const samples = [{ id: "quick", label: "Short passage", text: shortText }, ...data.presets];
    samples.forEach((preset) => $("preset").append(option(preset.id, preset.label)));
    $("preset").value = "quick";
    // Stable A/B meanings make chat feedback unambiguous across all selections.
    const order = data.schedule[0].order;
    let layouts = [],
      current;
    function selection() {
      const font = Number($("font").value),
        preset = samples.findIndex((p) => p.id === $("preset").value);
      const width = Number($("width").value);
      return { font, preset, width, order, key: `${font}:${preset}:${width}` };
    }
    function underlinePairs(canvas, font, positions, geometry) {
      const ns = "http://www.w3.org/2000/svg";
      canvas.parentElement.querySelector("svg")?.remove();
      const layer = document.createElementNS(ns, "svg");
      layer.classList.add("pair-underlines");
      layer.setAttribute("aria-hidden", "true");
      layer.setAttribute("viewBox", `0 0 ${geometry.width} ${geometry.height}`);
      layer.setAttribute("width", canvas.style.width);
      layer.setAttribute("height", canvas.style.height);
      layer.toggleAttribute("hidden", !$("underline").checked);
      const indices = new Map(font.codepoints.map((cp, i) => [cp, i]));
      const glyphs = new Map(font.glyphs.map((glyph) => [glyph.codepoint, glyph]));
      positions.lines.forEach((line, row) => {
        for (let i = 1; i < line.placements.length; i++) {
          const left = line.placements[i - 1],
            right = line.placements[i];
          const pair = indices.get(left.codepoint) * font.codepoints.length + indices.get(right.codepoint);
          // Compare the pair's actual table adjustment, not accumulated origin
          // shifts from earlier differences. Never underline across a wrap.
          if (font.tables[0][pair] === font.tables[1][pair]) continue;
          const a = glyphs.get(left.codepoint).bitmap,
            b = glyphs.get(right.codepoint).bitmap;
          const x1 = Math.min(left.x_px + a.left, right.x_px + b.left) - geometry.minX;
          const x2 = Math.max(left.x_px + a.left + a.width, right.x_px + b.left + b.width) - geometry.minX;
          // Below both ink bounds, including descenders. SVG annotations stay
          // separate from the retained binary cells and layout dimensions.
          const y = row * geometry.lineStep - geometry.top + Math.max(a.top + a.height, b.top + b.height) + 1.5;
          const mark = document.createElementNS(ns, "line");
          for (const [key, value] of Object.entries({ x1, x2, y1: y, y2: y })) mark.setAttribute(key, value);
          mark.dataset.pairIndex = right.index;
          layer.append(mark);
        }
      });
      canvas.parentElement.append(layer);
    }
    function render() {
      const previousKey = current?.key;
      current = selection();
      const font = data.fonts[current.font],
        text = samples[current.preset].text,
        zoom = Number($("zoom").value);
      layouts = current.order.map((arm) =>
        ContextualSpacing.layout(font, text, 4, 4, 0, 0, current.width, false, String(arm)),
      );
      for (const [i, side] of ["a", "b"].entries()) {
        $("label-" + side).textContent = side.toUpperCase();
        for (const [scale, factor] of [
          ["native", 1],
          ["zoom", zoom],
        ]) {
          const canvas = $(side + "-" + scale);
          const geometry = ContextualSpacing.paint(canvas, font, layouts[i], factor);
          underlinePairs(canvas, font, layouts[i], geometry);
        }
        $("stats-" + side).textContent =
          `${layouts[i].lines.length} lines · ${layouts[i].lines.reduce((sum, line) => sum + line.width_px, 0)} px summed line advances. Natural wrapping retained.`;
        if (previousKey !== current.key) {
          for (const scale of ["native", "zoom"])
            $(side + "-" + scale).closest(scale === "native" ? ".native" : ".enlarged").scrollTop = 0;
        }
      }
      $("review-status").textContent = `${font.label} · ${font.sizePx} px · ${Object.entries(font.axes)
        .map(([tag, value]) => `${tag}=${value}`)
        .join(", ")} · ${samples[current.preset].label}`;
      updateReveal();
    }
    function updateReveal() {
      $("reveal").disabled = exposed;
      $("methods").hidden = !exposed;
      $("methods").textContent = exposed ? data.arms.join(" versus ") + "." : "";
      for (const [i, side] of ["a", "b"].entries()) {
        $("label-" + side).textContent = side.toUpperCase() + (exposed ? ` · ${data.arms[current.order[i]]}` : "");
        $("stats-" + side).hidden = !exposed;
      }
    }
    for (const id of ["font", "preset", "width", "zoom", "underline"]) $(id).addEventListener("change", render);
    for (const scale of ["native", "enlarged"]) {
      const panes = [...document.querySelectorAll("." + scale)];
      let anchor = null,
        release;
      panes.forEach((pane) =>
        pane.addEventListener("scroll", () => {
          if (anchor && anchor !== pane) return;
          anchor = pane;
          const range = pane.scrollHeight - pane.clientHeight;
          const fraction = range > 0 ? pane.scrollTop / range : 0;
          for (const other of panes)
            if (other !== pane) other.scrollTop = fraction * (other.scrollHeight - other.clientHeight);
          clearTimeout(release);
          release = setTimeout(() => {
            anchor = null;
          }, 100);
        }),
      );
    }
    $("reveal").addEventListener("click", () => {
      exposed = true;
      updateReveal();
    });
    render();
    globalThis.SpacingBlindReview = {
      data,
      samples,
      selection,
      get layouts() {
        return layouts;
      },
    };
  } catch (error) {
    $("review-status").textContent = `Review could not load: ${error.message}`;
    throw error;
  }
})();
