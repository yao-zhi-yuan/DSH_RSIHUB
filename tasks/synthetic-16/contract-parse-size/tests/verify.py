from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import parse_size
assert parse_size(' 1.5 mb ') == 1572864
assert parse_size('7B') == 7
assert parse_size('1GB') == 1073741824
for value in ('-1KB', '2TB', 'oops'):
    try: parse_size(value)
    except ValueError: pass
    else: raise AssertionError(value)
