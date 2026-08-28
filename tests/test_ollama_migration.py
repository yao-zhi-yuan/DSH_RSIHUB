from __future__ import annotations

import importlib.util
import shutil
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    ROOT / ".env.example",
    ROOT / "config" / "dsh-qwen.patch.yml",
    ROOT / "recipes" / "dsh_hill_climb" / "README.md",
    ROOT / "recipes" / "dsh_hill_climb" / "evolve.yaml",
    ROOT / "scripts" / "api_smoke.py",
    ROOT / "scripts" / "qwen_mutate.py",
    ROOT / "seed" / "agent.py",
    ROOT / "seed" / "dsh-qwen.patch.yml",
)
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-08-28-rsihub-dsh-qwen-evolution.md"


class OllamaMigrationTests(unittest.TestCase):
    def test_retired_remote_models_and_environment_are_absent(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE_FILES)
        for retired in (
            "qwen3.7",
            "qwen3.8",
            "QWEN_TARGET_",
            "QWEN_MUTATOR_",
            "EXPERIMENT_PROVIDER_CAPACITY",
        ):
            self.assertNotIn(retired, combined)

    def test_local_model_roles_are_explicit(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE_FILES)
        for required in (
            "OLLAMA_BASE_URL",
            "OLLAMA_CONTAINER_BASE_URL",
            "OLLAMA_API_KEY",
            "OLLAMA_TARGET_MODEL",
            "OLLAMA_MUTATOR_MODEL",
            "qwen3:8b",
            "qwen3:14b",
        ):
            self.assertIn(required, combined)

    def test_harbor_identity_names_ollama_provider(self) -> None:
        recipe = (ROOT / "recipes" / "dsh_hill_climb" / "evolve.yaml").read_text(encoding="utf-8")
        self.assertIn("model: ollama/qwen3:8b", recipe)
        self.assertNotIn("model: openai/qwen3:8b", recipe)

    def test_formal_evaluation_uses_docker_isolation(self) -> None:
        recipe = (ROOT / "recipes" / "dsh_hill_climb" / "evolve.yaml").read_text(encoding="utf-8")
        self.assertIn("backend: docker", recipe)
        self.assertNotIn("evolve.harbor_local:LocalEnvironment", recipe)
        base = (ROOT / "containers" / "evaluator" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("node:24.15.0-bookworm-slim", base)
        self.assertIn(
            "sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d",
            base,
        )
        self.assertIn("@deepseek-ai/dsh@0.1.1-rc.2", base)
        for dockerfile in sorted((ROOT / "tasks" / "synthetic-16").glob("*/environment/Dockerfile")):
            self.assertEqual(
                dockerfile.read_text(encoding="utf-8").splitlines()[0],
                "FROM dsh-ollama-eval:node24-dsh011rc2",
            )

    def test_both_dsh_patches_disable_workflow_without_subagents(self) -> None:
        for relative in ("config/dsh-qwen.patch.yml", "seed/dsh-qwen.patch.yml"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("- id: subagent\n  disabled: true", text)
            self.assertIn("- id: workflow-worker-thread\n  disabled: true", text)
            self.assertIn("maxRetries: 0", text)

    def test_plan_requires_verified_parallelism_and_fail_closed_canary(self) -> None:
        plan = PLAN.read_text(encoding="utf-8")
        self.assertIn("OLLAMA_NUM_PARALLEL=2", plan)
        self.assertIn("three consecutive", plan)
        self.assertIn("must start a new experiment", plan)
        self.assertIn("no automatic model fallback", plan)

    def test_clean_environment_keeps_node_on_path(self) -> None:
        module_path = ROOT / "seed" / "runtime_env.py"
        if not module_path.exists():
            self.fail("seed/runtime_env.py is missing")
        spec = importlib.util.spec_from_file_location("runtime_env", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        env = module.build_dsh_env(
            {
                "HOME": "/Users/test",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "TMPDIR": "/tmp",
                "LANG": "en_US.UTF-8",
                "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1",
                "OLLAMA_API_KEY": "ollama",
                "OLLAMA_TARGET_MODEL": "qwen3:8b",
                "UNRELATED_SECRET": "do-not-pass",
            },
            dsh_home="/logs/agent/dsh-home",
        )
        self.assertEqual(shutil.which("node", path=env["PATH"]), "/usr/local/bin/node")
        self.assertNotIn("UNRELATED_SECRET", env)
        self.assertEqual(env["OLLAMA_TARGET_MODEL"], "qwen3:8b")
        command = module.render_clean_command(["/repo/node_modules/.bin/dsh", "--version"], env)
        self.assertTrue(command.startswith("env -i "))

    def test_runtime_digest_covers_clean_environment_helper(self) -> None:
        source = (ROOT / "scripts" / "runtime_digest.py").read_text(encoding="utf-8")
        self.assertIn('"seed/runtime_env.py"', source)
        self.assertIn('"containers/evaluator/Dockerfile"', source)
        self.assertIn('"scripts/ollama_config.py"', source)


if __name__ == "__main__":
    unittest.main()
