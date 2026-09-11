"""Tests for compare_native_translation (hand-computed, actual FT; solver not oracle)."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
import compare_native_translation as C

PY = sys.executable


def test_opcodes_per_kind():
    a, _ = C.target_op_asm('Abs', True)
    assert a[-1] == 'MDAP[1]'
    a, _ = C.target_op_asm('PAbs', False, 1)
    assert a[-1] == 'MIAP[0]'
    a, _ = C.target_op_asm('Dist', True)
    assert a[-1] == 'MDRP[00100]'
    a, _ = C.target_op_asm('PDist', False, 1)
    assert a[-1] == 'MIRP[00000]'
    a, _ = C.target_op_asm('Ratio', False)
    assert a[-1] == 'IP[ ]'


def test_hand_ref0_ppem125():
    # ref0 src x=100FU * 125/1000 = 12.5px + 1px SCFS setup move = 13.5px
    r = C.one_case('PAbs', 'x', 125, True, 0)
    assert r['native_error'] is None
    assert abs(r['declared_ref_targets_px']['0'][0] - 13.5) < 1e-9


def test_hand_signed():
    assert C.one_case('PDist', 'x', 125, True, -4)['native_target_px'][0] == 12.5
    assert C.one_case('PDist', 'x', 125, True, 0)['native_target_px'][0] == 13.5
    assert C.one_case('PDist', 'x', 125, True, 4)['native_target_px'][0] == 14.5
    assert C.one_case('PAbs', 'x', 125, True, -4)['native_target_px'][0] == -1.0
    assert C.one_case('PAbs', 'x', 125, True, 0)['native_target_px'][0] == 0.0
    assert C.one_case('PAbs', 'x', 125, True, 4)['native_target_px'][0] == 1.0


def test_hand_dist_ratio_cardinal():
    r = C.one_case('Abs', 'x', 16, True)
    assert abs(r['native_target_px'][0] - 5.0) < 1e-9
    r = C.one_case('PAbs', 'x', 125, True, 73)
    assert abs(r['native_target_px'][0] - 9.0) < 1e-9
    # Dist x ppem16 rounded: MDRP rounds the ORIGINAL distance (300-100)/1000*16=3.2
    # -> 3px; ref0 moved to 166/64=2.59375px, so target = 166/64+192/64 = 358/64.
    # FT actual 5.59375 confirms original-distance (not current-distance) semantics.
    r = C.one_case('Dist', 'x', 16, True)
    assert abs(r['native_target_px'][0] - 5.59375) < 1e-9
    # Ratio x ppem16: IP interpolates the original ratio between moved refs.
    # Hand derivation: ref0 x=100FU -> 166/64=2.59375px, ref1 x=500FU -> 512/64=8px;
    # original ratio t=(300-100)/(500-100)=0.5, midpoint (166+512)/2=339 -> 339/64=5.296875.
    r = C.one_case('Ratio', 'x', 16, False)
    assert abs(r['native_target_px'][0] - 5.296875) < 1e-9
    assert abs(r['native_target_px'][0] - (339 / 64)) < 1e-9


def test_flag_comparison_labels():
    fc = C.flag_comparison()
    assert set(fc) >= {'11101', '00100', 'follower_distance_px', 'note'}
    assert 'NOT a Fig.9 reproduction' in fc['note']
    a, b = fc['11101'], fc['00100']
    assert abs(a['target_px'][0] - b['target_px'][0]) < 1e-9  # same move; differ in rp0/min-distance/distance-type
    assert a['follower_px'][0] == a['target_px'][0]  # 11101 updates rp0: follower tracks moved target
    assert b['follower_px'][0] != b['target_px'][0]  # 00100 leaves rp0: follower does not track
    assert b['follower_px'][0] == b['ref0_px'][0]  # 00100 follower stays at ref0
    assert fc['follower_distance_px'] > 0


def test_unrepresentable_reasons():
    u = C.unsupported_examples()
    assert {'Abs', 'Dist', 'Ratio', 'PRatio'} <= {e['kind'] for e in u}
    assert all(e['reason'] and e['target_relation'] for e in u)


def test_output_fresh_gate():
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / 'o'
        out.mkdir()
        (out / 'x').write_text('x')
        p = subprocess.run([PY, 'compare_native_translation.py', '--output', str(out)],
                           capture_output=True, text=True)
        assert p.returncode != 0 and 'non-empty' in (p.stdout + p.stderr)


def test_full_matrix_once():
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / 'm'
        p = subprocess.run([PY, 'compare_native_translation.py', '--output', str(out)],
                           capture_output=True, text=True)
        assert p.returncode == 0, p.stderr[-2000:]
        rep = json.loads((out / 'report.json').read_text())
        assert rep['counts']['cases'] == 114 == len(rep['cases'])
        assert rep['verification_passed'] is True
        assert isinstance(rep['ft_version'], list)
        assert all(set(r['artifacts']) == {'native.ttf', 'scfs.ttf', 'native.asm', 'scfs.asm'} for r in rep['cases'])
        assert all(r['ppem'] in (14, 16, 20, 125) for r in rep['cases'])
        assert all('solver_hash' in rep and 'schedule_hash' in rep and 'constraints_hash' in rep for _ in [0])
        assert 'float64 end-quantization' in rep['precision_scope']


class TestNativeTranslation(unittest.TestCase):
    def test_opcodes_per_kind(self):
        test_opcodes_per_kind()

    def test_hand_ref0_ppem125(self):
        test_hand_ref0_ppem125()

    def test_hand_signed(self):
        test_hand_signed()

    def test_hand_dist_ratio_cardinal(self):
        test_hand_dist_ratio_cardinal()

    def test_flag_comparison_labels(self):
        test_flag_comparison_labels()

    def test_unrepresentable_reasons(self):
        test_unrepresentable_reasons()

    def test_output_fresh_gate(self):
        test_output_fresh_gate()

    def test_full_matrix_once(self):
        test_full_matrix_once()

    def test_native_ft_failure_records_error(self):
        # Inject a native-FT failure: runner must still write a complete
        # report (native_error set, verification fails, nonzero exit) and
        # must not crash writing a None ttf artifact.
        real_run = C.run_ft_raw
        calls = {'n': 0}

        def fake_run(src, asm, ppem, cvt_vals):
            # Fail every native call (first run_ft_raw per case), pass SCFS calls.
            calls['n'] += 1
            if calls['n'] % 2 == 1:
                raise RuntimeError('injected native FT failure')
            return real_run(src, asm, ppem, cvt_vals)
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / 'm'
            argv = ['compare_native_translation.py', '--output', str(out)]
            with mock.patch.object(C, 'run_ft_raw', side_effect=fake_run), \
                    mock.patch.object(sys, 'argv', argv):
                with self.assertRaises(SystemExit) as cm:
                    C.main()
            assert cm.exception.code != 0
            rep = json.loads((out / 'report.json').read_text())
            assert rep['counts']['cases'] == 114 == len(rep['cases'])
            assert rep['counts']['native_errors'] >= 1
            assert rep['verification_passed'] is False
            assert any(r['native_error'] for r in rep['cases'])
            for r in rep['cases']:
                assert '_native_data' not in r and '_scfs_data' not in r
                assert 'native.ttf' in r['artifacts'] or r['native_error'] is not None
