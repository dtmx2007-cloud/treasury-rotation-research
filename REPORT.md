# Treasury Duration Rotation: A Preregistered Test of Weekly Momentum

Declan Miller, University of Notre Dame. October 2026. Research contract
`0.2.3`.

**Status: final.** All three periods have been run: development
(2003-2015), validation (2016-2020, opened once on 2026-07-31) and the
locked test (2021-2025, opened once on 2026-10-13).

## 1. Abstract

I tested whether a weekly momentum rule across three Treasury ETFs (SHY,
IEF, TLT) beats just holding IEF after trading costs, and whether adjusting
momentum for volatility helps. Before running anything I locked the rules,
the cost model, the metrics and the data hashes in this public repository.
Then I opened three periods in order: development (2003-2015), validation
(2016-2020, one look) and a locked test (2021-2025, one look).

Raw momentum lost to buy-and-hold IEF in all three. Through 2020 it roughly
tied IEF on CAGR before costs, and the trading toll was more than the whole
deficit (-0.87 and -0.98 points a year). It trailed on Sharpe and Calmar
even before costs, because it was far more volatile. In the locked test it
trailed IEF by about 3 points a year before costs and 3.85 after, so the
signal itself failed. The volatility-adjusted version had the worst CAGR,
Sharpe and Calmar of the four portfolios in the first two periods, and the
best CAGR, drawdown and Calmar in the locked test. Of the four
preregistered hypotheses, both Phase 1 hypotheses failed and both Phase 2
hypotheses held. I don't read any of it as a tradable edge.

## 2. Question and design

Can a weekly duration-momentum rule across SHY, IEF and TLT improve
drawdown-adjusted returns compared with simple benchmarks, and does a
volatility adjustment improve the simple rule?

The frozen design (full detail in
[`research_contract.md`](research_contract.md)):

- **Assets:** SHY, IEF and TLT daily adjusted closes from yfinance,
  2003-2025.
- **Phase 1 (raw momentum):** rebalance weekly. Hold the ETF with the
  highest trailing 63-trading-day return, using data that ends the day
  before the decision. If all three are negative, hold SHY. Long-only,
  unlevered, one ETF at a time.
- **Phase 2 (risk-adjusted momentum):** same timing and fallback. ETFs with
  a positive 63-day return are ranked by that return divided by their
  annualized 21-day volatility.
- **Benchmarks:** buy-and-hold IEF, and equal-weight SHY/IEF/TLT
  rebalanced quarterly. Same return conventions and cost model as the
  strategies.
- **Costs:** 10 bps per unit of one-way turnover. Switching the whole
  portfolio from one ETF to another costs 10 bps of the portfolio, about 5
  bps on each side. 5 and 20 bps are labeled sensitivities. Costs are
  charged inside the simulation, so every number in the tables is net of
  costs. Section 7 backs them out as an estimate.
- **Metrics (six, frozen):** CAGR, annualized volatility, Sharpe (against
  the ^IRX three-month rate), maximum drawdown, Calmar, annual turnover.
- **Periods (frozen):** development 2003-2015, validation 2016-2020,
  locked test 2021-2025.

## 3. The preregistration timeline

Every rule was public before the result it governs was published. Each
commit below comes before the event in the last column. Times are Eastern.
Rows 2 to 9 show the GitHub Actions run time for that push. Row 1 shows its
commit time, because CI didn't exist yet, and row 2's run caps it anyway,
since row 1 is in row 2's history.

| # | Event | File | Commit (time) | Came before |
|---|---|---|---|---|
| 1 | Public snapshot at contract v0.2.3 | `research_contract.md` | `693787c` (2026-07-30 11:05 am) | any performance number on any period |
| 2 | Development first-look precommitment | `PRECOMMITMENT.md` | `fa1b9d7` (2026-07-30 3:55 pm) | the development table |
| 3 | Validation precommitment | `VALIDATION_PRECOMMITMENT.md` | `a88376c` (2026-07-31 2:55 pm) | the validation table |
| 4 | Validation procedure | `validation_procedure.md` | `b1cde17` (2026-07-31 3:51 pm) | the validation table |
| 5 | Validation runner and 12 tests | `src/…/validate.py`, tests | `cbf279d` (2026-07-31 3:58 pm) | the single validation run |
| 6 | Report skeleton and freeze declaration | `REPORT.md`, `FREEZE_DECLARATION.md` | `98a9821` (2026-08-03 2:49 pm) | the locked-test table |
| 7 | Locked-test procedure | `locked_test_procedure.md` | `88f4b52` (2026-10-13 8:51 pm) | the locked-test runner |
| 8 | Locked-test runner and 19 tests | `src/…/locked_test.py`, tests | `349f4e7` (2026-10-13 8:58 pm) | the single locked-test run |
| 9 | Locked-test unlock logged | `LOCKED_TEST_UNLOCK.md` | `f2ad1be` (2026-10-13 9:00 pm) | the single locked-test run |

The locked-test output was committed right after row 9, in the same commit
as this version of the report.

Commit times can be set by whoever makes the commit, which is why rows 2
to 9 use GitHub's record instead: every push from row 2 on triggered a test
run in GitHub Actions, and GitHub stamps those runs on its own servers.

The point of this table is the order. A backtest can leak in a lot of
ways, and the hardest one to catch is the researcher: you see a number, you
change a rule, and the next number looks better. Once that happens, part of
any gap between the backtest and real trading is just the leak. The
timestamps show every rule was public before the result it governs was
published. They can't prove I never ran anything privately first; every
preregistration asks you to take that part on trust. The public order is
the part you can check, and it's what makes preregistration the
leak-prevention device.

## 4. Development period, 2003-2015

Primary table, 10 bps, 3,208 trading days (measured-return window
2003-04-07 through 2015-12-31, the same for all four portfolios):

| Metric | Phase 1 | Phase 2 | Hold IEF | Eq weight |
|---|---|---|---|---|
| CAGR | 4.34% | 1.66% | 5.21% | 4.83% |
| Annualized volatility | 10.69% | 6.53% | 6.94% | 7.17% |
| Sharpe ratio | 0.333 | 0.091 | 0.584 | 0.517 |
| Maximum drawdown | -20.06% | -13.97% | -10.40% | -13.08% |
| Calmar ratio | 0.216 | 0.119 | 0.501 | 0.369 |
| Annual turnover | 8.955 | 6.991 | 0.000 | 0.039 |

Cost sensitivities: at 5 bps Phase 1 CAGR is 4.81% (still behind IEF at
5.21%) and Phase 2 is 2.01%. At 20 bps Phase 1 is 3.41% and Phase 2 is
0.95% (Sharpe -0.016). Turnover is the same at every cost level because
the decisions never see costs.

Both strategies trailed both benchmarks on CAGR, Sharpe and Calmar after
costs. Before costs, Phase 1 about tied IEF on CAGR (roughly 5.28% against
5.21%; section 7 shows how I backed costs out). On Sharpe and Calmar it
trailed even before costs, because it ran about 1.5 times IEF's
volatility. The toll then turned a tie on CAGR into a loss.

I regenerated this table on 2026-08-14 with the development runner, which
the contract lets me rerun, in the pinned environment against the
hash-checked cache. It matched both preregistered anchors (Phase 1 net CAGR
4.34%, Calmar 0.216).

## 5. Validation period, 2016-2020 (one look, run 2026-07-31)

Primary table, 10 bps, 1,259 trading days, same window for all four
portfolios:

| Metric | Phase 1 | Phase 2 | Hold IEF | Eq weight |
|---|---|---|---|---|
| CAGR | 3.40% | -1.94% | 4.38% | 4.77% |
| Annualized volatility | 12.02% | 5.07% | 5.35% | 6.64% |
| Sharpe ratio | 0.246 | -0.579 | 0.622 | 0.568 |
| Maximum drawdown | -16.37% | -23.42% | -8.82% | -9.07% |
| Calmar ratio | 0.207 | -0.083 | 0.497 | 0.526 |
| Annual turnover | 11.009 | 11.009 | 0.000 | 0.030 |

Cost sensitivities: at 5 bps Phase 1 CAGR is 3.97% (still behind IEF at
4.38%) and Phase 2 is -1.40%. At 20 bps Phase 1 is 2.26% and Phase 2 is
-3.02% (Sharpe -0.798). Turnover is again the same at every cost level.

Both strategies trailed both benchmarks on CAGR, Sharpe and Calmar at every
contract cost level, and Phase 2 trailed Phase 1 on all three.

Side by side, validation looks like development with the volume turned up.
Phase 1's CAGR fell from 4.34% to 3.40% and IEF's fell from 5.21% to 4.38%.
Both dropped about a point, so the gap barely moved (-0.87 to -0.98). The
Calmar ratios barely moved at all: Phase 1 went from 0.216 to 0.207 and IEF
from 0.501 to 0.497, across two very different rate environments. That's
hard to square with a "development was just unlucky" defense. If Phase 1
had been unlucky from 2003 to 2015, new years should have pulled it back
toward IEF. They didn't. It kept about the same risk-adjusted return, still
under half of IEF's. Phase 2 got worse on CAGR, Sharpe, drawdown and
Calmar, and both strategies traded more (Phase 1 from 8.955 to 11.009 turns
a year, Phase 2 from 6.991 to 11.009).

## 6. Locked test, 2021-2025 (one look, run 2026-10-13)

I opened this period once, after the procedure, the runner and the unlock
log were all public (section 3, rows 7 to 9). The raw output is in
[`artifacts/locked_test_output.txt`](artifacts/locked_test_output.txt).

Primary table, 10 bps, 1,255 trading days (measured-return window
2021-01-04 through 2025-12-31, the same for all four portfolios):

| Metric | Phase 1 | Phase 2 | Hold IEF | Eq weight |
|---|---|---|---|---|
| CAGR | -5.77% | -0.35% | -1.92% | -2.90% |
| Annualized volatility | 8.40% | 4.57% | 7.71% | 8.17% |
| Sharpe ratio | -1.047 | -0.758 | -0.630 | -0.713 |
| Maximum drawdown | -31.02% | -16.90% | -22.38% | -24.54% |
| Calmar ratio | -0.186 | -0.021 | -0.086 | -0.118 |
| Annual turnover | 8.634 | 3.614 | 0.000 | 0.044 |

Cost sensitivities: at 5 bps Phase 1 CAGR is -5.36% and Phase 2 is -0.17%.
At 20 bps Phase 1 is -6.58% and Phase 2 is -0.71%. IEF (-1.92%) and equal
weight (-2.90%) are the same at all three levels to two decimals.

The four preregistered hypotheses, scored on the primary table:

| # | Hypothesis | Numbers | Result |
|---|---|---|---|
| 1 | Phase 1 Calmar beats both benchmarks | -0.186 vs IEF -0.086 and EW -0.118 | Not supported |
| 2 | Phase 1 drawdown smaller than IEF's | 31.02% vs 22.38% | Not supported |
| 3 | Phase 2 Calmar beats Phase 1 | -0.021 vs -0.186 | Supported |
| 4 | Phase 2 drawdown smaller than Phase 1's | 16.90% vs 31.02% | Supported |

The calls come out the same at 5 and 20 bps. They compare point
estimates, with no significance test (section 9). And hypotheses 3 and 4
were a low bar this time, because Phase 1 finished last on almost
everything.

IEF lost 1.92% a year over these five years, and every portfolio here did
worse than T-bills: all four Sharpe ratios are below zero. Phase 1 had the
lowest CAGR, Sharpe and Calmar and the deepest drawdown of the four. Phase
2 had the best CAGR (-0.35%), the smallest drawdown (-16.90%) and the best
Calmar (-0.021), but it was third on Sharpe (-0.758), behind IEF (-0.630)
and equal weight (-0.713). Phase 2 against the benchmarks was never a
preregistered hypothesis, so I'm reporting that, not claiming it.

The contract allows 42- and 126-day lookbacks as labeled sensitivities
once these results are recorded. I didn't run them. They can't change the
conclusion, and running them would need its own preregistered procedure.

## 7. The toll

Here is Phase 1 against IEF in all three periods, in CAGR points per year:

| | Gross gap, est. (P1 - IEF) | Toll | Net gap (P1 - IEF) |
|---|---|---|---|
| Development 2003-2015 | +0.07 | 0.94 | -0.87 |
| Validation 2016-2020 | +0.17 | 1.15 | -0.98 |
| Locked test 2021-2025 | -3.03 | 0.82 | -3.85 |

How I got these. The net gap comes straight from the CAGR rows. Costs come
off each trade as a fraction of the portfolio, so they compound: a year of
trading multiplies wealth by (1 - 0.001) raised to the annual turnover.
Undoing that gives Phase 1's CAGR before costs, and the toll is gross CAGR
minus net CAGR. I checked the model against the report's own sensitivity
tables, and it reproduces every 5 and 20 bps CAGR, for both strategies in
all three periods, to within 0.01. The quick version, turnover times 10
bps, gives tolls of 0.90, 1.10 and 0.86 and tells the same story.

In development, Phase 1 started 0.07 points a year ahead of IEF before
costs, paid a 0.94 point toll, and landed at -0.87. In validation it
started 0.17 ahead, paid 1.15, and landed at -0.98. Both gaps are measured
against the same IEF, which never trades and pays no toll, so subtracting
the toll from the gross gap lands exactly on the net gap. In the locked
test Phase 1 started 3.03 behind, paid 0.82, and landed at -3.85.

After the first two periods I wrote: "The toll is not an execution detail
to be optimized away; it is the entire distance between the idea and a
tradable strategy." On CAGR, that held for 2003 to 2020. It didn't hold
for 2021 to 2025. Through 2020 the signal broke even on CAGR and the costs
lost the money. From 2021 on the signal lost the money on its own, and the
costs made it worse.

## 8. Phase 2: worst twice, best once

On Calmar, Phase 2 finished last of the four in development, last in
validation, and first in the locked test.

In validation the two simplest portfolios, equal weight and buy-and-hold
IEF, took the top two Calmar spots, with equal weight first (0.526 against
IEF's 0.497). Phase 2, the most complex, came last. That loosely echoes
DeMiguel, Garlappi and Uppal (2009), who found naive 1/N diversification
hard to beat out of sample. Their paper is about mean-variance
optimization, not momentum, and the echo only shows up in one of my three
periods. In the locked test the pattern broke: Phase 2 came first and
Phase 1 came last.

What I wrote after validation: "Volatility measures the scatter and throws
the average away; drawdown is what the average does to you compounded."

The next two paragraphs are my reading of the rules and the tables. I
never looked at holdings, because the procedures count that as iteration,
so none of this is measured.

Validation is the clearest case. Phase 2 was supposed to dodge drawdowns,
and it dug the deepest one of the four, -23.42%, at the lowest volatility,
5.07%. The most likely way to get that is a lot of small losses in a row
with no big recovery. Phase 2 traded as much as Phase 1 (11.0 turns a
year), so it paid the same toll. And dividing by 21-day volatility kept
steering it toward whatever had been calm lately, and in a choppy,
low-rate market a calm stretch doesn't tell you much about the next one.
Low volatility kept each loss small. Trading every few weeks made them add
up.

In the locked test the same rule did the opposite, and I can only partly
explain it. Phase 2 traded far less, 3.6 turns a year. Both rules fall
back to SHY when no trailing return is positive, and among the rest,
dividing by volatility tilts Phase 2 toward the calmer picks, which in a
rising-rate market should mean less duration. But a -16.90% drawdown means
it still held IEF or TLT through real losses. So the honest version is:
Phase 2 lost less than everything else, and I can't tell how much of that
was the volatility tilt and how much was timing luck. Either way, a rule
that is worst in two periods and best in one is not something I'd trust
with money.

## 9. Limitations

- **No significance test.** Validation and the locked test were each run
  once, and the hypothesis calls compare point estimates. I didn't
  preregister a significance test, so there isn't one. As a rough guide,
  the standard error of a five-year Sharpe ratio is around 0.45, so most
  single-period gaps between these portfolios are inside the noise. Phase
  1 losing to IEF in all three periods is the most consistent result, but
  three periods is still a thin basis, and any one period's ranking is
  weaker than that.
- **Calmar and Sharpe misbehave when returns are negative.** In 2021 to
  2025 every CAGR and every excess return was negative. With a negative
  CAGR, a deeper drawdown pulls Calmar toward zero, so Calmar can reward a
  worse drawdown. With negative excess returns, lower volatility pushes
  Sharpe further below zero, so Sharpe punishes being calm. Phase 2 leads
  on Calmar because its CAGR was far less negative (its small drawdown
  actually counts against it here), and it sits third on Sharpe because
  it was the calmest portfolio. The four hypothesis calls still hold, because in each Calmar
  comparison the winner had both the higher CAGR and the smaller drawdown,
  so the sign problem can't flip them. Next time I'd pick a headline metric
  that doesn't do this.
- **Hindsight.** I wrote the rules in July 2026, already knowing 2022 was a
  terrible year for bonds. Preregistration stops me from tuning on
  results. It doesn't erase what I knew about market history. Both rules
  are standard momentum with quarter and month windows, and I didn't build
  them to dodge 2022, but nobody can verify that from the outside.
- **No cash benchmark.** The benchmarks are IEF and equal weight. There's
  no T-bill or SHY benchmark, even though SHY is the fallback asset. In
  2021 to 2025 all four portfolios trailed T-bills.
- **Execution and costs.** Every trade fills at the decision day's close,
  using data through the day before. That's achievable with
  market-on-close orders, and 10 bps per full switch is probably on the
  conservative side for SHY, IEF and TLT at small size. But it's one flat
  number with no market impact, so it says nothing about trading real
  size.
- **The turnover coincidence.** In validation, Phase 1 and Phase 2 both
  show annual turnover of 11.009, about 55 switches each over five years.
  That's a coincidence of counts, not a bug or shared holdings. Their CAGRs
  are more than five points apart, and turnover doesn't change across cost
  levels, which backs up that decisions never see costs.
- **Three periods is still a small sample.** 2003-2015, 2016-2020 and
  2021-2025 are very different rate environments, but three eras is not
  much for a weekly rule.
- **Data.** Prices are yfinance adjusted closes pulled for personal
  educational research. Raw prices aren't redistributed. The manifest
  records where the data came from and its content hashes, but anyone
  reproducing this has to pull the data themselves under the provider's
  terms.
- **Scope.** No live trading and no advice. No market impact, taxes or
  borrowing.

## 10. Conclusion

Simple Treasury momentum lost to just holding IEF in all three periods.
From 2003 to 2020 the signal roughly broke even on CAGR before costs, and
the toll was more than the whole loss. On risk-adjusted terms it trailed
even before costs. From 2021 to 2025 the signal lost about 3 points a year
on its own. Adjusting for volatility lowered CAGR, Sharpe and Calmar in two
periods and raised them in one, the one with the 2022 rate hikes in it. Of
the four hypotheses I locked in before the test, both Phase 1 hypotheses
failed and both Phase 2 hypotheses held, on point estimates, against a
weak Phase 1.

None of that is an edge I'd put money behind. What I'd keep is the
process: write the rules down, lock the data, open each held-out period
once, and report what comes out, including the parts that don't fit the
story I had after the first two periods.

## References

- DeMiguel, V., Garlappi, L., & Uppal, R. (2009). Optimal versus naive
  diversification: How inefficient is the 1/N portfolio strategy?
  *Review of Financial Studies*, 22(5), 1915-1953.
- Repository: <https://github.com/dtmx2007-cloud/treasury-rotation-research>

## How this was built

I used AI assistants (Claude and Codex) for much of the code and for
drafting this write-up. The research rules, the precommitments, and every
decision about what got run and what got reported were mine.
