"""Saved Python checkpoint adapter, in explicit newest-to-oldest precedence.

These are required inputs for continuing the reviewed specimen, not a source-font
hinter API. The mathematical final stage receives only geometry and provenance.
"""
from pathlib import Path
from functools import lru_cache
import json

CHECKPOINTS = (
    'stem-relative-terminals-v1', 'source-junctions-v1',
    'curved-width-links-v2', 'round-symmetry-v4',
    'component-symmetry-v2', 'cumulative-hinter-v6',
)


@lru_cache(maxsize=None)
def required_outputs(report, mtime_ns):
    """A recorded changed glyph must not silently fall back to an older stage."""
    rows=json.loads(Path(report).read_text()).get('cases', [])
    return {(r['key'],r['char']) for r in rows if r.get('status')=='changed'}


def resolve(root, key, char):
    root=Path(root)
    for directory in CHECKPOINTS:
        if not (root/directory/'report.json').is_file():
            raise ValueError(f'missing cumulative checkpoint: {directory}')
    stem=f'{key}-u{ord(char):04x}'
    paths=[]
    for directory in CHECKPOINTS:
        report=root/directory/'report.json';path=root/directory/(stem+'-after.ttf')
        if (key,char) in required_outputs(str(report),report.stat().st_mtime_ns) and not path.is_file():
            raise ValueError(f'missing recorded correction: {directory}/{stem}')
        paths.append(path)
    paths += [root/'cumulative-hinter-v6'/(stem+'-current.ttf'),
              root/'geometric-candidate-v3'/(key+'-candidate.ttf')]
    for path in paths:
        if path.is_file():return path
    raise ValueError(f'no cumulative input for {stem}')
