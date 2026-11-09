/* The optical solver runs only in Python. This consumer places completed pair
 * tables and retained bitmaps; test_page_browser.mjs compares its placement with
 * Solver.layout, including signed offsets and line boundaries.
 */
(() => {
  "use strict";
  const densityModels = [
    "hu_alphabet_source_target",
    "hu_density_conserved",
    "hu_density_conserved_touch",
    "hu_fitted_density_conserved_touch",
    "hu_fitted_full_density_conserved_touch",
  ];
  const huModels = ["hu_hersch", "hu_source_relative", "hu_source_calibrated", ...densityModels];
  const sourceTargetFields = ["source_step_px", "source_target_px", "target_area_px2", "unconstrained_step_px"];
  const sourceDiagnosticFields = ["source_kerning", "source_step_px", "source_target_px"];
  const finite = (value) => {
    if (typeof value !== "number" || !Number.isFinite(value)) throw new Error("Expected a finite number.");
    return value;
  };
  const pixelRound = (value) => (value >= 0 ? Math.floor(finite(value) + 0.5) : Math.ceil(finite(value) - 0.5));

  function layout(
    font,
    text,
    kIndex,
    oIndex,
    letterSpacing = 0,
    wordSpacing = 0,
    width = null,
    preserveTabularSpacing = false,
    spacingModel = "hu_hersch",
    diagnosticDelta = null,
  ) {
    if (typeof text !== "string") throw new Error("Sample text must be a string.");
    if (width !== null && finite(width) <= 0) throw new Error("Wrap width must be positive.");
    if (font.monospace && (letterSpacing !== 0 || wordSpacing !== 0))
      throw new Error("Fixed-grid captures require neutral spacing.");
    const glyphs = new Map(font.glyphs.map((glyph) => [glyph.codepoint, glyph]));
    const indices = new Map(font.codepoints.map((cp, i) => [cp, i]));
    const unsupported = [...new Set(Array.from(text).filter((c) => c !== "\n" && !glyphs.has(c.codePointAt(0))))];
    if (unsupported.length)
      throw new Error(
        `Not captured: ${unsupported.map((c) => `${JSON.stringify(c)} (U+${c.codePointAt(0).toString(16).toUpperCase().padStart(4, "0")})`).join(", ")}. Choose characters from the capture details.`,
      );
    if (typeof preserveTabularSpacing !== "boolean") throw new Error("Tabular preservation must be a boolean.");
    const model = font.models[spacingModel];
    if (!model) throw new Error("Unknown spacing model.");
    const table = (preserveTabularSpacing ? model.preservedPairTables : model.pairTables)[kIndex * 5 + oIndex];
    if (!table || table.length !== font.codepoints.length ** 2)
      throw new Error("The selected solver table is incomplete.");
    const selected = diagnosticDelta ? reviewPairs(diagnosticDelta.pairs, diagnosticDelta.deltaPx) : null;
    const letter = pixelRound(letterSpacing),
      word = pixelRound(wordSpacing);
    const lines = [];
    let placements = [],
      pen = 0;
    const finish = () => {
      lines.push({ width_px: pen, placements });
      placements = [];
      pen = 0;
    };
    Array.from(text).forEach((character, index) => {
      if (character === "\n") {
        finish();
        return;
      }
      const cp = character.codePointAt(0),
        glyph = glyphs.get(cp);
      let adjustment = 0;
      if (placements.length) {
        const previous = placements[placements.length - 1].codepoint;
        adjustment = table[indices.get(previous) * font.codepoints.length + indices.get(cp)];
        if (previous !== 32 && cp !== 32) adjustment += letter;
        if (selected?.has(String.fromCodePoint(previous, cp))) adjustment += diagnosticDelta.deltaPx;
      }
      const advance = glyph.advancePx + (cp === 32 ? word : 0);
      if (width !== null && placements.length && pen + adjustment + advance > width) {
        finish();
        adjustment = 0;
      }
      const origin = pen + adjustment;
      placements.push({
        index,
        codepoint: cp,
        glyph_id: glyph.glyphId,
        variant: "original",
        x_px: origin,
        advance_px: advance,
      });
      pen = origin + advance;
    });
    finish();
    return { lines, letter_spacing_px: letter, word_spacing_px: word };
  }

  function reviewPairs(pairs, deltaPx) {
    if (
      !Array.isArray(pairs) ||
      pairs.some((pair) => typeof pair !== "string" || Array.from(pair).length !== 2 || pair.includes("\n"))
    )
      throw new Error("Review pairs must contain exactly two characters.");
    if (!Number.isInteger(deltaPx)) throw new Error("Neighbor review requires a whole-pixel delta.");
    return new Set(pairs);
  }

  function neighborTextLayout(
    font,
    text,
    kIndex,
    oIndex,
    width,
    preserveTabularSpacing,
    spacingModel,
    pairs,
    deltaPx,
    letterSpacing = 0,
    wordSpacing = 0,
  ) {
    return layout(font, text, kIndex, oIndex, letterSpacing, wordSpacing, width, preserveTabularSpacing, spacingModel, {
      pairs,
      deltaPx,
    });
  }

  function neighborLayout(positions, pairs, deltaPx) {
    if (!positions || !Array.isArray(positions.lines)) throw new Error("Neighbor review requires completed positions.");
    const selected = reviewPairs(pairs, deltaPx);
    return {
      ...positions,
      lines: positions.lines.map((line) => {
        let shift = 0;
        const placements = line.placements.map((item, index) => {
          if (index && selected.has(String.fromCodePoint(line.placements[index - 1].codepoint, item.codepoint)))
            shift += deltaPx;
          return { ...item, x_px: item.x_px + shift };
        });
        return { ...line, placements, width_px: line.width_px + shift };
      }),
    };
  }

  function synchronizeScroll(frames) {
    let syncing = false;
    const pending = new WeakMap();
    for (const source of frames)
      source.addEventListener("scroll", () => {
        const expected = pending.get(source);
        pending.delete(source);
        if (
          syncing ||
          (expected &&
            Math.abs(source.scrollTop - expected.top) < 0.01 &&
            Math.abs(source.scrollLeft - expected.left) < 0.01)
        )
          return;
        syncing = true;
        const extent = source.scrollHeight - source.clientHeight;
        const ratio = extent > 0 ? source.scrollTop / extent : 0;
        for (const target of frames)
          if (target !== source) {
            target.scrollTop = ratio * Math.max(0, target.scrollHeight - target.clientHeight);
            target.scrollLeft = source.scrollLeft;
            pending.set(target, { top: target.scrollTop, left: target.scrollLeft });
          }
        syncing = false;
      });
  }

  function layoutGrayscale(font, text, width) {
    const glyphs = new Map(font.glyphs.map((glyph) => [glyph.codepoint, glyph]));
    const lines = [];
    let placements = [],
      pen = 0;
    const finish = () => {
      lines.push({ width_px: pen, placements });
      placements = [];
      pen = 0;
    };
    Array.from(text).forEach((character, index) => {
      if (character === "\n") {
        finish();
        return;
      }
      const cp = character.codePointAt(0),
        glyph = glyphs.get(cp);
      if (!glyph) throw new Error("Character absent from the grayscale capture.");
      const previous = placements.at(-1)?.codepoint;
      let adjustment = previous === undefined ? 0 : font.pairAdjustmentsPx[`${previous},${cp}`] || 0;
      if (placements.length && pen + adjustment + glyph.advancePx > width) {
        finish();
        adjustment = 0;
      }
      const origin = pen + adjustment;
      placements.push({
        index,
        codepoint: cp,
        glyph_id: glyph.glyphId,
        variant: "original",
        x_px: origin,
        advance_px: glyph.advancePx,
      });
      pen = origin + glyph.advancePx;
    });
    finish();
    return { lines, letter_spacing_px: 0, word_spacing_px: 0 };
  }

  function sourceLinearMono(font) {
    const source = font.sourceLayout;
    if (!source) return null;
    return {
      sizePx: font.sizePx,
      metricsAscent: font.metricsAscent,
      metricsDescent: font.metricsDescent,
      metricsLineGap: font.metricsLineGap,
      spacingPolicy: source.spacingPolicy,
      inkLevels: 1,
      pairAdjustmentsPx: source.pairAdjustmentsPx,
      glyphs: font.glyphs.map((glyph) => ({ ...glyph, advancePx: source.advancesPx[glyph.codepoint] })),
    };
  }

  function contactPixels(leftBitmap, rightBitmap, step) {
    if (!Number.isInteger(step)) throw new Error("Contact inspection requires an integer origin step.");
    const cells = (b, origin) => {
      const result = [];
      for (let y = 0; y < b.height; y++)
        for (let x = 0; x < b.width; x++) {
          if (b.pixels[y * b.width + x]) result.push([origin + b.left + x, b.top + y]);
        }
      return result;
    };
    const left = cells(leftBitmap, 0),
      right = new Set(cells(rightBitmap, step).map(([x, y]) => `${x},${y}`));
    const marked = new Map(),
      counts = { overlaps: 0, faces: 0, corners: 0 };
    const rank = { corners: 1, faces: 2, overlaps: 3 };
    const mark = (x, y, kind) => {
      const key = `${x},${y}`,
        previous = marked.get(key);
      if (!previous || rank[kind] > rank[previous.kind]) marked.set(key, { x, y, kind });
    };
    // Closed unit bitmap cells touch at an edge for Manhattan distance one,
    // at a corner for a diagonal neighbor, and overlap at equal coordinates.
    // Contact categories are diagnostics; the selected Python model owns policy.
    for (const [x, y] of left)
      for (let dy = -1; dy <= 1; dy++)
        for (let dx = -1; dx <= 1; dx++) {
          if (!right.has(`${x + dx},${y + dy}`)) continue;
          const kind = dx === 0 && dy === 0 ? "overlaps" : dx === 0 || dy === 0 ? "faces" : "corners";
          counts[kind]++;
          mark(x, y, kind);
          mark(x + dx, y + dy, kind);
        }
    return { ...counts, pixels: [...marked.values()].sort((a, b) => a.y - b.y || a.x - b.x) };
  }

  function contactDisposition(contacts, clearancePolicy) {
    if (contacts.overlaps > 0) return "forbidden_overlap";
    if (contacts.faces > 0 || contacts.corners > 0)
      return clearancePolicy === "no_overlap" ? "allowed_contact" : "forbidden_contact";
    return "separated";
  }

  function paint(canvas, font, positions, zoom, contacts = null) {
    const glyphs = new Map(font.glyphs.map((glyph) => [glyph.codepoint, glyph]));
    let minX = 0,
      maxX = 1,
      top = -Math.ceil(font.metricsAscent || font.sizePx),
      bottom = Math.ceil(-(font.metricsDescent || 0));
    for (const line of positions.lines) {
      minX = Math.min(minX, line.width_px);
      maxX = Math.max(maxX, line.width_px);
      for (const item of line.placements) {
        const bitmap = glyphs.get(item.codepoint).bitmap;
        const origin = font.spacingPolicy === "source_linear_26_6" ? Math.floor(item.x_px + 0.5) : item.x_px;
        minX = Math.min(minX, origin + bitmap.left);
        maxX = Math.max(maxX, origin + bitmap.left + bitmap.width);
        top = Math.min(top, bitmap.top);
        bottom = Math.max(bottom, bitmap.top + bitmap.height);
      }
    }
    const lineStep = Math.max(1, bottom - top + Math.max(2, Math.ceil(font.metricsLineGap || 0)));
    minX = Math.floor(minX);
    const width = Math.max(1, Math.ceil(maxX - minX)),
      height = Math.max(1, lineStep * positions.lines.length);
    if (width > 8192 || height > 8192 || width * height > 8_000_000)
      throw new Error("This preview is too large. Shorten the text or reduce the spacing.");
    canvas.width = width;
    canvas.height = height;
    canvas.style.width = `${width * zoom}px`;
    canvas.style.height = `${height * zoom}px`;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = "black";
    const grayImage = font.inkLevels > 1 ? ctx.getImageData(0, 0, width, height) : null;
    positions.lines.forEach((line, row) => {
      for (const placement of line.placements) {
        const b = glyphs.get(placement.codepoint).bitmap;
        // Vanilla surface::Canvas::draw_line rounds the accumulated 26.6
        // origin here, without rounding individual advances or pair amounts.
        const origin = font.spacingPolicy === "source_linear_26_6" ? Math.floor(placement.x_px + 0.5) : placement.x_px;
        for (let y = 0; y < b.height; y++) {
          for (let x = 0; x < b.width; x++) {
            const ink = b.pixels[y * b.width + x];
            if (ink) {
              const px = origin + b.left - minX + x,
                py = row * lineStep + b.top - top + y;
              if (grayImage) {
                // Match surface::composite's black-over-white source-over and
                // per-texel nearest-byte rounding, including overlapping ink.
                const index = (py * width + px) * 4;
                const shade = Math.round(grayImage.data[index] * (1 - ink / font.inkLevels));
                grayImage.data[index] = grayImage.data[index + 1] = grayImage.data[index + 2] = shade;
              } else ctx.fillRect(px, py, 1, 1);
            }
          }
        }
      }
    });
    if (grayImage) ctx.putImageData(grayImage, 0, 0);
    const markContacts = (pixels, row) => {
      for (const pixel of pixels || []) {
        ctx.fillStyle = { faces: "#e02020", corners: "#0060ff", overlaps: "#8b2fc9" }[pixel.kind];
        ctx.fillRect(pixel.x - minX, row * lineStep + pixel.y - top, 1, 1);
      }
    };
    if (contacts?.pixels) markContacts(contacts.pixels, 0);
    contacts?.contactsByLine?.forEach((line, row) => markContacts(line.pixels, row));
    return { width, height, minX, top, lineStep };
  }

  function mount(data, doc = document) {
    const byId = (id) => doc.getElementById(id);
    const browserFonts = new Map();
    let browserRevision = 0,
      neighborRevision = 0;
    function browserFont(font) {
      const reference = font.browserReference;
      if (!reference) return Promise.reject(new Error("No embedded browser reference."));
      if (!browserFonts.has(reference.fontSha256)) {
        const family = `SpacingReference_${reference.fontSha256}`;
        const face = new FontFace(family, `url(${reference.dataUrl})`);
        browserFonts.set(
          reference.fontSha256,
          face.load().then((loaded) => {
            doc.fonts.add(loaded);
            return family;
          }),
        );
      }
      return browserFonts.get(reference.fontSha256);
    }
    function renderBrowser(font, text, width, zoom) {
      const revision = ++browserRevision,
        reference = font.browserReference;
      const target = byId("browser-native"),
        message = byId("browser-measure");
      const enlarged = byId("browser-enlarged"),
        frame = byId("browser-zoom-frame");
      byId("browser-comparison").hidden = !reference;
      target.hidden = true;
      frame.hidden = true;
      if (!reference) return;
      byId("browser-license").textContent =
        reference.licenseText || "License information is retained in the embedded font’s name records.";
      target.dataset.state = "loading";
      message.textContent = "Loading embedded source font…";
      browserFont(font)
        .then((family) => {
          if (revision !== browserRevision) return;
          for (const node of [target, enlarged]) {
            node.style.fontFamily = `"${family}"`;
            node.style.fontSize = `${font.sizePx}px`;
            node.style.fontVariationSettings =
              Object.entries(font.axes)
                .map(([tag, value]) => `"${tag}" ${value}`)
                .join(", ") || "normal";
            node.style.width = `${width}px`;
            node.textContent = text;
          }
          target.hidden = false;
          // CSS transforms scale after layout, preserving native line breaks,
          // fractional placement and optical-size axes rather than resizing text.
          // https://www.w3.org/TR/css-transforms-1/#transform-rendering
          enlarged.style.transform = `scale(${zoom})`;
          frame.hidden = false;
          frame.style.width = `${width * zoom}px`;
          frame.style.height = `${enlarged.getBoundingClientRect().height}px`;
          target.dataset.state = "ready";
          message.textContent = `${font.sizePx} px · browser shaping and spacing · embedded ${reference.geometry === "original_font_bytes" ? "original font" : "font instance subset"}`;
        })
        .catch((error) => {
          if (revision !== browserRevision) return;
          target.dataset.state = "failed";
          message.textContent = `Browser reference unavailable: ${error.message}`;
        });
    }
    function renderNeighborReview(font, k, o, preserve, zoom) {
      const panel = byId("neighbor-review"),
        config = data.neighborReview;
      if (!panel) return;
      panel.hidden = !config;
      if (!config) return;
      const textMode = config.mode === "text",
        wrap = textMode ? Number(byId("wrap").value) : null;
      const letter = textMode ? Number(byId("letter").value) : 0,
        word = textMode ? Number(byId("word").value) : 0;
      panel.dataset.mode = textMode ? "text" : "pairs";
      if (textMode) {
        panel.querySelector("header h2").textContent = "Compare complete texts";
        panel.querySelector("header p").textContent =
          "Current placement, a diagnostic tighter alternative and the normal browser reference. Both bitmap texts wrap independently at the selected width; glyph shapes and the solver are unchanged.";
      }
      const revision = ++neighborRevision,
        rows = byId("neighbor-review-rows"),
        summary = byId("neighbor-review-summary");
      rows.replaceChildren();
      try {
        if (!config.spacingModel || !font.models[config.spacingModel])
          throw new Error("The review model is not captured.");
        if (
          !textMode &&
          (!Array.isArray(config.words) ||
            config.words.some((text) => typeof text !== "string" || !text || text.includes("\n")))
        )
          throw new Error("Review words must be nonempty single-line text.");
        const showContacts = byId("neighbor-review-contacts")?.checked || false;
        const model = font.models[config.spacingModel],
          policy = model.calibration?.clearance_policy || "strict";
        const modelLabel = modelLabels[config.spacingModel] || config.spacingModel;
        summary.textContent = `Diagnostic neighbor review only · ${font.label} ${font.sizePx} px · ${modelLabel} · source kerning ${data.strengths[k] * 100}% · optical ${data.strengths[o] * 100}% · ${preserve ? "tabular spacing preserved" : "tabular preservation off"} · ${zoom}× · zero letter/word spacing · no wrapping. Only configured review pairs shift by ${config.deltaPx} px; no clearance clamp is applied to the neighbor. Browser reference uses normal source-font shaping.`;
        panel.dataset.model = config.spacingModel;
        panel.dataset.state = "loading";
        panel.dataset.kIndex = String(k);
        panel.dataset.oIndex = String(o);
        panel.dataset.preserve = String(preserve);
        const glyphs = new Map(font.glyphs.map((glyph) => [glyph.codepoint, glyph]));
        const textRows = textMode
          ? [{ text: byId("sample").value, kind: "text" }]
          : [
              ...config.pairs.map((text) => ({ text, kind: "pair" })),
              ...config.words.map((text) => ({ text, kind: "word" })),
            ];
        const browserRows = [];
        const contactCache = new Map();
        const contactsFor = (positions) => {
          const totals = { overlaps: 0, faces: 0, corners: 0 };
          const rank = { corners: 1, faces: 2, overlaps: 3 };
          const contactsByLine = positions.lines.map((line) => {
            const pixels = new Map();
            for (let index = 1; index < line.placements.length; index++) {
              const a = line.placements[index - 1],
                b = line.placements[index];
              const key = `${a.codepoint},${b.codepoint},${b.x_px - a.x_px}`;
              if (!contactCache.has(key))
                contactCache.set(
                  key,
                  contactPixels(glyphs.get(a.codepoint).bitmap, glyphs.get(b.codepoint).bitmap, b.x_px - a.x_px),
                );
              const contacts = contactCache.get(key);
              for (const key of Object.keys(totals)) totals[key] += contacts[key];
              for (const pixel of contacts.pixels) {
                const value = { ...pixel, x: pixel.x + a.x_px },
                  key = `${value.x},${value.y}`;
                if (!pixels.has(key) || rank[value.kind] > rank[pixels.get(key).kind]) pixels.set(key, value);
              }
            }
            return { pixels: [...pixels.values()] };
          });
          return { ...totals, contactsByLine };
        };
        for (const { text, kind } of textRows) {
          const current = layout(font, text, k, o, letter, word, wrap, preserve, config.spacingModel);
          const neighbor = textMode
            ? neighborTextLayout(
                font,
                text,
                k,
                o,
                wrap,
                preserve,
                config.spacingModel,
                config.pairs,
                config.deltaPx,
                letter,
                word,
              )
            : neighborLayout(current, config.pairs, config.deltaPx);
          const row = doc.createElement("article");
          row.className = "neighbor-review-row";
          row.dataset.text = text;
          row.dataset.kind = kind;
          const heading = doc.createElement("h3");
          heading.textContent = textMode ? "Full sample text" : text;
          row.append(heading);
          if (textMode) {
            const selected = new Set(config.pairs);
            const changed = neighbor.lines.reduce(
              (count, line) =>
                count +
                line.placements.filter(
                  (item, index) =>
                    index && selected.has(String.fromCodePoint(line.placements[index - 1].codepoint, item.codepoint)),
                ).length,
              0,
            );
            summary.textContent = `${font.label} ${font.sizePx} px · ${modelLabel} · k ${data.strengths[k] * 100}% / optical ${data.strengths[o] * 100}% · ${preserve ? "tabular preserved" : "tabular preservation off"} · letter ${pixelRound(letter)} px / word ${pixelRound(word)} px · wrap ${wrap} px · ${zoom}×. Diagnostic pairs ${config.pairs.join(", ")}: ${changed} transitions tightened by ${Math.abs(config.deltaPx)} px; independently wrapped lines ${current.lines.length} → ${neighbor.lines.length}. No clearance clamp; browser reference uses normal shaping.`;
          }
          const columns = doc.createElement("div");
          columns.className = "neighbor-review-cells";
          row.append(columns);
          let minimum = null;
          if (kind === "pair") {
            const cps = Array.from(text).map((character) => character.codePointAt(0));
            const index = font.codepoints.indexOf(cps[0]) * font.codepoints.length + font.codepoints.indexOf(cps[1]);
            minimum = (preserve ? model.preservedPairTargetMetadata : model.pairTargetMetadata)[index]
              .clearance_min_step_px;
          }
          for (const [variant, positions] of [
            ["current", current],
            ["neighbor", neighbor],
          ]) {
            const cell = doc.createElement("section");
            cell.className = "neighbor-review-cell";
            cell.dataset.variant = variant;
            const label = doc.createElement("h4");
            label.textContent =
              variant === "current"
                ? "Current"
                : `${Math.abs(config.deltaPx)} px ${config.deltaPx < 0 ? "closer" : "farther"}`;
            cell.append(label);
            const contacts = contactsFor(positions),
              disposition = contactDisposition(contacts, policy);
            for (const [scale, factor] of [
              ["native", 1],
              ["zoom", zoom],
            ]) {
              const paper = doc.createElement("div");
              paper.className = `paper ${scale === "native" ? "neighbor-native" : "neighbor-zoom"}`;
              if (textMode) paper.dataset.neighborScroll = scale;
              const canvas = doc.createElement("canvas");
              canvas.dataset.scale = scale;
              canvas.setAttribute("role", "img");
              canvas.setAttribute(
                "aria-label",
                `${textMode ? "Reading passage" : text} · ${label.textContent} · ${scale === "native" ? "native size" : `${zoom}×`}`,
              );
              paint(canvas, font, positions, factor, scale === "zoom" && showContacts ? contacts : null);
              paper.append(canvas);
              cell.append(paper);
            }
            const details = doc.createElement("p");
            details.className = "hint neighbor-review-contact-summary";
            const descriptions = {
              forbidden_overlap: "forbidden occupied-cell overlap",
              forbidden_contact: "contact forbidden under strict clearance",
              allowed_contact: "allowed edge/corner contact",
              separated: "no contact or overlap",
            };
            details.textContent = `${contacts.overlaps} overlaps · ${contacts.faces} edge contacts · ${contacts.corners} corner contacts · ${descriptions[disposition]}${textMode ? ` · ${positions.lines.length} lines` : ` · terminal width ${positions.lines[0].width_px} px`}`;
            for (const key of ["overlaps", "faces", "corners"]) cell.dataset[key] = String(contacts[key]);
            cell.dataset.policy = policy;
            cell.dataset.disposition = disposition;
            cell.dataset.width = String(positions.lines[0].width_px);
            cell.dataset.lines = String(positions.lines.length);
            if (kind === "pair") {
              const step = positions.lines[0].placements[1].x_px - positions.lines[0].placements[0].x_px;
              cell.dataset.step = String(step);
              cell.dataset.minimum = minimum == null ? "" : String(minimum);
              cell.dataset.feasible = minimum == null ? "" : String(step >= minimum);
              details.textContent += ` · origin step ${step} px${minimum == null ? " · wall-order bound unavailable" : ` · ${step >= minimum ? "meets" : "below"} ${policy === "no_overlap" ? "no-overlap" : "strict"} wall-order bound ${minimum} px`}`;
            }
            if (o === 0) details.textContent += " · optical guard inactive at zero strength";
            if (variant === "neighbor") details.textContent += " · diagnostic only; not clamped";
            cell.append(details);
            columns.append(cell);
          }
          const browser = doc.createElement("section");
          browser.className = "neighbor-review-cell";
          browser.dataset.variant = "browser";
          const label = doc.createElement("h4");
          label.textContent = "Browser reference";
          browser.append(label);
          const nativePaper = doc.createElement("div");
          nativePaper.className = "paper neighbor-native";
          const native = doc.createElement("span");
          native.className = "neighbor-browser-native";
          native.dataset.scale = "native";
          if (textMode) nativePaper.dataset.neighborScroll = "native";
          nativePaper.append(native);
          browser.append(nativePaper);
          const zoomPaper = doc.createElement("div");
          zoomPaper.className = "paper neighbor-zoom";
          const frame = doc.createElement("div");
          frame.className = "neighbor-browser-frame";
          const enlarged = doc.createElement("span");
          enlarged.className = "neighbor-browser-zoom";
          enlarged.dataset.scale = "zoom";
          if (textMode) zoomPaper.dataset.neighborScroll = "zoom";
          frame.append(enlarged);
          zoomPaper.append(frame);
          browser.append(zoomPaper);
          const note = doc.createElement("p");
          note.className = "hint";
          note.textContent = "Loading embedded original font…";
          browser.append(note);
          columns.append(browser);
          rows.append(row);
          browserRows.push({ native, enlarged, frame, browser, note, text });
        }
        if (textMode) {
          for (const scale of ["native", "zoom"]) {
            synchronizeScroll([...rows.querySelectorAll(`[data-neighbor-scroll="${scale}"]`)]);
          }
        }
        browserFont(font)
          .then((family) => {
            if (revision !== neighborRevision) return;
            for (const { native, enlarged, frame, browser, note, text } of browserRows) {
              for (const node of [native, enlarged]) {
                Object.assign(node.style, {
                  display: "inline-block",
                  whiteSpace: textMode ? "pre-wrap" : "pre",
                  overflowWrap: textMode ? "break-word" : "normal",
                  fontFamily: `"${family}"`,
                  fontSize: `${font.sizePx}px`,
                  fontWeight: "normal",
                  fontStyle: "normal",
                  fontKerning: "auto",
                  fontFeatureSettings: "normal",
                  fontOpticalSizing: "none",
                  fontSynthesis: "none",
                  fontVariantLigatures: "normal",
                  letterSpacing: "normal",
                  wordSpacing: "normal",
                  lineHeight: "normal",
                  fontVariationSettings:
                    Object.entries(font.axes)
                      .map(([tag, value]) => `"${tag}" ${value}`)
                      .join(", ") || "normal",
                });
                if (textMode) node.style.width = `${wrap}px`;
                node.textContent = text;
              }
              enlarged.style.transform = `scale(${zoom})`;
              enlarged.style.transformOrigin = "top left";
              frame.style.width = `${native.getBoundingClientRect().width * zoom}px`;
              frame.style.height = `${enlarged.getBoundingClientRect().height}px`;
              browser.dataset.state = "ready";
              note.textContent = `Normal source-font shaping · zero tracking · ${textMode ? `wrap ${wrap} px` : "no wrapping"}`;
            }
            panel.dataset.state = "ready";
          })
          .catch((error) => {
            if (revision !== neighborRevision) return;
            panel.dataset.state = "failed";
            summary.textContent += ` Browser reference unavailable: ${error.message}`;
          });
      } catch (error) {
        panel.dataset.state = "failed";
        summary.textContent = `Neighbor review unavailable: ${error.message}`;
      }
    }
    if (
      ![
        "contextual-spacing-page-v5",
        "contextual-spacing-page-v6",
        "contextual-spacing-page-v7",
        "contextual-spacing-page-v8",
        "contextual-spacing-page-v9",
      ].includes(data.schema_version)
    )
      throw new Error("Unsupported comparison data. Regenerate this page.");
    if (!data.cases.length) throw new Error("No completed captures available.");
    for (const [index, font] of data.cases.entries()) {
      const option = doc.createElement("option");
      option.value = String(index);
      option.textContent = font.label;
      byId("family").append(option);
    }
    const modelLabels = {
      hu_alphabet_source_target: "Hu · fixed source alphabet target",
      hu_density_conserved: "Hu · density conservation · strict clearance",
      hu_density_conserved_touch: "Hu · bitmap-wall density conservation · touching allowed",
      hu_fitted_density_conserved_touch: "Hu · fitted-wall density conservation · touching allowed",
      hu_fitted_full_density_conserved_touch: "Hu · complete-outline construction · touching allowed",
      hu_source_calibrated: "Hu · shared target · source-designed reference",
      hu_hersch: "Hu/Hersch · delivered bitmap reference spacing",
      hu_source_relative: "Hu · source-relative compensation",
      counterspace: "CounterSpace · raster calibration · closest feasible",
      counterspace_delivered_first: "CounterSpace · raster calibration · first crossing",
      counterspace_source_first: "CounterSpace · source calibration · first crossing",
      filtered_walls: "Filtered-wall comparison",
      font_calibrated: "FontForge calibrated comparison",
      source_relative: "FontForge · source-relative comparison",
      balanced: "Fixed target (diagnostic)",
    };
    const comparedModels = data.comparisonModels;
    if (
      comparedModels &&
      (comparedModels.length !== 2 || comparedModels.some((name) => !data.cases.every((font) => font.models[name])))
    )
      throw new Error("Two completed models are required for side-by-side comparison.");
    const availableModels =
      comparedModels ||
      Object.keys(data.cases[0].models).filter((name) => data.cases.every((font) => font.models[name]));
    const constructionComparison = comparedModels?.includes("hu_fitted_full_density_conserved_touch") || false;
    if (comparedModels) {
      const fittedComparison = comparedModels.includes("hu_fitted_density_conserved_touch");
      const touchingComparison = !fittedComparison && comparedModels.includes("hu_density_conserved_touch");
      const conservationComparison =
        fittedComparison || touchingComparison || comparedModels.includes("hu_density_conserved");
      const densityComparison = comparedModels.includes("hu_source_calibrated");
      const shortLabels = {
        hu_source_relative: "Source-relative",
        hu_hersch: densityComparison ? "Bitmap reference" : "Shared target",
        hu_source_calibrated: conservationComparison ? "Previous shared target" : "Source reference",
        hu_density_conserved: touchingComparison ? "Strict clearance" : "Latest candidate",
        hu_density_conserved_touch: fittedComparison ? "Bitmap walls" : "Latest candidate",
        hu_fitted_density_conserved_touch: constructionComparison ? "Current control" : "Latest candidate",
        hu_fitted_full_density_conserved_touch: "Construction-order candidate",
      };
      for (const [i, placement] of ["metric", "optical"].entries()) {
        const card = doc.querySelector(`[data-placement="${placement}"]`);
        card.querySelector("h2").textContent = shortLabels[comparedModels[i]] || modelLabels[comparedModels[i]];
        card.querySelector(".eyebrow").textContent = conservationComparison
          ? "Fixed-alphabet density experiment"
          : densityComparison
            ? "Shared-target calibration"
            : "Hu optical spacing";
        const hint = doc.createElement("p");
        hint.className = "hint";
        hint.textContent =
          comparedModels[i] === "hu_fitted_full_density_conserved_touch"
            ? "Construct complete fitted-outline walls, filter them, find cavities again, then measure the retained body window. The same fixed-alphabet density rule, rounding and bitmap overlap protection apply."
            : constructionComparison && comparedModels[i] === "hu_fitted_density_conserved_touch"
              ? "Retained fitted-wall control: construct and filter inside the body window. Displayed bitmap glyphs, density rule, rounding and overlap protection match the candidate."
              : comparedModels[i] === "hu_fitted_density_conserved_touch"
                ? "Fitted-outline walls supply measurement and the recalibrated fixed-alphabet target. Displayed ink and the no-overlap guard still use the original captured bitmaps."
                : fittedComparison && comparedModels[i] === "hu_density_conserved_touch"
                  ? "Delivered bitmap walls supply measurement and density calibration. Edge and corner contacts are allowed; occupied-cell overlap is forbidden."
                  : comparedModels[i] === "hu_density_conserved_touch"
                    ? "Same fixed-alphabet density target and rounding. Edge and corner contacts are allowed; occupied-cell overlap is forbidden."
                    : touchingComparison && comparedModels[i] === "hu_density_conserved"
                      ? "Previous density-conserving model with strict clearance: occupied cells may neither overlap nor touch."
                      : comparedModels[i] === "hu_source_relative"
                        ? "Preserves each pair’s source-designed filtered gap."
                        : comparedModels[i] === "hu_density_conserved"
                          ? "Fixed source-alphabet mean origin spacing sets density using delivered walls. Conservation applies before rounding and clearance, not to each word."
                          : comparedModels[i] === "hu_source_calibrated"
                            ? "Source-designed nn/HH sets one shared target, measured against delivered bitmap walls. Overall source-font density is not constrained by this mode."
                            : densityComparison
                              ? "Rasterized nn/HH at bitmap metric spacing sets density. Delivered bitmap walls determine placement."
                              : "Balances filtered gaps toward a font-calibrated shared target.";
        card.querySelector("header").after(hint);
        card
          .querySelectorAll("canvas")
          .forEach((canvas) =>
            canvas.setAttribute(
              "aria-label",
              `${shortLabels[comparedModels[i]]} placement ${canvas.id.endsWith("native") ? "at native size" : "enlarged"}`,
            ),
          );
      }
      doc.querySelector('label[for="spacing-model"]').textContent = "Inspect model";
      byId("optical").closest(".field").querySelector(".hint").textContent = "Applied to both comparison columns";
      const intro = doc.querySelector(".intro");
      if (intro) {
        intro.querySelector("h1").textContent = constructionComparison
          ? "Complete outlines, same bitmap forms"
          : fittedComparison
            ? "Fitted walls, unchanged bitmap ink"
            : touchingComparison
              ? "Optical spacing with touching allowed"
              : conservationComparison
                ? "Density-conserving optical spacing"
                : densityComparison
                  ? "Shared-target density calibration"
                  : "Two Hu spacing modes";
        intro.querySelector("p:last-child").textContent = constructionComparison
          ? "Compare the retained control with the construction-order candidate across complete texts, alongside normal browser rendering. Each binary view wraps independently. Glyphs, the density rule, rounding and overlap protection are unchanged; optical quality remains pending assessment."
          : fittedComparison
            ? "Compare bitmap-wall and fitted-outline-wall measurements. Each geometry recalibrates the same fixed-alphabet source-origin density rule; both display identical bitmap glyphs and use bitmap overlap protection."
            : touchingComparison
              ? "Compare strict clearance with the latest candidate using the same density target and rounding. Edge and corner contacts are allowed; occupied-cell overlap remains forbidden."
              : conservationComparison
                ? "Compare the previous shared target with a candidate calibrated from fixed source alphabets and actual bitmap walls. Continuous mean conservation is limited to the calibration alphabet before rounding and clearance."
                : densityComparison
                  ? "Compare bitmap-reference density with source-designed density on the same delivered glyphs."
                  : "Compare source-relative compensation with shared-target balancing on the same captured glyphs.";
      }
      if (constructionComparison) {
        const comparison = doc.querySelector(".comparisons");
        // The cards share seven grid rows. Keep the browser's ancillary notes
        // in one last row so native and enlarged panes align across columns.
        const browser = byId("browser-comparison"),
          notes = doc.createElement("div");
        let node = browser.querySelector(".enlarged").nextElementSibling;
        while (node) {
          const next = node.nextElementSibling;
          notes.append(node);
          node = next;
        }
        browser.append(notes);
        comparison.classList.add("construction-comparison");
        comparison.append(browser);
        comparison.setAttribute("aria-label", "Whole-text construction-order comparison");
      }
    }
    byId("spacing-model").replaceChildren();
    for (const name of availableModels) {
      const option = doc.createElement("option");
      option.value = name;
      option.textContent =
        data.schema_version === "contextual-spacing-page-v6" && name === "counterspace"
          ? "CounterSpace · source calibration · first crossing (retained)"
          : modelLabels[name] || name;
      byId("spacing-model").append(option);
    }
    const presets = data.presets || [];
    for (const entry of [
      { id: "default", label: "Default sample" },
      ...presets,
      { id: "custom", label: "Custom text" },
    ]) {
      const option = doc.createElement("option");
      option.value = entry.id;
      option.textContent = entry.label;
      option.disabled = entry.id === "custom";
      byId("preset").append(option);
    }
    byId("sample").value = data.defaultText;
    byId("spacing-model").value = data.defaultSpacingModel;
    byId("preserve-tabular").checked = data.defaultPreserveTabularSpacing;
    const fields = [
      "family",
      "kerning",
      "optical",
      "letter",
      "word",
      "wrap",
      "zoom",
      "sample",
      "preserve-tabular",
      "pair",
      "spacing-model",
    ];
    const explanations = {
      counterspace_no_feasible_candidate: [
        "Excluded",
        "No candidate inside the bounded CounterSpace search satisfies ink clearance; metric placement is retained.",
      ],
      counterspace_unsupported_scalar: [
        "Excluded",
        "The pinned CounterSpace adapter supports ASCII letters and digits; this pair keeps metric placement.",
      ],
      captured_bitmap_outside_reference_canvas: [
        "Excluded",
        "The delivered glyph exceeds CounterSpace’s reference canvas; this pair keeps metric placement.",
      ],
      clearance_limited: [
        "Clearance limited",
        "Ink clearance prevents the ideal whitespace target; the reported residual includes this constraint.",
      ],
      unsupported_geometry_policy: ["Excluded", "This measurement method requires delivered Mono bitmap geometry."],
      corrected: ["Corrected", "The optical correction changes the whole-pixel placement."],
      rounded_unchanged: [
        "Rounded unchanged",
        "An optical correction was calculated, but whole-pixel rounding keeps the metric placement.",
      ],
      unchanged: ["Unchanged", "The optical calculation already matches the metric placement."],
      optical_disabled: ["Disabled", "Optical strength is zero; the metric placement is used."],
      fixed_pitch: ["Excluded", "Fixed-pitch spacing is always preserved."],
      source_tabular_digits: [
        "Excluded",
        "Preserve tabular spacing is enabled, so this digit pair keeps its metric placement.",
      ],
      empty_geometry: ["Excluded", "An empty glyph has no usable optical geometry for this model."],
      no_shared_ink_rows: [
        "Excluded",
        "The glyphs have no shared occupied rows in the reference-height window; the metric placement is used.",
      ],
      no_shared_bands: ["Excluded", "The glyphs have no shared measurement bands; the metric placement is used."],
      unsupported_calibration_class: [
        "Excluded",
        "This pair is outside the supported calibration classes; the metric placement is used.",
      ],
      calibration_unavailable: [
        "Excluded",
        "The required font reference target is unavailable; the metric placement is used.",
      ],
    };
    const inspectPair = (font, text, k, o, letter, word, preserve, modelName) => {
      const model = font.models[modelName];
      const characters = Array.from(text),
        pairs = new Map();
      for (let i = 0; i + 1 < characters.length; i++) {
        if (characters[i] === "\n" || characters[i + 1] === "\n") continue;
        const cps = [characters[i].codePointAt(0), characters[i + 1].codePointAt(0)];
        pairs.set(cps.join(","), cps);
      }
      const selected = byId("pair").value;
      byId("pair").replaceChildren();
      for (const [key, cps] of pairs) {
        const option = doc.createElement("option");
        option.value = key;
        option.textContent = cps.map((cp) => (cp === 32 ? "␠" : String.fromCodePoint(cp))).join("");
        byId("pair").append(option);
      }
      doc.querySelector(".pair-details").hidden = pairs.size === 0;
      if (!pairs.size) return;
      byId("pair").value = pairs.has(selected)
        ? selected
        : comparedModels
          ? pairs.keys().next().value
          : pairs.has("116,121")
            ? "116,121"
            : pairs.has("114,101")
              ? "114,101"
              : pairs.has("49,50")
                ? "49,50"
                : pairs.keys().next().value;
      const cps = pairs.get(byId("pair").value),
        n = font.codepoints.length;
      const index = font.codepoints.indexOf(cps[0]) * n + font.codepoints.indexOf(cps[1]);
      const codes = (preserve ? model.preservedPairDiagnostics : model.pairDiagnostics)[k * 5 + o];
      const diagnostic = data.diagnosticLabels[codes[index]],
        explanation = explanations[diagnostic];
      if (!explanation) throw new Error("Missing pair explanation; regenerate this page.");
      const pairText = String.fromCodePoint(...cps);
      const metric = layout(font, pairText, k, 0, letter, word, null, preserve, modelName).lines[0].placements[1].x_px;
      const optical = layout(font, pairText, k, o, letter, word, null, preserve, modelName).lines[0].placements[1].x_px;
      byId("pair-outcome").textContent = explanation[0];
      byId("pair-explanation").textContent = explanation[1];
      byId("pair-step").textContent = `Origin step: metric ${metric} px → optical ${optical} px`;
      byId("pair-outcome").dataset.diagnostic = diagnostic;
      const metadata = { ...(preserve ? model.preservedPairTargetMetadata : model.pairTargetMetadata)[index] };
      if (modelName === "hu_source_relative") {
        const overlay = (preserve ? model.preservedPairTargetMetadataByKerning : model.pairTargetMetadataByKerning)[k][
          index
        ];
        for (const field of sourceTargetFields) metadata[field] = overlay[field];
        if (overlay.hu_hersch === null) metadata.hu_hersch = null;
        else {
          metadata.hu_hersch = { ...metadata.hu_hersch };
          for (const field of sourceDiagnosticFields) metadata.hu_hersch[field] = overlay.hu_hersch[field];
        }
      }
      const clearancePolicy = metadata.clearance_policy || model.calibration?.clearance_policy || "strict";
      const basisLabels = {
        lowercase: "nn · lowercase",
        uppercase: "HH · uppercase",
        mixed: "mean of nn and HH · mixed case",
        digits: "00 · experimental ASCII digits",
      };
      const calibration = byId("pair-calibration");
      calibration.dataset.provenance = metadata.target_provenance || "";
      calibration.dataset.basis = metadata.calibration_basis || "";
      calibration.dataset.reason = metadata.calibration_reason || "";
      calibration.textContent =
        diagnostic === "optical_disabled"
          ? "Optical target inactive at zero strength."
          : metadata.target_provenance === "font_calibrated"
            ? `Font-calibrated target: ${basisLabels[metadata.calibration_basis] || metadata.calibration_basis}.`
            : modelName === "hu_source_relative" && metadata.source_target_px !== null
              ? "Hu source-relative target: this pair’s own source-designed gap at the selected source-kerning strength."
              : modelName === "hu_hersch" && metadata.reference_pair
                ? `Hu/Hersch delivered-reference target: ${metadata.reference_pair} · ${metadata.calibration_basis || "reference density"}.`
                : densityModels.includes(modelName) && metadata.target_provenance && !metadata.calibration_reason
                  ? `Fixed-alphabet target: ${modelName !== "hu_alphabet_source_target" ? "source origin mean plus candidate wall mean" : "mean source filtered gap"} · ${metadata.calibration_basis || "fixed calibration domain"}.`
                  : modelName === "hu_source_calibrated" && metadata.reference_pair
                    ? `Hu/Hersch source-designed shared target: ${metadata.reference_pair} · ${metadata.calibration_basis || "reference density"}.`
                    : modelName.startsWith("counterspace") && metadata.reference_pair
                      ? `CounterSpace weighted score calibrated to ${metadata.reference_pair}.`
                      : metadata.target_provenance === "source_relative"
                        ? "Source-relative target: this pair’s own designed spacing."
                        : metadata.target_provenance === "configured_target"
                          ? "Configured fixed target; no font density calibration."
                          : metadata.calibration_reason
                            ? `Calibration unavailable: ${metadata.calibration_reason}${metadata.calibration_detail ? ` · ${metadata.calibration_detail}` : ""}`
                            : "No optical target for this pair under the current safeguards.";
      const sourceDetails = byId("pair-source-target");
      sourceDetails.hidden =
        modelName !== "hu_source_relative" || metadata.source_target_px == null || diagnostic === "optical_disabled";
      sourceDetails.textContent = sourceDetails.hidden
        ? ""
        : `Source target ${metadata.source_target_px} px · source step ${metadata.source_step_px} px · source Hu offset ${metadata.source_hu_offset_px} px · delivered Hu offset ${metadata.delivered_hu_offset_px} px.`;
      for (const [key, value] of Object.entries({
        target: metadata.source_target_px,
        sourceStep: metadata.source_step_px,
        sourceOffset: metadata.source_hu_offset_px,
        deliveredOffset: metadata.delivered_hu_offset_px,
      })) {
        if (sourceDetails.hidden) delete sourceDetails.dataset[key];
        else sourceDetails.dataset[key] = String(value);
      }
      const target = model.pairTargetsPx[k][index],
        offset = model.pairGeometryOffsetsPx[index];
      const measurable =
        !modelName.startsWith("counterspace") &&
        ["corrected", "rounded_unchanged", "unchanged", "clearance_limited"].includes(diagnostic) &&
        target !== null &&
        offset !== null;
      const measurement = byId("pair-separation");
      measurement.hidden = !measurable;
      if (measurable) {
        const realized = optical + offset,
          residual = realized - target;
        const fmt = (value) => Number(value.toFixed(4));
        measurement.textContent = `${densityModels.includes(modelName) ? "Modeled filtered mean gap" : [...huModels, "filtered_walls"].includes(modelName) ? "Filtered mean gap" : "Optical separation"}: target ${fmt(target)} px · realized ${fmt(realized)} px · residual ${residual >= 0 ? "+" : ""}${fmt(residual)} px${metadata.candidate_geometry === "fitted_outline" ? " · fitted-outline measurement; original bitmap ink is displayed" : ""}`;
        measurement.dataset.geometry = metadata.candidate_geometry || "";
        measurement.dataset.target = String(target);
        measurement.dataset.realized = String(realized);
        measurement.dataset.residual = String(residual);
      } else {
        measurement.textContent = "";
        for (const key of ["target", "realized", "residual", "geometry"]) delete measurement.dataset[key];
      }
      const score = byId("pair-score");
      score.hidden = !modelName.startsWith("counterspace");
      score.textContent = "";
      for (const key of ["target", "realized", "error", "reference", "tracked"]) delete score.dataset[key];
      if (!score.hidden) {
        const targetScore = (preserve ? model.preservedPairTargetScores : model.pairTargetScores)[k * 5 + o][index];
        const realizedScore = (preserve ? model.preservedPairRealizedScores : model.pairRealizedScores)[k * 5 + o][
          index
        ];
        const scoreError = (preserve ? model.preservedPairScoreErrors : model.pairScoreErrors)[k * 5 + o][index];
        const tracked =
          (cps.every((cp) => cp !== 32) && pixelRound(letter) !== 0) || (cps[0] === 32 && pixelRound(word) !== 0);
        score.dataset.tracked = String(tracked);
        score.dataset.reference = metadata.reference_pair || "";
        const fmt = (value) => Number(value.toPrecision(7));
        if (targetScore === null)
          score.textContent = "No CounterSpace score for this pair under the current safeguards.";
        else {
          score.dataset.target = String(targetScore);
          score.textContent = `CounterSpace weighted score: target ${fmt(targetScore)}`;
          if (tracked)
            score.textContent += " · realized score unavailable after deliberate spacing (no browser remeasurement)";
          else if (realizedScore !== null && scoreError !== null) {
            score.dataset.realized = String(realizedScore);
            score.dataset.error = String(scoreError);
            score.textContent += ` · realized ${fmt(realizedScore)} · error ${scoreError >= 0 ? "+" : ""}${fmt(scoreError)}`;
          }
          if (metadata.reference_pair) score.textContent += ` · reference ${metadata.reference_pair}`;
          score.textContent += ". Scores are weighted model values, not pixel distances.";
        }
      }
      const search = byId("pair-search");
      search.hidden = !modelName.startsWith("counterspace");
      search.textContent = "";
      for (const key of ["outcome", "policy", "geometry", "crossed", "feasibleCandidates"]) delete search.dataset[key];
      if (!search.hidden) {
        const outcomes = {
          no_feasible_candidate: "no feasible candidate in the search domain; metric placement retained",
          target_bracketed: "target lies within feasible candidate scores",
          target_below_feasible_scores: "target is below every feasible candidate score (unreachable)",
          target_above_feasible_scores: "target is above every feasible candidate score (unreachable)",
          first_crossing: "first candidate exceeding the target selected",
          peak_without_crossing:
            "target was never crossed; highest-scoring candidate selected (unreachable in searched domain)",
        };
        search.dataset.outcome = metadata.search_outcome || "";
        search.dataset.policy = metadata.search_policy || "";
        search.dataset.geometry = metadata.calibration_geometry || "";
        search.dataset.crossed =
          metadata.target_crossed === null || metadata.target_crossed === undefined
            ? ""
            : String(metadata.target_crossed);
        search.dataset.feasibleCandidates =
          metadata.feasible_candidate_count == null ? "" : String(metadata.feasible_candidate_count);
        search.textContent = `Full-strength search${o === 0 ? " (inactive at zero strength)" : ""}: ${outcomes[metadata.search_outcome] || metadata.search_outcome || "not evaluated for this pair"} · calibration ${metadata.calibration_geometry || "unrecorded"} · policy ${metadata.search_policy || "unrecorded"}`;
        if (metadata.candidate_domain_min_step_px != null && metadata.candidate_domain_stop_step_px != null)
          search.textContent += ` · origin domain [${metadata.candidate_domain_min_step_px}, ${metadata.candidate_domain_stop_step_px}) px`;
        if (metadata.candidate_count != null)
          search.textContent += ` · ${metadata.candidate_count} candidates evaluated`;
        if (metadata.feasible_candidate_count != null)
          search.textContent += ` · ${metadata.feasible_candidate_count} feasible`;
        if (metadata.first_crossing_step_px != null)
          search.textContent += ` · first crossing ${metadata.first_crossing_step_px} px`;
        if (metadata.closest_feasible_step_px != null)
          search.textContent += ` · closest feasible ${metadata.closest_feasible_step_px} px`;
      }
      const area = byId("pair-area"),
        clearance = byId("pair-clearance");
      area.hidden = !measurable || ![...huModels, "filtered_walls"].includes(modelName);
      clearance.hidden = area.hidden && !modelName.startsWith("counterspace");
      area.textContent = "";
      clearance.textContent = "";
      for (const key of ["target", "realized", "residual"]) delete area.dataset[key];
      for (const key of ["limited", "minimum", "adjustment", "roundedUnconstrained"]) delete clearance.dataset[key];
      if (modelName.startsWith("counterspace")) {
        const adjustment = (preserve ? model.preservedPairClearanceAdjustmentsPx : model.pairClearanceAdjustmentsPx)[
          k * 5 + o
        ][index];
        const rounded = (
          preserve ? model.preservedPairRoundedUnconstrainedStepsPx : model.pairRoundedUnconstrainedStepsPx
        )[k * 5 + o][index];
        if (rounded === null || metadata.unconstrained_step_px === null) clearance.hidden = true;
        else {
          clearance.dataset.limited = String(adjustment > 0);
          clearance.dataset.minimum = String(metadata.clearance_min_step_px);
          clearance.dataset.adjustment = String(adjustment);
          clearance.dataset.roundedUnconstrained = String(rounded);
          clearance.textContent = `Unconstrained score choice ${metadata.unconstrained_step_px} px · rounded blend ${rounded} px · ink-clearance minimum ${metadata.clearance_min_step_px} px${adjustment > 0 ? ` · blend guard adds ${adjustment} px` : " · blend guard adds no displacement"}. Closest-feasible selection already respects clearance. Deliberate spacing is applied afterward.`;
        }
      }
      if (!area.hidden) {
        const fmt = (value) => Number(value.toFixed(4));
        const height = metadata.window_height_px,
          window = metadata.measurement_window_px;
        const realizedArea = (optical + offset) * height;
        area.textContent = `${metadata.candidate_geometry === "fitted_outline" ? "Modeled fitted-outline whitespace area" : "Filtered whitespace area"}: target ${fmt(metadata.target_area_px2)} px² · realized ${fmt(realizedArea)} px² · residual ${fmt(realizedArea - metadata.target_area_px2)} px² · height ${fmt(height)} px · window ${window.map(fmt).join("…")} px`;
        area.dataset.target = String(metadata.target_area_px2);
        area.dataset.realized = String(realizedArea);
        area.dataset.residual = String(realizedArea - metadata.target_area_px2);
        const prefix = preserve && huModels.includes(modelName) ? "preservedPair" : "pair";
        const adjustment = model[`${prefix}ClearanceAdjustmentsPx`][k * 5 + o][index];
        const rounded = model[`${prefix}RoundedUnconstrainedStepsPx`][k * 5 + o][index];
        clearance.dataset.limited = String(adjustment > 0);
        clearance.dataset.minimum = String(metadata.clearance_min_step_px);
        clearance.dataset.adjustment = String(adjustment);
        clearance.dataset.roundedUnconstrained = String(rounded);
        clearance.textContent = `Ideal step ${fmt(metadata.unconstrained_step_px)} px · rounded blend ${fmt(rounded)} px · ${clearancePolicy === "no_overlap" ? "no-overlap wall-order minimum" : "strict clearance minimum"} ${fmt(metadata.clearance_min_step_px)} px${adjustment > 0 ? ` · clearance adds ${fmt(adjustment)} px` : " · clearance does not constrain this placement"}. Deliberate spacing is applied afterward.`;
      }
      const huDetails = byId("pair-hu-details");
      huDetails.hidden = !huModels.includes(modelName) || !metadata.hu_hersch || diagnostic === "optical_disabled";
      byId("pair-hu-policy").textContent = huDetails.hidden ? "" : JSON.stringify(metadata.hu_hersch);
      const positions = layout(font, pairText, k, o, letter, word, null, preserve, modelName);
      const minimum = metadata.clearance_min_step_px;
      for (const [id, delta] of [
        ["tighter", -1],
        ["selected", 0],
        ["looser", 1],
      ]) {
        const comparison = {
          ...positions,
          lines: positions.lines.map((line) => ({
            ...line,
            placements: line.placements.map((placement) => ({ ...placement })),
          })),
        };
        const line = comparison.lines[0];
        line.placements[1].x_px += delta;
        line.width_px += delta;
        const step = line.placements[1].x_px;
        paint(byId(`pair-${id}`), font, comparison, 1);
        const glyphs = new Map(font.glyphs.map((glyph) => [glyph.codepoint, glyph]));
        const contacts = contactPixels(glyphs.get(cps[0]).bitmap, glyphs.get(cps[1]).bitmap, step);
        paint(byId(`pair-${id}-contacts`), font, comparison, 8, contacts);
        const contactCount = byId(`pair-${id}-contact-count`);
        const disposition = contactDisposition(contacts, clearancePolicy);
        const policyLabel =
          clearancePolicy === "no_overlap"
            ? "edge/corner touching allowed; overlap forbidden"
            : "strict: contact and overlap forbidden";
        const dispositionLabels = {
          forbidden_overlap: "forbidden occupied-cell overlap",
          forbidden_contact: "contact forbidden under strict clearance",
          allowed_contact: "allowed edge/corner contact",
          separated: "no contact or overlap",
        };
        contactCount.textContent = `${contacts.overlaps} overlaps · ${contacts.faces} edge contacts · ${contacts.corners} corner contacts · ${dispositionLabels[disposition]} (${policyLabel})`;
        for (const key of ["overlaps", "faces", "corners"]) contactCount.dataset[key] = String(contacts[key]);
        contactCount.dataset.policy = clearancePolicy;
        contactCount.dataset.disposition = disposition;
        const meetsClearance = minimum == null ? null : step >= minimum;
        const label = byId(`pair-${id}-label`);
        const boundLabel = clearancePolicy === "no_overlap" ? "no-overlap wall-order bound" : "strict clearance";
        label.textContent = `${delta === 0 ? "Emitted" : delta < 0 ? "−1 px" : "+1 px"}: ${step} px · ${dispositionLabels[disposition]}${meetsClearance === null ? " · clearance bound unavailable" : meetsClearance ? ` · meets ${boundLabel}` : ` · below ${boundLabel}`}`;
        label.dataset.step = String(step);
        label.dataset.feasible = meetsClearance === null ? "" : String(meetsClearance);
        label.dataset.policy = clearancePolicy;
        label.dataset.disposition = disposition;
      }
    };
    const update = () => {
      const font = data.cases[Number(byId("family").value)];
      const sampleText = byId("sample").value;
      byId("preset").value =
        presets.find((preset) => preset.text === sampleText)?.id ||
        (sampleText === font.defaultText ? "default" : "custom");
      const k = Number(byId("kerning").value),
        o = Number(byId("optical").value),
        zoom = Number(byId("zoom").value);
      const preserve = byId("preserve-tabular").checked,
        modelName = byId("spacing-model").value;
      byId("model-target").textContent =
        modelName === "hu_fitted_full_density_conserved_touch"
          ? "Complete-outline fitted-wall construction; cavities found after the 45° filter, then measured in the retained body window. Captured bitmap ink supplies no-overlap protection"
          : modelName === "hu_fitted_density_conserved_touch"
            ? "Fixed-alphabet density calibration and pair measurement use fitted-outline walls; captured bitmap ink is displayed and supplies no-overlap clearance"
            : modelName === "hu_density_conserved_touch"
              ? "Fixed-alphabet density conservation with occupied-cell overlap forbidden; edge and corner contacts allowed"
              : modelName === "hu_density_conserved"
                ? "Fixed-alphabet source mean origin spacing plus actual candidate bitmap wall mean; conservation holds continuously on that domain before rounding and clearance"
                : modelName === "hu_alphabet_source_target"
                  ? "Shared filtered-gap target averaged over complete fixed source ASCII alphabets; actual bitmap walls determine placement"
                  : modelName === "hu_source_relative"
                    ? "Hu/Hersch source-outline to delivered-bitmap compensation; preserve each pair’s designed filtered gap"
                    : modelName === "hu_hersch"
                      ? "Hu/Hersch concavity filtering and bounded vertical cavities; delivered bitmap reference density"
                      : modelName === "hu_source_calibrated"
                        ? "Hu/Hersch source-designed shared density; source nn/HH spacing sets the target, delivered bitmap walls determine placement"
                        : modelName.startsWith("counterspace")
                          ? modelName === "counterspace_source_first" ||
                            data.schema_version === "contextual-spacing-page-v6"
                            ? "CounterSpace source-raster calibration; first-crossing integer placement"
                            : modelName === "counterspace_delivered_first"
                              ? "CounterSpace delivered-raster calibration; first-crossing integer placement"
                              : "CounterSpace delivered-raster calibration; closest feasible integer placement"
                          : modelName === "filtered_walls"
                            ? "Hu-inspired filtered whitespace area; source nn / HH / experimental 00 targets, with ink clearance"
                            : modelName === "font_calibrated"
                              ? "FontForge weighted separation; source nn / HH / experimental 00 targets"
                              : modelName === "balanced"
                                ? `Fixed target: ${data.targetSeparationEm} em · ${Number((font.sizePx * data.targetSeparationEm).toFixed(4))} px`
                                : "Comparison: preserve each source pair’s optical separation";
      byId("kerning-help").textContent = comparedModels
        ? comparedModels.some((name) => densityModels.includes(name))
          ? "Affects metric blend endpoints; fixed density calibration uses full source kerning."
          : comparedModels.includes("hu_source_calibrated")
            ? "Affects metric blend endpoints; shared targets use full reference kerning."
            : "Full source-relative follows this control; full shared-target uses its calibrated target."
        : ["source_relative", "hu_source_relative"].includes(modelName)
          ? "Affects the source-relative optical target."
          : "Affects metric and blended placement; full optical uses the selected target.";
      const referenceLabels = { lowercase: "nn", uppercase: "HH", mixed: "Mixed case", digits: "00 (experimental)" };
      const calibration = font.models[modelName].calibration;
      const publishedHuParameters = huModels.includes(modelName) && calibration?.fit?.status === "published_parameters";
      if (publishedHuParameters) {
        byId("model-target").textContent +=
          ` · published depth coefficients: ${calibration.fit.relative_depth} / ${calibration.fit.visual_depth_factor} (US5768490A); no parameter fitting`;
      } else if (
        huModels.includes(modelName) &&
        !densityModels.includes(modelName) &&
        calibration?.fit?.status !== "fitted"
      ) {
        byId("model-target").textContent +=
          ` · depth calibration ${calibration?.fit?.status || calibration?.status || "unrecorded"}; provisional, inspect the retained calibration diagnostics.`;
      }
      if (modelName.startsWith("counterspace") && calibration?.fit_status === "upstream_optimizer_did_not_converge") {
        byId("model-target").textContent += ". Calibration fit did not converge; these parameters are provisional.";
      }
      byId("calibration-summary").textContent = densityModels.includes(modelName)
        ? `Complete fixed ASCII alphabets supply calibration domains: a–z, A–Z, experimental 0–9, and both ordered mixed-case products. Full source kerning defines source origin steps; current text and the runtime kerning control do not choose density. ${modelName !== "hu_alphabet_source_target" ? "Only the unrounded continuous mean origin step on each calibration domain is conserved; word widths and rounded or clearance-constrained means may differ." : "This control uses mean source filtered whitespace rather than nn/HH reference gaps; it does not promise conservation after rasterization."} Filtered model gaps are not measured perception. Measurement geometry: ${calibration?.candidate_geometry === "fitted_outline" ? "fitted outlines; displayed ink remains the original captured bitmap cells" : "delivered bitmap walls"}. ${calibration?.clearance_policy === "no_overlap" ? "The no-overlap clearance policy allows edge and corner contacts, while preserving monotonic same-row wall order." : "Strict clearance forbids both contact and occupied-cell overlap."}`
        : modelName === "hu_source_relative"
          ? `Hu source-relative compensation · depth parameters: ${publishedHuParameters ? "published in US5768490A; no optimizer or parameter fit" : calibration?.fit?.status || "unrecorded"}. The same filters measure source outlines and delivered bitmap cells in one retained window. Each pair keeps its source-designed gap; the source-kerning control changes that target.`
          : modelName === "hu_hersch"
            ? `Hu/Hersch delivered-bitmap reference spacing · depth parameters: ${publishedHuParameters ? "published in US5768490A; no optimizer or parameter fit" : calibration?.fit?.status || calibration?.status || "unrecorded"}. Reference whitespace is measured at full maintained metric placement; independent of the source-kerning control.`
            : modelName === "hu_source_calibrated"
              ? "Source nn/HH outlines and full source metrics set shared density. Delivered bitmap walls and clearance determine placement. Delivered reference bounds define the common window; this is a bounded project adaptation."
              : modelName.startsWith("counterspace")
                ? `CounterSpace fitting: ${calibration?.fit_status || calibration?.status || "unrecorded"} · upstream ${calibration?.upstream?.revision || "unrecorded"} · ${calibration?.upstream?.license || "license unrecorded"}. Parameters fitted from designed reference placements using the selected calibration geometry; independent of the source-kerning control.`
                : calibration
                  ? `${modelName === "filtered_walls" ? "Filtered-wall mean gaps and areas" : "FontForge weighted separations"} from source-designed reference spacing; independent of the source-kerning control. Latin letter classes and ASCII digits only.`
                  : "This comparison uses no shared font-calibrated target.";
      if (modelName === "hu_fitted_full_density_conserved_touch") {
        byId("calibration-summary").textContent +=
          " Complete outlines supply construction context; cavity supports are found after the 45° stage. The global depth cap retains class body height, and the final integral uses the retained body window. Recalibration can move a pair whose own walls did not change.";
      }
      byId("calibration-targets").textContent =
        densityModels.includes(modelName) && calibration
          ? Object.entries(calibration.classes || {})
              .map(([basis, entry]) => {
                if (entry.status !== "available")
                  return `${basis}: unavailable (${entry.reason || entry.status}${entry.detail ? ` · ${entry.detail}` : ""})`;
                const fmt = (value) => (value == null ? "unrecorded" : Number(value.toFixed(5)));
                return `${basis}: ${entry.pair_count} fixed ordered pairs · mean source origin step ${fmt(entry.mean_source_step_px)} px · source wall mean ${fmt(entry.mean_source_offset_px)} px · candidate wall mean ${fmt(entry.mean_candidate_offset_px)} px · target modeled gap ${fmt(entry.target_px)} px · continuous candidate mean step ${fmt(entry.continuous_mean_step_px)} px · continuous mean residual ${fmt(entry.continuous_mean_origin_residual_px)} px`;
              })
              .join(" · ")
          : huModels.includes(modelName) && calibration
            ? `${publishedHuParameters ? "Published depth coefficients" : "Depth coefficients"}: aperture-relative ${calibration.fit?.relative_depth ?? "unrecorded"} · character-height ${calibration.fit?.visual_depth_factor ?? "unrecorded"}. References: ${JSON.stringify(calibration.references || calibration.classes || {})}`
            : modelName.startsWith("counterspace") && calibration
              ? `Reference scores: ${
                  Object.entries(calibration.reference_scores || {})
                    .map(([pair, score]) => `${pair}: ${Number(score.toPrecision(7))}`)
                    .join(" · ") || "unavailable"
                } · fit objectives: ${(calibration.optimizer_results || []).map((result) => `${result.success ? "converged" : "not converged"}: ${Number(result.objective.toPrecision(7))}`).join(" · ") || "unavailable"}. Weighted scores are not pixel distances.`
              : calibration?.classes
                ? Object.entries(calibration.classes)
                    .map(
                      ([basis, entry]) =>
                        `${referenceLabels[basis] || basis}: ${entry.status === "available" ? `${Number(entry.target_px.toFixed(4))} px${entry.target_area_px2 == null ? "" : ` · ${Number(entry.target_area_px2.toFixed(4))} px²`}` : `unavailable (${entry.reason || entry.status}${entry.detail ? ` · ${entry.detail}` : ""})`}`,
                    )
                    .join(" · ")
                : "";
      const modelProvenance = byId("model-provenance");
      modelProvenance.hidden = !modelName.startsWith("counterspace") && !huModels.includes(modelName);
      modelProvenance.textContent =
        densityModels.includes(modelName) && calibration
          ? `Fixed domains: lowercase a–z × a–z; uppercase A–Z × A–Z; mixed (a–z × A–Z) ∪ (A–Z × a–z); experimental digits 0–9 × 0–9, including repetitions. Current text never changes these domains. Calibration policies: ${JSON.stringify(Object.fromEntries(Object.entries(calibration).filter(([key]) => key !== "classes")))}`
          : huModels.includes(modelName) && calibration
            ? `Measurement and calibration policies: ${JSON.stringify(calibration)}`
            : modelName.startsWith("counterspace") && calibration
              ? `Analysis scale: ${calibration.analysis_pixels_per_delivered_pixel || "unrecorded"} cells per delivered pixel · fit pairs ${(calibration.key_pairs || []).join(", ")} · parameters ${JSON.stringify(calibration.options || {})} · calibration: ${calibration.calibration_geometry || "unrecorded"} (${calibration.calibration_geometry_description || "description unrecorded"}) · placement policy: ${calibration.search_policy || "unrecorded"} · delivered: ${calibration.delivered_geometry || "unrecorded"}`
              : "";
      const kerningPercent = `${data.strengths[k] * 100}%`,
        opticalPercent = `${data.strengths[o] * 100}%`;
      byId("kerning-value").textContent = kerningPercent;
      byId("optical-value").textContent = opticalPercent;
      byId("kerning").setAttribute("aria-valuetext", kerningPercent);
      byId("optical").setAttribute("aria-valuetext", opticalPercent);
      byId("optical-badge").textContent = `Optical ${opticalPercent}`;
      if (comparedModels)
        doc.querySelector('[data-placement="metric"] .badge').textContent = `Optical ${opticalPercent}`;
      doc.querySelectorAll(".enlarged-label").forEach((label) => {
        label.textContent = `Enlarged · ${zoom}×`;
      });
      byId("case-summary").textContent = `${font.sizePx} px · ${
        Object.entries(font.axes)
          .map(([tag, value]) => `${tag} ${value}`)
          .join(" · ") || "Default axes"
      }`;
      byId("provenance").textContent =
        `${font.label} · ${font.sizePx} px · ${JSON.stringify(font.axes)} · ${JSON.stringify(font.pipeline)} · Renderer ${font.rendererImplementation || "unrecorded"} · Source SHA-256 ${font.sourceSha256}`;
      byId("repertoire").textContent =
        `Captured characters (plus line breaks): ${font.codepoints.map((cp) => (cp === 32 ? "␠" : String.fromCodePoint(cp))).join("")}`;
      byId("letter").disabled = font.monospace;
      byId("word").disabled = font.monospace;
      byId("preserve-tabular").disabled = font.monospace;
      byId("tabular-help").textContent = font.monospace
        ? "Fixed-pitch spacing is always preserved."
        : font.tabularDigits
          ? "Keep equal-width digits aligned instead of applying optical pair corrections."
          : "These captured digits are proportional; the tabular safeguard does not apply.";
      if (font.monospace) {
        byId("letter").value = "0";
        byId("word").value = "0";
      }
      try {
        for (const id of ["letter", "word", "wrap"])
          if (!byId(id).value || !byId(id).checkValidity())
            throw new Error("Enter a valid spacing and wrap width before comparing.");
        const text = byId("sample").value,
          letter = Number(byId("letter").value),
          word = Number(byId("word").value),
          width = Number(byId("wrap").value);
        const metric = layout(
          font,
          text,
          k,
          comparedModels ? o : 0,
          letter,
          word,
          width,
          preserve,
          comparedModels?.[0] || modelName,
        );
        const optical = layout(font, text, k, o, letter, word, width, preserve, comparedModels?.[1] || modelName);
        for (const [name, positions] of [
          ["metric", metric],
          ["optical", optical],
        ]) {
          paint(byId(`${name}-native`), font, positions, 1);
          paint(byId(`${name}-enlarged`), font, positions, zoom);
          byId(`${name}-measure`).textContent =
            `${positions.lines.length} ${positions.lines.length === 1 ? "line" : "lines"} · terminal widths ${positions.lines.map((line) => line.width_px).join(", ")} px`;
        }
        const grayscale = font.grayscale,
          sourceMono = sourceLinearMono(font);
        byId("source-references").hidden = !font.browserReference && !sourceMono;
        renderBrowser(font, text, width, zoom);
        byId("source-mono-comparison").hidden = !sourceMono;
        if (sourceMono) {
          const positions = layoutGrayscale(sourceMono, text, width);
          paint(byId("source-mono-native"), sourceMono, positions, 1);
          paint(byId("source-mono-enlarged"), sourceMono, positions, zoom);
          byId("source-mono-measure").textContent =
            `${positions.lines.length} ${positions.lines.length === 1 ? "line" : "lines"} · terminal widths ${positions.lines.map((line) => line.width_px).join(", ")} px`;
        }
        byId("grayscale-comparison").hidden = !grayscale;
        byId("custom-grayscale-details").hidden = !grayscale;
        if (grayscale) {
          const positions = layoutGrayscale(grayscale, text, width);
          paint(byId("grayscale-native"), grayscale, positions, 1);
          paint(byId("grayscale-enlarged"), grayscale, positions, zoom);
          byId("grayscale-measure").textContent =
            `${positions.lines.length} ${positions.lines.length === 1 ? "line" : "lines"} · terminal widths ${positions.lines.map((line) => line.width_px).join(", ")} px`;
        }
        byId("error").hidden = true;
        byId("status").textContent = comparedModels
          ? "Complete · Hu models compared side by side"
          : "Complete · captured Mono placement comparison";
        byId("sample").removeAttribute("aria-invalid");
        doc.querySelector(".comparisons").hidden = false;
        inspectPair(font, text, k, o, letter, word, preserve, modelName);
        renderNeighborReview(font, k, o, preserve, zoom);
        return { metric, optical };
      } catch (error) {
        if (data.neighborReview?.mode === "text") {
          ++neighborRevision;
          if (byId("neighbor-review")) byId("neighbor-review").hidden = true;
          byId("neighbor-review-rows")?.replaceChildren();
        }
        doc.querySelector(".comparisons").hidden = true;
        byId("source-references").hidden = true;
        ++browserRevision;
        byId("browser-comparison").hidden = true;
        byId("custom-grayscale-details").hidden = true;
        byId("source-mono-comparison").hidden = true;
        byId("grayscale-comparison").hidden = true;
        doc.querySelector(".pair-details").hidden = true;
        byId("error").textContent = error.message;
        byId("error").hidden = false;
        byId("status").textContent = "Comparison unavailable for the current input";
        byId("sample").setAttribute("aria-invalid", "true");
        return null;
      }
    };
    fields.forEach((id) => byId(id).addEventListener("input", update));
    if (data.neighborReview?.mode === "text" && byId("neighbor-review-contacts"))
      byId("neighbor-review-contacts").checked = false;
    if (data.neighborReview)
      byId("neighbor-review-contacts")?.addEventListener("input", () => {
        renderNeighborReview(
          data.cases[Number(byId("family").value)],
          Number(byId("kerning").value),
          Number(byId("optical").value),
          byId("preserve-tabular").checked,
          Number(byId("zoom").value),
        );
      });
    byId("preset").addEventListener("input", () => {
      const selected = byId("preset").value;
      const text =
        selected === "default"
          ? data.cases[Number(byId("family").value)].defaultText
          : presets.find((preset) => preset.id === selected)?.text;
      if (text !== undefined) {
        byId("sample").value = text;
        update();
      }
    });
    byId("reset").addEventListener("click", () => {
      for (const [id, value] of Object.entries({ kerning: 4, optical: 4, letter: 0, word: 0, wrap: 280, zoom: 4 }))
        byId(id).value = String(value);
      byId("preserve-tabular").checked = data.defaultPreserveTabularSpacing;
      byId("spacing-model").value = data.defaultSpacingModel;
      update();
    });
    byId("reset-text").addEventListener("click", () => {
      byId("sample").value = data.cases[Number(byId("family").value)].defaultText;
      update();
    });
    if (constructionComparison) {
      for (const scale of ["native", "enlarged"])
        synchronizeScroll([...doc.querySelectorAll(`.construction-comparison > .comparison .${scale}`)]);
    } else {
      const scrollers = [...doc.querySelectorAll(".enlarged")];
      scrollers.forEach((source) =>
        source.addEventListener("scroll", () => {
          scrollers.forEach((target) => {
            if (source !== target && target.scrollLeft !== source.scrollLeft) target.scrollLeft = source.scrollLeft;
          });
        }),
      );
    }
    update();
    return { update };
  }

  globalThis.ContextualSpacing = {
    pixelRound,
    layout,
    neighborLayout,
    neighborTextLayout,
    layoutGrayscale,
    sourceLinearMono,
    contactPixels,
    contactDisposition,
    paint,
    mount,
  };
  if (typeof document !== "undefined" && document.getElementById("spacing-data")) {
    try {
      mount(JSON.parse(document.getElementById("spacing-data").textContent));
    } catch (error) {
      const status = document.getElementById("status");
      if (status) status.textContent = `Comparison could not load: ${error.message}`;
    }
  }
})();
