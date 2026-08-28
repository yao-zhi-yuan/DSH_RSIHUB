from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import normalize_tags
assert normalize_tags([' B ', 'a', 'b', '', None, ' A ']) == ['b', 'a']
assert normalize_tags([]) == []
