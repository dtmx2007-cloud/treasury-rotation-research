# Treasury Duration Rotation: A Preregistered Test of Weekly Momentum

**Status: SKELETON.** Drafted 2026-08-03, after the development first look
(2026-07-30) and the one validation review (2026-07-31), and **before** the
locked 2021-2025 test period has been opened. Locked-test cells below are
intentionally empty. Contract version `0.2.3`.

Author: Declan Miller. Drafting assistance under Declan's sign-off; every
sentence marked **[DTM]** is Declan's own and every `TODO(Declan)` slot must
be filled in his words before this document is called a draft.

---

## 1. Abstract

`TODO(Declan) — written LAST, after the locked test. Must state: the
question, the preregistered design, the three-period result, and the toll
finding, in under 200 words. No adjectives the tables don't earn.`

## 2. Question and design

Can a weekly duration-momentum rule across SHY, IEF, and TLT improve
drawdown-adjusted returns relative to transparent benchmarks, and does a
volatility adjustment improve the simple rule?

Summary of the frozen design (full detail in
[`research_contract.md`](research_contract.md)):

- **Assets:** SHY / IEF / TLT daily adjusted closes (yfinance), 2003-2025.
- **Phase 1:** weekly rebalance; hold the ETF with the highest trailing
  63-trading-day return (window ends one day before the decision close);
  all-negative fallback to SHY; long-only, unlevered, one ETF at a time.
- **Phase 2:** identical timing and fallback; candidates with positive
  63-day returns are ranked by return divided by annualized 21-day
  volatility.
- **Benchmarks:** buy-and-hold IEF; equal-weight SHY/IEF/TLT rebalanced
  quarterly. Same return conventions and cost model as the strategies.
- **Costs:** 10 bps per dollar traded (primary), 5 and 20 bps labeled
  sensitivities, charged on one-way turnover inside the simulation — all
  printed performance is therefore **net of costs**.
- **Metrics (six, frozen):** CAGR, annualized volatility, Sharpe (^IRX
  risk-free), maximum drawdown, Calmar, annual turnover.
- **Periods (frozen):** development 2003-2015; validation 2016-2020 (one
  look, now spent); locked test 2021-2025 (unopened as of this writing).

## 3. The preregistration timeline

Every rule above was fixed, in public, before the result it governs
existed. The commit timestamps are the evidence; each precedes the event
to its right.

| # | Event | File | Commit | Preceded |
|---|---|---|---|---|
| 1 | Public snapshot at contract v0.2.3 | `research_contract.md` | `693787c` (2026-07-30) | any performance number on any period |
| 2 | Development first-look precommitment | `PRECOMMITMENT.md` | `fa1b9d7` (2026-07-30) | the development table |
| 3 | Validation precommitment | `VALIDATION_PRECOMMITMENT.md` | `a88376c` (2026-07-31) | the validation table |
| 4 | Validation procedure preregistered | `validation_procedure.md` | `b1cde17` (2026-07-31) | the validation table |
| 5 | Validation runner + 12 tests pushed | `src/…/validate.py`, tests | `cbf279d` (2026-07-31) | the single execution of the runner |
| 6 | Report skeleton + freeze declaration | `REPORT.md`, `FREEZE_DECLARATION.md` | `98a9821` (2026-08-03) | the locked-test table |

`TODO(Declan): one paragraph, your words, on why the timestamps are the
point — what a reader should conclude from the promise always predating
the result. Your warm-up consequence sentence about the gap "measuring
the size of the leak" belongs in or near this paragraph: preregistration
is the leak-prevention device.` **[DTM slot]**

## 4. Development period, 2003-2015

Primary table, 10 bps, 3,208 trading days (measured-return window
2003-04-07 through 2015-12-31, identical for all four portfolios):

| Metric | Phase 1 | Phase 2 | Hold IEF | Eq weight |
|---|---|---|---|---|
| CAGR | 4.34% | 1.66% | 5.21% | 4.83% |
| Annualized volatility | 10.69% | 6.53% | 6.94% | 7.17% |
| Sharpe ratio | 0.333 | 0.091 | 0.584 | 0.517 |
| Maximum drawdown | -20.06% | -13.97% | -10.40% | -13.08% |
| Calmar ratio | 0.216 | 0.119 | 0.501 | 0.369 |
| Annual turnover | 8.955 | 6.991 | 0.000 | 0.039 |

Labeled cost sensitivities: at 5 bps Phase 1 CAGR 4.81% (still trailing
IEF at 5.21%), Phase 2 2.01%; at 20 bps Phase 1 3.41%, Phase 2 0.95%
(Sharpe -0.016). Turnover is identical at every cost level because
decisions never see costs.

Table regenerated 2026-08-14 with the develop runner (rerunnable freely
under the contract) in the pinned environment against the hash-validated
cache; the run matched both preregistered anchors (Phase 1 net CAGR
4.34%, Calmar 0.216).

Narrative bullets to expand into prose:

- Both strategies trail both benchmarks on CAGR, Sharpe, and Calmar net
  of primary costs.
- Gross of costs, Phase 1 approximately ties buy-and-hold IEF
  (≈5.24 vs 5.21): the signal roughly pays for itself before the toll and
  loses precisely the toll after it.

## 5. Validation period, 2016-2020 (the one look, executed 2026-07-31)

Primary table, 10 bps, 1,259 trading days, identical measured-return
window for all four portfolios:

| Metric | Phase 1 | Phase 2 | Hold IEF | Eq weight |
|---|---|---|---|---|
| CAGR | 3.40% | -1.94% | 4.38% | 4.77% |
| Annualized volatility | 12.02% | 5.07% | 5.35% | 6.64% |
| Sharpe ratio | 0.246 | -0.579 | 0.622 | 0.568 |
| Maximum drawdown | -16.37% | -23.42% | -8.82% | -9.07% |
| Calmar ratio | 0.207 | -0.083 | 0.497 | 0.526 |
| Annual turnover | 11.009 | 11.009 | 0.000 | 0.030 |

Labeled cost sensitivities: at 5 bps Phase 1 CAGR 3.97% (still trailing
IEF at 4.38%), Phase 2 -1.40%; at 20 bps Phase 1 2.26%, Phase 2 -3.02%
(Sharpe -0.798). Turnover is identical at every cost level because
decisions never see costs.

**Verdict of the review:** the development story holds on unseen years
and intensifies. Both strategies trail both benchmarks on CAGR, Sharpe,
and Calmar at every contract cost level; Phase 2 trails Phase 1 on all
three.

`TODO(Declan): side-by-side paragraph — development vs validation, metric
by metric. Include the Calmar stability observation (P1 0.216 → 0.207,
IEF 0.501 → 0.497 across very different rate regimes) and what it does to
a "development was unlucky" defense.` **[DTM slot]**

## 6. The toll

The central quantitative finding, replicated across two eras:

| | Gross gap (P1 − IEF) | Toll (pts/yr) | Net gap (P1 − IEF) |
|---|---|---|---|
| Development 2003-2015 | +0.03 | 0.90 | -0.87 |
| Validation 2016-2020 | +0.12 | 1.10 | -0.98 |

`TODO(Declan): the bridge sentence. You wrote it today with practice
numbers — "start at the gross edge, subtract the full toll, land
precisely on the net deficit, because both comparisons share the same
benchmark." Rewrite it with the real numbers above, once per period.`
**[DTM slot]**

**[DTM]** "The toll is not an execution detail to be optimized away; it
is the entire distance between the idea and a tradable strategy."

## 7. The complexity gradient runs backwards

Ordered by complexity: equal weight < buy-and-hold IEF < Phase 1 <
Phase 2. On unseen data the ranking of outcomes is the reverse of the
ranking of sophistication:

- Equal weight took the validation Calmar crown (0.526 vs IEF 0.497).
- Phase 2's single development-period virtue — the smaller drawdown —
  **reversed**: -23.42% is the deepest drawdown of all four portfolios,
  dug at the lowest volatility (5.07%). A staircase bleed, not an
  elevator shaft: persistent negative drift, not one violent day.
- This echoes DeMiguel, Garlappi & Uppal (2009): naive 1/N
  diversification is hard to beat out of sample. `TODO(Declan): verify
  citation details before the draft stage.`

**[DTM]** "Volatility measures the scatter and throws the average away;
drawdown is what the average does to you compounded."

`TODO(Declan): one paragraph in your words on WHY Phase 2's defense
failed out of sample — the whipsaw mechanism, not just the numbers.`
**[DTM slot]**

## 8. Locked test, 2021-2025 — preregistered, not yet run

This section is written, and this skeleton pushed publicly, **before**
the locked period is opened. The four preregistered hypotheses, verbatim
from the contract:

1. **Phase 1 primary:** after primary costs, raw momentum's locked-test
   Calmar exceeds both benchmarks.
2. **Phase 1 secondary:** after primary costs, raw momentum's locked-test
   maximum drawdown is smaller in magnitude than buy-and-hold IEF's.
3. **Phase 2 incremental:** after primary costs, risk-adjusted momentum's
   locked-test Calmar exceeds raw momentum's.
4. **Phase 2 secondary:** risk-adjusted momentum's locked-test maximum
   drawdown is smaller in magnitude than raw momentum's.

All results will be reported together; no metric cherry-picking; failure
does not authorize changing a rule and re-running. Opening the period is
a one-way event and will be logged. Only after both primary locked-test
results are recorded may the 42- and 126-day lookbacks run, as labeled
sensitivities that cannot change the conclusion.

| Metric | Phase 1 | Phase 2 | Hold IEF | Eq weight |
|---|---|---|---|---|
| CAGR | — | — | — | — |
| Annualized volatility | — | — | — | — |
| Sharpe ratio | — | — | — | — |
| Maximum drawdown | — | — | — | — |
| Calmar ratio | — | — | — | — |
| Annual turnover | — | — | — | — |

## 9. Limitations, stated plainly

- **The turnover coincidence.** Phase 1 and Phase 2 both print annual
  turnover of 11.009 in validation — approximately 55 switches each over
  five years. This is a coincidence of counts, not a bug or shared
  holdings: their CAGRs differ by more than five points, and turnover's
  invariance across cost levels corroborates that decisions never see
  costs. One honest sentence here prevents a careful reader from
  concluding the two signals are secretly identical.
- **One-look design.** The validation review was executed exactly once,
  by preregistered procedure, and can never be re-run; the printed tables
  are the only validation record. This is a feature for integrity and a
  limitation for statistical depth — no confidence intervals, no
  bootstrap, one draw per period.
- **Data provenance.** Prices are yfinance adjusted closes retrieved for
  personal educational research; raw prices are not redistributed. The
  manifest records provenance and content hashes, but a third party must
  re-retrieve data under the provider's terms to reproduce the tables.
- **Two regimes, three periods.** 2003-2015 and 2016-2020 span very
  different rate environments, but this is still a small number of
  independent eras for a weekly-frequency rule.
- **Educational scope.** No live trading, no advice, no market impact,
  taxes, or borrowing; costs are a flat per-dollar assumption.

`TODO(Declan): any limitation you believe that this list is missing. You
found the last two wrinkles yourself — look for a third.` **[DTM slot]**

## 10. Conclusion

`TODO(Declan) — written after the locked test, in your words. The
development and validation verdict you may pre-draft: simple timing rules
lost to sitting still, twice, on preregistered unseen data, and the toll
was the entire distance. The locked test completes or complicates that
sentence; nothing before it does.`

## References

- DeMiguel, V., Garlappi, L., & Uppal, R. (2009). Optimal versus naive
  diversification: How inefficient is the 1/N portfolio strategy?
  *Review of Financial Studies*, 22(5). `TODO(Declan): verify.`
- Repository: <https://github.com/dtmx2007-cloud/treasury-rotation-research>
