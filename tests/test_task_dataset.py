from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_tasks


class GeneratedTaskTests(unittest.TestCase):
    def generate(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "synthetic-16"
        with patch.object(generate_tasks, "TASKS_ROOT", root):
            generate_tasks.generate()
        return root

    def test_generates_exactly_sixteen_tasks(self) -> None:
        root = self.generate()
        self.assertEqual(len([path for path in root.iterdir() if path.is_dir()]), 16)

    def test_every_generated_python_file_parses(self) -> None:
        root = self.generate()
        failures = []
        for path in sorted(root.rglob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as error:
                failures.append(f"{path.relative_to(root)}:{error.lineno}:{error.msg}")
        self.assertEqual(failures, [])

    def test_required_result_expected_unique_word_count_is_three(self) -> None:
        root = self.generate()
        verifier = (
            root / "artifact-required-result" / "tests" / "verify.py"
        ).read_text(encoding="utf-8")
        self.assertIn("'unique_words': 3", verifier)
        self.assertNotIn("'unique_words': 4", verifier)

    def test_jsonl_fixture_keeps_escaped_newlines(self) -> None:
        root = self.generate()
        visible = (
            root / "verification-jsonl-summary" / "environment" / "test_visible.py"
        ).read_text(encoding="utf-8")
        self.assertIn(r"""summarize_jsonl('{"value":2}\n')""", visible)


if __name__ == "__main__":
    unittest.main()
