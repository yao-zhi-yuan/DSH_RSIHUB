# Evolution audit report: qwen-first-v1

- Target model: `ollama/qwen3:8b`
- Mutator operator: `rsihub_qwen_prompt_mutate.py`
- Champion: gen 1 (score 0.5)

## Score curve

| Stage | Gate | Sealed |
| --- | --- | --- |
| baseline | 0.0 | 0.25 |
| gen 1 | 0.5 | 0.5 |
| gen 2 | 0.0 | - |
| gen 3 | 0.5 | - |

## Generation decisions

| Gen | Parent | Verdict | Champion | Reason |
| --- | --- | --- | --- | --- |
| 1 | 0 | keep | yes | score 0.5 >= parent 0.0 |
| 2 | 1 | discard | no | score 0.0 < parent 0.5 |
| 3 | 1 | keep | no | score 0.5 >= parent 0.5 |

## Improvement hypotheses

- gen 1: The agent's failure patterns stem from repeating test executions without analyzing outcomes. Adding explicit outcome checking and adaptive code adjustment steps will improve success rates by aligning with the passing example's verification流程. (expected: Reduce failures in tasks with verification steps by ensuring agents analyze test results before re-running commands, breaking the cycle of repeated identical tool actions without adaptation.)
- gen 2: Adding explicit syntax validation steps will address the failure pattern where repeated writes with incorrect line continuation characters caused syntax errors in the module implementation. (expected: The agent will adapt code formatting to fix syntax issues before re-running tests, preventing repeated verification failures from formatting errors.)
- gen 3: Adding explicit error analysis requirements will reduce redundant edits and improve handling of format/parse errors and unhashable type failures by addressing root causes rather than repeating unchanged code modifications. (expected: Fewer repeated edit actions, better handling of input validation errors (like ' 1.5 m' parsing), and resolution of unhashable type errors through targeted code adjustments based on test failure diagnostics.)

## Resources

- target tokens (total): 474785
- mutator tokens (total): 21263
- mutator requests: 3
- wall time (s): 6646.117

## Limitations

- Stage 1 prompt-only run: the mutator may edit only target/prompt.md.
- Scores compare only within a fixed task-set cohort (stable task_set_hash).
- Gate and Sealed cohorts are disjoint task sets and are not directly comparable.
