from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)

from module import unique_records
rows = [{'id': [1, 2], 'v': 'a'}, {'v': 'skip'}, {'id': [1, 2], 'v': 'b'}, {'id': 3}]
copy = [dict(row) for row in rows]
assert unique_records(rows, 'id') == [{'id': [1, 2], 'v': 'a'}, {'id': 3}]
assert rows == copy
