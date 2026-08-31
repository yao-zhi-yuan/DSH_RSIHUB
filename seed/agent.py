"""Harbor candidate adapter that runs the pinned DSH headless CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

from harbor.agents.base import BaseAgent

from .dsh_session import SessionEvidence, parse_session_files
from .runtime_env import build_dsh_env, render_clean_command


_SENSITIVE_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH")


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
        dsh_bin = os.environ.get("DSH_EVALUATOR_BIN", "/usr/local/bin/dsh").strip()
        if not dsh_bin:
            raise RuntimeError("missing required DSH evaluator environment: DSH_EVALUATOR_BIN")
        timeout = int(os.environ.get("EXPERIMENT_TASK_TIMEOUT_SECONDS", "600"))
        configured_model = self._required_env("OLLAMA_TARGET_MODEL")
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
        # A slow or looping 8B run (DSH's own idle timeout, or the wall-clock
        # cap) is a task failure, not an infrastructure fault: capture it and
        # let the verifier score reward 0 instead of aborting the generation.
        # Only a run that never reached the model (no usage evidence) fails
        # closed below.
        timed_out = False
        try:
            result = await environment.exec(
                command=command,
                cwd="/app",
                env={},
                timeout_sec=timeout,
            )
            return_code = result.return_code
            # Harbor's exec may return None for either stream; coerce to "" so
            # log capture and downstream parsing never crash on a missing stream.
            stdout = result.stdout or ""
            stderr = result.stderr or ""
        except RuntimeError as exc:
            # DockerEnvironment raises a plain RuntimeError on wall-clock
            # timeout; re-raise anything else so real bugs stay visible.
            if "timed out" not in str(exc).lower():
                raise
            timed_out = True
            return_code = None
            stdout = ""
            stderr = str(exc)

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "dsh.stdout.txt").write_text(stdout, encoding="utf-8")
        (self.logs_dir / "dsh.stderr.txt").write_text(stderr, encoding="utf-8")
        (self.logs_dir / "dsh-run.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "exit_code": return_code,
                    "timed_out": timed_out,
                    "configured_model": configured_model,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        sessions_dir = self.logs_dir / "dsh-sessions"
        if await environment.is_dir("/logs/agent/dsh-home/sessions"):
            await environment.download_dir(
                "/logs/agent/dsh-home/sessions",
                sessions_dir,
            )

        # Collect trajectory and usage before deciding, so a failed run still
        # yields the evidence the mutator learns from and the usage the archive
        # records.
        evidence = self._collect_evidence(context, sessions_dir, configured_model)

        # Fail closed only when the target never reached the model at all: no
        # usage evidence on a nonzero or timed-out run means Ollama was
        # unreachable, the binary was missing, or the container was broken.
        # A run that produced at least one request but failed or timed out is a
        # scoreable task failure the verifier will mark reward 0.
        if (timed_out or return_code != 0) and evidence.usage.requests == 0:
            detail = "timed out" if timed_out else f"exited with code {return_code}"
            raise RuntimeError(
                f"DSH headless {detail} without producing any model request; "
                "treating as an infrastructure failure"
            )

    def _collect_evidence(self, context, sessions_dir: Path, configured_model: str) -> SessionEvidence:
        session_files = sorted(sessions_dir.rglob("*.jsonl")) if sessions_dir.is_dir() else []
        sensitive = {
            value
            for name, value in os.environ.items()
            if value and len(value) >= 8 and any(marker in name.upper() for marker in _SENSITIVE_ENV_MARKERS)
        }
        evidence = parse_session_files(session_files, sensitive_values=sensitive)

        (self.logs_dir / "trajectory.json").write_text(
            json.dumps({"schema_version": 1, "steps": evidence.events}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        context.n_input_tokens = evidence.usage.input_tokens
        context.n_cache_tokens = evidence.usage.cache_tokens
        context.n_output_tokens = evidence.usage.output_tokens
        context.cost_usd = 0.0
        context.metadata = context.metadata or {}
        context.metadata.update(
            {
                "request_count": evidence.usage.requests,
                "configured_model": configured_model,
                "session_files": [str(path) for path in session_files],
            }
        )
        return evidence
