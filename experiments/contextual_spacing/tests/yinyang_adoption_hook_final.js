// R-B independent native-call hook (scratch harness, page/worker untouched).
// Installed via addInitScript before any page script runs. It:
//  1. Optionally overrides hardwareConcurrency/deviceMemory.
//  2. Intercepts the #yy-worker-src text so every subsequently created
//     worker (primary + aux) runs an instrumented score boundary that posts
//     {kind:'yy-native'} enter/return/throw receipts. The scoring math and
//     call arguments are byte-identical to the page source.
//  3. Wraps window.Worker to log worker start/termination, outbound
//     score/cancel/drop posts, and all inbound receipts (author counters
//     recorded as witness only, yy-native routed separately).
//  4. Wraps the main-thread YinYangEngine (lazy) to log actual
//     score_pair_local entry/return/throw for the Worker-disabled path.
(function () {
  "use strict";
  var HW = (typeof window.__yyRBHW !== "undefined") ? window.__yyRBHW : {};
  function numOrUndef(v) { return (v === undefined || v === null) ? undefined : v; }
  try {
    var cpus = numOrUndef(HW.cpus), mem = numOrUndef(HW.mem);
    if (cpus !== undefined) {
      try {
        Object.defineProperty(Navigator.prototype, "hardwareConcurrency",
          { get: function () { return cpus; }, configurable: true });
      } catch (e) {}
    }
    if (mem !== undefined) {
      try {
        Object.defineProperty(Navigator.prototype, "deviceMemory",
          { get: function () { return mem; }, configurable: true });
      } catch (e) {}
    }
  } catch (e0) {}
  if (typeof window.__yyNoWorker !== "undefined" && window.__yyNoWorker) {
    try { window.Worker = undefined; } catch (e1) {}
  }

  window.__yyR = { workers: [], inbound: [], outbound: [], native: [],
    mainNative: [], terms: [], capByDataset: {} };

  // ---- 2. worker source patch (exact-match anchors, both page variants)
  var CAND_ANCHOR = "function scorePairCounted(dataset, left, right, metric, query) {\n  var res = JSON.parse(engine.score_pair_local(dataset, left, right,\n    metric, int32(query.deltas), TAU, NORM_RADIUS, STRENGTH, NaN));\n  return { metric: metric, steps: res.steps, domain: query.domain,\n    uncertainty: res.uncertainty || null };\n}";
  var CAND_REPLACEMENT = "function scorePairCounted(dataset, left, right, metric, query) {\n  var __cap = null, __qq = null, __qr = null;\n  try { __cap = (covers[dataset] || {}).captureSha || null; } catch (__x0) {}\n  try { if (engineParams) { __qq = engineParams.q; __qr = engineParams.radius; } } catch (__x1) {}\n  var __jobs = [];\n  try { for (var __jid in jobs) { var __jj = jobs[__jid]; if (__jj && __jj.items) { for (var __k = 0; __k < __jj.items.length; __k++) { var __it = __jj.items[__k]; if (__it.left === left && __it.right === right && __it.metric === metric) { __jobs.push(__jid); break; } } } } } catch (__x2) {}\n  try { self.postMessage({ kind: \"yy-native\", phase: \"enter\", dataset: dataset, left: left, right: right, metric: metric, q: __qq, r: __qr, captureSha: __cap, jobs: __jobs }); } catch (__x3) {}\n  var res;\n  try { res = JSON.parse(engine.score_pair_local(dataset, left, right,\n    metric, int32(query.deltas), TAU, NORM_RADIUS, STRENGTH, NaN)); }\n  catch (__err) { try { self.postMessage({ kind: \"yy-native\", phase: \"throw\", dataset: dataset, left: left, right: right, metric: metric, q: __qq, r: __qr, captureSha: __cap, jobs: __jobs }); } catch (__x4) {} throw __err; }\n  try { self.postMessage({ kind: \"yy-native\", phase: \"return\", dataset: dataset, left: left, right: right, metric: metric, q: __qq, r: __qr, captureSha: __cap, jobs: __jobs }); } catch (__x5) {}\n  return { metric: metric, steps: res.steps, domain: query.domain,\n    uncertainty: res.uncertainty || null };\n}";
  var BASE_ANCHOR = "function scoreOne(dataset, captureSha, item, params) {\n  loadPair(dataset, captureSha, item.left, item.right);\n  var query = scoreDomain(dataset, item.left, item.right, item.metric);\n  var res = JSON.parse(engine.score_pair_local(dataset, item.left,\n    item.right, item.metric, int32(query.deltas), TAU, NORM_RADIUS,\n    STRENGTH, NaN));\n  return { metric: item.metric, steps: res.steps, domain: query.domain,\n    uncertainty: res.uncertainty || null };\n}";
  var BASE_REPLACEMENT = "function scoreOne(dataset, captureSha, item, params) {\n  var __jobs = [];\n  try { for (var __jid in jobs) { var __jj = jobs[__jid]; if (__jj && __jj.items) { for (var __k = 0; __k < __jj.items.length; __k++) { var __it = __jj.items[__k]; if (__it === item) { __jobs.push(__jid); break; } } } } } catch (__x2) {}\n  try { self.postMessage({ kind: \"yy-native\", phase: \"enter\", dataset: dataset, left: item.left, right: item.right, metric: item.metric, q: params.q, r: params.radius, captureSha: captureSha, jobs: __jobs }); } catch (__x3) {}\n  loadPair(dataset, captureSha, item.left, item.right);\n  var query = scoreDomain(dataset, item.left, item.right, item.metric);\n  var res;\n  try { res = JSON.parse(engine.score_pair_local(dataset, item.left,\n    item.right, item.metric, int32(query.deltas), TAU, NORM_RADIUS,\n    STRENGTH, NaN)); }\n  catch (__err) { try { self.postMessage({ kind: \"yy-native\", phase: \"throw\", dataset: dataset, left: item.left, right: item.right, metric: item.metric, q: params.q, r: params.radius, captureSha: captureSha, jobs: __jobs }); } catch (__x4) {} throw __err; }\n  try { self.postMessage({ kind: \"yy-native\", phase: \"return\", dataset: dataset, left: item.left, right: item.right, metric: item.metric, q: params.q, r: params.radius, captureSha: captureSha, jobs: __jobs }); } catch (__x5) {}\n  return { metric: item.metric, steps: res.steps, domain: query.domain,\n    uncertainty: res.uncertainty || null };\n}";

  function patchWorkerSource(src) {
    if (src.indexOf("yy-native") >= 0) return src;
    if (src.indexOf(CAND_ANCHOR) >= 0) return src.replace(CAND_ANCHOR, CAND_REPLACEMENT);
    if (src.indexOf(BASE_ANCHOR) >= 0) return src.replace(BASE_ANCHOR, BASE_REPLACEMENT);
    return src;
  }
  // NOTE: HTMLScriptElement.prototype owns a shadowing textContent
  // accessor in Chromium, so patch every prototype that owns one.
  try {
    var protos = [Node.prototype];
    [Element, HTMLScriptElement, Document, DocumentFragment, Attr].forEach(
      function (ctor) {
        try {
          if (ctor && ctor.prototype &&
              Object.getOwnPropertyDescriptor(ctor.prototype, "textContent") &&
              protos.indexOf(ctor.prototype) < 0) {
            protos.push(ctor.prototype);
          }
        } catch (eP) {}
      });
    protos.forEach(function (proto) {
      var textDesc = Object.getOwnPropertyDescriptor(proto, "textContent");
      if (!textDesc || !textDesc.get || textDesc.get.__yyPatched) return;
      var origGet = textDesc.get, origSet = textDesc.set;
      var Patched = function () {
        var v = origGet.call(this);
        try {
          if (this && this.id === "yy-worker-src" && typeof v === "string" &&
              v.indexOf("score_pair_local") >= 0) {
            return patchWorkerSource(v);
          }
        } catch (e2) {}
        return v;
      };
      Patched.__yyPatched = true;
      var def = { configurable: true, enumerable: textDesc.enumerable,
        get: Patched };
      if (origSet) {
        def.set = function (v) { return origSet.call(this, v); };
      }
      Object.defineProperty(proto, "textContent", def);
    });
  } catch (e3) {}

  // ---- 3. Worker census + message log
  function installWorkerWrap() {
    var OrigWorker = window.Worker;
    if (!OrigWorker || OrigWorker.__yyW) return;
    function TWorker(url, opts) {
      var idx = window.__yyR.workers.length;
      var w = new OrigWorker(url, opts);
      window.__yyR.workers.push({ idx: idx, t0: Date.now(), alive: true, ref: w });
      var arm = setInterval(function () {
        try {
          var cur = w.onmessage;
          if (typeof cur === "function" && !cur.__yyWrapped) {
            var wrapped = function (e) {
              var data = e.data;
              // Probe receipts never reach the wiring: record them aside
              // and drop them here (the wiring ignores unknown jobIds,
              // but it must never observe our traffic at all).
              try {
                if (data && data.kind === "yy-native") {
                  window.__yyR.native.push({ t: Date.now(), worker: idx,
                    phase: data.phase, dataset: data.dataset,
                    left: data.left, right: data.right, metric: data.metric,
                    q: data.q, r: data.r, captureSha: data.captureSha,
                    jobs: data.jobs });
                  return undefined;
                }
              } catch (ignoreN) {}
              try {
                var rec = { t: Date.now(), worker: idx,
                  kind: data && data.kind,
                  jobId: data && data.jobId, key: data && data.key,
                  done: data && data.done, total: data && data.total,
                  engineCalls: data && data.engineCalls,
                  engineDone: data && data.engineDone,
                  engineThrows: data && data.engineThrows,
                  nKeys: data && data.results ?
                    Object.keys(data.results).length : undefined,
                  doneKeys: data && data.results ?
                    Object.keys(data.results) : undefined,
                  cpKeys: data && data.checkpoints ?
                    Object.keys(data.checkpoints) : undefined };
                window.__yyR.inbound.push(rec);
                if (data && data.kind === "progress" && data.checkpoints &&
                    Object.keys(data.checkpoints).length > 0 &&
                    !window.__yyR.sample) {
                  try {
                    window.__yyR.sample = JSON.parse(JSON.stringify({
                      kind: data.kind, jobId: data.jobId, key: data.key,
                      captureSha: data.captureSha, version: data.version,
                      checkpoints: data.checkpoints }));
                  } catch (ignore) {}
                }
              } catch (ignore2) {}
              return cur.call(w, { data: data });
            };
            wrapped.__yyWrapped = true;
            w.onmessage = wrapped;
            clearInterval(arm);
          }
        } catch (ignore4) {}
      }, 25);
      setTimeout(function () { clearInterval(arm); }, 120000);
      var origPost = w.postMessage.bind(w);
      w.postMessage = function (msg) {
        try {
          if (msg && (msg.kind === "score" || msg.kind === "cancel" ||
              msg.kind === "drop")) {
            window.__yyR.outbound.push({ t: Date.now(), worker: idx,
              kind: msg.kind, jobId: msg.jobId, key: msg.key || null,
              nItems: msg.items ? msg.items.length : 0,
              names: msg.items ? msg.items.map(function (i) { return i.key; }) : undefined,
              pairs: msg.items ? msg.items.map(function (i) {
                return String.fromCharCode(i.left) + String.fromCharCode(i.right);
              }) : undefined,
              dropKeys: msg.keys || undefined });
          }
        } catch (ignore5) {}
        return origPost.apply(w, arguments);
      };
      var origTerm = w.terminate.bind(w);
      w.terminate = function () {
        try {
          window.__yyR.terms.push({ worker: idx, t: Date.now() });
          window.__yyR.workers[idx].alive = false;
        } catch (ignore6) {}
        return origTerm();
      };
      return w;
    }
    TWorker.prototype = OrigWorker.prototype;
    TWorker.__yyW = true;
    window.Worker = TWorker;
  }
  installWorkerWrap();

  // ---- 4. main-thread fallback engine wrap (lazy poll)
  var fbArm = setInterval(function () {
    try {
      var rt = window.YYWasmRT;
      if (!rt || !rt.YinYangEngine || rt.YinYangEngine.__yyW) return;
      var Orig = rt.YinYangEngine;
      var proto = Orig.prototype;
      if (proto && !proto.__yyW) {
        proto.__yyW = true;
        var oLoad = proto.load_glyph;
        if (oLoad) {
          proto.load_glyph = function (ds, cap, cp, w, h, l, t, cover) {
            try { window.__yyR.capByDataset[String(ds)] = String(cap); } catch (x) {}
            return oLoad.call(this, ds, cap, cp, w, h, l, t, cover);
          };
        }
        var oScore = proto.score_pair_local;
        if (oScore) {
          proto.score_pair_local = function (dataset, left, right, metric,
              deltas, tau, norm, strength, cstar) {
            var cap = null, params = null;
            try { cap = window.__yyR.capByDataset[String(dataset)] || null; } catch (x2) {}
            try { params = this.__yyParams || null; } catch (x3) {}
            window.__yyR.mainNative.push({ ev: "enter", t: Date.now(),
              dataset: String(dataset), left: left, right: right,
              metric: metric, params: params, captureSha: cap });
            var out;
            try {
              out = oScore.call(this, dataset, left, right, metric, deltas,
                tau, norm, strength, cstar);
            } catch (err) {
              window.__yyR.mainNative.push({ ev: "throw", t: Date.now(),
                dataset: String(dataset), left: left, right: right,
                metric: metric, params: params, captureSha: cap });
              throw err;
            }
            window.__yyR.mainNative.push({ ev: "return", t: Date.now(),
              dataset: String(dataset), left: left, right: right,
              metric: metric, params: params, captureSha: cap });
            return out;
          };
        }
      }
      var W = function (arg) {
        var e = new Orig(arg);
        try { e.__yyParams = String(arg); } catch (x4) {}
        return e;
      };
      W.prototype = proto;
      W.__yyW = true;
      rt.YinYangEngine = W;
    } catch (x5) {}
  }, 25);
  setTimeout(function () { clearInterval(fbArm); }, 240000);
})();
