import json
import tempfile
import unittest
from pathlib import Path
from cumulative_inputs import CHECKPOINTS,resolve

class CheckpointTests(unittest.TestCase):
    def test_missing_recorded_correction_cannot_fall_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for directory in CHECKPOINTS:
                (root/directory).mkdir();(root/directory/'report.json').write_text('{"cases": []}')
            (root/CHECKPOINTS[0]/'report.json').write_text(json.dumps(dict(cases=[dict(key='face-16',char='a',status='changed')])))
            (root/CHECKPOINTS[-1]/'face-16-u0061-after.ttf').touch()
            with self.assertRaisesRegex(ValueError,'missing recorded correction'):resolve(root,'face-16','a')
            latest=root/CHECKPOINTS[0]/'face-16-u0061-after.ttf';latest.touch()
            self.assertEqual(resolve(root,'face-16','a'),latest)

    def test_missing_stage_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'missing cumulative checkpoint'):resolve(tmp,'face-16','a')

if __name__=='__main__':unittest.main()
