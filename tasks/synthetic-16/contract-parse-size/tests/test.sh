#!/bin/sh
set -eu
mkdir -p "$HARBOR_LOGS_DIR/verifier"
if python3 "$HARBOR_TESTS_DIR/verify.py" "$HARBOR_WORKDIR"; then
  printf '1
' > "$HARBOR_LOGS_DIR/verifier/reward.txt"
else
  printf '0
' > "$HARBOR_LOGS_DIR/verifier/reward.txt"
fi
