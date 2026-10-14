# Treasury Rotation Research

[![tests](https://github.com/dtmx2007-cloud/treasury-rotation-research/actions/workflows/tests.yml/badge.svg)](https://github.com/dtmx2007-cloud/treasury-rotation-research/actions/workflows/tests.yml)

A preregistered test of one question: does a weekly momentum rule across
short, intermediate and long Treasury ETFs (SHY, IEF, TLT) beat just
holding IEF after trading costs? And does adjusting momentum for
volatility help?

Short answer: raw momentum lost to IEF in all three periods I tested. The
volatility-adjusted version lost in two. In the third, the period with the
2022 rate hikes, it came out ahead on CAGR, drawdown and Calmar (not
Sharpe), and still trailed T-bills. The full write-up is in
[`REPORT.md`](REPORT.md).

## What I found

Net CAGR at the primary 10 bps cost, by period:

| Period | Phase 1 (raw momentum) | Phase 2 (risk-adjusted) | Hold IEF | Equal weight |
|---|---|---|---|---|
| Development, 2003-2015 | 4.34% | 1.66% | 5.21% | 4.83% |
| Validation, 2016-2020 (one look) | 3.40% | -1.94% | 4.38% | 4.77% |
| Locked test, 2021-2025 (one look) | -5.77% | -0.35% | -1.92% | -2.90% |

- Raw momentum lost to buy-and-hold IEF in all three periods.
- From 2003 to 2020 it about tied IEF on CAGR before costs, and the trading
  toll was more than the whole deficit (-0.87 points a year in development,
  -0.98 in validation). On Sharpe and Calmar it trailed even before costs,
  because it was much more volatile.
- From 2021 to 2025 the signal itself failed. It trailed IEF by about 3
  points a year before costs and 3.85 after.
- The volatility-adjusted version was last of the four on Calmar in the
  first two periods and first in the locked test, when every portfolio
  trailed T-bills. One good period out of three isn't an edge.
- Locked-test hypotheses: both Phase 1 hypotheses failed and both Phase 2
  hypotheses held, on point estimates (REPORT section 6).

## How I kept it honest

- I wrote the rules, cost model, metrics and periods into
  [`research_contract.md`](research_contract.md) and locked it before
  computing a single performance number.
- I pinned the data by content hash in
  [`artifacts/data_manifest.json`](artifacts/data_manifest.json).
- Before each look I pushed what I was committing to (a precommitment, a
  procedure, or both), then the runner, and only then ran it. The commit
  history and GitHub's own CI run times show the order (REPORT section 3).
- Validation and the locked test were each opened once. Neither runner
  gets rerun. The locked-test runner won't start without the logged unlock
  ([`LOCKED_TEST_UNLOCK.md`](LOCKED_TEST_UNLOCK.md)) and won't overwrite
  its own output, but the real guarantee is the public record: the unlock
  log was pushed before the run, and the output was committed with the
  report right after.
- Bad results got reported the same way good ones would have.

## Where things are

| File | What it is |
|---|---|
| [`REPORT.md`](REPORT.md) | The write-up: design, all three periods, the toll, limitations |
| [`research_contract.md`](research_contract.md) | The frozen rules (v0.2.3) |
| [`PRECOMMITMENT.md`](PRECOMMITMENT.md), [`VALIDATION_PRECOMMITMENT.md`](VALIDATION_PRECOMMITMENT.md), [`FREEZE_DECLARATION.md`](FREEZE_DECLARATION.md) | What I committed to before each look, in my words |
| [`validation_procedure.md`](validation_procedure.md), [`locked_test_procedure.md`](locked_test_procedure.md) | The preregistered procedures for the two one-shot looks |
| [`LOCKED_TEST_UNLOCK.md`](LOCKED_TEST_UNLOCK.md) | The logged unlock, pushed before the locked-test run |
| [`artifacts/locked_test_output.txt`](artifacts/locked_test_output.txt) | Raw output of the single locked-test run |
| `src/treasury_rotation/` | Data checks, signals, portfolio engine, metrics, and one runner per period |
| `tests/` | 109 tests on synthetic data, run in CI on every push |
| [`roadmap.md`](roadmap.md) | Ideas I parked. None of them are active. |

## Terms

SHY, IEF and TLT stand in for short, intermediate and long Treasury
duration. The pipeline uses **adjusted closes**, which account for
distributions and splits, and keeps only dates where all three ETFs have a
valid price. It never forward-fills a missing price.

Prices become daily **decimal returns** (`0.01` means 1%). A **weight** is
the fraction of the portfolio in one ETF, and weights sum to 1. Costs are
in **basis points** (10 bps is 0.10%) and are charged on **one-way
turnover**, the fraction of the portfolio moved, counting a sale and its
matching purchase once. So a full switch from one ETF to another is one
unit of turnover and costs 10 bps, about 5 bps on each side.

## Reproduce it

Python 3.12, Windows PowerShell shown.

```powershell
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -e '.[dev]'
```

Run the tests (synthetic data, no download):

```powershell
& '.\.venv\Scripts\python.exe' -m pytest
```

Pull and validate the data, then build the risk-free series:

```powershell
& '.\.venv\Scripts\python.exe' -m treasury_rotation.data
& '.\.venv\Scripts\python.exe' -m treasury_rotation.riskfree
```

This writes `data/cache/` (ignored by Git) and rewrites
`artifacts/data_manifest.json` with the content hashes of what you pulled.
Run `git diff artifacts/data_manifest.json` to compare against mine. If
Yahoo has revised its history since July 2026, the hashes won't match and
the numbers may move slightly.

Rerun the development period (the only runner meant to be rerun):

```powershell
& '.\.venv\Scripts\python.exe' -m treasury_rotation.develop
```

The validation and locked-test runners were each run once. The locked-test
printout is saved in `artifacts/locked_test_output.txt`. The validation
printout wasn't saved as a file; its tables are in REPORT section 5.

## Data and safety

Historical prices come from `yfinance` for personal educational research.
Yahoo data is not committed or redistributed, so anyone reproducing this
has to pull it under the provider's current terms.

This is research, not advice. There is no brokerage connection, no
credentials and no live-trading code path. The optional paper-trading
phase in the contract was cut.

## How this was built

I used AI assistants (Claude and Codex) for much of the code and for
drafting the write-up. The research rules, the precommitments, and every
decision about what got run and what got reported were mine.
