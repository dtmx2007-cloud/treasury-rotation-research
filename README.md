# Treasury Rotation Research

This repository tests two deliberately transparent questions:

> Can a weekly momentum rule across short-, intermediate-, and long-duration
> Treasury ETFs improve drawdown-adjusted returns relative to transparent
> benchmarks, and does adjusting momentum for recent volatility improve the
> simple rule?

The project is an educational research artifact. It does not provide investment
advice, connect to a live brokerage account, or contain a live-trading code path.

## Current milestone

Milestone 1 established data integrity. Milestone 2 added a benchmark engine.
Milestone 3 added the Phase 1 raw-momentum signal. Milestone 4 added the
Phase 2 risk-adjusted signal. Milestone 5 froze the six performance metrics
as contract v0.2.3 and implemented them. The code can:

- fetch adjusted daily prices for SHY, IEF, and TLT;
- validate coverage, schema, missing observations, and implausible price moves;
- cache the data locally without adding it to Git; and
- write a non-price data manifest containing provenance and content hashes;
- calculate daily returns;
- simulate buy-and-hold IEF and quarterly equal weighting;
- account for drifting weights, one-way turnover, costs, and compounding; and
- generate weekly Phase 1 raw-momentum targets and Phase 2 risk-adjusted
  targets and wire both through the portfolio engine under the contract
  v0.2.1 and v0.2.2 mechanical clarifications; and
- compute the six frozen metrics (CAGR, annualized volatility, Sharpe,
  maximum drawdown, Calmar, and annual turnover) on net-of-cost results
  under the contract v0.2.3 mechanical clarifications.

The engine and every metric function reject every date in the 2021-2025
locked test period. No strategy performance has been calculated or viewed on
historical data; signals and metrics are verified only against synthetic
examples with known answers. The ^IRX risk-free series is named in the
contract but its download pipeline is not implemented yet, so Sharpe cannot
be computed on real data.

Ongoing-session working notes live in a local `HANDOFF.md` that is not part
of the published artifact.

## Data flow and terminology

SHY, IEF, and TLT are tradable proxies for short-, intermediate-, and
long-duration U.S. Treasury exposure. The pipeline retrieves **adjusted close**
prices, which account for distributions and splits, and retains only dates with
valid observations for all three ETFs. It never forward-fills a missing price.

Prices become close-to-close **decimal returns**: `0.01` means 1%. A portfolio
**weight** is the fraction invested in an ETF, and all weights sum to 1.0.
**Held weights** earn the current day's return; **ending weights** include market
drift and any rebalance performed at that close. A **target** is the allocation
the portfolio should hold after such a rebalance.

Trading costs are quoted in **basis points**: 10 basis points equals 0.10%.
**One-way turnover** measures the fraction of the portfolio reallocated without
double-counting the matching sale and purchase.

The local **cache** contains prices and is excluded from Git. The public-safe
**manifest** contains provenance and validation statistics but no price rows.
Its SHA-256 fingerprint changes if the validated dataset changes.

The complete preregistered design is in
[`research_contract.md`](research_contract.md). The project is organized into:

1. raw momentum;
2. risk-adjusted momentum; and
3. optional paper-only execution.

[`roadmap.md`](roadmap.md) explains how later work could add macroeconomic
features, interpretable statistical learning, portfolio construction, and
fixed-income relative value. Those extensions are not active August scope.

## Setup

Python 3.12 is the supported runtime.

```powershell
py -3.12 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -e '.[dev]'
```

## Verify

Run unit tests:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest
```

Fetch and validate the historical dataset:

```powershell
& '.\.venv\Scripts\python.exe' -m treasury_rotation.data
```

The benchmark engine and both strategy signals are library modules rather
than reporting commands. Their behavior is verified with synthetic examples
in `tests/test_portfolio.py`, `tests/test_signals.py`,
`tests/test_signals_phase2.py`, and `tests/test_metrics.py`.

The command writes:

- `data/cache/adjusted_close.parquet`, ignored by Git; and
- `artifacts/data_manifest.json`, safe to review and commit because it contains
  metadata and hashes, not market prices.

## Data boundary

Historical prices are retrieved through `yfinance` for personal educational
research. Yahoo data is not committed or redistributed. Anyone reproducing the
analysis must retrieve data under the provider's then-current terms.

Alpaca is reserved for an optional paper-only execution milestone after the
offline research artifact is complete. No live account, credentials, endpoint,
or order-routing logic belongs in this repository.
