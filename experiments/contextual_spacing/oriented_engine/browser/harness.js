// Page-side harness: owns the module worker, routes {seq} responses,
// hashes the exact wasm bytes before handing them over (proves which
// bytes the worker instantiated), decodes bit-string covers, drops
// stale generations. The driver (node) orchestrates via call().
let worker = null;
let seq = 0;
const pending = new Map();

function logLine(s) {
  const el = document.getElementById("log");
  el.textContent += s + "\n";
}

function route(event) {
  const msg = event.data;
  const entry = pending.get(msg.seq);
  if (!entry) return; // stale or post-termination response: dropped
  pending.delete(msg.seq);
  entry.resolve(msg);
}

function spawn() {
  worker = new Worker("./engine_worker.js", { type: "module" });
  worker.onmessage = route;
  worker.onerror = (e) => logLine(`worker error: ${e.message}`);
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function decodeCover(bits, w, h) {
  const out = new Float64Array(w * h);
  for (let i = 0; i < w * h && i < bits.length; i++) out[i] = bits[i] === "1" ? 1.0 : 0.0;
  return out;
}

window.harness = {
  async start() {
    if (worker) return true;
    spawn();
    return true;
  },
  call(msg) {
    // All binary payloads are built in-page (bit-strings decoded here,
    // typed arrays allocated here); nothing binary crosses node.
    const id = ++seq;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      try {
        const m = { ...msg, seq: id };
        if (typeof m.coverBits === "string") {
          m.cover = decodeCover(m.coverBits, m.w, m.h);
          delete m.coverBits;
        } else if (m.cover instanceof ArrayBuffer) m.cover = new Float64Array(m.cover);
        else if (m.cover && !(m.cover instanceof Float64Array)) m.cover = Float64Array.from(m.cover);
        if (m.deltas instanceof ArrayBuffer) m.deltas = new Int32Array(m.deltas);
        else if (m.deltas && !(m.deltas instanceof Int32Array)) m.deltas = Int32Array.from(m.deltas);
        worker.postMessage(m);
      } catch (e) {
        pending.delete(id);
        reject(e);
      }
    });
  },
  async terminate() {
    const stale = [...pending.values()];
    worker.terminate();
    worker = null;
    for (const entry of stale) entry.resolve({ seq: -1, ok: false, error: "terminated" });
    pending.clear();
    return stale.length;
  },
  async respawn() {
    spawn();
    return true;
  },
  async fetchBytes(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`fetch ${url}: ${res.status}`);
    return res.arrayBuffer();
  },
  sha256Hex,
  decodeCover,
  pendingCount() {
    return pending.size;
  },
};
document.getElementById("status").textContent = "ready";
