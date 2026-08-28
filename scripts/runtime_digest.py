#!/usr/bin/env python3
"""Compute the immutable identity of the local evaluator runtime."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "config/upstream-lock.json",
    "containers/evaluator/Dockerfile",
    "package-lock.json",
    "vendor/RSIHub/uv.lock",
    "seed/agent.py",
    "seed/runtime_env.py",
    "seed/dsh-qwen.patch.yml",
    "scripts/ollama_config.py",
    "scripts/rsihub_qwen_prompt_mutate.py",
    "scripts/qwen_mutate.py",
    "patches/rsihub-run-plan-expected-trials.patch",
)


def command_version(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def main() -> None:
    digest = hashlib.sha256()
    for relative in FILES:
        path = ROOT / relative
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    facts = (
        f"python={sys.version.split()[0]}",
        f"platform={platform.system()}-{platform.machine()}",
        f"node={command_version(['node', '--version'])}",
        f"dsh={command_version([str(ROOT / 'node_modules/.bin/dsh'), '--version'])}",
    )
    for fact in facts:
        digest.update(fact.encode("utf-8") + b"\0")
    print(f"sha256:{digest.hexdigest()}")


if __name__ == "__main__":
    main()
