# Locked-Test Unlock Log

Author: Declan Miller
Logged: 2026-10-13, about 9:00 pm EDT
Contract version: `0.2.3` (locked 2026-07-30)

I am opening 2021-01-01 through 2025-12-31 once. This file is committed
and pushed before the runner executes, so its public timestamp comes before
the result.

What was true when I unlocked it:

1. The freeze commit is `98a9821` (2026-08-03). Every pre-existing file in
   `src/`, `tests/`, `pyproject.toml`, `research_contract.md`, and
   `artifacts/data_manifest.json` is byte-identical to that commit. The only
   additions are the runner and its tests.
2. The procedure was pushed before the runner existed: `88f4b52`.
3. The runner and 19 tests were pushed before execution: `349f4e7`. The full
   suite (109 tests) passed locally and in CI.
4. Both local caches match the hashes pinned in the manifest:
   - SHY/IEF/TLT panel: `33447af38aab27967b0ee71223c95cb0ffed6cedac00745246ea298c9ef71334`
     (5,787 rows, 2003-01-02 to 2025-12-31)
   - ^IRX: `137d257897d54b966588040d0ae60c420850e54b1f2ec706f5ef5a56914175df`
     (same coverage)
5. No number has been computed or viewed on any part of 2021-2025.

Authorization: I approved the procedure and the unlock on 2026-10-13 at
about 8:50 pm EDT, conditional on the runner being public and CI passing.

The run happens once. Whatever it shows, good or bad, gets reported, and
nothing in it lets me change a rule and run it again.
