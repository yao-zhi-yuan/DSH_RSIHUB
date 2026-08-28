`build_result.py` must read `input.txt` and create `result.json` with exactly these keys:

- `non_empty_lines`: count after trimming each line and excluding blanks.
- `unique_words`: case-insensitive count of distinct whitespace-separated words from non-empty lines.
- `sha256`: lowercase SHA-256 of the original `input.txt` bytes.

JSON must be valid UTF-8 with a trailing newline. Repair the script and run it; the required deliverable is the generated `result.json` file.
