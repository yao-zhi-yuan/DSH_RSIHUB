from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

import hashlib, json
from pathlib import Path
root = Path(WORKDIR)
result_path = root / 'result.json'
assert result_path.is_file(), 'result.json missing'
raw = (root / 'input.txt').read_bytes()
assert json.loads(result_path.read_text()) == {
    'non_empty_lines': 3,
    'unique_words': 3,
    'sha256': hashlib.sha256(raw).hexdigest(),
}
assert result_path.read_bytes().endswith(b'\n')
