Implement `allowed_changes(paths)`.

Return `True` only when every normalized path is under `src/` or `tests/`. Reject absolute paths, traversal, `.git`, secrets (`.env` or any `.pem`), and generated `__pycache__` entries. An empty list is allowed.
