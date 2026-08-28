from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import summarize_jsonl
text = '{"value":2}\nnot-json\n[]\n{"value":true}\n{"value":1.5}\n\n'
assert summarize_jsonl(text) == {'valid': 3, 'invalid': 2, 'total_value': 3.5}
