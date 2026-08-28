Implement `retry_delays(attempts, base=1.0, cap=30.0)`.

Return one delay per retry attempt: `base * 2**index`, capped individually at `cap`. `attempts=0` returns an empty list. Reject negative attempts, non-positive base, or non-positive cap with `ValueError`.
