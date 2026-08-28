from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import redact
assert redact('API_KEY=a-b_c password=hunter2; ok=1') == 'API_KEY=[REDACTED] password=[REDACTED]; ok=1'
assert redact('x=1&TOKEN=abc.def&y=2') == 'x=1&TOKEN=[REDACTED]&y=2'
assert redact('no secret') == 'no secret'
