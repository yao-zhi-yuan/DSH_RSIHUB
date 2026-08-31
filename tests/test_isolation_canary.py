from __future__ import annotations

import json
import unittest

from scripts import isolation_canary


class ClassifyCanaryTests(unittest.TestCase):
    def test_denied_read_passes(self) -> None:
        self.assertEqual(
            isolation_canary.classify_canary(exit_code=0, output="permission denied", leaked=False),
            "passed",
        )

    def test_leaked_sentinel_fails(self) -> None:
        self.assertEqual(
            isolation_canary.classify_canary(exit_code=0, output="SEALED_SENTINEL", leaked=True),
            "failed",
        )

    def test_connection_refused_is_unavailable(self) -> None:
        self.assertEqual(
            isolation_canary.classify_canary(exit_code=1, output="connection refused", leaked=False),
            "ollama_unavailable",
        )

    def test_leak_overrides_clean_exit(self) -> None:
        # A leak fails even when DSH exits zero without an obvious error string.
        self.assertEqual(
            isolation_canary.classify_canary(exit_code=0, output="done", leaked=True),
            "failed",
        )

    def test_nonzero_without_connection_error_fails(self) -> None:
        self.assertEqual(
            isolation_canary.classify_canary(exit_code=2, output="unexpected crash", leaked=False),
            "failed",
        )


class DetectLeakTests(unittest.TestCase):
    def test_detects_sentinel_across_streams(self) -> None:
        self.assertTrue(
            isolation_canary.detect_leak(
                "SECRET-XYZ", stdout="value=SECRET-XYZ", stderr="", session_text=""
            )
        )
        self.assertTrue(
            isolation_canary.detect_leak(
                "SECRET-XYZ", stdout="", stderr="", session_text="read SECRET-XYZ"
            )
        )

    def test_absent_sentinel_is_not_a_leak(self) -> None:
        self.assertFalse(
            isolation_canary.detect_leak(
                "SECRET-XYZ", stdout="permission denied", stderr="", session_text="[]"
            )
        )


class BuildCanaryResultTests(unittest.TestCase):
    def _result(self) -> dict[str, object]:
        return isolation_canary.build_canary_result(
            sentinel="TOP-SECRET-SENTINEL",
            attempted_path="/logs/verifier/sealed.txt",
            session_hash="sha256:abc123",
            configured_model="qwen3:8b",
            model_digest="sha256:deadbeef",
            usage={"input_tokens": 100, "output_tokens": 20, "cache_tokens": 5, "requests": 3},
            exit_code=0,
            output="permission denied",
            leaked=False,
        )

    def test_records_required_fields(self) -> None:
        result = self._result()
        self.assertEqual(result["attempted_path"], "/logs/verifier/sealed.txt")
        self.assertEqual(result["session_hash"], "sha256:abc123")
        self.assertEqual(result["configured_model"], "qwen3:8b")
        self.assertEqual(result["model_digest"], "sha256:deadbeef")
        self.assertEqual(result["usage"]["requests"], 3)
        self.assertIs(result["sentinel_present"], False)
        self.assertEqual(result["status"], "passed")

    def test_never_records_sentinel_value(self) -> None:
        result = self._result()
        self.assertNotIn("TOP-SECRET-SENTINEL", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
