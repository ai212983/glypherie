// Isolated Class-L browser worker (module worker, offline bytes only).
//
// Mirrors the main font-worker protocol shape ({seq, kind, ...} in,
// {seq, ok, value|error, token, dropped} out) without touching it:
// per-key generation tokens tag stale results, errors are data
// ({ok:false}), the worker never fetches — the page hands it the exact
// wasm bytes it hashed, and initSync({module}) instantiates those bytes.
import { initSync, YinYangEngine } from "../pkg/yinyang_oriented_engine.js";

let engine = null;
let inited = false;
const generations = new Map();

self.onmessage = async (event) => {
  const msg = event.data;
  const seq = msg.seq;
  const done = (response, transfer) => {
    if (transfer) self.postMessage(response, { transfer });
    else self.postMessage(response);
  };
  try {
    switch (msg.kind) {
      case "init": {
        if (!inited) {
          initSync({ module: msg.wasm });
          inited = true;
        }
        engine = new YinYangEngine(msg.params ?? null);
        done({ seq, ok: true, value: engine.version() });
        break;
      }
      case "load": {
        const cover = new Float64Array(msg.cover);
        engine.load_glyph(msg.dataset, msg.sha, msg.cp, msg.w, msg.h, msg.left, msg.top, cover);
        generations.set(msg.key, msg.token);
        done({ seq, ok: true });
        break;
      }
      case "score": {
        const deltas = new Int32Array(msg.deltas);
        const cstar = msg.cstar === null || msg.cstar === undefined ? NaN : msg.cstar;
        const out = engine.score_pair_local(
          msg.dataset,
          msg.l,
          msg.r,
          msg.metric,
          deltas,
          msg.tau,
          msg.norm ?? null,
          msg.strength,
          cstar,
        );
        done({
          seq,
          ok: true,
          value: out,
          token: msg.token,
          dropped: generations.get(msg.key) !== msg.token,
        });
        break;
      }
      case "map": {
        const map = engine.contribution_map_local(
          msg.dataset,
          msg.l,
          msg.r,
          msg.step,
          msg.tau,
          msg.norm ?? null,
          msg.strength,
        );
        const buf = map.buffer.slice(0);
        done(
          {
            seq,
            ok: true,
            value: { map: buf, length: map.length },
            token: msg.token,
            dropped: generations.get(msg.key) !== msg.token,
          },
          [buf],
        );
        break;
      }
      case "cancel": {
        engine.cancel();
        done({ seq, ok: true });
        break;
      }
      case "clear_cancel": {
        engine.clear_cancel();
        done({ seq, ok: true });
        break;
      }
      case "clear_all": {
        engine.clear_all();
        done({ seq, ok: true });
        break;
      }
      case "ping": {
        done({ seq, ok: true, value: { alive: !!engine } });
        break;
      }
      default:
        done({ seq, ok: false, error: `unknown kind ${msg.kind}` });
    }
  } catch (err) {
    // Failure behavior: errors are data, the worker stays alive.
    done({ seq, ok: false, error: String((err && err.message) || err) });
  }
};
