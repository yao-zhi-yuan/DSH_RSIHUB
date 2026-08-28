from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import merge_intervals
source = [(5, 7), (1, 2), (2, 3), (9, 9)]
assert merge_intervals(source) == [(1, 3), (5, 7), (9, 9)]
assert source == [(5, 7), (1, 2), (2, 3), (9, 9)]
try: merge_intervals([(3, 1)])
except ValueError: pass
else: raise AssertionError('reversed interval')
