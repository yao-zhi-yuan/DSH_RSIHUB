Implement `next_action(remaining_seconds, tests_passed, has_changes)`.

- No changes: return `work` when more than 60 seconds remain, otherwise `report`.
- Changes with passing tests: return `submit`.
- Changes with failing/unrun tests: return `verify` above 90 seconds, `salvage` from 31 through 90 seconds, and `submit` at 30 seconds or below.
- Reject negative remaining time.
