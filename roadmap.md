# Expansion Roadmap

## Active scope

The August artifact contains only:

1. Phase 1 raw momentum.
2. Phase 2 risk-adjusted momentum.
3. Optional Phase 3 paper-only execution.

Phases below describe how the research could become more sophisticated. They are
not promises, active tasks, or permission to expand the current build.

## Phase 4: interest-rate regime model

Add lagged economic information that has a direct relationship to Treasury
prices, such as:

- two-, ten-, and thirty-year Treasury yields;
- changes in the ten-year yield;
- the two-year versus ten-year yield-curve slope;
- the federal-funds rate; and
- market inflation expectations.

The question would change from "which duration recently performed best?" to
"what observable rate environment historically favored each duration?"

Main risk: macroeconomic series can be revised or published with delays. The
model must use only information actually available on each historical decision
date, preferably from point-in-time vintages.

## Phase 5: interpretable statistical prediction

Use a small statistical model, beginning with multinomial logistic regression,
to estimate which ETF is most likely to lead during the following week.

Candidate inputs could include lagged momentum, volatility, yield changes, and
yield-curve slope. Walk-forward training would use only earlier observations to
make each prediction.

Main risk: the dataset contains only a few thousand daily observations and far
fewer independent weekly regimes. A flexible model can memorize noise while
appearing impressive.

Gradient boosting could be compared later, but only against logistic regression
and only with a frozen feature set. Neural networks are not justified at this
sample size without substantially different data.

## Phase 6: portfolio construction and risk control

Instead of holding one ETF at 100%, allocate among all three using:

- inverse-volatility or risk-parity weights;
- an unlevered volatility target;
- maximum position limits;
- turnover penalties; and
- drawdown-aware exposure reductions.

This separates two questions: whether the signal predicts relative performance
and whether portfolio construction turns that signal into acceptable risk.

Main risk: every additional control adds parameters that can be tuned to past
losses.

## Phase 7: fixed-income relative value

Move from ETF direction to relationships along the yield curve, such as
steepening and flattening trades. A serious version would model duration,
convexity, carry, roll-down, financing, and transaction costs.

This is more directly related to institutional fixed-income relative-value work,
but it may require Treasury futures or bond-level data. It is inappropriate for
the current project until the simpler duration models are understood and
defensible.

Main risk: superficially market-neutral trades can still carry large curve,
liquidity, leverage, and basis risks.

## Phase 8: prospective validation

Run frozen candidate models forward with paper money for months rather than
days. Compare forecasted positions, simulated fills, realized costs, operational
failures, and performance with no historical redesign.

Prospective evidence is more credible than another round of historical tuning.
Real-money trading remains outside this roadmap unless it is separately
authorized after compliance, risk, and capital decisions.

## Rules for any expansion

Every future phase must:

1. State a finance-based reason for the added complexity.
2. Name the simple model it must beat.
3. Freeze features, parameters, costs, and evaluation rules before testing.
4. Use a genuinely untouched test, point-in-time walk-forward evaluation, or
   future paper period.
5. Report all comparisons, including failures.
6. Remain explainable without Claude, Codex, or the editor open.
7. Name what the new work displaces before it becomes active.

## Phase 9: the complexity gradient, studied honestly

Parked 2026-07-31, the morning after the development-period first look.
Origin disclosed for integrity: this idea was proposed the night the
first look disappointed, which is exactly when complexity ideas are
least trustworthy. It waits here until the current artifact ships.

The question: does added strategy complexity help or hurt in asset
allocation, measured across a preregistered ladder of models? The
current artifact already contains a four-rung gradient — hold IEF,
quarterly equal weight, Phase 1 ranking, Phase 2 risk-adjusted ranking —
and in development, Sharpe and Calmar fell monotonically as complexity
rose. The report may state that observation; this phase would test it
deliberately.

Relevant literature: DeMiguel, Garlappi, and Uppal, "Optimal Versus
Naive Diversification" (RFS 2009) — the 1/N result this project's own
equal-weight benchmark row echoes.

A legitimate version also requires a wider cross-section: three highly
correlated Treasury ETFs are close to the narrowest playground a
ranking rule can have, so any complexity study worth running would use
a broader asset universe, which multiplies both the opportunity and the
overfitting surface.

Evidence required before this becomes active, beyond the standard rules
below: every rung of the ladder preregistered before any rung is
evaluated; genuinely untouched out-of-sample data for the ladder as a
whole (the current project's test period is spent once and cannot serve
it); and an explicit accounting of in-sample-fit inflation, since more
complex models fit the past better mechanically and that improvement is
arithmetic, not evidence.
