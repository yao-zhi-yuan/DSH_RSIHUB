from __future__ import annotations

import hashlib
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


class TrainScheduleTests(unittest.TestCase):
    """The frozen Train schedule must cover every Train task across gens 1-3.

    Reproduces RSIHub's real selection without importing the heavy
    ``evolve.splits`` module (which needs harbor): the split is assigned exactly
    as ``evolve.splits._assign`` does (sort by ``sha256(seed\\0name)``, floor by
    ratio, distribute the remainder by fractional priority), then each
    generation's rollout picks ``budget_tasks`` via ``generation_shuffle`` keyed
    by ``f"{rollout_seed}:{genid}"`` (the rollout config seed defaults to 0).
    """

    ROOT = Path(__file__).resolve().parents[1]
    DATASET = ROOT / "tasks" / "synthetic-16"
    SPLIT_NAMES = ("train", "gate", "sealed")

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def _assign_train(self, names: list[str], seed: int) -> list[str]:
        import math

        ratios = {"train": 0.5, "gate": 0.25, "sealed": 0.25}
        ordered = sorted(names, key=lambda name: self._digest(f"{seed}\0{name}"))
        raw = {name: len(ordered) * ratios[name] for name in self.SPLIT_NAMES}
        counts = {name: math.floor(raw[name]) for name in self.SPLIT_NAMES}
        remainder = len(ordered) - sum(counts.values())
        priority = sorted(
            self.SPLIT_NAMES,
            key=lambda name: (-(raw[name] - counts[name]), self.SPLIT_NAMES.index(name)),
        )
        for name in priority[:remainder]:
            counts[name] += 1
        return sorted(ordered[: counts["train"]])

    def _train_split(self) -> list[str]:
        names = sorted(
            path.name
            for path in self.DATASET.iterdir()
            if path.is_dir() and (path / "task.toml").is_file()
        )
        return self._assign_train(names, 17)

    @staticmethod
    def _generation_batch(train: list[str], sampling_key: str, budget: int) -> list[str]:
        ordered = sorted(
            train,
            key=lambda name: hashlib.sha256(f"{sampling_key}\0{name}".encode()).hexdigest(),
        )
        return ordered[:budget]

    def test_generation_shuffle_covers_full_train_split(self) -> None:
        train = self._train_split()
        self.assertEqual(len(train), 8)
        covered: set[str] = set()
        for genid in ("1", "2", "3"):
            covered.update(self._generation_batch(train, f"0:{genid}", 4))
        self.assertEqual(covered, set(train))
        self.assertEqual(len(covered), 8)


class ParserTests(unittest.TestCase):
    """The control plane must expose retry with a positional generation id."""

    def test_retry_subcommand_binds_genid_and_handler(self) -> None:
        args = experimentctl.build_parser().parse_args(
            ["retry", "--workspace", "ws", "3"]
        )
        self.assertIs(args.func, experimentctl.cmd_retry)
        self.assertEqual(args.workspace, "ws")
        self.assertEqual(args.genid, "3")

    def test_retry_requires_genid(self) -> None:
        with self.assertRaises(SystemExit):
            experimentctl.build_parser().parse_args(["retry", "--workspace", "ws"])


if __name__ == "__main__":
    unittest.main()
