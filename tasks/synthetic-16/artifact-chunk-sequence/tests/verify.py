from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import chunks
assert chunks((x for x in range(5)), 2) == [[0, 1], [2, 3], [4]]
assert chunks([], 3) == []
for size in (0, -1, 1.5, True):
    try: chunks([1], size)
    except ValueError: pass
    else: raise AssertionError(size)
