# DSH RSIHub Qwen experiment

This repository defines a prompt-only RSIHub Hill Climb experiment using local
Ollama inference.

## Models

- DSH target: `qwen3:8b`
- Prompt mutator: `qwen3:14b`
- API: `http://127.0.0.1:11434/v1`

The model tags and Ollama-reported digests are frozen when a formal workspace
is initialized. The experiment does not use a remote model provider.

## Local checks

```bash
python3 -m unittest discover -s tests -v
python3 scripts/runtime_digest.py
uv run --project vendor/RSIHub --frozen evolve recipe check recipes/dsh_hill_climb/evolve.yaml
```

## Current checkpoint

The dataset fixes, Ollama routing, Docker evaluator image, and risk controls are
prepared. The unified `experimentctl.py`, three-run tool canary, trajectory
accounting, and report builder remain implementation-plan tasks. Do not run the
formal recipe directly before those gates exist.

```bash
ollama list
ollama show qwen3:8b
ollama show qwen3:14b
docker build -t dsh-ollama-eval:node24-dsh011rc2 containers/evaluator
```

The remaining implementation and execution sequence is in
`docs/superpowers/plans/2026-08-28-rsihub-dsh-qwen-evolution.md`.

`qwen3:8b` must pass three consecutive multi-turn tool-call canaries before the
baseline starts. There is no automatic fallback to another model because that
would change the experiment identity.

The recipe uses two concurrent target trials. Start the Ollama server with
`OLLAMA_NUM_PARALLEL=2` and restart it after changing that setting. The
sanitized DSH environment retains a `PATH` that resolves Node 24.

Only `target/prompt.md` may evolve. Generated workspaces and raw run artifacts
are intentionally excluded from Git; final reports contain hashes that bind
them to the published results.

## First completed run

- Report: `reports/qwen-first-v1/report.md`
- Machine-readable summary: `reports/qwen-first-v1/summary.json`
- Artifact manifest: `reports/qwen-first-v1/manifest.sha256`
