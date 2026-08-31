#!/bin/sh
set -eu
# Harbor uploads tests/ to /tests, runs the agent workspace at /app, and reads
# the reward from /logs/verifier/reward.txt. These fixed paths are the real
# Harbor contract; the audit harness overrides them via HARBOR_* for local runs.
WORKDIR="${HARBOR_WORKDIR:-/app}"
TESTS_DIR="${HARBOR_TESTS_DIR:-/tests}"
LOGS_DIR="${HARBOR_LOGS_DIR:-/logs}"
mkdir -p "$LOGS_DIR/verifier"
if python3 "$TESTS_DIR/verify.py" "$WORKDIR"; then
  printf '1
' > "$LOGS_DIR/verifier/reward.txt"
else
  printf '0
' > "$LOGS_DIR/verifier/reward.txt"
fi
