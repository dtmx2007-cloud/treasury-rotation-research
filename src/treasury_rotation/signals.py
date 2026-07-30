"""Phase 1 and Phase 2 momentum decisions under research contract v0.2.2.

This module turns validated prices into weekly one-hot target weights. It
contains no performance measurement, and it rejects the locked 2021-2025 test
period exactly as the portfolio engine does.

Contract clarifications implemented here (research_contract.md):

1. (v0.2.1) The trailing 63-trading-day return for a decision at calendar
   position ``p`` is ``price[p - 1] / price[p - 64] - 1``, so the
   decision-date price can never influence its own selection.
2. (v0.2.1) Exact ties are broken by shortest duration: the tied ticker
   earliest in ``(SHY, IEF, TLT)`` wins. The rule never inspects holdings.
3. (v0.2.1) The first decision date is the earliest final-trading-day-of-week
   observation with ``p >= 64``. Its selection is the free initial
   allocation, and measured strategy returns begin the next trading day.
4. (v0.2.1) A decision dated on the final observation is not traded,
   mirroring the quarterly benchmark convention.
5. (v0.2.2) Phase 2 volatility uses the sample standard deviation of the 21
   daily returns ending at position ``p - 1`` (prices ``p - 22`` through
   ``p - 1``), annualized by the square root of 252.
6. (v0.2.2) If no ETF has a strictly positive 63-day return, SHY is
   selected. Only strictly positive raw returns are scored, and a zero or
   missing volatility for a scored candidate is a validation failure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from treasury_rotation.config import (
    LOOKBACK_TRADING_DAYS,
    RISK_ADJUSTED_VOLATILITY_DAYS,
    TICKERS,
)
from treasury_rotation.portfolio import (
    PortfolioSimulation,
    PortfolioValidationError,
    calculate_returns,
    simulate_portfolio,
    validate_labeled_frame,
)

# A 63-trading-day total return needs 64 price observations: one at the start
# of the span and one at the end. The extra +1 exists because the window must
# end one trading day BEFORE the decision date, so the decision date itself is
# position 64 at the earliest.
MINIMUM_PRIOR_OBSERVATIONS = LOOKBACK_TRADING_DAYS + 1

# Likewise, 21 daily returns require 22 prices. The momentum warm-up (64)
# exceeds this, so Phase 2 qualifies on exactly the same decision dates.
VOLATILITY_PRICE_OBSERVATIONS = RISK_ADJUSTED_VOLATILITY_DAYS + 1

# The contract annualizes daily volatility by the square root of 252, the
# conventional count of U.S. trading days in a year.
ANNUALIZATION_FACTOR = math.sqrt(252.0)


class SignalValidationError(PortfolioValidationError):
    """Raised when signal inputs or arithmetic are invalid."""


@dataclass(frozen=True)
class MomentumDecisions:
    """Auditable record of every qualifying weekly decision.

    ``scores`` holds each ETF's trailing 63-day return per decision date,
    ``selections`` the chosen ticker, and ``targets`` the one-hot weights the
    portfolio engine installs at that decision close.
    """

    scores: pd.DataFrame
    selections: pd.Series
    targets: pd.DataFrame


def weekly_decision_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Return the final trading day of each calendar week in ``index``.

    Weeks are calendar weeks (Monday through Sunday). In an ordinary week the
    final trading day is Friday; in a holiday-shortened week it is the last
    day that actually traded.
    """

    dates = pd.DatetimeIndex(index)
    if dates.empty:
        return pd.DatetimeIndex([], name=dates.name)
    if dates.has_duplicates or not dates.is_monotonic_increasing:
        raise SignalValidationError(
            "Decision dates require unique, increasing observations."
        )
    date_series = pd.Series(dates, index=dates)
    week_ends = date_series.groupby(dates.to_period("W")).last()
    return pd.DatetimeIndex(week_ends.values, name=dates.name)


def trailing_returns(prices: pd.DataFrame, decision_date: pd.Timestamp) -> pd.Series:
    """Calculate each ETF's 63-day trailing return for one decision date.

    The window ends one trading day before ``decision_date`` and spans exactly
    ``LOOKBACK_TRADING_DAYS`` trading days, so it uses the prices at calendar
    positions ``p - 1`` and ``p - 64``.
    """

    raw_position = prices.index.get_loc(pd.Timestamp(decision_date))
    try:
        position = int(raw_position)
    except TypeError as error:
        raise SignalValidationError(
            "Decision date must match exactly one price row."
        ) from error
    if position < MINIMUM_PRIOR_OBSERVATIONS:
        raise SignalValidationError(
            f"Decision at position {position} lacks the "
            f"{MINIMUM_PRIOR_OBSERVATIONS} prior observations required."
        )
    window_end = prices.iloc[position - 1]
    window_start = prices.iloc[position - MINIMUM_PRIOR_OBSERVATIONS]
    return window_end / window_start - 1.0


def select_ticker(scores: pd.Series) -> str:
    """Apply the frozen selection rule to one row of trailing returns.

    Highest score wins. If every score is negative, SHY wins. An exact tie is
    broken by the shortest-duration ticker, which is simply the earliest
    entry in ``TICKERS`` because that tuple is ordered by duration.
    """

    if list(scores.index) != list(TICKERS):
        raise SignalValidationError(
            f"Scores must have labels {list(TICKERS)} in order."
        )
    if scores.isna().any():
        raise SignalValidationError("Scores contain missing values.")
    if (scores < 0).all():
        return TICKERS[0]
    best = float(scores.max())
    for ticker in TICKERS:
        if float(scores[ticker]) == best:
            return ticker
    raise SignalValidationError("No ticker matched the maximum score.")


def generate_phase1_decisions(prices: pd.DataFrame) -> MomentumDecisions:
    """Produce every qualifying weekly decision for a validated price table."""

    validate_labeled_frame(prices, frame_name="prices")
    if (prices <= 0).any(axis=None):
        raise SignalValidationError("Prices must be strictly positive.")

    qualifying = [
        date
        for date in weekly_decision_dates(prices.index)
        if prices.index.get_loc(date) >= MINIMUM_PRIOR_OBSERVATIONS
    ]
    if not qualifying:
        raise SignalValidationError(
            "No weekly decision date has enough history for the "
            f"{LOOKBACK_TRADING_DAYS}-day lookback."
        )

    decision_index = pd.DatetimeIndex(qualifying, name=prices.index.name)
    scores = pd.DataFrame(
        [trailing_returns(prices, date) for date in decision_index],
        index=decision_index,
    )
    selections = pd.Series(
        [select_ticker(row) for _, row in scores.iterrows()],
        index=decision_index,
        name="selection",
    )
    targets = pd.DataFrame(
        0.0,
        index=decision_index,
        columns=list(TICKERS),
    )
    for date, ticker in selections.items():
        targets.loc[date, ticker] = 1.0
    return MomentumDecisions(scores=scores, selections=selections, targets=targets)


def trailing_volatility(
    prices: pd.DataFrame,
    decision_date: pd.Timestamp,
) -> pd.Series:
    """Calculate each ETF's annualized 21-day volatility for one decision.

    The 21 daily returns end at position ``p - 1`` and come from the 22
    prices at positions ``p - 22`` through ``p - 1``, so the decision-date
    price can never influence its own volatility estimate. Volatility is the
    sample standard deviation (``n - 1`` denominator) of those daily
    returns, annualized by the square root of 252.
    """

    raw_position = prices.index.get_loc(pd.Timestamp(decision_date))
    try:
        position = int(raw_position)
    except TypeError as error:
        raise SignalValidationError(
            "Decision date must match exactly one price row."
        ) from error
    if position < VOLATILITY_PRICE_OBSERVATIONS:
        raise SignalValidationError(
            f"Decision at position {position} lacks the "
            f"{VOLATILITY_PRICE_OBSERVATIONS} prior observations required "
            "for the volatility window."
        )
    window_prices = prices.iloc[position - VOLATILITY_PRICE_OBSERVATIONS : position]
    daily_returns = window_prices.pct_change(fill_method=None).iloc[1:]
    return daily_returns.std(ddof=1) * ANNUALIZATION_FACTOR


def select_ticker_risk_adjusted(
    raw_scores: pd.Series,
    volatility: pd.Series,
) -> str:
    """Apply the frozen Phase 2 selection rule for one decision date.

    Only ETFs with strictly positive raw 63-day returns are scored; each
    candidate's score is raw return divided by annualized volatility. If no
    return is strictly positive, SHY is selected (v0.2.2 fallback). A zero
    or missing volatility for a scored candidate is a validation failure; a
    non-candidate's volatility is never used. Exact score ties break to the
    shortest-duration ticker via the ``TICKERS`` ordering.
    """

    for series, name in ((raw_scores, "raw scores"), (volatility, "volatility")):
        if list(series.index) != list(TICKERS):
            raise SignalValidationError(
                f"{name.title()} must have labels {list(TICKERS)} in order."
            )
    if raw_scores.isna().any():
        raise SignalValidationError("Raw scores contain missing values.")

    candidates = [ticker for ticker in TICKERS if float(raw_scores[ticker]) > 0.0]
    if not candidates:
        return TICKERS[0]

    risk_scores: dict[str, float] = {}
    for ticker in candidates:
        ticker_volatility = volatility[ticker]
        if pd.isna(ticker_volatility) or float(ticker_volatility) <= 0.0:
            raise SignalValidationError(
                f"Volatility for {ticker} is zero or missing; the contract "
                "treats this as a data-validation failure."
            )
        risk_scores[ticker] = float(raw_scores[ticker]) / float(ticker_volatility)

    best = max(risk_scores.values())
    for ticker in TICKERS:
        if ticker in risk_scores and risk_scores[ticker] == best:
            return ticker
    raise SignalValidationError("No candidate matched the maximum score.")


@dataclass(frozen=True)
class RiskAdjustedDecisions:
    """Auditable record of every qualifying Phase 2 weekly decision.

    ``raw_scores`` holds trailing 63-day returns, ``volatility`` the
    annualized 21-day volatilities, and ``risk_scores`` the ratio for
    scored candidates (``NaN`` for ETFs whose raw return was not strictly
    positive and were therefore never scored).
    """

    raw_scores: pd.DataFrame
    volatility: pd.DataFrame
    risk_scores: pd.DataFrame
    selections: pd.Series
    targets: pd.DataFrame


def generate_phase2_decisions(prices: pd.DataFrame) -> RiskAdjustedDecisions:
    """Produce every qualifying Phase 2 weekly decision.

    Phase 2 shares Phase 1's qualifying decision dates: the 64 observations
    required by the momentum window exceed the 22 required by the
    volatility window, so the momentum warm-up governs.
    """

    phase1 = generate_phase1_decisions(prices)
    decision_index = phase1.scores.index

    volatility = pd.DataFrame(
        [trailing_volatility(prices, date) for date in decision_index],
        index=decision_index,
    )
    selections = pd.Series(
        [
            select_ticker_risk_adjusted(raw_row, volatility.loc[date])
            for date, raw_row in phase1.scores.iterrows()
        ],
        index=decision_index,
        name="selection",
    )

    risk_scores = pd.DataFrame(
        float("nan"),
        index=decision_index,
        columns=list(TICKERS),
    )
    for date in decision_index:
        for ticker in TICKERS:
            raw = float(phase1.scores.loc[date, ticker])
            if raw > 0.0:
                risk_scores.loc[date, ticker] = raw / float(
                    volatility.loc[date, ticker]
                )

    targets = pd.DataFrame(0.0, index=decision_index, columns=list(TICKERS))
    for date, ticker in selections.items():
        targets.loc[date, ticker] = 1.0

    return RiskAdjustedDecisions(
        raw_scores=phase1.scores,
        volatility=volatility,
        risk_scores=risk_scores,
        selections=selections,
        targets=targets,
    )


def _simulate_targets(
    prices: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    cost_bps: int,
) -> PortfolioSimulation:
    """Shared wiring from decision targets into the portfolio engine.

    The first qualifying decision seeds the uncharged initial allocation and
    measurement begins the next trading day, so the simulated return index
    contains only dates after the first decision close. Later decisions are
    installed as close-date targets; the portfolio engine's locked-period
    guard continues to reject any 2021-2025 evaluation. A final-observation
    decision is dropped because no later return exists for it to affect.
    """

    first_decision = targets.index[0]
    initial_weights = targets.iloc[0]

    asset_returns = calculate_returns(prices)
    measured_returns = asset_returns.loc[asset_returns.index > first_decision]
    if measured_returns.empty:
        raise SignalValidationError(
            "No measured returns exist after the first decision date."
        )

    later_targets = targets.iloc[1:]
    later_targets = later_targets.loc[
        later_targets.index < measured_returns.index[-1]
    ]

    return simulate_portfolio(
        measured_returns,
        initial_weights=initial_weights,
        targets=later_targets,
        cost_bps=cost_bps,
    )


def run_phase1(
    prices: pd.DataFrame,
    *,
    cost_bps: int,
) -> tuple[MomentumDecisions, PortfolioSimulation]:
    """Wire Phase 1 decisions through the existing portfolio engine."""

    decisions = generate_phase1_decisions(prices)
    simulation = _simulate_targets(prices, decisions.targets, cost_bps=cost_bps)
    return decisions, simulation


def run_phase2(
    prices: pd.DataFrame,
    *,
    cost_bps: int,
) -> tuple[RiskAdjustedDecisions, PortfolioSimulation]:
    """Wire Phase 2 decisions through the existing portfolio engine."""

    decisions = generate_phase2_decisions(prices)
    simulation = _simulate_targets(prices, decisions.targets, cost_bps=cost_bps)
    return decisions, simulation
