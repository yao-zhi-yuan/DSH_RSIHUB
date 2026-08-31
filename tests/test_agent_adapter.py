"""Behavioral tests for the DSH Harbor adapter's failure classification.

These cover the contract that a slow or failing 8B run is a *scoreable* task
failure (the adapter returns so the verifier records reward 0), while a run that
never reached the model is an infrastructure failure the adapter raises on. The
adapter imports ``harbor.agents.base``, so this suite is skipped unless Harbor is
importable (it is inside the workspace virtualenv).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "seed"

_HARBOR = importlib.util.find_spec("harbor") is not None


def _load_agent_module():
    """Import ``seed.agent`` as a package so its relative imports resolve."""
    package = types.ModuleType("seedpkg")
    package.__path__ = [str(SEED_DIR)]
    import sys

    sys.modules.setdefault("seedpkg", package)
    for name in ("runtime_env", "dsh_session", "agent"):
        spec = importlib.util.spec_from_file_location(
            f"seedpkg.{name}", SEED_DIR / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"seedpkg.{name}"] = module
        spec.loader.exec_module(module)
    return sys.modules["seedpkg.agent"]


class _Context:
    def __init__(self) -> None:
        self.n_input_tokens = 0
        self.n_cache_tokens = 0
        self.n_output_tokens = 0
        self.cost_usd = 0.0
        self.metadata: dict[str, object] | None = None


class _ExecResult:
    def __init__(self, return_code: int, stdout: str | None, stderr: str | None) -> None:
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr


class _Environment:
    """Fake Harbor environment that scripts one ``exec`` outcome.

    ``exec_outcome`` is either an ``_ExecResult`` to return or an exception to
    raise. When ``session_text`` is set, ``download_dir`` writes it as one
    session JSONL so the adapter's evidence collection sees model usage.
    """

    def __init__(self, exec_outcome, session_text: str | None) -> None:
        self._exec_outcome = exec_outcome
        self._session_text = session_text

    async def upload_file(self, *args, **kwargs) -> None:
        return None

    async def exec(self, *args, **kwargs):
        if isinstance(self._exec_outcome, BaseException):
            raise self._exec_outcome
        return self._exec_outcome

    async def is_dir(self, path: str) -> bool:
        return self._session_text is not None

    async def download_dir(self, remote: str, local: Path) -> None:
        target = Path(local) / "--app--" / "session-test"
        target.mkdir(parents=True, exist_ok=True)
        (target / "session.jsonl").write_text(self._session_text or "", encoding="utf-8")


_USAGE_LINE = json.dumps(
    {
        "type": "assistant/chunk",
        "data": {"turn": 1, "step": 1, "chunk": {"type": "usage", "usage": {"inputTokens": 2949, "outputTokens": 724}}},
    }
)


@unittest.skipUnless(_HARBOR, "harbor is only importable inside the workspace venv")
class AgentFailureClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._agent_module = _load_agent_module()
        import os
        import tempfile

        self._tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        # build_dsh_env fails closed unless PATH resolves node; give it a stub.
        bin_dir = self._tmp / "bin"
        bin_dir.mkdir()
        node = bin_dir / "node"
        node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        node.chmod(0o755)

        self._prev_env = {
            key: os.environ.get(key)
            for key in (
                "OLLAMA_TARGET_MODEL",
                "OLLAMA_CONTAINER_BASE_URL",
                "OLLAMA_BASE_URL",
                "OLLAMA_API_KEY",
                "DSH_EVALUATOR_BIN",
                "PATH",
            )
        }
        os.environ["OLLAMA_TARGET_MODEL"] = "qwen3:8b"
        os.environ["OLLAMA_CONTAINER_BASE_URL"] = "http://host.docker.internal:11434/v1"
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434/v1"
        os.environ["OLLAMA_API_KEY"] = "ollama"
        os.environ["DSH_EVALUATOR_BIN"] = "/usr/local/bin/dsh"
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    def tearDown(self) -> None:
        import os

        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _make_agent(self, environment):
        agent = self._agent_module.HarborAgent(logs_dir=self._tmp / "logs")
        return agent

    def _run(self, exec_outcome, session_text):
        environment = _Environment(exec_outcome, session_text)
        agent = self._make_agent(environment)
        context = _Context()
        asyncio.run(agent.run("solve the task", environment, context))
        return context

    def test_clean_exit_returns_without_raising(self) -> None:
        context = self._run(_ExecResult(0, "done", ""), _USAGE_LINE)
        self.assertEqual(context.metadata["request_count"], 1)
        self.assertEqual(context.n_input_tokens, 2949)

    def test_timeout_with_usage_is_scoreable(self) -> None:
        # A wall-clock timeout that still produced model requests must not raise:
        # the verifier scores the workspace state as reward 0.
        context = self._run(RuntimeError("Command timed out after 900 seconds"), _USAGE_LINE)
        self.assertEqual(context.metadata["request_count"], 1)

    def test_nonzero_exit_with_usage_is_scoreable(self) -> None:
        context = self._run(_ExecResult(1, "", "dsh: TIMEOUT: idle"), _USAGE_LINE)
        self.assertEqual(context.metadata["request_count"], 1)

    def test_timeout_without_usage_fails_closed(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            self._run(RuntimeError("Command timed out after 900 seconds"), "")
        self.assertIn("infrastructure failure", str(caught.exception))

    def test_nonzero_exit_without_session_fails_closed(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            self._run(_ExecResult(1, "", "boom"), None)
        self.assertIn("infrastructure failure", str(caught.exception))

    def test_unexpected_runtime_error_propagates(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            self._run(RuntimeError("docker daemon not reachable"), _USAGE_LINE)
        self.assertIn("docker daemon", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
