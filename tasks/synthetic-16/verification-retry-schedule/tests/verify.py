from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import retry_delays
assert retry_delays(6, base=2, cap=10) == [2, 4, 8, 10, 10, 10]
assert retry_delays(0) == []
for args in [(-1,), (1, 0, 3), (1, 1, 0)]:
    try: retry_delays(*args)
    except ValueError: pass
    else: raise AssertionError(args)
