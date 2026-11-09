// cspell:words fastpath valuetext target
/* DOM wiring for the Class-L staged spacing sample viewer.
 *
 * Sliders carry real numeric min/max/step; each control also takes an
 * exact numeric entry with wider guardrails. The shipped default
 * geometry (R 12, q 2.0) answers from Class-L tables; every other
 * reach/falloff scores exactly on demand in the page WASM worker (the
 * same Rust engine through `score_pair_local`, no fallback math), in
 * chunked jobs so dragging never freezes the page. A same-engine
 * main-thread fallback covers a missing worker. Target moves never
 * rescore: choices re-derive from stored Class-L curves through the
 * shared TIE-v2 rule. Stale jobs cannot paint every async path is
 * generation-guarded. The normalizer window stays frozen at 12 and is
 * never user-controlled.
 */
(function () {
  "use strict";
  var LS = typeof LetterSpacing !== "undefined" ? LetterSpacing : null;
  var YYV = typeof YYVisual !== "undefined" ? YYVisual : null;
  var YYU = typeof YYCoupling !== "undefined" ? YYCoupling : null;
  var boot = JSON.parse(document.getElementById("yy-boot").textContent);
  window.YY_TABLES = window.YY_TABLES || {};

  function $(id) {
    return document.getElementById(id);
  }
  function el(tag, text, cls) {
    var n = document.createElement(tag);
    if (text !== undefined && text !== null) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }

  /* ---- settings model (actual numeric values, never indices) ---- */

  var GRID = {
    target: boot.controls.target,
    reach: boot.controls.reach,
    falloff: boot.controls.falloff,
  };
  var DEF = {
    target: boot.controls.default.target,
    reach: boot.controls.default.reach,
    falloff: boot.controls.default.falloff,
  };
  var NUMERIC = boot.numeric;
  var FAST = boot.fast_geometry;
  var GAINS = boot.gains || { slate: 6, contrib: 4 };
  var TAU = 0.5;
  var STRENGTH = "notebook";
  var SEARCH_POLICY = boot.search_policy || "yinyangfit-search-v2";
  /* Staged score identity. Shipped tables, computed caches, and every
   * worker/fallback result must carry this; anything else (including the
   * retired G2 identity) never answers from tables. */
  var SCORE_MODEL = boot.score_model || "yinyangfit-local-energy-v2";
  /* Frozen normalizer window (px). Passed explicitly on every
   * local-energy call; never user-controlled. */
  var NORM_RADIUS = 12;

  var SPECS = {
    target: {
      slider: "yy-spacing",
      out: "yy-spacing-v",
      num: "yy-spacing-n",
      err: "yy-spacing-e",
      note: "yy-spacing-x",
      label: "Interaction target",
      aria: "Interaction target",
      helper: "Each pair selects the placement whose score is closest to this number.",
    },
    reach: {
      slider: "yy-reach",
      out: "yy-reach-v",
      num: "yy-reach-n",
      err: "yy-reach-e",
      note: "yy-reach-x",
      label: "Edge reach",
      aria: "Edge reach",
      helper: "Half the width of the square region used to collect letter edges. Larger values include farther edges.",
    },
    falloff: {
      slider: "yy-falloff",
      out: "yy-falloff-v",
      num: "yy-falloff-n",
      err: "yy-falloff-e",
      note: "yy-falloff-x",
      label: "Distance falloff",
      aria: "Distance falloff",
      helper: "Higher values give nearby edges more weight relative to distant edges within Edge reach.",
    },
  };

  var state = {
    caseId: "roboto-16",
    profile: "mono",
    zoom: 1,
    target: DEF.target,
    reach: DEF.reach,
    falloff: DEF.falloff,
    textOverride: null,
    textDirty: false,
    showFields: true,
    showLetter: true,
    showContrib: true,
    letterAlpha: YYV ? YYV.DEFAULT_LETTER_ALPHA : 0.65,
    contribAlpha: YYV ? YYV.DEFAULT_CONTRIB_ALPHA : 1,
  };
  var pendingTable = {};
  /* Last validated preview parse ({ok, text, lines, ...}), shared by
   * layout and field painting for the current choice set. */
  var lastParse = null;
  /* Monotonic generations: only the latest selection may paint. */
  var focusSeq = 0;
  var renderSeq = 0;
  var computeTimer = null;
  var textTimer = null;

  function cases() {
    return boot.cases;
  }
  function findCase(id) {
    for (var i = 0; i < boot.cases.length; i++) if (boot.cases[i].id === id) return boot.cases[i];
    return boot.cases[0];
  }
  function datasetOf(c, profile) {
    return c.profiles[profile];
  }
  function tableLabel(c, profile) {
    return c.id + "-" + profile;
  }

  /* ---- preview text: entered text drives ink and fields alike ---- */

  function displayText(c) {
    return state.textOverride === null ? c.text : state.textOverride;
  }

  function parsePreview(c, profile) {
    var text = displayText(c);
    var glyphs = decodedGlyphs(c, profile);
    var check = LS.validatePreviewText(text, function (cp) {
      return Object.prototype.hasOwnProperty.call(glyphs, String(cp));
    });
    if (!check.ok) {
      return { ok: false, text: text, char: check.char, codepoint: check.codepoint };
    }
    var split = LS.wrapPreviewText(text);
    return { ok: true, text: text, lines: split.lines, capped: split.capped, total: split.total };
  }

  function textErrorMessage(c, profile, parse) {
    var cp = parse.codepoint,
      where = c.id + " " + profile;
    if (cp === 9) {
      return (
        "tabs are not supported (U+0009); use line breaks to split " +
        "lines. The " +
        where +
        " capture has no tab glyph."
      );
    }
    if (cp === 13) {
      return "carriage returns are not supported (U+000D); use line breaks.";
    }
    var shown = parse.char && parse.char.trim() ? "\u201c" + parse.char + "\u201d " : "";
    return "character " + shown + "(" + LS.formatCodepoint(cp) + ") is not in the " + where + " repertoire.";
  }

  function hasLetterGaps(lines) {
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      for (var k = 0; k + 1 < line.length; k++) {
        if (line[k] !== " " && line[k + 1] !== " ") return true;
      }
    }
    return false;
  }

  /* Metric step for any in-repertoire pair: shipped table values where
   * present, otherwise the source advance plus captured pair kerning
   * through the shared browser mirror (missing kern means no adjustment). */
  function metricFor(table, name) {
    if (table.pairs[name]) return table.pairs[name].metric;
    return LS.metricStep(table.advances, table.kern || {}, name.charCodeAt(0), name.charCodeAt(1));
  }

  /* Whole-pixel deltas for an ordered-letter domain, ascending. */
  function rangeDeltas(lo, hi, metric) {
    var out = [];
    for (var s = lo; s <= hi; s++) out.push(s - metric);
    return out;
  }

  function missingItems(table, missing) {
    return missing.map(function (name) {
      return {
        key: name,
        left: String(name.charCodeAt(0)),
        right: String(name.charCodeAt(1)),
        metric: metricFor(table, name),
      };
    });
  }

  /* __PAIRCACHE_HELPERS_BEGIN__ */
  /* Pure pair-curve cache helpers (no DOM, no engine): byte accounting,
   * metric-carrying pair identity, pair-aware LRU and complete-curve
   * validation. Extracted verbatim by the node unit test; keep this
   * block dependency-free.
   *
   * Accounted bytes count curve payload only: numbers 8 B, string
   * characters 2 B each, arrays and plain objects recursed over their
   * elements/values. Object keys, Map slots, booleans, nulls and all
   * other JS structural overhead are excluded: the budget is an
   * accounted payload target, not a strict heap cap. */
  var PAIR_CACHE_TARGET_BYTES = 16777216;

  function pairPayloadBytes(value) {
    var total = 0,
      i,
      k;
    if (typeof value === "number") return 8;
    if (typeof value === "string") return value.length * 2;
    if (value === null || value === undefined) return 0;
    if (typeof value !== "object") return 0;
    if (Array.isArray(value)) {
      for (i = 0; i < value.length; i++) total += pairPayloadBytes(value[i]);
      return total;
    }
    var keys = Object.keys(value);
    for (k = 0; k < keys.length; k++) {
      total += pairPayloadBytes(value[keys[k]]);
    }
    return total;
  }

  function pairRecordBytes(rec) {
    return pairPayloadBytes(rec);
  }

  function pairSettingKey(p) {
    return [
      p.dataset,
      p.font,
      p.capture,
      p.source,
      p.wasm,
      p.score,
      p.search,
      "r=" + p.r,
      "q=" + p.q,
      "tau=" + p.tau,
      "n=" + p.norm,
      "st=" + p.strength,
    ].join("|");
  }

  /* Full per-pair data identity: setting slot, requested metric, pair.
   * The metric rides the key itself, so a changed metric can never hit
   * or join another metric's computation or cached curve; the lookup
   * miss is exact, never a silent reuse. */
  function pairIdentityKey(settingKey, name, metric) {
    return settingKey + "\n@" + String(metric) + "\n" + name;
  }

  function pairSettingOf(identityKey) {
    var sep = identityKey.indexOf("\n");
    return sep < 0 ? identityKey : identityKey.slice(0, sep);
  }

  function createPairCache(budgetBytes) {
    return {
      slots: new Map(),
      settingCounts: {},
      pins: {},
      bytes: 0,
      budget: budgetBytes,
      stats: {
        hits: 0,
        misses: 0,
        stored: 0,
        checkpointStored: 0,
        evicted: 0,
        evictedBytes: 0,
        dropped: 0,
        overflow: false,
      },
    };
  }

  /* Verified read: the slot metric must equal the requested metric or
   * the record is foreign and misses. Read hit refreshes recency
   * (delete + re-insert at the newest end). */
  function pairCacheGet(cache, identityKey, metric) {
    var slot = cache.slots.get(identityKey);
    if (slot === undefined) {
      cache.stats.misses++;
      return null;
    }
    if (slot.rec.metric !== metric) {
      cache.stats.misses++;
      return null;
    }
    cache.stats.hits++;
    cache.slots.delete(identityKey);
    cache.slots.set(identityKey, slot);
    return slot.rec;
  }

  function pairCacheForget(cache, identityKey) {
    var slot = cache.slots.get(identityKey);
    if (slot === undefined) return 0;
    cache.slots.delete(identityKey);
    cache.bytes -= slot.bytes;
    var sk = pairSettingOf(identityKey);
    if (cache.settingCounts[sk] !== undefined) {
      cache.settingCounts[sk]--;
      if (cache.settingCounts[sk] <= 0) delete cache.settingCounts[sk];
    }
    return slot.bytes;
  }

  /* Insert or replace one complete pair record under its metric-carrying
   * identity. Replacing adjusts bytes by delta only, so a final receipt
   * repeated after its checkpoint never double-counts. */
  function pairCachePut(cache, identityKey, rec) {
    var bytes = pairRecordBytes(rec);
    var isNew = !cache.slots.has(identityKey);
    pairCacheForget(cache, identityKey);
    cache.slots.set(identityKey, { rec: rec, bytes: bytes });
    cache.bytes += bytes;
    var sk = pairSettingOf(identityKey);
    cache.settingCounts[sk] = (cache.settingCounts[sk] || 0) + 1;
    if (isNew) cache.stats.stored++;
    pairCacheEnforce(cache);
  }

  /* Evict oldest-first while over budget, skipping pinned current-view
   * records. When only pinned records remain above budget the working set
   * is kept whole and soft overflow is reported instead of recomputing,
   * evicting or looping. */
  function pairCacheEnforce(cache) {
    while (cache.bytes > cache.budget) {
      var victim = null;
      cache.slots.forEach(function (slot, key) {
        if (victim === null && !cache.pins[key]) victim = key;
      });
      if (victim === null) break;
      var freed = pairCacheForget(cache, victim);
      cache.stats.evicted++;
      cache.stats.evictedBytes += freed;
    }
    cache.stats.overflow = cache.bytes > cache.budget;
  }

  /* Pins name current-view identity keys; obsolete identities become
   * unpinned and evict first. In-flight (not yet complete) data is never
   * stored, so pins alone never make a pair readable. */
  function pairCacheSetPins(cache, identityKeys) {
    var pins = {};
    identityKeys.forEach(function (k) {
      pins[k] = true;
    });
    cache.pins = pins;
    pairCacheEnforce(cache);
  }

  function pairCacheClearPins(cache) {
    cache.pins = {};
    pairCacheEnforce(cache);
  }

  function pairCacheSnapshot(cache) {
    return {
      bytes: cache.bytes,
      pairs: cache.slots.size,
      settings: Object.keys(cache.settingCounts).length,
      pinned: Object.keys(cache.pins).length,
      hits: cache.stats.hits,
      misses: cache.stats.misses,
      stored: cache.stats.stored,
      checkpointStored: cache.stats.checkpointStored,
      evicted: cache.stats.evicted,
      evictedBytes: cache.stats.evictedBytes,
      dropped: cache.stats.dropped,
      overflow: cache.stats.overflow,
    };
  }

  /* A record is reusable only as a complete pair curve: the requested
   * metric, contiguous exact integer steps covering the ordered-letter
   * domain (lo, lo+1, …, hi — no dupes, gaps, fractionals or
   * out-of-domain steps, including malformed full-length records), or a
   * blank/row-disjoint abstain domain with finite numeric steps. Partial
   * curves, errors, malformed or metric-foreign records never validate.
   * Null entry fields (abstain/overlap) and the source fallback
   * metric-step records are legitimate and accepted. */
  function validateCheckpointSteps(item, rec) {
    if (!rec || typeof rec !== "object") return false;
    if (typeof rec.error === "string") return false;
    if (!item || rec.metric !== item.metric) return false;
    if (!Array.isArray(rec.steps) || !rec.steps.length) return false;
    var d = rec.domain;
    if (!d || typeof d !== "object") return false;
    if (typeof d.lo === "number" && typeof d.hi === "number") {
      if (!isFinite(d.lo) || !isFinite(d.hi)) return false;
      if (Math.floor(d.lo) !== d.lo || Math.floor(d.hi) !== d.hi) return false;
      if (!(d.hi >= d.lo)) return false;
      if (rec.steps.length !== d.hi - d.lo + 1) return false;
      for (var i = 0; i < rec.steps.length; i++) {
        var s = rec.steps[i];
        if (!s || typeof s !== "object") return false;
        if (typeof s.step !== "number" || !isFinite(s.step)) return false;
        if (Math.floor(s.step) !== s.step) return false;
        if (s.step !== d.lo + i) return false;
      }
      return true;
    }
    if (d.blank || d.empty) {
      for (var j = 0; j < rec.steps.length; j++) {
        var t = rec.steps[j];
        if (!t || typeof t !== "object") return false;
        if (typeof t.step !== "number" || !isFinite(t.step)) return false;
      }
      return true;
    }
    return false;
  }

  /* Terminal-store ownership gate, same rule as checkpoints: the current
   * owner stores (even while stopping: a detached lease with no newer
   * owner still caches, frozen T16). Verified late data with no live
   * owner at all also stores. An entry live-owned by a different call
   * means a newer owner took the key: the orphan receipt must not
   * store, release, or paint over it. Reads only the caller's registry
   * map, so unit tests drive it directly. */
  function terminalOwnerAllows(flight, jobKey, flightCall, name, metric) {
    var r = flight.running.get(pairIdentityKey(jobKey, name, metric));
    if (!r) return true;
    if (flightCall && r.owner === flightCall) return true;
    return false;
  }
  /* __PAIRCACHE_HELPERS_END__ */

  /* __FLIGHT_HELPERS_BEGIN__ */
  /* Pure running-work registry (no DOM, no engine): per-key ownership
   * with view subscribers, cancellation acknowledgement and bounded
   * exact retry. Extracted verbatim by the node unit test; keep this
   * block dependency-free. Adapted from singleflight duplicate keyed-call
   * suppression (https://pkg.go.dev/golang.org/x/sync/singleflight):
   * concurrent needs for one key share one execution, but unlike
   * singleflight a detached view may arm a bounded stop, and the same
   * key is never redispatched until the old owner acknowledges release,
   * fails, or its call record is gone (ack / done / error / drop).
   *
   * Ownership states per key: absent (no entry, no cache record),
   * running (one owner call, subscriber views), complete (cached; entry
   * released). A stopping entry refuses joins until its ack arrives. */
  function createFlight() {
    return { running: new Map(), calls: new Map(), seq: 0, stats: { starts: 0, joins: 0, blocked: 0 } };
  }

  /* Reserve one owner call for keys that are actually absent, classifying
   * join / stopping-block / absent again at reservation time. A key that
   * is already live-owned by another call is joined (subscriber added)
   * or counted blocked, never overwritten: reserve-then-dispatch can no
   * longer clobber a newer owner. Cached keys are the caller's filter;
   * the registry only decides ownership. Returns null callId (no record,
   * no sequence bump, no start counted) when nothing is reservable, so
   * every dispatcher posts exactly the reserved set. */
  function flightReserve(flight, keys, subs) {
    var reserved = [],
      joined = [],
      blocked = [];
    var seen = {};
    var list = Array.isArray(subs) ? subs : [];
    (keys || []).forEach(function (key) {
      if (seen[key]) return;
      seen[key] = true;
      var r = flight.running.get(key);
      if (!r) {
        reserved.push(key);
        return;
      }
      if (r.stopping) {
        flight.stats.blocked++;
        blocked.push(key);
        return;
      }
      list.forEach(function (v) {
        r.subs[v] = true;
      });
      flight.stats.joins++;
      joined.push(key);
    });
    if (!reserved.length) {
      return { callId: null, reserved: reserved, joined: joined, blocked: blocked };
    }
    var id = "k" + ++flight.seq;
    flight.calls.set(id, { keys: reserved.slice(), done: false, acked: false, retried: false });
    reserved.forEach(function (key) {
      var entry = { owner: id, subs: {}, stopping: false };
      list.forEach(function (view) {
        entry.subs[view] = true;
      });
      flight.running.set(key, entry);
    });
    flight.stats.starts++;
    return { callId: id, reserved: reserved, joined: joined, blocked: blocked };
  }

  /* Classify one view's needs: cache hits, joins on live owners, blocks
   * on stopping owners, and absent keys reserved under one new call. */
  function flightNeed(flight, view, keys, isCached) {
    var out = { started: null, joined: [], hit: [], blocked: [] };
    var absent = [];
    for (var n = 0; n < keys.length; n++) {
      var key = keys[n];
      if (isCached(key)) {
        out.hit.push(key);
        continue;
      }
      var r = flight.running.get(key);
      if (r && !r.stopping) {
        r.subs[view] = true;
        flight.stats.joins++;
        out.joined.push(key);
        continue;
      }
      if (r && r.stopping) {
        flight.stats.blocked++;
        out.blocked.push(key);
        continue;
      }
      absent.push(key);
    }
    if (absent.length) {
      var res = flightReserve(flight, absent, [view]);
      if (res.callId) {
        out.started = { callId: res.callId, keys: res.reserved };
      }
      res.joined.forEach(function (key) {
        out.joined.push(key);
      });
      res.blocked.forEach(function (key) {
        out.blocked.push(key);
      });
    }
    return out;
  }

  /* Ownership gate for one checkpoint: the caller validates the record
   * (strict complete-curve check); this only enforces one live owner and
   * the stop boundary. Returns "ok", "halted" or "dropped". */
  function flightCheckpointOwner(flight, callId, key) {
    var call = flight.calls.get(callId);
    var r = flight.running.get(key);
    if (!call || call.done || !r || r.owner !== callId) return "dropped";
    if (r.stopping) return "halted";
    return "ok";
  }

  /* Release one key after its validated record published to the cache. */
  function flightComplete(flight, callId, key) {
    var r = flight.running.get(key);
    if (r && r.owner === callId) flight.running.delete(key);
  }

  /* Detach one view: zero-subscriber entries arm a bounded stop at the
   * next chunk boundary. Data is never invalidated by a detach. */
  function flightDetach(flight, view) {
    var stopped = [];
    flight.running.forEach(function (r, key) {
      if (r.subs[view]) {
        delete r.subs[view];
        if (!r.stopping && Object.keys(r.subs).length === 0) {
          r.stopping = true;
          stopped.push(key);
        }
      }
    });
    return stopped;
  }

  /* Cancellation acknowledgement: release the call's keys (completed
   * ones are already cached; the rest become absent) and drop the call
   * record, so the same key may dispatch exactly one new owner. */
  function flightAck(flight, callId) {
    var call = flight.calls.get(callId);
    if (!call) return [];
    var released = [];
    flight.running.forEach(function (r, key) {
      if (r.owner === callId) {
        released.push(key);
        flight.running.delete(key);
      }
    });
    flight.calls.delete(callId);
    return released;
  }

  /* Release a call's ownership without dispatching (worker loss, force).
   * Returns keys with their surviving subscriber views for re-reserve. */
  function flightReleaseCall(flight, callId) {
    var call = flight.calls.get(callId);
    if (!call) return [];
    var out = [];
    flight.running.forEach(function (r, key) {
      if (r.owner === callId) {
        out.push({ key: key, subs: Object.keys(r.subs) });
        flight.running.delete(key);
      }
    });
    flight.calls.delete(callId);
    return out;
  }

  /* Bounded exact retry: release owned keys and reserve them once more
   * under the surviving subscribers. A call already retried fails
   * closed: the caller must surface an honest error, never a loop. */
  function flightFail(flight, callId) {
    var call = flight.calls.get(callId);
    if (!call) return null;
    var saved = flightReleaseCall(flight, callId);
    if (call.retried) return null;
    var id = "k" + ++flight.seq;
    flight.calls.set(id, {
      keys: saved.map(function (e) {
        return e.key;
      }),
      done: false,
      acked: false,
      retried: true,
    });
    saved.forEach(function (entry) {
      var r = { owner: id, subs: {}, stopping: false };
      Object.keys(entry.subs).forEach(function (v) {
        r.subs[v] = true;
      });
      flight.running.set(entry.key, r);
    });
    flight.stats.starts++;
    return id;
  }

  /* Transport registry for dispatched calls: pending calls with their
   * worker/main-thread legs and one acknowledgement timer each. These
   * run inside the helpers block so unit checks can drive the exact
   * production expiry handler with stub transports; at load time they
   * only declare functions, touching page state solely when called. */
  function flightNewCall(callId, keys) {
    flightCalls[callId] = { kind: "pending", keys: keys.slice(), transports: [], timer: null };
    flightArmAck(callId);
  }

  /* One acknowledgement-expiry handler for the production timer and the
   * test hook alike: after a full silence bound with no merged
   * checkpoint, the executor is presumed lost. Cancel posts go out
   * first (a live executor drains instead of running orphaned), then
   * ownership releases and the current view re-resolves. A call whose
   * recovery belongs to a live unsettled pool logical is skipped here:
   * the pool lifecycle is its single recovery authority. Downstream
   * reserve and terminal-store gates make the release safe even when
   * the old executor is still draining. */
  function flightAckExpired(callId) {
    var call = flightCalls[callId];
    if (!call) return;
    if (poolLogical && !poolLogical.settled && poolLogical.flightCall === callId && poolLogical.seq === renderSeq) {
      return;
    }
    call.transports.forEach(function (t) {
      try {
        if (t.worker && t.jobId) {
          t.worker.postMessage({ kind: "cancel", jobId: t.jobId });
        }
      } catch (ignore) {
        /* transport gone */
      }
    });
    /* A silent call burned its attempt, but only for keys the current
     * view still needs: trimmed or superseded keys must never accrue
     * failure credit toward a later view. Two silent expiries on live
     * needs therefore end honest instead of reposting forever. */
    var current = genNeeds[renderSeq];
    var wanted = {};
    if (current) {
      current.keys.forEach(function (k) {
        wanted[k.key] = true;
      });
    }
    var stale = (call.keys || []).filter(function (key) {
      return wanted[key];
    });
    if (stale.length) noteScoreFailures(stale);
    flightReleaseCallId(callId);
    settleCheck(renderSeq);
  }

  function flightArmAck(callId) {
    var call = flightCalls[callId];
    if (!call) return;
    if (call.timer) {
      try {
        clearTimeout(call.timer);
      } catch (ignore) {
        /* rearmed */
      }
    }
    call.timer = setTimeout(function () {
      flightAckExpired(callId);
    }, FLIGHT_ACK_MS);
  }

  function flightTouchAck(callId) {
    if (callId && flightCalls[callId]) flightArmAck(callId);
  }

  function flightReleaseCallId(callId) {
    flightReleaseCall(flight, callId);
    var call = flightCalls[callId];
    if (call && call.timer) {
      try {
        clearTimeout(call.timer);
      } catch (ignore) {
        /* released */
      }
    }
    delete flightCalls[callId];
  }
  /* __FLIGHT_HELPERS_END__ */

  /* Live pair-curve cache: complete shaped pair records under their exact
   * metric-carrying data identity, bounded by accounted curve-payload
   * bytes with pair-aware LRU. Current-view pins protect the working set;
   * see the helpers blocks for accounting, eviction, validation and the
   * running-work registry. */
  var pairCache = createPairCache(PAIR_CACHE_TARGET_BYTES);
  /* Cumulative main-thread fallback engine counts (observability only):
   * entries, successful returns, WASM throws, pre-call failures; errors
   * sums throws and pre-call failures for the legacy hook shape. */
  var mainThreadCalls = { calls: 0, returns: 0, throws: 0, pre: 0, errors: 0 };
  /* Running-work registry: one owner call per absent key, view
   * subscribers per key, bounded stop on detach. */
  var flight = createFlight();
  /* Live dispatch calls: callId -> {kind, keys, transports, ackTimer}.
   * Transports are {worker, jobId} for worker legs or {fallback: true}. */
  var flightCalls = {};
  /* View generations: gen -> {c, profile, table, keys, painted}. */
  var genNeeds = {};
  /* Per-identity consecutive validation-failure counts; two strikes end
   * in an honest error instead of a resolve loop. Bounded by pruning. */
  var scoreFailCounts = {};

  /* Merge shaped records under one setting identity; each record carries
   * its metric, so the store key always binds setting, metric and pair.
   * Returns the count of newly stored pairs so repeats never
   * double-count. Success clears that identity's failure count. */
  function storeShapedPairs(key, shaped) {
    var stored = 0;
    Object.keys(shaped).forEach(function (name) {
      var rec = shaped[name];
      if (!rec || rec.error || !rec.steps || typeof rec.metric !== "number") {
        return;
      }
      var identityKey = pairIdentityKey(key, name, rec.metric);
      var isNew = !pairCache.slots.has(identityKey);
      pairCachePut(pairCache, identityKey, rec);
      delete scoreFailCounts[identityKey];
      if (isNew) stored++;
    });
    return stored;
  }

  function publishComputed(key, results) {
    storeShapedPairs(key, results);
  }

  /* Verified single-pair read: setting slot plus the requested metric.
   * A metric-foreign record is an exact miss, never a silent reuse. */
  function cachedPairRecord(settingKey, name, metric) {
    return pairCacheGet(pairCache, pairIdentityKey(settingKey, name, metric), metric);
  }

  /* Current-view pins carry the full per-pair identity (setting, metric,
   * pair); refreshed whenever preview text parses valid, released when
   * the draft is invalid. */
  function refreshPairPins(c, profile, table, needed) {
    var key = computedKey(c, profile);
    pairCacheSetPins(
      pairCache,
      needed.map(function (name) {
        return pairIdentityKey(key, name, metricFor(table, name));
      }),
    );
  }

  /* Bounded failure accounting for redispatch decisions: two consecutive
   * validation-failure rounds on one identity end in an honest error
   * instead of recomputing forever. */
  function noteScoreFailures(identityKeys) {
    identityKeys.forEach(function (key) {
      scoreFailCounts[key] = (scoreFailCounts[key] || 0) + 1;
    });
    var names = Object.keys(scoreFailCounts);
    if (names.length > 512) {
      for (var i = 0; i < names.length - 512; i++) {
        delete scoreFailCounts[names[i]];
      }
    }
  }

  function scoreFailExhausted(identityKey) {
    return (scoreFailCounts[identityKey] || 0) >= 2;
  }

  function clearPairPins() {
    pairCacheClearPins(pairCache);
  }

  /* Checkpoint merge: validated complete-pair records join the cache
   * under their exact job identity. Never paints and never touches busy
   * notes; a superseded generation still caches for its own identity so
   * a revisit recomputes only the remainder. Engine identity is enforced
   * by the page-trusted boot WASM SHA already inside the key, never by
   * the receipt's version echo: trusting the echo would let a forged
   * receipt rewrite the learned version and then drop real checkpoints.
   *
   * Ownership-gated: only the current owner call merges. Receipts for a
   * stopping owner (detached view) or a released call are ignored without
   * counters, matching the running-work lease. Foreign pairs and invalid
   * records count as dropped; completed entries release their ownership. */
  function mergeScoreCheckpoints(jobLike, msg, callId) {
    var cps = msg && msg.checkpoints;
    if (!cps) return 0;
    if (!jobLike || msg.key !== jobLike.key || msg.captureSha !== jobLike.captureSha) {
      return 0;
    }
    var byKey = {};
    (jobLike.items || []).forEach(function (item) {
      byKey[item.key] = item;
    });
    var shaped = {};
    Object.keys(cps).forEach(function (name) {
      var item = byKey[name],
        rec = cps[name];
      if (!item) {
        pairCache.stats.dropped++;
        return;
      }
      var identityKey = pairIdentityKey(jobLike.key, name, item.metric);
      var r = callId ? flight.running.get(identityKey) : null;
      if (!r || r.owner !== callId || r.stopping) return;
      if (!validateCheckpointSteps(item, rec)) {
        pairCache.stats.dropped++;
        return;
      }
      shaped[name] = rec;
    });
    var names = Object.keys(shaped);
    if (!names.length) return 0;
    var fresh = storeShapedPairs(jobLike.key, shapeResults(shaped));
    if (fresh > 0) {
      names.forEach(function (name) {
        var item = byKey[name];
        flightComplete(flight, callId, pairIdentityKey(jobLike.key, name, item.metric));
      });
      flightTouchAck(callId);
    }
    pairCache.stats.checkpointStored += fresh;
    return fresh;
  }

  /* Shipped pairs answer only at the default geometry under the current
   * search policy AND the staged score identity; anything else (a
   * stale-policy table, or any G2-identity table) scores exactly on
   * demand and merges into the computed cache. */
  function fastAndCurrent(table) {
    return isFastGeometry() && table.search_policy === SEARCH_POLICY && table.score_model === SCORE_MODEL;
  }

  /* Normalize an engine domain record to the pair search shape the choice
   * rule reads for blank/disjoint fallback reasons. */
  function searchFor(domain) {
    if (!domain) return null;
    if (domain.blank) {
      return { policy: SEARCH_POLICY, lo: null, hi: null, domain_reason: "blank_glyph_no_ink", exhaustive: true };
    }
    if (domain.empty) {
      return {
        policy: SEARCH_POLICY,
        lo: null,
        hi: null,
        domain_reason: domain.reason || "row_bands_disjoint",
        exhaustive: true,
      };
    }
    return { policy: SEARCH_POLICY, lo: domain.lo, hi: domain.hi, domain_reason: null, exhaustive: true };
  }

  /* Verified choice entry: shipped pairs answer when fast and current,
   * otherwise the metric-verified cache record. A missing computed
   * record is a caller bug (paint waits for full coverage); the builder
   * reports it instead of throwing mid-paint. */
  function entryFor(name, table, settingKey, fast) {
    if (fast && table.pairs[name]) {
      var t = table.pairs[name];
      return { metric: t.metric, steps: t.steps, entry: t.geo, search: t.search || null };
    }
    var hit = cachedPairRecord(settingKey, name, metricFor(table, name));
    if (!hit) return null;
    return { metric: hit.metric, steps: hit.steps, entry: hit.entry, search: hit.search || null };
  }

  function buildChoiceSet(c, profile, table, needed) {
    var fast = fastAndCurrent(table);
    var settingKey = computedKey(c, profile);
    var pairs = {};
    for (var i = 0; i < needed.length; i++) {
      var rec = entryFor(needed[i], table, settingKey, fast);
      if (!rec) return null;
      var decided = LS.chosenStep(
        { metric: rec.metric, steps: rec.steps, geo: { d: rec.entry }, search: rec.search },
        "d",
        state.target,
      );
      pairs[needed[i]] = {
        metric: rec.metric,
        steps: rec.steps,
        entry: rec.entry,
        search: rec.search,
        chosen: decided.step,
        minimizing: decided.minimizing,
        fallback: decided.fallback,
        reason: decided.reason,
        targetOutside: decided.targetOutside,
      };
    }
    return { pairs: pairs };
  }

  /* Experiment layout over the shown lines: pair steps from the choice
   * set, space gaps at their metric word advance. */
  function liveOriginsFor(table, choiceSet, lines) {
    var pairSteps = {};
    Object.keys(choiceSet.pairs).forEach(function (name) {
      var p = choiceSet.pairs[name];
      pairSteps[name] = { metric: p.metric, step: p.chosen, fallback: p.fallback };
    });
    var spaceMetrics = {},
      adv = table.advances,
      kern = table.kern || {};
    lines.forEach(function (line) {
      for (var i = 0; i + 1 < line.length; i++) {
        var a = line[i],
          b = line[i + 1];
        if (a === " " || b === " ") {
          spaceMetrics[a + b] = LS.metricStep(adv, kern, a.charCodeAt(0), b.charCodeAt(0));
        }
      }
    });
    return LS.layoutLines(pairSteps, spaceMetrics, lines);
  }

  /* Source baseline over the shown lines: fractional-pen drawn origins
   * from the shipped advances and kerning, the browser mirror of the
   * captured-source word layout. */
  function capturedOriginsFor(table, lines) {
    var adv = table.advances,
      kern = table.kern || {};
    return lines.map(function (line) {
      return LS.capturedOrigins(adv, kern, line);
    });
  }

  /* ---- value formatting: full precision, never snapped ---- */

  function fmtValue(key, value) {
    if (key === "reach") return String(Math.round(value));
    return String(value);
  }

  function gridInfo(key, value) {
    var grid = GRID[key];
    var step = grid[1] - grid[0];
    var idx = Math.round((value - grid[0]) / step);
    var inBand = value >= grid[0] && value <= grid[grid.length - 1];
    var onGrid = inBand && idx >= 0 && idx < grid.length && Math.abs(grid[idx] - value) < 1e-9;
    if (!inBand) idx = Math.max(0, Math.min(grid.length - 1, idx));
    return { index: idx, onGrid: onGrid, inBand: inBand };
  }

  /* Guardrail check mirroring the Python validate_numeric messages. */
  function guardMessage(key, value) {
    if (key === "target") {
      /* No upper clamp by design: any finite value >= 0 is exact. A null
       * upper bound in the boot numeric means unbounded above. */
      if (!(value >= NUMERIC.target[0]) || (NUMERIC.target[1] !== null && !(value <= NUMERIC.target[1]))) {
        return "target must be finite and >= 0";
      }
    } else if (key === "reach") {
      if (!(value >= NUMERIC.reach[0] && value <= NUMERIC.reach[1])) {
        return "reach must be an integer in [1, 32]";
      }
    } else {
      if (!(value >= NUMERIC.falloff[0] && value <= NUMERIC.falloff[1])) {
        return "falloff must be in [0.25, 16]";
      }
    }
    return null;
  }

  function parseEntry(key, text) {
    var shown = key === "target" ? "target" : key;
    if (text.trim() === "") return { ok: false, message: "Enter a number." };
    var value = Number(text);
    if (typeof value !== "number" || isNaN(value)) {
      return { ok: false, message: shown + " must be a number" };
    }
    if (!isFinite(value)) {
      return { ok: false, message: shown + " must be finite" };
    }
    if (key === "reach" && Math.floor(value) !== value) {
      return { ok: false, message: "reach must be an integer in [1, 32]" };
    }
    var guard = guardMessage(key, value);
    if (guard) return { ok: false, message: guard };
    return { ok: true, value: value };
  }

  function isFastGeometry() {
    return state.reach === FAST.reach && state.falloff === FAST.falloff;
  }

  /* Current engine params for worker jobs (reach is the square kernel
   * half-width in px; falloff is the radial exponent). */
  function engineParams() {
    return { q: state.falloff, radius: state.reach };
  }

  /* ---- control UI ---- */

  function refreshControl(key, setField) {
    var spec = SPECS[key],
      value = state[key];
    var info = gridInfo(key, value);
    var grid = GRID[key];
    var slider = $(spec.slider);
    slider.value = String(grid[info.index]);
    if (setField) {
      $(spec.num).value = fmtValue(key, value);
      $(spec.num).setAttribute("aria-invalid", "false");
      $(spec.err).textContent = "";
    }
    var out, aria;
    if (key === "target") {
      out = fmtValue(key, value);
      aria = spec.aria + " " + out;
    } else if (key === "reach") {
      out = fmtValue(key, value) + " px";
      aria = spec.aria + " " + fmtValue(key, value) + " pixels";
    } else {
      out = fmtValue(key, value);
      aria = spec.aria + " " + fmtValue(key, value);
    }
    $(spec.out).textContent = out;
    slider.setAttribute("aria-valuetext", aria);
    var note = spec.helper;
    if (!info.inBand) {
      note = "Using " + fmtValue(key, value) + ", beyond the slider range.";
    } else if (!info.onGrid) {
      note = "Using " + fmtValue(key, value) + "; the slider shows " + fmtValue(key, grid[info.index]) + ".";
    }
    $(spec.note).textContent = note;
  }

  function refreshControls(setFields) {
    refreshControl("target", setFields);
    refreshControl("reach", setFields);
    refreshControl("falloff", setFields);
  }

  function showEntryError(key, message) {
    var spec = SPECS[key];
    $(spec.err).textContent = "Keeping " + fmtValue(key, state[key]) + " — " + message;
    $(spec.num).setAttribute("aria-invalid", "true");
  }

  /* ---- datasets and tables ---- */

  function decodedGlyphs(c, profile) {
    var ds = datasetOf(c, profile);
    if (ds.decoded) return ds.decoded;
    var out = {};
    Object.keys(ds.glyphs).forEach(function (cp) {
      var g = ds.glyphs[cp],
        s = g.cover,
        cover;
      if (profile === "mono") {
        cover = new Array(s.length);
        for (var i = 0; i < s.length; i++) cover[i] = s[i] === "1" ? 1 : 0;
      } else {
        cover = new Array(s.length);
        for (var j = 0; j < s.length; j++) cover[j] = (s.charCodeAt(j) - 48) / 7;
      }
      out[cp] = { w: g.w, h: g.h, left: g.left, top: g.top, cover: cover };
    });
    ds.decoded = out;
    return out;
  }

  /* Plain-array covers for worker transfer (structured clone). */
  function transferCovers(glyphs, codepoints) {
    var out = {};
    codepoints.forEach(function (cp) {
      var g = glyphs[String(cp)];
      if (!g) return;
      out[String(cp)] = { w: g.w, h: g.h, left: g.left, top: g.top, cover: g.cover.slice() };
    });
    return out;
  }

  function ensureTable(c, profile, done) {
    var label = tableLabel(c, profile);
    if (window.YY_TABLES[label]) {
      done(window.YY_TABLES[label]);
      return;
    }
    if (!pendingTable[label]) {
      pendingTable[label] = [];
      var script = document.createElement("script");
      script.src = "data/" + label + ".js";
      script.onload = function () {
        var list = pendingTable[label];
        delete pendingTable[label];
        list.forEach(function (fn) {
          fn(window.YY_TABLES[label]);
        });
      };
      script.onerror = function () {
        delete pendingTable[label];
        $("yy-sample-note").textContent = "Sample data for " + label + " did not load; showing defaults.";
      };
      document.head.appendChild(script);
    }
    pendingTable[label].push(done);
  }

  /* ---- exact on-demand compute: WASM worker, same-engine fallback ---- */

  var worker = null;
  var workerFailed = false;
  var workerJobs = {};
  var workerSeq = 0;
  var workerBytes = null;
  var fallbackEngines = {};
  var fallbackOrder = [];

  function wasmBytes() {
    if (workerBytes) return workerBytes;
    var node = document.getElementById("yy-wasm-b64");
    var text = node ? node.textContent.replace(/\s+/g, "") : "";
    var bin = atob(text);
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    workerBytes = out;
    return workerBytes;
  }

  function workerSource() {
    var node = document.getElementById("yy-worker-src");
    return node ? node.textContent : "";
  }

  function ensureWorker() {
    if (worker || workerFailed || typeof Worker === "undefined") return worker;
    try {
      var src = workerSource();
      if (!src) {
        workerFailed = true;
        return null;
      }
      var w = new Worker(URL.createObjectURL(new Blob([src], { type: "text/javascript" })));
      w.onmessage = function (e) {
        onWorkerMessage(e.data);
      };
      w.onerror = function () {
        workerFailed = true;
        try {
          w.terminate();
        } catch (ignore) {
          /* already gone */
        }
        worker = null;
        abortPoolToMainThread();
        /* Ownership by the dead worker is gone with it: release every
         * worker-owned running key (subscribers stay on their views) and
         * let the current view re-resolve from cache plus fresh work on
         * the same-engine fallback. Late receipts find no owner. */
        flightReleaseWorkerCalls();
        settleCheck(renderSeq);
        /* Pending field batches rerun on the same-engine fallback. */
        Object.keys(fieldWorkerJobs).forEach(function (jobId) {
          var rec = fieldWorkerJobs[jobId];
          delete fieldWorkerJobs[jobId];
          if (!rec.fallbackRetried) {
            rec.fallbackRetried = true;
            runFieldFallback(findFieldBatch(rec.batchId));
          }
        });
      };
      w.onmessageerror = w.onerror;
      worker = w;
      try {
        w.postMessage({ kind: "init", params: engineParams(), bytes: wasmBytes() });
      } catch (ignore) {
        /* init carries a large buffer; failure falls back below. */
        workerFailed = true;
        try {
          w.terminate();
        } catch (t) {
          /* already gone */
        }
        worker = null;
        return null;
      }
    } catch (ignore) {
      workerFailed = true;
      worker = null;
    }
    return worker;
  }

  function datasetKey(c, profile) {
    return tableLabel(c, profile);
  }

  /* Full data identity: dataset/profile, font, capture and source SHAs,
   * the running WASM implementation, score/search models, R/q and the
   * frozen tau/normalizer/strength. Target/text/display/zoom never enter:
   * choices re-derive from stored curves. Fallback and pool share it. */
  function computedKey(c, profile) {
    var ds = datasetOf(c, profile);
    return pairSettingKey({
      dataset: tableLabel(c, profile),
      font: c.font_sha256 || "",
      capture: ds.capture_sha256 || "",
      source: ds.source_sha256 || "",
      wasm: (boot.implementation && boot.implementation.wasm_sha256) || "",
      score: SCORE_MODEL,
      search: SEARCH_POLICY,
      r: state.reach,
      q: state.falloff,
      tau: TAU,
      norm: NORM_RADIUS,
      strength: STRENGTH,
    });
  }

  function captureSha(c, profile) {
    return datasetOf(c, profile).capture_sha256;
  }

  function currentParamsKey() {
    return "q=" + state.falloff + "|r=" + state.reach;
  }

  /* ---- shared running work: dispatch, trim, acknowledgement ---- */

  var FLIGHT_ACK_MS = 60000;

  /* Reserve ownership and arm the stop-acknowledgement bound. The timer
   * resets on every merged checkpoint; 60 s of silence presumes the
   * transport dead, releases ownership, and lets the current view
   * re-resolve. Late receipts find no owner and are ignored. */
  /* Release every worker-transport call (dead worker proof). Subscriber
   * views stay on their generations; settle re-resolves from cache. */
  function flightReleaseWorkerCalls() {
    Object.keys(flightCalls).forEach(function (callId) {
      var call = flightCalls[callId];
      var workerLeg = call.transports.some(function (t) {
        return !!t.worker;
      });
      if (workerLeg || call.kind === "pending") flightReleaseCallId(callId);
    });
  }

  function flightAttachTransport(callId, transport) {
    var call = flightCalls[callId];
    if (!call) return;
    call.transports.push(transport);
  }

  /* Trim live worker transports to the current view: pairs no longer
   * subscribed never start (bounded pair/chunk boundary in the worker);
   * the atomic in-flight pair always finishes first and its progress
   * precedes the drain acknowledgement on the same channel. */
  function trimLiveCalls(gen) {
    var need = genNeeds[gen];
    if (!need) return;
    var wanted = {};
    need.keys.forEach(function (k) {
      wanted[k.key] = true;
    });
    Object.keys(flightCalls).forEach(function (callId) {
      var call = flightCalls[callId];
      if (!call) return;
      call.transports.forEach(function (t) {
        if (!t.worker || !t.jobId) return;
        if (!t.droppedNames) t.droppedNames = {};
        var drop = [];
        (t.keys || []).forEach(function (entry) {
          if (!wanted[entry.key] && !t.droppedNames[entry.name]) {
            t.droppedNames[entry.name] = true;
            drop.push(entry.name);
          }
        });
        if (!drop.length) return;
        try {
          t.worker.postMessage({ kind: "drop", jobId: t.jobId, keys: drop });
        } catch (ignore) {
          /* Transport gone; the ack bound or the error path releases. */
        }
      });
    });
  }

  function flightCallForJob(jobId) {
    var found = null;
    Object.keys(flightCalls).forEach(function (callId) {
      if (found) return;
      flightCalls[callId].transports.forEach(function (t) {
        if (t.jobId === jobId) found = callId;
      });
    });
    return found;
  }

  /* Release one job's ownership after a terminal receipt (done, error,
   * acknowledgement), then let the current view re-resolve. Late
   * receipts for the released call find no record and are ignored. */
  function releaseJobOwnership(job) {
    if (!job) return;
    if (job.flightCall) flightReleaseCallId(job.flightCall);
    job.flightCall = null;
  }

  function setScoreBusy() {
    $("yy-explain-note").textContent = "Updating fields…";
    $("yy-explain-field").setAttribute("aria-busy", "true");
  }

  /* __POOL_HELPERS_BEGIN__ */
  /* Pure pool helpers (no DOM): admission, geometry estimate, deterministic
   * partition, partition validation. Extracted verbatim by the node unit
   * test; keep this block dependency-free. */
  var POOL_MIN_PAIRS = 16;
  var POOL_MIN_CPUS = 4;
  var POOL_LINEAR_TARGET = 536870912;
  var POOL_MAX_HALFWIDTH = 12;
  var POOL_F64_LATTICES = 146;
  var POOL_WORKSPACE_FLOOR = 8388608;

  function poolPad(R) {
    return POOL_MAX_HALFWIDTH + R;
  }

  function poolCells(w, h, R) {
    var p = poolPad(R);
    return (w + 2 * p) * (h + 2 * p);
  }

  function poolPairCost(item, dims, R) {
    var l = dims[item.left],
      r = dims[item.right];
    if (!l || !r) return 0;
    return poolCells(l.w, l.h, R) + poolCells(r.w, r.h, R);
  }

  function poolDimsKey(dims) {
    return Object.keys(dims).sort();
  }

  /* Deterministic greedy balance over cheap geometry cost only: no
   * warm-up scoring, no domain search. Ties break by pair key. */
  function poolPartition(items, dims, R) {
    var scored = items.map(function (item) {
      return { item: item, cost: poolPairCost(item, dims, R) };
    });
    scored.sort(function (x, y) {
      if (y.cost !== x.cost) return y.cost - x.cost;
      return x.item.key < y.item.key ? -1 : x.item.key > y.item.key ? 1 : 0;
    });
    var a = [],
      b = [],
      sa = 0,
      sb = 0;
    scored.forEach(function (entry) {
      if (sa <= sb) {
        a.push(entry.item);
        sa += entry.cost;
      } else {
        b.push(entry.item);
        sb += entry.cost;
      }
    });
    return { a: a, b: b, costA: sa, costB: sb };
  }

  function poolGlyphSet(items) {
    var set = {};
    items.forEach(function (item) {
      set[item.left] = true;
      set[item.right] = true;
    });
    return Object.keys(set);
  }

  /* Admission estimate for both partitions plus the primary
   * retained highwater. Per-glyph retained lattices follow the engine
   * array inventory (fields/scales/orientations/energies/one EL key);
   * cover transfer buffers are counted per subjob; the workspace margin
   * covers FFT/score scratch. Retained allocation and new geometry may
   * coexist, so both are included; runtime telemetry remains the backstop. */
  function poolEstimateBytes(itemsA, itemsB, dims, R, highwater) {
    var perCell = POOL_F64_LATTICES * 8 + 16;
    function owned(items) {
      var total = 0,
        transfer = 0;
      poolGlyphSet(items).forEach(function (cp) {
        var rec = dims[cp];
        if (!rec) return;
        total += poolCells(rec.w, rec.h, R) * perCell + rec.w * rec.h * 8;
        transfer += rec.w * rec.h * 8;
      });
      return { owned: total, transfer: transfer };
    }
    var ea = owned(itemsA),
      eb = owned(itemsB);
    var ownedSum = ea.owned + eb.owned;
    var workspace = Math.max(POOL_WORKSPACE_FLOOR, Math.ceil(ownedSum * 0.04));
    var hw = typeof highwater === "number" && isFinite(highwater) && highwater > 0 ? highwater : 0;
    var primaryPeak = hw + ea.owned;
    var total = primaryPeak + eb.owned + ea.transfer + eb.transfer + workspace;
    return {
      total: total,
      ownedA: ea.owned,
      ownedB: eb.owned,
      transfer: ea.transfer + eb.transfer,
      workspace: workspace,
      highwater: hw,
      primaryPeak: primaryPeak,
    };
  }

  function poolAdmit(count, cpus, memGB, estimateTotal) {
    if (!(count >= POOL_MIN_PAIRS)) return { ok: false, reason: "small-job" };
    if (!(typeof cpus === "number" && cpus >= POOL_MIN_CPUS)) {
      return { ok: false, reason: cpus === undefined || cpus === null ? "cpu-unknown" : "cpu-low" };
    }
    if (memGB === undefined || memGB === null) {
      return { ok: false, reason: "memory-unknown" };
    }
    if (!(typeof estimateTotal === "number" && isFinite(estimateTotal)) || estimateTotal > POOL_LINEAR_TARGET) {
      return { ok: false, reason: "over-budget" };
    }
    return { ok: true, reason: "admitted" };
  }

  /* Exact partition validation: the expected key set must be present with
   * either valid step data or an honest engine error. Missing, extra,
   * duplicate or malformed records invalidate the partition. */
  function poolValidatePartition(expectedKeys, results) {
    var valid = {},
      errors = {};
    if (!results || typeof results !== "object") {
      return { ok: false, reason: "malformed-response", valid: valid };
    }
    var keys = Object.keys(results);
    if (keys.length !== expectedKeys.length) {
      return { ok: false, reason: "incomplete-partition", valid: valid };
    }
    for (var i = 0; i < expectedKeys.length; i++) {
      var key = expectedKeys[i];
      if (!Object.prototype.hasOwnProperty.call(results, key)) {
        return { ok: false, reason: "wrong-key", valid: valid };
      }
      var rec = results[key];
      if (rec && typeof rec.error === "string") {
        errors[key] = rec;
        continue;
      }
      if (rec && Array.isArray(rec.steps)) {
        valid[key] = rec;
        continue;
      }
      return { ok: false, reason: "malformed-record", valid: valid };
    }
    return { ok: true, reason: "complete", valid: valid, errors: errors };
  }
  /* __POOL_HELPERS_END__ */

  /* Pool runtime: one logical score generation over two subjobs. The aux
   * worker is retired after every settle so it retains no engine bytes. */
  var POOL_WATCHDOG_MS = 60000;
  var POOL_AUX_READY_MS = 30000;
  var POOL_PROBE_MS = 8000;
  var poolJobs = {};
  var poolLogical = null;
  var poolProbe = null;
  var poolSessionDisabled = null;
  var poolHighwater = null;

  function poolLedger() {
    return window.__yyPoolJobs || (window.__yyPoolJobs = []);
  }

  function poolState() {
    if (!window.__yyPool) {
      window.__yyPool = { disabled: null, highwater: null, lastDecision: null, auxLive: false };
    }
    return window.__yyPool;
  }

  function poolRecord(entry) {
    var ledger = poolLedger();
    ledger.push(entry);
    while (ledger.length > 16) ledger.shift();
    return entry;
  }

  function poolNotePrimaryLinear(bytes) {
    if (typeof bytes === "number" && isFinite(bytes) && bytes > 0) {
      if (poolHighwater === null || bytes > poolHighwater) {
        poolHighwater = bytes;
        poolState().highwater = bytes;
      }
    }
  }

  function poolDims(glyphs) {
    var dims = {};
    Object.keys(glyphs).forEach(function (cp) {
      var g = glyphs[cp];
      dims[cp] = { w: g.w, h: g.h };
    });
    return dims;
  }

  function poolHardware() {
    var nav = typeof navigator !== "undefined" ? navigator : {};
    return { cpus: nav.hardwareConcurrency, memGB: nav.deviceMemory };
  }

  function retireAuxWorker(logical) {
    if (logical && logical.aux) {
      try {
        logical.aux.terminate();
      } catch (ignore) {
        /* retired */
      }
      logical.aux = null;
    }
    if (poolLogical === logical) poolLogical = null;
    poolState().auxLive = false;
  }

  function cancelActivePoolJobs() {
    if (poolProbe) {
      try {
        clearTimeout(poolProbe.timer);
      } catch (ignore) {
        /* gone */
      }
      poolProbe = null;
    }
    Object.keys(poolJobs).forEach(function (jobId) {
      var logical = poolJobs[jobId];
      delete poolJobs[jobId];
      if (!logical || logical.settled) return;
      logical.settled = true;
      if (logical.timer) {
        try {
          clearTimeout(logical.timer);
        } catch (ignore) {
          /* gone */
        }
        logical.timer = null;
      }
      delete poolJobs[logical.partA.jobId];
      delete poolJobs[logical.partB.jobId];
      /* Score cancel only: the field registry is never touched here. */
      try {
        if (worker) {
          worker.postMessage({ kind: "cancel", jobId: logical.partA.jobId });
        }
      } catch (ignore) {
        /* worker gone */
      }
      try {
        if (logical.aux) {
          logical.aux.postMessage({ kind: "cancel", jobId: logical.partB.jobId });
        }
      } catch (ignore) {
        /* aux gone */
      }
      retireAuxWorker(logical);
      if (logical.ledger) {
        logical.ledger.status = "cancelled";
        logical.ledger.outcome = "superseded";
      }
    });
  }

  function resetPoolWatchdog(logical) {
    if (logical.timer) {
      try {
        clearTimeout(logical.timer);
      } catch (ignore) {
        /* gone */
      }
    }
    logical.timer = setTimeout(function () {
      poolWatchdogExpired(logical);
    }, POOL_WATCHDOG_MS);
  }

  function poolDecide(job, done) {
    var state = poolState();
    function reject(reason, est) {
      state.lastDecision = {
        admitted: false,
        reason: reason,
        pairs: job.items.length,
        estimateBytes: est ? est.total : null,
      };
      done(false, est || null);
    }
    if (poolSessionDisabled) {
      reject("disabled:" + poolSessionDisabled, null);
      return;
    }
    var hw = poolHardware();
    var glyphs = decodedGlyphs(findCase(job.caseId), job.profile);
    var dims = poolDims(glyphs);
    var part = poolPartition(job.items, dims, job.params.radius);
    var est = poolEstimateBytes(part.a, part.b, dims, job.params.radius, poolHighwater);
    var gate = poolAdmit(job.items.length, hw.cpus, hw.memGB, est.total);
    if (!gate.ok) {
      reject(gate.reason, est);
      return;
    }
    if (poolHighwater !== null) {
      state.lastDecision = {
        admitted: true,
        reason: "admitted",
        pairs: job.items.length,
        estimateBytes: est.total,
        aItems: part.a.length,
        bItems: part.b.length,
      };
      done(true, { part: part, est: est, dims: dims });
      return;
    }
    if (!worker) {
      reject("memory-unknown", est);
      return;
    }
    var finished = false;
    poolProbe = {};
    poolProbe.timer = setTimeout(function () {
      if (finished) return;
      finished = true;
      poolProbe = null;
      reject("memory-unknown", est);
    }, POOL_PROBE_MS);
    poolProbe.next = function (msg) {
      if (finished) return;
      finished = true;
      try {
        clearTimeout(poolProbe.timer);
      } catch (ignore) {
        /* gone */
      }
      poolProbe = null;
      poolNotePrimaryLinear(msg.wasmLinearBytes);
      if (poolHighwater === null) {
        reject("memory-unknown", est);
        return;
      }
      var re = poolEstimateBytes(part.a, part.b, dims, job.params.radius, poolHighwater);
      var gate2 = poolAdmit(job.items.length, hw.cpus, hw.memGB, re.total);
      if (!gate2.ok) {
        reject(gate2.reason, re);
        return;
      }
      state.lastDecision = {
        admitted: true,
        reason: "admitted-probed",
        pairs: job.items.length,
        estimateBytes: re.total,
        aItems: part.a.length,
        bItems: part.b.length,
      };
      done(true, { part: part, est: re, dims: dims });
    };
    try {
      worker.postMessage({ kind: "pool-stats" });
    } catch (ignore) {
      if (!finished) {
        finished = true;
        try {
          clearTimeout(poolProbe.timer);
        } catch (e2) {
          /* gone */
        }
        poolProbe = null;
        reject("memory-unknown", est);
      }
    }
  }

  function transportKeys(job, items) {
    return items.map(function (item) {
      return { key: pairIdentityKey(job.key, item.key, item.metric), name: item.key };
    });
  }

  function startSingleJob(w, job) {
    var jobId = "j" + ++workerSeq;
    job.jobId = jobId;
    workerJobs[jobId] = job;
    if (job.flightCall) {
      var call = flightCalls[job.flightCall];
      if (call) call.kind = "single";
      flightAttachTransport(job.flightCall, { worker: w, jobId: jobId, keys: transportKeys(job, job.items) });
    }
    /* A pool retry must never hang on a silently dead worker: after
     * 60 s without settle it takes the main-thread fallback instead.
     * Ownership stays with the same call across the transport switch. */
    if (job.poolFinal) {
      job.retryTimer = setTimeout(function () {
        if (!workerJobs[jobId]) return;
        delete workerJobs[jobId];
        runMainThread(job);
      }, POOL_WATCHDOG_MS);
    }
    try {
      w.postMessage({
        kind: "score",
        jobId: jobId,
        dataset: job.dataset,
        captureSha: job.captureSha,
        glyphs: job.covers,
        key: job.key,
        params: job.params,
        items: job.items,
      });
    } catch (ignore) {
      delete workerJobs[jobId];
      if (job.retryTimer) {
        try {
          clearTimeout(job.retryTimer);
        } catch (e2) {
          /* gone */
        }
        job.retryTimer = null;
      }
      runMainThread(job);
    }
  }

  function clearRetryTimer(job) {
    if (job && job.retryTimer) {
      try {
        clearTimeout(job.retryTimer);
      } catch (ignore) {
        /* gone */
      }
      job.retryTimer = null;
    }
  }

  function startPoolJob(job, decided) {
    var part = decided.part,
      est = decided.est;
    var logicalId = "p" + ++workerSeq;
    var glyphs = decodedGlyphs(findCase(job.caseId), job.profile);
    function coversFor(items) {
      var cps = {};
      items.forEach(function (item) {
        cps[item.left] = true;
        cps[item.right] = true;
      });
      return transferCovers(glyphs, Object.keys(cps));
    }
    var logical = {
      id: logicalId,
      seq: job.seq,
      job: job,
      partA: {
        jobId: logicalId + "-a",
        items: part.a,
        keys: part.a.map(function (item) {
          return item.key;
        }),
        done: 0,
        result: null,
      },
      partB: {
        jobId: logicalId + "-b",
        items: part.b,
        keys: part.b.map(function (item) {
          return item.key;
        }),
        done: 0,
        result: null,
      },
      aux: null,
      auxReady: false,
      settled: false,
      retried: false,
      timer: null,
      estimateBytes: est.total,
      ledger: null,
    };
    logical.ledger = poolRecord({
      id: logicalId,
      gen: job.seq,
      admitted: true,
      pairs: job.items.length,
      aItems: part.a.length,
      bItems: part.b.length,
      estimateBytes: est.total,
      status: "pending",
      outcome: null,
      retries: 0,
      memA: null,
      memB: null,
    });
    poolJobs[logical.partA.jobId] = logical;
    poolJobs[logical.partB.jobId] = logical;
    poolLogical = logical;
    logical.flightCall = job.flightCall;
    if (job.flightCall) {
      var pcall = flightCalls[job.flightCall];
      if (pcall) pcall.kind = "pool";
      flightAttachTransport(job.flightCall, {
        worker: worker,
        jobId: logical.partA.jobId,
        keys: transportKeys(job, part.a),
      });
    }
    var aux;
    try {
      var src = workerSource();
      if (!src) throw new Error("worker source unavailable");
      var url = URL.createObjectURL(new Blob([src], { type: "text/javascript" }));
      aux = new Worker(url);
      URL.revokeObjectURL(url);
    } catch (err) {
      poolJobsCleanup(logical);
      logical.ledger.status = "settled";
      logical.ledger.outcome = "aux-spawn-failed:single";
      poolState().lastDecision = {
        admitted: false,
        reason: "aux-spawn-failed",
        pairs: job.items.length,
        estimateBytes: est.total,
      };
      startSingleJob(worker, job);
      return;
    }
    logical.aux = aux;
    poolState().auxLive = true;
    var readyTimer = setTimeout(function () {
      poolAuxFailed(logical, "aux-ready-timeout");
    }, POOL_AUX_READY_MS);
    aux.onmessage = function (e) {
      var msg = e.data;
      if (!msg || logical.settled) return;
      if (msg.kind === "ready" && !logical.auxReady) {
        logical.auxReady = true;
        try {
          clearTimeout(readyTimer);
        } catch (ignore) {
          /* gone */
        }
        if (logical.flightCall) {
          flightAttachTransport(logical.flightCall, {
            worker: aux,
            jobId: logical.partB.jobId,
            keys: transportKeys(job, part.b),
          });
        }
        try {
          aux.postMessage({
            kind: "score",
            jobId: logical.partB.jobId,
            dataset: job.dataset,
            captureSha: job.captureSha,
            key: job.key,
            glyphs: coversFor(logical.partB.items),
            params: job.params,
            items: logical.partB.items,
          });
        } catch (err) {
          poolAuxFailed(logical, "aux-post-failed");
          return;
        }
        try {
          worker.postMessage({
            kind: "score",
            jobId: logical.partA.jobId,
            dataset: job.dataset,
            captureSha: job.captureSha,
            key: job.key,
            glyphs: coversFor(logical.partA.items),
            params: job.params,
            items: logical.partA.items,
          });
        } catch (err) {
          recoverPoolJob(logical, "primary-post-failed");
          return;
        }
        resetPoolWatchdog(logical);
        return;
      }
      if (msg.kind === "error" && msg.jobId === null && !logical.auxReady) {
        try {
          clearTimeout(readyTimer);
        } catch (ignore) {
          /* gone */
        }
        poolAuxFailed(logical, "aux-init-error");
        return;
      }
      onWorkerMessage(msg);
    };
    aux.onerror = function () {
      if (!logical.settled && !logical.auxReady) {
        try {
          clearTimeout(readyTimer);
        } catch (ignore) {
          /* gone */
        }
      }
      poolAuxFailed(logical, "aux-error");
    };
    aux.onmessageerror = function () {
      poolAuxFailed(logical, "aux-messageerror");
    };
    try {
      aux.postMessage({
        kind: "init",
        params: job.params,
        dataset: job.dataset,
        captureSha: job.captureSha,
        glyphs: coversFor(logical.partB.items),
        bytes: wasmBytes(),
      });
    } catch (err) {
      try {
        clearTimeout(readyTimer);
      } catch (ignore) {
        /* gone */
      }
      poolAuxFailed(logical, "aux-init-post-failed");
    }
  }

  function poolJobsCleanup(logical) {
    delete poolJobs[logical.partA.jobId];
    delete poolJobs[logical.partB.jobId];
    if (logical.timer) {
      try {
        clearTimeout(logical.timer);
      } catch (ignore) {
        /* gone */
      }
      logical.timer = null;
    }
    retireAuxWorker(logical);
  }

  function poolAuxFailed(logical, reason) {
    if (!logical || logical.settled) return;
    recoverPoolJob(logical, reason);
  }

  function poolWatchdogExpired(logical) {
    if (!logical || logical.settled) return;
    logical.timer = null;
    recoverPoolJob(logical, "watchdog-inactivity");
  }

  /* Primary death during a pool job: the existing onerror handoff calls
   * this before rerunning single jobs. Recovery retries full missing
   * work on the main-thread fallback, never a partial paint. */
  function abortPoolToMainThread() {
    var seen = [];
    Object.keys(poolJobs).forEach(function (jobId) {
      var logical = poolJobs[jobId];
      if (!logical || logical.settled) return;
      if (seen.indexOf(logical) >= 0) return;
      seen.push(logical);
      recoverPoolJob(logical, "primary-terminated");
    });
  }

  /* Read-only observability plus the injected watchdog trigger used by
   * tests instead of a 60 s wait. No control knob: same expiry handler. */
  window.__yyPoolTest = {
    expireWatchdog: function () {
      if (poolLogical && !poolLogical.settled) {
        poolWatchdogExpired(poolLogical);
        return poolLogical ? poolLogical.id : "expired";
      }
      return null;
    },
    expireRetry: function () {
      var fired = [];
      Object.keys(workerJobs).forEach(function (jobId) {
        var job = workerJobs[jobId];
        if (job && job.poolFinal && job.retryTimer) {
          try {
            clearTimeout(job.retryTimer);
          } catch (ignore) {
            /* gone */
          }
          job.retryTimer = null;
          delete workerJobs[jobId];
          fired.push(jobId);
          runMainThread(job);
        }
      });
      return fired;
    },
    current: function () {
      return poolLogical ? poolLogical.id : null;
    },
  };

  /* Bounded pair-cache observability for independent checks: counters
   * and sizes only, no event history. `inject` routes a crafted receipt
   * through the real onWorkerMessage path. */
  window.__yyPairCache = {
    snapshot: function () {
      return pairCacheSnapshot(pairCache);
    },
  };
  window.__yyMainCalls = mainThreadCalls;
  window.__yyPairCacheTest = {
    stats: function () {
      return pairCacheSnapshot(pairCache);
    },
    inject: function (msg) {
      onWorkerMessage(msg);
      return true;
    },
    mainCalls: function () {
      return {
        calls: mainThreadCalls.calls,
        returns: mainThreadCalls.returns,
        throws: mainThreadCalls.throws,
        pre: mainThreadCalls.pre,
        errors: mainThreadCalls.errors,
      };
    },
  };

  /* Bounded flight observability for independent checks: running counts,
   * live call records and failure marks only, no event history.
   * expireAcks runs the production acknowledgement-expiry handler
   * verbatim for every pending call (the same code the 60 s timer runs,
   * only the wait is skipped); setBudget/resetBudget swap the accounted
   * budget for tiny-budget tests (private helper, no UI). */
  window.__yyFlightTest = {
    stats: function () {
      return {
        starts: flight.stats.starts,
        joins: flight.stats.joins,
        blocked: flight.stats.blocked,
        running: flight.running.size,
        calls: Object.keys(flightCalls).length,
        gens: Object.keys(genNeeds).length,
        fails: Object.keys(scoreFailCounts).length,
      };
    },
    expireAcks: function () {
      Object.keys(flightCalls).forEach(flightAckExpired);
      settleCheck(renderSeq);
      return true;
    },
    setBudget: function (bytes) {
      pairCache.budget = bytes;
      pairCacheEnforce(pairCache);
      return pairCacheSnapshot(pairCache);
    },
    resetBudget: function () {
      pairCache.budget = PAIR_CACHE_TARGET_BYTES;
      pairCacheEnforce(pairCache);
      return pairCacheSnapshot(pairCache);
    },
  };

  /* Publish one side's partition: every record passes the same strict
   * complete-curve validation as checkpoints and final receipts. Records
   * that fail validation (or honest engine errors) are excluded and
   * reported so the bounded recovery retries exactly them, never a
   * silent partial merge. */
  function poolPublishValid(logical, valid) {
    var names = Object.keys(valid);
    if (!names.length) return { kept: 0, failed: [] };
    var byKey = {};
    logical.job.items.forEach(function (item) {
      byKey[item.key] = item;
    });
    var shaped = {},
      failed = [];
    names.forEach(function (name) {
      var rec = valid[name];
      var item = byKey[name];
      if (!item || !validateCheckpointSteps(item, rec)) {
        pairCache.stats.dropped++;
        if (item) {
          failed.push(pairIdentityKey(logical.job.key, name, item.metric));
        }
        return;
      }
      /* Same ownership gate as single terminals: an orphan side
       * terminal with a newer live owner on the key drops without
       * releasing or painting the new owner. */
      if (!terminalOwnerAllows(flight, logical.job.key, logical.flightCall, name, item.metric)) {
        pairCache.stats.dropped++;
        return;
      }
      shaped[name] = { metric: rec.metric, steps: rec.steps, domain: rec.domain };
    });
    /* Exact-identity cache only: never paints or touches busy notes. */
    var kept = storeShapedPairs(logical.job.key, shapeResults(shaped));
    scoreCalls += names.length;
    return { kept: kept, failed: failed };
  }

  /* Pair name from a metric-carrying identity key (setting and metric
   * precede the final separator; names never contain newlines). */
  function pairNameOf(identityKey) {
    return identityKey.slice(identityKey.lastIndexOf("\n") + 1);
  }

  /* Keys still owned by one logical pool call. */
  function poolOwnedKeys(logical) {
    if (!logical.flightCall) return [];
    var out = [];
    flight.running.forEach(function (r, key) {
      if (r.owner === logical.flightCall) out.push(key);
    });
    return out;
  }

  /* Names this side was told to skip: trimmed pairs never arrive in
   * its done receipt, so the exact-set check excludes them and the
   * recovery path treats them as released, not lost. */
  function sideDroppedNames(logical, side) {
    var out = {};
    if (!logical.flightCall) return out;
    var call = flightCalls[logical.flightCall];
    if (!call) return out;
    call.transports.forEach(function (t) {
      if (t.jobId !== side.jobId || !t.droppedNames) return;
      Object.keys(t.droppedNames).forEach(function (name) {
        out[name] = true;
      });
    });
    return out;
  }

  function onPoolMessage(msg) {
    var logical = poolJobs[msg.jobId];
    if (!logical || logical.settled) return;
    var side =
      msg.jobId === logical.partA.jobId ? logical.partA : msg.jobId === logical.partB.jobId ? logical.partB : null;
    if (!side) return;
    /* Stop acknowledgement for one side: release its owned keys (the
     * completed subset already merged via progress) and let the current
     * view re-resolve. A fully trimmed logical job retires here. */
    if (msg.kind === "score-stopped") {
      if (logical.flightCall) {
        var owned = [];
        flight.running.forEach(function (r, key) {
          if (r.owner === logical.flightCall && side.keys.indexOf(pairNameOf(key)) >= 0) {
            owned.push(key);
          }
        });
        owned.forEach(function (key) {
          flight.running.delete(key);
        });
      }
      if (!poolOwnedKeys(logical).length) {
        if (logical.flightCall) flightReleaseCallId(logical.flightCall);
        logical.flightCall = null;
        logical.settled = true;
        poolJobsCleanup(logical);
        logical.ledger.status = "settled";
        logical.ledger.outcome = "trimmed-idle";
        settleCheck(renderSeq);
      }
      return;
    }
    if (msg.kind === "progress") {
      /* Subjob checkpoints merge under the logical job identity now;
       * the done receipt still decides the paint. Ownership-gated: only
       * the current owner merges; halted or foreign receipts are ignored
       * without counters. */
      mergeScoreCheckpoints(
        { key: logical.job.key, captureSha: logical.job.captureSha, items: side.items },
        msg,
        logical.flightCall,
      );
      if (typeof msg.done === "number" && msg.done > side.done) {
        side.done = msg.done;
        logical.job.received = logical.partA.done + logical.partB.done;
        if (side === logical.partA) {
          logical.linA = msg.wasmLinearBytes;
        } else {
          logical.linB = msg.wasmLinearBytes;
        }
        resetPoolWatchdog(logical);
      }
      return;
    }
    if (msg.kind === "done") {
      var dropped = sideDroppedNames(logical, side);
      var expected = side.keys.filter(function (name) {
        return !dropped[name];
      });
      var check = poolValidatePartition(expected, msg.results);
      if (!check.ok) {
        recoverPoolJob(logical, "malformed-" + (side === logical.partA ? "a" : "b") + ":" + check.reason);
        return;
      }
      side.result = check;
      /* Trimmed keys were released when the drop was posted; the rest
       * stay owned until the logical job settles or recovers. */
      if (logical.flightCall) {
        var dtable = window.YY_TABLES[tableLabel(findCase(logical.job.caseId), logical.job.profile)];
        Object.keys(dropped).forEach(function (name) {
          var idkey = pairIdentityKey(logical.job.key, name, metricFor(dtable, name));
          var r = flight.running.get(idkey);
          if (r && r.owner === logical.flightCall) {
            flight.running.delete(idkey);
          }
        });
      }
      side.done = side.keys.length;
      logical.job.received = logical.partA.done + logical.partB.done;
      if (side === logical.partA) {
        poolNotePrimaryLinear(msg.wasmLinearBytes);
        logical.ledger.memA = msg.wasmLinearBytes;
        logical.linA = msg.wasmLinearBytes;
      } else {
        logical.ledger.memB = msg.wasmLinearBytes;
        logical.linB = msg.wasmLinearBytes;
      }
      resetPoolWatchdog(logical);
      if (logical.partA.result && logical.partB.result) {
        settlePoolJob(logical);
        return;
      }
      /* Observed combined over target while one side is still running:
       * terminate aux and retry the unfinished work on one worker. */
      if (
        typeof logical.linA === "number" &&
        typeof logical.linB === "number" &&
        logical.linA + logical.linB > POOL_LINEAR_TARGET
      ) {
        recoverPoolJob(logical, "combined-over-target");
      }
      return;
    }
    if (msg.kind === "error") {
      /* OOM fails closed with the same full-work fallback below: no
       * domain clamp, no search budget. */
      var oom = /memory|alloc|OOM/i.test(String(msg.message || ""));
      recoverPoolJob(logical, (oom ? "oom-" : "error-") + (side === logical.partA ? "a" : "b"));
      return;
    }
  }

  function settlePoolJob(logical) {
    if (logical.settled) return;
    /* Honest engine errors terminate through the bounded retry instead
     * of counting as complete. */
    var errCount = Object.keys(logical.partA.result.errors).length + Object.keys(logical.partB.result.errors).length;
    if (errCount) {
      recoverPoolJob(logical, "partition-engine-errors");
      return;
    }
    /* A trimmed side never completes its dropped keys: without the full
     * original set there is nothing exact to present, so the remainder
     * goes through the same bounded recovery as any other shortfall. */
    var incomplete = false;
    logical.job.items.forEach(function (item) {
      if (
        !Object.prototype.hasOwnProperty.call(logical.partA.result.valid, item.key) &&
        !Object.prototype.hasOwnProperty.call(logical.partB.result.valid, item.key)
      ) {
        incomplete = true;
      }
    });
    if (incomplete) {
      recoverPoolJob(logical, "partial-after-trim");
      return;
    }
    /* Observed combined over target with both sides done: the full set
     * is exact, so present it once, then disable the pool for the
     * session. The aux retire in cleanup frees its engine bytes. */
    var overTarget =
      typeof logical.linA === "number" &&
      typeof logical.linB === "number" &&
      logical.linA + logical.linB > POOL_LINEAR_TARGET;
    logical.settled = true;
    poolJobsCleanup(logical);
    var merged = {};
    logical.job.items.forEach(function (item) {
      merged[item.key] = Object.prototype.hasOwnProperty.call(logical.partA.result.valid, item.key)
        ? logical.partA.result.valid[item.key]
        : logical.partB.result.valid[item.key];
    });
    logical.ledger.status = "settled";
    logical.ledger.outcome = overTarget ? "completed-over-target" : "completed";
    if (overTarget) {
      poolSessionDisabled = "combined-over-target";
      poolState().disabled = "combined-over-target";
    }
    finishScoreJob(logical.job, "pool", merged);
  }

  /* Stop request to both pool sides before recovery re-resolves: a live
   * executor drains at its chunk boundary instead of running orphaned
   * beside the retry. Best effort (a dead transport is already proof);
   * posting cancel proves nothing by itself, the reserve and terminal
   * gates below carry the safety. */
  function poolCancelSides(logical) {
    [logical.partA, logical.partB].forEach(function (side) {
      try {
        var w = side === logical.partA ? worker : logical.aux;
        if (w) w.postMessage({ kind: "cancel", jobId: side.jobId });
      } catch (ignore) {
        /* transport gone */
      }
    });
  }

  /* Bounded recovery: disable the pool for the session, keep validated
   * records under their exact cache identity, then retry the remainder
   * exactly once on the existing one-worker/main-thread path. A failed
   * retry ends in an honest visible error, never a resolve loop. The
   * retry reserves only keys no live owner holds (checked reserve joins
   * running work instead of clobbering it), so repeated error, watchdog
   * or ack invocations collapse onto one bounded exact retry with the
   * latest view subscribed. */
  function recoverPoolJob(logical, reason) {
    if (!logical || logical.settled) return;
    /* Idempotent: exactly one bounded retry per logical call. A repeat
     * invocation only re-resolves the current view. */
    if (logical.retried) {
      settleCheck(renderSeq);
      return;
    }
    logical.settled = true;
    poolJobsCleanup(logical);
    poolSessionDisabled = reason;
    poolState().disabled = reason;
    poolCancelSides(logical);
    var kept = 0,
      failedIds = [];
    [logical.partA, logical.partB].forEach(function (side) {
      if (side.result && side.result.ok) {
        var pub = poolPublishValid(logical, side.result.valid);
        kept += pub.kept;
        failedIds = failedIds.concat(pub.failed);
      }
    });
    noteScoreFailures(failedIds);
    var c = findCase(logical.job.caseId);
    var table = window.YY_TABLES[tableLabel(c, logical.job.profile)];
    var settingKey = logical.job.key;
    var missing = [];
    logical.job.items.forEach(function (item) {
      if (!table || !cachedPairRecord(settingKey, item.key, item.metric)) {
        missing.push(item);
      }
    });
    /* Release pool ownership before re-reserving: no key keeps two
     * owners across the handoff. */
    if (logical.flightCall) flightReleaseCallId(logical.flightCall);
    logical.flightCall = null;
    logical.ledger.retries++;
    logical.ledger.keptPairs = kept;
    if (!missing.length && kept) {
      logical.ledger.status = "settled";
      logical.ledger.outcome = "recovered-complete";
      /* Cached records never paint a superseded generation, but the
       * current view may already be complete from this cache. */
      if (logical.job.seq !== renderSeq) {
        logical.ledger.outcome = "recovered-complete-stale";
        settleCheck(renderSeq);
        return;
      }
      settleCheck(logical.job.seq);
      return;
    }
    if (!missing.length) {
      logical.ledger.status = "settled";
      logical.ledger.outcome = "recovery-failed";
      showEngineError("pool " + reason + "; showing last valid view.");
      /* Cached data may still complete the current view. */
      settleCheck(renderSeq);
      return;
    }
    if (logical.job.seq !== renderSeq) {
      logical.ledger.status = "cancelled";
      logical.ledger.outcome = "superseded-during-recovery";
      /* Ownership already released above; the current view re-resolves
       * instead of hanging on keys no owner holds. */
      settleCheck(renderSeq);
      return;
    }
    /* Retry only keys the current view still subscribes: unsubscribed
     * remainder stays released for a later view to dispatch. */
    var current = genNeeds[renderSeq];
    var wanted = {};
    if (current) {
      current.keys.forEach(function (k) {
        wanted[k.key] = true;
      });
    }
    var retryItems = missing.filter(function (item) {
      return wanted[pairIdentityKey(settingKey, item.key, item.metric)];
    });
    if (!retryItems.length) {
      logical.ledger.status = "settled";
      logical.ledger.outcome = "retry-unneeded-superseded";
      settleCheck(renderSeq);
      return;
    }
    /* Checked reservation: keys already live-owned elsewhere (an ack
     * path already redispatched them, a side still draining) are
     * joined, never overwritten. Only the actually reserved keys are
     * posted below, so two racing recovery callbacks can never start
     * the same key twice. */
    var retryIds = retryItems.map(function (item) {
      return pairIdentityKey(settingKey, item.key, item.metric);
    });
    var res = flightReserve(flight, retryIds, [renderSeq]);
    var reservedIds = {};
    res.reserved.forEach(function (key) {
      reservedIds[key] = true;
    });
    retryItems = retryItems.filter(function (item) {
      return reservedIds[pairIdentityKey(settingKey, item.key, item.metric)];
    });
    if (!res.callId) {
      logical.retried = true;
      logical.ledger.status = "settled";
      logical.ledger.outcome = "retry-joined-live";
      settleCheck(renderSeq);
      return;
    }
    logical.retried = true;
    logical.ledger.status = "pending";
    logical.ledger.outcome = "retrying:" + reason;
    flightNewCall(res.callId, res.reserved);
    /* Attempt credit: the pool already spent the first attempt, so a
     * failed retry lands on the honest error instead of a third run. */
    noteScoreFailures(res.reserved);
    var retry = {
      seq: renderSeq,
      caseId: logical.job.caseId,
      profile: logical.job.profile,
      key: logical.job.key,
      captureSha: logical.job.captureSha,
      dataset: logical.job.dataset,
      covers: logical.job.covers,
      params: logical.job.params,
      items: retryItems,
      results: {},
      received: 0,
      total: retryItems.length,
      ms: null,
      source: null,
      fallbackRetried: false,
      poolFinal: true,
      flightCall: res.callId,
    };
    if (worker && !workerFailed) {
      startSingleJob(worker, retry);
    } else {
      runMainThread(retry);
    }
  }

  function onWorkerMessage(msg) {
    if (!msg) return;
    if (msg.kind === "pool-stats") {
      if (poolProbe) poolProbe.next(msg);
      else poolNotePrimaryLinear(msg.wasmLinearBytes);
      return;
    }
    if (msg.jobId && poolJobs[msg.jobId]) {
      onPoolMessage(msg);
      return;
    }
    if (msg.kind === "ready" || msg.kind === "synced") {
      poolNotePrimaryLinear(msg.wasmLinearBytes);
      return;
    }
    /* Field batches travel on their own registry so score cancellation
     * never touches them and vice versa. A stopped receipt only records
     * executed counts on its ledger entry; only a matching generation
     * may paint or settle. */
    if (msg.kind === "fields" || msg.kind === "fields-stopped") {
      var frec = fieldWorkerJobs[msg.jobId];
      if (msg.kind === "fields-stopped") {
        if (frec) {
          delete fieldWorkerJobs[msg.jobId];
          noteStoppedFieldJob(msg.jobId, msg);
        }
        return;
      }
      if (!frec) return;
      delete fieldWorkerJobs[msg.jobId];
      finishFieldBatch(frec.batchId, msg, "worker");
      return;
    }
    var job = workerJobs[msg.jobId];
    if (!job) {
      /* A fields-job error arrives under the field registry. */
      var efr = fieldWorkerJobs[msg.jobId];
      if (efr && msg.kind === "error") {
        delete fieldWorkerJobs[msg.jobId];
        if (!efr.fallbackRetried && !workerFailed) {
          efr.fallbackRetried = true;
          runFieldFallback(findFieldBatch(efr.batchId));
        } else {
          finishFieldBatch(efr.batchId, { error: msg.message }, "worker");
        }
      }
      return;
    }
    if (msg.kind === "score-stopped") {
      /* Stop acknowledgement: the transport confirms which pairs it
       * executed (already merged via progress) and that nothing more
       * will arrive. Release ownership and let the current view
       * re-resolve; the same key may now dispatch exactly one new owner. */
      releaseJobOwnership(job);
      delete workerJobs[msg.jobId];
      clearRetryTimer(job);
      poolNotePrimaryLinear(msg.wasmLinearBytes);
      settleCheck(renderSeq);
      return;
    }
    if (msg.kind === "progress") {
      job.received = msg.done;
      poolNotePrimaryLinear(msg.wasmLinearBytes);
      /* Validated checkpoints merge now under the owner call; paint
       * still waits for full view coverage. */
      mergeScoreCheckpoints(job, msg, job.flightCall);
      return;
    }
    if (msg.kind === "done") {
      delete workerJobs[msg.jobId];
      clearRetryTimer(job);
      poolNotePrimaryLinear(msg.wasmLinearBytes);
      finishScoreJob(job, "worker", msg.results);
      return;
    }
    if (msg.kind === "error") {
      delete workerJobs[msg.jobId];
      clearRetryTimer(job);
      if (!job.fallbackRetried && !workerFailed && !job.poolFinal) {
        job.fallbackRetried = true;
        runMainThread(job);
      } else if (job.poolFinal && !job.fallbackRetried && !workerFailed) {
        job.fallbackRetried = true;
        runMainThread(job);
      } else {
        if (!job.poolFinal) {
          /* A wholly failed attempt counts like failed records: the
           * next settle retries once or ends honest instead of looping
           * a dead transport. */
          var failedAll = {};
          job.items.forEach(function (item) {
            failedAll[item.key] = { error: msg.message };
          });
          finishScoreJob(job, "worker", failedAll);
        }
        showEngineError(msg.message);
      }
    }
  }

  function showEngineError(message) {
    /* Engine failure is honest and visible: replace any pending busy on
     * both notes, since the comparison box may stay collapsed. */
    var text = "Engine unavailable (" + message + "); showing last valid view.";
    $("yy-sample-note").textContent = text;
    $("yy-explain-note").textContent = text;
    $("yy-explain-field").removeAttribute("aria-busy");
  }

  /* Dispatch one batch of genuinely missing pairs under a fresh owner
   * call (or an existing reservation). Concurrent needs for one key share
   * the running execution: the registry reserved them, this only attaches
   * the transport. At most one pool logical runs at a time; overflow
   * batches fall back to the single worker. */
  function dispatchMissing(c, profile, table, needs, gen, callId) {
    var reserved = needs.map(function (n) {
      return n.key;
    });
    if (!callId) {
      var res = flightReserve(flight, reserved, [gen]);
      if (!res.callId) {
        /* Everything is already owned, blocked or cached: no ghost
         * call, no empty dispatch; the current view re-resolves. */
        settleCheck(gen);
        return;
      }
      callId = res.callId;
      reserved = res.reserved;
    }
    if (!flightCalls[callId]) {
      flightNewCall(callId, reserved);
    }
    var allowed = {};
    reserved.forEach(function (key) {
      allowed[key] = true;
    });
    var items = needs
      .filter(function (n) {
        return allowed[n.key];
      })
      .map(function (n) {
        return n.item;
      });
    var glyphs = decodedGlyphs(c, profile);
    var cps = {};
    items.forEach(function (item) {
      cps[item.left] = true;
      cps[item.right] = true;
    });
    var job = {
      seq: gen,
      caseId: c.id,
      profile: profile,
      key: computedKey(c, profile),
      captureSha: captureSha(c, profile),
      dataset: tableLabel(c, profile),
      covers: transferCovers(glyphs, Object.keys(cps)),
      params: engineParams(),
      items: items,
      results: {},
      received: 0,
      total: items.length,
      ms: null,
      source: null,
      fallbackRetried: false,
      flightCall: callId,
    };
    var w = ensureWorker();
    if (!w) {
      flightCalls[callId].kind = "fallback";
      runMainThread(job);
      return;
    }
    poolDecide(job, function (usePool, decided) {
      /* Superseded generations release instead of dispatching. */
      if (job.seq !== renderSeq || !genNeeds[gen]) {
        flightReleaseCallId(callId);
        return;
      }
      if (usePool && decided && !poolLogical) {
        startPoolJob(job, decided);
        return;
      }
      startSingleJob(w, job);
    });
  }

  /* Validate one terminal receipt with the same strict complete-curve
   * rule as checkpoints, then store. Returns stored count and the failed
   * identity keys (invalid records and honest engine errors). Never
   * throws; never loops by itself. */
  function validateAndStore(job, results) {
    var byKey = {};
    (job.items || []).forEach(function (item) {
      byKey[item.key] = item;
    });
    var shaped = {},
      failed = [];
    Object.keys(results || {}).forEach(function (name) {
      var rec = results[name];
      var item = byKey[name];
      if (!item || !rec || rec.error || !validateCheckpointSteps(item, rec)) {
        if (item) {
          if (rec && !rec.error) pairCache.stats.dropped++;
          failed.push(pairIdentityKey(job.key, name, item.metric));
        } else {
          pairCache.stats.dropped++;
        }
        return;
      }
      /* A newer live owner wins: an orphan terminal never overwrites
       * it, and the orphan's call cannot release it either (release is
       * keyed on the orphan's own call). Ownerless late data still
       * caches; the current owner stores. */
      if (!terminalOwnerAllows(flight, job.key, job.flightCall, name, item.metric)) {
        pairCache.stats.dropped++;
        return;
      }
      shaped[name] = rec;
    });
    var stored = storeShapedPairs(job.key, shapeResults(shaped));
    return { stored: stored, failed: failed };
  }

  /* Chunked same-engine main-thread fallback: the identical WASM engine
   * instantiated from the same inlined bytes, yielding between pairs so
   * controls stay responsive. Used only when the worker is unavailable;
   * never old math. */
  function fallbackEngine(params) {
    var key = "q=" + params.q + "|r=" + params.radius;
    if (fallbackEngines[key]) return fallbackEngines[key];
    if (!window.YYWasmRT) return null;
    var rt = window.YYWasmRT;
    if (!rt.__yyModule) rt.__yyModule = rt.initSync({ module: wasmBytes() });
    var eng;
    try {
      eng = new rt.YinYangEngine(JSON.stringify(params));
      var v = JSON.parse(eng.version());
      if (!v || v.score_model !== SCORE_MODEL || v.frozen_normalization_radius !== NORM_RADIUS) {
        return null;
      }
    } catch (ignore) {
      return null;
    }
    fallbackEngines[key] = eng;
    fallbackOrder.push(key);
    while (fallbackOrder.length > 2) delete fallbackEngines[fallbackOrder.shift()];
    return eng;
  }

  /* Chunked same-engine main-thread fallback: the identical WASM engine
   * instantiated from the same inlined bytes, yielding between pairs so
   * controls stay responsive. Used only when the worker is unavailable;
   * never old math. Each pair consults the running registry at its chunk
   * boundary, so detached work is skipped without computing and batches
   * never clobber each other: ownership, not a global active flag,
   * decides what runs. Counters sit on the actual score_pair_local
   * boundary like the worker path. */
  function runMainThread(job) {
    var eng = fallbackEngine(job.params);
    if (job.flightCall && flightCalls[job.flightCall]) {
      flightCalls[job.flightCall].kind = "fallback";
      flightAttachTransport(job.flightCall, { fallback: true });
    }
    if (!eng) {
      releaseJobOwnership(job);
      /* A futile main-thread attempt still counts: without credit the
       * settle below redispatches the same missing pairs onto dead
       * transports instead of ending honest after two strikes. */
      noteScoreFailures(
        job.items.map(function (item) {
          return pairIdentityKey(job.key, item.key, item.metric);
        }),
      );
      showEngineError("WASM unavailable in this browser");
      settleCheck(job.seq);
      return;
    }
    var glyphs = decodedGlyphs(findCase(job.caseId), job.profile);
    var i = 0;
    function identityOf(item) {
      return pairIdentityKey(job.key, item.key, item.metric);
    }
    function ownedLive(item) {
      if (!job.flightCall) return true;
      var r = flight.running.get(identityOf(item));
      return !!(r && r.owner === job.flightCall && !r.stopping);
    }
    function loadBoth(leftCp, rightCp) {
      var out = true;
      [[leftCp], [rightCp]].forEach(function (pair) {
        var cp = pair[0];
        var rec = glyphs[String(cp)];
        if (!rec) {
          out = false;
          return;
        }
        try {
          eng.load_glyph(
            job.dataset,
            job.captureSha,
            Number(cp),
            rec.w,
            rec.h,
            rec.left,
            rec.top,
            new Float64Array(rec.cover),
          );
        } catch (ignore) {
          out = false;
        }
      });
      return out;
    }
    function chunk() {
      if (!job.flightCall || !flightCalls[job.flightCall]) return;
      /* Same validated checkpoint merge as the worker path, at the same
       * <=2-pair boundary; errors still ride the terminal receipt only. */
      var startM = i;
      var end = Math.min(i + 2, job.items.length);
      for (; i < end; i++) {
        var item = job.items[i];
        if (!ownedLive(item)) continue;
        var domain;
        try {
          if (!loadBoth(item.left, item.right)) throw new Error("missing cover");
          domain = JSON.parse(eng.search_domain(job.dataset, Number(item.left), Number(item.right)));
        } catch (e) {
          job.results[item.key] = { error: String((e && e.message) || e) };
          mainThreadCalls.pre++;
          mainThreadCalls.errors++;
          continue;
        }
        mainThreadCalls.calls++;
        try {
          var deltas =
            domain.lo === undefined || domain.hi === undefined ? [0] : rangeDeltas(domain.lo, domain.hi, item.metric);
          var res = JSON.parse(
            eng.score_pair_local(
              job.dataset,
              Number(item.left),
              Number(item.right),
              item.metric,
              new Int32Array(deltas),
              TAU,
              NORM_RADIUS,
              STRENGTH,
              NaN,
            ),
          );
          job.results[item.key] = { metric: item.metric, steps: res.steps, domain: domain };
          mainThreadCalls.returns++;
        } catch (e) {
          job.results[item.key] = { error: String((e && e.message) || e) };
          mainThreadCalls.throws++;
          mainThreadCalls.errors++;
        }
        job.received++;
      }
      var fbCps = {};
      for (var m = startM; m < end; m++) {
        var fbItem = job.items[m];
        var fbRec = job.results[fbItem.key];
        if (fbRec && !fbRec.error && Array.isArray(fbRec.steps)) {
          fbCps[fbItem.key] = fbRec;
        }
      }
      mergeScoreCheckpoints(job, { key: job.key, captureSha: job.captureSha, checkpoints: fbCps }, job.flightCall);
      var moreOwned = false;
      for (var q = i; q < job.items.length; q++) {
        if (ownedLive(job.items[q])) {
          moreOwned = true;
          break;
        }
      }
      if (moreOwned) {
        setTimeout(chunk, 0);
        return;
      }
      finishScoreJob(job, "main-thread", job.results);
    }
    setTimeout(chunk, 0);
  }

  function shapeResults(results) {
    var shaped = {};
    Object.keys(results).forEach(function (name) {
      var rec = results[name];
      if (!rec || rec.error || !rec.steps) return;
      shaped[name] = {
        metric: rec.metric,
        steps: rec.steps.map(function (s) {
          return s.step;
        }),
        entry: YYU.shapeEntry(rec.steps),
        search: searchFor(rec.domain),
      };
    });
    return shaped;
  }

  /* Terminal receipt: validate every record with the same strict rule
   * as checkpoints (no legacy bypass), release ownership, then let the
   * current view settle. Failures count toward the bounded retry gate:
   * two consecutive validation failures on one identity end in an honest
   * error instead of a resolve loop. */
  function finishScoreJob(job, source, results) {
    if (job.jobId) delete workerJobs[job.jobId];
    job.source = source;
    scoreCalls += job.received || Object.keys(results).length;
    var checked = validateAndStore(job, results || {});
    if (checked.failed.length) noteScoreFailures(checked.failed);
    releaseJobOwnership(job);
    settleCheck(job.seq);
    /* A terminal from a superseded producer still wakes the current
     * subscribed view: joined generations never settle themselves, and
     * only the current view may paint. Idempotent via the painted guard. */
    if (job.seq !== renderSeq) settleCheck(renderSeq);
  }

  /* ---- field layers: slate crops + contribution maps, on demand ---- */

  var lastChoiceSet = null;

  /* Slate lattice cache: one entry per (dataset, codepoint) in the
   * whole-glyph `slate` projection namespace. Values are whole engine
   * `slate` lattices in glyph-local ink-plane coords (origin at
   * trunc(left - pad)); placement-independent, so the frame is not in
   * the key and repeats share one entry. The lattice extent follows the
   * reach (pad includes R) and the values follow q, so both stay in the
   * key; the `slate|` namespace keeps stale `lslate` grids unrestorable.
   * The painter translates each lattice by its run's
   * laid-out origin and clips to the display frame. Bounded by entry
   * count and total points. Display only. */
  var slateCache = {};
  var slateOrder = [];
  var slatePoints = 0;
  var SLATE_ENTRY_CAP = 512;
  var SLATE_POINTS_CAP = 4000000;

  function slateCacheKey(tag, cp) {
    return tag + "|slate|" + cp + "|" + state.reach + "|" + state.falloff;
  }

  function cachedSlate(tag, cp) {
    return slateCache[slateCacheKey(tag, cp)] || null;
  }

  function publishSlate(tag, cp, grid) {
    var key = slateCacheKey(tag, cp);
    if (!slateCache[key]) {
      slateCache[key] = grid;
      slateOrder.push(key);
      if (grid && grid.f) slatePoints += grid.f.length;
      while (
        slateOrder.length &&
        (slateOrder.length > SLATE_ENTRY_CAP || slatePoints > SLATE_POINTS_CAP) &&
        slateOrder[0] !== key
      ) {
        var oldest = slateOrder.shift();
        var drop = slateCache[oldest];
        if (drop && drop.f) slatePoints -= drop.f.length;
        delete slateCache[oldest];
      }
    }
    return slateCache[key];
  }

  /* Coupling-map cache: one entry per (dataset, pair, chosen step, R, q).
   * Target is not in the key: target-only moves reuse the map whenever the
   * chosen step is unchanged; R/q change the window and the values, so
   * they miss. Bounded by entry count and total map points. Display only:
   * the scorer never reads these maps. */
  var contribCache = {};
  var contribOrder = [];
  var contribPoints = 0;
  var CONTRIB_ENTRY_CAP = 512;
  var CONTRIB_POINTS_CAP = 2000000;
  var contribHits = 0,
    contribMisses = 0;
  /* Cumulative score-call count for diagnostics. */
  var scoreCalls = 0;
  /* Last valid paint inputs for color-only repaints: color/alpha edits
   * redraw these cached grids/layers and never rescore or rebuild maps. */
  var lastPaint = null;
  var fieldSeq = 0;

  /* Cache accounting for unique (pair, step) computations: hits reuse a
   * shared map, misses compute it once for all placed occurrences. */
  function contribAccount(key) {
    if (contribCache[key] !== undefined) {
      contribHits++;
      return true;
    }
    contribMisses++;
    return false;
  }

  function publishContrib(key, layer) {
    contribCache[key] = layer;
    contribOrder.push(key);
    if (layer && layer.c) contribPoints += layer.c.length;
    while (
      contribOrder.length &&
      (contribOrder.length > CONTRIB_ENTRY_CAP || contribPoints > CONTRIB_POINTS_CAP) &&
      contribOrder[0] !== key
    ) {
      var oldest = contribOrder.shift();
      var drop = contribCache[oldest];
      if (drop && drop.c) contribPoints -= drop.c.length;
      delete contribCache[oldest];
    }
  }

  /* Field-layer request batch for the current view: one cancellable batch
   * per logical view. Ink paints immediately in renderFocus; fields are
   * debounced separately so rapid choice moves coalesce into a single
   * dispatch. Every placed occurrence renders a translated layer, but maps
   * with an identical computation identity (dataset, pair, step, reach,
   * falloff) compute once and share the result. Covers travel once per
   * logical batch. Missing layers keep the previous paint; only the
   * matching generation paints, and a superseded batch stops at a bounded
   * operation without touching the notes. */
  var FIELD_DEBOUNCE_MS = 90;
  var fieldTimer = null;
  var fieldPending = null;
  var fieldWorkerJobs = {};
  var fieldBatches = {};

  function fieldLedger() {
    return window.__yyFieldBatches || (window.__yyFieldBatches = []);
  }

  function findFieldBatch(batchId) {
    return fieldBatches[batchId] || null;
  }

  function ledgerEntry(batchId) {
    var ledger = fieldLedger();
    for (var i = 0; i < ledger.length; i++) {
      if (ledger[i].id === batchId) return ledger[i];
    }
    return null;
  }

  function recordFieldBatch(batch, slateCount, mapCount) {
    var ledger = fieldLedger();
    ledger.push({
      id: batch.id,
      gen: batch.gen,
      jobId: null,
      postedSlates: slateCount,
      postedMaps: mapCount,
      executedSlates: 0,
      executedMaps: 0,
      status: "pending",
      source: null,
      painted: false,
    });
    while (ledger.length > 8) ledger.shift();
  }

  /* A stopped receipt only fills executed counts on its ledger entry; the
   * batch itself was already superseded at cancel time and never paints. */
  function noteStoppedFieldJob(jobId, msg) {
    var ledger = fieldLedger();
    for (var i = 0; i < ledger.length; i++) {
      if (ledger[i].jobId === jobId && ledger[i].status === "pending") {
        ledger[i].executedSlates = msg.executedSlates || 0;
        ledger[i].executedMaps = msg.executedMaps || 0;
        ledger[i].status = "cancelled";
        ledger[i].source = "worker";
      }
    }
    Object.keys(fieldBatches).forEach(function (id) {
      var b = fieldBatches[id];
      if (b && !b.settled && b.jobId === jobId) {
        b.settled = true;
        delete fieldBatches[id];
      }
    });
  }

  /* Cancel in-flight field work without touching score jobs. Ledger entries
   * stay "pending" until their terminal message arrives (done, stopped or
   * error), which only fills counts or settles; a settled entry is never
   * reopened. */
  function cancelDispatchedFieldJobs() {
    Object.keys(fieldWorkerJobs).forEach(function (jobId) {
      var rec = fieldWorkerJobs[jobId];
      if (rec.cancelRequested) return;
      rec.cancelRequested = true;
      var b = fieldBatches[rec.batchId];
      if (b && !b.settled) b.superseded = true;
      if (worker) {
        try {
          worker.postMessage({ kind: "cancel", jobId: jobId });
        } catch (ignore) {
          /* worker already gone; failure path reruns */
        }
      }
    });
    Object.keys(fieldBatches).forEach(function (id) {
      var fb = fieldBatches[id];
      if (!fb || fb.settled) return;
      if (!fb.dispatched) {
        /* Scheduled but never dispatched: no worker job exists, so drop
         * the record here. */
        fb.settled = true;
        delete fieldBatches[id];
        var ne = ledgerEntry(id);
        if (ne && ne.status === "pending") ne.status = "cancelled";
      } else {
        fb.aborted = true;
      }
    });
  }

  function cancelPendingFieldWork() {
    if (fieldTimer) {
      clearTimeout(fieldTimer);
      fieldTimer = null;
    }
    fieldPending = null;
    fieldSeq++;
    cancelDispatchedFieldJobs();
  }

  function clearFieldPendingNote() {
    $("yy-explain-note").textContent = "";
    $("yy-explain-field").removeAttribute("aria-busy");
  }

  function requestFieldLayers(c, profile, table, choiceSet, layout) {
    if (fieldTimer) {
      clearTimeout(fieldTimer);
      fieldTimer = null;
    }
    fieldPending = null;
    cancelDispatchedFieldJobs();
    var gen = ++fieldSeq;
    var tag = c.id + "|" + profile;
    var glyphs = decodedGlyphs(c, profile);
    var shown = letterRuns(c, profile, layout);
    var frame = excerptFrameFor(c, profile, table, shown.runs);
    if (!layersVisible()) {
      /* Hidden: no extraction, no posts; the last valid ink stays and the
       * field canvas shows ink alone from the current runs and frame.
       * The master switch and the both-sublayers-off state share this
       * path; individual choices stay retained in state. */
      clearFieldPendingNote();
      paintHiddenFields(frame, shown.runs, profile);
      return;
    }
    var needCovers = {};
    shown.runs.forEach(function (run) {
      needCovers[run.cp] = true;
    });
    var lines = lastParse.lines;
    var shownAt = {};
    shown.runs.forEach(function (run) {
      shownAt[run.li + ":" + run.k] = run;
    });
    /* Dedupe by full computation identity: every occurrence renders, but
     * repeats share one map computation. */
    var seenMaps = {},
      mapNeeds = [],
      occurrences = 0;
    for (var q = 0; q < lines.length; q++) {
      for (var m = 0; m + 1 < lines[q].length; m++) {
        var a = lines[q][m],
          b = lines[q][m + 1];
        if (a === " " || b === " ") continue;
        var lr = shownAt[q + ":" + m],
          rr = shownAt[q + ":" + (m + 1)];
        if (!lr || !rr) continue;
        var key2 = a + b,
          ps = choiceSet.pairs[key2];
        if (!ps || ps.fallback || !ps.entry) continue;
        var ci = ps.steps.indexOf(ps.chosen);
        if (ci < 0 || !ps.entry.ok[ci]) continue;
        occurrences++;
        var mapKey = tag + "|" + key2 + "|" + ps.chosen + "|" + state.reach + "|" + state.falloff;
        if (seenMaps[mapKey]) continue;
        seenMaps[mapKey] = true;
        if (!contribAccount(mapKey)) {
          needCovers[String(a.charCodeAt(0))] = true;
          needCovers[String(b.charCodeAt(0))] = true;
          mapNeeds.push({ key: mapKey, pairKey: key2, left: a.charCodeAt(0), right: b.charCodeAt(0), step: ps.chosen });
        }
      }
    }
    var seenSlate = {},
      slateNeeds = [];
    shown.runs.forEach(function (run) {
      if (seenSlate[run.cp] || cachedSlate(tag, run.cp)) return;
      seenSlate[run.cp] = true;
      slateNeeds.push(run.cp);
    });
    /* Batch composition for diagnosis (unique computations, placed
     * occurrences, runs, fallbacks); read-only, never affects rendering. */
    window.__yyLastBatch = {
      occurrences: occurrences,
      mapNeeds: mapNeeds.length + countCachedMaps(tag, choiceSet, lines, shownAt),
      uniqueMaps: mapNeeds.length,
      slateNeeds: slateNeeds.length,
      pairs: Object.keys(choiceSet.pairs).length,
      runs: shown.runs.length,
      fallbackPairs: Object.keys(choiceSet.pairs).filter(function (k) {
        return choiceSet.pairs[k].fallback;
      }).length,
    };
    if (!slateNeeds.length && !mapNeeds.length) {
      /* All cached: paint synchronously from the same batch shape the async
       * path paints, so the painter sees case/profile/runs/frame/choice. */
      var syncBatch = {
        id: "b" + ++workerSeq,
        gen: gen,
        caseId: c.id,
        profile: profile,
        table: table,
        choiceSet: choiceSet,
        layout: layout,
        runs: shown.runs,
        frame: frame,
        settled: true,
        params: { reach: state.reach, falloff: state.falloff },
      };
      recordFieldBatch(syncBatch, 0, 0);
      var se = ledgerEntry(syncBatch.id);
      if (se) {
        se.status = "settled";
        se.source = "cache";
        se.painted = true;
      }
      paintFieldLayers(syncBatch);
      return;
    }
    /* Ink is already visible; fields stay visibly pending until the
     * matching generation paints. A stale batch never clears this note. */
    $("yy-explain-note").textContent = "Updating fields…";
    var covers = transferCovers(glyphs, Object.keys(needCovers));
    var batch = {
      id: "b" + ++workerSeq,
      gen: gen,
      settled: false,
      superseded: false,
      aborted: false,
      dispatched: false,
      jobId: null,
      executedSlates: 0,
      executedMaps: 0,
      fallbackRetried: false,
      caseId: c.id,
      profile: profile,
      table: table,
      choiceSet: choiceSet,
      layout: layout,
      runs: shown.runs,
      frame: frame,
      tag: tag,
      dataset: tableLabel(c, profile),
      captureSha: captureSha(c, profile),
      covers: covers,
      slateCps: slateNeeds,
      mapNeeds: mapNeeds,
      params: { reach: state.reach, falloff: state.falloff },
    };
    fieldBatches[batch.id] = batch;
    recordFieldBatch(batch, slateNeeds.length, mapNeeds.length);
    fieldPending = batch;
    fieldTimer = setTimeout(function () {
      fieldTimer = null;
      if (fieldPending !== batch) return;
      fieldPending = null;
      dispatchFieldBatch(batch);
    }, FIELD_DEBOUNCE_MS);
  }

  /* Cached (pair, step) entries for the shown occurrences: total unique
   * computations behind this view, posted plus already cached. */
  function countCachedMaps(tag, choiceSet, lines, shownAt) {
    var n = 0,
      seen = {};
    for (var q = 0; q < lines.length; q++) {
      for (var m = 0; m + 1 < lines[q].length; m++) {
        var a = lines[q][m],
          b = lines[q][m + 1];
        if (a === " " || b === " ") continue;
        if (!shownAt[q + ":" + m] || !shownAt[q + ":" + (m + 1)]) continue;
        var key2 = a + b,
          ps = choiceSet.pairs[key2];
        if (!ps || ps.fallback || !ps.entry) continue;
        var mapKey = tag + "|" + key2 + "|" + ps.chosen + "|" + state.reach + "|" + state.falloff;
        if (seen[mapKey]) continue;
        seen[mapKey] = true;
        if (contribCache[mapKey]) n++;
      }
    }
    return n;
  }

  function dropFieldBatch(batch) {
    if (!batch) return;
    batch.settled = true;
    delete fieldBatches[batch.id];
    var e = ledgerEntry(batch.id);
    if (e && e.status === "pending") e.status = "cancelled";
  }

  function dispatchFieldBatch(batch) {
    if (!batch || batch.settled || batch.aborted || batch.gen !== fieldSeq) {
      dropFieldBatch(batch);
      return;
    }
    batch.dispatched = true;
    var w = ensureWorker();
    if (w) {
      var jobId = "f" + ++workerSeq;
      batch.jobId = jobId;
      fieldWorkerJobs[jobId] = { batchId: batch.id, fallbackRetried: false };
      var e = ledgerEntry(batch.id);
      if (e) e.jobId = jobId;
      try {
        w.postMessage({
          kind: "fields",
          jobId: jobId,
          dataset: batch.dataset,
          captureSha: batch.captureSha,
          glyphs: batch.covers,
          params: engineParams(),
          codepoints: batch.slateCps.map(Number),
          maps: batch.mapNeeds,
        });
        return;
      } catch (ignore) {
        delete fieldWorkerJobs[jobId];
      }
    }
    runFieldFallback(batch);
  }

  /* Field canvas with ink alone for the current runs and frame: the
   * hidden paint. Display only; scores, maps and caches are untouched, so
   * zoom and opacity repaints over this paint stay zero-work. */
  function paintHiddenFields(frame, runs, profile) {
    if (!YYV) {
      clearFieldPendingNote();
      return;
    }
    YYV.drawExcerptField(
      $("yy-explain-field"),
      [],
      frame,
      runs,
      profile,
      [],
      layerAlphas(),
      state.zoom,
      GAINS,
      fieldOpts(),
    );
    lastPaint = { grids: [], frame: frame, runs: runs, profile: profile, layers: [] };
    clearFieldPendingNote();
  }

  /* Same-engine main-thread fallback for one field batch: the identical
   * WASM engine computes the same unique slate and map lists, one map per
   * chunk so controls stay responsive, and the batch settles exactly once
   * through the shared finish path. Stale batches still publish under
   * their exact cache identity but never paint. */
  function runFieldFallback(batch) {
    if (!batch || batch.settled || batch.gen !== fieldSeq) {
      dropFieldBatch(batch);
      return;
    }
    batch.dispatched = true;
    var eng = fallbackEngine(engineParams());
    if (!eng) {
      finishFieldBatch(batch.id, { error: "WASM unavailable in this browser" }, "main-thread");
      return;
    }
    var queue = [];
    batch.slateCps.forEach(function (cp) {
      queue.push({ kind: "slate", cp: String(cp) });
    });
    batch.mapNeeds.forEach(function (need) {
      queue.push({ kind: "map", need: need });
    });
    var i = 0;
    function loadRec(cp) {
      var rec = batch.covers[String(cp)];
      if (!rec) return null;
      eng.load_glyph(
        batch.dataset,
        batch.captureSha,
        Number(cp),
        rec.w,
        rec.h,
        rec.left,
        rec.top,
        new Float64Array(rec.cover),
      );
      return rec;
    }
    function chunk() {
      if (batch.settled || batch.aborted || batch.gen !== fieldSeq) {
        if (!batch.settled) {
          batch.settled = true;
          delete fieldBatches[batch.id];
          var ae = ledgerEntry(batch.id);
          if (ae) {
            if (ae.status === "pending") ae.status = "cancelled";
            ae.executedSlates = batch.executedSlates;
            ae.executedMaps = batch.executedMaps;
            ae.source = "main-thread";
          }
        }
        return;
      }
      var mapsThisChunk = 0;
      while (i < queue.length) {
        if (batch.aborted || batch.gen !== fieldSeq) {
          setTimeout(chunk, 0);
          return;
        }
        var item = queue[i++];
        try {
          if (item.kind === "slate") {
            var rec = loadRec(item.cp);
            if (!rec) {
              publishSlate(batch.tag, item.cp, null);
            } else {
              var arr = eng.glyph_component(batch.dataset, Number(item.cp), "slate", 0, 0);
              var note = JSON.parse(eng.last_component_note());
              publishSlate(batch.tag, item.cp, cropSlateMain(rec, arr, note.width, note.height));
              batch.executedSlates++;
            }
          } else {
            var need = item.need;
            loadRec(String(need.left));
            loadRec(String(need.right));
            var map = eng.contribution_map_local(
              batch.dataset,
              Number(need.left),
              Number(need.right),
              need.step,
              TAU,
              NORM_RADIUS,
              STRENGTH,
            );
            var geometry = JSON.parse(eng.last_map_geometry());
            var copy = new Float64Array(map.length);
            copy.set(map);
            publishContrib(need.key, {
              x0: geometry.origin[0],
              y0: geometry.origin[1],
              w: geometry.width,
              h: geometry.height,
              c: copy,
            });
            batch.executedMaps++;
          }
        } catch (e) {
          finishFieldBatch(batch.id, { error: String((e && e.message) || e) }, "main-thread");
          return;
        }
        if (item.kind === "map") {
          mapsThisChunk++;
          if (mapsThisChunk >= 1) break;
        }
      }
      if (i < queue.length) {
        setTimeout(chunk, 0);
        return;
      }
      finishFieldBatch(
        batch.id,
        { executedSlates: batch.executedSlates, executedMaps: batch.executedMaps },
        "main-thread",
      );
    }
    setTimeout(chunk, 0);
  }

  /* Glyph-local slate lattice on the main thread (mirrors the worker):
   * whole lattice with its origin, never frame-clipped; the painter
   * translates by each run's origin and clips to the display frame. */
  function cropSlateMain(rec, arr, w, h) {
    var pad = Math.round((w - rec.w + (h - rec.h)) / 4);
    var ox = Math.trunc(rec.left - pad),
      oy = Math.trunc(rec.top - pad);
    var out = new Float64Array(arr.length);
    out.set(arr);
    return { x0: ox, y0: oy, w: w, h: h, f: out };
  }

  /* Shared settle for one field batch, exactly once. Completed results
   * stay reusable under their exact cache identity even when a newer
   * generation has taken over the display; only the matching generation
   * paints or touches the pending note. */
  function finishFieldBatch(batchId, msg, source) {
    var b = fieldBatches[batchId];
    if (!b || b.settled) return;
    b.settled = true;
    delete fieldBatches[batchId];
    var e = ledgerEntry(batchId);
    if (msg && msg.error) {
      if (e) {
        e.status = "cancelled";
        e.source = source;
      }
      if (b.gen !== fieldSeq) return;
      $("yy-explain-note").textContent = "Fields could not be displayed. The spacing comparison is available below.";
      $("yy-explain-field").removeAttribute("aria-busy");
      return;
    }
    cacheFieldBatchMessage(b, msg);
    b.executedSlates = msg.executedSlates || b.executedSlates || 0;
    b.executedMaps = msg.executedMaps || b.executedMaps || 0;
    if (e) {
      e.executedSlates = b.executedSlates;
      e.executedMaps = b.executedMaps;
      e.source = source;
    }
    if (b.gen !== fieldSeq) {
      if (e) e.status = "cancelled";
      return;
    }
    if (e) {
      e.status = "settled";
      e.painted = true;
    }
    paintFieldLayers(b);
  }

  function cacheFieldBatchMessage(batch, msg) {
    if (!msg) return;
    if (msg.grids) {
      Object.keys(msg.grids).forEach(function (cp) {
        var g = msg.grids[cp];
        if (!g) {
          publishSlate(batch.tag, cp, null);
          return;
        }
        publishSlate(batch.tag, cp, { x0: g.x0, y0: g.y0, w: g.w, h: g.h, f: new Float64Array(g.f) });
      });
    }
    if (msg.maps) {
      Object.keys(msg.maps).forEach(function (key) {
        var m = msg.maps[key];
        publishContrib(key, { x0: m.x0, y0: m.y0, w: m.w, h: m.h, c: new Float64Array(m.c) });
      });
    }
  }

  /* ---- focused comparison ---- */

  function gapStats(c, profile, table, layout, choiceSet) {
    var edge = false,
      changed = false,
      fallback = 0,
      outside = 0;
    var reasons = {};
    layout.lines.forEach(function (line) {
      line.gaps.forEach(function (g) {
        if (g.space) return;
        if (g.chosen !== g.metric) changed = true;
        var p = choiceSet.pairs[g.pair];
        if (!p) return;
        if (p.fallback) {
          fallback++;
          reasons[p.reason || "unknown"] = true;
          return;
        }
        if (p.targetOutside) outside++;
        if (g.chosen === p.steps[0] || g.chosen === p.steps[p.steps.length - 1]) edge = true;
      });
    });
    return { edge: edge, changed: changed, fallback: fallback, outside: outside, reasons: Object.keys(reasons) };
  }

  function drawLines(canvas, glyphs, profile, words, lineOrigins, pitch, bounds, scale) {
    var ctx = canvas.getContext("2d");
    var off = LS.fitCanvas(canvas, bounds, scale);
    ctx.save();
    ctx.translate(off.dx, off.dy);
    ctx.fillStyle = "#fff";
    ctx.fillRect(
      bounds.x0 * scale,
      bounds.y0 * scale,
      (bounds.x1 - bounds.x0) * scale,
      (bounds.y1 - bounds.y0) * scale,
    );
    var count = 0;
    words.forEach(function (word, li) {
      var origins = lineOrigins[li];
      for (var k = 0; k < word.length; k++) {
        var g = glyphs[String(word.charCodeAt(k))];
        if (!g) continue;
        count += LS.drawCell(ctx, profile, g, origins[k], li * pitch, scale, false, null);
      }
    });
    ctx.restore();
    return count;
  }

  /* Pure placement plan for the ink canvases: per-line origins at the
   * choice set's steps plus the shared Source/Adjusted union bounds. Null
   * when a pair is still uncovered; rescoring never happens here. */
  function inkPlan(c, table, choiceSet, lines, glyphs) {
    var layout = liveOriginsFor(table, choiceSet, lines);
    if (layout.error) return null;
    var expOrigins = layout.lines.map(function (l) {
      return l.origins;
    });
    var capOrigins = capturedOriginsFor(table, lines);
    var b1 = LS.linesBounds(glyphs, lines, expOrigins, c.line_pitch);
    var b2 = LS.linesBounds(glyphs, lines, capOrigins, c.line_pitch);
    return {
      layout: layout,
      expOrigins: expOrigins,
      capOrigins: capOrigins,
      union: {
        x0: Math.min(b1.x0, b2.x0),
        x1: Math.max(b1.x1, b2.x1),
        y0: Math.min(b1.y0, b2.y0),
        y1: Math.max(b1.y1, b2.y1),
      },
    };
  }

  /* Zoom-only repaint: rescales the cached display at the new zoom without
   * rescoring pairs or rebuilding field layers. Placements re-derive from
   * the cached choice set; field windows, interaction layers and ink origins
   * are reused. Captions and notes describe the same text/setting and
   * stay untouched. False when the cached paint is not
   * reusable, so the caller falls back to a full render. */
  function repaintZoom(c, profile, table) {
    if (!lastPaint || !YYV || lastPaint.profile !== profile) return false;
    var glyphs = decodedGlyphs(c, profile);
    var lines = lastParse.lines;
    var plan = inkPlan(c, table, lastChoiceSet.set, lines, glyphs);
    if (!plan) return false;
    drawLines($("yy-original"), glyphs, profile, lines, plan.capOrigins, c.line_pitch, plan.union, state.zoom);
    drawLines($("yy-adjusted"), glyphs, profile, lines, plan.expOrigins, c.line_pitch, plan.union, state.zoom);
    YYV.drawExcerptField(
      $("yy-explain-field"),
      lastPaint.grids,
      lastPaint.frame,
      lastPaint.runs,
      lastPaint.profile,
      lastPaint.layers,
      layerAlphas(),
      state.zoom,
      GAINS,
      fieldOpts(),
    );
    if (window.YY_SUMMARY) window.YY_SUMMARY.zoom = state.zoom;
    return true;
  }

  function renderFocus(c, profile, table, choiceSet) {
    lastChoiceSet = { caseId: c.id, profile: profile, set: choiceSet, text: lastParse.text, layout: null };
    var glyphs = decodedGlyphs(c, profile);
    $("yy-focus-title").textContent =
      c.family_label + " " + c.size_px + " px" + (profile === "mono" ? " (black and white)" : " (grayscale)");
    var lines = lastParse.lines;
    var plan = inkPlan(c, table, choiceSet, lines, glyphs);
    if (!plan) {
      /* Coverage is ensured before painting, so this is unreachable in
       * normal use; never substitute other text for the requested view. */
      $("yy-sample-note").textContent = "Pair data is missing for this text; keeping the last valid view.";
      return;
    }
    var layout = plan.layout;
    lastChoiceSet.layout = layout;
    var zoom = state.zoom;
    /* Machine-side placement record for tests: the same origins the ink
     * paint uses, recorded synchronously so checks never wait on layers.
     * Layer fields go stale here and return with the field paint, so gates
     * on them still wait for fresh layers. */
    window.YY_SUMMARY = window.YY_SUMMARY || {};
    window.YY_SUMMARY.caseId = c.id;
    window.YY_SUMMARY.profile = profile;
    window.YY_SUMMARY.target = state.target;
    window.YY_SUMMARY.reach = state.reach;
    window.YY_SUMMARY.falloff = state.falloff;
    window.YY_SUMMARY.origins = layout.lines.map(function (l) {
      return l.origins.join(",");
    });
    delete window.YY_SUMMARY.pairLayers;
    delete window.YY_SUMMARY.coupling;
    var n0 = drawLines($("yy-original"), glyphs, profile, lines, plan.capOrigins, c.line_pitch, plan.union, zoom);
    var n1 = drawLines($("yy-adjusted"), glyphs, profile, lines, plan.expOrigins, c.line_pitch, plan.union, zoom);
    $("yy-original-cap").textContent = "Font's spacing";
    var note = $("yy-sample-note");
    if (!hasLetterGaps(lines)) {
      note.textContent = "Nothing to space — enter letters to compare placements.";
    } else {
      var stats = gapStats(c, profile, table, layout, choiceSet);
      var parts = [];
      if (!stats.changed) {
        parts.push("Font's spacing unchanged.");
      }
      if (stats.fallback) {
        parts.push(
          "Source retained for " +
            stats.fallback +
            " pair" +
            (stats.fallback === 1 ? "" : "s") +
            " (" +
            stats.reasons.join(", ") +
            ").",
        );
      }
      if (stats.outside) {
        parts.push(
          "Target outside measured range for " +
            stats.outside +
            " pair" +
            (stats.outside === 1 ? "" : "s") +
            "; showing closest.",
        );
      }
      note.textContent = parts.join(" ");
    }
    if (lastParse.capped) {
      note.textContent +=
        (note.textContent ? " " : "") + "Showing the first " + LS.MAX_LINES + " of " + lastParse.total + " lines.";
    }
    $("yy-adjusted-cap").textContent = "Adjusted spacing";
    requestFieldLayers(c, profile, table, choiceSet, layout);
  }

  /* ---- full-text fields: same setting and placements, no recompute ---- */

  /* Display frames stay fixed for each text and never follow the controls,
   * so field extent changes remain visible instead of rescaling away. */
  var frameCache = {};

  function frameCachePrune() {
    var keys = Object.keys(frameCache);
    while (keys.length > 12) delete frameCache[keys.shift()];
  }

  /* Ink-plane tight extent of one decoded cell. Null for blank cells. */
  function inkExtent(cell) {
    var x0 = Infinity,
      x1 = -Infinity,
      y0 = Infinity,
      y1 = -Infinity;
    var any = false;
    for (var row = 0; row < cell.h; row++) {
      for (var col = 0; col < cell.w; col++) {
        if (!(cell.cover[row * cell.w + col] > 0)) continue;
        any = true;
        var x = cell.left + col,
          y = cell.top + row;
        if (x < x0) x0 = x;
        if (x + 1 > x1) x1 = x + 1;
        if (y < y0) y0 = y;
        if (y + 1 > y1) y1 = y + 1;
      }
    }
    return any ? { x0: x0, x1: x1, y0: y0, y1: y1 } : null;
  }

  /* Display frame for the shown letters, from Source placement so the
   * frame stays fixed across control moves for the same text. Cached per
   * dataset and text; the cache stays bounded. */
  function excerptFrameFor(c, profile, table, runs) {
    var key = "ex|" + c.id + "|" + profile + "|" + lastParse.text;
    if (frameCache[key]) return frameCache[key];
    var capLines = capturedOriginsFor(table, lastParse.lines);
    var bounds = runs.map(function (run) {
      var ox = capLines[run.li][run.k];
      return [ox + run.ext.x0, ox + run.ext.x1, run.oy + run.ext.y0, run.oy + run.ext.y1];
    });
    var frame = YYV.frameForRuns(bounds, runs.length);
    frameCache[key] = frame;
    frameCachePrune();
    return frame;
  }

  /* Shown letter runs for the strip view: every non-space letter of the
   * shown lines with its origin and line offset. Shown lines already carry
   * the shared preview-text policy (explicit newlines, blank-line offsets,
   * explicit newlines only, at most 10 lines with a visible capped note). */
  function letterRuns(c, profile, layout) {
    var glyphs = decodedGlyphs(c, profile);
    var lines = lastParse.lines;
    var runs = [],
      total = 0;
    for (var li = 0; li < lines.length; li++) {
      var line = lines[li],
        origins = layout.lines[li].origins;
      var oy = li * c.line_pitch;
      for (var k = 0; k < line.length; k++) {
        var ch = line[k];
        if (ch === " ") continue;
        total++;
        var g = glyphs[String(ch.charCodeAt(0))];
        if (!g) continue;
        var ext = inkExtent(g);
        if (!ext) continue;
        runs.push({ cell: g, cp: String(ch.charCodeAt(0)), ox: origins[k], oy: oy, ext: ext, ch: ch, li: li, k: k });
      }
    }
    return { runs: runs, total: total };
  }

  /* Effective layer visibility: the master switch hides both layers
   * while retaining the individual choices; both sublayers off behaves
   * hidden and also retains the choices for re-show. */
  function layersVisible() {
    if (state.showFields === false) return false;
    return state.showLetter !== false || state.showContrib !== false;
  }

  /* Per-layer opacity for the renderer (display only). */
  function layerAlphas() {
    return { letter: state.letterAlpha, contrib: state.contribAlpha };
  }

  /* Current layer options for the renderer: hiding paints ink alone
   * from the same cached grids/layers, so the master checkbox, layer
   * checkboxes, zoom, opacity and late async paints all honor the
   * latest choice with zero rescore. */
  function fieldOpts() {
    return {
      showFields: state.showFields !== false,
      showLetter: state.showLetter !== false,
      showContrib: state.showContrib !== false,
    };
  }

  /* Display-only repaint: redraws the cached slate crops and
   * interaction layers with the active visibility and opacity. Never
   * rescores pairs or rebuilds maps, so text/params/profile/zoom keep
   * the user display choices. */
  function repaintDisplay() {
    if (!lastPaint || !YYV) {
      return;
    }
    YYV.drawExcerptField(
      $("yy-explain-field"),
      lastPaint.grids,
      lastPaint.frame,
      lastPaint.runs,
      lastPaint.profile,
      lastPaint.layers,
      layerAlphas(),
      state.zoom,
      GAINS,
      fieldOpts(),
    );
    if (window.YY_SUMMARY) {
      window.YY_SUMMARY.letterAlpha = state.letterAlpha;
      window.YY_SUMMARY.contribAlpha = state.contribAlpha;
      window.YY_SUMMARY.showLetter = state.showLetter !== false;
      window.YY_SUMMARY.showContrib = state.showContrib !== false;
    }
  }

  /* Paint the excerpt field view from cached slate crops and maps. The
   * batch carries the case/profile/table/choice/layout the layers were
   * requested for; stale batches never reach this function. */
  function paintFieldLayers(batch) {
    var c = findCase(batch.caseId);
    var profile = batch.profile;
    var table = window.YY_TABLES[tableLabel(c, profile)];
    if (!table) return;
    var note = $("yy-explain-note");
    if (!YYV) {
      note.textContent = "Explanation view unavailable.";
      $("yy-explain-field").removeAttribute("aria-busy");
      return;
    }
    var tag = c.id + "|" + profile;
    var grids = batch.runs.map(function (run) {
      return cachedSlate(tag, run.cp);
    });
    var glyphs = decodedGlyphs(c, profile);
    var shownAt = {};
    batch.runs.forEach(function (run) {
      shownAt[run.li + ":" + run.k] = run;
    });
    var layers = [],
      diag = [];
    var lines = lastParse.lines;
    for (var q = 0; q < lines.length; q++) {
      for (var m = 0; m + 1 < lines[q].length; m++) {
        var a = lines[q][m],
          b = lines[q][m + 1];
        if (a === " " || b === " ") continue;
        var lr = shownAt[q + ":" + m],
          rr = shownAt[q + ":" + (m + 1)];
        if (!lr || !rr) continue;
        var key2 = a + b,
          ps = batch.choiceSet.pairs[key2];
        if (!ps || ps.fallback || !ps.entry) {
          diag.push({
            pair: key2,
            metric: ps ? ps.metric : null,
            step: ps ? ps.chosen : null,
            score: null,
            mapSum: null,
            shown: false,
          });
          continue;
        }
        var ci = ps.steps.indexOf(ps.chosen);
        var score = ci >= 0 && ps.entry.ok[ci] ? ps.entry.gl[ci] : null;
        if (score === null || score === undefined) {
          diag.push({ pair: key2, metric: ps.metric, step: ps.chosen, score: null, mapSum: null, shown: false });
          continue;
        }
        var mapKey = tag + "|" + key2 + "|" + ps.chosen + "|" + batch.params.reach + "|" + batch.params.falloff;
        var layer = contribCache[mapKey];
        if (!layer) {
          diag.push({ pair: key2, metric: ps.metric, step: ps.chosen, score: score, mapSum: null, shown: false });
          continue;
        }
        layers.push({ x0: layer.x0 + lr.ox, y0: layer.y0 + lr.oy, w: layer.w, h: layer.h, c: layer.c });
        var sum = YYU.mapSum(layer.c);
        diag.push({ pair: key2, metric: ps.metric, step: ps.chosen, score: score, mapSum: sum, shown: true });
      }
    }
    YYV.drawExcerptField(
      $("yy-explain-field"),
      grids,
      batch.frame,
      batch.runs,
      profile,
      layers,
      layerAlphas(),
      state.zoom,
      GAINS,
      fieldOpts(),
    );
    lastPaint = { grids: grids, frame: batch.frame, runs: batch.runs, profile: profile, layers: layers };
    /* Live coupling diagnostics: exact per-pair sums beside the display. */
    var dlines = [
      "pair step score mapsum |diff|",
      "gain " +
        GAINS.contrib +
        " fixed \u00b7 pairs " +
        layers.length +
        " \u00b7 cache " +
        contribHits +
        "h/" +
        contribMisses +
        "m",
    ];
    diag.forEach(function (dd) {
      if (dd.score === null) {
        dlines.push(dd.pair + " n/a (fallback/invalid: not shown)");
      } else if (!dd.shown || dd.mapSum === null) {
        dlines.push(
          dd.pair +
            " " +
            (dd.step >= 0 ? "+" : "") +
            (dd.step - (dd.metric || 0)) +
            " score " +
            YYU.formatScore(dd.score) +
            " (no map: asynchronously scheduled)",
        );
      } else {
        var diff = Math.abs(dd.mapSum - dd.score);
        dlines.push(
          dd.pair +
            " " +
            (dd.step >= 0 ? "+" : "") +
            (dd.step - (dd.metric || 0)) +
            " " +
            YYU.formatScore(dd.score) +
            " " +
            YYU.formatScore(dd.mapSum) +
            " " +
            diff.toExponential(1) +
            (diff <= 1e-9 * Math.max(1, Math.abs(dd.score)) ? " ok" : " MISMATCH"),
        );
      }
    });
    note.textContent = "";
    $("yy-explain-field").removeAttribute("aria-busy");
    if (lastParse.capped) {
      note.textContent = "Showing the first " + LS.MAX_LINES + " of " + lastParse.total + " lines.";
    }
    window.YY_SUMMARY = {
      caseId: c.id,
      profile: profile,
      target: state.target,
      reach: state.reach,
      falloff: state.falloff,
      zoom: state.zoom,
      text: lastParse.text,
      shownText: lines.slice(),
      shownLetters: batch.runs.length,
      shownLines: lines.length,
      pairLayers: layers.length,
      contribHits: contribHits,
      contribMisses: contribMisses,
      scoreCalls: scoreCalls,
      origins:
        batch.layout && !batch.layout.error
          ? batch.layout.lines.map(function (l) {
              return l.origins.join(",");
            })
          : null,
      coupling: dlines.slice(),
      letterAlpha: state.letterAlpha,
      contribAlpha: state.contribAlpha,
      showLetter: state.showLetter !== false,
      showContrib: state.showContrib !== false,
    };
  }

  /* Reconcile the current view against cache and running work after a
   * valid parse. Same-geometry needs hit cache or join the running
   * owner: nothing restarts. Only genuinely missing pairs dispatch, and
   * only unneeded live work is trimmed at the next chunk boundary.
   * Detached generations never paint; their completed curves still cache
   * under the original computation identity. */
  function reconcile(c, profile, table, parse, gen) {
    var names = LS.textPairs(parse.lines);
    var settingKey = computedKey(c, profile);
    /* Coverage first: shipped pairs answer at the default geometry and
     * computed-cached pairs answer anywhere, so only genuinely missing
     * pairs enter the running-work registry. The verified read also
     * refreshes recency, keeping the working set promoted. */
    var fast = fastAndCurrent(table);
    var missingNames = names.filter(function (name) {
      if (fast && table.pairs[name]) return false;
      return !cachedPairRecord(settingKey, name, metricFor(table, name));
    });
    var needs = missingItems(table, missingNames).map(function (item) {
      return {
        key: pairIdentityKey(settingKey, item.key, item.metric),
        name: item.key,
        metric: item.metric,
        item: item,
      };
    });
    genNeeds[gen] = { c: c, profile: profile, table: table, keys: needs, painted: false };
    /* Need before detaching: keys the new view shares with running work
     * join under the new generation instead of blocking behind a stop
     * the view itself just armed. Only keys no live view needs are
     * abandoned below, and the same key still never runs twice. */
    refreshPairPins(c, profile, table, names);
    clearTextError();
    var byKey = {};
    needs.forEach(function (n) {
      byKey[n.key] = n;
    });
    var res = flightNeed(
      flight,
      gen,
      needs.map(function (n) {
        return n.key;
      }),
      function (key) {
        var n = byKey[key];
        return !!cachedPairRecord(settingKey, n.name, n.metric);
      },
    );
    /* Detach superseded generations now: older views never paint, and
     * keys left with zero subscribers arm a bounded stop. Joined keys
     * keep the new subscriber, so shared work is never cancelled. */
    Object.keys(genNeeds).forEach(function (g) {
      if (Number(g) !== gen) {
        flightDetach(flight, Number(g));
        delete genNeeds[g];
      }
    });
    trimLiveCalls(gen);
    var started = res.started
      ? res.started.keys.map(function (k) {
          return byKey[k];
        })
      : [];
    if (started.length) {
      setScoreBusy();
      dispatchMissing(c, profile, table, started, gen, res.started.callId);
      return;
    }
    settleCheck(gen);
  }

  /* View-centric settle: paint once the current view's full pair set is
   * cached; dispatch genuinely missing work otherwise. Blocked keys wait
   * for their stop acknowledgement; a failed validation round counts
   * toward the bounded retry gate, and two strikes end in an honest
   * error instead of a resolve loop. */
  function settleCheck(gen) {
    if (gen !== renderSeq) return;
    var need = genNeeds[gen];
    if (!need || need.painted) return;
    var settingKey = computedKey(need.c, need.profile);
    var missing = [],
      blocked = false;
    need.keys.forEach(function (n) {
      if (cachedPairRecord(settingKey, n.name, n.metric)) return;
      var r = flight.running.get(n.key);
      /* Running keys wait like stopping ones: a live execution may still
       * deliver them, so the view stays busy instead of painting short. */
      if (r) {
        blocked = true;
        return;
      }
      missing.push(n);
    });
    if (missing.length) {
      var exhausted = missing.filter(function (n) {
        return scoreFailExhausted(n.key);
      });
      if (exhausted.length) {
        showEngineError("pair scoring failed twice; showing last valid view.");
        return;
      }
      setScoreBusy();
      dispatchMissing(need.c, need.profile, need.table, missing, gen, null);
      return;
    }
    if (blocked) return;
    if (paintCurrentView(need.c, need.profile, need.table, gen)) {
      need.painted = true;
    }
  }

  /* Paint the current view from fully cached curves. Returns false (no
   * paint, no busy change) when the draft moved on mid-flight. */
  function paintCurrentView(c, profile, table, gen) {
    var parse = lastParse;
    if (!parse || !parse.ok || parse.text !== displayText(c)) return false;
    var choiceSet = buildChoiceSet(c, profile, table, LS.textPairs(parse.lines));
    if (!choiceSet) {
      showEngineError("complete pair set unavailable; showing last valid view.");
      return false;
    }
    renderFocus(c, profile, table, choiceSet);
    return true;
  }

  /* Invalid drafts never paint: the canvases keep their last valid view,
   * and both notes say so. The draft stays in the field for editing.
   * Pins release; running work continues into the cache (data ready is
   * never deleted) but can never paint the invalid draft. */
  function renderInvalid(c, profile, parse) {
    cancelPendingFieldWork();
    /* Invalid text releases the working-set pins; the last valid view
     * stays painted but is evictable under budget pressure. */
    clearPairPins();
    renderSeq++;
    $("yy-text-e").textContent = "Preview text not applied: " + textErrorMessage(c, profile, parse);
    $("yy-sample-note").textContent = "Showing the last valid text — fix the preview text to update.";
    /* No field update is coming for the rejected draft: clear any pending
     * busy so the last valid view does not look stale forever. */
    $("yy-explain-note").textContent = "";
    $("yy-explain-field").removeAttribute("aria-busy");
  }

  function clearTextError() {
    $("yy-text-e").textContent = "";
  }

  /* ---- sample selection ---- */

  function sampleLabel(c) {
    return c.family_label + " " + c.size_px + " px";
  }

  function refreshSampleOptions() {
    var sel = $("yy-sample");
    if (!sel.options.length) {
      cases().forEach(function (c) {
        var opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = sampleLabel(c);
        sel.appendChild(opt);
      });
    }
    sel.value = state.caseId;
  }

  /* ---- render requests: fast path sync, compute debounced ---- */

  function requestRender(immediate) {
    refreshControls(false);
    refreshSampleOptions();
    var c = findCase(state.caseId);
    var seq = ++focusSeq;
    var myRender = ++renderSeq;
    if (computeTimer) {
      clearTimeout(computeTimer);
      computeTimer = null;
    }
    /* No blind cancellation: reconcile joins or trims running work once
     * the table is ready. Field work still cancels per view. */
    cancelPendingFieldWork();
    ensureTable(c, state.profile, function (table) {
      if (seq !== focusSeq) return;
      resolveSetting(c, state.profile, table, myRender, immediate);
    });
    if (!window.YY_TABLES[tableLabel(c, state.profile)] && !lastChoiceSet) {
      $("yy-sample-note").textContent = "Loading sample data.";
    }
  }

  function resolveSetting(c, profile, table, myRender, immediate) {
    if (myRender !== renderSeq) return;
    var parse = parsePreview(c, profile);
    lastParse = parse;
    if (!parse.ok) {
      renderInvalid(c, profile, parse);
      return;
    }
    /* Immediate visible busy: the compare-box line stays hidden while
     * collapsed, so mark the field preview updating here, before the
     * debounce and the worker scoring. Cleared only by a same-or-newer
     * generation paint or an honest error. */
    function go() {
      if (myRender !== renderSeq) return;
      reconcile(c, profile, table, parse, myRender);
    }
    if (immediate) {
      go();
    } else {
      $("yy-sample-note").textContent = "Updating spacing…";
      computeTimer = setTimeout(function () {
        computeTimer = null;
        go();
      }, 120);
    }
  }

  /* ---- controls ---- */

  function setSliderAttributes() {
    Object.keys(SPECS).forEach(function (key) {
      var grid = GRID[key];
      var slider = $(SPECS[key].slider);
      slider.min = String(grid[0]);
      slider.max = String(grid[grid.length - 1]);
      slider.step = String(grid[1] - grid[0]);
    });
  }

  function sliderChanged(key) {
    var grid = GRID[key];
    var slider = $(SPECS[key].slider);
    var raw = parseFloat(slider.value);
    var step = grid[1] - grid[0];
    var idx = Math.max(0, Math.min(grid.length - 1, Math.round((raw - grid[0]) / step)));
    state[key] = grid[idx];
    $(SPECS[key].num).value = fmtValue(key, state[key]);
    $(SPECS[key].num).setAttribute("aria-invalid", "false");
    $(SPECS[key].err).textContent = "";
    requestRender(false);
  }

  function entryCommitted(key) {
    var spec = SPECS[key];
    var parsed = parseEntry(key, $(spec.num).value);
    if (!parsed.ok) {
      showEntryError(key, parsed.message);
      return;
    }
    state[key] = parsed.value;
    requestRender(true);
    refreshControl(key, true);
  }

  function initControls() {
    setSliderAttributes();
    var profile = $("yy-profile");
    ["mono", "gray"].forEach(function (p) {
      var label = el("label", p === "mono" ? "Black and white" : "Grayscale");
      var input = document.createElement("input");
      input.type = "radio";
      input.name = "profile";
      input.value = p;
      if (p === state.profile) input.checked = true;
      input.addEventListener("change", function () {
        state.profile = p;
        requestRender(true);
      });
      label.insertBefore(input, label.firstChild);
      profile.appendChild(label);
    });
    var zoomSel = $("yy-zoom");
    [
      ["1", "Native size"],
      ["2", "2x"],
      ["4", "4x"],
    ].forEach(function (opt) {
      var o = document.createElement("option");
      o.value = opt[0];
      o.textContent = opt[1];
      zoomSel.appendChild(o);
    });
    zoomSel.value = "1";
    zoomSel.addEventListener("change", function () {
      state.zoom = Number(zoomSel.value);
      var c = findCase(state.caseId);
      var table = window.YY_TABLES[tableLabel(c, state.profile)] || null;
      if (
        table &&
        lastChoiceSet &&
        lastChoiceSet.caseId === state.caseId &&
        lastChoiceSet.profile === state.profile &&
        lastParse &&
        lastParse.ok &&
        lastChoiceSet.text === displayText(c) &&
        repaintZoom(c, state.profile, table)
      ) {
        /* Zoom rescales the cached display; no rescore or map rebuild. */
      } else {
        requestRender(true);
      }
    });
    Object.keys(SPECS).forEach(function (key) {
      var spec = SPECS[key];
      $(spec.slider).addEventListener("input", function () {
        sliderChanged(key);
      });
      $(spec.num).addEventListener("change", function () {
        entryCommitted(key);
      });
    });
    refreshSampleOptions();
    var textArea = $("yy-text");
    textArea.value = findCase(state.caseId).text;
    textArea.addEventListener("input", function () {
      /* The draft is preserved verbatim for editing; validation paints
       * nothing until the text parses against the dataset repertoire. */
      state.textOverride = textArea.value;
      state.textDirty = true;
      $("yy-text-restore").hidden = false;
      if (textTimer) {
        clearTimeout(textTimer);
        textTimer = null;
      }
      textTimer = setTimeout(function () {
        textTimer = null;
        requestRender(true);
      }, 250);
    });
    $("yy-text-restore").addEventListener("click", function () {
      state.textOverride = null;
      state.textDirty = false;
      textArea.value = findCase(state.caseId).text;
      $("yy-text-restore").hidden = true;
      requestRender(true);
    });
    $("yy-sample").addEventListener("change", function (e) {
      var valid = cases().some(function (c) {
        return c.id === e.target.value;
      });
      if (!valid) {
        e.target.value = state.caseId;
        return;
      }
      state.caseId = e.target.value;
      if (!state.textDirty) {
        /* No deliberate edit: the field follows the new sample. */
        state.textOverride = null;
        textArea.value = findCase(state.caseId).text;
        $("yy-text-restore").hidden = true;
      }
      requestRender(true);
    });
    $("yy-reset").addEventListener("click", function () {
      state.target = DEF.target;
      state.reach = DEF.reach;
      state.falloff = DEF.falloff;
      refreshControls(true);
      requestRender(true);
    });
    /* Layer display: the master checkbox hides both layers while
     * retaining the individual choices; each layer checkbox toggles one
     * fixed ramp; opacity sliders rescale one layer. All are cached
     * repaints with zero score/map/slate work: field batches run only
     * when the caches cannot cover the current view, never for a pure
     * repaint. A late batch can never resurrect hidden layers: only the
     * matching generation paints, and painting honors the live choices.
     * Spacing resets leave this alone. */
    $("yy-show-fields").addEventListener("change", function (e) {
      state.showFields = !!e.target.checked;
      refreshDisplay();
    });
    $("yy-show-letter").addEventListener("change", function (e) {
      state.showLetter = !!e.target.checked;
      refreshDisplay();
    });
    $("yy-show-contrib").addEventListener("change", function (e) {
      state.showContrib = !!e.target.checked;
      refreshDisplay();
    });
    bindAlpha("yy-letter-alpha", "yy-letter-alpha-v", "letterAlpha");
    bindAlpha("yy-contrib-alpha", "yy-contrib-alpha-v", "contribAlpha");
    syncAlphaUI("letterAlpha");
    syncAlphaUI("contribAlpha");
    refreshControls(true);
  }

  /* Cached display refresh for the layer controls: repaints from the
   * warm caches with zero engine work whenever they cover the current
   * choice set, and fetches only missing field batches (never scores)
   * when they cannot. Falls back to a full render without valid cached
   * choices. */
  function currentDisplayRequest() {
    if (!lastChoiceSet || !lastParse || !lastParse.ok) return null;
    var c = findCase(state.caseId);
    if (lastChoiceSet.caseId !== state.caseId || lastChoiceSet.profile !== state.profile) return null;
    if (!lastChoiceSet.layout || lastChoiceSet.text !== displayText(c)) return null;
    var table = window.YY_TABLES[tableLabel(c, state.profile)];
    if (!table) return null;
    return { c: c, table: table };
  }

  function refreshDisplay() {
    var req = currentDisplayRequest();
    if (!req) {
      requestRender(true);
      return;
    }
    if (!layersVisible()) {
      cancelPendingFieldWork();
      clearFieldPendingNote();
      if (lastPaint) paintHiddenFields(lastPaint.frame, lastPaint.runs, lastPaint.profile);
      return;
    }
    if (lastPaint && lastPaint.profile === state.profile && lastPaint.grids.length) {
      repaintDisplay();
      return;
    }
    requestFieldLayers(req.c, state.profile, req.table, lastChoiceSet.set, lastChoiceSet.layout);
  }

  /* Opacity readout: slider moves land exactly on whole percent. */
  function fmtAlphaPct(a) {
    return String(parseFloat((a * 100).toFixed(6))) + "%";
  }

  var ALPHA_IDS = {
    letterAlpha: { slider: "yy-letter-alpha", out: "yy-letter-alpha-v" },
    contribAlpha: { slider: "yy-contrib-alpha", out: "yy-contrib-alpha-v" },
  };

  function syncAlphaUI(key) {
    var ids = ALPHA_IDS[key];
    var slider = $(ids.slider);
    var out = $(ids.out);
    var a = state[key];
    slider.value = String(Math.round(a * 100));
    out.textContent = fmtAlphaPct(a);
    slider.setAttribute("aria-valuetext", fmtAlphaPct(a));
  }

  /* Opacity sliders rescale one fixed ramp (0-100%, step 1%).
   * Display only: one cached repaint, no score or map rebuild. */
  function bindAlpha(sliderId, outId, key) {
    $(sliderId).addEventListener("input", function (e) {
      state[key] = Number(e.target.value) / 100;
      syncAlphaUI(key);
      refreshDisplay();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initControls();
      requestRender(true);
    });
  } else {
    initControls();
    requestRender(true);
  }
})();
