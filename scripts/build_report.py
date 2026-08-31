#!/usr/bin/env python3
"""Build a deterministic, auditable report from a completed RSIHub workspace.

This reader never mutates the workspace and never calls a model. It parses the
frozen ``archive.jsonl`` (one row per generation/purpose), the per-generation
mutation diffs and usage, and the experiment identity, then writes a report
bundle: ``summary.json``, ``report.md``, ``manifest.sha256``, and one candidate
diff per generation. It fails closed on incomplete expected trials, uncertified
receipts, mismatched task sets, missing generations, absent final Sealed
evidence, malformed usage, or referenced files that do not exist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
GENERATIONS = ("1", "2", "3")

_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|authorization|auth)\b"
    r"(\s*[:=]\s*)([^\s,;}]+)"
)


class ReportError(RuntimeError):
    """The workspace evidence is incomplete or inconsistent; refuse to report."""


def _redact(text: str) -> tuple[str, int]:
    """Return redacted text and the number of substitutions performed."""
    count = 0

    def _sub_secret(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}{match.group(2)}[REDACTED]"

    def _sub_bearer(_match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "Bearer [REDACTED]"

    text = _BEARER.sub(_sub_bearer, text)
    text = _SECRET_ASSIGNMENT.sub(_sub_secret, text)
    return text, count


def _require_file(workspace: Path, relative: str) -> Path:
    path = workspace / relative
    if not path.is_file():
        raise ReportError(f"missing required artifact: {relative}")
    return path


def _read_json(workspace: Path, relative: str) -> dict[str, Any]:
    path = _require_file(workspace, relative)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"malformed JSON in {relative}: {exc}") from None
    if not isinstance(value, dict):
        raise ReportError(f"expected a JSON object in {relative}")
    return value


def _read_archive(workspace: Path) -> list[dict[str, Any]]:
    path = _require_file(workspace, "archive.jsonl")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ReportError(f"malformed archive.jsonl line {index}: {exc}") from None
        if not isinstance(row, dict):
            raise ReportError(f"archive.jsonl line {index} is not an object")
        rows.append(row)
    return rows


def _eval(rows: list[dict[str, Any]], generation: str, purpose: str) -> dict[str, Any]:
    for row in rows:
        if str(row.get("generation")) == generation and row.get("purpose") == purpose:
            return row
    raise ReportError(f"missing {purpose} evaluation for generation {generation}")


def _usage(row: dict[str, Any], where: str) -> dict[str, Any]:
    usage = row.get("usage")
    if not isinstance(usage, dict):
        raise ReportError(f"malformed usage in {where}")
    for field in ("n_input_tokens", "n_output_tokens", "n_cache_tokens", "total_tokens"):
        value = usage.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ReportError(f"malformed usage.{field} in {where}")
    return usage


def _certify(row: dict[str, Any], where: str) -> dict[str, Any]:
    """Validate one evaluation row: complete trials, certified, non-null score."""
    expected = row.get("expected_trials")
    scoreable = row.get("scoreable_trials")
    if not isinstance(expected, int) or expected < 1:
        raise ReportError(f"invalid expected_trials in {where}")
    if scoreable != expected:
        raise ReportError(f"incomplete trials in {where}: {scoreable}/{expected}")
    if not row.get("contract_certified"):
        raise ReportError(f"uncertified receipt in {where}")
    if not isinstance(row.get("score"), (int, float)) or isinstance(row.get("score"), bool):
        raise ReportError(f"missing score in {where}")
    reason, _ = _redact(str(row.get("reason") or ""))
    return {
        "score": float(row["score"]),
        "expected_trials": expected,
        "scoreable_trials": scoreable,
        "task_set_hash": str(row.get("task_set_hash") or ""),
        "reason": reason,
    }


def build_report(workspace: Path) -> dict[str, Any]:
    """Read a completed workspace and return the audit summary (no writes)."""
    workspace = Path(workspace).resolve()
    experiment = _read_json(workspace, "experiment.json")
    rows = _read_archive(workspace)

    baseline = {
        "gate": _certify(_eval(rows, "0", "gate"), "baseline gate"),
        "sealed": _certify(_eval(rows, "0", "sealed"), "baseline sealed"),
    }

    # Task sets must stay stable across the run so scores are comparable.
    gate_hash = baseline["gate"]["task_set_hash"]
    sealed_hash = baseline["sealed"]["task_set_hash"]

    generations: list[dict[str, Any]] = []
    target_total = 0
    for name in GENERATIONS:
        gate = _certify(_eval(rows, name, "gate"), f"generation {name} gate")
        sealed = _certify(_eval(rows, name, "sealed"), f"generation {name} sealed")
        if gate["task_set_hash"] != gate_hash or sealed["task_set_hash"] != sealed_hash:
            raise ReportError(f"mismatched task set in generation {name}")
        _require_file(workspace, f"mutate/gen-{name}/patch.diff")
        generations.append({"generation": name, "gate": gate, "sealed": sealed})

    for row in rows:
        target_total += _usage(row, f"generation {row.get('generation')} {row.get('purpose')}")["total_tokens"]

    mutator_requests = 0
    mutator_tokens = 0
    for name in GENERATIONS:
        usage = _read_json(workspace, f"mutate/gen-{name}/usage.json")
        request_count = usage.get("request_count")
        total = usage.get("total_tokens")
        if not isinstance(request_count, int) or isinstance(request_count, bool):
            raise ReportError(f"malformed mutator usage in mutate/gen-{name}/usage.json")
        if not isinstance(total, int) or isinstance(total, bool):
            raise ReportError(f"malformed mutator total_tokens in mutate/gen-{name}/usage.json")
        mutator_requests += request_count
        mutator_tokens += total

    final = {
        "champion": experiment.get("champion") or {},
        "gate": generations[-1]["gate"],
        "sealed": generations[-1]["sealed"],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": experiment,
        "baseline": baseline,
        "generations": generations,
        "final": final,
        "resources": {
            "target": {"total_tokens": target_total},
            "mutator": {"request_count": mutator_requests, "total_tokens": mutator_tokens},
            "ollama_models": experiment.get("ollama_models") or [],
            "host": experiment.get("host") or {},
            "wall_s": 0,
            "disk_bytes": 0,
            "cost_usd": 0,
        },
        "audit": {"artifact_hashes": {}, "missing_artifacts": [], "redactions": 0},
        "limitations": [
            "Stage 1 prompt-only run: the mutator may edit only target/prompt.md.",
        ],
    }


def _render_markdown(report: dict[str, Any]) -> tuple[str, int]:
    experiment = report["experiment"]
    lines = [
        f"# Evolution audit report: {experiment.get('experiment_id', 'unknown')}",
        "",
        "## Score curve",
        "",
        "| Stage | Gate | Sealed |",
        "| --- | --- | --- |",
        f"| baseline | {report['baseline']['gate']['score']} | {report['baseline']['sealed']['score']} |",
    ]
    for generation in report["generations"]:
        lines.append(
            f"| gen {generation['generation']} | {generation['gate']['score']} | {generation['sealed']['score']} |"
        )
    lines += [
        "",
        "## Resources",
        "",
        f"- target total tokens: {report['resources']['target']['total_tokens']}",
        f"- mutator requests: {report['resources']['mutator']['request_count']}",
        "",
        "## Generation reasons",
        "",
    ]
    for generation in report["generations"]:
        lines.append(f"- gen {generation['generation']} gate: {generation['gate']['reason']}")
    text = "\n".join(lines) + "\n"
    return _redact(text)


def write_report(workspace: Path, output_root: Path) -> dict[str, Any]:
    """Write the report bundle for ``workspace`` under ``output_root``."""
    workspace = Path(workspace).resolve()
    report = build_report(workspace)
    experiment_id = str(report["experiment"].get("experiment_id") or "experiment")
    bundle = Path(output_root) / experiment_id
    diffs = bundle / "candidate-diffs"
    diffs.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for name in GENERATIONS:
        source = workspace / "mutate" / f"gen-{name}" / "patch.diff"
        redacted, _ = _redact(source.read_text(encoding="utf-8"))
        target = diffs / f"gen-{name}.diff"
        target.write_text(redacted, encoding="utf-8")
        written.append(f"candidate-diffs/gen-{name}.diff")

    markdown, redactions = _render_markdown(report)
    report["audit"]["redactions"] = redactions
    (bundle / "summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    written.append("summary.json")
    (bundle / "report.md").write_text(markdown, encoding="utf-8")
    written.append("report.md")

    manifest_lines = []
    hashes: dict[str, str] = {}
    for relative in sorted(written):
        digest = hashlib.sha256((bundle / relative).read_bytes()).hexdigest()
        hashes[relative] = digest
        manifest_lines.append(f"{digest}  {relative}")
    (bundle / "manifest.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    report["audit"]["artifact_hashes"] = hashes
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)
    report = write_report(args.workspace, args.output)
    experiment_id = str(report["experiment"].get("experiment_id") or "experiment")
    print(f"report: wrote reports/{experiment_id}/ (redactions={report['audit']['redactions']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
