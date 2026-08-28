#!/usr/bin/env python3
"""Probe both configured models through the local Ollama endpoint."""

from __future__ import annotations

import argparse
import json
import os
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


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
RESULT_PATH = ROOT / "runs" / "smoke" / "ollama-smoke.json"


def load_dotenv(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required setting: {name}")
    return value


def completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def safe_usage(body: dict[str, Any]) -> dict[str, int | None]:
    usage = body.get("usage") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def probe(role: str, *, base_url: str, api_key: str, model: str) -> dict[str, Any]:
    is_target = role == "target"
    base_url = validate_ollama_base_url(base_url)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Call the probe tool with value 'ok'. Do not answer in plain text."
                    if is_target
                    else "Return only this JSON object: {\"status\":\"ok\"}"
                ),
            }
        ],
        "temperature": 0,
        "max_tokens": 64,
    }
    if is_target:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "probe",
                    "description": "Complete the API smoke probe.",
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                        "additionalProperties": False,
                    },
                },
            }
        ]
        payload["tool_choice"] = "auto"

    request = urllib.request.Request(
        completions_url(base_url),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status_code = response.status
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return {
            "role": role,
            "ok": False,
            "status_code": exc.code,
            "elapsed_ms": elapsed_ms,
            "error_type": "http_error",
        }
    except Exception as exc:  # noqa: BLE001 - sanitized at the trust boundary
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return {
            "role": role,
            "ok": False,
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "error_type": type(exc).__name__,
        }

    elapsed_ms = round((time.monotonic() - started) * 1000)
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    tool_calls = message.get("tool_calls") or []
    tool_name = None
    if tool_calls:
        tool_name = ((tool_calls[0] or {}).get("function") or {}).get("name")

    if is_target:
        contract_ok = tool_name == "probe"
    else:
        content = message.get("content") or ""
        try:
            contract_ok = json.loads(content).get("status") == "ok"
        except (json.JSONDecodeError, AttributeError):
            contract_ok = False

    model_ok = model_matches(model, body.get("model"))
    return {
        "role": role,
        "ok": status_code == 200 and contract_ok and model_ok,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "configured_model": model,
        "returned_model": body.get("model"),
        "model_ok": model_ok,
        "finish_reason": choice.get("finish_reason"),
        "tool_call_name": tool_name,
        "contract_ok": contract_ok,
        "usage": safe_usage(body),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("all", "target", "mutator"), default="all")
    args = parser.parse_args()
    if not ENV_PATH.exists():
        print("missing .env; copy .env.example and fill it locally", file=sys.stderr)
        return 2
    load_dotenv(ENV_PATH)
    probes = {
        "target": lambda: probe(
            "target",
            base_url=required("OLLAMA_BASE_URL"),
            api_key=required("OLLAMA_API_KEY"),
            model=required("OLLAMA_TARGET_MODEL"),
        ),
        "mutator": lambda: probe(
            "mutator",
            base_url=required("OLLAMA_BASE_URL"),
            api_key=required("OLLAMA_API_KEY"),
            model=required("OLLAMA_MUTATOR_MODEL"),
        ),
    }
    roles = ("target", "mutator") if args.role == "all" else (args.role,)
    results = [probes[role]() for role in roles]
    report = {
        "schema_version": 1,
        "all_ok": all(item["ok"] for item in results),
        "results": results,
    }
    result_path = RESULT_PATH if args.role == "all" else RESULT_PATH.with_name(f"api-smoke-{args.role}.json")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
