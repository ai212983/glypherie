# Round-curve extremity pixel tips: primary-source research

<!-- cspell:words sopfbsc André Gürtler ptgogf sopfbsp Infoscience rasterizers ftraster gridfitting -->

Research-only report. No renderer change is proposed or implemented here.
Evidence records: `out/diagnostics/curve-extremity-tip-research/` (`SOURCES.md`,
`web-excerpts.md`, rendered Hersch95 Figure 5 crops). Prior Muse findings in
`out/diagnostics/roboto-flex-48-arc-tops/` were treated as untrusted context; every
decisive claim below was re-checked against the cited primary original this session.
The case font hash was re-verified this session
(`fonts/RobotoFlex.ttf` SHA-256 `9b523f7d82...c810c8281`).

Headline, corrected: the phase origin is recovered. Hersch95 Figure 5's caption
defines phase as distances from pixel centers, and both cited windows exclude phase 0. Our fitted round apex at y = 22.5 sits exactly on a pixel-center row (phase 0),
so under the sourced rule our apex placement is the explicitly excluded case — the
prior report's "apex at 8/16 sits inside both windows" reading used an edge origin
the source does not use and is retired. The literature now gives a concrete sourced
anti-spur placement for all four sides; the exact window choice and displacement
direction under our scanner remain for the empirical sweep in §6.

## 1. What the artifact is called, and that it is recognized (Q1)

Primary sources name this exact defect class and treat it as a fitting problem even
when scan conversion itself is conforming:

- Microsoft, "TrueType hinting": "Hinting can be particularly useful in helping the
  avoidance of _individual pixel spurs_ and _flat runs_" — "local aesthetics",
  distinct from global consistency. Conforming scan conversion producing a spur is
  still a defect to be hinted away.
- Hobby 1993 §2: a curve boundary yields a long "flat spot" on one side and a
  "pimple" on the other (Fig. 10); "Font designers know that it is desirable to
  avoid both pimples and flat spots when scan converting curved outlines."
  Cause diagnosed in §3: tangent points near the _middle_ of a pixel square rather
  than near an edge.
- Hersch 1993 §5 / Hersch95 "Displacement": "keeping the phase of the vertical or
  horizontal extremity of arcs within a given range" — "The phase range influences
  the flatness of the produced discrete arc" (Fig. 20 / Fig. 5).
- Hu thesis §4.5.2.2 (printed p. 94): keeping "the phase of the extremum of a
  round part in a certain range, for example between 1/16 to 9/16 [Hersch95], will
  prevent a 'single pixel' or a flat 'long run' at the extrema." Scope is
  loop and half-loop components; connecting sweeps are explicitly handled
  differently (elastic response to connected parts, after [Bétrisey89]).
- Microsoft, "Fixing rasterization issues": after correct width/position linking,
  "we may be left with knees or elbows and other unfortunate pixel patterns" —
  residual local shape defects are expected and handled with size-dependent control
  values, not re-linking.
- FontLab 9 manual: "At a small pixel size, an overshoot can instead become an
  unwanted extra pixel."

Our 48 px arc tips (narrow 1-pixel-tall crown protrusions on round tops, including a
FreeType dropout-off `o` case) sit squarely in the "spur/pimple" member of this
class, not the "flat run" member. Scanner parity (prior 27/54-capture result) proves
compatibility only; every source above treats parity-compatible spurs as hinting
defects, so parity cannot close the case. Prior conclusions to the contrary should
be retired.

## 2. Established remedies (Q2)

| Remedy                                               | Source                                                                                                                                                             | Mechanism                                                                                                                                                      |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bowl-extremity phase window, origin at pixel centers | Hersch95 "Displacement"/Fig. 5; Hersch 1993 §5, Fig. 20; Hu thesis §4.5.2.2 cites `[Hersch95]`                                                                     | keep extremity phase (distance from pixel center) in an allowed range; range position selects crown flatness                                                   |
| Tangent-on-boundary                                  | Hobby 1993 §3.3                                                                                                                                                    | curves through vertical/horizontal render best with the tangent line on pixel boundaries; X/Y-symmetric rule                                                   |
| Sharp-extremum centering                             | Hobby 1993 §3.3, eq. 8, Fig. 22                                                                                                                                    | side extreme with small transverse extent: cross-coordinate to pixel-row middle (`I+0.5`)                                                                      |
| Corner pixel-center placement                        | Hobby 1993 §3.3, eq. 9, Fig. 23                                                                                                                                    | simultaneous x/y extremum: medial axis through a pixel center, outward offset max 1/2 px                                                                       |
| Overshoot suppression by zone                        | Type 1 BlueValues/BlueScale/BlueShift (Hersch §9); FreeType blue zones (Turner/Lemberg §2); FontLab zones; Hersch 1993 §5 discrete optical correction [Bétrisey89] | snap zone edges to one row at small sizes; source overshoot retained, rendered interpretation changed                                                          |
| Paired-width + ratio control                         | Shamir 2003 §§3.3-3.6: anchor/Dist/Ratio constraints                                                                                                               | Dist keeps stroke/counter widths (rounded); Ratio positions points between extremes; arc-stem joints constrained; uniform round heights (o-height vs x-height) |
| Stem/advance consistency                             | Turner/Lemberg §2; MS tutorial (O strategy)                                                                                                                        | top/bottom curves mutually consistent; left/right curves mutually consistent; advance from fitted side bearings                                                |
| Dropout rescue (separate)                            | Hersch §7; TrueType dropout; FreeType smart/simple dropout + `include_stubs` (`crates/generator/API.md`)                                                           | inserts pixels where strokes fall between samples; can _create_ tip-like pixels — a distinct mechanism from phase aesthetics                                   |

Only the first row is a _phase-window_ remedy; the rest are complementary, and the
last row works in the opposite direction (adds pixels). Conflating dropout rescue
with phase placement is the main category error to avoid: prior evidence shows
stub/dropout involvement in most tips but a dropout-independent `o` tip, so both
mechanisms need separate controls.

## 3. The Hu/Hersch numeric interval and its convention (Q3) — corrected

### 3.1 What is verified in the originals

- Hu thesis (`sopfbsc.pdf`, 154 pages, SHA-256 `f9427be9...ceb2cae98`),
  printed p. 94 (PDF p. 100), §4.5.2.2 "Grid-fitting component-based characters
  without hints": "Keeping the phase of the extremum of a round part in a certain
  range, for example between 1/16 to 9/16 [Hersch95], will prevent a 'single
  pixel' or a flat 'long run' at the extrema."
- Bibliography, printed p. 119 (PDF p. 124): `[Hersch95]` is Roger D. Hersch,
  Claude Bétrisey, Justin Bur, André Gürtler, "Perceptually Tuned Generation of
  Grayscale Fonts", IEEE Computer Graphics and Applications 15(6), November 1995,
  pp. 78–89.
- Author-hosted original (`ptgogf_95.pdf`, 14 pages, SHA-256
  `29bc6099...87f50b7d7fd`), printed p. 81 (PDF p. 4), "Displacement" section
  (a bilevel-rasterization section: "In bilevel rasterization, the software
  controls the bowls and curved character parts by keeping the phase of the
  vertical or horizontal extremity of arcs within a given range") plus Figure 5
  caption, verified from the rendered page this session: "The flatness of an arc
  in the 'o' character is controlled by altering the phase range — the range
  between two pixel centers where the continuous contour is allowed to pass. The
  white dots in the center of the squares are the centers of the pixels; the other
  dots represent the trajectory of the phase-controlled outline. In (a), the phase
  range (distances from the pixel center) is 1/16 to 9/16. In (b), it is 3/16 to
  11/16."
- The earlier `sopfbsp.pdf` URL was a misspelling (final p for final c); the
  correct `sopfbsc.pdf` opened successfully. The EPFL Infoscience record for the
  thesis remains access-restricted ("Request a copy"), but the author-hosted LSP
  copy above is openly accessible — an access-limited catalog record must not be
  mistaken for an unavailable document.

### 3.2 What Figure 5 actually shows

Rendered PDF p. 4 viewed this session:

- Panel (a), 1/16–9/16: crown callout 4 full pixels; the bowl carries a
  single-pixel protrusion below the bottom row (and a narrower crown on top) —
  the tip-like outcome.
- Panel (b), 3/16–11/16: crown callout 5 full pixels; flat full-width bottom row —
  the clean outcome.

So in Hersch95's own rendering the 1/16–9/16 window co-occurs with the MORE
tip-like crown, while Hu cites 1/16–9/16 as the example window that _prevents_
single pixels. Both windows are 8/16 (half-pixel) wide and both exclude phase 0;
the figure's lesson is that the window _selects_ flatness. The exact "good"
window differs between Hu's example and the flatter Fig. 5(b) — this is a genuine
unresolved calibration point (different rasterizers: Hu's component synthesizer
vs Hersch's renderer), not a contradiction that voids the mechanism. It is
decided by the §6 sweep under our scanner, not by re-reading.

### 3.3 Convention mapping for our case

Phase origin is now explicit: distances from the pixel center, measured along the
segment between two adjacent pixel centers where the contour passes. Our scanner
(pinned FreeType 2.15.0 mono; `crates/generator/API.md`: nonzero-winding
center fill; vendored `ftraster.c` `SCALED` shifts the grid to pixel centers)
places pixel centers at half-integer outline coords — the same grid-line
convention Hobby §3.3 assumes. Our fitted round apex at y = 22.5 is therefore
exactly ON a pixel-center row: phase 0, outside both `[1/16, 9/16]` and
`[3/16, 11/16]`. Hobby's diagnosis ("tangent near the middle of a pixel square")
predicts exactly this sensitivity. Minimum displacement to enter a sourced window
is 1/16 px (window a) or 3/16 px (window b); which window and which sign per side
is the calibration the sweep must settle. The prior edge-origin reading is
retired: do not adopt raw fractions across conventions.

### 3.4 Top/bottom, sides, inside/outside

- Top and bottom move together: Fig. 5 shows both crowns of the same "o" change
  between panels — paired-extremity treatment, consistent with MS's O strategy
  (top/bottom curves controlled to match) and Turner/Lemberg's blue-edge fitting.
- Sides by rotation: the rule as stated covers "vertical or horizontal"
  extremities — one axis-symmetric statement. Hobby §3.3 likewise defines the
  horizontal rule "by just using Y in place of X". A correct model states the
  window once per axis and maps top/bottom by Y-reflection, sides by 90°
  rotation — never a separately tuned per-side constant.
- The rasterizer is NOT symmetric, so a symmetric model still needs per-axis
  validation: Hersch §7 applies dropout vertically by rotating the outline 90°;
  our vendored `ftraster.c` carries separate `IS_TOP_OVERSHOOT` /
  `IS_BOTTOM_OVERSHOOT` macros and an explicit comment that "the vertical sweep
  mishandles horizontal lines through pixel centers" — precisely our apex
  condition. Validation must cover all four sides plus inner boundaries.
- Inner follows outer with weight preserved: Hersch95 printed p. 84–85
  (PDF pp. 7–8), Figure 16 — the exterior arc boundary is placed to share the
  phase of the o/O optical-correction reference, while weight control enforces a
  minimum distance between exterior and interior arc boundaries at the extrema.
  The grayscale gray-value matching does NOT transfer to Mono; the structural
  part does: move inner with outer, preserve stem weight. Endpoints (open vs
  closed interval ends) are unspecified in every source read.

## 4. Tip rescue vs terminal/dropout rescue; overshoot coexistence (Q4)

- Isolated round tip (phase/center-fill marginal coverage at a smooth apex) vs
  genuine sharp terminal vs dropout rescue (sub-pixel span re-insertion) are three
  different mechanisms with different signatures: phase tips move continuously
  with subpixel placement and vanish at boundary-tangent placements; dropout/stub
  pixels appear/disappear discretely with dropout/stub policy at unchanged
  outlines (as observed for most of our glyphs); the dropout-off `o` tip implicates
  the third mechanism, center-fill boundary sampling, consistent with the vendored
  sweep-mishandling comment.
- Established practice preserves the round-vs-flat height ordering while
  suppressing its rendering, in bilevel as well as grayscale: Hersch 1993 §5
  states bowls "can be further constrained to produce a discrete optical
  correction from a given size [Bétrisey89]" with "separate control ... for
  optical correction on baseline, x-height line and caps line"; Type 1
  BlueScale/BlueShift, FreeType blue zones, and the FontLab zone text ("The
  source overshoot remains part of the drawing; gridfitting changes its rendered
  interpretation") say the same. A phase window is the same kind of operation —
  placement of the fitted extremity, not deletion of design overshoot — so it
  coexists with optical overshoot by construction, provided the window is shared
  across the zone (paired round tops/bottoms move together, stroke weight and
  tangents preserved, native axis ownership respected).
- It must NOT be implemented as overshoot collapse (blanket removal of subpixel
  overshoot) or per-glyph exception: the prior passes correctly rejected those,
  and nothing here revives them.

## 5. Prescribed vs project adaptation; revised conclusion (Q5)

Established by sources: artifact class and its cause (tangent-near-center);
phase-window remedy with pixel-center origin for smooth arc extremities in
bilevel rasterization; zone/discrete optical-correction overshoot handling with
preserved source heights; paired top/bottom and left/right consistency; dropout
as a separate pixel-adding mechanism; axis-symmetric statement with
rasterizer-asymmetric realization.

Conclusion: the literature now gives a concrete sourced anti-spur method for all
four sides — keep each smooth-arc extremum's phase (distance from the nearest
pixel-center row/column) inside an ~8/16-px-wide window strictly off pixel
center, stated once per axis, top/bottom paired, sides by rotation, inner
boundary following outer with weight preserved. What remains project adaptation,
prescribed nowhere: (a) which window (Hu's 1/16–9/16 example vs the flatter
Fig. 5(b) 3/16–11/16) holds under center-fill Mono + FreeType 2.15.0;
(b) displacement sign per side and which pixel row the crown lands on;
(c) which extrema qualify (smooth outer/inner loops vs sharp terminals vs
connecting sweeps — Hu excludes sweeps; Hobby's sharp-extremum rules differ);
(d) zone-sharing/paired implementation with native-axis ownership respected.
Note the existing project phase-range arm (`docs/hobby-fitting.md`) covers
horizontal reflection-midpoint placement only and explicitly abstains on
apexes — arc-extremity phase is uncovered ground, not a revision of that arm.

Falsifying checks: (a) synthetic arc sweep — apex phase in 1/16-px steps across
one pixel under our exact scanner AND an independent from-spec center-fill
model; if no window position preserves a clean crown, or the windows disagree,
the transplant is falsified; (b) independent-capture comparison of any candidate
against stock FreeType across the agreed corpus; (c) bottom/side/inner
replication — any fix that helps tops but damages bottoms, sides, inner
counters, stroke weight, joins, or advances is rejected; (d) optical assessment
through the browser preview per `docs/evaluation.md` — parity alone never
suffices.

## 6. Validation proposals (not implemented; no `experiments/` involvement)

1. Synthetic single-arc sweep: one round outer apex (large radius, 48 px
   geometry), apex y stepped 16ths across one pixel; record crown run-lengths and
   protrusion presence under (i) our Mono pipeline, (ii) dropout-off, stub-off
   variants, (iii) stock FreeType. This single experiment calibrates the window
   choice and direction of §3.2–§3.3 and separates phase tips from rescue pixels.
   New files under `out/diagnostics/curve-extremity-tip-research/` only.
2. Rotation/reflection set: the same arc rotated 90°/180°/270° plus a ring (outer +
   inner apex) to test side extremities and inner boundaries under both sweeps.
3. Real-glyph panel: round tops (`o`, `e`, `c` shoulders), round bottoms (same
   glyphs, undershoot side), side extrema (`o`/`e` left/right, `C`, `G`), flat
   controls (`n`, `m` shoulders, `H`, `O`) to check round/flat ordering is preserved.
4. Zone-sharing check: paired extrema of one glyph moved together; verify top stroke
   weight, counter, joins, advance unchanged except the crown row.
5. Falsification gate: any candidate must beat (i)-(iii) against stock FreeType
   captures and pass browser optical review; dropout/stub toggles are diagnostics,
   not fixes, and per-glyph constants are out of scope.

## 7. Limitations

Endpoint inclusion (open vs closed window ends) is unspecified; the Hu-window vs
Fig.-5(b)-window choice is unresolved pending the sweep; FreeType-version drift
between the 1993/1995 scan rules and 2.15.0 is unquantified; the Fig. 5 reading
rests on a rendered-page crop, not the original bitmap data; grayscale
contrast/weight-value machinery (Hersch95 pp. 84–85) does not transfer
numerically to Mono. No optical acceptance is claimed; per `docs/evaluation.md`,
tests do not establish it.
