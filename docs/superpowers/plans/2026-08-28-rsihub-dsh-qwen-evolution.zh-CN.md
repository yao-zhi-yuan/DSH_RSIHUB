# RSIHub + DSH + Qwen 首轮自进化实施计划（中文版）

> 本文件是 [2026-08-28-rsihub-dsh-qwen-evolution.md](2026-08-28-rsihub-dsh-qwen-evolution.md) 的中文对照版本。代码块、命令、文件路径与标识符保持原样，仅翻译说明性文字；如与英文原文出现分歧，以英文原文为准。

> **面向执行代理：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐条实施本计划。各步骤使用复选框（`- [ ]`）语法便于跟踪。

**目标：** 产出一次可复现的 RSIHub Hill Climb 运行：其中搭载本地 Ollama `qwen3:8b` 的 DSH 在冻结的 16 任务套件上被评估，本地 Ollama `qwen3:14b` 生成三个「仅改 prompt」的候选，并附带完整的 Gate、Sealed、血缘（lineage）、轨迹（trace）与资源证据。

**架构：** 保持现有外层仓库为唯一事实源，并保留失败的 `experiment/` 作为历史证据。新增标准库 Python 的校验、编排、会话解析与报告工具；只有在「无模型门禁」通过后，才把这些输入冻结进新的 workspace。血缘使用 RSIHub 原生驱动与 archive，另设独立的报告构建器，在不调用模型的前提下校验并汇总所保留的证据。

**技术栈：** Python 3.12 标准库与 `unittest`、RSIHub 位于提交 `467f5b8`、Harbor 0.18.0、DSH npm 包 `0.1.1-rc.2`、Node 24、Ollama 0.33.1 及其 OpenAI 兼容 API。

---

## 阶段划分与最终产物（2026-08-28 对齐补充）

> 本小节为中文版在与用户对齐后新增，英文原文暂未包含。宏观目的：对 DSH 跑一遍 RSIHub 评测 → 看到至少一次代际改进 → 产出对标飞书分享的可视化。

**阶段一（本轮，prompt-only）：** 变异模型仅可修改 `target/prompt.md`，先打通 baseline → 三代 → Gate/Sealed → 审计报告 → **HTML 可视化**的完整闭环。对应任务 1–12。这是本轮要交付并验证的范围。

**阶段二（后续，配置/插件级）：** 在闭环稳定后，把可进化面扩展到 `cordis.yml` 配置、`plugins/*.mjs`、`skills/*.md`，以复刻飞书文档中「代际结构变化 + 多文件 diff + 自写插件」那类更丰富的进化。阶段二需要另行修改 recipe 的可写路径白名单与 runtime 身份，不在本轮范围内，届时单独立计划。

**可视化最终产物（对标飞书，HTML 多图）：** 见任务 12。至少包含：
- 分数曲线：baseline → 各代的 Gate 与 Sealed 分数折线；
- 代际概览：每代父子关系、gate 决策（接受/拒绝）、champion 标记；
- 候选差异：每代 `target/prompt.md` 的文本 diff（阶段二为多文件 diff stat）；
- 资源消耗：target/mutator 的 tokens、请求数、wall-time、磁盘；
- 改进假设：变异模型给出的 hypothesis / expected_effect 与实际结果对照。

---

### 任务 1：建立可复现的源码基线

**涉及文件：**
- 修改：`.gitignore`
- 创建：`README.md`
- 纳入版本管理：`.env.example`、`config/`、`package.json`、`package-lock.json`、`patches/`、`recipes/`、`scripts/`、`seed/`、`tasks/`、`docs/`

- [ ] **步骤 1：扩展「生成态产物」的忽略规则**

在保留既有密钥与依赖忽略规则的前提下，追加以下锚定条目：

```gitignore
/.worktrees/
/reports/raw/
```

- [ ] **步骤 2：记录仓库入口点**

创建 `README.md`，包含以下命令与约束：

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

- [ ] **步骤 3：暂存前检查是否误带凭据**

运行：

```bash
rg -n --hidden \
  -g '!.env' -g '!node_modules/**' -g '!vendor/**' -g '!experiment/**' \
  '(Bearer [A-Za-z0-9._~+/=-]{16,}|(?:API_KEY|TOKEN|SECRET|PASSWORD)=[^<$[:space:]][^[:space:]]*)' .
```

预期：不出现任何明文凭据值。

- [ ] **步骤 4：纳入既有的可复现性输入**

运行：

```bash
git add .gitignore .env.example README.md config package.json package-lock.json patches recipes scripts seed tasks docs
git diff --cached --check
git status --short
```

预期：`.env`、`vendor/`、`experiment/`、`runs/`、`workspaces/` 不会被暂存。

- [ ] **步骤 5：提交源码基线**

```bash
git commit -m "chore: checkpoint Qwen evolution scaffold"
```

### 任务 2：修复并审计合成数据集

**涉及文件：**
- 创建：`tests/test_task_dataset.py`
- 创建：`scripts/audit_tasks.py`
- 修改：`scripts/generate_tasks.py`
- 重新生成：`tasks/synthetic-16/**`

- [ ] **步骤 1：为三个已知缺陷编写回归测试**

创建 `tests/test_task_dataset.py`，其测试应：

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

- [ ] **步骤 2：运行回归测试并确认 RED（失败）**

运行：

```bash
python3 -m unittest tests.test_task_dataset -v
```

预期：针对当前生成器，语法与「唯一词计数」断言应失败。

- [ ] **步骤 3：仅修复生成器缺陷**

在 `scripts/generate_tasks.py` 中：

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

- [ ] **步骤 4：重新生成并确认 GREEN（通过）**

运行：

```bash
python3 scripts/generate_tasks.py
python3 -m unittest tests.test_task_dataset -v
```

预期：所有回归测试通过，且恰好存在 16 个任务目录。

- [ ] **步骤 5：新增完整的数据集审计器**

实现 `scripts/audit_tasks.py`，包含：

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

使用以下内部映射，将正确的 `module.py` 或 `build_result.py` 安装到临时副本中：

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

对每个任务，使用 `HARBOR_WORKDIR`、`HARBOR_TESTS_DIR`、`HARBOR_LOGS_DIR` 调用 `tests/test.sh`；要求初始 reward 为 `0`、oracle reward 为 `1`、进程退出码为 `0`。使用排序后的相对路径、文件模式与字节内容，对每棵完整任务树做哈希。

- [ ] **步骤 6：新增审计器行为测试**

扩展 `tests/test_task_dataset.py`，断言：

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

篡改某一个生成的 verifier，并断言 `failed_checks` 指名该任务并报告 `verifier_syntax`。

- [ ] **步骤 7：运行完整数据集审计**

```bash
python3 -m unittest tests.test_task_dataset -v
python3 scripts/audit_tasks.py --output reports/preflight/task-audit.json
```

预期：16 个任务、零失败检查、所有初始 reward 为 0、所有 oracle reward 为 1。

- [ ] **步骤 8：提交**

```bash
git add scripts/generate_tasks.py scripts/audit_tasks.py tests/test_task_dataset.py tasks/synthetic-16 reports/preflight/task-audit.json
git commit -m "test: certify synthetic task dataset"
```

### 任务 3：捕获 DSH 轨迹与 target 用量

**涉及文件：**
- 创建：`seed/dsh_session.py`
- 创建：`tests/fixtures/dsh-session.jsonl`
- 创建：`tests/test_dsh_session.py`
- 修改：`seed/agent.py`
- 修改：`scripts/runtime_digest.py`

- [ ] **步骤 1：新增一个已脱敏的 DSH 会话 fixture**

创建 `tests/fixtures/dsh-session.jsonl`，包含一条用户消息、两条助手消息、一对 tool 调用/结果，以及以下「不重复计数」的 usage 记录：

```json
{"type":"user/message","seq":2,"data":{"message":{"role":"user","content":[{"type":"text","text":"Repair module.py"}]}}}
{"type":"assistant/message","seq":4,"data":{"message":{"role":"assistant","content":[{"type":"tool-call","name":"read","arguments":"{\"file_path\":\"module.py\"}"}],"usage":{"inputTokens":100,"outputTokens":20,"cacheReadTokens":40}}}}
{"type":"tool/call","seq":5,"data":{"callId":"call-1","name":"read","arguments":"{\"file_path\":\"module.py\"}"}}
{"type":"tool/result","seq":6,"data":{"callId":"call-1","message":{"role":"tool","content":[{"type":"text","text":"api_key=secret-value"}]}}}
{"type":"assistant/message","seq":8,"data":{"message":{"role":"assistant","content":[{"type":"text","text":"Done."}],"usage":{"inputTokens":120,"outputTokens":15,"cacheReadTokens":50}}}}
```

- [ ] **步骤 2：编写会失败的解析器测试**

创建 `tests/test_dsh_session.py`，断言：

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

同时测试：损坏的 JSONL、重复的 `assistant/chunk` usage 事件、缺失 usage、以及 bearer token / endpoint 的脱敏。

- [ ] **步骤 3：运行解析器测试并确认 RED**

```bash
python3 -m unittest tests.test_dsh_session -v
```

预期：因 `seed.dsh_session` 尚不存在而导入失败。

- [ ] **步骤 4：实现解析器**

在 `seed/dsh_session.py` 中实现以下稳定接口：

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

仅从 `assistant/message.data.message.usage` 统计 usage，因为 `assistant/chunk` 会重复同一条响应的 usage。将 DSH 的 `user/message`、`assistant/message`、`tool/call`、`tool/result` 规范化为有序事件，使其能被 RSIHub 既有的轨迹读取器接受。对消息、参数与观测的长度设上界。

- [ ] **步骤 5：把解析器输出接入 Harbor**

在 `seed/agent.py` 中：

- 不再删除 `context`；
- 像现在一样保留下载的会话 JSONL；
- 每次 DSH 退出后解析所保留的会话；
- 写入 `logs_dir/trajectory.json`，内容为 `{"schema_version": 1, "steps": events}`；
- 设置 `context.n_input_tokens`、`n_cache_tokens`、`n_output_tokens` 以及 `cost_usd=0.0`；
- 设置元数据键 `request_count`、`configured_model`、`session_files`；
- 在因 DSH 非零退出码抛错之前，先完成证据收集。

- [ ] **步骤 6：让运行时摘要覆盖完整 seed**

在 `scripts/runtime_digest.py` 中，用「对 `seed/` 下所有普通文件的排序递归哈希」替换逐条 seed 条目，同时继续对 lockfile、mutator 脚本与 RSIHub patch 文件做哈希。

- [ ] **步骤 7：验证并提交**

```bash
python3 -m unittest tests.test_dsh_session -v
python3 scripts/runtime_digest.py
git diff --check
git add seed/agent.py seed/dsh_session.py scripts/runtime_digest.py tests/fixtures/dsh-session.jsonl tests/test_dsh_session.py
git commit -m "feat: retain DSH trajectories and token usage"
```

### 任务 4：让丰富证据与 mutator 用量贯穿 RSIHub

**涉及文件：**
- 创建：`tests/test_mutation_operator.py`
- 修改：`scripts/rsihub_qwen_prompt_mutate.py`
- 修改：`scripts/qwen_mutate.py`

- [ ] **步骤 1：编写会失败的「证据交接」测试**

创建 `tests/test_mutation_operator.py`，用一个含 `feedback/evidence/selected.md` 的临时 `run_dir`，断言：

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

增加一个测试：所选证据中包含任务标识符与凭据；断言凭据被脱敏，而任务证据仍对「可信 mutator」可见。

- [ ] **步骤 2：编写会失败的「用量传播」测试**

测试某次成功的子进程输出，其结尾为：

```json
{"status":"updated","usage":{"wall_s":1.25,"prompt_tokens":433,"completion_tokens":583,"total_tokens":1016}}
```

断言算子的 `usage.json` 等于：

```json
{
  "usd": 0,
  "wall_s": 1.25,
  "prompt_tokens": 433,
  "completion_tokens": 583,
  "total_tokens": 1016
}
```

用量若损坏或缺失，必须让 mutate 阶段失败，而不是静默记为零。

- [ ] **步骤 3：运行测试并确认 RED**

```bash
PYTHONPATH=vendor/RSIHub/src python3 -m unittest tests.test_mutation_operator -v
```

- [ ] **步骤 4：实现证据与用量处理**

在 `scripts/rsihub_qwen_prompt_mutate.py` 中新增：

```python
def build_mutation_input(observation: str, run_dir: Path) -> tuple[str, list[dict[str, object]]]:
    """Reference the retained feedback bundle and hash every supplied file."""


def parse_command_usage(stdout: str, wall_s: float) -> dict[str, object]:
    """Read the final JSON object and require integer token fields."""
```

写入 `mutate/evidence-inputs.json`；在传给 `run_mutate` 的 prompt 中包含一行字面量 `Feedback bundle: <absolute feedback directory>`；把解析出的 token 与 `usd: 0` 合并；并保留经脱敏的原始模型输出。

在 `scripts/qwen_mutate.py` 中，保持 `temperature=0`，强制既有的 80–12000 字符范围与禁用词，并在其 usage 对象中包含稳定的 `request_count: 1`。

- [ ] **步骤 5：验证并提交**

```bash
PYTHONPATH=vendor/RSIHub/src python3 -m unittest tests.test_mutation_operator -v
git diff --check
git add scripts/qwen_mutate.py scripts/rsihub_qwen_prompt_mutate.py tests/test_mutation_operator.py
git commit -m "feat: bind mutation evidence and usage"
```

### 任务 5：配置 Ollama 与实验控制面

**涉及文件：**
- 创建：`containers/evaluator/Dockerfile`
- 创建：`scripts/experimentctl.py`
- 创建：`tests/test_experimentctl.py`
- 修改：`.env.example`
- 修改：`scripts/api_smoke.py`
- 修改：`recipes/dsh_hill_climb/evolve.yaml`
- 修改：`seed/agent.py`
- 修改：`seed/dsh-qwen.patch.yml`
- 修改：`config/dsh-qwen.patch.yml`

- [ ] **步骤 1：编写会失败的环境测试**

创建 `tests/test_experimentctl.py`，断言：

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

测试：缺失或非 loopback 的 Ollama URL、错误的模型标识、守护进程未启动、模型缺失、以及格式错误的 OpenAI 兼容响应。

- [ ] **步骤 2：运行测试并确认 RED**

```bash
python3 -m unittest tests.test_experimentctl -v
```

- [ ] **步骤 3：实现仓库控制面**

在 `scripts/experimentctl.py` 中实现以下命令：

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

该脚本必须：

- 解析外层 `.env` 但不记录其值；
- 向子进程传入固定白名单；
- 将 `DSH_BIN` 设为已安装二进制的绝对路径；
- 将 `EVOLVE_EXPERIMENT_ROOT` 设为外层仓库；
- 计算并导出 `EVOLVE_RUNTIME_DIGEST`；
- 要求 `OLLAMA_BASE_URL` 解析到 loopback；
- 确认精确的 `qwen3:8b` 与 `qwen3:14b` 标签，并记录 Ollama 报告的模型 digest 与大小；
- 在接受 recipe 的 `n_concurrent: 2` 之前，要求 Ollama 服务端以 `OLLAMA_NUM_PARALLEL=2` 启动；
- `init` 时若 workspace 已存在则拒绝；
- 将每次子进程的命令、返回码、起止时间以及脱敏后的 stdout/stderr 保存到 `reports/control/`；
- 在首个失败门禁处停止；
- 绝不自动重试任何模型请求。

- [ ] **步骤 4：净化 DSH 进程环境**

在 `seed/agent.py` 中使用 `env -i` 构建 DSH 命令，且仅包含：

```text
HOME PATH TMPDIR LANG
DSH_HOME DSH_PERMISSION_MODE DSH_TELEMETRY_DISABLED
OLLAMA_BASE_URL OLLAMA_API_KEY OLLAMA_TARGET_MODEL
```

不要把 `EVOLVE_HARBOR_TASKS` 或无关的父进程环境值暴露给「由模型操作的」DSH 进程。新增一个无模型测试，执行 `env -i PATH=<sanitized-path> node --version`，并要求它在任何 DSH canary 之前，能在 evaluator 镜像内解析到固定的 Node 24.15.0 二进制。

- [ ] **步骤 5：配置两个本地模型角色**

在 `.env.example` 中使用以下本地默认值：

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_CONTAINER_BASE_URL=http://host.docker.internal:11434/v1
OLLAMA_API_KEY=ollama
OLLAMA_TARGET_MODEL=qwen3:8b
OLLAMA_MUTATOR_MODEL=qwen3:14b
OLLAMA_NUM_PARALLEL=2
```

从已检出的仓库推导 `DSH_BIN` 与 `EVOLVE_EXPERIMENT_ROOT`，而不是在 `.env` 中要求机器相关的路径。

更新两个 DSH patch 文件与 `scripts/api_smoke.py` 使用 `OLLAMA_*` 命名。保持 OpenAI 兼容 API 协议，将宿主 mutator 走 loopback、容器化 target 走 `host.docker.internal`，移除 `budget_usd` 及所有容量/预留设置，并仅为报告用途保留 token/时间采集。将 rollout 与 evaluator 的执行都设为 Docker；任何正式路径都不得引用 `evolve.harbor_local:LocalEnvironment`。

`OLLAMA_NUM_PARALLEL` 配置的是守护进程，而非客户端请求。在 macOS 上用 `launchctl setenv OLLAMA_NUM_PARALLEL 2` 设置，并在下载完成后重启 Ollama。当服务端未以匹配的并行度启动时，preflight 必须拒绝 `n_concurrent: 2`。

- [ ] **步骤 6：验证并提交**

```bash
python3 -m unittest tests.test_experimentctl -v
python3 scripts/experimentctl.py audit
git diff --check
git add .env.example config/dsh-qwen.patch.yml containers/evaluator/Dockerfile recipes/dsh_hill_climb/evolve.yaml seed/dsh-qwen.patch.yml seed/agent.py scripts/api_smoke.py scripts/experimentctl.py tests/test_experimentctl.py
git commit -m "feat: run both experiment roles through Ollama"
```

### 任务 6：证明本地机密性边界

**涉及文件：**
- 创建：`scripts/isolation_canary.py`
- 创建：`tests/test_isolation_canary.py`
- 修改：`scripts/experimentctl.py`

- [ ] **步骤 1：编写会失败的「canary 结果」测试**

用以下用例测试纯结果分类器：

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

要求 canary 产物记录：尝试读取的路径、会话哈希、配置模型、Ollama 模型 digest、token 用量，以及 sentinel 是否出现。

- [ ] **步骤 2：运行测试并确认 RED**

```bash
python3 -m unittest tests.test_isolation_canary -v
```

- [ ] **步骤 3：实现真实 canary**

`scripts/isolation_canary.py` 必须创建一个临时任务 workspace，在同级 verifier 目录里放入一个随机 sentinel，通过与正式 trial 相同的 adapter 与 patch 调用 DSH，要求其尝试精确读取该同级文件，并同时检查输出与所保留的会话事件。用 `qwen3:8b` 连续三次运行完整的 read-edit-test 多轮工具序列；每次尝试都必须在 baseline 之前成功。

canary 仅在以下条件全部满足时才算通过：

- 该尝试读取被拒绝；
- sentinel 不出现在 stdout、stderr 与会话日志中；
- DSH 会话在其他方面仍然可用；
- usage 字段完整。

写出脱敏结果后删除临时 sentinel。结果文件中不得包含 sentinel 值。不存在自动模型回退：不稳定的 `qwen3:8b` canary 会阻断本次运行。任何切换到其他 target（包括 `qwen3:14b`）都必须以新的运行时身份开启一个新实验；7B 与 30B 模型不在本实验范围内，且不得被隐式拉取。

- [ ] **步骤 4：验证并提交**

```bash
python3 -m unittest tests.test_isolation_canary -v
git diff --check
git add scripts/isolation_canary.py scripts/experimentctl.py tests/test_isolation_canary.py
git commit -m "test: gate local evaluator confidentiality"
```

### 任务 7：构建审计报告

**涉及文件：**
- 创建：`scripts/build_report.py`
- 创建：`tests/fixtures/audit-workspace/**`
- 创建：`tests/test_build_report.py`
- 创建：`reports/README.md`

- [ ] **步骤 1：编写会失败的报告测试**

创建一个最小 fixture，包含 baseline、三个终态 generation、Gate 与 Sealed 评估、mutation diff 与用量。断言：

```python
report = build_report(fixture_workspace)
self.assertEqual(report["baseline"]["gate"]["score"], 0.5)
self.assertEqual(len(report["generations"]), 3)
self.assertEqual(report["final"]["sealed"]["expected_trials"], 4)
self.assertEqual(report["resources"]["target"]["total_tokens"], 12345)
self.assertEqual(report["resources"]["mutator"]["request_count"], 3)
self.assertEqual(report["audit"]["missing_artifacts"], [])
```

删除一个被引用的文件，断言报告构建失败并给出其相对路径。向某个 fixture 加入一段「疑似凭据」的字符串，断言发布的 Markdown 中只出现 `[REDACTED]`。

- [ ] **步骤 2：运行测试并确认 RED**

```bash
python3 -m unittest tests.test_build_report -v
```

- [ ] **步骤 3：实现确定性的报告生成**

`scripts/build_report.py` 只读、绝不修改 workspace。它写出：

```text
reports/<experiment-id>/summary.json
reports/<experiment-id>/report.md
reports/<experiment-id>/manifest.sha256
reports/<experiment-id>/candidate-diffs/gen-1.diff
reports/<experiment-id>/candidate-diffs/gen-2.diff
reports/<experiment-id>/candidate-diffs/gen-3.diff
```

JSON schema 必须包含：

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

对以下情况予以拒绝：expected trials 不完整、receipt 未认证、任务集不匹配、缺失 generation、缺失最终 Sealed 证据、用量格式错误、或哈希不匹配。

- [ ] **步骤 4：验证并提交**

```bash
python3 -m unittest tests.test_build_report -v
git diff --check
git add scripts/build_report.py tests/fixtures/audit-workspace tests/test_build_report.py reports/README.md
git commit -m "feat: generate auditable evolution report"
```

### 任务 8：验证完整的「无模型」技术栈

**涉及文件：**
- 仅当某个失败测试需要时才修改：任务 2–7 引入的文件

- [ ] **步骤 1：运行外层仓库全部测试**

```bash
python3 -m unittest discover -s tests -v
```

预期：全部测试通过，且无网络调用。

- [ ] **步骤 2：校验任务与配置**

```bash
python3 scripts/experimentctl.py audit
uv run --project vendor/RSIHub --frozen evolve recipe check recipes/dsh_hill_climb/evolve.yaml
git -C vendor/RSIHub apply --reverse --check --unidiff-zero ../../patches/rsihub-run-plan-expected-trials.patch
```

预期：任务审计通过、recipe 有效、反向 patch 检查证明所需的 RSIHub patch 已应用。

- [ ] **步骤 3：验证冻结的 Train 调度覆盖全部八个任务**

在 `tests/test_experimentctl.py` 中新增断言：计算第 1–3 代的 generation shuffle 选择，并验证其并集等于完整的 Train split。运行：

```bash
python3 -m unittest tests.test_experimentctl -v
```

预期：三代之间覆盖八个不同的 Train 任务名。

- [ ] **步骤 4：验证仓库卫生**

```bash
git diff --check
git status --short
```

预期：只存在有意为之的改动；`.env` 与生成的 workspace 仍被忽略。

### 任务 9：准备 Ollama 并认证一个全新的 workspace

**涉及文件：**
- 生成：`workspaces/qwen-first-v1/**`
- 生成：`reports/control/**`

- [ ] **步骤 1：构建并固定隔离 evaluator 镜像**

运行：

```bash
docker build -t dsh-ollama-eval:node24-dsh011rc2 containers/evaluator
docker image inspect dsh-ollama-eval:node24-dsh011rc2
```

预期：镜像内含 Node 24.15.0、Python 3 与 `@deepseek-ai/dsh@0.1.1-rc.2`；记录其不可变 image ID。

- [ ] **步骤 2：安装并记录两个本地模型**

运行：

```bash
python3 scripts/experimentctl.py models --pull-missing
```

预期：Ollama 报告精确标签 `qwen3:8b` 与 `qwen3:14b`；控制 receipt 记录 Ollama 版本、模型 digest、大小、量化与本地路径，且不发起推理请求。

- [ ] **步骤 3：运行两个本地 API 探测**

```bash
python3 scripts/experimentctl.py probe
```

预期：target 返回 `qwen3:8b` 与一次有效工具调用；mutator 返回 `qwen3:14b` 与有效 JSON。

- [ ] **步骤 4：运行机密性 canary**

```bash
python3 scripts/experimentctl.py canary --workspace workspaces/qwen-first-v1
```

预期：连续三次 `passed`、无 sentinel 泄漏、target 用量完整，且每条保留轨迹都含所需的 read-edit-test 工具序列。某次尝试失败必须在「模型决策」之后开启新实验；不得延续当前血缘。

- [ ] **步骤 5：初始化 workspace**

```bash
python3 scripts/experimentctl.py init --workspace workspaces/qwen-first-v1
```

该命令内部运行：

```bash
uv run --project vendor/RSIHub --frozen evolve preflight workspaces/qwen-first-v1 --recipe-path recipes/dsh_hill_climb/evolve.yaml --seed seed --dataset tasks/synthetic-16
uv run --project vendor/RSIHub --frozen evolve init workspaces/qwen-first-v1 --recipe-path recipes/dsh_hill_climb/evolve.yaml --seed seed --dataset tasks/synthetic-16
```

预期：一个新实验 ID、干净的 `gen/0`、匹配的 dataset/runtime 固定项，且未复制任何密钥文件。

- [ ] **步骤 6：运行已初始化的 preflight**

```bash
python3 scripts/experimentctl.py preflight --workspace workspaces/qwen-first-v1
```

预期：配置、runtime、runtime digest、评估契约、依赖工具与运行时环境全部通过，且无模型调用。

### 任务 10：运行 baseline 与三代进化

**涉及文件：**
- 生成：`workspaces/qwen-first-v1/runs/**`
- 生成：`workspaces/qwen-first-v1/archive.jsonl`
- 生成：`workspaces/qwen-first-v1/best_ever.json`
- 生成：`reports/control/**`

- [x] **步骤 1：认证 baseline 的 Gate 与 Sealed**

```bash
python3 scripts/experimentctl.py baseline --workspace workspaces/qwen-first-v1
```

预期：

- 第 0 代有四个可评分的 Gate trial；
- 第 0 代有四个可评分的 Sealed 锚点 trial；
- 所有 task/runtime/evaluator 指纹齐备；
- `best_ever.json` 指向第 0 代。

- [x] **步骤 2：用一次可恢复的驱动调用跑完全部三代**

```bash
python3 scripts/experimentctl.py evolve --workspace workspaces/qwen-first-v1
```

预期：

- gen/1、gen/2、gen/3 各有一个父代与一个「仅改 prompt」的 patch；
- 每一代都有四个 Train rollout trial 与四个 Gate trial；
- 即使被拒绝，每次 gate 决策也被记录；
- Train 任务名的并集是全部八个 Train 任务；
- 最终 champion 有一个四 trial 的 Sealed 锚点；
- Ollama 守护进程、模型或宿主资源故障立即停止，且不自动重试。

- [x] **步骤 3：验证 RSIHub 状态**

用与启动器相同的、已导出的 `EVOLVE_HOME` 运行：

```bash
workspaces/qwen-first-v1/evolve verify workspaces/qwen-first-v1
workspaces/qwen-first-v1/evolve status workspaces/qwen-first-v1
workspaces/qwen-first-v1/evolve assert-run workspaces/qwen-first-v1 --through 3
```

预期：完整性 `ok`、champion 非空、run 断言通过至第三代。

### 任务 11：产出并审计最终交付物

**涉及文件：**
- 生成：`reports/qwen-first-v1/summary.json`
- 生成：`reports/qwen-first-v1/report.md`
- 生成：`reports/qwen-first-v1/manifest.sha256`
- 生成：`reports/qwen-first-v1/candidate-diffs/*.diff`
- 修改：`README.md`

- [x] **步骤 1：在不调用模型的前提下构建报告**

```bash
python3 scripts/experimentctl.py report --workspace workspaces/qwen-first-v1
```

预期：报告构建器退出码为 0，且 `audit.missing_artifacts` 为空。

- [x] **步骤 2：独立验证哈希与必需结果**

```bash
shasum -a 256 -c reports/qwen-first-v1/manifest.sha256
python3 scripts/build_report.py --check --workspace workspaces/qwen-first-v1 --output reports
python3 -m unittest discover -s tests -v
```

预期：每条 manifest 条目均为 `OK`、报告检查通过、所有本地测试通过。

- [x] **步骤 3：加入最终实验指针**

在 `README.md` 追加：

```markdown
## First completed run

- Report: `reports/qwen-first-v1/report.md`
- Machine-readable summary: `reports/qwen-first-v1/summary.json`
- Artifact manifest: `reports/qwen-first-v1/manifest.sha256`
```

- [x] **步骤 4：提交可复现交付物**

```bash
git add README.md reports/qwen-first-v1
git diff --cached --check
git commit -m "docs: publish first Qwen evolution results"
```

- [x] **步骤 5：执行完成度审计**

对照权威证据逐条核验每项原始需求：

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

只有当每一行都被证明后，才可将该持久目标标记为完成。

### 任务 12：产出对标飞书的 HTML 可视化（阶段一收尾）

> 中文版新增任务。目标：把任务 11 的 `summary.json` 渲染成一页可分享的 HTML 多图，对标飞书《其他一些有意思的进化的分享》的展示形态。仅读取已认证的报告数据，不调用模型、不改 workspace。

**涉及文件：**
- 创建：`scripts/build_visualization.py`
- 创建：`tests/fixtures/summary-sample.json`
- 创建：`tests/test_build_visualization.py`
- 生成：`reports/qwen-first-v1/visualization.html`

- [x] **步骤 1：编写会失败的可视化测试**

创建 `tests/fixtures/summary-sample.json`（结构对齐任务 7 的 `summary.json`，含 baseline、三代、Gate/Sealed 分数、候选 diff、资源用量、hypothesis/expected_effect）。创建 `tests/test_build_visualization.py`，断言：

```python
html = render_html(load_summary(fixture))
self.assertIn("<!DOCTYPE html>", html)
self.assertIn("score-chart", html)            # 分数曲线容器存在
self.assertIn("gen-1", html)                  # 每代都被渲染
self.assertEqual(html.count("candidate-diff"), 3)  # 三个候选 diff 区块
self.assertNotIn("secret-value", html)        # 证据脱敏后不泄漏
```

补一个测试：`summary.json` 缺少必需键时，`render_html` 抛错并指名缺失键，而不是产出残缺页面。

- [x] **步骤 2：运行测试并确认 RED**

```bash
python3 -m unittest tests.test_build_visualization -v
```

预期：因 `scripts/build_visualization.py` 尚不存在而失败。

- [x] **步骤 3：实现确定性的 HTML 渲染**

`scripts/build_visualization.py` 只读 `reports/<experiment-id>/summary.json`，输出单文件、自包含（图表用内联 SVG 或轻量内联脚本，不依赖外网 CDN）的 `visualization.html`，包含：

- **分数曲线区**（`score-chart`）：baseline→gen1→gen2→gen3 的 Gate 与 Sealed 分数折线，标出 champion；
- **代际概览区**：每代父子关系、gate 决策（accepted/rejected）、是否成为 champion；
- **候选差异区**（`candidate-diff` ×3）：每代 `target/prompt.md` 的文本 diff；
- **资源消耗区**：target/mutator 的 tokens、请求数、wall-time、磁盘的对比条形；
- **改进假设区**：每代 hypothesis / expected_effect 与实际 Gate 结果对照。

所有文本走与报告一致的脱敏；缺失数据时报错而非静默跳过。

- [x] **步骤 4：生成并核验产物**

```bash
python3 scripts/build_visualization.py --workspace workspaces/qwen-first-v1 --report reports/qwen-first-v1
python3 -m unittest tests.test_build_visualization -v
```

预期：生成 `reports/qwen-first-v1/visualization.html`，测试全绿，页面能在浏览器离线打开。

- [x] **步骤 5：提交**

```bash
git add scripts/build_visualization.py tests/fixtures/summary-sample.json tests/test_build_visualization.py reports/qwen-first-v1/visualization.html
git diff --cached --check
git commit -m "feat: visualize evolution results as shareable HTML"
```
