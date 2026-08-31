from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import build_report


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "audit-workspace"


class BuildReportTests(unittest.TestCase):
    def _workspace(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        workspace = Path(temporary.name) / "audit-workspace"
        shutil.copytree(FIXTURE, workspace)
        return workspace

    def test_report_summarizes_run(self) -> None:
        report = build_report.build_report(self._workspace())
        self.assertEqual(report["baseline"]["gate"]["score"], 0.5)
        self.assertEqual(len(report["generations"]), 3)
        self.assertEqual(report["final"]["sealed"]["expected_trials"], 4)
        self.assertEqual(report["resources"]["target"]["total_tokens"], 12345)
        self.assertEqual(report["resources"]["mutator"]["request_count"], 3)
        self.assertEqual(report["audit"]["missing_artifacts"], [])

    def test_missing_referenced_file_fails_with_path(self) -> None:
        workspace = self._workspace()
        (workspace / "mutate" / "gen-2" / "patch.diff").unlink()
        with self.assertRaises(build_report.ReportError) as caught:
            build_report.build_report(workspace)
        self.assertIn("mutate/gen-2/patch.diff", str(caught.exception))

    def test_published_markdown_redacts_credentials(self) -> None:
        workspace = self._workspace()
        output_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(output_dir, ignore_errors=True))
        build_report.write_report(workspace, output_dir)
        markdown = (output_dir / "qwen-first-v1" / "report.md").read_text(encoding="utf-8")
        self.assertNotIn("SECRETLEAK12345", markdown)
        self.assertIn("[REDACTED]", markdown)

    def test_manifest_hashes_every_written_artifact(self) -> None:
        workspace = self._workspace()
        output_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(output_dir, ignore_errors=True))
        build_report.write_report(workspace, output_dir)
        bundle = output_dir / "qwen-first-v1"
        manifest = (bundle / "manifest.sha256").read_text(encoding="utf-8")
        self.assertIn("summary.json", manifest)
        self.assertIn("candidate-diffs/gen-1.diff", manifest)


if __name__ == "__main__":
    unittest.main()
