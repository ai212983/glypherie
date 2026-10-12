import { effectiveZoom, formatEffectiveZoom, magnification } from "./display-scaling.js";
const slider = document.querySelector("#zoom");
const output = document.querySelector("#zoom-value");
const profileSwitch = document.querySelector("#output-mode");
const displayScale = document.querySelector("#display-scale");
// Optional pixel-accurate display toggle for the main interactive preview
// only (off by default until saved, persisted in localStorage). When on,
// each font pixel maps to a whole number of screen pixels and the preview
// size adjusts slightly to the magnification actually achieved; the
// requested zoom stays unchanged.
const exactToggle = document.querySelector("#pixel-accurate");
const exactStatus = document.querySelector("#pixel-accurate-status");
const exactStorageKey = "font-preview.pixel-accurate";
function requestedZoom() {
  return [1, 2, 3, 4][Number(slider?.value)] ?? 1;
}
function updateExactStatus() {
  if (!exactToggle || !exactStatus) return;
  if (!exactToggle.checked) {
    exactStatus.value = "";
    exactStatus.hidden = true;
    return;
  }
  const ratio = window.devicePixelRatio || 1;
  const mag = magnification(requestedZoom(), ratio);
  exactStatus.value = `Effective ${formatEffectiveZoom(effectiveZoom(mag, ratio))} · ${mag} screen px per font px`;
  exactStatus.hidden = false;
}
if (displayScale) {
  let watchedRatio = null;
  let resolutionQuery = null;
  function updateDisplayScale() {
    const ratio = window.devicePixelRatio || 1;
    displayScale.value = `${ratio.toFixed(4)}×`;
    displayScale.title = `${ratio} device pixels per CSS pixel, including browser zoom and display scaling.`;
    if (ratio === watchedRatio) return;
    const first = watchedRatio === null;
    resolutionQuery?.removeEventListener("change", updateDisplayScale);
    watchedRatio = ratio;
    resolutionQuery = window.matchMedia(`(resolution: ${ratio}dppx)`);
    resolutionQuery.addEventListener("change", updateDisplayScale);
    updateExactStatus();
    // Notify the interactive preview so a ratio change repaints with the
    // new integer magnification (and updates its own layout math).
    if (!first) window.dispatchEvent(new CustomEvent("display-scale-change", { detail: { ratio } }));
  }
  window.addEventListener("resize", updateDisplayScale);
  updateDisplayScale();
}
if (exactToggle) {
  try {
    exactToggle.checked = localStorage.getItem(exactStorageKey) === "true";
  } catch {}
  exactToggle.addEventListener("change", () => {
    try { localStorage.setItem(exactStorageKey, String(exactToggle.checked)); } catch {}
    updateExactStatus();
  });
  updateExactStatus();
}
const stickyHeader = document.querySelector(".page-header--sticky");
if (stickyHeader) {
  const updateHeaderHeight = () => document.documentElement.style.setProperty("--header-height", `${stickyHeader.getBoundingClientRect().height}px`);
  updateHeaderHeight();
  new ResizeObserver(updateHeaderHeight).observe(stickyHeader);
}
const parameters = new URLSearchParams(window.location.search);
const zoomScope = document.body.dataset.zoomScope ?? "specimen";
const zoomKeys = { specimen: "font-preview.zoom.specimen", glyph: "font-preview.zoom.glyph" };
const zoomDefaults = { specimen: 1, glyph: 4 };
const zoomStops = [1, 2, 3, 4];
function storedZoom(scope) {
  try {
    const value = Number(localStorage.getItem(zoomKeys[scope]));
    if (zoomStops.includes(value)) return value;
  } catch {}
  return zoomDefaults[scope];
}

function preserveControls() {
  const profile = profileSwitch?.querySelector("input:checked")?.value;
  const zoom = zoomStops[Number(slider?.value)] ?? 1;
  for (const link of document.querySelectorAll("a[data-preserve-controls]")) {
    const url = new URL(link.href);
    if (profile) url.searchParams.set("profile", profile);
    const targetScope = link.dataset.targetZoomScope ?? "specimen";
    url.searchParams.set("zoom", String(targetScope === zoomScope ? zoom : storedZoom(targetScope)));
    link.href = url.href;
  }
  if (document.querySelector("a[data-preserve-controls]")) {
    const url = new URL(window.location.href);
    if (profile) url.searchParams.set("profile", profile);
    url.searchParams.set("zoom", String(zoom));
    window.history.replaceState(null, "", url);
  }
}

if (profileSwitch) {
  const cards = [...document.querySelectorAll(".specimen-card")];
  const groups = [...document.querySelectorAll(".size-group")];
  const families = [...document.querySelectorAll(".family")];
  for (const input of profileSwitch.querySelectorAll("input")) {
    if (input.value === parameters.get("profile")) input.checked = true;
  }
  // The index shows only the selected font's interactive family; glyph
  // pages have no font select and keep the size-group rule.
  const fontSelect = document.querySelector("#font-select");
  function updateProfile() {
    const selected = profileSwitch.querySelector("input:checked")?.value;
    if (!selected) return;
    for (const card of cards) card.hidden = card.dataset.profile !== selected;
    for (const stats of document.querySelectorAll("[data-impact-profile]")) stats.hidden = stats.dataset.impactProfile !== selected;
    for (const sheet of document.querySelectorAll(".glyph-sheet")) sheet.hidden = !sheet.querySelector(".glyph-link:not([hidden])");
    for (const block of document.querySelectorAll(".glyph-block")) block.hidden = block.querySelector(".glyph-sheet").hidden;
    for (const group of groups) group.hidden = !group.querySelector(".specimen-card:not([hidden])");
    for (const family of families) {
      family.hidden = fontSelect
        ? family.id !== `family-${fontSelect.value}`
        : !family.querySelector(".size-group:not([hidden])");
    }
    const unchanged = document.querySelector("#no-pixel-changes");
    if (unchanged) unchanged.hidden = cards.some((card) => !card.hidden);
    preserveControls();
  }
  profileSwitch.disabled = false;
  profileSwitch.addEventListener("change", updateProfile);
  fontSelect?.addEventListener("change", updateProfile);
  updateProfile();
}

if (slider && output) {
  const requested = Number(parameters.get("zoom"));
  slider.value = String(zoomStops.indexOf(zoomStops.includes(requested) ? requested : storedZoom(zoomScope)));
  function updateZoom() {
    const zoom = zoomStops[Number(slider.value)] ?? 1;
    document.documentElement.style.setProperty("--zoom", String(zoom));
    output.value = `${zoom}×`;
    slider.setAttribute("aria-valuetext", `${zoom}×`);
    try { localStorage.setItem(zoomKeys[zoomScope], String(zoom)); } catch {}
    preserveControls();
    updateExactStatus();
  }
  slider.disabled = false;
  slider.addEventListener("input", updateZoom);
  slider.addEventListener("change", updateZoom);
  updateZoom();
}
