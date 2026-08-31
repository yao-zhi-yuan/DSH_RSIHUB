#!/usr/bin/env python3
"""Use local Ollama Qwen 14B to make one bounded prompt edit."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .ollama_config import model_matches, validate_ollama_base_url
except ImportError:
    from ollama_config import model_matches, validate_ollama_base_url


MAX_EVIDENCE_CHARS = 45_000
MIN_PROMPT_CHARS = 80
MAX_PROMPT_CHARS = 12_000


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required setting: {name}")
    return value


def completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def read_bounded(path: Path, limit: int) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    return text[:limit]


def feedback_files(framework_prompt: str) -> list[Path]:
    match = re.search(r"^Feedback bundle:\s*(.+)$", framework_prompt, re.MULTILINE)
    if not match:
        return []
    root = Path(match.group(1).strip())
    return [
        root / "index.md",
        root / "evidence" / "selected.md",
        root / "last_accepted.diff",
    ]


def collect_evidence(framework_prompt: str) -> str:
    remaining = MAX_EVIDENCE_CHARS
    sections: list[str] = []
    for path in feedback_files(framework_prompt):
        if remaining <= 0:
            break
        text = read_bounded(path, remaining)
        if not text:
            continue
        sections.append(f"## {path.name}\n{text}")
        remaining -= len(text)
    return "\n\n".join(sections) or "No retained training feedback was available."


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("mutator response did not contain a JSON object") from None
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("mutator response must be a JSON object")
    return value


def request_mutation(current: str, framework_prompt: str, evidence: str) -> tuple[dict[str, Any], dict[str, Any]]:
    model = required("OLLAMA_MUTATOR_MODEL")
    payload = {
        "model": model,
        "temperature": 0,
        # Local inference is uncapped: let the mutator finish its JSON object
        # naturally instead of risking a truncated candidate.
        "messages": [
            {
                "role": "system",
                "content": (
                    "You improve a coding agent's general execution policy. Return one JSON object with keys "
                    "new_prompt, hypothesis, and expected_effect. Edit only the policy. Preserve useful behavior. "
                    "Do not mention task identifiers, benchmark splits, scores, hidden tests, evaluator internals, "
                    "credentials, endpoints, or model selection. Do not encode individual task answers."
                ),
            },
            {
                "role": "user",
                "content": (
                    "# Current policy\n\n"
                    f"{current}\n\n"
                    "# RSIHub mutation instructions\n\n"
                    f"{framework_prompt[:12000]}\n\n"
                    "# Training-only evidence\n\n"
                    f"{evidence}\n\n"
                    "Return JSON only. Make one concise, transferable improvement."
                ),
            },
        ],
    }
    request = urllib.request.Request(
        completions_url(validate_ollama_base_url(required("OLLAMA_BASE_URL"))),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {required('OLLAMA_API_KEY')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"mutator HTTP status {exc.code}") from None
    if not model_matches(model, body.get("model")):
        raise RuntimeError("mutator response model does not match OLLAMA_MUTATOR_MODEL")
    choice = (body.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    usage = body.get("usage") or {}
    usage_summary = {
        "wall_s": round(time.monotonic() - started, 3),
        "request_count": 1,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    return extract_json(content), usage_summary


def validate_new_prompt(value: object, current: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError("new_prompt must be a string")
    prompt = value.strip() + "\n"
    if not MIN_PROMPT_CHARS <= len(prompt) <= MAX_PROMPT_CHARS:
        raise RuntimeError(f"new_prompt length must be {MIN_PROMPT_CHARS}..{MAX_PROMPT_CHARS} characters")
    if prompt == current:
        raise RuntimeError("new_prompt is unchanged")
    forbidden = ("OLLAMA_", "API_KEY", "sealed", "reward.txt", "archive.jsonl")
    found = [token for token in forbidden if token.lower() in prompt.lower()]
    if found:
        raise RuntimeError("new_prompt contains forbidden experiment details: " + ", ".join(found))
    return prompt


def main() -> int:
    prompt_file = Path(required("EVOLVE_PROMPT_FILE"))
    target = Path.cwd() / "target" / "prompt.md"
    current = target.read_text(encoding="utf-8")
    framework_prompt = prompt_file.read_text(encoding="utf-8")
    evidence = collect_evidence(framework_prompt)
    proposal, usage = request_mutation(current, framework_prompt, evidence)
    new_prompt = validate_new_prompt(proposal.get("new_prompt"), current)
    target.write_text(new_prompt, encoding="utf-8")
    output = {
        "status": "updated",
        "changed": "target/prompt.md",
        "hypothesis": str(proposal.get("hypothesis") or "")[:1000],
        "expected_effect": str(proposal.get("expected_effect") or "")[:1000],
        "new_prompt_chars": len(new_prompt),
        "usage": usage,
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - command boundary returns sanitized failure
        print(json.dumps({"status": "error", "error_type": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from None
