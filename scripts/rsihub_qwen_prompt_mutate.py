#!/usr/bin/env python3
"""RSIHub mutate-stage operator for one Qwen-generated prompt edit."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from evolve.agent import AgentCommandError, run_mutate
from evolve.frozen import sdk
from evolve.frozen.config import Config, string
from evolve.frozen.interfaces import MutateOperator, MutateResult, OperatorContext
from evolve.patching import create_candidate_patch, load_surface_policy, patch_parent_ref


CONFIG = Config(
    {
        "command": string(
            required=True,
            description="Trusted local command that edits target/prompt.md.",
        )
    }
)

# Files RSIHub retains in the feedback bundle, hashed and referenced for the
# trusted mutator. Missing entries are skipped rather than fatal.
FEEDBACK_FILES = (
    "index.md",
    "evidence/selected.md",
    "last_accepted.diff",
)

_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|authorization|auth)\b"
    r"(\s*[:=]\s*)([^\s,;}]+)"
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _redact(text: str) -> str:
    """Strip credentials while leaving task evidence for the trusted mutator."""
    text = _BEARER.sub("Bearer [REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)


def build_mutation_input(observation: str, run_dir: Path) -> tuple[str, list[dict[str, object]]]:
    """Reference the retained feedback bundle and hash every supplied file."""
    feedback_dir = (run_dir / "feedback").resolve()
    inputs: list[dict[str, object]] = []
    for relative in FEEDBACK_FILES:
        path = feedback_dir / relative
        if not path.is_file():
            continue
        raw = path.read_bytes()
        inputs.append(
            {
                "path": f"feedback/{relative}",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            }
        )
    selected = feedback_dir / "evidence" / "selected.md"
    selected_text = _redact(selected.read_text(encoding="utf-8", errors="replace")) if selected.is_file() else ""
    prompt = (
        "# RSIHub Hill Climb prompt mutation\n\n"
        "Improve the candidate's general coding-task execution policy using only the training feedback below. "
        "Make one coherent, transferable change. Do not encode task-specific answers, identifiers, evaluator "
        "details, model settings, endpoints, credentials, scores, or held-out information. The only permitted "
        "candidate change is `target/prompt.md`.\n\n"
        f"Feedback bundle: {feedback_dir}\n\n"
        "## Selected training evidence (feedback/evidence/selected.md)\n\n"
        f"{selected_text[:30000]}\n\n"
        "## Rollout observation\n\n"
        f"{_redact(observation)[:30000]}\n\n"
        "Edit the checkout directly and exit successfully only after `target/prompt.md` changed.\n"
    )
    return prompt, inputs


def parse_command_usage(stdout: str, wall_s: float) -> dict[str, object]:
    """Read the final JSON object and require integer token fields."""
    end = stdout.rfind("}")
    start = stdout.rfind("{", 0, end + 1)
    while start != -1:
        try:
            payload = json.loads(stdout[start : end + 1])
        except json.JSONDecodeError:
            start = stdout.rfind("{", 0, start)
            continue
        break
    else:
        raise ValueError("mutation command produced no JSON usage object")
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        raise ValueError("mutation command output is missing a usage object")
    tokens: dict[str, object] = {"usd": 0, "wall_s": wall_s}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"mutation usage.{field} must be an integer")
        tokens[field] = value
    return tokens


class QwenPromptMutate(MutateOperator):
    """Run the trusted Qwen editor and stamp its bounded candidate patch."""

    def mutate(self, checkout: Path, observation: str, ctx: OperatorContext) -> MutateResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        output_dir = ctx.run_dir / "mutate"
        output_dir.mkdir(parents=True, exist_ok=True)
        prompt, evidence_inputs = build_mutation_input(observation, ctx.run_dir)
        (output_dir / "prompt.md").write_text(prompt, encoding="utf-8")
        write_json(output_dir / "evidence-inputs.json", evidence_inputs)
        try:
            agent_run = run_mutate(checkout, prompt, ctx.config)
        except AgentCommandError as exc:
            (output_dir / "output.txt").write_text(exc.output, encoding="utf-8")
            write_json(output_dir / "usage.json", exc.usage)
            raise SystemExit(exc.returncode) from None

        patch = create_candidate_patch(
            checkout=checkout,
            parent_ref=parent_ref,
            surface=load_surface_policy(checkout),
            repair=False,
        )
        violations = list(patch.surface_report.get("violations") or [])
        if violations:
            write_json(output_dir / "surface-check.json", patch.surface_report)
            raise SystemExit("mutation changed paths outside target/prompt.md")
        if patch.changed_paths != ["target/prompt.md"]:
            write_json(output_dir / "surface-check.json", patch.surface_report)
            raise SystemExit("mutation must change exactly target/prompt.md")

        # Derive usage from the command's own report; missing tokens fail the
        # stage rather than silently recording zero.
        usage = parse_command_usage(agent_run.stdout, agent_run.wall_s)
        (output_dir / "output.txt").write_text(agent_run.output, encoding="utf-8")
        (output_dir / "model_patch.diff").write_text(patch.diff, encoding="utf-8")
        (output_dir / "patch.diff").write_text(patch.diff, encoding="utf-8")
        (output_dir / "rationale.md").write_text(
            "operator: rsihub-qwen-prompt\nwritten-by: scripts/rsihub_qwen_prompt_mutate.py\n",
            encoding="utf-8",
        )
        write_json(output_dir / "changed.json", patch.changed_paths)
        write_json(output_dir / "surface-check.json", patch.surface_report)
        write_json(output_dir / "usage.json", usage)
        return MutateResult(
            changed=patch.changed_paths,
            notes=["operator: rsihub-qwen-prompt", *patch.notes],
            usage=usage,
        )


if __name__ == "__main__":
    sdk.main(QwenPromptMutate, config_schema=CONFIG)
