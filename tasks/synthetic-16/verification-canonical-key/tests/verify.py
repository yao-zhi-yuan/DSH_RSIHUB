from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

import hashlib, json
from module import canonical_key
value = {'z': '中文', 'a': [1, True]}
raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
assert canonical_key(value) == hashlib.sha256(raw).hexdigest()
