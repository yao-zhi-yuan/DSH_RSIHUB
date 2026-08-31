#!/usr/bin/env python3
"""Compute the immutable identity of the local evaluator runtime."""

from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = "seed"
FILES = (
    "config/upstream-lock.json",
    "containers/evaluator/Dockerfile",
    "package-lock.json",
    "vendor/RSIHub/uv.lock",
    "scripts/ollama_config.py",
    "scripts/rsihub_qwen_prompt_mutate.py",
    "scripts/qwen_mutate.py",
    "patches/rsihub-run-plan-expected-trials.patch",
)


def seed_files() -> list[str]:
    """Every regular file under seed/, by sorted POSIX relative path.

    Hashing the whole tree keeps the runtime identity honest as the seed grows,
    rather than tracking a hand-maintained list of individual seed modules.
    """
    root = ROOT / SEED_DIR
    relatives = []
    for path in root.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relatives.append(path.relative_to(ROOT).as_posix())
    return sorted(relatives)


def command_version(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def main() -> None:
    digest = hashlib.sha256()
    for relative in (*seed_files(), *FILES):
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
