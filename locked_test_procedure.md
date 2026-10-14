# Preregistered Locked-Test Procedure

Author: Declan Miller, with Claude drafting under Declan's sign-off
Date: 2026-10-13
Contract version: `0.2.3` (locked 2026-07-30)
Status: recorded and pushed BEFORE the locked-test runner exists and BEFORE
any strategy or benchmark performance number has been computed or viewed on
2021-01-01 through 2025-12-31. Governed by
[`FREEZE_DECLARATION.md`](FREEZE_DECLARATION.md) (freeze commit `98a9821`).

This document preregisters the complete procedure for the contract's final
evaluation: the one opening of the locked test period. Nothing here may
change after results are seen.

## Question

The four hypotheses frozen in `research_contract.md`, evaluated once, on
2021-2025, after primary transaction costs:

1. **Phase 1 primary:** raw momentum's locked-test Calmar ratio exceeds both
   benchmarks' Calmar ratios.
2. **Phase 1 secondary:** raw momentum's locked-test maximum drawdown is
   smaller in magnitude than buy-and-hold IEF's.
3. **Phase 2 incremental:** risk-adjusted momentum's locked-test Calmar ratio
   exceeds raw momentum's.
4. **Phase 2 secondary:** risk-adjusted momentum's locked-test maximum
   drawdown is smaller in magnitude than raw momentum's.

All four are evaluated on the primary 10 bps table, the contract's primary
cost assumption. The contract's wording of hypothesis 4 omits "after primary
transaction costs"; this procedure reads it on the same primary table as the
other three, fixed here before any number exists. "Exceeds" and "smaller in
magnitude" are strict inequalities: a tie is NOT SUPPORTED.

## Instrument (identical to the development and validation looks)

1. Portfolios: Phase 1 raw momentum, Phase 2 risk-adjusted momentum,
   buy-and-hold IEF, and equal-weight SHY/IEF/TLT rebalanced quarterly,
   exactly as frozen in the contract.
2. Metrics: the six frozen metrics under the v0.2.3 mechanical
   clarifications. No additions, no removals.
3. Costs: primary 10 bps per dollar traded, plus the contract-frozen
   {5, 20} bps labeled sensitivities. No other level may run.
4. Risk-free: the ^IRX series under clauses 3-5 of the metric
   clarifications, aligned to the measured-return window.
5. Lookbacks: 63 trading days only. The contract permits 42- and 126-day
   lookbacks as labeled sensitivities after both primary results are
   recorded; this session does NOT run them. Any future sensitivity run
   requires its own preregistered procedure and cannot change the
   conclusion.

## Measured-return window

1. The measured-return window is every trading day from the first trading
   day on or after `TEST_START` (2021-01-01) through the last trading day on
   or before `TEST_END` (2025-12-31).
2. Signals may read pre-2021 prices as trailing lookback input only. On
   every 2021 decision date, all such prices already existed; no
   performance is measured on any pre-2021 day.
3. Initial allocation: the position held entering the window is the
   selection made at the last qualifying weekly decision date of 2020 under
   the standard frozen rules (all inputs predating 2021). It is installed
   without cost and contributes zero turnover, mirroring the contract's
   uncharged-initial-purchase convention and the validation procedure.
   Measured strategy returns begin on the first trading day of the window.
4. Benchmarks: buy-and-hold IEF and the equal-weight portfolio are installed
   without cost at the window start and evaluated over the identical
   measured-return window, with equal-weight quarterly rebalances occurring
   inside the window under the existing conventions. The risk-free series
   is aligned to the same window.

## Fences and checks

1. `TEST_START` and `TEST_END` are read from the frozen config and
   hard-coded into the runner. No flag, parameter, or argument can move
   either edge.
2. End fence: the runner slices prices on or before `TEST_END` first and
   verifies the slice. The cache ends 2025-12-31, so this fence is a
   belt-and-braces check, not a cut.
3. Start fence: no measured return before `TEST_START` may enter any
   metric. Pre-2021 data is lookback fuel only.
4. Window identity: all four portfolios must share the exact same
   measured-return index, enforced by an index-equality check. A mismatch
   raises an error instead of printing a table.
5. Pinned data (freeze item 7): the runner reads the local caches only,
   never downloads, recomputes both content hashes through the existing
   validation functions, and halts on any mismatch with the manifest
   (`33447af3…` panel, `137d2578…` ^IRX). A mismatch is a reportable
   blocker, never a permission to re-fetch.
6. Code freeze (freeze item 5): before execution, the session verifies that
   `src/`, `tests/`, `pyproject.toml`, `research_contract.md`, and
   `artifacts/data_manifest.json` differ from `98a9821` only by the added
   runner and its tests.

## How the engine's locked-period guard is lifted

The frozen portfolio engine and metrics module reject any date on or after
`TEST_START` through a module-level constant. Freeze item 5 forbids editing
either file, so the runner lifts the guard without editing them: inside a
context manager it rebinds that constant in `treasury_rotation.portfolio`
and `treasury_rotation.metrics` to the data end (`2026-01-01`), runs the
frozen functions unchanged, and restores the original constant on exit,
including on error. The guard therefore stays in force for every other
caller, and every number is produced by the exact frozen code paths.

## Logged unlock and run-once guard

1. The runner refuses to execute on real data unless
   `LOCKED_TEST_UNLOCK.md` exists in the repository root. That file records
   the deliberate unlock: date and time, the freeze and runner commits, the
   verified data hashes, and Declan's authorization. It is committed and
   pushed BEFORE the run.
2. The runner writes its complete output to
   `artifacts/locked_test_output.txt` and refuses to execute if that file
   already exists. The run happens once.

## Outputs (these ARE the look)

The runner prints, and writes to `artifacts/locked_test_output.txt`, exactly:

1. Three labeled tables, primary 10 bps first, then the 5 and 20 bps
   labeled sensitivities, each showing the six frozen metrics for the four
   portfolios over the identical window, in the format of the development
   and validation reports, plus the window metadata lines.
2. The four hypotheses above, each evaluated mechanically on the primary
   table: the comparison, the numbers compared, and SUPPORTED or NOT
   SUPPORTED.

Anything beyond these outputs (plots, holdings inspection, date slicing,
sub-period statistics, additional metrics) is iteration and is prohibited.

## Execution order

1. This procedure is pushed publicly before the runner exists.
2. The runner and its tests are written, the full suite passes, and they
   are pushed publicly before execution.
3. `LOCKED_TEST_UNLOCK.md` is committed and pushed.
4. The runner is executed once.
5. The output file and the report update are committed and pushed together.
   Results are reported regardless of outcome: a bad result and a
   flattering one are reported the same way, and neither authorizes
   changing any commitment and rerunning.
