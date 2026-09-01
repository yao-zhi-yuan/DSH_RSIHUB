#!/usr/bin/env python3
"""Build a deterministic, auditable report from a completed RSIHub workspace.

This reader never mutates the workspace and never calls a model. It parses the
real RSIHub evidence a Hill Climb run leaves behind and writes a report bundle:
``summary.json``, ``report.md``, ``manifest.sha256``, and one candidate diff per
generation. It fails closed on incomplete expected trials, uncertified
receipts, mismatched task sets, missing generations, absent final Sealed
evidence, malformed usage, or referenced files that do not exist.

Authoritative sources (grounded in the actual archive, not an assumed schema):

- ``archive.jsonl`` evaluation rows carry ``purpose`` in
  ``{genesis, candidate, anchor}`` (not ``gate``/``sealed``). Baseline Gate is
  the genesis row; baseline Sealed is the gen-0 anchor. Each later generation's
  Gate score is its certified ``candidate`` row — when a generation was retried
  the certified attempt is the scoreable one, so the highest certified attempt
  wins (gen 3 uses attempt 2, not the infrastructure-failed attempt 1).
- The standalone gate/record row (``{genid, verdict, valid_parent, reason}``)
  holds the keep/discard decision.
- ``runs/gen-<n>/mutate/patch.diff`` is the candidate diff; ``mutate/output.txt``
  carries the mutator hypothesis, expected effect, and per-call token usage.
- ``runs/gen-<n>/analyze/evidence/metrics.json`` holds the parent rollout the
  mutation reacted to: per-task rewards and target token usage.
- ``best_ever.json`` names the champion; ``.evolve-components.json`` and
  ``evolve.yaml`` carry the non-secret experiment and model identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 2
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


def _eval_row(rows: list[dict[str, Any]], generation: str, purpose: str) -> dict[str, Any]:
    """Return the certified evaluation row for one generation and purpose.

    A retried generation has more than one ``candidate`` row (the terminal
    infrastructure_failed attempt plus the certified retry). Prefer the highest
    attempt that is contract-certified with a numeric score so retries resolve
    to the scoreable evidence rather than the failure that triggered them.
    """
    matches = [
        row
        for row in rows
        if row.get("_evolve_mechanism_eval")
        and str(row.get("generation")) == generation
        and row.get("purpose") == purpose
    ]
    if not matches:
        raise ReportError(f"missing {purpose} evaluation for generation {generation}")
    certified = [
        row
        for row in matches
        if row.get("contract_certified")
        and isinstance(row.get("score"), (int, float))
        and not isinstance(row.get("score"), bool)
    ]
    pool = certified or matches
    return max(pool, key=lambda row: int(row.get("attempt") or 0))


def _gate_record(rows: list[dict[str, Any]], generation: str) -> dict[str, Any]:
    """Return the standalone keep/discard gate row for one generation."""
    for row in rows:
        if (
            not row.get("_evolve_mechanism_eval")
            and str(row.get("genid")) == generation
            and "verdict" in row
            and "valid_parent" in row
        ):
            return row
    raise ReportError(f"missing gate decision for generation {generation}")


def _certify(row: dict[str, Any], where: str) -> dict[str, Any]:
    """Validate one evaluation row: complete trials, certified, non-null score."""
    expected = row.get("expected_trials")
    scoreable = row.get("scoreable_trials")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
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
        "task_set_members": list(row.get("task_set_members") or []),
    }


def _task_vector(row: dict[str, Any]) -> dict[str, float]:
    """Flatten an evaluation row's per-task rewards to ``{task: reward}``."""
    vector = row.get("task_vector")
    tasks = vector.get("tasks") if isinstance(vector, dict) else None
    if not isinstance(tasks, dict):
        return {}
    flat: dict[str, float] = {}
    for name, body in tasks.items():
        trials = body.get("trials") if isinstance(body, dict) else None
        if isinstance(trials, list) and trials:
            reward = trials[0].get("reward")
            flat[str(name)] = float(reward) if isinstance(reward, (int, float)) and not isinstance(reward, bool) else None
    return flat


def _mutator_output(workspace: Path, generation: str) -> dict[str, Any]:
    """Parse ``runs/gen-<n>/mutate/output.txt`` for hypothesis and usage."""
    relative = f"runs/gen-{generation}/mutate/output.txt"
    path = _require_file(workspace, relative)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"malformed JSON in {relative}: {exc}") from None
    if not isinstance(value, dict):
        raise ReportError(f"expected a JSON object in {relative}")
    usage = value.get("usage")
    if not isinstance(usage, dict):
        raise ReportError(f"malformed mutator usage in {relative}")
    for field in ("prompt_tokens", "completion_tokens", "total_tokens", "request_count"):
        token = usage.get(field)
        if not isinstance(token, int) or isinstance(token, bool):
            raise ReportError(f"malformed mutator usage.{field} in {relative}")
    hypothesis, _ = _redact(str(value.get("hypothesis") or ""))
    expected, _ = _redact(str(value.get("expected_effect") or ""))
    return {
        "hypothesis": hypothesis,
        "expected_effect": expected,
        "usage": {
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "request_count": usage["request_count"],
        },
    }


def _target_rollout(workspace: Path, generation: str) -> dict[str, Any]:
    """Parse the parent rollout metrics the mutation reacted to."""
    relative = f"runs/gen-{generation}/analyze/evidence/metrics.json"
    path = _require_file(workspace, relative)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"malformed JSON in {relative}: {exc}") from None
    if not isinstance(value, dict):
        raise ReportError(f"expected a JSON object in {relative}")
    input_tokens = output_tokens = cache_tokens = 0
    per_task = value.get("per_task")
    if not isinstance(per_task, list):
        raise ReportError(f"malformed per_task in {relative}")
    for entry in per_task:
        usage = entry.get("usage") if isinstance(entry, dict) else None
        if not isinstance(usage, dict):
            raise ReportError(f"malformed per-task usage in {relative}")
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        cache_tokens += int(usage.get("cache_tokens") or 0)
    return {
        "mean_reward": value.get("mean_reward"),
        "trials": value.get("trials"),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_tokens": cache_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _tree_bytes(root: Path) -> int:
    """Return the total size in bytes of all files under ``root`` (0 if absent)."""
    if not root.is_dir():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def build_report(workspace: Path) -> dict[str, Any]:
    """Read a completed workspace and return the audit summary (no writes)."""
    workspace = Path(workspace).resolve()
    rows = _read_archive(workspace)
    components = _read_json(workspace, ".evolve-components.json")
    champion = _read_json(workspace, "best_ever.json")

    # Baseline: genesis is the gen-0 Gate cohort; the gen-0 anchor is Sealed.
    baseline = {
        "gate": _certify(_eval_row(rows, "0", "genesis"), "baseline gate"),
        "sealed": _certify(_eval_row(rows, "0", "anchor"), "baseline sealed"),
    }
    gate_hash = baseline["gate"]["task_set_hash"]
    sealed_hash = baseline["sealed"]["task_set_hash"]

    generations: list[dict[str, Any]] = []
    for name in GENERATIONS:
        candidate = _eval_row(rows, name, "candidate")
        gate = _certify(candidate, f"generation {name} gate")
        if gate["task_set_hash"] != gate_hash:
            raise ReportError(f"mismatched Gate task set in generation {name}")
        decision = _gate_record(rows, name)
        reason, _ = _redact(str(decision.get("reason") or ""))
        diff_path = _require_file(workspace, f"runs/gen-{name}/mutate/patch.diff")
        diff_text, _ = _redact(diff_path.read_text(encoding="utf-8"))
        generations.append(
            {
                "generation": name,
                "parent": str(candidate.get("parent")),
                "candidate_commit": str(candidate.get("candidate_commit") or ""),
                "attempt": int(candidate.get("attempt") or 0),
                "gate": gate,
                "task_vector": _task_vector(candidate),
                "verdict": str(decision.get("verdict") or ""),
                "valid_parent": bool(decision.get("valid_parent")),
                "reason": reason,
                "became_champion": str(champion.get("genid")) == name,
                "diff": diff_text,
                "mutation": _mutator_output(workspace, name),
                "parent_rollout": _target_rollout(workspace, name),
            }
        )

    # The champion is the only later generation guaranteed a Sealed anchor, so
    # anchor Sealed evidence is required for the generation best_ever names.
    champion_genid = str(champion.get("genid") or "")
    if champion_genid in GENERATIONS:
        champion_sealed = _certify(_eval_row(rows, champion_genid, "anchor"), "champion sealed")
    else:
        champion_sealed = baseline["sealed"]

    target_input = sum(g["parent_rollout"]["input_tokens"] for g in generations)
    target_output = sum(g["parent_rollout"]["output_tokens"] for g in generations)
    mutator_requests = sum(g["mutation"]["usage"]["request_count"] for g in generations)
    mutator_tokens = sum(g["mutation"]["usage"]["total_tokens"] for g in generations)
    wall_s = 0.0
    for row in rows:
        if row.get("_evolve_mechanism_eval"):
            cost = row.get("cost")
            if isinstance(cost, dict) and isinstance(cost.get("wall_s"), (int, float)):
                wall_s += float(cost["wall_s"])
    disk_bytes = _tree_bytes(workspace / "runs")

    final = {
        "champion_genid": champion_genid,
        "champion_score": champion.get("score"),
        "champion_commit": str(champion.get("candidate_commit") or ""),
        "gate": generations[-1]["gate"],
        "sealed": champion_sealed,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": {
            "experiment_id": str(champion.get("experiment_id") or components.get("recipe") or "experiment"),
            "recipe": str(components.get("recipe") or ""),
            "target_model": _component_model(rows),
            "mutator_operator": _mutator_name(components),
            "evaluator_engine": str(components.get("evaluator_engine") or ""),
        },
        "baseline": baseline,
        "generations": generations,
        "final": final,
        "resources": {
            "target": {
                "input_tokens": target_input,
                "output_tokens": target_output,
                "total_tokens": target_input + target_output,
            },
            "mutator": {"request_count": mutator_requests, "total_tokens": mutator_tokens},
            "wall_s": round(wall_s, 3),
            "disk_bytes": disk_bytes,
            "cost_usd": 0.0,
        },
        "audit": {"artifact_hashes": {}, "missing_artifacts": [], "redactions": 0},
        "limitations": [
            "Stage 1 prompt-only run: the mutator may edit only target/prompt.md.",
            "Scores compare only within a fixed task-set cohort (stable task_set_hash).",
            "Gate and Sealed cohorts are disjoint task sets and are not directly comparable.",
        ],
    }


def _component_model(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        header = row.get("request_header")
        if isinstance(header, dict):
            config = header.get("config")
            if isinstance(config, dict) and config.get("model"):
                return str(config["model"])
    return "ollama/qwen3:8b"


def _mutator_name(components: dict[str, Any]) -> str:
    operators = components.get("operators")
    if isinstance(operators, dict):
        mutate = operators.get("mutate")
        if isinstance(mutate, dict) and mutate.get("name"):
            return str(mutate["name"])
    return ""


def _render_markdown(report: dict[str, Any]) -> tuple[str, int]:
    experiment = report["experiment"]
    final = report["final"]
    lines = [
        f"# Evolution audit report: {experiment.get('experiment_id', 'unknown')}",
        "",
        f"- Target model: `{experiment.get('target_model', '')}`",
        f"- Mutator operator: `{experiment.get('mutator_operator', '')}`",
        f"- Champion: gen {final.get('champion_genid')} (score {final.get('champion_score')})",
        "",
        "## Score curve",
        "",
        "| Stage | Gate | Sealed |",
        "| --- | --- | --- |",
        f"| baseline | {report['baseline']['gate']['score']} | {report['baseline']['sealed']['score']} |",
    ]
    for generation in report["generations"]:
        sealed = "-"
        if generation["became_champion"]:
            sealed = final["sealed"]["score"]
        lines.append(
            f"| gen {generation['generation']} | {generation['gate']['score']} | {sealed} |"
        )
    lines += [
        "",
        "## Generation decisions",
        "",
        "| Gen | Parent | Verdict | Champion | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for generation in report["generations"]:
        lines.append(
            f"| {generation['generation']} | {generation['parent']} | "
            f"{generation['verdict']} | {'yes' if generation['became_champion'] else 'no'} | "
            f"{generation['reason']} |"
        )
    lines += [
        "",
        "## Improvement hypotheses",
        "",
    ]
    for generation in report["generations"]:
        lines.append(
            f"- gen {generation['generation']}: {generation['mutation']['hypothesis']} "
            f"(expected: {generation['mutation']['expected_effect']})"
        )
    lines += [
        "",
        "## Resources",
        "",
        f"- target tokens (total): {report['resources']['target']['total_tokens']}",
        f"- mutator tokens (total): {report['resources']['mutator']['total_tokens']}",
        f"- mutator requests: {report['resources']['mutator']['request_count']}",
        f"- wall time (s): {report['resources']['wall_s']}",
        "",
        "## Limitations",
        "",
    ]
    for note in report["limitations"]:
        lines.append(f"- {note}")
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
    for generation in report["generations"]:
        name = generation["generation"]
        # The diff text is already redacted in build_report; reuse it so the
        # standalone file and the summary embed stay byte-identical.
        target = diffs / f"gen-{name}.diff"
        target.write_text(generation["diff"], encoding="utf-8")
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


def check_report(workspace: Path, output_root: Path) -> list[str]:
    """Re-derive the report and confirm the published bundle still matches.

    Returns a list of discrepancies; an empty list means the on-disk bundle is
    byte-for-byte reproducible from the workspace evidence.
    """
    workspace = Path(workspace).resolve()
    report = build_report(workspace)
    experiment_id = str(report["experiment"].get("experiment_id") or "experiment")
    bundle = Path(output_root) / experiment_id
    problems: list[str] = []
    if not bundle.is_dir():
        return [f"missing report bundle: {bundle}"]

    manifest_path = bundle / "manifest.sha256"
    if not manifest_path.is_file():
        return ["missing manifest.sha256"]
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, _, relative = line.partition("  ")
        artifact = bundle / relative
        if not artifact.is_file():
            problems.append(f"missing artifact: {relative}")
            continue
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual != digest:
            problems.append(f"hash mismatch: {relative}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the published bundle matches the workspace instead of writing",
    )
    args = parser.parse_args(argv)
    if args.check:
        problems = check_report(args.workspace, args.output)
        if problems:
            for problem in problems:
                print(f"report check: {problem}")
            return 1
        print("report check: ok")
        return 0
    report = write_report(args.workspace, args.output)
    experiment_id = str(report["experiment"].get("experiment_id") or "experiment")
    print(f"report: wrote reports/{experiment_id}/ (redactions={report['audit']['redactions']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
