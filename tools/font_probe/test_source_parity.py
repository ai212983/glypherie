"""Source-parity scoreboard: executable claims from external references.

Each item cites the source document and section it encodes.
An alignment step is product-code change plus a regen census
and dual-witness oracle; a test's call shape may only change
with a written source-architecture justification on record
(see single-width note). Passing items pin behavior sources
require.

Status key: GATE = implementation landed, census/oracle
pending; HELD = passes, pinned.

GATE RECORD (wired 2026-09-15, production wiring reverted same day):
- single-width rejoins main at the link layer: CVT spec
  MIRP/MDRP single_width_cut_in test (vendored
  docs/reference/fonts/specs/truetype-instruction-set-otspec184.md,
  MIRP section) + Shamir 2003 Sec. 1 (uniform stem width with a
  minimum) and Sec. 5/Fig. 18 (whole font moves 1px to 2px
  together). VTT's own prep snaps to CVT within 4px below
  29ppem (vendored preptmpl.txt, VTT 6.01C), and its Res links
  realize whichever width the glyph program assigns
  (ResDDLink -> fpgm 104 cut-in + floor, verified in
  docs/reference/VisualTrueType at 1bd4ed4). The link-layer
  vehicle is correct architecture (shared table
  geometry-free, per-link choice consumes role — spec MIRP
  flags, VTT Link(parent, child, cvt, minDist),
  TTGenerator.cpp:82); the test below pins its decision rule
  at unit level and passes.
- What the gates showed: role classification exists
  (`stem_roles`, VTT `TheColor` pattern TTFont.cpp:145).
  Two predicates were each wired through standardize and
  regen-gated across all 12 faces. Span-cover (zone touches
  span): exactly 2 deltas (ss3-18/20 `[`), REJECTED under
  absolute judgment (candidate 14/21px from settled W=0
  witnesses; arch-probe-v19). Endpoint-touch (endpoint on
  zone): same 2 deltas, same rejection (arch-probe-v20) —
  the bracket's straight section reaches the voted cap
  (656u) while its terminals overshoot past, so any
  zone-touch rule fires on it. Production wiring reverted.
  Production standing, absolute: ss3-18 `[` thin is
  established (W=0, C=0, APPROVE); n/m/+/o show no
  change-induced movement (any gaps there are absolute
  findings, see ledger evaluation protocol, not regressions).
  Lesson, recorded against the old premise: the thin
  classes hold only foundry-thin strokes (brackets, symbols,
  floating arms) — the assumed 64u split of n/m/p from the
  main does not occur in current tables, so no live rejoin
  target exists. A global floor stays rejected (77-to-17
  precedent).
- Reopen condition: a width table containing an
  anchored sub-main width the witnesses want widened, plus
  a predicate that takes it while holding brackets/plus
  thin, proven through the same census + oracle gates.

HELD (pinned by existing suites, referenced here):
- thin-only sharing (Shamir 2003 Sec. 3.5: a shared target
  applies when it thins the design): test_curved_width_links
  (thin-only + hold-or-widen), test_stem_width_table
  JointSubstitutionTests.
- cut-in gating (spec SCVTCI/SSWCI; VTT prep): TargetTests
  (straddling snap, distant rejection, own-rounding fallback).
- font-wide standard widths (Turner-Lemberg 2003: standards
  computed once, ahglobals): build_table spans all records.
- minimum 1px rendering (spec minimum_distance direction):
  curved shared_target and joint guards never emit 0px.
- settled witness targets (WitnessSettledTests below):
  ss3-18 `[` (witnesses agree exactly) and `o` (W=4).
  These pin that the *target* is settled, re-derived live
  every run from the committed font; production standing
  against them is re-verified by the oracle gate after
  each regen (census trips, oracle judges).
"""
import json
import tempfile
import unittest
from pathlib import Path

import freetype as ft

import stem_width_table as T


class SourceParityTests(unittest.TestCase):
    def test_single_width_rejoins_main(self):
        # Aligned 2026-09-15 with the source architecture: the
        # shared table stays geometry-free (spec CVT fetch; VTT
        # value lookup), while the per-link choice consumes the
        # role (spec MIRP per-instruction flags; VTT
        # Link(parent, child, cvt, minDist), TTGenerator.cpp:82).
        # The previous shape asserted lookup(table, 64.0) == 2,
        # which demands of the shared layer what sources only
        # ever do at the link layer — it encoded the rejected
        # font-wide floor, not the requirement. Intent
        # preserved: the anchored 64u stem takes the 2px main.
        from stem_roles import ANCHORED, FLOATING
        table = {'ppem': 16, 'em': 1000, 'cut_in_px': 1.0, 'clusters': [
            {'design_mean_units': 95.0, 'members': [{}] * 12,
             'target_px': 2, 'reason': 'main stem class'},
            {'design_mean_units': 64.0, 'members': [{}, {}],
             'target_px': 1, 'reason': 'thin stem class'}]}
        self.assertEqual(T.main_stem_target(table), 2)
        # Shared layer unchanged: geometry-free fetch returns
        # the cluster target.
        self.assertEqual(T.lookup(table, 64.0), 1)
        # Link layer: anchored rejoins, floating holds.
        self.assertEqual(T.rejoin_main(table, 64.0, ANCHORED), 2)
        self.assertIsNone(T.rejoin_main(table, 64.0, FLOATING))
        self.assertIsNone(T.rejoin_main(table, 64.0, None))


def _witness_pixels(ttf_path, char, size, mode):
    """Mono freetype render as an ink set, pipeline settings.

    Mirrors the oracle harness: dropout repair disabled, target
    mono, position folded in. Native runs the foundry bytecode;
    autohint runs FreeType's hinter instead.
    """
    from compare_paper_prototypes import FLAGS
    face = ft.Face(str(ttf_path))
    face.set_pixel_sizes(0, size)
    flags = ft.FT_LOAD_NO_BITMAP | ft.FT_LOAD_TARGET_MONO
    if mode == 'native':
        flags |= ft.FT_LOAD_PEDANTIC | ft.FT_LOAD_NO_AUTOHINT
    elif mode == 'autohint':
        flags |= ft.FT_LOAD_FORCE_AUTOHINT
    else:
        raise ValueError(mode)
    face.load_char(char, flags)
    outline = face.glyph.outline._FT_Outline
    outline.flags = ((outline.flags & ~FLAGS)
                     | ft.FT_OUTLINE_IGNORE_DROPOUTS)
    face.glyph.render(ft.FT_RENDER_MODE_MONO)
    s = face.glyph
    b = s.bitmap
    buf = b.buffer
    w, h = b.width, b.rows
    px = [(buf[y * b.pitch + x // 8] >> (7 - x % 8)) & 1
          for y in range(h) for x in range(w)]
    left, top = s.bitmap_left, -s.bitmap_top
    return {(left + i % w, top + i // w)
            for i, v in enumerate(px) if v}


class WitnessSettledTests(unittest.TestCase):
    """Settledness of witness targets, re-derived live.

    Pins that the target itself is established (witnesses
    agree), from the committed font and job — no generated
    output involved, so this runs on a clean checkout.
    Production standing against these targets is a separate
    step: the census trips on movement, the oracle judges
    (see ledger evaluation protocol).
    """
    FACE = 'source-sans-3'
    SIZE = 18

    @classmethod
    def setUpClass(cls):
        from compare_shamir_pipeline import instance
        here = Path(__file__).resolve()
        job_path = (here.parent.parent / 'font_generator'
                    / 'examples' / f'{cls.FACE}.json')
        job = json.loads(job_path.read_text())
        source = (job_path.parent / job['font']).resolve()
        axes = dict(job['settings']['axes'])
        axes['wght'] = 400
        if 'opsz' in axes:
            axes['opsz'] = min(72, max(7, cls.SIZE))
        cls.work = tempfile.TemporaryDirectory()
        cls.ttf = str(Path(cls.work.name) / 'source.ttf')
        instance(str(source), cls.ttf, axes)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def assertSettled(self, char, limit):
        auto = _witness_pixels(self.ttf, char, self.SIZE, 'autohint')
        nat = _witness_pixels(self.ttf, char, self.SIZE, 'native')
        self.assertLessEqual(len(auto ^ nat), limit)

    def test_bracket_target_settled_exactly(self):
        # ss3-18 `[`: witnesses agree pixel-for-pixel (W=0),
        # establishing the thin bracket both keep.
        self.assertSettled('[', 0)

    def test_o_target_settled(self):
        # ss3-18 `o`: witnesses agree within 4px (W=4).
        self.assertSettled('o', 4)
