# Locked-Test Freeze Declaration

Author: Declan Miller
Date: 2026-08-03
Contract version at time of writing: `0.2.3` (locked 2026-07-30)
Status: recorded and pushed BEFORE the locked 2021-01-01 through
2025-12-31 test period is opened and before any locked-test performance
number has been computed or viewed on any portfolio.

This document declares the complete instrument frozen between the commit
that introduces this declaration and the recorded locked-test results.
In my own words:

1. The two strategies stay exactly as `research_contract.md` v0.2.3
   specifies — Phase 1 raw momentum (weekly rebalance, trailing
   63-trading-day return ending one day earlier, highest-return ETF among
   SHY/IEF/TLT, SHY if all trailing returns are negative, one ETF
   long-only and unlevered) and Phase 2 risk-adjusted momentum as
   written — and I will not alter any signal, timing, or tie-break rule
   for any reason.

2. The cost model stays: 10 basis points per dollar of one-way turnover
   as the primary assumption, with 5 and 20 basis points reported only as
   labeled sensitivities, and the uncharged initial allocation convention
   stands.

3. The benchmarks stay exactly two — buy-and-hold IEF, and equal-weight
   SHY/IEF/TLT rebalanced quarterly — under the same return conventions
   and cost model as the strategies, and I will not add, drop, or
   substitute a benchmark after seeing any locked-test number.

4. The metrics stay exactly six — CAGR, annualized volatility, Sharpe
   ratio against the contemporaneous three-month Treasury rate, maximum
   drawdown, Calmar ratio, and annual turnover — computed under the
   v0.2.3 mechanical clarifications, with nothing added, dropped, or
   redefined after the look.

5. The code and test suite stay as they exist at the commit that
   introduces this declaration, with one narrow exception: the
   locked-test session may add — never edit — the locked-test procedure
   document, the locked-test runner, and the runner's tests, each pushed
   publicly before execution. Auditably: between the freeze commit and
   the run commit, the diff over `src/`, `tests/`, `pyproject.toml`,
   `research_contract.md`, and `artifacts/data_manifest.json` shows only
   those added files, and every pre-existing file in that set remains
   byte-identical. Report and documentation prose outside that set may
   continue to change; no prose edit can alter execution.

6. Opening 2021-01-01 through 2025-12-31 is a one-way event: I will log
   the unlock deliberately before running, run once, and no result —
   including a bad one, and including a flattering one — authorizes
   changing any commitment above and rerunning.

7. The input data stays exactly as pinned in
   `artifacts/data_manifest.json` — the SHY/IEF/TLT adjusted-close panel
   (content hash `33447af3…`, 5,787 rows, 2003-01-02 through 2025-12-31)
   and the `^IRX` risk-free series (content hash `137d2578…`, same
   coverage) — and the locked-test run reads only the local caches
   matching those hashes: no re-download, no refresh, no substitute
   source, and a hash mismatch at run time halts the session as a
   reportable blocker, never a permission to re-fetch.

The public timestamp on this freeze precedes the public timestamp on the
locked-test result.
