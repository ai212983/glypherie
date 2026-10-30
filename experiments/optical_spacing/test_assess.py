import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import assess


SCRIPT = Path(__file__).with_name('assess.py')


class AssessmentChecks(unittest.TestCase):
    def fixture(self, directory):
        case = directory / 'landing' / 'literata-16'
        (case / 'repo').mkdir(parents=True)
        font = b'synthetic verification fixture'
        (case / 'input.ttf').write_bytes(font)
        png = io.BytesIO()
        Image.new('RGBA', (1, 1), (0, 0, 0, 255)).save(png, format='PNG')
        atlas = base64.b64encode(png.getvalue()).decode()
        (case / 'repo' / 'font.fnt').write_text(
            f'width=1\nheight=1\ntracking=0\n--metrics={{"baseline":1}}\ndata={atlas}\nn\t1\n')
        commands = [dict(op='move_to', x=0, y=0), dict(op='line_to', x=1, y=0),
                    dict(op='line_to', x=1, y=1), dict(op='line_to', x=0, y=1), dict(op='close')]
        glyph = dict(codepoint=110, left=0, top=-1, width=1, height=1,
                     pixels=[1], advance_26_6=64, fitted_commands=commands)
        return dict(settings=dict(size_px=16), pipeline=dict(fitting='font_hints_auto', diagonal_fitting=True),
                    source=dict(records=[glyph]), fitted=dict(records=[dict(glyph)],
                    source_sha256=hashlib.sha256(font).hexdigest()), source_kerning=dict(pairs=[]),
                    finalized_advances=[dict(codepoint=110, advance_26_6=64)], finalized_pairs=[])

    def verify_optimized(self, directory, capture):
        path = directory / 'capture.json'
        path.write_text(json.dumps(capture))
        return subprocess.run([sys.executable, '-O', '-c',
            "import json,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
            "from assess import verify_export; verify_export(json.loads(Path(sys.argv[2]).read_text()),Path(sys.argv[3]))",
            str(SCRIPT.parent), str(path), str(directory / 'landing')], capture_output=True, text=True)

    def test_optimized_verification_accepts_matching_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            capture = self.fixture(directory)
            assess.verify_export(capture, directory / 'landing')
            result = self.verify_optimized(directory, capture)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_optimized_verification_rejects_mismatches(self):
        for mismatch in ('font', 'bitmap', 'advance', 'pairs'):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                capture = self.fixture(directory)
                if mismatch == 'font':
                    capture['fitted']['source_sha256'] = 'wrong identity'
                elif mismatch == 'bitmap':
                    capture['fitted']['records'][0]['pixels'] = [0]
                elif mismatch == 'advance':
                    capture['finalized_advances'][0]['advance_26_6'] = 128
                else:
                    capture['finalized_pairs'] = [dict(left=110, right=110, adjustment_26_6=64)]
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    assess.verify_export(capture, directory / 'landing')
                result = self.verify_optimized(directory, capture)
                self.assertNotEqual(result.returncode, 0, f'{mismatch} mismatch was accepted')
                self.assertIn('mismatch', result.stderr.lower())

    def test_page_reports_only_performed_export_verification(self):
        for verified in (False, True):
            with self.subTest(verified=verified), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                capture = self.fixture(directory)
                path = directory / 'captures.jsonl'
                path.write_text(json.dumps(capture) + '\n')
                output = directory / 'review'
                command = [str(SCRIPT), '--captures', str(path), '--out', str(output)]
                if verified:
                    command += ['--landing-root', str(directory / 'landing')]
                with patch.object(sys, 'argv', command), redirect_stdout(io.StringIO()):
                    assess.main()
                page = (output / 'index.html').read_text()
                message = ('Export parity was verified for 1 current captures.'
                           if verified else 'Export parity was not checked.')
                self.assertIn(message, page)
                self.assertNotIn('Current captures exactly match the published', page)
                receipt = json.loads((output / 'verification.json').read_text())
                self.assertEqual(receipt['exact_export_parity_cases'], int(verified))


if __name__ == '__main__':
    unittest.main()
