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
        self.assertEqual(report["baseline"]["sealed"]["score"], 0.25)
        self.assertEqual(len(report["generations"]), 3)
        self.assertEqual(report["final"]["champion_genid"], "1")
        self.assertEqual(report["final"]["sealed"]["expected_trials"], 4)
        # Target rollout tokens are summed from the per-gen analyze metrics.
        self.assertEqual(report["resources"]["target"]["total_tokens"], 3300 + 4400 + 3740)
        self.assertEqual(report["resources"]["mutator"]["request_count"], 3)
        self.assertEqual(report["audit"]["missing_artifacts"], [])

    def test_retry_resolves_to_certified_attempt(self) -> None:
        # gen 3 has an infrastructure_failed attempt 1 and a certified attempt 2;
        # the report must score the retry, not the failure that triggered it.
        report = build_report.build_report(self._workspace())
        gen3 = report["generations"][2]
        self.assertEqual(gen3["attempt"], 2)
        self.assertEqual(gen3["gate"]["score"], 0.5)
        self.assertEqual(gen3["verdict"], "keep")
        self.assertFalse(gen3["became_champion"])

    def test_generation_carries_hypothesis(self) -> None:
        report = build_report.build_report(self._workspace())
        gen1 = report["generations"][0]
        self.assertIn("outcome checking", gen1["mutation"]["hypothesis"])
        self.assertTrue(gen1["mutation"]["expected_effect"])

    def test_summary_embeds_diff_and_disk(self) -> None:
        report = build_report.build_report(self._workspace())
        # Each generation embeds its redacted diff so downstream readers (the
        # visualization) need only summary.json.
        for generation in report["generations"]:
            self.assertIn("diff --git", generation["diff"])
        self.assertNotIn("SECRETLEAK12345", report["generations"][1]["diff"])
        self.assertIsInstance(report["resources"]["disk_bytes"], int)
        self.assertGreater(report["resources"]["disk_bytes"], 0)

    def test_missing_referenced_file_fails_with_path(self) -> None:
        workspace = self._workspace()
        (workspace / "runs" / "gen-2" / "mutate" / "patch.diff").unlink()
        with self.assertRaises(build_report.ReportError) as caught:
            build_report.build_report(workspace)
        self.assertIn("runs/gen-2/mutate/patch.diff", str(caught.exception))

    def test_missing_key_names_the_artifact(self) -> None:
        workspace = self._workspace()
        (workspace / "best_ever.json").unlink()
        with self.assertRaises(build_report.ReportError) as caught:
            build_report.build_report(workspace)
        self.assertIn("best_ever.json", str(caught.exception))

    def test_published_markdown_redacts_credentials(self) -> None:
        workspace = self._workspace()
        output_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(output_dir, ignore_errors=True))
        build_report.write_report(workspace, output_dir)
        diff = (output_dir / "qwen-first-v1" / "candidate-diffs" / "gen-2.diff").read_text(encoding="utf-8")
        self.assertNotIn("SECRETLEAK12345", diff)
        self.assertIn("[REDACTED]", diff)

    def test_manifest_hashes_every_written_artifact(self) -> None:
        workspace = self._workspace()
        output_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(output_dir, ignore_errors=True))
        build_report.write_report(workspace, output_dir)
        bundle = output_dir / "qwen-first-v1"
        manifest = (bundle / "manifest.sha256").read_text(encoding="utf-8")
        self.assertIn("summary.json", manifest)
        self.assertIn("candidate-diffs/gen-1.diff", manifest)

    def test_check_round_trips_written_bundle(self) -> None:
        workspace = self._workspace()
        output_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(output_dir, ignore_errors=True))
        build_report.write_report(workspace, output_dir)
        self.assertEqual(build_report.check_report(workspace, output_dir), [])
        # A tampered artifact must be reported as a hash mismatch.
        (output_dir / "qwen-first-v1" / "report.md").write_text("tampered\n", encoding="utf-8")
        problems = build_report.check_report(workspace, output_dir)
        self.assertTrue(any("report.md" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
