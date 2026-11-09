// cspell:words yinyangfit
/* Engine-record shaping for the Class-L staged spacing page.
 *
 * The WASM worker and the shipped tables carry the same per-step
 * Class-L records; this module shapes raw engine step arrays into the
 * entry form the page derives choices from, with no scoring of its own.
 * Entry shape (shared by tables and worker results):
 *   { ok:[bool], gl:[gl|null], both:[n], abst:[bool],
 *     why:[reason|null], areason:[abstain_reason|null],
 *     weak:[share|null], skip:[n], short:[n], bound:[honest|null],
 *     fa:[n], co:[n] }
 * `gl` holds the normalized local interaction score per step
 * (dimensionless Class-L units, never G2 units, never a 0..128 bound);
 * `both` counts energy-eligible scored pair pixels; `abst` marks
 * abstained steps with the engine abstain reason kept separately in
 * `areason`. G2 fields (raw sums, floor shares) are never carried here:
 * staged tables reject G2 reuse.
 */
(function (root) {
  "use strict";

  function shapeEntry(steps) {
    var entry = {
      ok: [],
      gl: [],
      both: [],
      abst: [],
      why: [],
      areason: [],
      weak: [],
      skip: [],
      short: [],
      bound: [],
      fa: [],
      co: [],
    };
    steps.forEach(function (s) {
      entry.ok.push(!!s.valid);
      entry.gl.push(s.valid ? s.gl : null);
      entry.both.push(s.both_supported_pairpx || 0);
      entry.abst.push(!!s.abstain);
      entry.why.push(s.valid ? null : s.reason || "invalid");
      entry.areason.push(s.abstain_reason || null);
      entry.weak.push(s.valid ? (s.weak_normalized_share ?? null) : null);
      entry.skip.push(s.skipped_nonpositive || 0);
      entry.short.push(s.conditioning_shortfall || 0);
      entry.bound.push(s.valid ? (s.honest_bound ?? null) : null);
      entry.fa.push(s.faces || 0);
      entry.co.push(s.corners || 0);
    });
    return entry;
  }

  /* Exact per-pixel Class-L summands of one contribution map; the engine
   * guarantees sum == the chosen step gl. Callers compare the two as a
   * live display-vs-score check (diagnostics only). */
  function mapSum(values) {
    var sum = 0;
    for (var i = 0; i < values.length; i++) sum += values[i];
    return sum;
  }

  /* Display formatting for Class-L scores: fixed decimals, never
   * rescaled, never mapped onto the retired G2 0..128 bound. */
  function formatScore(value) {
    if (value === null || value === undefined || !isFinite(value)) return "n/a";
    return value.toFixed(4);
  }

  var api = { shapeEntry: shapeEntry, mapSum: mapSum, formatScore: formatScore };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.YYCoupling = api;
  }
})(typeof self !== "undefined" ? self : this);
