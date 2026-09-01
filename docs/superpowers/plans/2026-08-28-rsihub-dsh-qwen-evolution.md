# RSIHub + DSH + Qwen First Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reproducible RSIHub Hill Climb run in which DSH with local Ollama `qwen3:8b` is evaluated on the frozen 16-task suite and local Ollama `qwen3:14b` creates three prompt-only candidates, with complete Gate, Sealed, lineage, trace, and resource evidence.

**Architecture:** Keep the existing outer repository as the source of truth and preserve the failed `experiment/` as historical evidence. Add standard-library Python validation, orchestration, session parsing, and reporting utilities; freeze those inputs into a new workspace only after model-free gates pass. Use RSIHub's native driver and archive for lineage, with a separate report builder that verifies and summarizes retained evidence without making model calls.

**Tech Stack:** Python 3.12 standard library and `unittest`, RSIHub at commit `467f5b8`, Harbor 0.18.0, DSH npm package `0.1.1-rc.2`, Node 24, Ollama 0.33.1 with its OpenAI-compatible API.

---

## Stages and Final Deliverables (2026-08-28 alignment)

The macro objective: run RSIHub's evaluation over DSH, observe at least one
generational improvement, and publish a Feishu-style visualization of the run.

**Stage 1 (this run, prompt-only):** the mutator may edit only
`target/prompt.md`. Close the full loop — baseline → three generations →
Gate/Sealed → audit report → **HTML visualization** — across Tasks 1–12. This is
the scope delivered and verified in this run.

**Stage 2 (later, config/plugin-level):** once the loop is stable, widen the
evolvable surface to `cordis.yml` configuration, `plugins/*.mjs`, and
`skills/*.md` to reproduce the richer evolution shown in the Feishu share
(generational structure changes, multi-file diffs, agent-authored plugins).
Stage 2 requires changing the recipe's writable-path allowlist and the runtime
identity; it is out of scope here and gets its own plan.

**Visualization deliverable (Feishu-style, HTML):** see Task 12. It must include
at least a score curve (baseline → each generation, Gate and Sealed), a
generation overview (parent/child, gate accept/reject, champion), candidate
diffs (per-generation `target/prompt.md` text diff; multi-file diff stat in
Stage 2), resource consumption (target/mutator tokens, requests, wall-time,
disk), and the mutator's hypothesis / expected_effect against actual outcomes.

---

### Task 1: Establish a Reproducible Source Baseline

**Files:**
- Modify: `.gitignore`
- Create: `README.md`
- Track: `.env.example`, `config/`, `package.json`, `package-lock.json`, `patches/`, `recipes/`, `scripts/`, `seed/`, `tasks/`, `docs/`

- [ ] **Step 1: Extend generated-state exclusions**

Add these anchored entries while preserving the existing secret and dependency
rules:

```gitignore
/.worktrees/
/reports/raw/
```

- [ ] **Step 2: Document the repository entry points**

Create `README.md` with these commands and constraints:

```markdown
# DSH RSIHub Qwen experiment

This repository defines a local-Ollama, prompt-only Hill Climb experiment.

## Local checks

python3 -m unittest discover -s tests -v
python3 scripts/audit_tasks.py --output reports/preflight/task-audit.json
python3 scripts/experimentctl.py preflight --workspace workspaces/qwen-first-v1

## Live execution

python3 scripts/experimentctl.py models --pull-missing
python3 scripts/experimentctl.py probe
python3 scripts/experimentctl.py canary --workspace workspaces/qwen-first-v1
python3 scripts/experimentctl.py baseline --workspace workspaces/qwen-first-v1
python3 scripts/experimentctl.py evolve --workspace workspaces/qwen-first-v1
python3 scripts/experimentctl.py report --workspace workspaces/qwen-first-v1

The runner uses only the configured local Ollama daemon.
Only `target/prompt.md` may evolve.
```

- [ ] **Step 3: Check for accidental credentials before staging**

Run:

```bash
rg -n --hidden \
  -g '!.env' -g '!node_modules/**' -g '!vendor/**' -g '!experiment/**' \
  '(Bearer [A-Za-z0-9._~+/=-]{16,}|(?:API_KEY|TOKEN|SECRET|PASSWORD)=[^<$[:space:]][^[:space:]]*)' .
```

Expected: no literal credential values.

- [ ] **Step 4: Track the existing reproducibility inputs**

Run:

```bash
git add .gitignore .env.example README.md config package.json package-lock.json patches recipes scripts seed tasks docs
git diff --cached --check
git status --short
```

Expected: `.env`, `vendor/`, `experiment/`, `runs/`, and `workspaces/` are not
staged.

- [ ] **Step 5: Commit the source baseline**

```bash
git commit -m "chore: checkpoint Qwen evolution scaffold"
```

### Task 2: Repair and Audit the Synthetic Dataset

**Files:**
- Create: `tests/test_task_dataset.py`
- Create: `scripts/audit_tasks.py`
- Modify: `scripts/generate_tasks.py`
- Regenerate: `tasks/synthetic-16/**`

- [ ] **Step 1: Write regression tests for the three known defects**

Create `tests/test_task_dataset.py` with tests that:

```python
from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_tasks


class GeneratedTaskTests(unittest.TestCase):
    def generate(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "synthetic-16"
        with patch.object(generate_tasks, "TASKS_ROOT", root):
            generate_tasks.generate()
        return root

    def test_every_generated_python_file_parses(self) -> None:
        root = self.generate()
        failures = []
        for path in sorted(root.rglob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as error:
                failures.append(f"{path.relative_to(root)}:{error.lineno}:{error.msg}")
        self.assertEqual(failures, [])

    def test_required_result_expected_unique_word_count_is_three(self) -> None:
        root = self.generate()
        verifier = (
            root / "artifact-required-result" / "tests" / "verify.py"
        ).read_text(encoding="utf-8")
        self.assertIn("'unique_words': 3", verifier)
        self.assertNotIn("'unique_words': 4", verifier)

    def test_jsonl_fixture_keeps_escaped_newlines(self) -> None:
        root = self.generate()
        visible = (
            root / "verification-jsonl-summary" / "environment" / "test_visible.py"
        ).read_text(encoding="utf-8")
        self.assertIn(r"""summarize_jsonl('{"value":2}\n')""", visible)
```

- [ ] **Step 2: Run the regression tests and confirm RED**

Run:

```bash
python3 -m unittest tests.test_task_dataset -v
```

Expected: syntax and unique-word assertions fail against the current generator.

- [ ] **Step 3: Fix only the generator defects**

In `scripts/generate_tasks.py`:

```python
# verification-jsonl-summary strings written into generated Python
self.assertEqual(
    summarize_jsonl('{"value":2}\\n'),
    {'valid': 1, 'invalid': 0, 'total_value': 2},
)

text = '{"value":2}\\nnot-json\\n[]\\n{"value":true}\\n{"value":1.5}\\n\\n'

# execution-safe-relative-path strings written into generated Python
assert safe_relative_path(r'a\\b\\c.txt') == 'a/b/c.txt'
for value in ('', '/etc/passwd', '../x', 'a/../../x', r'C:\\temp\\x'):
    try:
        safe_relative_path(value)
    except ValueError:
        pass
    else:
        raise AssertionError(value)

# artifact-required-result oracle expectation
'unique_words': 3,

# every generated task executes in the pinned evaluator image
dockerfile = "FROM dsh-ollama-eval:node24-dsh011rc2\nWORKDIR /app\nCOPY . /app\n"
```

- [ ] **Step 4: Regenerate and verify GREEN**

Run:

```bash
python3 scripts/generate_tasks.py
python3 -m unittest tests.test_task_dataset -v
```

Expected: all regression tests pass and exactly 16 task directories exist.

- [ ] **Step 5: Add the full dataset auditor**

Implement `scripts/audit_tasks.py` with:

```python
@dataclass(frozen=True)
class TaskAudit:
    name: str
    files_ok: bool
    python_ok: bool
    initial_reward: float | None
    oracle_reward: float | None
    sha256: str


def audit_dataset(dataset: Path) -> dict[str, object]:
    """Validate 16 Harbor task trees and execute each verifier twice."""


def write_report(dataset: Path, output: Path) -> None:
    payload = audit_dataset(dataset)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
```

Use this internal mapping to install a correct `module.py` or
`build_result.py` into a temporary copy:

```python
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
```

For every task, invoke `tests/test.sh` with `HARBOR_WORKDIR`,
`HARBOR_TESTS_DIR`, and `HARBOR_LOGS_DIR`; require initial reward `0`, oracle
reward `1`, and process exit `0`. Hash each complete task tree using sorted
relative paths, modes, and bytes.

- [ ] **Step 6: Add auditor behavior tests**

Extend `tests/test_task_dataset.py` to assert:

```python
report = audit_tasks.audit_dataset(self.generate())
self.assertEqual(report["schema_version"], 1)
self.assertEqual(report["task_count"], 16)
self.assertEqual(report["failed_checks"], [])
self.assertEqual(
    {row["oracle_reward"] for row in report["tasks"]},
    {1.0},
)
self.assertEqual(
    {row["initial_reward"] for row in report["tasks"]},
    {0.0},
)
```

Tamper one generated verifier and assert that `failed_checks` names that task
and reports `verifier_syntax`.

- [ ] **Step 7: Run the complete dataset audit**

```bash
python3 -m unittest tests.test_task_dataset -v
python3 scripts/audit_tasks.py --output reports/preflight/task-audit.json
```

Expected: 16 tasks, zero failed checks, all initial rewards 0, all oracle
rewards 1.

- [ ] **Step 8: Commit**

```bash
git add scripts/generate_tasks.py scripts/audit_tasks.py tests/test_task_dataset.py tasks/synthetic-16 reports/preflight/task-audit.json
git commit -m "test: certify synthetic task dataset"
```

### Task 3: Capture DSH Trajectories and Target Usage

**Files:**
- Create: `seed/dsh_session.py`
- Create: `tests/fixtures/dsh-session.jsonl`
- Create: `tests/test_dsh_session.py`
- Modify: `seed/agent.py`
- Modify: `scripts/runtime_digest.py`

- [ ] **Step 1: Add a sanitized DSH session fixture**

Create `tests/fixtures/dsh-session.jsonl` containing one user message, two
assistant messages, one tool call/result pair, and these non-duplicated usage
records:

```json
{"type":"user/message","seq":2,"data":{"message":{"role":"user","content":[{"type":"text","text":"Repair module.py"}]}}}
{"type":"assistant/message","seq":4,"data":{"message":{"role":"assistant","content":[{"type":"tool-call","name":"read","arguments":"{\"file_path\":\"module.py\"}"}],"usage":{"inputTokens":100,"outputTokens":20,"cacheReadTokens":40}}}}
{"type":"tool/call","seq":5,"data":{"callId":"call-1","name":"read","arguments":"{\"file_path\":\"module.py\"}"}}
{"type":"tool/result","seq":6,"data":{"callId":"call-1","message":{"role":"tool","content":[{"type":"text","text":"api_key=secret-value"}]}}}
{"type":"assistant/message","seq":8,"data":{"message":{"role":"assistant","content":[{"type":"text","text":"Done."}],"usage":{"inputTokens":120,"outputTokens":15,"cacheReadTokens":50}}}}
```

- [ ] **Step 2: Write failing parser tests**

Create `tests/test_dsh_session.py` and assert:

```python
evidence = parse_session_files([fixture], sensitive_values={"secret-value"})
self.assertEqual(evidence.usage.input_tokens, 220)
self.assertEqual(evidence.usage.output_tokens, 35)
self.assertEqual(evidence.usage.cache_tokens, 90)
self.assertEqual(evidence.usage.requests, 2)
self.assertEqual(evidence.final_response, "Done.")
self.assertEqual([event["type"] for event in evidence.events], [
    "tool_call", "tool_result", "message"
])
self.assertNotIn("secret-value", json.dumps(evidence.events))
self.assertIn("[REDACTED]", json.dumps(evidence.events))
```

Also test malformed JSONL, duplicate `assistant/chunk` usage events, absent
usage, and bearer-token/endpoint redaction.

- [ ] **Step 3: Run parser tests and confirm RED**

```bash
python3 -m unittest tests.test_dsh_session -v
```

Expected: import failure because `seed.dsh_session` does not exist.

- [ ] **Step 4: Implement the parser**

Implement these stable interfaces in `seed/dsh_session.py`:

```python
@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cache_tokens: int
    output_tokens: int
    requests: int


@dataclass(frozen=True)
class SessionEvidence:
    events: list[dict[str, object]]
    final_response: str
    usage: Usage
    session_files: list[str]


def parse_session_files(
    paths: Iterable[Path],
    *,
    sensitive_values: set[str] | None = None,
) -> SessionEvidence:
    """Parse DSH JSONL once, count assistant/message usage, and redact evidence."""
```

Count usage only from `assistant/message.data.message.usage`, because
`assistant/chunk` repeats the same response usage. Normalize DSH
`user/message`, `assistant/message`, `tool/call`, and `tool/result` into ordered
events accepted by RSIHub's existing trajectory reader. Bound message,
argument, and observation lengths.

- [ ] **Step 5: Connect parser output to Harbor**

In `seed/agent.py`:

- stop deleting `context`;
- retain downloaded session JSONL as today;
- parse the retained session after every DSH exit;
- write `logs_dir/trajectory.json` with `{"schema_version": 1, "steps": events}`;
- set `context.n_input_tokens`, `n_cache_tokens`, `n_output_tokens`, and
  `cost_usd=0.0`;
- set metadata keys `request_count`, `configured_model`, and `session_files`;
- perform collection before raising for a nonzero DSH exit.

- [ ] **Step 6: Make the runtime digest cover the complete seed**

Replace individual seed entries in `scripts/runtime_digest.py` with sorted,
recursive hashing of every regular file under `seed/`, while continuing to
hash lockfiles, mutator scripts, and RSIHub patch files.

- [ ] **Step 7: Verify and commit**

```bash
python3 -m unittest tests.test_dsh_session -v
python3 scripts/runtime_digest.py
git diff --check
git add seed/agent.py seed/dsh_session.py scripts/runtime_digest.py tests/fixtures/dsh-session.jsonl tests/test_dsh_session.py
git commit -m "feat: retain DSH trajectories and token usage"
```

### Task 4: Pass Rich Evidence and Mutator Usage Through RSIHub

**Files:**
- Create: `tests/test_mutation_operator.py`
- Modify: `scripts/rsihub_qwen_prompt_mutate.py`
- Modify: `scripts/qwen_mutate.py`

- [ ] **Step 1: Write failing evidence-handoff tests**

Create `tests/test_mutation_operator.py` with a temporary `run_dir` containing
`feedback/evidence/selected.md` and assert:

```python
prompt, inputs = build_mutation_input(
    '{"failed": 1}',
    run_dir,
)
self.assertIn("Feedback bundle:", prompt)
self.assertIn("selected.md", prompt)
self.assertEqual(inputs[0]["path"], "feedback/evidence/selected.md")
self.assertEqual(len(inputs[0]["sha256"]), 64)
```

Add a test where the selected evidence contains task identifiers and
credentials; assert credentials are redacted while task evidence remains
available to the trusted mutator.

- [ ] **Step 2: Write failing usage propagation tests**

Test a successful subprocess output ending with:

```json
{"status":"updated","usage":{"wall_s":1.25,"prompt_tokens":433,"completion_tokens":583,"total_tokens":1016}}
```

Assert the operator `usage.json` equals:

```json
{
  "usd": 0,
  "wall_s": 1.25,
  "prompt_tokens": 433,
  "completion_tokens": 583,
  "total_tokens": 1016
}
```

Malformed or missing usage must make the mutate stage fail rather than silently
recording zero.

- [ ] **Step 3: Run tests and confirm RED**

```bash
PYTHONPATH=vendor/RSIHub/src python3 -m unittest tests.test_mutation_operator -v
```

- [ ] **Step 4: Implement evidence and usage handling**

In `scripts/rsihub_qwen_prompt_mutate.py`, add:

```python
def build_mutation_input(observation: str, run_dir: Path) -> tuple[str, list[dict[str, object]]]:
    """Reference the retained feedback bundle and hash every supplied file."""


def parse_command_usage(stdout: str, wall_s: float) -> dict[str, object]:
    """Read the final JSON object and require integer token fields."""
```

Write `mutate/evidence-inputs.json`; include a literal
`Feedback bundle: <absolute feedback directory>` line in the prompt passed to
`run_mutate`; merge parsed tokens with `usd: 0`; and preserve the raw sanitized
model output.

In `scripts/qwen_mutate.py`, keep `temperature=0`, enforce the existing
80–12000 character range and forbidden terms, and include a stable
`request_count: 1` in its usage object.

- [ ] **Step 5: Verify and commit**

```bash
PYTHONPATH=vendor/RSIHub/src python3 -m unittest tests.test_mutation_operator -v
git diff --check
git add scripts/qwen_mutate.py scripts/rsihub_qwen_prompt_mutate.py tests/test_mutation_operator.py
git commit -m "feat: bind mutation evidence and usage"
```

### Task 5: Configure Ollama and the Experiment Control Plane

**Files:**
- Create: `containers/evaluator/Dockerfile`
- Create: `scripts/experimentctl.py`
- Create: `tests/test_experimentctl.py`
- Modify: `.env.example`
- Modify: `scripts/api_smoke.py`
- Modify: `recipes/dsh_hill_climb/evolve.yaml`
- Modify: `seed/agent.py`
- Modify: `seed/dsh-qwen.patch.yml`
- Modify: `config/dsh-qwen.patch.yml`

- [ ] **Step 1: Write failing environment tests**

Create `tests/test_experimentctl.py` and assert:

```python
env = build_runtime_env(
    {
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1",
        "OLLAMA_API_KEY": "ollama",
        "OLLAMA_TARGET_MODEL": "qwen3:8b",
        "OLLAMA_MUTATOR_MODEL": "qwen3:14b",
        "UNRELATED_SECRET": "must-not-leak",
    },
    root=Path("/repo"),
)
self.assertNotIn("UNRELATED_SECRET", env)
self.assertEqual(env["OLLAMA_TARGET_MODEL"], "qwen3:8b")
self.assertEqual(env["OLLAMA_MUTATOR_MODEL"], "qwen3:14b")
self.assertEqual(env["DSH_BIN"], "/repo/node_modules/.bin/dsh")
self.assertEqual(env["EVOLVE_EXPERIMENT_ROOT"], "/repo")
```

Test missing or non-loopback Ollama URLs, wrong model identifiers, a stopped
daemon, a missing model, and malformed OpenAI-compatible responses.

- [ ] **Step 2: Run tests and confirm RED**

```bash
python3 -m unittest tests.test_experimentctl -v
```

- [ ] **Step 3: Implement the repository control plane**

Implement these commands in `scripts/experimentctl.py`:

```text
audit      run all model-free source and dataset checks
models     verify or explicitly pull the two Ollama model tags
probe      call target and mutator Ollama probes once
init       initialize a fresh workspace with a unique experiment id
preflight  validate an initialized workspace without model use
canary     run one target task and the local isolation probe
baseline   run generation zero and require Gate plus Sealed evidence
evolve     run through generation three
report     regenerate the final audit bundle without model calls
```

The script must:

- parse the outer `.env` without logging values;
- pass a fixed allowlist to subprocesses;
- set `DSH_BIN` to the absolute installed binary;
- set `EVOLVE_EXPERIMENT_ROOT` to the outer repository;
- compute and export `EVOLVE_RUNTIME_DIGEST`;
- require `OLLAMA_BASE_URL` to resolve to loopback;
- confirm exact `qwen3:8b` and `qwen3:14b` tags and record the Ollama-reported
  model digests and sizes;
- require the Ollama server process to start with `OLLAMA_NUM_PARALLEL=2`
  before accepting recipe `n_concurrent: 2`;
- reject an existing workspace for `init`;
- preserve every subprocess command, return code, start/end time, and sanitized
  stdout/stderr under `reports/control/`;
- stop on the first failed gate;
- never retry a model request automatically.

- [ ] **Step 4: Sanitize the DSH process environment**

Build the DSH command in `seed/agent.py` using `env -i` and only:

```text
HOME PATH TMPDIR LANG
DSH_HOME DSH_PERMISSION_MODE DSH_TELEMETRY_DISABLED
OLLAMA_BASE_URL OLLAMA_API_KEY OLLAMA_TARGET_MODEL
```

Do not expose `EVOLVE_HARBOR_TASKS` or unrelated parent environment values to
the model-operated DSH process. Add a model-free test that executes
`env -i PATH=<sanitized-path> node --version` and require it to resolve the
pinned Node 24.15.0 binary inside the evaluator image before any DSH canary.

- [ ] **Step 5: Configure both local model roles**

Use these local defaults in `.env.example`:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_CONTAINER_BASE_URL=http://host.docker.internal:11434/v1
OLLAMA_API_KEY=ollama
OLLAMA_TARGET_MODEL=qwen3:8b
OLLAMA_MUTATOR_MODEL=qwen3:14b
OLLAMA_NUM_PARALLEL=2
```

Derive `DSH_BIN` and `EVOLVE_EXPERIMENT_ROOT` from the checked-out repository
instead of requiring machine-specific paths in `.env`.

Update both DSH patch files and `scripts/api_smoke.py` to use the
`OLLAMA_*` names. Keep the OpenAI-compatible API protocol, route the host
mutator through loopback and the containerized target through
`host.docker.internal`, remove `budget_usd` and all capacity/reservation
settings, and retain token/time collection for reporting only. Set both
rollout and evaluator execution to Docker; no formal path may reference
`evolve.harbor_local:LocalEnvironment`.

`OLLAMA_NUM_PARALLEL` configures the daemon, not a client request. On macOS,
set it with `launchctl setenv OLLAMA_NUM_PARALLEL 2` and restart Ollama after
downloads finish. Preflight must reject `n_concurrent: 2` when the server was
not started with matching parallelism.

- [ ] **Step 6: Verify and commit**

```bash
python3 -m unittest tests.test_experimentctl -v
python3 scripts/experimentctl.py audit
git diff --check
git add .env.example config/dsh-qwen.patch.yml containers/evaluator/Dockerfile recipes/dsh_hill_climb/evolve.yaml seed/dsh-qwen.patch.yml seed/agent.py scripts/api_smoke.py scripts/experimentctl.py tests/test_experimentctl.py
git commit -m "feat: run both experiment roles through Ollama"
```

### Task 6: Prove the Local Confidentiality Boundary

**Files:**
- Create: `scripts/isolation_canary.py`
- Create: `tests/test_isolation_canary.py`
- Modify: `scripts/experimentctl.py`

- [ ] **Step 1: Write failing canary-result tests**

Test the pure result classifier with:

```python
self.assertEqual(
    classify_canary(exit_code=0, output="permission denied", leaked=False),
    "passed",
)
self.assertEqual(
    classify_canary(exit_code=0, output="SEALED_SENTINEL", leaked=True),
    "failed",
)
self.assertEqual(
    classify_canary(exit_code=1, output="connection refused", leaked=False),
    "ollama_unavailable",
)
```

Require the canary artifact to record the attempted path, session hash,
configured model, Ollama model digest, token usage, and whether the sentinel
appeared.

- [ ] **Step 2: Run tests and confirm RED**

```bash
python3 -m unittest tests.test_isolation_canary -v
```

- [ ] **Step 3: Implement the live canary**

`scripts/isolation_canary.py` must create a temporary task workspace with a
random sentinel in a sibling verifier directory, invoke DSH through the same
adapter and patch used by formal trials, ask it to attempt the exact sibling
read, and inspect both output and retained session events. Run the complete
read-edit-test multi-turn tool sequence three consecutive times with
`qwen3:8b`; every attempt must succeed before baseline.

The canary passes only when:

- the attempted read is denied;
- the sentinel is absent from stdout, stderr, and session logs;
- the DSH session remains otherwise functional;
- usage fields are complete.

Delete the temporary sentinel after writing a redacted result. Do not include
the sentinel value in the result file. There is no automatic model fallback:
an unstable `qwen3:8b` canary blocks the run. Any switch to another target,
including `qwen3:14b`, must start a new experiment with a new runtime identity;
7B and 30B models are outside this experiment and must not be pulled
implicitly.

- [ ] **Step 4: Verify and commit**

```bash
python3 -m unittest tests.test_isolation_canary -v
git diff --check
git add scripts/isolation_canary.py scripts/experimentctl.py tests/test_isolation_canary.py
git commit -m "test: gate local evaluator confidentiality"
```

### Task 7: Build the Audit Report

**Files:**
- Create: `scripts/build_report.py`
- Create: `tests/fixtures/audit-workspace/**`
- Create: `tests/test_build_report.py`
- Create: `reports/README.md`

- [ ] **Step 1: Write failing report tests**

Create a minimal fixture with baseline, three terminal generations, Gate and
Sealed evaluations, mutation diffs, and usage. Assert:

```python
report = build_report(fixture_workspace)
self.assertEqual(report["baseline"]["gate"]["score"], 0.5)
self.assertEqual(len(report["generations"]), 3)
self.assertEqual(report["final"]["sealed"]["expected_trials"], 4)
self.assertEqual(report["resources"]["target"]["total_tokens"], 12345)
self.assertEqual(report["resources"]["mutator"]["request_count"], 3)
self.assertEqual(report["audit"]["missing_artifacts"], [])
```

Delete one referenced file and assert report construction fails with its
relative path. Add a credential-shaped string to a fixture and assert the
published Markdown contains only `[REDACTED]`.

- [ ] **Step 2: Run tests and confirm RED**

```bash
python3 -m unittest tests.test_build_report -v
```

- [ ] **Step 3: Implement deterministic report generation**

`scripts/build_report.py` reads but never changes a workspace. It writes:

```text
reports/<experiment-id>/summary.json
reports/<experiment-id>/report.md
reports/<experiment-id>/manifest.sha256
reports/<experiment-id>/candidate-diffs/gen-1.diff
reports/<experiment-id>/candidate-diffs/gen-2.diff
reports/<experiment-id>/candidate-diffs/gen-3.diff
```

The JSON schema must contain:

```json
{
  "schema_version": 1,
  "experiment": {},
  "baseline": {"gate": {}, "sealed": {}},
  "generations": [],
  "final": {"champion": {}, "gate": {}, "sealed": {}},
  "resources": {
    "target": {},
    "mutator": {},
    "ollama_models": [],
    "host": {},
    "wall_s": 0,
    "disk_bytes": 0,
    "cost_usd": 0
  },
  "audit": {"artifact_hashes": {}, "missing_artifacts": [], "redactions": 0},
  "limitations": []
}
```

Reject incomplete expected trials, uncertified receipts, mismatched task sets,
missing generations, absent final Sealed evidence, malformed usage, or hashes
that do not match.

- [ ] **Step 4: Verify and commit**

```bash
python3 -m unittest tests.test_build_report -v
git diff --check
git add scripts/build_report.py tests/fixtures/audit-workspace tests/test_build_report.py reports/README.md
git commit -m "feat: generate auditable evolution report"
```

### Task 8: Validate the Complete Model-Free Stack

**Files:**
- Modify only if a failing test requires it: files introduced in Tasks 2–7

- [ ] **Step 1: Run all outer-repository tests**

```bash
python3 -m unittest discover -s tests -v
```

Expected: all tests pass with no network calls.

- [ ] **Step 2: Validate tasks and configuration**

```bash
python3 scripts/experimentctl.py audit
uv run --project vendor/RSIHub --frozen evolve recipe check recipes/dsh_hill_climb/evolve.yaml
git -C vendor/RSIHub apply --reverse --check --unidiff-zero ../../patches/rsihub-run-plan-expected-trials.patch
```

Expected: task audit passes, recipe is valid, and reverse patch check proves the
required RSIHub patch is already applied.

- [ ] **Step 3: Verify the frozen Train schedule covers all eight tasks**

Add an assertion to `tests/test_experimentctl.py` that computes generation
shuffle selections for generations 1–3 and verifies their union equals the
complete Train split. Run:

```bash
python3 -m unittest tests.test_experimentctl -v
```

Expected: eight distinct Train task names are covered across three generations.

- [ ] **Step 4: Verify repository hygiene**

```bash
git diff --check
git status --short
```

Expected: only deliberate changes are present; `.env` and generated workspaces
remain ignored.

### Task 9: Prepare Ollama and Certify a Fresh Workspace

**Files:**
- Generate: `workspaces/qwen-first-v1/**`
- Generate: `reports/control/**`

- [ ] **Step 1: Build and pin the isolated evaluator image**

Run:

```bash
docker build -t dsh-ollama-eval:node24-dsh011rc2 containers/evaluator
docker image inspect dsh-ollama-eval:node24-dsh011rc2
```

Expected: the image contains Node 24.15.0, Python 3, and
`@deepseek-ai/dsh@0.1.1-rc.2`; record its immutable image ID.

- [ ] **Step 2: Install and record both local models**

Run:

```bash
python3 scripts/experimentctl.py models --pull-missing
```

Expected: Ollama reports exact tags `qwen3:8b` and `qwen3:14b`; the control
receipt records Ollama version, model digests, sizes, quantization, and local
paths without making an inference request.

- [ ] **Step 3: Run both local API probes**

```bash
python3 scripts/experimentctl.py probe
```

Expected: target returns `qwen3:8b` and a valid tool call; mutator returns
`qwen3:14b` and valid JSON.

- [ ] **Step 4: Run the confidentiality canary**

```bash
python3 scripts/experimentctl.py canary --workspace workspaces/qwen-first-v1
```

Expected: three consecutive `passed` attempts, no sentinel leakage, complete
target usage, and the required read-edit-test tool sequence in every retained
trajectory. A failed attempt must start a new experiment after the model
decision; it must not continue the current lineage.

- [ ] **Step 5: Initialize the workspace**

```bash
python3 scripts/experimentctl.py init --workspace workspaces/qwen-first-v1
```

The command internally runs:

```bash
uv run --project vendor/RSIHub --frozen evolve preflight workspaces/qwen-first-v1 --recipe-path recipes/dsh_hill_climb/evolve.yaml --seed seed --dataset tasks/synthetic-16
uv run --project vendor/RSIHub --frozen evolve init workspaces/qwen-first-v1 --recipe-path recipes/dsh_hill_climb/evolve.yaml --seed seed --dataset tasks/synthetic-16
```

Expected: a new experiment ID, clean `gen/0`, matching dataset/runtime pins, and
no copied secret file.

- [ ] **Step 6: Run initialized preflight**

```bash
python3 scripts/experimentctl.py preflight --workspace workspaces/qwen-first-v1
```

Expected: configuration, runtime, runtime digest, evaluation contract,
dependency tools, and runtime environment all pass without a model call.

### Task 10: Run Baseline and Three Generations

**Files:**
- Generate: `workspaces/qwen-first-v1/runs/**`
- Generate: `workspaces/qwen-first-v1/archive.jsonl`
- Generate: `workspaces/qwen-first-v1/best_ever.json`
- Generate: `reports/control/**`

- [x] **Step 1: Certify baseline Gate and Sealed**

```bash
python3 scripts/experimentctl.py baseline --workspace workspaces/qwen-first-v1
```

Expected:

- generation zero has four scoreable Gate trials;
- generation zero has four scoreable Sealed anchor trials;
- all task/runtime/evaluator fingerprints are present;
- `best_ever.json` names generation zero.

- [x] **Step 2: Run all three generations in one resumable driver call**

```bash
python3 scripts/experimentctl.py evolve --workspace workspaces/qwen-first-v1
```

Expected:

- gen/1, gen/2, and gen/3 each have one parent and one prompt-only patch;
- every generation has four Train rollout trials and four Gate trials;
- each gate decision is recorded even when rejected;
- the union of Train task names is all eight Train tasks;
- the final champion has a four-trial Sealed anchor;
- Ollama daemon, model, or host-resource failure stops immediately without an
  automatic retry.

- [x] **Step 3: Verify RSIHub state**

Run with the same exported `EVOLVE_HOME` used by the launcher:

```bash
workspaces/qwen-first-v1/evolve verify workspaces/qwen-first-v1
workspaces/qwen-first-v1/evolve status workspaces/qwen-first-v1
workspaces/qwen-first-v1/evolve assert-run workspaces/qwen-first-v1 --through 3
```

Expected: integrity `ok`, a non-null champion, and run assertion passing through
generation three.

### Task 11: Produce and Audit the Final Deliverables

**Files:**
- Generate: `reports/qwen-first-v1/summary.json`
- Generate: `reports/qwen-first-v1/report.md`
- Generate: `reports/qwen-first-v1/manifest.sha256`
- Generate: `reports/qwen-first-v1/candidate-diffs/*.diff`
- Modify: `README.md`

- [ ] **Step 1: Build the report without model calls**

```bash
python3 scripts/experimentctl.py report --workspace workspaces/qwen-first-v1
```

Expected: report builder exits zero and `audit.missing_artifacts` is empty.

- [ ] **Step 2: Independently verify hashes and required outcomes**

```bash
shasum -a 256 -c reports/qwen-first-v1/manifest.sha256
python3 scripts/build_report.py --check workspaces/qwen-first-v1 reports/qwen-first-v1
python3 -m unittest discover -s tests -v
```

Expected: every manifest entry is `OK`, report check passes, and all local tests
pass.

- [ ] **Step 3: Add the final experiment pointer**

Append to `README.md`:

```markdown
## First completed run

- Report: `reports/qwen-first-v1/report.md`
- Machine-readable summary: `reports/qwen-first-v1/summary.json`
- Artifact manifest: `reports/qwen-first-v1/manifest.sha256`
```

- [ ] **Step 4: Commit reproducible deliverables**

```bash
git add README.md reports/qwen-first-v1
git diff --cached --check
git commit -m "docs: publish first Qwen evolution results"
```

- [ ] **Step 5: Perform the completion audit**

Verify each original requirement against authoritative evidence:

```text
16 tasks              task audit + frozen dataset manifest
qwen3:8b              trial agent_info + DSH request headers + Ollama digest
qwen3:14b             mutate output + configured/returned model + Ollama digest
baseline              certified gen/0 Gate record
three generations     gen/1, gen/2, gen/3 terminal lineage records
Gate retest           candidate evaluation records and task vectors
Sealed retest         baseline and final anchor records
logs                  hashed retained DSH/Harbor/operator artifacts
scores                certified archive and summary
candidate differences three prompt diffs and commit identities
resource consumption  target/mutator tokens, requests, time, disk
conclusion            report claims limited to matching task-set cohorts
local-only inference  loopback endpoint receipts and no remote model route
```

Only after every row is proven should the persistent goal be marked complete.

### Task 12: Publish the Feishu-Style HTML Visualization (Stage 1 finish)

Render Task 11's `summary.json` into one shareable HTML page with multiple
charts, matching the presentation style of the Feishu "interesting evolution
shares" section. Read only certified report data; make no model calls and do not
modify the workspace.

**Files:**
- Create: `scripts/build_visualization.py`
- Create: `tests/fixtures/summary-sample.json`
- Create: `tests/test_build_visualization.py`
- Generate: `reports/qwen-first-v1/visualization.html`

- [ ] **Step 1: Write failing visualization tests**

Create `tests/fixtures/summary-sample.json` mirroring Task 7's `summary.json`
schema (baseline, three generations, Gate/Sealed scores, candidate diffs,
resource usage, hypothesis/expected_effect). Create
`tests/test_build_visualization.py` and assert:

```python
html = render_html(load_summary(fixture))
self.assertIn("<!DOCTYPE html>", html)
self.assertIn("score-chart", html)
self.assertIn("gen-1", html)
self.assertEqual(html.count("candidate-diff"), 3)
self.assertNotIn("secret-value", html)
```

Add a test asserting that a `summary.json` missing a required key makes
`render_html` raise and name the missing key rather than emit a partial page.

- [ ] **Step 2: Run tests and confirm RED**

```bash
python3 -m unittest tests.test_build_visualization -v
```

Expected: failure because `scripts/build_visualization.py` does not exist.

- [ ] **Step 3: Implement deterministic HTML rendering**

`scripts/build_visualization.py` reads only
`reports/<experiment-id>/summary.json` and writes a single, self-contained
`visualization.html` (inline SVG or a small inline script; no external CDN)
containing:

- a score-curve region (`score-chart`): baseline→gen1→gen2→gen3 Gate and Sealed
  score lines with the champion marked;
- a generation-overview region: per-generation parent/child, gate decision
  (accepted/rejected), and whether it became champion;
- a candidate-diff region (`candidate-diff` ×3): each generation's
  `target/prompt.md` text diff;
- a resource-consumption region: comparative bars for target/mutator tokens,
  request count, wall-time, and disk;
- an improvement-hypothesis region: each generation's hypothesis /
  expected_effect against the actual Gate outcome.

Apply the same redaction used by the report; on missing data, raise rather than
silently skip.

- [ ] **Step 4: Generate and verify the artifact**

```bash
python3 scripts/build_visualization.py --workspace workspaces/qwen-first-v1 --report reports/qwen-first-v1
python3 -m unittest tests.test_build_visualization -v
```

Expected: `reports/qwen-first-v1/visualization.html` is generated, tests pass,
and the page opens offline in a browser.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_visualization.py tests/fixtures/summary-sample.json tests/test_build_visualization.py reports/qwen-first-v1/visualization.html
git diff --cached --check
git commit -m "feat: visualize evolution results as shareable HTML"
```
