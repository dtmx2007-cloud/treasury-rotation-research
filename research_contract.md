# Research Contract

Contract version: `0.2.3`  
Locked: `2026-07-30`  
Status: locked before strategy results

Version history:

- `0.2.0` (2026-07-29): initial lock.
- `0.2.1` (2026-07-29): added the mechanical clarifications section. Recorded
  before any strategy result was calculated or viewed. No signal, timing,
  cost, benchmark, or metric rule changed.
- `0.2.2` (2026-07-29): added the Phase 2 mechanical clarifications section.
  Recorded before any strategy result was calculated or viewed. No signal,
  timing, cost, benchmark, or metric rule changed.
- `0.2.3` (2026-07-30): added the metric mechanical clarifications section and
  named the risk-free data series. Recorded before any strategy result was
  calculated or viewed. No signal, timing, cost, or benchmark rule changed;
  the six frozen metrics were made mechanically precise without altering any
  frozen choice.

## Question

Can a simple duration-momentum rule improve drawdown-adjusted returns relative
to transparent benchmarks, and does one risk adjustment improve the simple
rule?

This is a comparison of two preregistered, transparent rules. It is not a search
for whichever rule looks best after viewing the results.

## Assets and data

- Tradable proxies: SHY, IEF, and TLT.
- Field: daily adjusted close, including distribution adjustments supplied by
  the data provider.
- Research range: `2003-01-01` through `2025-12-31`.
- Primary historical source: `yfinance`, used for personal educational research.
- Raw and cached prices remain local and are excluded from Git.
- Retrieval parameters, package versions, coverage, and content hashes are
  recorded in `artifacts/data_manifest.json`.

## Frozen periods

| Period | Dates | Permitted use |
|---|---|---|
| Development | 2003-01-01 through 2015-12-31 | Implementation and debugging |
| Validation | 2016-01-01 through 2020-12-31 | One robustness review |
| Locked test | 2021-01-01 through 2025-12-31 | Final evaluation only |

Downloading and validating the test-period schema is allowed. Calculating or
viewing strategy or benchmark performance on the test period is prohibited until
the signal, timing, cost model, benchmarks, metrics, and automated tests are
frozen. Opening the test period is a one-way event and must be logged.

## Phase 1: raw momentum

1. Rebalance on the final trading day of each calendar week.
2. At the rebalance close, calculate each ETF's trailing 63-trading-day total
   return using data ending one trading day earlier.
3. Select the ETF with the highest trailing return.
4. If every trailing return is negative, select SHY.
5. Hold exactly one ETF, long-only and unlevered, until the next rebalance.
6. Apply the new position only to returns occurring after the rebalance close.

There is no parameter optimization. The 63-day lookback is the primary
specification.

## Mechanical clarifications (v0.2.1)

These clarifications make the frozen rules deterministic. They were resolved
and recorded before any strategy result existed, and they are not parameters
to optimize. Each applies to Phase 1 and, where relevant, Phase 2.

1. Trailing-return arithmetic. For a decision date at position `p` in the
   trading calendar, the 63-trading-day total return uses the price at
   position `p - 1` divided by the price at position `p - 64`, minus one.
   The window spans exactly 63 trading days and ends one trading day before
   the decision close, which therefore cannot influence its own selection.
2. Ties. If two or more ETFs share the exactly highest score under the active
   ranking rule, select the tied ETF earliest in the order SHY, IEF, TLT.
   When the signal cannot distinguish candidates, the shortest-duration
   (lowest interest-rate-risk) candidate wins. The rule is stateless: it
   never depends on current holdings.
3. Warm-up and initial allocation. The first decision date is the earliest
   final-trading-day-of-week observation with position `p >= 64`. Its
   selection is the strategy's initial allocation, installed without cost
   under the existing initial-purchase convention. Measured strategy returns
   begin on the next trading day. Benchmarks compared against the strategy
   are evaluated over this identical measured-return window.
4. Final observation. Mirroring the quarterly benchmark convention, a
   decision dated on the final observation of an evaluation window is not
   traded, because no later return exists in which it could matter.

## Phase 2: risk-adjusted momentum

Phase 2 keeps the Phase 1 timing, fallback, long-only allocation, and 63-day
lookback. It changes only how the three ETFs are ranked.

1. Calculate each ETF's trailing 63-trading-day total return using data ending
   one trading day before the rebalance close.
2. Calculate each ETF's trailing 21-trading-day realized volatility from daily
   returns ending on that same day.
3. Annualize volatility by multiplying the daily-return standard deviation by
   the square root of 252.
4. For each ETF with a positive 63-day return, calculate:

   `risk-adjusted score = 63-day return / annualized 21-day volatility`

5. Select the ETF with the highest risk-adjusted score.
6. If every 63-day return is negative, select SHY.
7. Hold exactly one ETF, long-only and unlevered, until the next rebalance.

A zero or missing volatility observation is a data-validation failure, not an
invitation to substitute a new rule. There is no volatility-window or score
optimization.

## Phase 2 mechanical clarifications (v0.2.2)

These clarifications make the Phase 2 rules deterministic. They were resolved
and recorded before any strategy result existed, and they are not parameters
to optimize. The v0.2.1 clarifications continue to apply.

1. Volatility window. For a decision date at position `p`, the 21 daily
   returns end at position `p - 1` and are computed from the 22 prices at
   positions `p - 22` through `p - 1`. The decision-date price can never
   influence its own volatility estimate.
2. Standard deviation convention. Volatility uses the sample standard
   deviation (`n - 1` denominator) of the 21 daily returns, annualized by
   multiplying by the square root of 252.
3. Fallback restated. If no ETF has a strictly positive 63-day trailing
   return, select SHY. This single rule covers the all-negative case and the
   otherwise-undefined case in which the highest trailing return is exactly
   zero.
4. Candidates and validation. Only ETFs with a strictly positive 63-day
   return are scored. A zero or missing volatility for a scored candidate
   raises a validation error; volatility of a non-candidate is never used
   and therefore cannot fail.
5. Ties. An exact tie in risk-adjusted scores breaks by the v0.2.1 rule:
   the tied ticker earliest in SHY, IEF, TLT wins.
6. Warm-up. Phase 2 uses the same qualifying decision dates as Phase 1: the
   64 prior observations required by the momentum window exceed the 22
   required by the volatility window, so the momentum warm-up governs.

## Benchmarks

1. Buy and hold IEF.
2. Equal-weight SHY, IEF, and TLT, rebalanced quarterly.

Both benchmarks receive the same return conventions and applicable cost model
as the two strategies.

## Costs

- Primary assumption: 10 basis points per dollar traded.
- Sensitivities: 5 and 20 basis points per dollar traded.
- Costs are applied to one-way turnover whenever target weights change.
- Every portfolio begins immediately after its initial allocation, so the common
  initial purchase is not charged. Only subsequent changes incur costs.
- No leverage, shorting, borrowing, market impact, taxes, or advisory fees.

## Metrics

- Compound annual growth rate.
- Annualized volatility.
- Sharpe ratio using a contemporaneous three-month Treasury rate when available.
- Maximum drawdown.
- Calmar ratio.
- Annual turnover.

## Metric mechanical clarifications (v0.2.3)

These clarifications make the six frozen metrics deterministic. They were
resolved and recorded before any strategy result existed, and they are not
parameters to optimize. The 252-trading-day year is the single time convention
for every metric in this contract.

1. Years elapsed. Years = number of measured daily returns divided by 252,
   over the identical measured-return window defined in v0.2.1 clause 3.
2. Compound annual growth rate. CAGR = (ending value of the net-of-cost
   wealth index divided by its starting value)^(1 / years elapsed) - 1.
3. Risk-free source. The three-month Treasury rate is the daily ^IRX series
   from Yahoo Finance via yfinance, a fourth data series recorded and hashed
   in the data manifest under the existing validation machinery. The quoted
   value is treated as the annualized percentage rate; the discount-basis
   approximation is acknowledged and immaterial at reported precision.
4. Daily risk-free rate. Daily rate = (quoted value / 100) / 252.
5. Risk-free gaps. A missing observation on a trading day is forward-filled
   from the most recent prior trading day. A gap exceeding 10 consecutive
   trading days, or a missing value with no prior observation to carry
   forward, is a data-validation failure, not an invitation to substitute a
   new rule.
6. Annualized volatility. Sample standard deviation (n - 1 denominator) of
   daily net returns, multiplied by the square root of 252, mirroring the
   v0.2.2 conventions.
7. Sharpe ratio. (Mean daily excess net return x 252) divided by (sample
   standard deviation of daily excess net returns x the square root of 252),
   where the daily excess net return is the daily net return minus the daily
   risk-free rate.
8. Maximum drawdown. The largest peak-to-trough decline of the net-of-cost
   wealth index, reported as a negative decimal.
9. Calmar ratio. CAGR divided by the absolute value of maximum drawdown. A
   maximum drawdown of exactly zero leaves Calmar undefined and raises a
   validation error rather than reporting infinity.
10. Annual turnover. The sum of daily one-way turnover divided by years
    elapsed. The uncharged initial allocation contributes zero turnover,
    mirroring the cost model.

Every metric is computed identically for both strategies and both benchmarks
over the identical measured-return window.

## Evaluation rules

Phase 1 primary hypothesis: after primary transaction costs, raw momentum's
locked-test Calmar ratio exceeds both benchmarks.

Phase 1 secondary hypothesis: after primary transaction costs, raw momentum's
locked-test maximum drawdown is smaller in magnitude than buy-and-hold IEF.

Phase 2 incremental hypothesis: after primary transaction costs, risk-adjusted
momentum's locked-test Calmar ratio exceeds raw momentum's Calmar ratio.

Phase 2 secondary hypothesis: risk-adjusted momentum's locked-test maximum
drawdown is smaller in magnitude than raw momentum's maximum drawdown.

Every result is reported together. Phase 2 is not declared better merely because
one metric improves. Failure or a null result does not authorize changing either
strategy and rerunning the same test period.

## Sensitivity policy

After both primary locked-test results are recorded, 42-day and 126-day momentum
lookbacks may be reported as labeled sensitivities. They cannot replace the
primary 63-day results or change the conclusion. The Phase 2 volatility window
remains 21 trading days.

## Phase 3: optional paper execution

After the offline report is frozen, one or both strategies may run in an Alpaca
Paper Only account. Paper execution tests scheduling, order construction,
position reconciliation, logging, and failure handling. It does not reopen the
historical research conclusion and does not prove profitability.

The paper layer is cut first if it threatens the offline artifact deadline.

## Safety boundary

- Offline research is the required deliverable.
- No real-money brokerage account or deposit.
- No live credentials, live API hostname, or live-order code path.
- Any later execution demonstration must use an Alpaca Paper Only account and
  must exit unless its configured trading hostname is exactly
  `paper-api.alpaca.markets`.
- Paper performance is an execution test, not evidence of profitability.

## Beyond the current project

Possible later research directions and the evidence required to justify them
are documented in [`roadmap.md`](roadmap.md). Those phases are not active scope
and receive no implementation time until Phases 1 and 2 ship.

## Artifact success

The artifact succeeds when the repository is reproducible, tests pass, the
method and limitations are defensible with the editor closed, and the result is
reported honestly. It does not require an economically favorable result.
