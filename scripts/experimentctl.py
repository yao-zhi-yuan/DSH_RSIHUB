#!/usr/bin/env python3
"""Model-aware control plane for the local Ollama Hill Climb experiment.

This is the single operator entry point. It parses the outer ``.env`` without
logging its values, passes a fixed allowlist to every subprocess, verifies the
local Ollama daemon and exact model identities, and records each command it runs
under ``reports/control/``. Every gate is fail-closed: the first failure stops
the run and no model request is ever retried automatically.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

try:
    from .ollama_config import validate_ollama_base_url
except ImportError:
    from ollama_config import validate_ollama_base_url


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
CONTROL_DIR = ROOT / "reports" / "control"
RECIPE_PATH = ROOT / "recipes" / "dsh_hill_climb" / "evolve.yaml"
DATASET_DIR = ROOT / "tasks" / "synthetic-16"
REQUIRED_MODELS = ("OLLAMA_TARGET_MODEL", "OLLAMA_MUTATOR_MODEL")
# Only these names ever reach a subprocess; everything else in .env stays local.
RUNTIME_ALLOWLIST = (
    "OLLAMA_BASE_URL",
    "OLLAMA_CONTAINER_BASE_URL",
    "OLLAMA_API_KEY",
    "OLLAMA_TARGET_MODEL",
    "OLLAMA_MUTATOR_MODEL",
    "OLLAMA_NUM_PARALLEL",
    "EXPERIMENT_MAX_GENERATIONS",
    "EXPERIMENT_CHILDREN_PER_GENERATION",
    "EXPERIMENT_MAX_CONCURRENCY",
    "EXPERIMENT_TASK_TIMEOUT_SECONDS",
)

Opener = Callable[..., object]


class GateError(RuntimeError):
    """A fail-closed control-plane gate refused to continue."""


def parse_dotenv(path: Path) -> dict[str, str]:
    """Parse ``.env`` into a dict without ever logging its values."""
    values: dict[str, str] = {}
    if not path.exists():
        raise GateError(f"missing {path.name}; copy .env.example and fill it locally")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def build_runtime_env(source: Mapping[str, str], *, root: Path) -> dict[str, str]:
    """Return the fixed allowlist env passed to subprocesses.

    Drops every unrelated parent value, requires a loopback Ollama URL, and
    derives ``DSH_BIN`` and ``EVOLVE_EXPERIMENT_ROOT`` from the checkout rather
    than trusting machine-specific paths.
    """
    base_url = source.get("OLLAMA_BASE_URL", "").strip()
    if not base_url:
        raise ValueError("missing required setting: OLLAMA_BASE_URL")
    validate_ollama_base_url(base_url)  # raises ValueError for non-loopback URLs
    env: dict[str, str] = {}
    for name in RUNTIME_ALLOWLIST:
        value = source.get(name, "").strip()
        if value:
            env[name] = value
    for name in REQUIRED_MODELS:
        if not env.get(name):
            raise ValueError(f"missing required setting: {name}")
    env["DSH_BIN"] = str(root / "node_modules" / ".bin" / "dsh")
    env["EVOLVE_EXPERIMENT_ROOT"] = str(root)
    return env


def _default_opener(url: str, timeout: float | None = None) -> object:
    return urllib.request.urlopen(url, timeout=timeout)


def probe_models(
    base_url: str,
    required: Sequence[str],
    *,
    opener: Opener = _default_opener,
) -> dict[str, dict[str, object]]:
    """Confirm each required tag exists and record its digest and size.

    Fail-closed: a stopped daemon, a missing tag, or a malformed response all
    raise ``RuntimeError``. The request is never retried.
    """
    normalized = validate_ollama_base_url(base_url)
    tags_url = normalized[: -len("/v1")] + "/api/tags"
    try:
        with opener(tags_url, timeout=30) as response:  # type: ignore[union-attr]
            raw = response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"Ollama daemon is unreachable at {tags_url}: {exc}") from None
    try:
        payload = json.loads(raw)
        entries = payload["models"]
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        raise RuntimeError("Ollama /api/tags returned a malformed response") from None
    catalog = {
        str(entry.get("model")): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("model")
    }
    resolved: dict[str, dict[str, object]] = {}
    for tag in required:
        entry = catalog.get(tag)
        if entry is None:
            raise RuntimeError(f"required Ollama model is not installed: {tag}")
        resolved[tag] = {"digest": entry.get("digest"), "size": entry.get("size")}
    return resolved


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(text: str, secrets: Sequence[str]) -> str:
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text


def record_command(
    name: str,
    argv: Sequence[str],
    env: Mapping[str, str],
    *,
    secrets: Sequence[str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and preserve its sanitized transcript under reports/control/."""
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    started = _now()
    start = time.monotonic()
    completed = subprocess.run(
        list(argv),
        cwd=str(cwd or ROOT),
        env=dict(env),
        text=True,
        capture_output=True,
        check=False,
    )
    record = {
        "schema_version": 1,
        "command": list(argv),
        "return_code": completed.returncode,
        "started_at": started,
        "finished_at": _now(),
        "wall_s": round(time.monotonic() - start, 3),
        "stdout": _sanitize(completed.stdout, secrets),
        "stderr": _sanitize(completed.stderr, secrets),
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    (CONTROL_DIR / f"{stamp}-{name}.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return completed


def _subprocess_env(runtime: Mapping[str, str]) -> dict[str, str]:
    import os

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    tmp = os.environ.get("TMPDIR")
    if tmp:
        env["TMPDIR"] = tmp
    env.update(runtime)
    return env


def _load(require_models: bool = True) -> tuple[dict[str, str], dict[str, str], list[str]]:
    raw = parse_dotenv(ENV_PATH)
    runtime = build_runtime_env(raw, root=ROOT)
    secrets = [raw[name] for name in ("OLLAMA_API_KEY",) if raw.get(name)]
    if require_models and raw.get("OLLAMA_NUM_PARALLEL", "").strip() != "2":
        raise GateError(
            "OLLAMA_NUM_PARALLEL must be 2 to match recipe n_concurrent: 2; "
            "set it with `launchctl setenv OLLAMA_NUM_PARALLEL 2` and restart Ollama"
        )
    return raw, runtime, secrets


def _runtime_digest(env: dict[str, str], secrets: list[str]) -> str:
    completed = record_command(
        "runtime-digest",
        [sys.executable, str(ROOT / "scripts" / "runtime_digest.py")],
        _subprocess_env(env),
        secrets=secrets,
    )
    if completed.returncode != 0:
        raise GateError("runtime digest computation failed")
    return completed.stdout.strip()


# --- subcommands -----------------------------------------------------------


def cmd_audit(_args: argparse.Namespace) -> int:
    """Run every model-free source and dataset check."""
    _raw, runtime, secrets = _load(require_models=False)
    unittest = record_command(
        "audit-unittest",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        _subprocess_env(runtime),
        secrets=secrets,
    )
    dataset = record_command(
        "audit-dataset",
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_tasks.py"),
            "--output",
            str(ROOT / "reports" / "preflight" / "task-audit.json"),
        ],
        _subprocess_env(runtime),
        secrets=secrets,
    )
    ok = unittest.returncode == 0 and dataset.returncode == 0
    print(f"audit: {'ok' if ok else 'failed'} (see reports/control/)")
    return 0 if ok else 1


def cmd_models(args: argparse.Namespace) -> int:
    """Verify or explicitly pull the two Ollama model tags."""
    raw, runtime, secrets = _load(require_models=False)
    tags = tuple(raw[name] for name in REQUIRED_MODELS)
    try:
        resolved = probe_models(runtime["OLLAMA_BASE_URL"], tags)
    except RuntimeError as exc:
        if not args.pull_missing:
            print(f"models: {exc}", file=sys.stderr)
            return 1
        for tag in tags:
            record_command(
                f"pull-{tag.replace(':', '-')}",
                ["ollama", "pull", tag],
                _subprocess_env(runtime),
                secrets=secrets,
            )
        resolved = probe_models(runtime["OLLAMA_BASE_URL"], tags)
    (CONTROL_DIR).mkdir(parents=True, exist_ok=True)
    (CONTROL_DIR / "models.json").write_text(
        json.dumps({"schema_version": 1, "models": resolved}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"models: verified {', '.join(tags)}")
    return 0


def cmd_probe(_args: argparse.Namespace) -> int:
    """Call the target and mutator Ollama probes once."""
    _raw, runtime, secrets = _load(require_models=False)
    completed = record_command(
        "probe",
        [sys.executable, str(ROOT / "scripts" / "api_smoke.py"), "--role", "all"],
        _subprocess_env(runtime),
        secrets=secrets,
    )
    print(f"probe: {'ok' if completed.returncode == 0 else 'failed'}")
    return completed.returncode


def _evolve_env(env: dict[str, str], secrets: list[str]) -> dict[str, str]:
    subprocess_env = _subprocess_env(env)
    subprocess_env["EVOLVE_RUNTIME_DIGEST"] = _runtime_digest(env, secrets)
    return subprocess_env


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a fresh workspace; refuse to reuse an existing one."""
    workspace = Path(args.workspace).expanduser()
    if workspace.exists():
        print(f"init: refusing to reuse existing workspace {workspace}", file=sys.stderr)
        return 1
    _raw, runtime, secrets = _load(require_models=False)
    completed = record_command(
        "init",
        [
            sys.executable,
            "-m",
            "evolve",
            "init",
            str(workspace),
            "--recipe-path",
            str(RECIPE_PATH),
            "--dataset",
            str(DATASET_DIR),
        ],
        _evolve_env(runtime, secrets),
        secrets=secrets,
    )
    print(f"init: {'ok' if completed.returncode == 0 else 'failed'} {workspace}")
    return completed.returncode


def cmd_preflight(args: argparse.Namespace) -> int:
    """Validate an initialized workspace without model use."""
    _raw, runtime, secrets = _load(require_models=True)
    completed = record_command(
        "preflight",
        [sys.executable, "-m", "evolve", "preflight", str(Path(args.workspace).expanduser())],
        _evolve_env(runtime, secrets),
        secrets=secrets,
    )
    print(f"preflight: {'ok' if completed.returncode == 0 else 'failed'}")
    return completed.returncode


def _run_generations(args: argparse.Namespace, name: str, max_generations: int) -> int:
    _raw, runtime, secrets = _load(require_models=True)
    completed = record_command(
        name,
        [
            sys.executable,
            "-m",
            "evolve",
            "run",
            str(Path(args.workspace).expanduser()),
            "--max-generations",
            str(max_generations),
        ],
        _evolve_env(runtime, secrets),
        secrets=secrets,
    )
    print(f"{name}: {'ok' if completed.returncode == 0 else 'failed'}")
    return completed.returncode


def cmd_canary(args: argparse.Namespace) -> int:
    """Run one target task and the local isolation probe."""
    return _run_generations(args, "canary", 0)


def cmd_baseline(args: argparse.Namespace) -> int:
    """Run generation zero and require Gate plus Sealed evidence."""
    return _run_generations(args, "baseline", 0)


def cmd_evolve(args: argparse.Namespace) -> int:
    """Run through generation three."""
    return _run_generations(args, "evolve", 3)


def cmd_report(args: argparse.Namespace) -> int:
    """Regenerate the final audit bundle without model calls."""
    _raw, runtime, secrets = _load(require_models=False)
    completed = record_command(
        "report",
        [sys.executable, "-m", "evolve", "report", str(Path(args.workspace).expanduser())],
        _subprocess_env(runtime),
        secrets=secrets,
    )
    print(f"report: {'ok' if completed.returncode == 0 else 'failed'}")
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("audit", help="run all model-free source and dataset checks").set_defaults(func=cmd_audit)

    models = sub.add_parser("models", help="verify or explicitly pull the two Ollama model tags")
    models.add_argument("--pull-missing", action="store_true", help="pull tags that are not installed")
    models.set_defaults(func=cmd_models)

    sub.add_parser("probe", help="call target and mutator Ollama probes once").set_defaults(func=cmd_probe)

    for name, func, help_text in (
        ("init", cmd_init, "initialize a fresh workspace with a unique experiment id"),
        ("preflight", cmd_preflight, "validate an initialized workspace without model use"),
        ("canary", cmd_canary, "run one target task and the local isolation probe"),
        ("baseline", cmd_baseline, "run generation zero and require Gate plus Sealed evidence"),
        ("evolve", cmd_evolve, "run through generation three"),
        ("report", cmd_report, "regenerate the final audit bundle without model calls"),
    ):
        stage = sub.add_parser(name, help=help_text)
        stage.add_argument("--workspace", required=True, help="workspace directory")
        stage.set_defaults(func=func)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (GateError, ValueError) as exc:
        print(f"{args.command}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
