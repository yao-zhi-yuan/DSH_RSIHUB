from __future__ import annotations

import json
import unittest
import urllib.error
from pathlib import Path

from scripts import experimentctl


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _tags(*models: dict[str, object]) -> bytes:
    return json.dumps({"models": list(models)}).encode("utf-8")


class BuildRuntimeEnvTests(unittest.TestCase):
    def _env(self, **overrides: str) -> dict[str, str]:
        source = {
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1",
            "OLLAMA_API_KEY": "ollama",
            "OLLAMA_TARGET_MODEL": "qwen3:8b",
            "OLLAMA_MUTATOR_MODEL": "qwen3:14b",
            "UNRELATED_SECRET": "must-not-leak",
        }
        source.update(overrides)
        return experimentctl.build_runtime_env(source, root=Path("/repo"))

    def test_builds_allowlisted_runtime_env(self) -> None:
        env = self._env()
        self.assertNotIn("UNRELATED_SECRET", env)
        self.assertEqual(env["OLLAMA_TARGET_MODEL"], "qwen3:8b")
        self.assertEqual(env["OLLAMA_MUTATOR_MODEL"], "qwen3:14b")
        self.assertEqual(env["DSH_BIN"], "/repo/node_modules/.bin/dsh")
        self.assertEqual(env["EVOLVE_EXPERIMENT_ROOT"], "/repo")

    def test_missing_base_url_fails(self) -> None:
        with self.assertRaises(ValueError):
            self._env(OLLAMA_BASE_URL="")

    def test_non_loopback_base_url_fails(self) -> None:
        with self.assertRaises(ValueError):
            self._env(OLLAMA_BASE_URL="http://10.0.0.5:11434/v1")


class ProbeModelsTests(unittest.TestCase):
    REQUIRED = ("qwen3:8b", "qwen3:14b")

    def test_returns_digests_and_sizes(self) -> None:
        def opener(url: str, timeout: float | None = None) -> FakeResponse:
            self.assertEqual(url, "http://127.0.0.1:11434/api/tags")
            return FakeResponse(
                _tags(
                    {"model": "qwen3:8b", "digest": "sha256:aaa", "size": 123},
                    {"model": "qwen3:14b", "digest": "sha256:bbb", "size": 456},
                )
            )

        resolved = experimentctl.probe_models(
            "http://127.0.0.1:11434/v1", self.REQUIRED, opener=opener
        )
        self.assertEqual(resolved["qwen3:8b"]["digest"], "sha256:aaa")
        self.assertEqual(resolved["qwen3:14b"]["size"], 456)

    def test_stopped_daemon_fails(self) -> None:
        def opener(url: str, timeout: float | None = None) -> FakeResponse:
            raise urllib.error.URLError("connection refused")

        with self.assertRaises(RuntimeError):
            experimentctl.probe_models(
                "http://127.0.0.1:11434/v1", self.REQUIRED, opener=opener
            )

    def test_missing_model_fails(self) -> None:
        def opener(url: str, timeout: float | None = None) -> FakeResponse:
            return FakeResponse(_tags({"model": "qwen3:8b", "digest": "sha256:aaa", "size": 1}))

        with self.assertRaises(RuntimeError):
            experimentctl.probe_models(
                "http://127.0.0.1:11434/v1", self.REQUIRED, opener=opener
            )

    def test_malformed_response_fails(self) -> None:
        def opener(url: str, timeout: float | None = None) -> FakeResponse:
            return FakeResponse(b"not json at all")

        with self.assertRaises(RuntimeError):
            experimentctl.probe_models(
                "http://127.0.0.1:11434/v1", self.REQUIRED, opener=opener
            )


if __name__ == "__main__":
    unittest.main()
