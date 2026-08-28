"""Build the minimal environment used by the model-operated DSH process."""

from __future__ import annotations

import shlex
import shutil
from collections.abc import Mapping, Sequence


_HOST_ENV = ("HOME", "PATH", "TMPDIR", "LANG")
_OLLAMA_ENV = ("OLLAMA_BASE_URL", "OLLAMA_API_KEY", "OLLAMA_TARGET_MODEL")


def build_dsh_env(source: Mapping[str, str], *, dsh_home: str) -> dict[str, str]:
    """Return a fail-closed DSH environment with a working Node executable."""
    env = {name: source[name] for name in _HOST_ENV if source.get(name)}
    for name in _OLLAMA_ENV:
        value = source.get(name, "").strip()
        if not value:
            raise RuntimeError(f"missing required DSH evaluator environment: {name}")
        env[name] = value
    path = env.get("PATH", "")
    if shutil.which("node", path=path) is None:
        raise RuntimeError("sanitized DSH PATH cannot resolve node")
    env.update(
        {
            "DSH_HOME": dsh_home,
            "DSH_PERMISSION_MODE": "workspace-write",
            "DSH_TELEMETRY_DISABLED": "1",
        }
    )
    return env


def render_clean_command(argv: Sequence[str], env: Mapping[str, str]) -> str:
    """Render an `env -i` command with shell-safe arguments."""
    assignments = [shlex.quote(f"{name}={value}") for name, value in sorted(env.items())]
    arguments = [shlex.quote(value) for value in argv]
    return " ".join(["env", "-i", *assignments, *arguments])
