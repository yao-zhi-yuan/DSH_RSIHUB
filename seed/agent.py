"""Harbor candidate adapter that runs the pinned DSH headless CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

from harbor.agents.base import BaseAgent

from .runtime_env import build_dsh_env, render_clean_command


class HarborAgent(BaseAgent):
    """Run one DSH session with candidate-owned instructions."""

    @staticmethod
    def name() -> str:
        return "dsh-qwen-agent"

    def version(self) -> str | None:
        return "0.1.0"

    def _candidate_root(self) -> Path:
        value = self._extra_env.get("EVOLVE_CANDIDATE_SOURCE") or os.environ.get("EVOLVE_CANDIDATE_SOURCE")
        if not value:
            return Path(__file__).resolve().parent
        return Path(value).expanduser().resolve()

    @staticmethod
    def _required_env(name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError(f"missing required DSH evaluator environment: {name}")
        return value

    async def setup(self, environment) -> None:
        candidate = self._candidate_root()
        await environment.upload_file(candidate / "prompt.md", "/app/AGENTS.md")
        await environment.upload_file(candidate / "dsh-qwen.patch.yml", "/app/.dsh-qwen.patch.yml")

    async def run(self, instruction: str, environment, context) -> None:
        del context
        dsh_bin = os.environ.get("DSH_EVALUATOR_BIN", "/usr/local/bin/dsh").strip()
        if not dsh_bin:
            raise RuntimeError("missing required DSH evaluator environment: DSH_EVALUATOR_BIN")
        timeout = int(os.environ.get("EXPERIMENT_TASK_TIMEOUT_SECONDS", "600"))
        dsh_source = dict(os.environ)
        dsh_source["OLLAMA_BASE_URL"] = self._required_env("OLLAMA_CONTAINER_BASE_URL")
        dsh_env = build_dsh_env(dsh_source, dsh_home="/logs/agent/dsh-home")
        command = render_clean_command(
            [
                dsh_bin,
                "--profile",
                "headless",
                "--patch",
                ".dsh-qwen.patch.yml",
                instruction,
            ],
            dsh_env,
        )
        result = await environment.exec(
            command=command,
            cwd="/app",
            env={},
            timeout_sec=timeout,
        )

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "dsh.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (self.logs_dir / "dsh.stderr.txt").write_text(result.stderr, encoding="utf-8")
        (self.logs_dir / "dsh-run.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "exit_code": result.return_code,
                    "configured_model": self._required_env("OLLAMA_TARGET_MODEL"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if await environment.is_dir("/logs/agent/dsh-home/sessions"):
            await environment.download_dir(
                "/logs/agent/dsh-home/sessions",
                self.logs_dir / "dsh-sessions",
            )
        if result.return_code != 0:
            raise RuntimeError(f"DSH headless exited with code {result.return_code}")
