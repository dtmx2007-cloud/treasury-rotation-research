# Preregistered Validation Procedure

Author: Declan Miller, with Claude drafting under Declan's sign-off
Date: 2026-07-31
Contract version: `0.2.3` (locked 2026-07-30)
Status: recorded and pushed BEFORE `validate.py` existed and BEFORE any
strategy or benchmark performance number was computed or viewed on
2016-01-01 through 2020-12-31. Companion to
[`VALIDATION_PRECOMMITMENT.md`](VALIDATION_PRECOMMITMENT.md).

This document preregisters the complete procedure for the contract's one
permitted robustness review of the validation period. Nothing here may
change after results are seen.

## Question

Does the development-period story hold on unseen years? Specifically: on
2016-2020, do the two strategies still trail the two benchmarks on
CAGR, Sharpe, and Calmar after costs, and do costs still consume the
signal's edge? The comparison against the development-period table IS the
robustness review. No new hypothesis is introduced and none of the locked
2021-2025 hypotheses are evaluated.

## Instrument (identical to the development first look)

1. Portfolios: Phase 1 raw momentum, Phase 2 risk-adjusted momentum,
   buy-and-hold IEF, and equal-weight SHY/IEF/TLT rebalanced quarterly,
   exactly as frozen in the contract.
2. Metrics: the six frozen metrics under the v0.2.3 mechanical
   clarifications. No additions, no removals.
3. Costs: primary 10 bps per dollar traded, plus the contract-frozen
   {5, 20} bps labeled sensitivities. No other level may run. The 42-day
   and 126-day lookbacks do NOT run today; per the Sensitivity policy
   they are permitted only after both primary locked-test results are
   recorded.
4. Risk-free: the ^IRX series under clauses 3-5 of the metric
   clarifications, aligned to the measured-return window.

## Measured-return window

1. The measured-return window is every trading day from the first
   trading day on or after `VALIDATION_START` (2016-01-01) through the
   last trading day on or before `VALIDATION_END` (2020-12-31).
2. Signals may read pre-2016 prices as trailing lookback input only. On
   every 2016 decision date, all such prices already existed; no
   performance is measured on any pre-2016 day.
3. Initial allocation: the position held entering the window is the
   selection made at the last qualifying weekly decision date of 2015
   under the standard frozen rules (all inputs predating 2016). It is
   installed without cost and contributes zero turnover, mirroring the
   contract's uncharged-initial-purchase convention. Measured strategy
   returns begin on the first trading day of the window.
4. Benchmarks: buy-and-hold IEF and the equal-weight portfolio are
   installed without cost at the window start and evaluated over the
   identical measured-return window, with the equal-weight portfolio's
   quarterly rebalances occurring inside the window under the existing
   conventions. The risk-free series is aligned to the same window.

## Fences and checks

1. `VALIDATION_START` and `VALIDATION_END` are read from the frozen
   config and hard-coded into the runner. No flag, parameter, or
   argument can move either edge.
2. End fence: no price or quote observation after `VALIDATION_END` may
   reach a signal, a portfolio, or a metric. The runner slices first and
   verifies the slice; a post-2020 date past the fence raises an error.
   This is the mechanical enforcement of precommitment promise 5.
3. Start fence: no measured return before `VALIDATION_START` may enter
   any metric. Pre-2016 data is lookback fuel only.
4. Window identity: all four portfolios must share the exact same
   measured-return index, enforced by an index-equality check. A
   mismatch raises an error instead of printing a table.
5. The runner reads local caches only and never downloads data.

## Outputs (these ARE the look)

The runner prints exactly three labeled tables — primary 10 bps first,
then the 5 and 20 bps labeled sensitivities — each showing the six
frozen metrics for the four portfolios over the identical window, in the
same format as the development report, plus the window metadata lines.
Anything beyond these preregistered outputs (plots, holdings
inspection, date slicing, additional statistics) is iteration and is
prohibited by precommitment promise 2.

## Execution

`tests` run first and must pass. `validate.py` and its tests are pushed
publicly BEFORE the runner is executed, so the machinery's public
timestamp precedes the results. The runner is then executed once. The
results are taught against the development-period table one metric at a
time and reported regardless of outcome. The locked test period is not
opened today under any circumstances.
