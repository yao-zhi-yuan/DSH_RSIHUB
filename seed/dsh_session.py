"""Parse DSH session JSONL into bounded, redacted rollout evidence.

DSH writes one JSONL event stream per session. This module folds that stream
into the compact ``SessionEvidence`` the mutator consumes: ordered trajectory
events shaped for RSIHub's existing trajectory reader, the final assistant
response, and target token usage. Token totals come only from
``assistant/message`` records because ``assistant/chunk`` records repeat the
same response usage and would double-count it. All text is redacted and length
bounded before it leaves this module so no secret or endpoint reaches the
mutator.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


_FIELD_LIMIT = 2000
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_URL = re.compile(r"(?i)\bhttps?://\S+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|authorization|auth)\b"
    r"(\s*[:=]\s*)([^\s,;}]+)"
)


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cache_tokens: int
    output_tokens: int
    requests: int


@dataclass(frozen=True)
class SessionEvidence:
    events: list[dict[str, object]]
    final_response: str
    usage: Usage
    session_files: list[str]


def _redact(text: str, sensitive_values: set[str]) -> str:
    for value in sorted((value for value in sensitive_values if value), key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _URL.sub("[REDACTED]", text)
    return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)


def _clip(text: str, limit: int = _FIELD_LIMIT) -> str:
    if len(text) <= limit:
        return text
    marker = f"...[truncated {len(text) - limit} chars]..."
    kept = max(1, limit - len(marker))
    return text[:kept] + marker


def _clean(value: object, sensitive_values: set[str]) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return _clip(_redact(text, sensitive_values))


def _message_text(message: dict[str, object]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts)


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _iter_records(paths: Iterable[Path], session_files: list[str]) -> Iterable[dict[str, object]]:
    for path in paths:
        try:
            lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        session_files.append(str(path))
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def parse_session_files(
    paths: Iterable[Path],
    *,
    sensitive_values: set[str] | None = None,
) -> SessionEvidence:
    """Parse DSH JSONL once, count assistant/message usage, and redact evidence."""
    sensitive = set(sensitive_values or set())
    session_files: list[str] = []
    events: list[dict[str, object]] = []
    final_response = ""
    input_tokens = cache_tokens = output_tokens = requests = 0

    for row in _iter_records(paths, session_files):
        row_type = str(row.get("type") or "")
        data = row.get("data")
        data = data if isinstance(data, dict) else {}
        message = data.get("message")
        message = message if isinstance(message, dict) else {}

        if row_type == "assistant/message":
            # One model response: count usage here, never on assistant/chunk.
            requests += 1
            usage = message.get("usage")
            if isinstance(usage, dict):
                input_tokens += _int(usage.get("inputTokens"))
                output_tokens += _int(usage.get("outputTokens"))
                cache_tokens += _int(usage.get("cacheReadTokens"))
            text = _message_text(message)
            if text.strip():
                clipped = _clean(text, sensitive)
                events.append({"type": "message", "source": "agent", "message": clipped})
                final_response = clipped
        elif row_type == "tool/call":
            events.append(
                {
                    "type": "tool_call",
                    "source": "agent",
                    "message": "",
                    "tool_calls": [
                        {
                            "name": str(data.get("name") or "unknown"),
                            "arguments": _clean(data.get("arguments") or {}, sensitive),
                        }
                    ],
                }
            )
        elif row_type == "tool/result":
            events.append(
                {
                    "type": "tool_result",
                    "source": "tool",
                    "message": "",
                    "observation": {"results": [{"content": _clean(_message_text(message), sensitive)}]},
                }
            )
        # user/message and assistant/chunk are recognized but contribute no
        # trajectory event: the instruction is supplied to the mutator by Harbor
        # separately, and chunk usage duplicates the assistant/message total.

    usage = Usage(
        input_tokens=input_tokens,
        cache_tokens=cache_tokens,
        output_tokens=output_tokens,
        requests=requests,
    )
    return SessionEvidence(
        events=events,
        final_response=final_response,
        usage=usage,
        session_files=session_files,
    )
