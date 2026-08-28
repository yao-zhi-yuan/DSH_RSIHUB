from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import next_action
assert next_action(90, False, True) == 'salvage'
assert next_action(30, False, True) == 'submit'
assert next_action(30, False, False) == 'report'
assert next_action(61, False, False) == 'work'
try: next_action(-1, False, False)
except ValueError: pass
else: raise AssertionError('negative')
