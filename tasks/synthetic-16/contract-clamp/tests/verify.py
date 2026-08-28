from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import clamp
assert clamp(11, 0, 10) == 10
assert clamp(2.5, 0.0, 2.0) == 2.0
try:
    clamp(1, 3, 2)
except ValueError:
    pass
else:
    raise AssertionError('invalid bounds must fail')
