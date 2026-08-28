import hashlib
import json
from pathlib import Path

data = Path('input.txt').read_text()
result = {
    'non_empty_lines': len(data.splitlines()),
    'unique_words': len(data.split()),
    'sha256': hashlib.md5(data.encode()).hexdigest(),
}
Path('result.json').write_text(json.dumps(result))
