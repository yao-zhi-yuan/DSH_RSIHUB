from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import parse_bool
for value in (True, 1, 'TRUE', 'on', '1'): assert parse_bool(value) is True
for value in (False, 0, 'false', ' off ', '0'): assert parse_bool(value) is False
for value in (None, 2, '', 'maybe', []):
    try: parse_bool(value)
    except ValueError: pass
    else: raise AssertionError(repr(value))
