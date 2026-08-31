from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from seed.dsh_session import SessionEvidence, Usage, parse_session_files


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dsh-session.jsonl"


class ParseSessionTests(unittest.TestCase):
    def _write(self, *lines: str) -> Path:
        temporary = tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        self.addCleanup(lambda: Path(temporary.name).unlink(missing_ok=True))
        temporary.write("\n".join(lines) + "\n")
        temporary.close()
        return Path(temporary.name)

    def test_parses_usage_events_and_redacts(self) -> None:
        evidence = parse_session_files([FIXTURE], sensitive_values={"secret-value"})
        self.assertIsInstance(evidence, SessionEvidence)
        self.assertIsInstance(evidence.usage, Usage)
        self.assertEqual(evidence.usage.input_tokens, 220)
        self.assertEqual(evidence.usage.output_tokens, 35)
        self.assertEqual(evidence.usage.cache_tokens, 90)
        self.assertEqual(evidence.usage.requests, 2)
        self.assertEqual(evidence.final_response, "Done.")
        self.assertEqual(
            [event["type"] for event in evidence.events],
            ["tool_call", "tool_result", "message"],
        )
        self.assertNotIn("secret-value", json.dumps(evidence.events))
        self.assertIn("[REDACTED]", json.dumps(evidence.events))
        self.assertEqual(evidence.session_files, [str(FIXTURE)])

    def test_ignores_malformed_jsonl(self) -> None:
        path = self._write(
            "not json at all",
            "{",
            json.dumps(
                {
                    "type": "assistant/message",
                    "seq": 1,
                    "data": {
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "Hi."}],
                            "usage": {"inputTokens": 5, "outputTokens": 2, "cacheReadTokens": 1},
                        }
                    },
                }
            ),
        )
        evidence = parse_session_files([path])
        self.assertEqual(evidence.usage.input_tokens, 5)
        self.assertEqual(evidence.usage.requests, 1)
        self.assertEqual(evidence.final_response, "Hi.")

    def test_does_not_double_count_chunk_usage(self) -> None:
        path = self._write(
            json.dumps(
                {
                    "type": "assistant/message",
                    "seq": 1,
                    "data": {
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "Answer."}],
                            "usage": {"inputTokens": 10, "outputTokens": 4, "cacheReadTokens": 2},
                        }
                    },
                }
            ),
            json.dumps(
                {
                    "type": "assistant/chunk",
                    "seq": 2,
                    "data": {
                        "message": {
                            "role": "assistant",
                            "usage": {"inputTokens": 10, "outputTokens": 4, "cacheReadTokens": 2},
                        }
                    },
                }
            ),
        )
        evidence = parse_session_files([path])
        self.assertEqual(evidence.usage.input_tokens, 10)
        self.assertEqual(evidence.usage.output_tokens, 4)
        self.assertEqual(evidence.usage.cache_tokens, 2)
        self.assertEqual(evidence.usage.requests, 1)

    def test_absent_usage_contributes_zero(self) -> None:
        path = self._write(
            json.dumps(
                {
                    "type": "assistant/message",
                    "seq": 1,
                    "data": {
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "No usage here."}],
                        }
                    },
                }
            ),
        )
        evidence = parse_session_files([path])
        self.assertEqual(evidence.usage.input_tokens, 0)
        self.assertEqual(evidence.usage.output_tokens, 0)
        self.assertEqual(evidence.usage.cache_tokens, 0)
        self.assertEqual(evidence.usage.requests, 1)

    def test_redacts_bearer_token_and_endpoint(self) -> None:
        path = self._write(
            json.dumps(
                {
                    "type": "tool/result",
                    "seq": 1,
                    "data": {
                        "callId": "call-9",
                        "message": {
                            "role": "tool",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Authorization: Bearer sk-abc123 to http://host.docker.internal:11434/v1",
                                }
                            ],
                        },
                    },
                }
            ),
        )
        evidence = parse_session_files([path])
        serialized = json.dumps(evidence.events)
        self.assertNotIn("sk-abc123", serialized)
        self.assertNotIn("host.docker.internal", serialized)
        self.assertIn("[REDACTED]", serialized)


if __name__ == "__main__":
    unittest.main()
