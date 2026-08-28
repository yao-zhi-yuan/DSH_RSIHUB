#!/usr/bin/env python3
"""RSIHub mutate-stage operator for one Qwen-generated prompt edit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_usage(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"usd": 0}
    result = dict(value)
    result["usd"] = 0
    return result


def mutation_prompt(observation: str) -> str:
    return (
        "# RSIHub Hill Climb prompt mutation\n\n"
        "Improve the candidate's general coding-task execution policy using only the training feedback below. "
        "Make one coherent, transferable change. Do not encode task-specific answers, identifiers, evaluator "
        "details, model settings, endpoints, credentials, scores, or held-out information. The only permitted "
        "candidate change is `target/prompt.md`.\n\n"
        "## Training feedback\n\n"
        f"{observation[:30000]}\n\n"
        "Edit the checkout directly and exit successfully only after `target/prompt.md` changed.\n"
    )


class QwenPromptMutate(MutateOperator):
    """Run the trusted Qwen editor and stamp its bounded candidate patch."""

    def mutate(self, checkout: Path, observation: str, ctx: OperatorContext) -> MutateResult:
        parent_ref = patch_parent_ref(checkout, ctx)
        output_dir = ctx.run_dir / "mutate"
        output_dir.mkdir(parents=True, exist_ok=True)
        prompt = mutation_prompt(observation)
        (output_dir / "prompt.md").write_text(prompt, encoding="utf-8")
        try:
            agent_run = run_mutate(checkout, prompt, ctx.config)
        except AgentCommandError as exc:
            (output_dir / "output.txt").write_text(exc.output, encoding="utf-8")
            write_json(output_dir / "usage.json", safe_usage(exc.usage))
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

        usage = safe_usage(agent_run.usage)
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
