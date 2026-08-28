Implement `summarize_jsonl(text)`.

Parse non-empty lines as JSON objects. Ignore malformed JSON and non-object JSON values. Return `{'valid': N, 'invalid': M, 'total_value': S}` where `total_value` sums numeric `value` fields but excludes booleans.
