# Reports

This directory holds the experiment's auditable evidence. It has three kinds of
contents:

- `preflight/task-audit.json` — the frozen dataset audit (tracked). Produced by
  `scripts/audit_tasks.py`; certifies all 16 tasks are solvable (initial reward
  `0`, oracle reward `1`).
- `control/` — per-run control-plane transcripts (gitignored). Produced by
  `scripts/experimentctl.py`; each file records one subprocess with sanitized
  stdout/stderr, timing, and exit code.
- `<experiment-id>/` — the final audit bundle (produced on demand). Written by
  `scripts/build_report.py`.

## Building the report

```bash
python3 scripts/build_report.py --workspace workspaces/qwen-first-v1
```

`build_report.py` is **read-only** and **model-free**: it never mutates the
workspace and never calls a model. It fails closed when the evidence is
incomplete — incomplete expected trials, uncertified receipts, mismatched task
sets, missing generations, absent final Sealed evidence, malformed usage, or a
referenced file that does not exist.

## Bundle layout

```text
reports/<experiment-id>/
├── summary.json                # machine-readable audit summary (schema_version 1)
├── report.md                   # human-readable report; credentials are [REDACTED]
├── manifest.sha256             # sha256 of every written artifact
└── candidate-diffs/
    ├── gen-1.diff              # per-generation target/prompt.md change
    ├── gen-2.diff
    └── gen-3.diff
```

`summary.json` carries the experiment identity, the baseline and per-generation
Gate/Sealed scores, the champion, resource consumption (target and mutator
tokens, Ollama model digests, host facts), the audit hashes and redaction count,
and the run's stated limitations.
