__YY_WASM_GLUE__

/* Class-L oriented-engine WASM worker driver (template; the builder
 * inlines the transformed classic glue on the first line above this
 * comment, so the worker instantiates from inlined bytes with no fetch).
 *
 * All score math runs in the Rust engine (YinYangEngine over typed
 * arrays) through the Class-L local-energy path (`score_pair_local`,
 * `contribution_map_local`, whole-glyph `slate` letter context) with
 * the frozen normalizer window; this driver owns transfer, chunking
 * and cancellation only.
 * Field layers arrive as one cancellable batch per logical view: covers
 * once, unique slate codepoints plus unique (pair, step) maps, processed
 * at most one map per chunk so a cancel posted between chunks drops the
 * rest. A synchronous WASM call cannot be preempted mid-flight, so a
 * superseded batch may finish its in-flight map and then stops; a
 * stopped receipt reports executed counts and the batch never paints.
 * Generation guards on the main thread give the same guarantee for
 * completed-but-stale jobs.
 *
 * Cache identity is never codepoint-only: covers carry the capture SHA
 * and geometry, and reload on any change; the engine additionally keys
 * fields by capture/params/geometry. LRU holds 32 glyph entries per the
 * engine contract; long texts reload evicted glyphs on demand, so the
 * driver loads both glyphs of a pair before every score or map.
 */

(function () {
  "use strict";

  var TAU = 0.5;
  var STRENGTH = "notebook";
  /* Frozen normalizer window (px). Never user-controlled, never coupled
   * to the field reach: passed explicitly on every local-energy call and
   * cross-checked against the engine version report. */
  var NORM_RADIUS = 12;

  var engine = null;
  var engineParams = null; /* {q, radius} the live engine was built with */
  var versionInfo = null;
  /* Observational only: initSync return (WASM instance exports). Never
   * enters scoring; only memory.buffer.byteLength is read for reports. */
  var wasmExports = null;
  var covers = {}; /* dataset -> {captureSha, glyphs: {cp: cover record}} */
  var coverDatasets = [];
  var jobs = {};

  function paramsKey(params) {
    return "q=" + params.q + "|r=" + params.radius;
  }

  function assertVersion(info) {
    var v = typeof info === "string" ? JSON.parse(info) : info;
    if (!v || v.score_model !== "yinyangfit-local-energy-v2" || v.frozen_normalization_radius !== NORM_RADIUS) {
      throw new Error(
        "engine score identity mismatch: expected " + "yinyangfit-local-energy-v2 with frozen normalizer 12",
      );
    }
    return v;
  }

  function ensureEngine(params) {
    if (engine && engineParams && engineParams.q === params.q && engineParams.radius === params.radius) {
      return;
    }
    engine = new self.YYWasmRT.YinYangEngine(JSON.stringify({ q: params.q, radius: params.radius }));
    engineParams = { q: params.q, radius: params.radius };
    versionInfo = engine.version();
    assertVersion(versionInfo);
  }

  function rememberCovers(dataset, captureSha, glyphs) {
    var slot = covers[dataset];
    if (!slot || slot.captureSha !== captureSha) {
      covers[dataset] = { captureSha: captureSha, glyphs: glyphs || {} };
      coverDatasets.push(dataset);
      while (coverDatasets.length > 2) delete covers[coverDatasets.shift()];
      return covers[dataset];
    }
    if (glyphs) {
      Object.keys(glyphs).forEach(function (cp) {
        slot.glyphs[cp] = glyphs[cp];
      });
    }
    return slot;
  }

  function coverOf(dataset, cp) {
    var slot = covers[dataset];
    if (!slot) return null;
    return slot.glyphs[String(cp)] || null;
  }

  /* Load both glyphs of a pair before any score or map. load_glyph is
   * idempotent: unchanged capture/params/geometry is a cheap no-op, and
   * any change recomputes. Throws when the cover is missing or invalid. */
  function loadPair(dataset, captureSha, left, right) {
    var l = coverOf(dataset, left),
      r = coverOf(dataset, right);
    if (!l || !r) {
      throw new Error("missing cover for pair " + left + "/" + right + " in dataset " + dataset);
    }
    [l, r].forEach(function (rec, i) {
      var cp = i === 0 ? left : right;
      var cover = new Float64Array(rec.cover);
      engine.load_glyph(dataset, captureSha, cp, rec.w, rec.h, rec.left, rec.top, cover);
    });
  }

  function int32(list) {
    return new Int32Array(list);
  }

  /* Bounded observational resource report: existing cache_sizes counters
   * plus WASM linear-memory bytes. Never enters score math or identity. */
  function resReport() {
    var stats = null;
    try {
      stats = engine ? JSON.parse(engine.cache_sizes()) : null;
    } catch (ignore) {
      stats = null;
    }
    var linear = null;
    try {
      if (wasmExports && wasmExports.memory) {
        linear = wasmExports.memory.buffer.byteLength;
      } else if (typeof wasm !== "undefined" && wasm && wasm.memory) {
        linear = wasm.memory.buffer.byteLength;
      }
    } catch (ignore) {
      linear = null;
    }
    return { stats: stats, wasmLinearBytes: linear };
  }

  /* Raw engine step records travel to the main thread; entry shaping
   * happens exactly once there (YYCoupling.shapeEntry), shared with the
   * main-thread fallback path. Shaping here as well would feed numbers
   * back into the shaper and invalidate every step. The candidate domain
   * comes from the engine geometry query per pair (ordered-letter bounds;
   * blank or row-disjoint pairs score the metric step only and abstain),
   * never from a fixed offset list. */
  function scoreDomain(dataset, left, right, metric) {
    var domain = JSON.parse(engine.search_domain(dataset, left, right));
    if (domain.lo === undefined || domain.hi === undefined) {
      return { deltas: [0], domain: domain };
    }
    var deltas = [];
    for (var s = domain.lo; s <= domain.hi; s++) deltas.push(s - metric);
    return { deltas: deltas, domain: domain };
  }

  /* Engine boundary only: exactly one score_pair_local entry per call.
   * Covers and the domain query are main-thread-visible preparation owned
   * by the caller, never engine work. */
  function scorePairCounted(dataset, left, right, metric, query) {
    var res = JSON.parse(
      engine.score_pair_local(dataset, left, right, metric, int32(query.deltas), TAU, NORM_RADIUS, STRENGTH, NaN),
    );
    return { metric: metric, steps: res.steps, domain: query.domain, uncertainty: res.uncertainty || null };
  }

  /* Acknowledgement for a stopped score job: carries the completed keys
   * and the actual boundary counts as proof, so the main thread can
   * release ownership without waiting on a timer. Queued-but-never-run
   * pairs are simply absent; the atomic in-flight pair always finishes
   * first and its progress precedes this ack on the same channel. */
  function stopWithAck(job, reason) {
    var keys = Object.keys(job.results);
    dropJob(job.id);
    var rep = resReport();
    self.postMessage({
      kind: "score-stopped",
      jobId: job.id,
      key: job.key,
      captureSha: job.captureSha,
      reason: reason,
      executedKeys: keys,
      executedCalls: job.engineCalls,
      executedReturns: job.engineDone,
      stats: rep.stats,
      wasmLinearBytes: rep.wasmLinearBytes,
    });
  }

  /* Complete-pair checkpoints ride the existing <=2-pair chunk boundary:
   * each progress receipt carries the raw engine records finished in that
   * chunk so the main thread can validate and merge them immediately. Only
   * records with a step array travel early; errors ride the final receipt.
   * Counters sit on the actual score_pair_local boundary: engineCalls
   * counts entries, engineDone successful returns, engineThrows WASM
   * throws; preCallErrors counts cover/domain preparation failures that
   * never entered the engine. Observability only, never score math. */
  function runScoreJob(job) {
    var i = 0;
    job.engineCalls = 0;
    job.engineDone = 0;
    job.engineThrows = 0;
    job.preCallErrors = 0;
    function chunk() {
      if (!jobs[job.id]) return;
      try {
        ensureEngine(job.params);
      } catch (e) {
        dropJob(job.id);
        self.postMessage({ kind: "error", jobId: job.id, message: String((e && e.message) || e) });
        return;
      }
      /* Trim at the chunk boundary: pairs detached while queued never
       * start. All remaining pairs dropped drains the job with an ack. */
      while (i < job.items.length && job.dropped && job.dropped[job.items[i].key]) {
        i++;
      }
      if (i >= job.items.length) {
        stopWithAck(job, "drained");
        return;
      }
      var start = i;
      var end = Math.min(i + 2, job.items.length);
      for (; i < end; i++) {
        if (!jobs[job.id]) return;
        var item = job.items[i];
        if (job.dropped && job.dropped[item.key]) continue;
        var query;
        try {
          loadPair(job.dataset, job.captureSha, item.left, item.right);
          query = scoreDomain(job.dataset, item.left, item.right, item.metric);
        } catch (e) {
          job.results[item.key] = { error: String((e && e.message) || e) };
          job.preCallErrors++;
          continue;
        }
        job.engineCalls++;
        try {
          job.results[item.key] = scorePairCounted(job.dataset, item.left, item.right, item.metric, query);
          job.engineDone++;
        } catch (e) {
          job.results[item.key] = { error: String((e && e.message) || e) };
          job.engineThrows++;
        }
      }
      var checkpoints = {};
      for (var k = start; k < end; k++) {
        var done_item = job.items[k];
        var done_rec = job.results[done_item.key];
        if (done_rec && !done_rec.error && Array.isArray(done_rec.steps)) {
          checkpoints[done_item.key] = done_rec;
        }
      }
      var rep = resReport();
      self.postMessage({
        kind: "progress",
        jobId: job.id,
        done: i,
        total: job.items.length,
        key: job.key,
        captureSha: job.captureSha,
        version: versionInfo,
        checkpoints: checkpoints,
        engineCalls: job.engineCalls,
        engineDone: job.engineDone,
        engineThrows: job.engineThrows,
        preCallErrors: job.preCallErrors,
        stats: rep.stats,
        wasmLinearBytes: rep.wasmLinearBytes,
      });
      if (i < job.items.length) {
        setTimeout(chunk, 0);
        return;
      }
      /* The page's exact-set check excludes posted drops, so dropped
       * pairs -- finished or errored -- never ride the done receipt.
       * Their complete curves already traveled the checkpoint channel
       * (or were never wanted); returning them would fail partition
       * validation for a routine trim. */
      var results = {};
      Object.keys(job.results).forEach(function (k) {
        if (!job.dropped || !job.dropped[k]) results[k] = job.results[k];
      });
      var calls = job.engineCalls,
        done = job.engineDone,
        throws = job.engineThrows,
        pre = job.preCallErrors;
      dropJob(job.id);
      var doneRep = resReport();
      self.postMessage({
        kind: "done",
        jobId: job.id,
        results: results,
        key: job.key,
        captureSha: job.captureSha,
        version: versionInfo,
        engineCalls: calls,
        engineDone: done,
        engineThrows: throws,
        preCallErrors: pre,
        stats: doneRep.stats,
        wasmLinearBytes: doneRep.wasmLinearBytes,
      });
    }
    setTimeout(chunk, 0);
  }

  function dropJob(id) {
    delete jobs[id];
  }

  /* Attach the glyph-local lattice origin to a padded-lattice slate.
   * Lattice origin in the ink plane is (trunc(left - pad),
   * trunc(top - pad)); pad is recovered from the lattice/delivered size
   * difference so no frozen constant is duplicated here. No frame
   * intersection: the lattice is placement-independent (one entry per
   * codepoint), and the painter translates it by each run's laid-out origin
   * before clipping to the display frame. */
  function cropSlate(rec, arr, w, h) {
    var pad = Math.round((w - rec.w + (h - rec.h)) / 4);
    var ox = Math.trunc(rec.left - pad),
      oy = Math.trunc(rec.top - pad);
    var out = new Float64Array(arr.length);
    out.set(arr);
    return { x0: ox, y0: oy, w: w, h: h, f: out };
  }

  self.onmessage = function (e) {
    var msg = e.data;
    if (!msg || !msg.kind) return;
    if (msg.kind === "init") {
      try {
        var bytes = msg.bytes instanceof Uint8Array ? msg.bytes : new Uint8Array(msg.bytes);
        wasmExports = self.YYWasmRT.initSync({ module: bytes });
        ensureEngine(msg.params);
        rememberCovers(msg.dataset, msg.captureSha, msg.glyphs);
        var readyRep = resReport();
        self.postMessage({
          kind: "ready",
          version: versionInfo,
          stats: readyRep.stats,
          wasmLinearBytes: readyRep.wasmLinearBytes,
        });
      } catch (err) {
        self.postMessage({ kind: "error", jobId: null, message: String((err && err.message) || err) });
      }
      return;
    }
    if (msg.kind === "sync") {
      try {
        ensureEngine(msg.params);
        rememberCovers(msg.dataset, msg.captureSha, msg.glyphs);
        var syncRep = resReport();
        self.postMessage({
          kind: "synced",
          dataset: msg.dataset,
          stats: syncRep.stats,
          wasmLinearBytes: syncRep.wasmLinearBytes,
        });
      } catch (err) {
        self.postMessage({ kind: "error", jobId: null, message: String((err && err.message) || err) });
      }
      return;
    }
    /* Read-only preflight probe for pool admission: no engine, cache or
     * job state is touched. */
    if (msg.kind === "pool-stats") {
      var probeRep = resReport();
      self.postMessage({ kind: "pool-stats", stats: probeRep.stats, wasmLinearBytes: probeRep.wasmLinearBytes });
      return;
    }
    /* Stop a score job with an acknowledgement carrying completed keys
     * and boundary counts. Unknown or already-finished jobs ack empty so
     * the main thread never waits on a missing proof; field batches keep
     * their existing silent drop plus fields-stopped receipt. */
    if (msg.kind === "cancel") {
      var cjob = jobs[msg.jobId];
      if (!cjob) {
        self.postMessage({
          kind: "score-stopped",
          jobId: msg.jobId,
          executedKeys: [],
          executedCalls: 0,
          executedReturns: 0,
          reason: "unknown-job",
        });
        return;
      }
      if (!cjob.items) {
        dropJob(msg.jobId);
        return;
      }
      stopWithAck(cjob, "cancelled");
      return;
    }
    /* Trim queued pairs at the next chunk boundary. Started pairs always
     * finish; fully trimmed jobs drain with an ack, never a done. */
    if (msg.kind === "drop") {
      var djob = jobs[msg.jobId];
      if (!djob || !djob.items) {
        self.postMessage({
          kind: "score-stopped",
          jobId: msg.jobId,
          executedKeys: [],
          executedCalls: 0,
          executedReturns: 0,
          reason: "unknown-job",
        });
        return;
      }
      if (!djob.dropped) djob.dropped = {};
      (msg.keys || []).forEach(function (k) {
        djob.dropped[k] = true;
      });
      return;
    }
    if (msg.kind === "score") {
      if (!self.YYWasmRT) {
        self.postMessage({ kind: "error", jobId: msg.jobId, message: "WASM runtime not initialized" });
        return;
      }
      rememberCovers(msg.dataset, msg.captureSha, msg.glyphs);
      jobs[msg.jobId] = {
        id: msg.jobId,
        dataset: msg.dataset,
        captureSha: msg.captureSha,
        items: msg.items,
        params: msg.params,
        key: msg.key || null,
        results: {},
      };
      runScoreJob(jobs[msg.jobId]);
      return;
    }
    /* One cancellable field batch per logical view. Covers travel once;
     * codepoints hold unique slate glyphs, maps hold unique (pair, step)
     * computations. At most one map runs per chunk; a cancel posted
     * between chunks stops the queue and reports executed counts. */
    if (msg.kind === "fields") {
      jobs[msg.jobId] = { id: msg.jobId };
      var queue = [];
      (msg.codepoints || []).forEach(function (cp) {
        queue.push({ t: "slate", cp: cp });
      });
      (msg.maps || []).forEach(function (m) {
        queue.push({ t: "map", key: m.key, left: m.left, right: m.right, step: m.step });
      });
      var grids = {},
        outMaps = {},
        transfers = [];
      var execSlate = 0,
        execMap = 0,
        qi = 0;
      function stopped() {
        self.postMessage({
          kind: "fields-stopped",
          jobId: msg.jobId,
          executedSlates: execSlate,
          executedMaps: execMap,
        });
      }
      function fieldChunk() {
        if (!jobs[msg.jobId]) {
          stopped();
          return;
        }
        try {
          ensureEngine(msg.params);
        } catch (e) {
          dropJob(msg.jobId);
          self.postMessage({ kind: "error", jobId: msg.jobId, message: String((e && e.message) || e) });
          return;
        }
        rememberCovers(msg.dataset, msg.captureSha, msg.glyphs);
        var mapsThisChunk = 0;
        while (qi < queue.length) {
          if (!jobs[msg.jobId]) {
            stopped();
            return;
          }
          var item = queue[qi++];
          try {
            if (item.t === "slate") {
              var rec = coverOf(msg.dataset, item.cp);
              if (!rec) {
                grids[item.cp] = null;
                continue;
              }
              var cover = new Float64Array(rec.cover);
              engine.load_glyph(msg.dataset, msg.captureSha, item.cp, rec.w, rec.h, rec.left, rec.top, cover);
              /* Whole-glyph amplitude projection for display: fixed
               * per-glyph denominator, so weak far responses stay weak.
               * Scoring still uses score_pair_local /
               * contribution_map_local only. */
              var arr = engine.glyph_component(msg.dataset, item.cp, "slate", 0, 0);
              var note = JSON.parse(engine.last_component_note());
              var cropped = cropSlate(rec, arr, note.width, note.height);
              if (!cropped) {
                grids[item.cp] = null;
                continue;
              }
              var buf = new Float64Array(cropped.f.length);
              buf.set(cropped.f);
              transfers.push(buf.buffer);
              grids[item.cp] = { x0: cropped.x0, y0: cropped.y0, w: cropped.w, h: cropped.h, f: buf.buffer };
              execSlate++;
            } else {
              loadPair(msg.dataset, msg.captureSha, item.left, item.right);
              var map = engine.contribution_map_local(
                msg.dataset,
                item.left,
                item.right,
                item.step,
                TAU,
                NORM_RADIUS,
                STRENGTH,
              );
              var geometry = JSON.parse(engine.last_map_geometry());
              var copy = new Float64Array(map.length);
              copy.set(map);
              transfers.push(copy.buffer);
              outMaps[item.key] = {
                x0: geometry.origin[0],
                y0: geometry.origin[1],
                w: geometry.width,
                h: geometry.height,
                c: copy.buffer,
              };
              execMap++;
              mapsThisChunk++;
              if (mapsThisChunk >= 1) break;
            }
          } catch (err) {
            dropJob(msg.jobId);
            self.postMessage({ kind: "error", jobId: msg.jobId, message: String((err && err.message) || err) });
            return;
          }
        }
        if (qi < queue.length) {
          setTimeout(fieldChunk, 0);
          return;
        }
        dropJob(msg.jobId);
        self.postMessage(
          {
            kind: "fields",
            jobId: msg.jobId,
            grids: grids,
            maps: outMaps,
            executedSlates: execSlate,
            executedMaps: execMap,
            version: versionInfo,
          },
          transfers,
        );
      }
      setTimeout(fieldChunk, 0);
      return;
    }
  };
})();
