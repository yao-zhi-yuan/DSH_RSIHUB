#!/usr/bin/env python3
"""Generate the frozen 16-task local Harbor dataset."""

from __future__ import annotations

import shutil
import textwrap
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = ROOT / "tasks" / "synthetic-16"


@dataclass(frozen=True)
class Task:
    name: str
    contract: str
    source: str
    visible_test: str
    verifier: str
    instruction: str | None = None
    extra_files: tuple[tuple[str, str], ...] = ()


TASKS = [
    Task(
        "contract-clamp",
        """Implement `clamp(value, lower, upper)` in `module.py`.

- Return `lower` below the range and `upper` above it.
- Preserve values already inside the inclusive range.
- Raise `ValueError` when `lower > upper`.
- Accept integers and floats without converting their type unnecessarily.
""",
        """def clamp(value, lower, upper):
    if value < lower:
        return upper
    if value > upper:
        return lower
    return value
""",
        """import unittest
from module import clamp

class Visible(unittest.TestCase):
    def test_inside(self): self.assertEqual(clamp(5, 0, 10), 5)
    def test_low(self): self.assertEqual(clamp(-1, 0, 10), 0)

if __name__ == '__main__': unittest.main()
""",
        """from module import clamp
assert clamp(11, 0, 10) == 10
assert clamp(2.5, 0.0, 2.0) == 2.0
try:
    clamp(1, 3, 2)
except ValueError:
    pass
else:
    raise AssertionError('invalid bounds must fail')
""",
    ),
    Task(
        "contract-normalize-tags",
        """Implement `normalize_tags(values)`.

Trim surrounding whitespace, lowercase tags, discard empty tags, and remove duplicates while preserving the first-seen order. Inputs may contain non-string values; ignore them.
""",
        """def normalize_tags(values):
    return sorted(set(values))
""",
        """import unittest
from module import normalize_tags

class Visible(unittest.TestCase):
    def test_basic(self): self.assertEqual(normalize_tags([' A ', 'b']), ['a', 'b'])

if __name__ == '__main__': unittest.main()
""",
        """from module import normalize_tags
assert normalize_tags([' B ', 'a', 'b', '', None, ' A ']) == ['b', 'a']
assert normalize_tags([]) == []
""",
    ),
    Task(
        "contract-parse-size",
        """Implement `parse_size(text)` and return an integer byte count.

Accepted suffixes are B, KB, MB, and GB, case-insensitively, using powers of 1024. Decimal numbers are allowed. Whitespace around the number or suffix is allowed. Reject negative, malformed, or unsupported values with `ValueError`.
""",
        """def parse_size(text):
    return int(text[:-2]) * 1000
""",
        """import unittest
from module import parse_size

class Visible(unittest.TestCase):
    def test_kb(self): self.assertEqual(parse_size('2KB'), 2048)

if __name__ == '__main__': unittest.main()
""",
        """from module import parse_size
assert parse_size(' 1.5 mb ') == 1572864
assert parse_size('7B') == 7
assert parse_size('1GB') == 1073741824
for value in ('-1KB', '2TB', 'oops'):
    try: parse_size(value)
    except ValueError: pass
    else: raise AssertionError(value)
""",
    ),
    Task(
        "contract-merge-intervals",
        """Implement `merge_intervals(intervals)`.

Each interval is a two-item iterable `(start, end)` with `start <= end`. Return sorted list pairs. Merge overlapping intervals and intervals that touch at an endpoint. Do not mutate the input. Raise `ValueError` for reversed intervals.
""",
        """def merge_intervals(intervals):
    return list(intervals)
""",
        """import unittest
from module import merge_intervals

class Visible(unittest.TestCase):
    def test_overlap(self): self.assertEqual(merge_intervals([(1, 3), (2, 4)]), [(1, 4)])

if __name__ == '__main__': unittest.main()
""",
        """from module import merge_intervals
source = [(5, 7), (1, 2), (2, 3), (9, 9)]
assert merge_intervals(source) == [(1, 3), (5, 7), (9, 9)]
assert source == [(5, 7), (1, 2), (2, 3), (9, 9)]
try: merge_intervals([(3, 1)])
except ValueError: pass
else: raise AssertionError('reversed interval')
""",
    ),
    Task(
        "verification-redact-secrets",
        """Implement `redact(text)`.

Replace values following `api_key=`, `token=`, or `password=` with `[REDACTED]`. Keys are case-insensitive. A value ends at whitespace, `&`, or `;`. Preserve all other text and the original key spelling.
""",
        """import re

def redact(text):
    return re.sub(r'token=\\w+', 'token=[REDACTED]', text)
""",
        """import unittest
from module import redact

class Visible(unittest.TestCase):
    def test_token(self): self.assertEqual(redact('token=abc'), 'token=[REDACTED]')

if __name__ == '__main__': unittest.main()
""",
        """from module import redact
assert redact('API_KEY=a-b_c password=hunter2; ok=1') == 'API_KEY=[REDACTED] password=[REDACTED]; ok=1'
assert redact('x=1&TOKEN=abc.def&y=2') == 'x=1&TOKEN=[REDACTED]&y=2'
assert redact('no secret') == 'no secret'
""",
    ),
    Task(
        "verification-canonical-key",
        """Implement `canonical_key(value)`.

Return a lowercase SHA-256 hex digest of canonical UTF-8 JSON. Canonical JSON uses sorted object keys, no insignificant whitespace, and preserves Unicode characters rather than ASCII escaping. Equivalent dictionary insertion orders must produce the same digest.
""",
        """import hashlib, json

def canonical_key(value):
    return hashlib.md5(json.dumps(value).encode()).hexdigest()
""",
        """import unittest
from module import canonical_key

class Visible(unittest.TestCase):
    def test_stable(self): self.assertEqual(canonical_key({'b': 2, 'a': 1}), canonical_key({'a': 1, 'b': 2}))

if __name__ == '__main__': unittest.main()
""",
        """import hashlib, json
from module import canonical_key
value = {'z': '中文', 'a': [1, True]}
raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
assert canonical_key(value) == hashlib.sha256(raw).hexdigest()
""",
    ),
    Task(
        "verification-retry-schedule",
        """Implement `retry_delays(attempts, base=1.0, cap=30.0)`.

Return one delay per retry attempt: `base * 2**index`, capped individually at `cap`. `attempts=0` returns an empty list. Reject negative attempts, non-positive base, or non-positive cap with `ValueError`.
""",
        """def retry_delays(attempts, base=1.0, cap=30.0):
    return [base * 2 ** (i + 1) for i in range(attempts)]
""",
        """import unittest
from module import retry_delays

class Visible(unittest.TestCase):
    def test_three(self): self.assertEqual(retry_delays(3), [1.0, 2.0, 4.0])

if __name__ == '__main__': unittest.main()
""",
        """from module import retry_delays
assert retry_delays(6, base=2, cap=10) == [2, 4, 8, 10, 10, 10]
assert retry_delays(0) == []
for args in [(-1,), (1, 0, 3), (1, 1, 0)]:
    try: retry_delays(*args)
    except ValueError: pass
    else: raise AssertionError(args)
""",
    ),
    Task(
        "verification-jsonl-summary",
        """Implement `summarize_jsonl(text)`.

Parse non-empty lines as JSON objects. Ignore malformed JSON and non-object JSON values. Return `{'valid': N, 'invalid': M, 'total_value': S}` where `total_value` sums numeric `value` fields but excludes booleans.
""",
        """import json

def summarize_jsonl(text):
    rows = [json.loads(line) for line in text.splitlines()]
    return {'valid': len(rows), 'invalid': 0, 'total_value': sum(row['value'] for row in rows)}
""",
        """import unittest
from module import summarize_jsonl

class Visible(unittest.TestCase):
    def test_valid(self): self.assertEqual(summarize_jsonl('{"value":2}\\n'), {'valid': 1, 'invalid': 0, 'total_value': 2})

if __name__ == '__main__': unittest.main()
""",
        """from module import summarize_jsonl
text = '{"value":2}\\nnot-json\\n[]\\n{"value":true}\\n{"value":1.5}\\n\\n'
assert summarize_jsonl(text) == {'valid': 3, 'invalid': 2, 'total_value': 3.5}
""",
    ),
    Task(
        "execution-safe-relative-path",
        """Implement `safe_relative_path(value)`.

Return a normalized POSIX relative path. Reject absolute paths, Windows drive paths, empty paths, and any path that contains or normalizes through `..`. Convert backslashes to slashes and remove `.` components.
""",
        """from pathlib import Path

def safe_relative_path(value):
    return str(Path(value))
""",
        """import unittest
from module import safe_relative_path

class Visible(unittest.TestCase):
    def test_basic(self): self.assertEqual(safe_relative_path('./a/b'), 'a/b')

if __name__ == '__main__': unittest.main()
""",
        """from module import safe_relative_path
assert safe_relative_path(r'a\\b\\c.txt') == 'a/b/c.txt'
for value in ('', '/etc/passwd', '../x', 'a/../../x', r'C:\\temp\\x'):
    try: safe_relative_path(value)
    except ValueError: pass
    else: raise AssertionError(value)
""",
    ),
    Task(
        "execution-deadline-action",
        """Implement `next_action(remaining_seconds, tests_passed, has_changes)`.

- No changes: return `work` when more than 60 seconds remain, otherwise `report`.
- Changes with passing tests: return `submit`.
- Changes with failing/unrun tests: return `verify` above 90 seconds, `salvage` from 31 through 90 seconds, and `submit` at 30 seconds or below.
- Reject negative remaining time.
""",
        """def next_action(remaining_seconds, tests_passed, has_changes):
    return 'work'
""",
        """import unittest
from module import next_action

class Visible(unittest.TestCase):
    def test_verified(self): self.assertEqual(next_action(100, True, True), 'submit')
    def test_verify(self): self.assertEqual(next_action(100, False, True), 'verify')

if __name__ == '__main__': unittest.main()
""",
        """from module import next_action
assert next_action(90, False, True) == 'salvage'
assert next_action(30, False, True) == 'submit'
assert next_action(30, False, False) == 'report'
assert next_action(61, False, False) == 'work'
try: next_action(-1, False, False)
except ValueError: pass
else: raise AssertionError('negative')
""",
    ),
    Task(
        "execution-diff-policy",
        """Implement `allowed_changes(paths)`.

Return `True` only when every normalized path is under `src/` or `tests/`. Reject absolute paths, traversal, `.git`, secrets (`.env` or any `.pem`), and generated `__pycache__` entries. An empty list is allowed.
""",
        """def allowed_changes(paths):
    return all(path.startswith('src/') for path in paths)
""",
        """import unittest
from module import allowed_changes

class Visible(unittest.TestCase):
    def test_src(self): self.assertTrue(allowed_changes(['src/app.py']))
    def test_docs(self): self.assertFalse(allowed_changes(['README.md']))

if __name__ == '__main__': unittest.main()
""",
        """from module import allowed_changes
assert allowed_changes(['src/a.py', 'tests/test_a.py'])
assert allowed_changes([])
for paths in [['src/../.env'], ['/tmp/x'], ['tests/key.pem'], ['src/__pycache__/x.pyc'], ['.git/config']]:
    assert not allowed_changes(paths), paths
""",
    ),
    Task(
        "execution-money-total",
        """Implement `invoice_total(items, tax_basis_points)`.

Each item has integer `unit_cents` and `quantity`. Reject negative values. Compute subtotal in cents, then tax using integer half-up rounding where 10,000 basis points equals 100%. Return `{'subtotal_cents', 'tax_cents', 'total_cents'}`.
""",
        """def invoice_total(items, tax_basis_points):
    subtotal = sum(x['unit_cents'] for x in items)
    tax = round(subtotal * tax_basis_points / 10000)
    return {'subtotal_cents': subtotal, 'tax_cents': tax, 'total_cents': subtotal + tax}
""",
        """import unittest
from module import invoice_total

class Visible(unittest.TestCase):
    def test_basic(self): self.assertEqual(invoice_total([{'unit_cents': 100, 'quantity': 2}], 500)['total_cents'], 210)

if __name__ == '__main__': unittest.main()
""",
        """from module import invoice_total
assert invoice_total([{'unit_cents': 1, 'quantity': 5}], 1000) == {'subtotal_cents': 5, 'tax_cents': 1, 'total_cents': 6}
assert invoice_total([], 0) == {'subtotal_cents': 0, 'tax_cents': 0, 'total_cents': 0}
for items, rate in [([{'unit_cents': -1, 'quantity': 1}], 0), ([{'unit_cents': 1, 'quantity': -1}], 0), ([], -1)]:
    try: invoice_total(items, rate)
    except ValueError: pass
    else: raise AssertionError((items, rate))
""",
    ),
    Task(
        "artifact-unique-records",
        """Implement `unique_records(records, key)`.

Return shallow copies of the first record for each distinct key value, preserving order. Records missing the key are skipped. Unhashable key values must be supported by canonical JSON comparison. Do not mutate inputs.
""",
        """def unique_records(records, key):
    return list({row[key]: row for row in records}.values())
""",
        """import unittest
from module import unique_records

class Visible(unittest.TestCase):
    def test_first(self): self.assertEqual(unique_records([{'id': 1, 'v': 'a'}, {'id': 1, 'v': 'b'}], 'id'), [{'id': 1, 'v': 'a'}])

if __name__ == '__main__': unittest.main()
""",
        """from module import unique_records
rows = [{'id': [1, 2], 'v': 'a'}, {'v': 'skip'}, {'id': [1, 2], 'v': 'b'}, {'id': 3}]
copy = [dict(row) for row in rows]
assert unique_records(rows, 'id') == [{'id': [1, 2], 'v': 'a'}, {'id': 3}]
assert rows == copy
""",
    ),
    Task(
        "artifact-parse-boolean",
        """Implement `parse_bool(value)`.

Accept booleans directly. Accept integers 0 and 1. Accept strings `true/false`, `yes/no`, `on/off`, and `1/0`, ignoring surrounding whitespace and case. Raise `ValueError` for every other value, including `None` and integers other than 0 or 1.
""",
        """def parse_bool(value):
    return bool(value)
""",
        """import unittest
from module import parse_bool

class Visible(unittest.TestCase):
    def test_words(self): self.assertTrue(parse_bool(' yes ')); self.assertFalse(parse_bool('NO'))

if __name__ == '__main__': unittest.main()
""",
        """from module import parse_bool
for value in (True, 1, 'TRUE', 'on', '1'): assert parse_bool(value) is True
for value in (False, 0, 'false', ' off ', '0'): assert parse_bool(value) is False
for value in (None, 2, '', 'maybe', []):
    try: parse_bool(value)
    except ValueError: pass
    else: raise AssertionError(repr(value))
""",
    ),
    Task(
        "artifact-chunk-sequence",
        """Implement `chunks(values, size)`.

Return a list of lists containing consecutive chunks. Preserve order, include a final short chunk, accept any iterable including generators, and raise `ValueError` unless size is a positive integer. Booleans are not valid sizes.
""",
        """def chunks(values, size):
    return [values[i:i+size] for i in range(0, len(values), size)]
""",
        """import unittest
from module import chunks

class Visible(unittest.TestCase):
    def test_list(self): self.assertEqual(chunks([1, 2, 3], 2), [[1, 2], [3]])

if __name__ == '__main__': unittest.main()
""",
        """from module import chunks
assert chunks((x for x in range(5)), 2) == [[0, 1], [2, 3], [4]]
assert chunks([], 3) == []
for size in (0, -1, 1.5, True):
    try: chunks([1], size)
    except ValueError: pass
    else: raise AssertionError(size)
""",
    ),
    Task(
        "artifact-required-result",
        """`build_result.py` must read `input.txt` and create `result.json` with exactly these keys:

- `non_empty_lines`: count after trimming each line and excluding blanks.
- `unique_words`: case-insensitive count of distinct whitespace-separated words from non-empty lines.
- `sha256`: lowercase SHA-256 of the original `input.txt` bytes.

JSON must be valid UTF-8 with a trailing newline. Repair the script and run it; the required deliverable is the generated `result.json` file.
""",
        """import hashlib
import json
from pathlib import Path

data = Path('input.txt').read_text()
result = {
    'non_empty_lines': len(data.splitlines()),
    'unique_words': len(data.split()),
    'sha256': hashlib.md5(data.encode()).hexdigest(),
}
Path('result.json').write_text(json.dumps(result))
""",
        """import subprocess
import unittest

class Visible(unittest.TestCase):
    def test_script_runs(self):
        completed = subprocess.run(['python3', 'build_result.py'], check=False)
        self.assertEqual(completed.returncode, 0)

if __name__ == '__main__': unittest.main()
""",
        """import hashlib, json
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
assert result_path.read_bytes().endswith(b'\\n')
""",
        instruction="Repair `build_result.py` according to README.md and run it. The final required artifact is `result.json`. Do not edit `input.txt`, README.md, or tests.",
        extra_files=(("input.txt", "Alpha beta\n\nalpha\nGamma\n"),),
    ),
]


TEST_SH = """#!/bin/sh
set -eu
# Harbor uploads tests/ to /tests, runs the agent workspace at /app, and reads
# the reward from /logs/verifier/reward.txt. These fixed paths are the real
# Harbor contract; the audit harness overrides them via HARBOR_* for local runs.
WORKDIR="${HARBOR_WORKDIR:-/app}"
TESTS_DIR="${HARBOR_TESTS_DIR:-/tests}"
LOGS_DIR="${HARBOR_LOGS_DIR:-/logs}"
mkdir -p "$LOGS_DIR/verifier"
if python3 "$TESTS_DIR/verify.py" "$WORKDIR"; then
  printf '1\n' > "$LOGS_DIR/verifier/reward.txt"
else
  printf '0\n' > "$LOGS_DIR/verifier/reward.txt"
fi
"""


VERIFY_PREFIX = """from pathlib import Path
import sys

WORKDIR = sys.argv[1]
sys.path.insert(0, WORKDIR)
"""


def write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    if executable:
        path.chmod(0o755)


def generate() -> None:
    if TASKS_ROOT.exists():
        shutil.rmtree(TASKS_ROOT)
    for task in TASKS:
        root = TASKS_ROOT / task.name
        instruction = task.instruction or (
            "Repair `module.py` according to README.md. Preserve the public API, do not edit README.md or tests, "
            "and run `python3 -m unittest -v test_visible.py` before finishing."
        )
        write(root / "task.toml", f'[metadata]\nname = "{task.name}"\n')
        write(root / "instruction.md", instruction + "\n")
        write(
            root / "environment" / "Dockerfile",
            "FROM dsh-ollama-eval:node24-dsh011rc2\nWORKDIR /app\nCOPY . /app\n",
        )
        write(root / "environment" / "README.md", task.contract)
        source_name = "build_result.py" if task.name == "artifact-required-result" else "module.py"
        write(root / "environment" / source_name, task.source)
        write(root / "environment" / "test_visible.py", task.visible_test)
        for relative, content in task.extra_files:
            write(root / "environment" / relative, content)
        write(root / "tests" / "test.sh", TEST_SH, executable=True)
        write(root / "tests" / "verify.py", VERIFY_PREFIX + "\n" + task.verifier)


if __name__ == "__main__":
    generate()
    print(f"generated {len(TASKS)} tasks under {TASKS_ROOT}")
