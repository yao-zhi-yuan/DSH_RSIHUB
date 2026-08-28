from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OllamaEndpointTests(unittest.TestCase):
    def load_module(self):
        path = ROOT / "scripts" / "ollama_config.py"
        if not path.exists():
            self.fail("scripts/ollama_config.py is missing")
        spec = importlib.util.spec_from_file_location("ollama_config", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_accepts_only_loopback_openai_endpoint(self) -> None:
        module = self.load_module()
        self.assertEqual(
            module.validate_ollama_base_url("http://127.0.0.1:11434/v1"),
            "http://127.0.0.1:11434/v1",
        )
        self.assertEqual(
            module.validate_ollama_base_url("http://localhost:11434/v1/"),
            "http://localhost:11434/v1",
        )
        for invalid in (
            "https://api.example.com/v1",
            "http://192.168.1.10:11434/v1",
            "http://127.0.0.1:11434/api",
        ):
            with self.assertRaises(ValueError):
                module.validate_ollama_base_url(invalid)

    def test_requires_exact_model_identity(self) -> None:
        module = self.load_module()
        self.assertTrue(module.model_matches("qwen3:8b", "qwen3:8b"))
        self.assertFalse(module.model_matches("qwen3:8b", "qwen3:14b"))
        self.assertFalse(module.model_matches("qwen3:8b", None))


if __name__ == "__main__":
    unittest.main()
