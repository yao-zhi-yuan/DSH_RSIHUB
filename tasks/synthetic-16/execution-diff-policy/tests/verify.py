from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import allowed_changes
assert allowed_changes(['src/a.py', 'tests/test_a.py'])
assert allowed_changes([])
for paths in [['src/../.env'], ['/tmp/x'], ['tests/key.pem'], ['src/__pycache__/x.pyc'], ['.git/config']]:
    assert not allowed_changes(paths), paths
