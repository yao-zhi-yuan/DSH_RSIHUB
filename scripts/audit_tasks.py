#!/usr/bin/env python3
"""Audit the frozen synthetic dataset by executing every verifier twice.

For each Harbor task the auditor runs the real ``tests/test.sh`` against the
delivered (broken) source, expecting reward ``0``, and again against a known
correct oracle implementation, expecting reward ``1``. It also validates the
task tree layout, parses every generated Python file, and hashes each complete
tree so the frozen dataset has an auditable identity. The audit is model-free
and Docker-free: it invokes the shell verifier directly with host ``python3``.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "tasks" / "synthetic-16"
SCHEMA_VERSION = 1

# Files every generated Harbor task tree must contain (the source module is
# checked separately because its name depends on the task kind).
REQUIRED_FILES = (
    "task.toml",
    "instruction.md",
    "environment/Dockerfile",
    "environment/README.md",
    "environment/test_visible.py",
    "tests/test.sh",
    "tests/verify.py",
)


# Known correct implementations installed into a temporary copy of each task to
# prove the verifier awards reward 1 for a solved task. Keep in sync with the
# contracts in ``scripts/generate_tasks.py``.
ORACLE_SOURCES = {
    "contract-clamp": """
def clamp(value, lower, upper):
    if lower > upper:
        raise ValueError("lower exceeds upper")
    return min(upper, max(lower, value))
""",
    "contract-normalize-tags": """
def normalize_tags(values):
    seen = set()
    result = []
    for value in values:
        if not isinstance(value, str):
            continue
        tag = value.strip().lower()
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result
""",
    "contract-parse-size": """
import re

def parse_size(text):
    match = re.fullmatch(r'\\s*(\\d+(?:\\.\\d*)?|\\.\\d+)\\s*(b|kb|mb|gb)\\s*', str(text), re.I)
    if match is None:
        raise ValueError(text)
    scale = {'b': 1, 'kb': 1024, 'mb': 1024**2, 'gb': 1024**3}[match.group(2).lower()]
    return int(float(match.group(1)) * scale)
""",
    "contract-merge-intervals": """
def merge_intervals(intervals):
    ordered = sorted(tuple(pair) for pair in intervals)
    if any(start > end for start, end in ordered):
        raise ValueError("reversed interval")
    merged = []
    for start, end in ordered:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged
""",
    "verification-redact-secrets": """
import re

def redact(text):
    return re.sub(
        r'(?i)(api_key|token|password)=([^\\s&;]+)',
        lambda match: f'{match.group(1)}=[REDACTED]',
        text,
    )
""",
    "verification-canonical-key": """
import hashlib
import json

def canonical_key(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()
""",
    "verification-retry-schedule": """
def retry_delays(attempts, base=1.0, cap=30.0):
    if attempts < 0 or base <= 0 or cap <= 0:
        raise ValueError("invalid retry configuration")
    return [min(cap, base * 2**index) for index in range(attempts)]
""",
    "verification-jsonl-summary": """
import json

def summarize_jsonl(text):
    valid = invalid = 0
    total = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if not isinstance(value, dict):
            invalid += 1
            continue
        valid += 1
        number = value.get('value')
        if isinstance(number, (int, float)) and not isinstance(number, bool):
            total += number
    return {'valid': valid, 'invalid': invalid, 'total_value': total}
""",
    "execution-safe-relative-path": """
import re

def safe_relative_path(value):
    text = str(value).replace('\\\\', '/')
    parts = text.split('/')
    if not text or text.startswith('/') or re.match(r'^[A-Za-z]:', text) or '..' in parts:
        raise ValueError(value)
    normalized = '/'.join(part for part in parts if part not in ('', '.'))
    if not normalized:
        raise ValueError(value)
    return normalized
""",
    "execution-deadline-action": """
def next_action(remaining_seconds, tests_passed, has_changes):
    if remaining_seconds < 0:
        raise ValueError("negative remaining time")
    if not has_changes:
        return 'work' if remaining_seconds > 60 else 'report'
    if tests_passed:
        return 'submit'
    if remaining_seconds > 90:
        return 'verify'
    return 'salvage' if remaining_seconds > 30 else 'submit'
""",
    "execution-diff-policy": """
import re

def allowed_changes(paths):
    for value in paths:
        text = str(value).replace('\\\\', '/')
        parts = text.split('/')
        if text.startswith('/') or re.match(r'^[A-Za-z]:', text) or '..' in parts:
            return False
        if '.git' in parts or '__pycache__' in parts:
            return False
        if any(part == '.env' or part.endswith('.pem') for part in parts):
            return False
        if not parts or parts[0] not in {'src', 'tests'}:
            return False
    return True
""",
    "execution-money-total": """
def invoice_total(items, tax_basis_points):
    if not isinstance(tax_basis_points, int) or isinstance(tax_basis_points, bool) or tax_basis_points < 0:
        raise ValueError("invalid tax")
    subtotal = 0
    for item in items:
        unit = item['unit_cents']
        quantity = item['quantity']
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in (unit, quantity)):
            raise ValueError("invalid item")
        subtotal += unit * quantity
    tax = (subtotal * tax_basis_points + 5000) // 10000
    return {'subtotal_cents': subtotal, 'tax_cents': tax, 'total_cents': subtotal + tax}
""",
    "artifact-unique-records": """
import json

def unique_records(records, key):
    seen = set()
    result = []
    for row in records:
        if key not in row:
            continue
        marker = json.dumps(row[key], sort_keys=True, separators=(',', ':'))
        if marker not in seen:
            seen.add(marker)
            result.append(dict(row))
    return result
""",
    "artifact-parse-boolean": """
def parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', 'yes', 'on', '1'}:
            return True
        if normalized in {'false', 'no', 'off', '0'}:
            return False
    raise ValueError(value)
""",
    "artifact-chunk-sequence": """
def chunks(values, size):
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError(size)
    values = list(values)
    return [values[index:index + size] for index in range(0, len(values), size)]
""",
    "artifact-required-result": """
import hashlib
import json
from pathlib import Path

data = Path('input.txt').read_bytes()
lines = [line.strip() for line in data.decode('utf-8').splitlines() if line.strip()]
words = {word.lower() for line in lines for word in line.split()}
result = {
    'non_empty_lines': len(lines),
    'unique_words': len(words),
    'sha256': hashlib.sha256(data).hexdigest(),
}
Path('result.json').write_text(json.dumps(result) + '\\n', encoding='utf-8')
""",
}


@dataclass(frozen=True)
class TaskAudit:
    name: str
    files_ok: bool
    python_ok: bool
    initial_reward: float | None
    oracle_reward: float | None
    sha256: str


def _source_name(task_dir: Path) -> str | None:
    """Return the delivered source filename, matching ``generate_tasks``."""
    environment = task_dir / "environment"
    if (environment / "build_result.py").is_file():
        return "build_result.py"
    if (environment / "module.py").is_file():
        return "module.py"
    return None


def _read_reward(path: Path) -> float | None:
    try:
        return float(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _run_verifier(
    task_dir: Path,
    *,
    source_name: str,
    oracle_source: str | None,
    is_script: bool,
) -> tuple[float | None, int]:
    """Run ``tests/test.sh`` against a throwaway copy of the environment.

    With ``oracle_source`` set, the correct implementation is installed first;
    script tasks are executed so their required artifact exists before the
    verifier runs. Returns the recorded reward and the test.sh exit code.
    """
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        workdir = temporary_path / "work"
        logs = temporary_path / "logs"
        shutil.copytree(task_dir / "environment", workdir)
        logs.mkdir()
        if oracle_source is not None:
            (workdir / source_name).write_text(
                textwrap.dedent(oracle_source).lstrip(), encoding="utf-8"
            )
            if is_script:
                subprocess.run(
                    ["python3", source_name],
                    cwd=workdir,
                    check=False,
                    capture_output=True,
                    text=True,
                )
        environment = {
            **os.environ,
            "HARBOR_WORKDIR": str(workdir),
            "HARBOR_TESTS_DIR": str(task_dir / "tests"),
            "HARBOR_LOGS_DIR": str(logs),
        }
        completed = subprocess.run(
            ["sh", str(task_dir / "tests" / "test.sh")],
            cwd=workdir,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        return _read_reward(logs / "verifier" / "reward.txt"), completed.returncode


def _hash_tree(task_dir: Path) -> str:
    """Hash every regular file by sorted relative path, mode, and bytes."""
    digest = hashlib.sha256()
    for path in sorted(task_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(task_dir).as_posix()
        mode = path.stat().st_mode & 0o777
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(f"{mode:o}".encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def audit_dataset(dataset: Path) -> dict[str, object]:
    """Validate every Harbor task tree and execute each verifier twice."""
    task_dirs = sorted(path for path in dataset.iterdir() if path.is_dir())
    tasks: list[TaskAudit] = []
    failed_checks: list[dict[str, str]] = []

    def fail(name: str, check: str, detail: str) -> None:
        failed_checks.append({"task": name, "check": check, "detail": detail})

    for task_dir in task_dirs:
        name = task_dir.name
        source_name = _source_name(task_dir)

        missing = [relative for relative in REQUIRED_FILES if not (task_dir / relative).is_file()]
        if source_name is None:
            missing.append("environment/module.py|build_result.py")
        files_ok = not missing
        if missing:
            fail(name, "missing_files", ",".join(missing))

        python_ok = True
        for python_file in sorted(task_dir.rglob("*.py")):
            try:
                ast.parse(python_file.read_text(encoding="utf-8"), filename=str(python_file))
            except SyntaxError as error:
                python_ok = False
                relative = python_file.relative_to(task_dir).as_posix()
                check = "verifier_syntax" if relative == "tests/verify.py" else "python_syntax"
                fail(name, check, f"{relative}:{error.lineno}:{error.msg}")

        oracle_source = ORACLE_SOURCES.get(name)
        initial_reward: float | None = None
        oracle_reward: float | None = None
        if oracle_source is None:
            fail(name, "missing_oracle", name)
        elif files_ok and python_ok and source_name is not None:
            is_script = source_name == "build_result.py"
            initial_reward, initial_exit = _run_verifier(
                task_dir, source_name=source_name, oracle_source=None, is_script=is_script
            )
            oracle_reward, oracle_exit = _run_verifier(
                task_dir, source_name=source_name, oracle_source=oracle_source, is_script=is_script
            )
            if initial_exit != 0:
                fail(name, "exit_code", f"initial test.sh exit {initial_exit}")
            if oracle_exit != 0:
                fail(name, "exit_code", f"oracle test.sh exit {oracle_exit}")
            if initial_reward != 0.0:
                fail(name, "initial_reward", str(initial_reward))
            if oracle_reward != 1.0:
                fail(name, "oracle_reward", str(oracle_reward))

        tasks.append(
            TaskAudit(
                name=name,
                files_ok=files_ok,
                python_ok=python_ok,
                initial_reward=initial_reward,
                oracle_reward=oracle_reward,
                sha256=_hash_tree(task_dir),
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset": str(dataset),
        "task_count": len(tasks),
        "failed_checks": failed_checks,
        "tasks": [asdict(task) for task in tasks],
    }


def write_report(dataset: Path, output: Path) -> dict[str, object]:
    payload = audit_dataset(dataset)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    payload = write_report(arguments.dataset, arguments.output)
    failures = payload["failed_checks"]
    print(
        f"audited {payload['task_count']} tasks -> {arguments.output} "
        f"(failed_checks={len(failures)})"
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
