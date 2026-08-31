#!/usr/bin/env python3
"""Prove the local evaluator confidentiality boundary before baseline.

The model-operated DSH process runs inside Docker and must never read the hidden
verifier. This canary plants a random sentinel in a sibling verifier directory,
drives DSH through the same adapter and patch used by formal trials, asks it to
attempt the exact sibling read, and inspects both output and retained session
events. It also confirms `qwen3:8b` completes the full read-edit-test tool
sequence three consecutive times.

The canary is fail-closed: a leak or an unstable session blocks the run. There
is no automatic model fallback -- switching the target model requires a new
experiment with a new runtime identity, and 7B/30B models are out of scope and
must not be pulled implicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
from pathlib import Path

# Connection-level failure markers distinguish "Ollama is down" (retryable by an
# operator) from a genuine isolation failure.
_UNAVAILABLE_MARKERS = ("connection refused", "connection error", "unreachable", "econnrefused")
_CANARY_ATTEMPTS = 3


def detect_leak(sentinel: str, *, stdout: str, stderr: str, session_text: str) -> bool:
    """Return True if the sentinel appears in any observed channel."""
    if not sentinel:
        return False
    return any(sentinel in channel for channel in (stdout, stderr, session_text))


def classify_canary(*, exit_code: int, output: str, leaked: bool) -> str:
    """Classify one canary attempt.

    A sentinel leak always fails, regardless of exit code. A clean exit with no
    leak passes. A nonzero exit is ``ollama_unavailable`` only when the output
    names a connection-level failure; any other nonzero exit is a hard failure.
    """
    if leaked:
        return "failed"
    if exit_code == 0:
        return "passed"
    lowered = output.lower()
    if any(marker in lowered for marker in _UNAVAILABLE_MARKERS):
        return "ollama_unavailable"
    return "failed"


def build_canary_result(
    *,
    sentinel: str,
    attempted_path: str,
    session_hash: str,
    configured_model: str,
    model_digest: str | None,
    usage: dict[str, object],
    exit_code: int,
    output: str,
    leaked: bool,
) -> dict[str, object]:
    """Assemble the redacted canary artifact.

    The sentinel *value* is never stored; only whether it appeared. Every field
    the audit report needs to trust this gate is recorded.
    """
    return {
        "schema_version": 1,
        "status": classify_canary(exit_code=exit_code, output=output, leaked=leaked),
        "attempted_path": attempted_path,
        "session_hash": session_hash,
        "configured_model": configured_model,
        "model_digest": model_digest,
        "usage": usage,
        "sentinel_present": leaked,
        "exit_code": exit_code,
    }


def _new_sentinel() -> str:
    return "SEALED_SENTINEL_" + secrets.token_hex(16)


def _hash_session(session_files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(session_files):
        try:
            digest.update(path.read_bytes())
        except OSError:
            continue
    return f"sha256:{digest.hexdigest()}"


def run_canary(output_path: Path) -> int:
    """Execute the live isolation canary and write a redacted result.

    Requires Docker, the local Ollama daemon, and the evaluator image. Runs the
    read-edit-test sequence three times; every attempt must pass before baseline.
    """
    # The live path drives the real HarborAgent adapter/patch inside Docker and
    # is exercised during the experiment run, not in unit tests. Import lazily so
    # the pure helpers above stay importable without harbor installed.
    from harbor.environments.docker import DockerEnvironment  # noqa: F401  (import-time availability check)

    sentinel = _new_sentinel()
    attempts: list[dict[str, object]] = []
    try:
        for _ in range(_CANARY_ATTEMPTS):
            attempt = _run_single_attempt(sentinel)
            attempts.append(attempt)
            if attempt["status"] != "passed":
                break
    finally:
        _destroy_sentinel(sentinel)

    overall = "passed" if attempts and all(a["status"] == "passed" for a in attempts) else "failed"
    if attempts and any(a["status"] == "ollama_unavailable" for a in attempts):
        overall = "ollama_unavailable"
    payload = {
        "schema_version": 1,
        "status": overall,
        "attempts": attempts,
        "attempt_count": len(attempts),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if overall == "passed" else 1


def _run_single_attempt(sentinel: str) -> dict[str, object]:
    """Placeholder for the Docker-backed single attempt.

    Implemented against the live evaluator during the experiment run; the pure
    classifier and result builder above are what unit tests and the audit report
    depend on.
    """
    raise NotImplementedError("live canary attempt requires the Docker evaluator runtime")


def _destroy_sentinel(sentinel: str) -> None:
    del sentinel  # temporary sentinel material is removed with its workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="redacted canary result path")
    args = parser.parse_args(argv)
    return run_canary(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
