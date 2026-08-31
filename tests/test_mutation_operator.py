from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import rsihub_qwen_prompt_mutate as operator


class BuildMutationInputTests(unittest.TestCase):
    def _run_dir(self, selected: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        run_dir = Path(temporary.name)
        evidence = run_dir / "feedback" / "evidence"
        evidence.mkdir(parents=True)
        (evidence / "selected.md").write_text(selected, encoding="utf-8")
        return run_dir

    def test_references_and_hashes_feedback_bundle(self) -> None:
        run_dir = self._run_dir("Task contract-clamp failed the oracle check.\n")
        prompt, inputs = operator.build_mutation_input('{"failed": 1}', run_dir)
        self.assertIn("Feedback bundle:", prompt)
        self.assertIn("selected.md", prompt)
        self.assertEqual(inputs[0]["path"], "feedback/evidence/selected.md")
        self.assertEqual(len(inputs[0]["sha256"]), 64)

    def test_redacts_credentials_but_keeps_task_evidence(self) -> None:
        run_dir = self._run_dir(
            "Task contract-clamp failed.\napi_key=supersecretvalue123\n"
        )
        prompt, _inputs = operator.build_mutation_input('{"failed": 1}', run_dir)
        self.assertIn("contract-clamp", prompt)
        self.assertNotIn("supersecretvalue123", prompt)
        self.assertIn("[REDACTED]", prompt)


class ParseCommandUsageTests(unittest.TestCase):
    def test_parses_final_json_usage(self) -> None:
        stdout = (
            "diagnostic log line\n"
            '{"status":"updated","usage":{"wall_s":1.25,"prompt_tokens":433,'
            '"completion_tokens":583,"total_tokens":1016}}\n'
        )
        usage = operator.parse_command_usage(stdout, 1.25)
        self.assertEqual(
            usage,
            {
                "usd": 0,
                "wall_s": 1.25,
                "prompt_tokens": 433,
                "completion_tokens": 583,
                "total_tokens": 1016,
            },
        )

    def test_missing_usage_fails(self) -> None:
        with self.assertRaises(ValueError):
            operator.parse_command_usage('{"status":"updated"}', 1.0)

    def test_non_integer_tokens_fail(self) -> None:
        stdout = '{"usage":{"prompt_tokens":"x","completion_tokens":1,"total_tokens":2}}'
        with self.assertRaises(ValueError):
            operator.parse_command_usage(stdout, 1.0)


if __name__ == "__main__":
    unittest.main()
