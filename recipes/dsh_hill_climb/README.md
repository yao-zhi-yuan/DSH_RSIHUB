# DSH Qwen Hill Climb

This custom RSIHub recipe evaluates a pinned DSH headless runtime with local Ollama `qwen3:8b` and uses local Ollama `qwen3:14b` to edit only `target/prompt.md`. The evaluator, tasks, model route, adapter, runtime limits, and sealed split stay outside the mutable surface.
