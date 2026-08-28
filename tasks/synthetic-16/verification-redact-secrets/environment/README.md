Implement `redact(text)`.

Replace values following `api_key=`, `token=`, or `password=` with `[REDACTED]`. Keys are case-insensitive. A value ends at whitespace, `&`, or `;`. Preserve all other text and the original key spelling.
